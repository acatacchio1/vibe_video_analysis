# Video Analyzer Web - Agent Development Guide

> Version 0.5.0 | Last updated: 2026-04-24

This document provides essential context for AI agents working on this codebase.

---

## Architecture Overview

### Tech Stack
- **Backend**: Flask + Flask-SocketIO (eventlet driver via gunicorn)
- **Frontend**: Vanilla JS (modular, no framework/bundler), CSS custom properties
- **AI Providers**: Ollama (local/remote instances), OpenRouter (cloud)
- **ML**: faster-whisper (transcription), imagehash (frame dedup), PySceneDetect (scene detection)
- **Video**: ffmpeg/ffprobe for transcoding, frame extraction, audio extraction
- **GPU**: NVIDIA CUDA, pynvml for VRAM monitoring
- **Deployment**: Docker (nvidia/cuda:12.1.0-base-ubuntu22.04), docker-compose
- **External package**: `video-analyzer` (provides Config, VideoProcessor, VideoAnalyzer, AudioProcessor, PromptLoader, OllamaClient, GenericOpenAIAPIClient)

### Port
- **Port 10000** - All services run on port 10000 (non-privileged, Docker maps 10000:10000)

### Key Design Decisions
- **Source videos preserved** - Original uploaded files are NOT deleted after transcode
- **Whisper models cached on host volume** - HF cache at `./hf_cache` mounted to `/root/.cache/huggingface`. Downloaded on first run if missing.
- **Compute type**: `float16` for CUDA, `int8` for CPU (in `_transcribe_video` and `_process_video_direct`)
- **Job execution**: VRAM-aware scheduler (`vram_manager`) → spawns worker subprocess per job
- **Real-time updates**: SocketIO for job progress, frame analysis, system monitoring, server logs
- **Frame renumbering**: After dedup, frames are renamed sequentially (1,2,3...) with `frames_index.json` mapping each frame to its actual video timestamp
- **OpenWebUI Knowledge Base sync**: After job completion, results are auto-synced to OpenWebUI KB via REST API
- **Two-step analysis**: Phase 1 (vision) + Phase 2 (synthesis combining vision + transcript via secondary LLM)
- **Parallel upload processing**: Frame extraction and audio transcription run concurrently on upload
- **Parallel deduplication**: Uses `src.utils.parallel_file_ops` and `src.utils.dedup_scheduler` for GPU-accelerated dedup; falls back to sequential

---

## Directory Structure

```
video-analyzer-web/
├── app.py                          # Flask entry point (~1858 lines)
│   ├── Flask app + SocketIO setup (with debug emit wrapper)
│   ├── SocketLogHandler (thread-safe queue + background emitter)
│   ├── Blueprint registration (src/api/*)
│   ├── SocketIO handler registration (src/websocket/*)
│   ├── spawn_worker() / monitor_job() - worker lifecycle
│   ├── VRAM manager callbacks, monitor callbacks
│   ├── _transcode_and_delete_with_cleanup() - deprecated transcode flow
│   ├── _process_video_direct() - parallel frames + transcription upload flow
│   ├── _extract_frames_direct() - direct frame extraction from original video
│   ├── _extract_frames() / _transcribe_video() - legacy extraction/transcription
│   ├── _run_dedup_sequential() / _run_dedup_parallel() / _run_dedup() - smart dispatcher
│   ├── _renumber_frames() - sequential renumbering with timestamp index
│   ├── recover_stale_jobs() - startup recovery
│   └── init_providers() - Ollama + OpenRouter provider initialization
│
├── worker.py                       # Worker dispatcher → src.worker.pipelines.create_pipeline()
│   └── run_analysis() - loads config, routes to pipeline factory
│
├── src/worker/pipelines/             # Analysis pipeline implementations
│   ├── base.py                       # AnalysisPipeline ABC + typed config support
│   ├── standard_two_step.py          # Standard two-step vision + synthesis
│   ├── linkedin_extraction.py        # LinkedIn short-form extraction
│   └── __init__.py                   # Pipeline factory + registry
│
├── src/schemas/                      # Pydantic configuration schemas
│   └── config.py                     # JobConfig, AnalysisParams, nested configs
│
├── vram_manager.py                 # GPU-aware job scheduler (EXTERNAL, DO NOT MODIFY)
│   ├── VRAMManager class with priority queue, multi-GPU scheduling
│   ├── NVML integration for real-time VRAM tracking
│   ├── Per-GPU job limits (MAX_JOBS_PER_GPU=2)
│   ├── Context VRAM overhead (1GB) for already-loaded models
│   └── Background thread (5s interval) for queue processing
│
├── chat_queue.py                   # LLM chat queue manager (EXTERNAL, DO NOT MODIFY)
│   ├── ChatQueueManager for LLM chat requests
│   ├── Rate limiting (MAX_JOBS_PER_MINUTE=30) + concurrent limits
│   └── Background worker thread (1s interval)
│
├── monitor.py                      # System monitor (EXTERNAL, DO NOT MODIFY)
│   ├── nvidia-smi polling (60s interval) with structured per-GPU stats
│   └── ollama ps API polling (45s interval)
│
├── discovery.py                    # Ollama network discovery (EXTERNAL, DO NOT MODIFY)
│   ├── Subnet scan (192.168.1.0/24) + common hosts
│   └── Background refresh thread (30s interval)
│
├── thumbnail.py                    # Thumbnail extraction (EXTERNAL, DO NOT MODIFY)
│   └── FFmpeg-based thumbnail at 10% of video duration
│
├── gpu_transcode.py                # FFmpeg transcode command builder (EXTERNAL, DO NOT MODIFY)
│   ├── Forces CPU encoding (libx264) - TODO: restore GPU encoding
│   └── Progress parser for standard FFmpeg output
│
├── providers/                      # Provider implementations (EXTERNAL, DO NOT MODIFY)
│   ├── base.py                     # Abstract BaseProvider class
│   ├── ollama.py                   # OllamaProvider - /api/chat REST endpoint, VRAM estimation
│   └── openrouter.py               # OpenRouterProvider - pricing cache, cost estimation
│
├── config/                         # Configuration files
│   ├── constants.py                # All tunable constants (VRAM, chat, video, dedup, etc.)
│   ├── paths.py                    # Directory paths (uploads, jobs, cache, config, output)
│   └── default_config.json         # Default analysis config, OpenWebUI settings, Ollama instances
│
├── src/                            # Refactored modules
│   ├── api/                        # Flask blueprints (routes only)
│   │   ├── videos.py               # /api/videos - upload, delete, frames, transcript, dedup, scenes
│   │   ├── providers.py            # /api/providers - discover, models, cost, balance, ollama-instances
│   │   ├── jobs.py                 # /api/jobs - list, cancel, priority, results, frames_index
│   │   ├── llm.py                  # /api/llm/chat - submit, status, cancel, queue stats
│   │   ├── results.py              # /api/results - stored results browser
│   │   ├── system.py               # /api/vram, /api/gpus, /api/debug
│   │   ├── transcode.py            # /api/videos/transcode, /api/videos/reprocess
│   │   └── knowledge.py            # /api/knowledge - sync, config, test, bases, send
│   │
│   ├── websocket/
│   │   └── handlers.py             # SocketIO events: connect, disconnect, subscribe_job,
│   │                                # unsubscribe_job, start_analysis
│   │
│   ├── worker/
│   │   └── main.py                 # Legacy worker (pre-v0.5.0 code path in app.py)
│   │
│   ├── utils/
│   │   ├── helpers.py              # format_bytes(), format_duration(), map_exit_code_to_status()
│   │   ├── security.py             # secure_filename(), allowed_file(), verify_path(), validate_upload_size()
│   │   ├── video.py                # get_video_duration(), probe_video(), probe_all_videos()
│   │   ├── transcript.py           # get_video_directory_from_path(), find_transcript_file(),
│   │                                # load_transcript(), get_transcript_segments_with_end_times()
│   │   └── scene_detection.py      # detect_scenes_from_frames(), save_scene_info(),
│   │                                # get_scene_statistics(), integrate_scenes_with_dedup()
│   │
│   └── services/
│       └── openwebui_kb.py         # OpenWebUIClient - KB CRUD, file upload, results markdown
│
├── static/
│   ├── css/style.css               # All styles (~3339 lines, dark theme with CSS custom properties)
│   └── js/
│       ├── app.js                  # Module loader comment (deprecated)
│       └── modules/
│           ├── state.js            # Global state object, saveStateToLocalStorage()
│           ├── ui.js               # escapeHtml(), formatFrameAnalysis(), formatBytes(),
│           │                        # showToast(), closeModal(), updateStartButton()
│           ├── socket.js           # initSocket() - all SocketIO event registration
│           ├── videos.js           # loadVideos(), upload, delete, reprocess, transcode progress,
│           │                        # parallel video processing progress UI, server log
│           ├── providers.js        # loadProviders(), provider/model selects, Phase 2 handling
│           ├── jobs.js             # Job cards, live analysis, dedup multi-scan, tab switching
│           ├── llm.js              # Chat across 3 contexts (live/modal/results), polling
│           ├── frame-browser.js    # Dual-range sliders, thumbnails, transcript context,
│           │                        # scene markers visualization, getFrameTimestamp()
│           ├── scene-detection.js  # PySceneDetect integration, scene-aware dedup UI
│           ├── system.js           # GPU status display, monitor tabs
│           ├── results.js          # Stored results browser, detail view, LLM chat in results
│           ├── settings.js         # Settings persistence, debug toggle, advanced options
│           ├── knowledge.js        # OpenWebUI KB settings, send-to-KB modal
│           ├── ollama-settings.js  # Ollama instances management modal
│           └── init.js             # DOMContentLoaded bootstrap, event wiring, submitAnalysis()
│
├── templates/index.html            # Single-page template (~725 lines, loads all JS modules)
├── Dockerfile                      # nvidia/cuda:12.1.0-base-ubuntu22.04, gunicorn+eventlet
├── docker-compose.yml              # Port 10000, GPU reservations, host.docker.internal
├── requirements.txt
├── VERSION                         # 0.5.0
├── README.md                       # Project overview, quick start
├── CHANGELOG.md                    # Version history
├── CONTRIBUTING.md                 # Development guidelines
├── DEVELOPMENT.md                  # Architecture guide
├── API.md                          # REST API + SocketIO documentation
├── TROUBLESHOOTING.md              # Common issues
├── SECURITY.md                     # Security considerations
└── AGENTS.md                       # This file
```

---

## External Dependencies (DO NOT MODIFY)

These files are part of external packages or utilities. Treat as read-only:

| File | Purpose |
|---|---|
| `vram_manager.py` | GPU-aware job scheduler with priority queue, VRAM tracking, callbacks |
| `chat_queue.py` | LLM chat queue with rate limiting, priority, status tracking |
| `monitor.py` | Background threads for nvidia-smi (60s) and ollama ps (45s) polling |
| `discovery.py` | Subnet scan for Ollama instances on port 11434 |
| `thumbnail.py` | FFmpeg-based thumbnail extraction at 10% of video duration |
| `gpu_transcode.py` | Builds ffmpeg transcode commands (forces CPU encoding currently) |
| `providers/base.py` | Abstract `Provider` class |
| `providers/ollama.py` | Ollama provider with direct REST /api/chat, model listing, VRAM estimation |
| `providers/openrouter.py` | OpenRouter provider with pricing cache, cost estimation, balance check |

---

## Key Patterns & Conventions

### Backend

1. **Blueprints** - All routes live in `src/api/*.py` as Flask blueprints. Registered in `app.py` with `app.register_blueprint()`.
2. **Error responses** - Use `api_error(message, code)` which returns `{"error": {"code": N, "message": "..."}}`.
3. **SocketIO events** - All handlers registered in `src/websocket/handlers.py:register_socket_handlers(socketio)`.
4. **SocketIO handlers must accept `auth=None` parameter** - Flask-SocketIO passes auth on connect/disconnect.
5. **Socket log handler** - `SocketLogHandler` in `app.py` uses a thread-safe queue + background emitter thread (`_log_emitter`). Instantiated AFTER `socketio` is created.
6. **Two-step analysis** (v0.5.0+):
   - **Phase 1 (Vision)**: Frame-by-frame vision analysis using primary LLM provider
   - **Phase 2 (Synthesis)**: Each frame's vision result is combined with transcript context via a secondary LLM
   - **Separate configuration**: phase2_provider_type, phase2_model, phase2_temperature in params
   - **Real-time display**: `frame_analysis` SocketIO event (vision), `frame_synthesis` SocketIO event (combined)
   - **Data flow**: `frames.jsonl` (vision results) → `synthesis.jsonl` (combined results)
7. **Job lifecycle**:
   ```
   Client emits "start_analysis" → VRAM manager queues job →
   on_vram_event("started") → spawn_worker() → monitor_job() →
   worker.py runs stages → results.json saved → emit job_complete →
   auto-sync to OpenWebUI KB (if enabled)
   ```
8. **Upload flow**: XHR POST `/api/videos/upload` → `_process_video_direct()` → parallel `_extract_frames_direct()` + `_transcribe_video()` → emit `videos_updated`.
9. **Frame renumbering**: After dedup, frames are renamed sequentially (`frame_000001`, `frame_000002`, ...) and `frames_index.json` maps new frame number → video timestamp in seconds.

### Frontend

1. **Module loading order** (defined in `index.html`): state → ui → socket → videos → providers → jobs → llm → frame-browser → scene-detection → system → results → settings → ollama-settings → knowledge → init.
2. **Global `state` object** in `state.js` - single source of truth. Properties: `debug`, `providers`, `currentJob`, `currentJobResults`, `settings`, `analysisVideoName`, `frameBrowser`, `currentVideo`, `socket`.
3. **SocketIO** connection established in `socket.js:initSocket()`. All event handler functions registered there (calling functions in other modules).
4. **No build step** - Plain script tags in `index.html`. No ES modules, no bundler.
5. **CSS custom properties** - All colors, spacing, radii defined as `--var-*` in `:root`.
6. **Frame browser** uses `frames_index.json` - `getFrameTimestamp(frameNum)` reads from the index for accurate transcript sync, falling back to `(frameNum-1)/fps`.
7. **Three chat contexts**: `live` (analysis results panel), `modal` (job detail modal), `results` (stored results view). Each has its own set of DOM selectors.

### Docker

1. **HF_HOME**: Whisper models cache to `/root/.cache/huggingface` via host volume mount `./hf_cache:/root/.cache/huggingface`. Entrypoint script downloads models on first run if host cache is empty.
2. **Port 10000** everywhere - Dockerfile EXPOSE, HEALTHCHECK, CMD, docker-compose, app.py.
3. **Volume mounts**: `uploads`, `jobs`, `cache`, `config`, `output` - persist across restarts.
4. **GPU access**: `deploy.resources.reservations.devices` with `driver: nvidia`, `capabilities: [gpu]`.
5. **CUDA compatibility**: `nvidia-cublas-cu12` pip package symlinked into ctranslate2 libs dir for ABI compatibility.
6. **Start command**: `gunicorn -k eventlet -w 1 --bind 0.0.0.0:10000 --timeout 300 app:app`.

---

## Key SocketIO Events

### Client → Server
| Event | Data | Handler |
|---|---|---|
| `start_analysis` | `{video_path, provider_type, provider_name, model, priority, provider_config, params}` | `handle_start_analysis` |
| `subscribe_job` | `{job_id}` | `handle_subscribe_job` |
| `unsubscribe_job` | `{job_id}` | `handle_unsubscribe_job` |

### Server → Client
| Event | Data | Purpose |
|---|---|---|
| `job_created` | `{job_id, status}` | Analysis job submitted |
| `job_status` | `{job_id, stage, progress, current_frame, total_frames}` | Job progress updates |
| `frame_analysis` | `{job_id, frame_number, analysis, timestamp, video_ts, transcript_context}` | Vision analysis per frame |
| `frame_synthesis` | `{job_id, frame_number, combined_analysis, vision_analysis}` | Combined analysis per frame |
| `job_transcript` | `{job_id, transcript}` | Full transcript text |
| `job_description` | `{job_id, description}` | Final video description |
| `job_complete` | `{job_id, success}` | Job finished |
| `videos_updated` | `{}` | Video list changed |
| `vram_event` | `{event, job}` | VRAM manager status change |
| `system_status` | `{type, data}` | nvidia-smi / ollama ps output |
| `log_message` | `{level, message, timestamp}` | Server log lines |
| `transcode_progress` | `{source, stage, progress}` | Transcode progress (legacy) |
| `video_processing_progress` | `{source, stage, progress, message}` | Upload processing (parallel) |
| `frame_extraction_progress` | `{source, stage, progress}` | Frame extraction (legacy) |
| `transcription_progress` | `{source, stage, progress}` | Transcription (legacy) |
| `kb_sync_complete` | `{job_id, kb_id}` | OpenWebUI sync done |
| `kb_sync_error` | `{job_id, error}` | OpenWebUI sync failed |

---

## Key API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/videos` | List uploaded videos |
| POST | `/api/videos/upload` | Upload video (parallel frames + transcription) |
| DELETE | `/api/videos/<filename>` | Delete video + thumbnails + job data |
| GET | `/api/videos/<filename>/frames` | Frame metadata (count, fps, duration) |
| GET | `/api/videos/<filename>/frames/<n>` | Get specific frame image |
| GET | `/api/videos/<filename>/frames/<n>/thumb` | Get frame thumbnail |
| GET | `/api/videos/<filename>/frames_index` | Get frame timestamp index |
| GET | `/api/videos/<filename>/transcript` | Get transcript data |
| POST | `/api/videos/<filename>/dedup` | Apply deduplication at threshold |
| POST | `/api/videos/<filename>/dedup-multi` | Multi-threshold dedup scan |
| GET/POST | `/api/videos/<filename>/scenes` | Scene detection |
| POST | `/api/videos/<filename>/scene-aware-dedup` | Scene-aware dedup |
| POST | `/api/videos/reprocess` | Re-extract + re-transcribe |
| POST | `/api/videos/transcode` | Direct processing (legacy) |
| GET | `/api/providers` | List all providers |
| GET | `/api/providers/discover` | Scan network for Ollama |
| GET | `/api/providers/ollama/models` | List Ollama models by URL |
| GET | `/api/providers/openrouter/models` | List OpenRouter models |
| GET | `/api/providers/ollama-instances` | Get saved Ollama URLs |
| POST | `/api/providers/ollama-instances` | Save Ollama URLs |
| GET | `/api/jobs` | List all jobs |
| GET | `/api/jobs/<id>` | Get job details |
| DELETE | `/api/jobs/<id>` | Cancel job |
| GET | `/api/jobs/<id>/results` | Get job results |
| GET | `/api/results` | List stored results |
| POST | `/api/llm/chat` | Submit chat job |
| GET | `/api/llm/chat/<id>` | Poll chat job status |
| DELETE | `/api/llm/chat/<id>` | Cancel chat job |
| GET | `/api/llm/queue/stats` | Chat queue statistics |
| GET | `/api/vram` | VRAM status |
| GET | `/api/gpus` | GPU list with details |
| GET/POST | `/api/debug` | Toggle debug mode |
| GET | `/api/knowledge/status` | OpenWebUI config status |
| POST | `/api/knowledge/config` | Save OpenWebUI config |
| POST | `/api/knowledge/test` | Test OpenWebUI connection |
| POST | `/api/knowledge/sync/<id>` | Sync single job to KB |
| POST | `/api/knowledge/sync-all` | Sync all jobs to KB |
| GET | `/api/knowledge/bases` | List KBs from OpenWebUI |
| POST | `/api/knowledge/send/<id>` | Send job to specific KB |

---

## Worker Architecture (worker.py)

The worker runs as a subprocess spawned by `app.py:spawn_worker()`. It communicates via files in the job directory.

### Job Directory Structure
```
jobs/<job_id>/
├── input.json           # Job configuration
├── status.json          # Live status updates (written by worker, read by monitor)
├── frames.jsonl         # Vision analysis results (one JSON line per frame)
├── synthesis.jsonl      # Combined analysis results (one JSON line per frame, Phase 2)
├── config.json          # Temp config for video_analyzer library
├── pid                  # Worker process PID
├── pgid                 # Process group ID
├── gpu_assigned.txt     # GPU index assigned by VRAM manager
├── worker.log           # Worker stdout/stderr
└── output/
    └── results.json     # Final results (frames, transcript, video_description)
```

### Worker Pipeline Stages (worker.py:run_analysis)
1. **Initialization**: Load config, update status
2. **Audio extraction + transcription**: Extract audio with ffmpeg, transcribe with faster-whisper, or load pre-existing transcript
3. **Frame preparation**: Use pre-extracted frames from uploads/ or extract via VideoProcessor
4. **Frame analysis (Phase 1)**: Analyze each frame via Ollama/OpenRouter, inject transcript context, write to `frames.jsonl`
5. **Phase 2 synthesis**: For each frame, call secondary LLM combining vision + transcript, write to `synthesis.jsonl`
6. **Video reconstruction**: Generate final video description from all analyses + transcript
7. **Auto-LLM**: Submit results to chat queue if configured

### Prompt Injection for Transcript
The worker injects transcript context into frame analysis prompts via token replacement:
- `{TRANSCRIPT_CONTEXT}` - Old format, replaced with recent + prior transcript blocks
- `{TRANSCRIPT_RECENT}` - New format, replaced with transcript at current timestamp
- `{TRANSCRIPT_PRIOR}` - New format, replaced with 2 prior transcript segments
- If no tokens found, transcript is appended to the prompt as a fallback

### Frame Metadata Sources
- `frames_index.json`: Maps renumbered frame number → video timestamp (after dedup)
- `dedup_results.json`: Maps original frame numbers ↔ deduped frame numbers
- `frames_meta.json`: Contains frame_count, fps, duration

---

## Transcription Flow

### Upload Phase
1. `_process_video_direct()` starts parallel frame extraction and audio transcription
2. Audio extracted via ffmpeg (pcm_s16le, 16kHz, mono)
3. Transcribed via faster-whisper with GPU (CUDA float16) or CPU (int8) fallback
4. Transcript saved to `uploads/<video_name>/transcript.json`
5. Audio file (`audio.wav`) cleaned up in finally block

### Analysis Phase
1. Worker first tries to extract audio from video and transcribe directly
2. If no audio stream (e.g., deduped video), loads pre-existing `transcript.json`
3. Uses shared `src/utils/transcript.py:load_transcript()` for consistent path resolution
4. Path resolution handles: `_720p` suffix removal, `_dedup` directory naming

### Accepted Languages
Full list of ISO 639-1 language codes (~100 languages, defined in both `_transcribe_video()` and `_process_video_direct()`). If a language is not in the list, `lang_param` is set to `None` (auto-detect).

---

## Dedup System

### Three Methods
1. **Sequential** (`_run_dedup_sequential` in app.py): Basic frame-by-frame phash comparison, no parallelization
2. **Parallel** (`_run_dedup_parallel` in app.py): Uses `src.utils.parallel_hash.compute_hashes_parallel()` + `src.utils.parallel_file_ops.delete_frames_parallel()` for GPU-accelerated hashing
3. **Smart dispatcher** (`_run_dedup` in app.py): Chooses parallel or sequential based on `src.utils.dedup_scheduler.get_dedup_strategy()`

### Multi-threshold Scan
- `POST /api/videos/<filename>/dedup-multi` runs `dedup_worker.py` as subprocess
- Pre-computes hash results for multiple thresholds simultaneously
- Results saved to `dedup_detailed_results.json` for instant application via UI

### Scene-Aware Dedup
- Uses `PySceneDetect` for content-based scene boundary detection
- Dedup runs within scene boundaries (preserves scene-transition frames)
- Accessible via `/api/videos/<filename>/scene-aware-dedup` endpoint

### Frame Renumbering
After dedup, `_renumber_frames()` creates `frames_index.json`:
```json
{"1": 0.0, "2": 1.2, "3": 2.5, ...}
```
Key: 1-based sequential frame number, Value: video timestamp in seconds.

---

## Phase 2 (Synthesis) Architecture

### Configuration Flow
1. User selects Phase 2 provider/model in UI (or "Same as Phase 1")
2. Config passed via `params.phase2_provider_type`, `params.phase2_model`, etc.
3. Implementation:
   - **`StandardTwoStepPipeline._synthesize_frame()`**: Direct HTTP call to Ollama/OpenRouter API
   - **Pipeline via video_analyzer library**: Uses VideoAnalyzer with phase2 client config

### Synthesis Prompt
```
Combine the visual analysis with transcript context to create an enhanced description.
VISION ANALYSIS: <frame analysis text>
TRANSCRIPT CONTEXT: <recent transcript text>
TIMESTAMP: <time in seconds>
Create a comprehensive analysis... [5 focus areas]
```

---

## Ollama Instance Management

### Discovery Methods
1. **Static config**: URLs saved in `config/default_config.json` under `ollama_instances`
2. **Manual addition**: via Ollama Instances modal in UI
3. **Network scan**: `discovery.py` scans subnet `192.168.1.0/24` + common hosts (localhost, host.docker.internal)
4. **Hardcoded fallback** in `app.py:init_providers()`: `192.168.1.237:11434`, `192.168.1.241:11434`

### Monkey-patching
- **worker.py**: Ollama client's `chat()` patched to add `think:false`, use `/api/chat` directly
- **worker.py**: `VideoAnalyzer.analyze_frame()` patched for transcript injection + previous frame context limiting

---

## Gotchas

1. **`providers` dict** is global in `app.py` - blueprints import it via `from app import providers`
2. **`socketio` and `app`** are also globals imported by blueprints and handlers
3. **Double-spawn guard**: `_spawned_jobs` set in `app.py` prevents worker from being spawned twice
4. **`flask.request` vs `flask_socketio.request`**: Use `from flask import request` in SocketIO handlers
5. **SocketLogHandler must be created after socketio** - Otherwise `socketio.emit()` silently fails
6. **Port 10000** - Non-privileged port. Port 1000 requires root on Linux.
7. **`host.docker.internal`** is used for Docker-to-host communication (Ollama, OpenWebUI)
8. **`request` comes from `flask`, NOT `flask_socketio`** - Common import error in SocketIO handlers
9. **Phase 2 Ollama URL** defaults to `http://192.168.1.237:11434` (not localhost) since text models are on that instance
10. **`src/worker/main.py`** is legacy code (pre-v0.5.0). The active worker is `worker.py` at the root, which dispatches to `src/worker/pipelines`. `src/worker/__init__.py` exports pipeline classes.
11. **Current two-step limitation**: Phase 2 synthesis runs sequentially within the frame loop, causing vision analysis to wait for synthesis completion before moving to next frame

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
- Upload transcription (`_process_video_direct`): Lines ~1412-1423 in `app.py`
- Worker transcription: Lines 416-421 in `worker.py`
- Legacy transcription (`_transcribe_video`): Lines 1712-1723 in `app.py`
- Dockerfile pre-downloads: `base` and `large` models during build

### Modify UI spacing/styling
- All CSS in `static/css/style.css`
- Spacing variables in `:root` (`--spacing-xs` through `--spacing-xl`)
- No inline styles in JS (toast creation uses `Object.assign` for dynamic values only)
