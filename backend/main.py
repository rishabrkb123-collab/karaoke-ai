import sys
import uuid
import shutil
import subprocess
import threading
from pathlib import Path
import torch
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="VocalRemover API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# In-memory job store
jobs: dict = {}

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus"}


def run_demucs(job_id: str, input_path: Path):
    try:
        jobs[job_id]["status"] = "processing"
        job_output_dir = OUTPUT_DIR / job_id

        # Use GPU if available — dramatically faster (< 1 min vs 5-10 min on CPU)
        device = "cuda" if torch.cuda.is_available() else "cpu"

        # htdemucs_ft = fine-tuned model, cleaner separation than base htdemucs
        # --shifts=2 averages two time-shifted predictions: less vocal bleed + fewer artifacts
        #   On GPU: fast enough to always use shifts
        #   On CPU: skip shifts to keep time reasonable (~5-8 min instead of 10-16 min)
        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems=vocals",
            "-n", "htdemucs_ft",
            "-d", device,
            "--overlap=0.25",
            "-o", str(job_output_dir),
        ]
        if device == "cuda":
            cmd += ["--shifts=2"]

        cmd.append(str(input_path))

        # Store device info so the status endpoint can report it
        jobs[job_id]["device"] = device

        timeout = 300 if device == "cuda" else 1800  # 5 min GPU / 30 min CPU
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            # Demucs sometimes writes errors to stdout instead of stderr
            error_detail = result.stderr.strip() or result.stdout.strip() or "Demucs processing failed"
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = error_detail
            return

        # Demucs outputs: job_output_dir/htdemucs_ft/<input_stem>/no_vocals.wav
        input_stem = input_path.stem  # includes job_id prefix
        no_vocals_path = job_output_dir / "htdemucs_ft" / input_stem / "no_vocals.wav"

        if not no_vocals_path.exists():
            # Search anywhere under the job output dir in case the path differs slightly
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

        # Clean download filename: use original song name (stored in job dict)
        original_stem = Path(jobs[job_id]["original_name"]).stem
        clean_name = "".join(c for c in original_stem if c.isalnum() or c in " _-").strip() or "song"
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
        # Clean up uploaded file
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/api/upload")
async def upload_song(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    job_id = str(uuid.uuid4())
    # Sanitize filename — no spaces to avoid path mismatches on Windows
    safe_name = "".join(c for c in Path(file.filename).stem if c.isalnum() or c in "_-").strip()
    safe_name = safe_name.replace(" ", "_") or "song"
    input_path = UPLOAD_DIR / f"{job_id}_{safe_name}{ext}"

    # Save uploaded file using async read to avoid blocking the event loop
    content = await file.read()
    with open(input_path, "wb") as f:
        f.write(content)

    jobs[job_id] = {
        "status": "queued",
        "original_name": file.filename,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }

    # Run demucs in background thread
    thread = threading.Thread(target=run_demucs, args=(job_id, input_path), daemon=True)
    thread.start()

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return {
        "status": job["status"],
        "error": job.get("error"),
        "filename": job.get("filename"),
        "device": job.get("device"),
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

    job = jobs[job_id]
    # Remove output directory for this job
    job_output_dir = OUTPUT_DIR / job_id
    if job_output_dir.exists():
        shutil.rmtree(job_output_dir, ignore_errors=True)

    del jobs[job_id]
    return {"message": "Cleaned up"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve React frontend (for production)
frontend_build = BASE_DIR.parent / "frontend" / "dist"
if frontend_build.exists():
    app.mount("/", StaticFiles(directory=str(frontend_build), html=True), name="frontend")
