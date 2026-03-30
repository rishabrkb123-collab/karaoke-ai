# VocalRemover — Free AI Karaoke Maker

Remove vocals from any song instantly using **Demucs** (Meta AI's state-of-the-art audio source separation). Upload a song, get a high-quality karaoke track. 100% free, open source, runs locally.

## Features

- Drag & drop file upload (MP3, WAV, FLAC, M4A, OGG, AAC, WMA, OPUS)
- AI-powered vocal removal using **Demucs htdemucs** model — the best free model available
- Built-in audio preview player before downloading
- Download karaoke track as high-quality WAV
- No quality loss on the instrumental track
- No sign-up, no API keys, no cost

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | Python FastAPI + Uvicorn |
| AI Model | Demucs `htdemucs` (Meta AI, open source) |
| Audio | PyTorch / torchaudio |

## Prerequisites

- **Python 3.9+** — [python.org](https://www.python.org/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **pip** (comes with Python)
- **~2GB disk** for PyTorch + Demucs model on first run

## Quick Start (Windows)

### First time setup:
```
Double-click install.bat
```

### Every subsequent run:
```
Double-click start.bat
```

Then open **http://localhost:3000** in your browser.

## Manual Setup

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (separate terminal)
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**

## How It Works

1. User uploads a song (any common audio format)
2. Backend saves it and runs Demucs with `--two-stems=vocals` flag
3. Demucs uses the `htdemucs` hybrid transformer model to separate:
   - `vocals.wav` — isolated vocals
   - `no_vocals.wav` — everything else (instruments, bass, drums)
4. The `no_vocals.wav` is returned as the karaoke track
5. User previews and downloads it

## Why Demucs?

| Model | Quality | Speed | Cost |
|-------|---------|-------|------|
| Demucs htdemucs | ⭐⭐⭐⭐⭐ | Fast | Free |
| Spleeter | ⭐⭐⭐ | Fastest | Free |
| Commercial APIs | ⭐⭐⭐⭐ | Fast | Paid |

Demucs `htdemucs` (hybrid transformer) is Meta AI's most advanced model — it outperforms Spleeter and matches/exceeds many paid services.

## Testing with YouTube Downloads

If you have the **YouTube Downloader** project at `D:\youtube downloader\`:
1. Download a song using that project
2. Go to http://localhost:3000
3. Upload the downloaded MP3/WAV
4. Get the karaoke track

## Project Structure

```
VocalRemover/
├── backend/
│   ├── main.py          # FastAPI server
│   ├── requirements.txt # Python deps
│   ├── uploads/         # Temp uploaded files (auto-cleaned)
│   └── outputs/         # Processed audio files
├── frontend/
│   ├── src/
│   │   ├── App.jsx      # Main React component
│   │   ├── main.jsx     # Entry point
│   │   └── index.css    # Tailwind + animations
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
├── .gitignore
├── install.bat          # First-time setup
├── start.bat            # Launch app
└── README.md
```

## License

MIT — free to use, modify, and distribute.
