# Development Guide

This document provides technical architecture and development guidelines for Video Analyzer Web.

## Architecture Overview

### Tech Stack
- **Backend**: Flask + Flask-SocketIO (eventlet driver)
- **Frontend**: Vanilla JS (modular, no framework/bundler), CSS custom properties
- **CLI**: Python argparse-based with `click`-style groups, SocketIO client, tabular output
- **AI Providers**: LiteLLM proxy (local), OpenRouter (cloud)
- **ML**: faster-whisper (transcription), imagehash (frame dedup)
- **Video**: ffmpeg/ffprobe for transcoding, frame extraction, audio extraction
- **GPU**: NVIDIA CUDA, pynvml for VRAM monitoring
- **Deployment**: Docker (nvidia/cuda base), docker-compose

### Key Design Decisions

1. **Port 10000** - All services run on port 10000 (non-privileged, Docker maps 10000:10000)
2. **Source videos preserved** - Upload transcodes to 720p but keeps original
3. **Whisper models cached on host volume** - HF cache at `./hf_cache` mounted to `/root/.cache/huggingface`
4. **Compute type**: `float16` for CUDA, `int8` for CPU (in `_transcribe_video` and `_process_video_direct`)
5. **Job execution**: VRAM-aware scheduler → spawns worker subprocess per job
6. **Real-time updates**: SocketIO for job progress, frame analysis, system monitoring, server logs
7. **Frame renumbering**: After dedup, frames are renumbered sequentially with `frames_index.json` mapping to video timestamps
8. **OpenWebUI Knowledge Base sync**: Results auto-synced to OpenWebUI KB via REST API
9. **Two-step analysis**: Phase 1 (vision) + Phase 2 (synthesis combining vision + transcript via secondary LLM)
10. **Parallel upload processing**: Frame extraction and audio transcription run concurrently on upload

## Directory Structure

```
video-analyzer-web/
├── app.py                          # Flask entry point (~1858 lines, blueprints + callbacks + upload/extract logic)
├── worker.py                       # Pure dispatcher (~85 lines) → src/worker/pipelines/*
├── vram_manager.py                 # GPU-aware job scheduler (EXTERNAL, DO NOT MODIFY)
├── chat_queue.py                   # LLM chat queue manager (EXTERNAL, DO NOT MODIFY)
├── monitor.py                      # System monitor (nvidia-smi, provider polling)
├── thumbnail.py                    # Thumbnail extraction (EXTERNAL, DO NOT MODIFY)
├── gpu_transcode.py               # FFmpeg transcode command builder (EXTERNAL, DO NOT MODIFY)
├── setup.py                        # Package definition with CLI entry point (`va`)
├── VERSION                         # Current version (0.6.0)
│
├── providers/                      # Provider implementations (EXTERNAL, DO NOT MODIFY)
│   ├── base.py                     # Abstract Provider class
│   ├── litellm.py                  # LiteLLMProvider — /v1/chat/completions REST, VRAM estimation
│   └── openrouter.py               # OpenRouterProvider — pricing cache, cost estimation
│
├── src/
│   ├── api/                        # Flask blueprints (routes only)
│   │   ├── videos.py               # /api/videos — upload, delete, frames, transcript, dedup, scenes
│   │   ├── providers.py            # /api/providers — discover, models, cost, balance, litellm-instances
│   │   ├── jobs.py                 # /api/jobs — list, cancel, priority, results, frames_index
│   │   ├── llm.py                  # /api/llm/chat — submit, status, cancel, queue stats
│   │   ├── results.py              # /api/results — stored results browser
│   │   ├── system.py               # /api/vram, /api/gpus, /api/debug
│   │   ├── transcode.py            # /api/videos/transcode, /api/videos/reprocess
│   │   └── knowledge.py            # /api/knowledge — sync, config, test, bases, send
│   │
│   ├── websocket/
│   │   └── handlers.py             # SocketIO events: connect, subscribe_job, start_analysis, etc.
│   │
│   ├── worker/
│   │   ├── __init__.py             # Pipeline class exports
│   │   ├── main.py                 # Legacy worker (pre-v0.5.0 code path in app.py)
│   │   └── pipelines/
│   │       ├── base.py             # AnalysisPipeline ABC + typed config support
│   │       ├── standard_two_step.py # Standard two-step vision + synthesis
│   │       └── linkedin_extraction.py # LinkedIn short-form extraction
│   │
│   ├── schemas/
│   │   └── config.py               # Pydantic v2: JobConfig, AnalysisParams, nested configs
│   │
│   ├── utils/
│   │   ├── helpers.py              # format_bytes(), format_duration(), map_exit_code_to_status()
│   │   ├── security.py             # secure_filename(), allowed_file(), verify_path(), validate_upload_size()
│   │   ├── video.py                # get_video_duration(), probe_video(), probe_all_videos()
│   │   ├── transcript.py           # load_transcript(), get_transcript_segments_with_end_times()
│   │   ├── scene_detection.py      # detect_scenes_from_frames(), save_scene_info()
│   │   ├── parallel_file_ops.py    # Parallel file deletion for dedup
│   │   ├── parallel_hash.py        # Parallel perceptual hashing for dedup
│   │   └── dedup_scheduler.py      # GPU-accelerated dedup strategy selection
│   │
│   ├── services/
│   │   └── openwebui_kb.py         # OpenWebUIClient — KB CRUD, file upload, results markdown
│   │
│   └── cli/                        # CLI command-line interface
│       ├── __init__.py             # Package init
│       ├── main.py                 # CLI group registration, argument parsing
│       ├── config.py               # Persistent config (~/.video-analyzer-cli.json)
│       ├── api_client.py           # HTTP client (requests) with auth, error handling
│       ├── socketio_client.py      # SocketIO client for real-time CLI updates
│       ├── output.py               # Tabular output (Table class), key-value printers
│       └── commands/
│           ├── __init__.py
│           ├── videos.py           # va videos (list, upload, delete, frames, transcript, dedup, scenes)
│           ├── jobs.py             # va jobs (list, show, cancel, priority, frames, results)
│           ├── providers.py        # va providers (list, discover, litellm-instances)
│           ├── results.py          # va results (list, show)
│           ├── system.py           # va system (vram, gpus, debug)
│           ├── llm.py              # va llm (chat, queue-stats, cancel)
│           └── knowledge.py        # va knowledge (config, test, sync, bases, send)
│
├── config/
│   ├── constants.py                # MAX_FILE_SIZE, VRAM_BUFFER, DEDUP defaults
│   ├── paths.py                    # UPLOAD_DIR, JOBS_DIR, THUMBS_DIR, CACHE_DIR, CONFIG_DIR, OUTPUT_DIR
│   └── default_config.json         # Default analysis config, OpenWebUI settings, LiteLLM settings
│
├── static/
│   ├── css/style.css               # All styles (~3339 lines, dark theme with CSS custom properties)
│   └── js/
│       └── modules/                # 14 JS modules (no build step)
│           ├── state.js            # Global state, localStorage persistence
│           ├── ui.js               # escapeHtml(), showToast(), formatBytes(), formatFrameAnalysis()
│           ├── socket.js           # Socket.IO connection, event registration
│           ├── videos.js           # Upload, video lists, processing progress, server log
│           ├── providers.js        # Provider/model selects, Phase 2 handling
│           ├── jobs.js             # Job cards, live analysis, dedup multi-scan, tab switching
│           ├── llm.js              # Chat across 3 contexts (live/modal/results), polling
│           ├── frame-browser.js    # Dual-range sliders, thumbnails, transcript context, scene markers
│           ├── scene-detection.js  # PySceneDetect integration, scene-aware dedup UI
│           ├── system.js           # GPU status display, monitor tabs
│           ├── results.js          # Stored results browser, detail view, LLM chat
│           ├── settings.js         # Settings persistence, debug toggle
│           ├── knowledge.js        # OpenWebUI KB settings, send-to-KB modal
│           └── init.js             # DOMContentLoaded bootstrap, event wiring
│
├── templates/index.html            # Single-page template (~669 lines, loads all JS modules)
├── Dockerfile                      # nvidia/cuda:12.1.0-base-ubuntu22.04, gunicorn+eventlet
├── docker-compose.yml              # Port 10000, GPU reservations, host.docker.internal
├── requirements.txt
└── tests/                          # Three-tier test suite (see TEST_AUTOMATION.md)
```

## Core Components

### 1. Application Entry Point (`app.py`)
- **~1858 lines** — Flask app + SocketIO setup with debug emit wrapper
- **SocketLogHandler** — Thread-safe queue + background emitter (`_log_emitter`)
- **Blueprint registration** — All `src/api/*.py` blueprints registered here
- **SocketIO handler registration** — `src/websocket/handlers.py:register_socket_handlers(socketio)`
- **Worker lifecycle** — `spawn_worker()` / `monitor_job()`
- **VRAM manager callbacks** — `on_vram_event()` → job dispatch
- **Upload flow** — `_process_video_direct()` → parallel `_extract_frames_direct()` + `_transcribe_video()`
- **Dedup dispatcher** — `_run_dedup()` → smart selection (parallel or sequential via `dedup_scheduler`)
- **Frame renumbering** — `_renumber_frames()` → creates `frames_index.json`

### 2. Worker System (`worker.py` → `src/worker/pipelines/`)
**Architecture:**
- `worker.py` — Thin dispatcher (~85 lines). Loads config via input.json, routes to pipeline factory
- `src/worker/pipelines/__init__.py` — `create_pipeline()` factory with auto-typed `JobConfig` building
- `src/worker/pipelines/base.py` — Abstract `AnalysisPipeline` base class with typed config support
- `src/worker/pipelines/standard_two_step.py` — Standard two-step vision + synthesis
- `src/worker/pipelines/linkedin_extraction.py` — LinkedIn short-form content extraction

**Job Stages (StandardTwoStepPipeline):**
1. Audio extraction + faster-whisper transcription
2. Frame preparation (pre-extracted or VideoProcessor)
3. Frame analysis (Phase 1: vision with transcript context injection)
4. Phase 2 synthesis (combine vision + transcript via secondary LLM)
5. Video description generation
6. Results compilation (`output/results.json`), auto-LLM queue, OpenWebUI KB sync

**Prompt Injection for Transcript:**
- Tokens `{TRANSCRIPT_CONTEXT}`, `{TRANSCRIPT_RECENT}`, `{TRANSCRIPT_PRIOR}` replaced in prompts
- If no tokens found, transcript appended as fallback

### 3. CLI System (`src/cli/`)

The `va` CLI provides full access to all functionality from the terminal.

**Architecture:**
- `main.py` — CLI group registration with global `--url` and `--json` flags
- `config.py` — Persistent config at `~/.video-analyzer-cli.json` with `set`/`show` commands
- `api_client.py` — HTTP client wrapping `requests` with error formatting, pagination support
- `socketio_client.py` — SocketIO client for real-time CLI updates (job progress, etc.)
- `output.py` — `Table` class for tabular output, `print_key_value()` for config/status display

**Command Groups (in `src/cli/commands/`):**
- `videos.py` — 16 subcommands (list, upload, delete, frames, transcript, dedup, scenes, etc.)
- `jobs.py` — 9 subcommands (list, show, cancel, priority, frames, results, etc.)
- `providers.py` — 4 subcommands (list, discover, litellm-instances, cost)
- `results.py` — 3 subcommands (list, show, delete)
- `system.py` — 4 subcommands (vram, gpus, debug, logs)
- `llm.py` — 4 subcommands (chat, status, cancel, queue-stats)
- `knowledge.py` — 6 subcommands (status, config, test, sync, bases, send)

### 4. API Layer (`src/api/*.py`)
- **Blueprints** — Modular route definitions, one file per domain
- **Error handling** — Consistent `api_error(message, code)` responses
- **File validation** — Security checks via `src.utils.security`
- **Pagination** — Offset/limit for large datasets (videos, frames, results)

### 5. SocketIO Layer (`src/websocket/handlers.py`)
- **Real-time events** — Job progress, frame analysis, system monitoring
- **Connection management** — Client subscriptions/unsubscribes
- **Handler convention** — Must accept `auth=None` parameter

### 6. Frontend Architecture (`static/js/modules/`)
- **Module loading** — Strict order via `<script>` tags in `index.html`
- **Global state** — `state` object in `state.js` maintains application state
- **Event-driven** — SocketIO events update UI components
- **No build step** — Plain JavaScript loaded via script tags
- **CSS custom properties** — All colors, spacing in `:root` of `style.css`

## Data Flow

### Video Upload → Processing
```
1. Client XHR POST /api/videos/upload → saves to uploads/
2._process_video_direct() starts parallel tasks:
   ├─ _extract_frames_direct() → ffmpeg → uploads/<name>/frames/
   └─ _transcribe_video() → ffmpeg (audio) → faster-whisper → transcript.json
3. SocketIO emit video_processing_progress (two parallel bars)
4. Emit videos_updated on completion
```

### Job Analysis (Two-Step)
```
1. Client emits "start_analysis" with provider config + params
2. VRAM manager queues job → assigns GPU with most free VRAM
3. spawn_worker() → subprocess worker.py with PID tracking
4. Worker loads pipeline via create_pipeline()
5. Pipeline.run() stages:
   ├─ Audio extraction + transcription
   ├─ Frame preparation
   ├─ Phase 1: frame-by-frame vision analysis → frames.jsonl
   ├─ Phase 2: vision + transcript synthesis → synthesis.jsonl
   ├─ Video description generation
   └─ Results compilation → output/results.json
6. Real-time updates via SocketIO (job_status, frame_analysis, frame_synthesis)
7. Auto-sync to OpenWebUI KB (if enabled)
```

### Frame Dedup → Renumbering
```
1. _run_dedup() → dedup_scheduler.get_dedup_strategy()
2. Parallel: compute_hashes_parallel() + compare + delete_frames_parallel()
3. _renumber_frames() → sequential frame_000001, frame_000002, ...
4. Creates frames_index.json: {"1": 0.0, "2": 1.2, "3": 2.5, ...}
```

## Configuration

### Environment Variables
- `APP_ROOT` — Custom installation directory (default: project root)
- `OPENROUTER_API_KEY` — OpenRouter API key for cloud inference
- `OPENWEBUI_URL` — OpenWebUI instance URL for KB sync
- `OPENWEBUI_API_KEY` — OpenWebUI API key
- `LITELLM_API_BASE` — LiteLLM proxy endpoint (default: `http://172.16.17.3:4000/v1`)

### Path Configuration (`config/paths.py`)
- `UPLOAD_DIR` — Upload files (videos, frames, transcripts, thumbs)
- `JOBS_DIR` — Job working directories (input.json, status.json, frames.jsonl)
- `CACHE_DIR` — Cached data (OpenRouter pricing cache)
- `CONFIG_DIR` — Configuration files
- `OUTPUT_DIR` — Analysis results storage

### Constants (`config/constants.py`)
- `MAX_FILE_SIZE` — 1GB upload limit
- `VRAM_BUFFER` — 1GB VRAM overhead buffer
- `MAX_JOBS_PER_GPU` — 2 concurrent jobs per GPU

## Development Patterns

### Backend Patterns
1. **Blueprints** — All routes in `src/api/*.py`, registered in `app.py`
2. **Error responses** — Use `api_error(message, code)` helper
3. **SocketIO handlers** — Must accept `auth=None` parameter
4. **Worker spawning** — Use `spawn_worker()` with `_spawned_jobs` guard
5. **Transcript access** — Use `src.utils.transcript` utilities for consistency

### Frontend Patterns
1. **Module loading order** — `state.js` and `ui.js` first, `init.js` last
2. **SocketIO events** — Register in `socket.js`, handle in feature modules
3. **State management** — Use `state` object for global state
4. **UI updates** — Event-driven via SocketIO callbacks
5. **Frame browser** — Use `frames_index.json` for timestamp mapping

### CLI Patterns
1. **Global flags** — `--url` and `--json` available at all command levels
2. **Config persistence** — `~/.video-analyzer-cli.json` stores server URL and API keys
3. **Output** — `Table` class for tabular data, `print_key_value()` for status
4. **Error handling** — `api_client.py` wraps errors with descriptive messages

### Security Patterns
1. **File validation** — `allowed_file()`, `secure_filename()`
2. **Path verification** — `verify_path()` prevents directory traversal
3. **Size limits** — `MAX_FILE_SIZE` enforcement (1GB)
4. **Input sanitization** — Escape all user input before HTML rendering

## Common Gotchas

1. **`providers` dict** is global in `app.py` — blueprints import via `from app import providers`
2. **`socketio` and `app`** are also globals imported by blueprints
3. **Double-spawn guard**: `_spawned_jobs` set prevents worker from being spawned twice
4. **`flask.request` vs `flask_socketio.request`**: Use `from flask import request` in SocketIO handlers
5. **SocketLogHandler must be created after socketio** — Otherwise `socketio.emit()` silently fails
6. **`host.docker.internal`** is used for Docker-to-host communication (LiteLLM, OpenWebUI)
8. **`src/worker/main.py`** is legacy (pre-v0.5.0). Active worker is `worker.py` which dispatches to pipelines.
9. **Current two-step limitation**: Phase 2 synthesis runs sequentially within the frame loop

## Testing & Debugging

### Running Tests
See [TEST_AUTOMATION.md](TEST_AUTOMATION.md) for full test suite documentation.

```bash
# Quick dev run
python -m pytest tests/unit/ -v

# Full suite with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Debugging Tips
1. **Worker logs** — Check `jobs/<job_id>/worker.log`
2. **SocketIO events** — Browser dev tools Network → WS tab
3. **Server logs** — Emitted to UI via SocketLogHandler, or `docker compose logs -f`
4. **GPU status** — Check `/api/vram` or System Status sidebar
5. **Debug mode** — Toggle via 🐛 button or `POST /api/debug`

### Common Issues
- **Transcript errors**: Ensure `frames_index.json` exists and `transcript.json` is valid
- **GPU memory**: Monitor VRAM with `nvidia-smi` or `/api/vram`
- **LiteLLM connection**: Verify LiteLLM proxy is running and accessible from Docker
- **File permissions**: Check volume mounts in `docker-compose.yml`
- **Port conflicts**: Ensure port 10000 is available

## External Dependencies (DO NOT MODIFY)

| File | Purpose |
|------|---------|
| `vram_manager.py` | GPU-aware job scheduler with priority queue, VRAM tracking |
| `chat_queue.py` | LLM chat queue with rate limiting, concurrent limits |
| `monitor.py` | nvidia-smi (60s) and provider ps (45s) polling |
| `thumbnail.py` | FFmpeg-based thumbnail at 10% of video duration |
| `gpu_transcode.py` | FFmpeg transcode command builder (CPU encoding) |
| `providers/` | Provider implementations (base, litellm, openrouter) |

## References

- [README.md](README.md) — Project overview, quick start
- [CLI.md](CLI.md) — CLI command reference (v0.6.0)
- [GUI.md](GUI.md) — Web interface documentation
- [API.md](API.md) — REST API + SocketIO endpoint reference
- [TEST_AUTOMATION.md](TEST_AUTOMATION.md) — Test suite structure and execution
- [CHANGELOG.md](CHANGELOG.md) — Version history and migration notes
- [AGENTS.md](AGENTS.md) — Multi-agent development workflow
- [SECURITY.md](SECURITY.md) — Security considerations
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Common issues and solutions
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines
