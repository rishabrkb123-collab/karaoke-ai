import { useState, useCallback, useRef } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import {
  Music,
  Upload,
  Download,
  Mic2,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Play,
  Pause,
  Volume2,
} from "lucide-react";

const API_BASE = "/api";
const POLL_INTERVAL = 3000;

const ALLOWED_EXT = [".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma", ".opus"];

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function WaveformAnimation() {
  return (
    <div className="flex items-center gap-1 h-10">
      {[...Array(8)].map((_, i) => (
        <div
          key={i}
          className="waveform-bar w-1.5 rounded-full bg-brand-400"
          style={{ height: "100%" }}
        />
      ))}
    </div>
  );
}

function AudioPlayer({ src, filename }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const toggle = () => {
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setPlaying(!playing);
  };

  const formatTime = (s) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  return (
    <div className="glass rounded-2xl p-4 flex flex-col gap-3">
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.target.duration)}
        onEnded={() => setPlaying(false)}
      />
      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          className="w-10 h-10 rounded-full bg-brand-500 hover:bg-brand-600 flex items-center justify-center flex-shrink-0 transition-colors"
        >
          {playing ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
        </button>
        <div className="flex-1">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={duration || 1}
            value={currentTime}
            onChange={(e) => {
              audioRef.current.currentTime = e.target.value;
              setCurrentTime(Number(e.target.value));
            }}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-white/10"
            style={{
              background: `linear-gradient(to right, #4f6ef7 ${(currentTime / (duration || 1)) * 100}%, rgba(255,255,255,0.1) 0%)`,
            }}
          />
        </div>
        <Volume2 size={16} className="text-gray-400 flex-shrink-0" />
      </div>
      <p className="text-xs text-gray-400 truncate">{filename}</p>
    </div>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | uploading | processing | done | error
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(0);
  const [downloadFilename, setDownloadFilename] = useState("");
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [device, setDevice] = useState(null);
  const pollRef = useRef(null);

  const reset = () => {
    setFile(null);
    setJobId(null);
    setStatus("idle");
    setError(null);
    setProgress(0);
    setDownloadFilename("");
    setDevice(null);
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    setDownloadUrl(null);
    if (pollRef.current) clearInterval(pollRef.current);
  };

  const startPolling = useCallback((id) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE}/status/${id}`);
        const data = res.data;

        if (data.device) setDevice(data.device);

        if (data.status === "done") {
          clearInterval(pollRef.current);
          setDownloadFilename(data.filename || "karaoke.wav");

          // Fetch the file as blob for preview + download
          const fileRes = await axios.get(`${API_BASE}/download/${id}`, {
            responseType: "blob",
          });
          const blob = new Blob([fileRes.data], { type: "audio/wav" });
          const url = URL.createObjectURL(blob);
          setDownloadUrl(url);
          setStatus("done");
        } else if (data.status === "error") {
          clearInterval(pollRef.current);
          setError(data.error || "An unknown error occurred during processing.");
          setStatus("error");
        } else {
          // Still processing — animate progress
          setProgress((p) => Math.min(p + 3, 90));
        }
      } catch (err) {
        clearInterval(pollRef.current);
        const msg = err?.response?.data?.detail || "Lost connection to server. Please try again.";
        setError(msg);
        setStatus("error");
      }
    }, POLL_INTERVAL);
  }, []);

  const processFile = useCallback(async (selectedFile) => {
    setFile(selectedFile);
    setStatus("uploading");
    setError(null);
    setProgress(5);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await axios.post(`${API_BASE}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          const pct = Math.max(5, Math.round((e.loaded / e.total) * 40));
          setProgress(pct);
        },
      });

      setJobId(res.data.job_id);
      setStatus("processing");
      setProgress(45);
      startPolling(res.data.job_id);
    } catch (err) {
      const msg = err?.response?.data?.detail || "Upload failed. Please try again.";
      setError(msg);
      setStatus("error");
    }
  }, [startPolling]);

  const onDrop = useCallback(
    (acceptedFiles) => {
      if (status !== "idle") return;
      const f = acceptedFiles[0];
      if (!f) return;
      const ext = "." + f.name.split(".").pop().toLowerCase();
      if (!ALLOWED_EXT.includes(ext)) {
        setError(`Unsupported format. Please upload: ${ALLOWED_EXT.join(", ")}`);
        setStatus("error");
        return;
      }
      processFile(f);
    },
    [status, processFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "audio/*": ALLOWED_EXT },
    maxFiles: 1,
    disabled: status !== "idle",
  });

  const handleDownload = () => {
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = downloadFilename;
    a.click();
  };

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-white/5 px-6 py-4 flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-brand-500 flex items-center justify-center">
          <Mic2 size={20} />
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-tight">VocalRemover</h1>
          <p className="text-xs text-gray-400">Free AI-powered karaoke maker</p>
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
          <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
          Powered by Demucs (Meta AI)
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center px-4 py-12 gap-8">
        <div className="text-center max-w-xl">
          <h2 className="text-4xl font-extrabold tracking-tight mb-3 bg-gradient-to-r from-brand-400 to-purple-400 bg-clip-text text-transparent">
            Remove Vocals Instantly
          </h2>
          <p className="text-gray-400 text-lg">
            Upload any song — get a studio-quality karaoke track in minutes.
            100% free, no sign-up required.
          </p>
        </div>

        {/* Upload / Processing / Result Card */}
        <div className="w-full max-w-2xl space-y-5">

          {/* Dropzone */}
          {status === "idle" && (
            <div
              {...getRootProps()}
              className={`glass rounded-3xl p-12 flex flex-col items-center gap-5 cursor-pointer transition-all duration-200
                ${isDragActive ? "border-brand-400 bg-brand-500/10 scale-[1.01]" : "hover:border-white/20 hover:bg-white/5"}`}
            >
              <input {...getInputProps()} />
              <div className="w-20 h-20 rounded-2xl bg-brand-500/15 flex items-center justify-center">
                <Upload size={36} className="text-brand-400" />
              </div>
              <div className="text-center">
                <p className="text-lg font-semibold">
                  {isDragActive ? "Drop your song here" : "Drag & drop your song"}
                </p>
                <p className="text-gray-400 text-sm mt-1">or click to browse files</p>
                <p className="text-gray-500 text-xs mt-3">
                  Supports MP3, WAV, FLAC, M4A, OGG, AAC — up to any size
                </p>
              </div>
              <button className="mt-2 px-6 py-2.5 bg-brand-500 hover:bg-brand-600 rounded-xl font-medium text-sm transition-colors">
                Choose File
              </button>
            </div>
          )}

          {/* Uploading */}
          {status === "uploading" && (
            <div className="glass rounded-3xl p-10 flex flex-col items-center gap-5">
              <div className="w-16 h-16 rounded-2xl bg-brand-500/15 flex items-center justify-center">
                <Upload size={30} className="text-brand-400 animate-bounce" />
              </div>
              <div className="text-center">
                <p className="font-semibold text-lg">Uploading...</p>
                <p className="text-gray-400 text-sm mt-1 truncate max-w-xs">{file?.name}</p>
                <p className="text-gray-500 text-xs">{file && formatSize(file.size)}</p>
              </div>
              <div className="w-full bg-white/10 rounded-full h-2">
                <div
                  className="bg-brand-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-gray-400 text-sm">{progress}%</p>
            </div>
          )}

          {/* Processing */}
          {status === "processing" && (
            <div className="glass rounded-3xl p-10 flex flex-col items-center gap-5">
              <WaveformAnimation />
              <div className="text-center">
                <p className="font-semibold text-xl">Removing Vocals...</p>
                <p className="text-gray-400 text-sm mt-2">
                  AI is separating your vocals from the instrumental track.
                </p>
                <p className="text-gray-500 text-xs mt-1">
                  {device === "cuda"
                    ? "GPU detected — under 1 min with high-quality mode (shifts=2)."
                    : "CPU mode — typically 5–10 min for a 4-minute song."}
                </p>
              </div>
              <div className="w-full bg-white/10 rounded-full h-2">
                <div
                  className="bg-gradient-to-r from-brand-500 to-purple-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <RefreshCw size={12} className="animate-spin" />
                High-quality mode: htdemucs_ft + shift ensemble
              </div>
            </div>
          )}

          {/* Done */}
          {status === "done" && (
            <div className="glass rounded-3xl p-8 flex flex-col gap-5">
              <div className="flex items-center gap-3">
                <CheckCircle size={28} className="text-green-400 flex-shrink-0" />
                <div>
                  <p className="font-bold text-lg">Vocals Removed!</p>
                  <p className="text-gray-400 text-sm">
                    Your karaoke track is ready — preview and download below.
                  </p>
                </div>
              </div>

              {/* Audio Preview */}
              {downloadUrl && (
                <AudioPlayer src={downloadUrl} filename={downloadFilename} />
              )}

              <div className="flex gap-3">
                <button
                  onClick={handleDownload}
                  className="flex-1 flex items-center justify-center gap-2 py-3 bg-brand-500 hover:bg-brand-600 rounded-xl font-semibold text-sm transition-colors"
                >
                  <Download size={18} />
                  Download Karaoke Track
                </button>
                <button
                  onClick={reset}
                  className="px-4 py-3 glass rounded-xl hover:bg-white/10 text-sm transition-colors"
                >
                  New Song
                </button>
              </div>

              <div className="text-xs text-gray-500 flex items-center gap-2">
                <Music size={12} />
                Output: {downloadFilename} — High quality WAV, vocals fully removed
              </div>
            </div>
          )}

          {/* Error */}
          {status === "error" && (
            <div className="glass rounded-3xl p-8 flex flex-col gap-5 border-red-500/20">
              <div className="flex items-start gap-3">
                <AlertCircle size={24} className="text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold text-red-300">Something went wrong</p>
                  <p className="text-gray-400 text-sm mt-1">{error}</p>
                </div>
              </div>
              <button
                onClick={reset}
                className="w-full py-3 glass rounded-xl hover:bg-white/10 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
            </div>
          )}
        </div>

        {/* How it works */}
        {status === "idle" && (
          <div className="w-full max-w-2xl mt-4">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4 text-center">
              How it works
            </h3>
            <div className="grid grid-cols-3 gap-4">
              {[
                { icon: Upload, title: "Upload Song", desc: "Any format — MP3, WAV, FLAC, M4A…" },
                { icon: Mic2, title: "AI Processes", desc: "Demucs separates vocals from instruments" },
                { icon: Download, title: "Download", desc: "Get your karaoke WAV, no quality loss" },
              ].map(({ icon: Icon, title, desc }) => (
                <div key={title} className="glass rounded-2xl p-4 text-center">
                  <div className="w-10 h-10 rounded-xl bg-brand-500/15 flex items-center justify-center mx-auto mb-3">
                    <Icon size={20} className="text-brand-400" />
                  </div>
                  <p className="font-semibold text-sm mb-1">{title}</p>
                  <p className="text-gray-500 text-xs">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-white/5 px-6 py-4 text-center text-xs text-gray-600">
        VocalRemover — Free, open source. Powered by{" "}
        <a
          href="https://github.com/facebookresearch/demucs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-brand-400 hover:underline"
        >
          Demucs by Meta AI
        </a>
        .
      </footer>
    </div>
  );
}
