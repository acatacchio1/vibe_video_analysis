# Development Guide

This document provides technical architecture and development guidelines for Video Analyzer Web.

## Architecture Overview

### Tech Stack
- **Backend**: Flask + Flask-SocketIO (eventlet driver)
- **Frontend**: Vanilla JS (modular, no framework/bundler), CSS custom properties
- **AI Providers**: Ollama (local), OpenRouter (cloud)
- **ML**: faster-whisper (transcription), imagehash (frame dedup)
- **Video**: ffmpeg/ffprobe for transcoding, frame extraction, audio extraction
- **GPU**: NVIDIA CUDA, pynvml for VRAM monitoring
- **Deployment**: Docker (nvidia/cuda base), docker-compose

### Key Design Decisions

1. **Port 10000** - All services run on port 10000 (non-privileged, Docker maps 10000:10000)
2. **Source videos preserved** - Upload transcodes to 720p but keeps original
3. **Whisper models baked into Docker image** - HF cache at `/root/.cache/huggingface` (NOT under volume mount)
4. **Compute type**: `float16` for CUDA, `int8` for CPU (in `app.py` transcribe)
5. **Job execution**: VRAM-aware scheduler → spawns worker subprocess per job
6. **Real-time updates**: SocketIO for job progress, frame analysis, system monitoring, server logs
7. **Frame renumbering**: After dedup, frames are renumbered sequentially with `frames_index.json` mapping to video timestamps
8. **OpenWebUI Knowledge Base sync**: Results auto-synced to OpenWebUI KB via REST API

## Directory Structure

```
video-analyzer-web/
├── app.py                          # Flask entry point (~700 lines)
│   ├── Flask app + SocketIO setup
│   ├── Blueprint registration (src/api/*)
│   ├── SocketIO handler registration (src/websocket/*)
│   ├── SocketLogHandler - emits logs to UI via SocketIO
│   ├── spawn_worker() / monitor_job() - worker lifecycle
│   ├── VRAM manager + monitor callbacks
│   └── _transcode_and_delete_with_cleanup(), _extract_frames(), _transcribe_video()
│
├── worker.py                       # Worker entry shim → src.worker.main
├── vram_manager.py                 # GPU-aware job scheduler (external, DO NOT modify)
├── chat_queue.py                   # LLM chat queue manager (external, DO NOT modify)
├── monitor.py                      # System monitor (nvidia-smi, ollama ps)
├── discovery.py                    # Ollama network discovery
├── thumbnail.py                    # Thumbnail extraction
├── gpu_transcode.py               # ffmpeg transcode command builder
│
├── providers/
│   ├── base.py                     # Abstract provider interface
│   ├── ollama.py                   # Ollama provider implementation
│   └── openrouter.py               # OpenRouter provider implementation
│
├── config/
│   ├── constants.py                # MAX_FILE_SIZE, VRAM_BUFFER, etc.
│   ├── paths.py                    # UPLOAD_DIR, JOBS_DIR, THUMBS_DIR, etc.
│   └── default_config.json
│
├── src/                            # Refactored modules (v0.2.0+)
│   ├── api/                        # Flask blueprints (routes only)
│   │   ├── videos.py               # /api/videos, upload, delete, frames, transcript, frames_index
│   │   ├── providers.py            # /api/providers, discover, models, cost, balance
│   │   ├── jobs.py                 # /api/jobs, cancel, priority, results
│   │   ├── llm.py                  # /api/llm/chat, queue stats
│   │   ├── results.py              # /api/results (stored results browser)
│   │   ├── system.py               # /api/vram, /api/gpus
│   │   ├── transcode.py            # /api/videos/transcode, /api/videos/reprocess
│   │   └── knowledge.py            # /api/knowledge/sync, /api/knowledge/config, /api/knowledge/test
│   │
│   ├── websocket/
│   │   └── handlers.py             # SocketIO events (connect, subscribe_job, start_analysis)
│   │
│   ├── worker/
│   │   ├── __init__.py             # Re-exports run_analysis
│   │   └── main.py                 # Worker: stages (frames → transcript → description → results)
│   │
│   ├── utils/
│   │   ├── helpers.py              # format_bytes(), format_duration(), map_exit_code_to_status()
│   │   ├── security.py             # secure_filename(), allowed_file(), verify_path()
│   │   ├── video.py                # get_video_duration(), probe_video(), probe_all_videos()
│   │   └── transcript.py           # Transcript loading utilities (v0.3.4+)
│   │
│   ├── services/
│   │   └── openwebui_kb.py         # OpenWebUI Knowledge Base API client
│   │
└── static/
    ├── css/style.css               # All styles (merged from style-additions.css)
    └── js/
        ├── app.js                  # Module loader (was 2267-line monolith)
        └── modules/
            ├── state.js            # Global state object, localStorage helpers
            ├── socket.js           # Socket.IO connection, event registrations
            ├── videos.js           # Upload, list, delete, reprocess, transcode progress, server log
            ├── providers.js        # Discovery, model loading, OpenRouter key/balance
            ├── jobs.js             # Job rendering, cancellation, details modal
            ├── llm.js              # LLM chat (live/modal/results contexts), polling
            ├── frame-browser.js    # Frame range sliders, thumbnails, transcript context (timestamp-aware)
            ├── system.js           # GPU status display, monitor tabs
            ├── results.js          # Stored results browser, detail view
            ├── settings.js         # Settings persistence, toggle handlers
            ├── knowledge.js        # OpenWebUI KB settings, test, sync
            ├── ui.js               # Toasts, modals, escapeHtml, formatFrameAnalysis
            └── init.js             # DOMContentLoaded bootstrap, event wiring
```

## Core Components

### 1. Application Entry Point (`app.py`)
- **Monolithic Flask app** - Needs refactoring into factory pattern
- **SocketIO setup** - Real-time communication with clients
- **VRAM manager integration** - GPU-aware job scheduling
- **Worker spawning** - Subprocess management for job execution
- **Log handler** - SocketLogHandler emits logs to UI

### 2. Worker System (`worker.py`, `src/worker/main.py`)
**Job stages:**
1. Frame extraction and deduplication
2. Transcript loading (via `src/utils/transcript.py`)
3. Frame analysis with AI providers
4. Video description generation
5. Results compilation and storage
6. OpenWebUI KB sync (if configured)

**Key functions:**
- `safe_get_transcript_text()` - Robust transcript access (v3.5.0+)
- `safe_get_transcript_segments()` - Safe segment access
- `run_analysis()` - Main worker entry point

### 3. API Layer (`src/api/*.py`)
- **Blueprints** - Modular route definitions
- **Error handling** - Consistent `api_error()` responses
- **File validation** - Security checks for uploads
- **Pagination** - Offset/limit for large datasets

### 4. SocketIO Layer (`src/websocket/handlers.py`)
- **Real-time events** - Job progress, system monitoring
- **Connection management** - Client subscriptions
- **Event handlers** - Must accept `auth=None` parameter

### 5. Frontend Architecture (`static/js/modules/`)
- **Module loading** - `app.js` loads modules in dependency order
- **Global state** - `state.js` maintains application state
- **Event-driven** - SocketIO events update UI components
- **No build step** - Plain JavaScript loaded via script tags

## Data Flow

### Video Upload & Processing
```
1. Client upload → /api/videos/upload
2. Server saves file → uploads/<video>_720p.mp4
3. Background task → _transcode_and_delete_with_cleanup()
4. Frame extraction → _extract_frames() → frames/<video>/
5. Transcription → _transcribe_video() → transcript.json
6. SocketIO emit → videos_updated event
```

### Job Analysis
```
1. Client → "start_analysis" event
2. VRAM manager → queues job based on GPU availability
3. Worker spawned → subprocess with job parameters
4. Worker stages → frames → transcript → AI analysis → results
5. Real-time updates → SocketIO events for progress
6. Completion → results.json saved, KB sync (if configured)
```

### Frame Deduplication & Renumbering
```
1. Original frames → frames/<video>/
2. Perceptual hashing → imagehash.phash()
3. Duplicate removal → threshold-based comparison
4. Renumbering → frame_000001, frame_000002, ...
5. Index creation → frames_index.json maps to original timestamps
```

## Configuration

### Environment Variables
- `APP_ROOT` - Custom installation directory (default: project root)
- `OPENROUTER_API_KEY` - OpenRouter API key for cloud inference
- `OPENWEBUI_URL` - OpenWebUI instance URL for KB sync
- `OPENWEBUI_API_KEY` - OpenWebUI API key

### Path Configuration (`config/paths.py`)
```python
UPLOAD_DIR = os.path.join(APP_ROOT, "uploads")
JOBS_DIR = os.path.join(APP_ROOT, "jobs")
THUMBS_DIR = os.path.join(APP_ROOT, "thumbs")
CACHE_DIR = os.path.join(APP_ROOT, "cache")
CONFIG_DIR = os.path.join(APP_ROOT, "config")
OUTPUT_DIR = os.path.join(APP_ROOT, "output")
```

### Constants (`config/constants.py`)
```python
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
VRAM_BUFFER = 1024 * 1024 * 1024    # 1GB buffer
MAX_CONCURRENT_JOBS = 3             # Chat queue limit
MAX_FRAMES_PER_JOB = 1000           # Processing limit
```

## External Dependencies

### Critical Files (DO NOT MODIFY)
These files are part of external packages or core infrastructure:

| File | Purpose | Note |
|------|---------|------|
| `vram_manager.py` | GPU-aware job scheduler | External package |
| `chat_queue.py` | LLM chat queue manager | External package |
| `monitor.py` | System monitoring (nvidia-smi, ollama ps) | External utility |
| `discovery.py` | Ollama network discovery | External utility |
| `thumbnail.py` | Thumbnail extraction | External utility |
| `gpu_transcode.py` | GPU/CPU transcoding | External utility |
| `providers/` | AI provider implementations | External package |

### Python Dependencies
- **Flask ecosystem**: Flask, Flask-SocketIO, eventlet
- **AI/ML**: faster-whisper, transformers, torch
- **Video processing**: opencv-python, imagehash, PySceneDetect
- **Utilities**: psutil, pynvml, requests

## Development Patterns

### Backend Patterns
1. **Blueprint registration** - All routes in `src/api/*.py`
2. **Error responses** - Use `api_error(message, code)` helper
3. **SocketIO handlers** - Must accept `auth=None` parameter
4. **Worker spawning** - Use `spawn_worker()` from `app.py`
5. **Transcript access** - Use `src/utils/transcript.py` utilities

### Frontend Patterns
1. **Module loading order** - `state.js` and `ui.js` first, `init.js` last
2. **SocketIO events** - Register in `socket.js`, handle in feature modules
3. **State management** - Use `state` object for global state
4. **UI updates** - Event-driven via SocketIO callbacks
5. **Frame browser** - Use `frames_index.json` for timestamp mapping

### Security Patterns
1. **File validation** - `allowed_file()`, `secure_filename()`
2. **Path verification** - `verify_path()` prevents traversal
3. **Size limits** - `MAX_FILE_SIZE` enforcement
4. **Input sanitization** - Escape user input in templates

## Common Gotchas

1. **`providers` dict** is global in `app.py` - blueprints import it
2. **`socketio` and `app`** are also globals imported by blueprints
3. **Double-spawn guard**: `_spawned_jobs` set prevents duplicate workers
4. **Ollama patch in worker**: Monkey-patches `ollama.chat` with `think:false`
5. **Frame dedup**: Uses perceptual hashing with configurable threshold
6. **Audio cleanup**: `audio.wav` deleted after transcription
7. **Source video preserved**: Original not deleted after transcode
8. **SocketLogHandler created after socketio** - Otherwise `socketio.emit()` fails
9. **Port 10000** - Non-privileged port (1000 requires root)
10. **`request` comes from `flask`** - Not `flask_socketio` in SocketIO handlers

## Testing & Debugging

### Running Tests
```bash
# Unit tests
python -m pytest tests/unit/

# Integration tests  
python -m pytest tests/integration/

# With coverage
python -m pytest --cov=src tests/
```

### Debugging Tips
1. **Check worker logs** - `jobs/<job_id>/worker.log`
2. **Monitor SocketIO events** - Browser dev tools Network → WS
3. **System monitoring** - `/api/system` endpoints
4. **GPU status** - `/api/vram` and `/api/gpus`
5. **Server logs** - Emitted to UI via SocketLogHandler

### Common Issues
- **Transcript errors**: Check `frames_index.json` exists and `transcript.json` valid
- **GPU memory**: Monitor VRAM with `nvidia-smi` or `/api/vram`
- **Ollama connection**: Verify Ollama running and accessible
- **File permissions**: Check volume mounts in Docker
- **Port conflicts**: Ensure port 10000 available

## Future Architecture Improvements

### High Priority
1. **Split `app.py`** - Use Flask factory pattern (`src/core/app.py` exists but unused)
2. **Add authentication** - Basic API key or OAuth
3. **Improve error handling** - Consistent across all routes
4. **Add configuration validation** - Validate on startup
5. **Docker security** - Run as non-root user

### Medium Priority
1. **Database integration** - Replace file-based job storage
2. **Queue abstraction** - Common base for VRAMManager and ChatQueueManager
3. **Plugin system** - Extensible providers and processors
4. **Configuration UI** - Web-based configuration management
5. **Advanced monitoring** - Prometheus metrics, health checks

### Low Priority
1. **Multi-user support** - User accounts and isolation
2. **Batch processing** - Process multiple videos as a batch
3. **Advanced analytics** - Video analytics dashboard
4. **Export formats** - Additional result export options
5. **API versioning** - Versioned API endpoints

## References

- **AGENTS.md** - Detailed internal developer guide
- **CONTRIBUTING.md** - Contribution guidelines
- **CHANGELOG.md** - Version history and breaking changes
- **API.md** - REST API documentation
- **TROUBLESHOOTING.md** - Common issues and solutions
- **SECURITY.md** - Security considerations and best practices