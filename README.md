# Video Analyzer Web

> **Version 3.5.0**

A web-based GUI for video-analyzer with multi-provider AI support (Ollama and OpenRouter), multi-GPU VRAM-aware job queueing, LLM chat queue, real-time monitoring, cost estimation, and automatic video transcoding.

## Changelog

### v3.5.0 (2026-04-23) - Critical Bug Fix: Transcript Handling

- **Fixed**: Critical bug causing job failures with "'dict' object has no attribute 'text'" error
- **Improved**: Robust transcript handling with safe access functions for all transcript data types
- **Fixed**: Transcript loading logic to handle dictionaries, objects, and None values consistently
- **Enhanced**: Error recovery for transcript format variations

### v0.3.4 (2026-04-22) - Transcription Flow Fixes
- **Fixed**: Consistent transcript loading between frontend and workers
- **Added**: Shared transcript utilities in `src/utils/transcript.py`
- **Improved**: Transcript injection with fallback for missing prompt tokens
- **Enhanced**: Better validation of transcript segments with missing fields
- **Fixed**: Path resolution for deduped videos with `_dedup` suffix

### v0.3.2 (2026-04-19)
- Various bug fixes and improvements

### v0.3.1 (2026-04-18)
- Initial public release

## Features

- **Multi-Provider Support**: Ollama (local/remote) and OpenRouter (cloud) with dynamic model loading
- **Multi-GPU Support**: Distributes jobs across multiple GPUs with per-GPU VRAM tracking and job limits
- **VRAM-Aware Queueing**: Intelligently queues jobs based on GPU memory availability, accounting for already-loaded Ollama models
- **LLM Chat Queue**: Rate-limited queue for standalone LLM chat requests (separate from video analysis)
- **Auto-LLM Analysis**: Optionally runs a follow-up LLM prompt against analysis results (transcript, description, frame analyses)
- **Reasoning Model Compatibility**: Patches Ollama `/api/chat` with `think:false` to prevent reasoning/thinking models from consuming all tokens
- **Cost Estimation**: Real-time cost estimates for OpenRouter with budget validation and pricing cache
- **System Monitoring**: Live nvidia-smi and Ollama `/api/ps` updates via structured GPU stats
- **Auto-Transcoding**: Uploaded videos are automatically transcoded to 720p@1fps with source cleanup
- **GPU Encoder Detection**: Detects NVENC/QSV/VAAPI encoders with CPU fallback (libx264 with thread optimization)
- **Real-time Updates**: WebSocket-powered live frame analysis display with auto-reconnect
- **Job Management**: Priority-based queueing, per-GPU concurrent jobs, cancel/update priority
- **Stored Results**: Browse and retrieve completed analysis results via API
- **File Security**: Path traversal protection, filename sanitization, upload size validation (1GB max)
- **Standalone Dedup**: Run frame deduplication independently before analysis to test different thresholds and see frame drop-off without running full analysis
- **Transcript-Aware Analysis**: Injects relevant transcript context (from last analyzed frame to current+3s) into each frame's LLM prompt for richer, context-aware analysis with robust path resolution and fallback injection
- **Live Frame Preview**: Displays actual frame thumbnails alongside analysis output in the live view, with original (pre-dedup) frame numbers and timestamps

## Quick Start

### Prerequisites

- Docker with Docker Compose plugin
- NVIDIA Docker runtime (for GPU support)
- At least one Ollama instance or OpenRouter API key

### Docker Installation

```bash
# Clone the directory
mkdir -p ~/video-analyzer-web
cd ~/video-analyzer-web

# Start the service
./start.sh
```

Or manually:

```bash
docker compose up --build -d
```

### Direct Installation (No Docker)

```bash
pip3 install -r requirements.txt
./run.sh
```

This runs the app directly on port 10000.

### Docker Installation

```bash
# Clone the directory
mkdir -p ~/video-analyzer-web
cd ~/video-analyzer-web

# Start the service
./start.sh
```

Or manually:

```bash
docker compose up --build -d
```

### Direct Installation (No Docker)

```bash
pip3 install -r requirements.txt
./run.sh
```

This runs the app directly on port 10000.

### Access

- Docker: http://localhost:10000
- Direct: http://localhost:10000
- Accessible from local network at http://your-ip:10000

## Configuration

### Ollama Setup

1. Ensure Ollama is running on your machine or network
2. The app auto-discovers Ollama instances on your subnet, or you can add manually
3. VRAM estimation uses model size + 2GB overhead for KV cache
4. Already-loaded models are detected via `/api/ps` and only 1GB context overhead is required

### OpenRouter Setup

1. Get an API key from [openrouter.ai](https://openrouter.ai)
2. Enter the API key in the web interface when selecting OpenRouter
3. Your balance will be displayed and validated before starting analysis
4. Pricing data is cached for 1 hour

### Default Configuration

See `config/default_config.json` for defaults:

- Default Ollama model: `gemma4-180k`
- Default OpenRouter model: `meta-llama/llama-3.2-11b-vision-instruct`
- Default Whisper model: `large`
- Default frames per minute: 60
- Default temperature: 0.0

### GPU Support

The Docker container includes NVIDIA runtime support. Ensure you have:

```bash
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

The app supports **multiple GPUs** and assigns jobs to the GPU with the most available VRAM. Up to 2 concurrent jobs per GPU are allowed.

## Usage

1. **Upload Video**: Drag & drop or click to upload a video file (auto-transcoded to 720p@1fps)
2. **Select Provider**: Choose an Ollama instance or OpenRouter
3. **Select Model**: Models are dynamically loaded from the provider
4. **Configure**: Set max frames, duration, whisper model, temperature, etc.
5. **Optional Prompt**: Enter a custom prompt for automatic LLM analysis after video analysis completes
6. **Start Analysis**: Click "Start Analysis" to begin

### VRAM Queueing

- Jobs requiring more VRAM than available are queued
- Queue is processed automatically when VRAM becomes available (every 5 seconds)
- Already-loaded Ollama models only need 1GB context overhead instead of full model size
- Up to 2 concurrent jobs per GPU if VRAM permits
- Smaller VRAM jobs can run ahead of larger queued jobs if they fit
- Manually set job priority to control queue order

### LLM Chat Queue

- Standalone LLM chat requests are handled by a separate rate-limited queue
- Up to 5 concurrent chat jobs, 30 requests per minute
- Priority-based ordering (higher priority runs first)
- Supports both Ollama and OpenRouter providers

### Cost Estimation (OpenRouter)

- Cost is estimated based on frame count before starting
- System checks your API balance against estimated cost
- If insufficient funds, suggests max affordable frames
- Token usage tracked per job for actual cost calculation

### Auto-Transcoding

Uploaded videos are automatically transcoded on upload:

- Resolution: 720p (1280x720)
- Frame rate: 1 fps (optimized for analysis)
- Encoder: CPU (libx264) with thread optimization (GPU encoding disabled for driver compatibility)
- Audio: AAC 128kbps @ 44100Hz
- Source file is deleted after successful transcode
- Output naming: `{original}_720p1fps.mp4`

## API Endpoints

### Videos

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/videos` | GET | List uploaded videos with metadata |
| `/api/videos/upload` | POST | Upload video file (auto-transcodes) |
| `/api/videos/<filename>` | DELETE | Delete video, thumbnail, and associated jobs |
| `/api/videos/transcode` | POST | Manually trigger transcode for uploaded video |
| `/api/videos/<filename>/dedup` | POST | Run deduplication with given threshold |
| `/api/videos/<filename>/dedup` | GET | Get stored dedup results |
| `/api/videos/<filename>/dedup` | DELETE | Clear dedup results and restore original frames |
| `/api/thumbnail/<filename>` | GET | Get video thumbnail |

### Providers

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/providers` | GET | List configured providers |
| `/api/providers/discover` | GET | Trigger Ollama subnet discovery scan |
| `/api/providers/ollama/models` | GET | Get models from Ollama server |
| `/api/providers/openrouter/models` | GET | Get models from OpenRouter |
| `/api/providers/openrouter/cost` | GET | Estimate cost for analysis |
| `/api/providers/openrouter/balance` | GET | Get OpenRouter API key balance |

### Jobs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jobs` | GET | List all jobs |
| `/api/jobs/running` | GET | List running jobs |
| `/api/jobs/queued` | GET | List queued jobs |
| `/api/jobs/<id>` | GET | Get job details |
| `/api/jobs/<id>` | DELETE | Cancel a job (kills entire process group) |
| `/api/jobs/<id>/frames` | GET | Get frame analyses with pagination |
| `/api/jobs/<id>/results` | GET | Get final analysis results |
| `/api/jobs/<id>/priority` | POST | Update job priority |

### System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/vram` | GET | Current VRAM status for all GPUs |
| `/api/gpus` | GET | List all GPUs with details |

### LLM Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/llm/chat` | POST | Submit chat request to queue |
| `/api/llm/chat/<job_id>` | GET | Get chat job status |
| `/api/llm/chat/<job_id>` | DELETE | Cancel a chat job |
| `/api/llm/queue/stats` | GET | Get chat queue statistics |

### Stored Results

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/results` | GET | List all completed jobs with stored results |

## Directory Structure

```
~/video-analyzer-web/
├── app.py              # Main Flask application
├── worker.py            # Video analysis worker subprocess
├── chat_queue.py        # LLM chat queue manager
├── vram_manager.py      # Multi-GPU VRAM-aware job scheduler
├── monitor.py           # System monitor (nvidia-smi, Ollama ps)
├── discovery.py          # Ollama network discovery scanner
├── gpu_transcode.py      # GPU/CPU transcoding with encoder detection
├── thumbnail.py          # Video thumbnail extraction
├── providers/            # AI provider implementations
│   ├── base.py           # Base provider class
│   ├── ollama.py         # Ollama provider
│   └── openrouter.py     # OpenRouter provider with pricing
├── src/utils/            # Utility modules
│   ├── file.py           # File validation, security, path verification
│   └── transcode.py      # Video probing and metadata utilities
├── config/               # Configuration
│   ├── constants.py      # Application constants
│   ├── default_config.json  # Default video-analyzer config
│   └── paths.py           # Path configuration
├── templates/            # HTML templates
├── static/               # CSS and JS assets
├── tests/                # Test suite (unit, integration, e2e)
├── uploads/              # Uploaded videos
├── uploads/thumbs/       # Video thumbnails
├── jobs/                 # Job working directories
├── cache/                # Cached data (OpenRouter pricing)
└── output/               # Analysis results
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Default Ollama host |
| `NVIDIA_VISIBLE_DEVICES` | `all` | GPU visibility |
| `APP_URL` | `http://localhost:10000` | App URL for internal API calls (auto-LLM) |
| `APP_ROOT` | `.` | Application root directory |
| `PYTHONUNBUFFERED` | `1` | Unbuffered Python output |

## Architecture

- **Backend**: Flask + Flask-SocketIO (Python 3.11)
- **Frontend**: Vanilla JS + Socket.IO client
- **Server**: Gunicorn + Eventlet async worker (Docker), direct Flask-SocketIO (development)
- **GPU**: NVML (pynvml) for VRAM monitoring, CUDA for Whisper transcription
- **Video**: FFmpeg for transcoding and thumbnail extraction
- **Container**: NVIDIA Docker runtime for GPU passthrough
- **Job Queue**: In-memory VRAM-aware priority queue with multi-GPU assignment
- **Chat Queue**: Separate rate-limited queue for LLM chat requests
- **State**: Filesystem-based job persistence (status.json, frames.jsonl, results.json)
- **Workers**: Subprocess isolation with process group tracking for clean cancellation

## Troubleshooting

### No GPU detected

Ensure nvidia-docker2 is installed and Docker daemon is restarted. The app gracefully degrades to CPU mode.

### Ollama not discovered

- Check Ollama is running: `ollama serve`
- Try accessing directly: `curl http://localhost:11434/api/tags`
- Add manually via "Custom..." option
- Discovery scans your subnet (takes ~30 seconds)

### OpenRouter balance shows 0

- Verify API key is correct
- Check key has credit at openrouter.ai

### Jobs stuck in queue

- Check VRAM usage in System Status panel
- Ensure no zombie processes are holding GPU memory
- Check logs: `docker compose logs -f`
- Verify already-loaded models are detected via Ollama `/api/ps`

### Reasoning models return empty responses

The worker patches Ollama `/api/chat` with `think:false` to prevent reasoning models (qwen3, deepseek-r1, etc.) from consuming all tokens on thinking blocks. If issues persist, try a non-reasoning model.

### Transcoding issues

- GPU encoding is currently disabled; CPU (libx264) is used as a fallback
- Transcoding timeout is 1 hour
- Check logs for FFmpeg errors

## License

MIT License - See original video-analyzer project for details.
