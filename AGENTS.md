# Video Analyzer Web - Agent Development Guide

> Version 0.3.1 | Last updated: 2026-04-19

This document provides essential context for AI agents working on this codebase.

---

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
- **Port 10000** - All services run on port 10000 (non-privileged, Docker maps 10000:10000)
- **Source videos preserved** - Upload transcodes to 720p but keeps original
- **Whisper models baked into Docker image** - HF cache at `/root/.cache/huggingface` (NOT under volume mount)
- **Compute type**: `float16` for CUDA, `int8` for CPU (in `app.py` transcribe)
- **Job execution**: VRAM-aware scheduler → spawns worker subprocess per job
- **Real-time updates**: SocketIO for job progress, frame analysis, system monitoring, server logs
- **Frame renumbering**: After dedup, frames are renumbered sequentially (1,2,3...) with a `frames_index.json` mapping each frame to its actual video timestamp for accurate transcript sync

---

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
│   │   └── transcode.py            # /api/videos/transcode, /api/videos/reprocess
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
│   │   ├── file.py                 # Re-exports from security.py (backward compat)
│   │   └── transcode.py            # Re-exports from video.py (backward compat)
│   │
│   ├── core/                       # (scaffolded, not yet active)
│   ├── services/                   # (scaffolded, not yet active)
│   └── queue/                      # (scaffolded, not yet active)
│
├── static/
│   ├── css/style.css               # All styles (merged from style-additions.css)
│   └── js/
│       ├── app.js                  # Module loader (was 2267-line monolith)
│       └── modules/
│           ├── state.js            # Global state object, localStorage helpers
│           ├── socket.js           # Socket.IO connection, event registrations
│           ├── videos.js           # Upload, list, delete, reprocess, transcode progress, server log
│           ├── providers.js        # Discovery, model loading, OpenRouter key/balance
│           ├── jobs.js             # Job rendering, cancellation, details modal
│           ├── llm.js              # LLM chat (live/modal/results contexts), polling
│           ├── frame-browser.js    # Frame range sliders, thumbnails, transcript context (timestamp-aware)
│           ├── system.js           # GPU status display, monitor tabs
│           ├── results.js          # Stored results browser, detail view
│           ├── settings.js         # Settings persistence, toggle handlers
│           ├── ui.js               # Toasts, modals, escapeHtml, formatFrameAnalysis
│           └── init.js             # DOMContentLoaded bootstrap, event wiring
│
├── templates/index.html            # Single-page template (loads all JS modules)
├── Dockerfile                      # nvidia/cuda:12.1.0-base-ubuntu22.04
├── docker-compose.yml
├── requirements.txt
├── VERSION                         # Current: 0.2.1
└── AGENTS.md                       # This file
```

---

## External Dependencies (DO NOT MODIFY)

These files are part of the `video-analyzer` Python package or are external utilities. Treat as read-only:

| File | Purpose |
|---|---|
| `vram_manager.py` | GPU-aware job scheduler with priority queue, VRAM tracking, callbacks |
| `chat_queue.py` | LLM chat queue with priority, status tracking, Ollama/OpenRouter execution |
| `monitor.py` | Background threads for nvidia-smi (10s) and ollama ps (15s) polling |
| `discovery.py` | Subnet scan for Ollama instances on port 11434 |
| `thumbnail.py` | ffmpeg-based thumbnail extraction |
| `gpu_transcode.py` | Builds ffmpeg transcode commands with GPU encoder detection |
| `providers/base.py` | Abstract `Provider` class |
| `providers/ollama.py` | Ollama provider with model listing, frame analysis, VRAM estimation |
| `providers/openrouter.py` | OpenRouter provider with cost estimation, balance check |

---

## Key Patterns & Conventions

### Backend

1. **Blueprints** - All routes live in `src/api/*.py` as Flask blueprints. The main `app.py` only registers them.
2. **Error responses** - Use `api_error(message, code)` which returns `{"error": {"code": N, "message": "..."}}`.
3. **SocketIO events** - Registered via `register_socket_handlers(socketio)` in `src/websocket/handlers.py`.
4. **SocketIO handlers must accept `auth=None` parameter** - Flask-SocketIO passes an auth argument on connect/disconnect.
5. **Socket log handler** - `SocketLogHandler` in `app.py` emits all log records to clients via `socketio.emit('log_message', ...)`. Must be instantiated AFTER `socketio` is created.
6. **Job lifecycle**:
   ```
   Client emits "start_analysis" → VRAM manager queues job → 
   on_vram_event("started") → spawn_worker() → monitor_job() → 
   worker.py runs stages → results.json saved → emit job_complete
   ```
7. **Worker stages**: Get frames → Analyze each frame (Ollama/OpenRouter) → Load transcript → Generate video description → Save results → Auto-LLM (if configured).
8. **Transcode flow**: Upload → `_transcode_and_delete_with_cleanup()` → `_extract_frames()` → `_transcribe_video()` → emit `videos_updated`.
9. **Frame renumbering**: After dedup, frames are renamed sequentially (frame_000001, frame_000002, ...) and `frames_index.json` maps each new frame number to its actual video timestamp. This ensures transcript context is always accurate.

### Frontend

1. **Module loading order matters** - `state.js` and `ui.js` load first (no dependencies), then others in dependency order, `init.js` last.
2. **Global `state` object** - Single source of truth for app state, defined in `state.js`.
3. **SocketIO** - Connection established in `socket.js`, all event handlers registered there.
4. **No build step** - Plain script tags in `index.html`. No ES modules, no bundler.
5. **CSS custom properties** - All colors, spacing, radii defined as `--var-*` in `:root`.
6. **Frame browser uses `frames_index.json`** - `getFrameTimestamp(frameNum)` reads from the index for accurate transcript sync, falling back to `(frameNum-1)/fps` if unavailable.

### Docker

1. **HF_HOME removed** - Whisper models cache to `/root/.cache/huggingface` (default), NOT under volume mount.
2. **Port 10000** everywhere - Dockerfile EXPOSE, HEALTHCHECK, CMD, docker-compose, app.py.
3. **Volume mounts**: `uploads`, `jobs`, `cache`, `config`, `output` - these persist across restarts.
4. **GPU access**: `deploy.resources.reservations.devices` with `driver: nvidia`.

---

## Common Tasks

### Add a new API endpoint
1. Create route in appropriate `src/api/*.py` blueprint (or create new blueprint)
2. Register blueprint in `app.py` if new
3. Add corresponding frontend call in appropriate `static/js/modules/*.js`

### Add a new SocketIO event
1. Add handler in `src/websocket/handlers.py` inside `register_socket_handlers()`
2. Handler signature must accept `auth=None` parameter: `def handle_event(data, auth=None):`
3. Add client-side listener in `static/js/modules/socket.js`
4. Add handler function in appropriate module

### Change Whisper model behavior
- **app.py transcription** (upload flow): Lines with `WhisperModel(whisper_model, device=device, compute_type=compute_type)`
- **worker.py**: Uses `video_analyzer.audio_processor.AudioProcessor` from external package
- **Dockerfile**: Pre-downloads `base` and `large` models during build

### Modify UI spacing/styling
- All CSS in `static/css/style.css`
- Spacing variables in `:root` (`--spacing-xs` through `--spacing-xl`)
- No inline styles in JS (toast creation uses `Object.assign` for dynamic values only)

---

## Gotchas

1. **`providers` dict** is global in `app.py` - blueprints import it via `from app import providers`
2. **`socketio` and `app`** are also globals imported by blueprints and handlers
3. **Double-spawn guard**: `_spawned_jobs` set in `app.py` prevents worker from being spawned twice
4. **Ollama patch in worker**: Monkey-patches `ollama.chat` to add `think:false` - this is runtime, not a file change
5. **Frame dedup**: Uses perceptual hashing (`imagehash.phash`) with configurable threshold. After dedup, frames are renumbered sequentially and `frames_index.json` is saved.
6. **Audio cleanup**: `audio.wav` is always deleted after transcription (finally block)
7. **Source video preserved**: The original uploaded file is NOT deleted after transcode (changed in v0.2.0)
8. **SocketLogHandler must be created after socketio** - Otherwise `socketio.emit()` silently fails
9. **Port 10000** - Non-privileged port. Port 1000 requires root on Linux.
10. **`request` comes from `flask`, NOT `flask_socketio`** - Common import error in SocketIO handlers

---

## Testing

No formal test suite exists yet. To manually test:

```bash
# Start the app
python3 app.py

# Or via Docker
docker compose up --build

# Test endpoints
curl http://localhost:10000/api/vram
curl http://localhost:10000/api/providers
curl http://localhost:10000/api/jobs
```

---

## Future Work (Scaffolded but Not Active)

These directories exist but are not yet wired into the application:

| Directory | Intended Purpose |
|---|---|
| `src/core/` | Flask app factory pattern (currently app.py does this directly) |
| `src/services/` | Business logic layer between blueprints and data access |
| `src/queue/` | Common base class for VRAMManager and ChatQueueManager |

When ready to activate these, refactor `app.py` to use `src.core.app.create_app()` factory pattern.
