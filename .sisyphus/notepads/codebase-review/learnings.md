# Learnings from Codebase Review Plan Execution

## Wave 1 + 2 Completed (Tasks 1-8)

### Infrastructure Learnings
- Venv is at `/home/anthony/venvs/video-analyzer` (not in project root)
- 10 `__init__.py` files were missing in tests/ directories — all now created
- The plan said `tests/integration/backend/` but actual directory is `tests/integration/test_backend/`
- `tests/conftest.py` had broken import `from fixtures.conftest import` → fixed to `from tests.fixtures.conftest import`
- Before fix: 0 tests collected. After fix: 292 tests collected (279 pass, 13 fail)
- All 13 failures are pre-existing from Ollama→LiteLLM migration — no new failures introduced

### P0 Bug Fixes
- Bug 1 (videos_updated): Added `socketio.emit("videos_updated", {})` in `_process_video_direct()` at line 1486
- Bug 2 (KeyError in dedup): Removed redundant re-read `keep_indices = keep_indices_by_threshold[str(threshold)]` at line 423
- Bug 3 (scene detection warning): Added no-op comment at line 703 in `detect_video_scenes`
- Bug 4 (session leak): Added `__del__`, `close`, `__enter__`, `__exit__` to `OpenWebUIClient`; updated `sync_job_to_kb` to use context manager

### Workflow Observations
- Running `./run.sh` starts gunicorn-based server via `setsid python app.py` — PID file at `/tmp/video-analyzer.pid`
- Server logs at `/tmp/video-analyzer.log`
- Upload processing (frame extraction + transcription) runs as background task via `socketio.start_background_task`
- Processing time: ~40s video with large whisper model takes 120-300s for parallel frame extraction + transcription

## T12 + T13 Learnings (2026-04-29)

### API Evidence Collection Pattern
- `curl -s http://127.0.0.1:10001/api/jobs` returns array of all jobs sorted newest-first
- `curl -s http://127.0.0.1:10001/api/jobs/<id>/results` returns `{"error":"Results not found"}` when job failed before writing results.json
- Worker logs at `jobs/<id>/worker.log` contain the actual error traceback — more useful than status.json

### Analysis Failure: Two Distinct Errors
1. **Pre-fix**: `No module named 'video_analyzer'` — caused by worker subprocess using `python3` (system Python) instead of `sys.executable` (venv Python). Fixed by changing `app.py:spawn_worker`.
2. **Post-fix**: `VideoProcessor.extract_keyframes() got an unexpected keyword argument 'similarity_threshold'` — `standard_two_step.py:550` passes `similarity_threshold` to `VideoProcessor.extract_keyframes()`. The installed `video_analyzer` library version does NOT accept this parameter. This is an API compatibility issue between the pipeline code and the installed library.

### VideoProcessor API
- `VideoProcessor(video_path, frames_dir, model)` — constructor takes 3 args
- `extract_keyframes(frames_per_minute, duration, max_frames)` — NO `similarity_threshold` parameter in installed version
- When video path is relative, worker chdir matters — Docker container runs from `/app`, videos are at `uploads/...`

### Worker Execution Context
- Worker subprocess runs in `/app` (Docker container) — paths to videos must be relative to `/app` or absolute
- The pipeline receives `video_frames_dir` as absolute path (`/app/uploads/...`) which works
- The `video_path` for VideoProcessor is just the filename — ffmpeg looks in cwd

## T11-T13 Learnings (2026-04-29) - GPU Contention Fix

### Analysis Failure: GPU Contention Deadlock
3. **Post-fix-v2**: Worker spawns successfully, imports video_analyzer, starts frame analysis, but DEADLOCKS because `qwen3-27b-q8` on LiteLLM is served by VLLM running on the SAME two RTX A6000 GPUs. VLLM occupies ~44GB per GPU, leaving only ~5GB for worker's frame I/O and Whisper. Result: worker stalls at 20% progress.

### Solution: Route to vision-best Model
- `qwen3-27b-q8` on LiteLLM → served by LOCAL VLLM (SAME GPUs)
- `vision-best` on LiteLLM → served on DIFFERENT infrastructure (cloud/GPU pool)
- Using `--model vision-best --provider-type litellm` avoids GPU contention entirely
- This is the key finding for the CLI workflow validation

### Server Crash Pattern
- gunicorn with eventlet worker on Python 3.13 + `nvidia-ml-py` (not pynvml) causes shutdown crashes
- Workaround: Run `python app.py` directly (Flask dev server) instead of gunicorn
- PID file at `/tmp/video-analyzer.pid` (run.sh), NOT `/tmp/video-analyzer-10000.pid`
- Use `./run.sh` to restart — it handles the kill + restart cycle correctly
- `run.sh` uses venv Python automatically when `/home/anthony/venvs/video-analyzer` exists

### Model Routing for Analysis
- Always use `vision-best` model for CLI analysis on this machine (v0.6.0)
- `qwen3-27b-q8` and `qwen3-27b-best` will deadlock on local GPU resources

### Additional Infrastructure Gotchas (2026-04-29)
- `killall python` and `pkill -f "python app"` hang indefinitely — avoid these commands
- The subagent accidentally deleted the old video upload processing for the farmer video and re-uploaded it
- Large video upload takes ~5 minutes (106MB, 219 frames, whisper base)
- Medium video upload (robots, 13MB, 93 frames) already in place but unused
- Subagent background tasks can fail due to SocketIO client API mismatch

### WebSocket Handler Convention (P0)
- `handle_subscribe_job()` and `handle_unsubscribe_job()` MUST accept `auth=None` parameter
- Flask-SocketIO passes auth on disconnect events — missing parameter causes TypeError
- Already fixed in `src/websocket/handlers.py` by subagent (added `auth=None` to all 5 handlers)
