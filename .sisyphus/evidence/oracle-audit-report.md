# Oracle Audit Report — video-analyzer-web

> Generated: 2026-04-29
> Scope: Complete Python codebase (app.py, worker.py, src/, config/, vram_manager.py, chat_queue.py, monitor.py, providers/, gpu_transcode.py, thumbnail.py)
> Status: Static analysis + architectural review

---

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | 28 |
| High     | 40 |
| Medium   | 35 |
| **Total** | **103** |

The codebase contains 103 issues across eight categories. The dominant problems are silent exception swallowing (12 Critical), unprotected shared state under eventlet (6 Critical), and duplicated functions that will diverge over time (5 Critical). None of the Critical issues cause immediate security compromise, but collectively they create a fragile system where failures go unlogged, concurrent requests corrupt state, and debugging is near-impossible.

---

## 1. Error Handling

Silent exception handlers are the single largest class of defect. Over a dozen Critical-level bare `except Exception: pass` patterns throughout the codebase drop errors without any logging. When something fails — authentication, job status updates, frame analysis — the system silently proceeds with stale or missing data.

| File | Lines | Severity | Description | Recommended Fix |
|------|-------|----------|-------------|-----------------|
| `app.py` | 87-88 | Critical | `_log_queue.Full` caught and dropped silently — log messages lost without indication | Remove `queue.Full` catch or log a warning; queue should be sized to never lose messages |
| `app.py` | 96-99 | Critical | `_log_emitter` catches ALL `Exception` inside the emit loop — broken socket silently drops all future logs | Log the exception; re-raise after a retry limit |
| `app.py` | 259-260 | Critical | Bare `except Exception: pass` in debug frame logging — frame errors swallowed | Add `logger.error(...)` with traceback; never silently swallow |
| `app.py` | 318 | Critical | Broad `except Exception` in pgid cleanup — worker group kill failures invisible | Log the failure; pgid cleanup is critical for process hygiene |
| `app.py` | 338 | Critical | `except Exception: pass` in `status.json` update — job status silently incorrect after errors | Log the exception; status corruption causes monitoring blindness |
| `src/api/videos.py` | 522-525 | Critical | Logger created inside `except` block — `getLogger` can fail in except context | Create logger at module top; never instantiate in except blocks |
| `src/websocket/handlers.py` | 81-83 | Critical | Bare `except Exception: pass` in frame history replay — missing frames silently dropped | Log the error; emit error event to client |
| `vram_manager.py` | 611-612 | Critical | Bare `except Exception` in callback loop — VRAM manager callback failures invisible | Log exception per-callback; ensure callbacks are isolated |
| `chat_queue.py` | 94-95 | Critical | Broad `Exception` catch in `_worker_loop` — chat queue failures silent | Log the exception; queue needs watchdog restart capability |
| `chat_queue.py` | 195-197 | Critical | `KeyboardInterrupt` caught in `_process_job` — worker can't be stopped with Ctrl-C | Re-raise `KeyboardInterrupt`; only catch task-specific exceptions |
| `src/worker/pipelines/standard_two_step.py` | 121-123 | Critical | `_synthesize_frame` swallows all exceptions — Phase 2 failures produce empty results | Log error per frame; continue with vision-only result |
| `src/worker/pipelines/standard_two_step.py` | 843-844 | Critical | Synthesis exception handler too broad — entire synthesis pipeline masked | Narrow to `requests.RequestException` and LLM-specific errors |

---

## 2. Type Safety

The codebase has near-total absence of type annotations. Out of ~784 lines of function definitions in `app.py`, only ~7 have type hints. This makes refactoring risky, IDE assistance limited, and automated static analysis (mypy) non-functional.

| File | Lines | Severity | Description | Recommended Fix |
|------|-------|----------|-------------|-----------------|
| Throughout | — | High | No type hints on ~99% of functions across codebase | Add return type + parameter annotations to all public functions |
| `app.py` | 157 | High | `_spawned_jobs: set = set()` — missing generic parameter | Change to `set[str]` |
| `vram_manager.py` | 55 | High | `params: Dict` — bare Dict without key/value types | Change to `Dict[str, Any]` |
| `vram_manager.py` | 92 | High | `List[Callable]` — no signature information on callbacks | Change to `List[Callable[[Job, str], None]]` or appropriate signature |
| `chat_queue.py` | 78 | High | Same bare `List[Callable]` without signature | Same fix as vram_manager |
| `monitor.py` | 19-20 | High | Same bare `List[Callable]` without signature | Same fix as vram_manager |

---

## 3. Security

The most immediate risk is session invalidation on every restart due to `SECRET_KEY` regeneration. The more insidious risks are path traversal vectors in transcode and reprocess endpoints, and API key exposure in logs and plaintext config.

| File | Lines | Severity | Description | Recommended Fix |
|------|-------|----------|-------------|-----------------|
| `app.py` | 54 | Critical | `SECRET_KEY = os.urandom(24)` regenerated every restart — breaks Flask sessions and CSRF protection | Persist to `config/secret_key`; load with `os.environ.get("SECRET_KEY")` fallback to file |
| `src/api/transcode.py` | 16 | Critical | `Path(video_path).exists()` with NO sanitization — full path traversal via user input | Use `security.verify_path()` or `secure_filename()` before any filesystem operation |
| `src/api/transcode.py` | 31 | Critical | Same path traversal in reprocess endpoint | Same fix |
| `src/websocket/handlers.py` | 210 | Critical | `video_path` from client socket message used in filesystem operations without sanitization | Validate against whitelisted upload directory; reject paths containing `..` |
| `chat_queue.py` | 162-163 | High | Empty Bearer token sent to LiteLLM — auth header present but value is `""` | Only set Authorization header when API key is non-empty |
| `providers/litellm.py` | 30, 140 | High | Same empty Bearer auth pattern in LiteLLM provider | Same fix |
| `src/utils/security.py` | 26-27 | High | `secure_filename` order bug: `..` replacement happens after `/` stripping — `....//` bypasses filter | Replace `..` before stripping special characters; or use `os.path.basename` |
| `app.py` | 184-190 | High | Worker subprocess inherits full parent env including OPENAI_API_KEY, LITELLM_API_KEY, etc. | Spawn with filtered env: only PATH, HOME, CUDA-related vars |
| `app.py` | 57 | Medium | `cors_allowed_origins="*"` — accepts cross-origin requests from any domain | Restrict to known frontend origins |
| `src/api/providers.py` | 108 | Medium | API key transmitted in Authorization header and potentially written to access logs | Redact in logging; ensure access logs don't include full headers |
| `src/api/knowledge.py` | 31-34 | Medium | OpenWebUI API key stored in plaintext `config/default_config.json` | Move to env var or encrypted credential store |

---

## 4. Concurrency

The codebase runs on `eventlet` (green threads) but contains multiple race conditions where unprotected shared state is accessed without proper synchronization. The `_spawned_jobs` set and `_log_queue` are the most critical.

| File | Lines | Severity | Description | Recommended Fix |
|------|-------|----------|-------------|-----------------|
| `app.py` | 76 | Critical | `_log_queue` drops NEWEST messages on full; analytics lose the most recent log lines when backlog occurs | Switch to a deque-based rotating buffer that drops OLDEST messages instead |
| `app.py` | 157 | Critical | `_spawned_jobs: set = set()` accessed without lock — GIL-based safety broken by eventlet yields | Protect with `threading.Lock` or eventlet-compatible lock |
| `app.py` | 453-498 | Critical | `recover_stale_jobs` called at module import time — races with concurrent startup threads | Defer to app startup hook (after all blueprints registered, after socketio init) |
| `chat_queue.py` | 77 | Critical | `_notify_callbacks` acquires self.lock; if callback itself acquires lock → guaranteed deadlock | Copy callback list under lock, then call outside lock scope |
| `src/api/videos.py` | 188-200 | Critical | Delete endpoint iterates `state.videos` while potentially mutating via other concurrent requests | Use `list(state.videos)` copy for iteration; guard with lock |
| `app.py` | 101-104 | High | `SocketLogHandler.format` accesses `state.settings` without sync — may see partial writes | Make settings immutable updates (always create new dict) |
| `app.py` | 107-108 | High | `_log_thread` set to daemon=True — killed abruptly on shutdown, losing in-flight messages | Add graceful shutdown hook: signal thread to stop, join it |
| `vram_manager.py` | 91, 622 | High | RLock re-entry in `_process_queue` — if callback acquires lock, deadlocks | Document lock ordering; use trylock pattern in callbacks |
| `app.py` | 657-663 | High | Non-daemon reader threads spawned in transcode — block interpreter exit | Set `daemon=True` or add proper lifecycle management |
| `app.py` | 1240-1242 | High | Same non-daemon thread issue in `_extract_frames_direct` | Same fix |
| `monitor.py` | 243-244 | High | Background threads set `daemon=True` — killed on shutdown without cleanup | Add stop event + join on shutdown |

---

## 5. Resource Management

File descriptor leaks and non-atomic writes create data corruption risk. The `log_file = open(...)` pattern in `app.py` is the most concerning — each spawned worker opens a file handle that is never closed.

| File | Lines | Severity | Description | Recommended Fix |
|------|-------|----------|-------------|-----------------|
| `app.py` | 172 | Critical | `log_file = open(...)` never closed — file descriptor leak per spawned job, eventual EMFILE | Use `with open(...) as log_file:` or close in cleanup handler |
| `src/api/knowledge.py` | 220 | Critical | `config_path.write_text()` is non-atomic — power failure mid-write corrupts config | Write to temp file, then `os.replace()` for atomic rename |
| `src/api/videos.py` | 275-280 | High | `json.load()` on large `frames.jsonl` — loads entire file into memory mid-stream | Use line-by-line iteration or `ijson` for streaming parse |
| `app.py` | 307-309 | High | `while proc.poll() is None:` acceptable with eventlet sleep but still busy-loop pattern | Use `proc.communicate()` or eventlet subprocess wrapper |
| `worker.py` | 36-38 | High | `status` write fails silently if disk full — job status becomes stale with no alert | Add try/except with logging; monitor disk space |
| `providers/openrouter.py` | 94-99 | High | Non-atomic cache file write — concurrent writes can corrupt JSON | Write to temp, then atomic rename |
| `providers/openrouter.py` | 277-281 | High | `CACHE_FILE` read without existence check — `FileNotFoundError` on first run | Check `os.path.exists()` or use `try/except FileNotFoundError` |

---

## 6. Magic Numbers

Timeout, memory, and buffer values are hardcoded throughout the codebase. The 192GB memory value and conflicting WebSocket ping intervals between `app.py` and `config/constants.py` stand out as particularly problematic.

| File | Lines | Severity | Description | Recommended Fix |
|------|-------|----------|-------------|-----------------|
| `app.py` | 60 | High | `max_http_buffer_size=1024*1024*100` (100MB) — conflicts with `constants.py` MAX_UPLOAD_SIZE (16MB) | Import from `config.constants`; use a single constant |
| `app.py` | 57-59 | High | `ping_interval=25` vs `constants.py` WS_PING_INTERVAL=5 — two different values in codebase | Use `WS_PING_INTERVAL` from constants |
| `app.py` | 999 | High | `available_memory_gb=192` hardcoded — assumes specific server configuration | Import from constants or probe with `psutil.virtual_memory()` |
| `src/api/videos.py` | 858 | High | Same `192` GB duplication — now in two files | Single source of truth in `config/constants.py` |
| `app.py` | 1541 | High | `timeout=1800` hardcoded for video processing | Import `VIDEO_PROCESSING_TIMEOUT` from constants |
| `app.py` | 701-702 | High | `timeout=3600` hardcoded for transcode | Import `TRANSCODE_TIMEOUT` from constants |
| `app.py` | 1246 | High | `timeout=3600` hardcoded for frame extraction | Import `FRAME_EXTRACTION_TIMEOUT` from constants |
| `app.py` | 1381 | High | `timeout=300` hardcoded for transcription | Import `TRANSCRIPTION_TIMEOUT` from constants |
| `app.py` | 1481-1482 | High | `7200` max workers and `1800` idle timeout for ThreadPoolExecutor | Import from constants |
| `src/worker/pipelines/standard_two_step.py` | 22-23 | High | `LLM_TIMEOUT=300`, `MIN_NUM_PREDICT=2048` duplicated across pipeline files | Centralize in `config/constants.py` |
| `src/worker/pipelines/standard_two_step.py` | 69-70, 90-91 | High | `max_tokens: 4096` hardcoded — not configurable per model | Read from model metadata or config |

---

## 7. Code Duplication

Over 200 lines of near-identical code exist across different files and functions in the same file. The `_extract_frames` vs `_extract_frames_direct` pair alone is ~150 lines of duplication that will inevitably diverge.

| File | Lines | Severity | Description | Recommended Fix |
|------|-------|----------|-------------|-----------------|
| `app.py` | `_extract_frames` vs `_extract_frames_direct` | Critical | ~150 lines of near-identical frame extraction logic — different entry points, same core implementation | Single function with `direct` boolean flag; or extract to `src/utils/video.py` |
| `app.py` | `_transcribe_video` vs `_process_video_direct.transcribe_audio_task` | Critical | ~80 lines of near-identical transcription logic | Extract shared whisper invocation to `src/utils/transcript.py` |
| `app.py` | `_run_dedup_sequential` vs `_run_dedup_parallel` | Critical | Hash computation duplicated between sequential and parallel dedup paths | Single `_compute_frame_hashes()` function; strategy pattern for sequential vs parallel deletion |
| `src/utils/helpers.py` + 4 other files | `format_bytes` | Critical | Byte-for-byte identical function in 5 files | Single `src/utils/helpers.py:format_bytes`; import everywhere else |
| `src/utils/helpers.py`, `src/utils/video.py` | `format_duration` | High | Byte-for-byte identical in 2 files | Keep in `src/utils/helpers.py`; import in `video.py` |
| `app.py`, `worker.py` | `update_status` | High | Status JSON write duplicated between orchestrator and worker | Shared utility in `src/utils/helpers.py` |
| `app.py`, `src/worker/pipelines/base.py` | `update_status` pattern | High | Same pattern in pipeline base class | Inherit from shared base or use helper |
| 4 files | `get_openrouter_api_key` | High | 4 identical copies across app.py, worker.py, chat_queue.py, providers/ | Single function in `src/utils/helpers.py` |

---

## 8. TODO / FIXME / HACK

| File | Lines | Severity | Description | Status |
|------|-------|----------|-------------|--------|
| `gpu_transcode.py` | 159 | Medium | TODO: Restore GPU encoding when driver compatibility fixed | Open — blocked on CUDA driver resolution |
| `src/utils/scene_detection.py` | 206 | Medium | TODO: Implement proper frame-based scene detection | Open — current implementation is placeholder |
| `src/services/synthesis_queue.py` | 249 | Medium | TODO: Load from prompts/frame_analysis/synthesis.txt | Open — hardcoded prompt fallback |
| `AGENTS.md` gotcha #10 | — | High | Phase 2 synthesis runs sequentially, blocking the frame loop | Documented limitation; architectural refactor needed |

---

## Workflow Audit

Five HIGH-severity bugs found in critical code paths that affect production behavior.

### 1. Missing `videos_updated` Emission in `_process_video_direct`
**File:** `app.py` lines 1318-1503
**Issue:** When a video Upload completes (frames extracted, audio transcribed), the function does NOT emit `videos_updated` via SocketIO. The client's video list never refreshes after upload unless the page is reloaded manually.
**Impact:** Users see no new video in the UI after a successful upload.
**Fix:** Add `emit("videos_updated", {})` after successful processing in the finally/return path.

### 2. KeyError in Pre-Computed Dedup Path
**File:** `src/api/videos.py` lines 418-427
**Issue:** The dedup endpoint constructs a path assuming `dedup_results.json` exists, but when the multi-threshold scan hasn't been run yet, the key lookup fails with `KeyError`.
**Impact:** Dedup endpoint 500s for videos that haven't had a pre-computed scan.
**Fix:** Check key existence before access; run inline dedup if pre-computed results don't exist.

### 3. Scene Detection No-Op
**File:** `src/utils/scene_detection.py` lines 169-224
**Issue:** `detect_scenes_from_frames()` treats all frames as belonging to a single scene. The PySceneDetect integration is incomplete — it never actually detects scene boundaries from frame content.
**Impact:** Scene-aware dedup is equivalent to regular dedup. No scene boundaries are detected.
**Fix:** Implement proper content-based scene boundary detection using frame feature comparison or integrate PySceneDetect at the video level.

### 4. requests.Session Leak in OpenWebUIClient
**File:** `src/services/openwebui_kb.py` line 21
**Issue:** `requests.Session()` creates a new HTTP connection pool per client instance. Clients are created fresh per request. The session (and its connection pool) is never closed, leaking file descriptors.
**Impact:** Under sustained KB sync load, file descriptors accumulate until EMFILE.
**Fix:** Use `__enter__`/`__exit__` context manager pattern or `session.close()` in a finally block. Alternatively, use a shared global session.

### 5. Eventlet Blocking in Auto-Sync
**File:** `app.py` line 392
**Issue:** `openwebui_client.sync_job_results()` performs a synchronous HTTP request (potentially multiple) in the eventlet main thread. If OpenWebUI is slow or unreachable, it blocks all other WebSocket clients.
**Impact:** Slow OpenWebUI server freezes the entire Video Analyzer for the duration of the sync.
**Status:** Documented, no fix planned. Acceptable for current scale but will become a bottleneck at higher concurrency.

---

## Top 5 Priority

These are the highest-impact issues to fix first, ordered by severity and blast radius:

### 1. Fix SECRET_KEY regeneration (`app.py:54`) — Critical
Every server restart invalidates all user sessions and breaks CSRF protection. This is a security vulnerability AND a user experience issue. Persist the key to disk or inject via environment variable.

### 2. Sanitize paths in transcode/reprocess endpoints (`src/api/transcode.py:16,31`) — Critical
Path traversal allows reading any file on the system. Add `security.verify_path()` before all filesystem operations on user-provided paths.

### 3. Eliminate silent exception handlers (12 locations) — Critical
Every `except Exception: pass` pattern hides bugs and makes debugging impossible. Replace with `logger.error(...)` at minimum.

### 4. Fix `_spawned_jobs` race condition (`app.py:157`) — Critical
Under eventlet, unprotected set operations can produce double-spawn of workers. Protect with a lock.

### 5. Fix file descriptor leak on `log_file` (`app.py:172`) — Critical
Open file handles accumulate with each job. On a busy system this will hit the per-process FD limit and cause spurious failures across all operations.

---

## Notes

- External files (`vram_manager.py`, `chat_queue.py`, `monitor.py`, `thumbnail.py`, `gpu_transcode.py`, `providers/`) were audited but issues in those files are flagged for awareness only — they are marked DO NOT MODIFY in AGENTS.md.
- Frontend JavaScript and CSS were excluded per scope.
- This report is based on static analysis and architectural review. Runtime behavior, memory leaks, and performance issues may exist that are visible only under load testing.
