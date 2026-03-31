import sys
import uuid
import shutil
import subprocess
import threading
import time
import asyncio
from pathlib import Path
from collections import deque
from contextlib import asynccontextmanager
import torch
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ── Device: checked once at startup, never again ─────────────────────────────
# torch.cuda.is_available() is expensive (~50ms). Caching it avoids paying
# that cost on every upload request.
DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

# ── Job serialization ─────────────────────────────────────────────────────────
# Running two Demucs jobs simultaneously doesn't halve time — it thrashes CPU
# and doubles memory usage per job. A semaphore(1) serializes jobs so the
# second job waits rather than competing. A deque tracks waiting job_ids so
# the status endpoint can report queue position to the frontend.
_processing_sem = threading.Semaphore(1)
_queue_lock = threading.Lock()
_job_queue: deque = deque()

# ── In-memory job store ───────────────────────────────────────────────────────
jobs: dict = {}

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus"}
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB — max RAM held at once during upload


# ── Auto-cleanup background task ─────────────────────────────────────────────
# Without this, the jobs dict and outputs/ directory grow forever.
# Every hour, any job that finished more than 2 hours ago is removed from
# memory and its output directory is deleted from disk.
async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        cutoff = time.time() - 7200  # 2-hour TTL
        for jid in list(jobs.keys()):
            job = jobs.get(jid)
            if (
                job
                and job["status"] in ("done", "error")
                and job.get("created_at", 0) < cutoff
            ):
                shutil.rmtree(OUTPUT_DIR / jid, ignore_errors=True)
                jobs.pop(jid, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="VocalRemover API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Core processing ───────────────────────────────────────────────────────────

def run_demucs(job_id: str, input_path: Path) -> None:
    """Run Demucs. Must only be called after acquiring _processing_sem."""
    try:
        jobs[job_id]["status"] = "processing"
        job_output_dir = OUTPUT_DIR / job_id

        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems=vocals",
            "-n", "htdemucs_ft",
            "-d", DEVICE,
            "--overlap=0.25",
            "-o", str(job_output_dir),
        ]
        if DEVICE == "cuda":
            # GPU is fast enough to afford shift-ensemble for better quality
            cmd += ["--shifts=2"]
        cmd.append(str(input_path))

        timeout = 300 if DEVICE == "cuda" else 1800
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            error_detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or "Demucs processing failed"
            )
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = error_detail
            return

        input_stem = input_path.stem
        no_vocals_path = job_output_dir / "htdemucs_ft" / input_stem / "no_vocals.wav"

        if not no_vocals_path.exists():
            found = list(job_output_dir.rglob("no_vocals.wav"))
            if found:
                no_vocals_path = found[0]
            else:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = (
                    f"no_vocals.wav not found after processing. "
                    f"stdout: {result.stdout.strip()[:300]}"
                )
                return

        original_stem = Path(jobs[job_id]["original_name"]).stem
        clean_name = (
            "".join(c for c in original_stem if c.isalnum() or c in " _-").strip()
            or "song"
        )
        jobs[job_id]["status"] = "done"
        jobs[job_id]["output_file"] = str(no_vocals_path)
        jobs[job_id]["filename"] = f"{clean_name}_karaoke.wav"

    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = "Processing timed out (file may be too large)"
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
    finally:
        # Always delete the temp upload — even on error
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass


def run_demucs_worker(job_id: str, input_path: Path) -> None:
    """Serializes jobs: waits for the semaphore, removes itself from the
    visible queue, then runs Demucs. This is the thread target."""
    _processing_sem.acquire()          # blocks here if another job is running
    with _queue_lock:
        try:
            _job_queue.remove(job_id)  # no longer waiting — about to run
        except ValueError:
            pass
    try:
        run_demucs(job_id, input_path)
    finally:
        _processing_sem.release()


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_song(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    job_id = str(uuid.uuid4())
    safe_name = (
        "".join(c for c in Path(file.filename).stem if c.isalnum() or c in "_-").strip()
        or "song"
    )
    input_path = UPLOAD_DIR / f"{job_id}_{safe_name}{ext}"

    # Chunked write: holds at most UPLOAD_CHUNK_SIZE bytes in RAM at once.
    # The old `content = await file.read()` loaded the entire file (can be
    # 50–200 MB for uncompressed WAV) into Python memory before writing.
    with open(input_path, "wb") as f:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)

    jobs[job_id] = {
        "status": "queued",
        "original_name": file.filename,
        "device": DEVICE,
        "created_at": time.time(),
    }

    with _queue_lock:
        _job_queue.append(job_id)

    thread = threading.Thread(
        target=run_demucs_worker, args=(job_id, input_path), daemon=True
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]

    # Compute queue position only for queued jobs — O(n) on the deque but
    # the queue will rarely have more than a handful of entries.
    queue_position = None
    if job["status"] == "queued":
        with _queue_lock:
            try:
                queue_position = list(_job_queue).index(job_id) + 1
            except ValueError:
                queue_position = None

    return {
        "status": job["status"],
        "error": job.get("error"),
        "filename": job.get("filename"),
        "device": job.get("device"),
        "queue_position": queue_position,
    }


@app.get("/api/download/{job_id}")
async def download_result(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="File not ready yet")

    output_file = Path(job["output_file"])
    if not output_file.exists():
        raise HTTPException(status_code=404, detail="Output file missing")

    return FileResponse(
        path=str(output_file),
        filename=job["filename"],
        media_type="audio/wav",
    )


@app.delete("/api/cleanup/{job_id}")
async def cleanup_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    shutil.rmtree(OUTPUT_DIR / job_id, ignore_errors=True)
    del jobs[job_id]
    return {"message": "Cleaned up"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve React frontend (production build)
frontend_build = BASE_DIR.parent / "frontend" / "dist"
if frontend_build.exists():
    app.mount("/", StaticFiles(directory=str(frontend_build), html=True), name="frontend")
