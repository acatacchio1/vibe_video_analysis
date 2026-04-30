# API Documentation

This document provides comprehensive documentation for the Video Analyzer Web REST API and SocketIO events.

**Base URL**: `http://localhost:10000/api/`

## Authentication

Currently no authentication is required. All endpoints are publicly accessible.

## Error Response Format

```json
{
  "error": {
    "code": 400,
    "message": "Error description"
  }
}
```

All errors use the `api_error(message, code)` helper returning this format.

---

## REST API Endpoints

### Videos API

| Method | Path | Description | CLI Equivalent |
|--------|------|-------------|----------------|
| GET | `/api/videos` | List uploaded videos with metadata | `va videos list` |
| POST | `/api/videos/upload` | Upload video file (parallel frames + transcription) | `va videos upload <file>` |
| DELETE | `/api/videos/<filename>` | Delete video + thumbnails + job data | `va videos delete <name>` |
| GET | `/api/videos/<filename>/frames` | Frame metadata (count, fps, duration) | `va videos frames <name>` |
| GET | `/api/videos/<filename>/frames/<n>` | Get specific frame image | — |
| GET | `/api/videos/<filename>/frames/<n>/thumb` | Get frame thumbnail | — |
| GET | `/api/videos/<filename>/frames_index` | Get frame timestamp index | `va videos frames-index <name>` |
| GET | `/api/videos/<filename>/transcript` | Get transcript data | `va videos transcript <name>` |
| POST | `/api/videos/<filename>/dedup` | Apply deduplication at threshold | `va videos dedup <name> --threshold <n>` |
| POST | `/api/videos/<filename>/dedup-multi` | Multi-threshold dedup scan | `va videos dedup-multi <name> --thresholds "5,10,15"` |
| GET/POST | `/api/videos/<filename>/scenes` | Scene detection | `va videos scenes <name>` |
| POST | `/api/videos/<filename>/scene-aware-dedup` | Scene-aware dedup | `va videos scene-dedup <name>` |
| POST | `/api/videos/reprocess` | Re-extract + re-transcribe | `va videos reprocess <name>` |

#### GET `/api/videos`

List all videos (both processed and source).

```json
[
  {
    "filename": "video.mp4",
    "size": 10485760,
    "duration": 120.5,
    "fps": 1.0,
    "frame_count": 120,
    "type": "processed",
    "has_frames": true,
    "has_transcript": true,
    "has_dedup": false
  }
]
```

#### POST `/api/videos/upload`

Upload a video file. Starts parallel frame extraction and audio transcription.

**Request:** `multipart/form-data`
- `file`: Video file (required)
- `fps`: Frames per second for extraction (default: 1.0)
- `whisper_model`: Whisper model — `tiny`, `base`, `small`, `medium`, `large` (default: `base`)
- `language`: ISO 639-1 language code (default: auto-detect)

**Response:**
```json
{
  "success": true,
  "filename": "video.mp4",
  "size": 10485760,
  "duration": 120.5
}
```

> **Note**: Source videos are preserved. Processed frames go to `uploads/<video_name>/frames/`.

### Providers API

| Method | Path | Description | CLI Equivalent |
|--------|------|-------------|----------------|
| GET | `/api/providers` | List all providers | `va providers list` |
| GET | `/api/providers/litellm/models` | List models via LiteLLM proxy | `va models litellm --server <url>` |
| GET | `/api/providers/openrouter/models` | List OpenRouter models | `va models openrouter` |
| GET | `/api/providers/openrouter/cost` | Estimate cost | `va providers cost --model <m> --frames <n>` |
| GET | `/api/providers/openrouter/balance` | Check balance | `va providers balance` |

#### GET `/api/providers`

```json
[
  {
    "name": "LiteLLM",
    "type": "litellm",
    "url": "http://172.16.17.3:4000/v1",
    "status": "online",
    "models": ["qwen3-27b-q8", "qwen3-27b-best", "vision-best"]
  },
  {
    "name": "OpenRouter",
    "type": "openrouter",
    "status": "online"
  }
]
```

#### GET `/api/providers/litellm/models`

Fetch available models from the LiteLLM proxy.

**Query Parameters:**
- `server`: LiteLLM proxy URL (default: `http://172.16.17.3:4000/v1`)

**Response:**
```json
{
  "server": "http://172.16.17.3:4000/v1",
  "models": ["qwen3-27b-q8", "qwen3-27b-best", "vision-best"],
  "status": "online"
}
```

> **LiteLLM Proxy**: The app routes all LLM requests through a LiteLLM proxy at `http://172.16.17.3:4000/v1`. The proxy handles load balancing, rate limiting, and context management across backend GPU instances running `qwen3-27b-q8` on GPU backends.

### Jobs API

| Method | Path | Description | CLI Equivalent |
|--------|------|-------------|----------------|
| GET | `/api/jobs` | List all jobs | `va jobs list` |
| GET | `/api/jobs/<id>` | Get job details | `va jobs show <id>` |
| DELETE | `/api/jobs/<id>` | Cancel job (kills process group) | `va jobs cancel <id>` |
| POST | `/api/jobs/<id>/priority` | Update job priority | `va jobs priority <id> <n>` |
| GET | `/api/jobs/<id>/results` | Get job results | `va jobs results <id>` |

#### GET `/api/jobs`

```json
[
  {
    "job_id": "abc-123-def",
    "video_path": "uploads/video.mp4",
    "video_name": "video.mp4",
    "status": "running",
    "stage": "frame_analysis",
    "progress": 45,
    "current_frame": 54,
    "total_frames": 120,
    "priority": 0,
    "gpu_assigned": 0,
    "pid": 12345,
    "created_at": "2026-04-27T10:00:00",
    "started_at": "2026-04-27T10:00:05"
  }
]
```

### LLM Chat API

| Method | Path | Description | CLI Equivalent |
|--------|------|-------------|----------------|
| POST | `/api/llm/chat` | Submit chat job | `va llm chat <message> --context live` |
| GET | `/api/llm/chat/<id>` | Poll chat job status | `va llm status <id>` |
| DELETE | `/api/llm/chat/<id>` | Cancel chat job | `va llm cancel <id>` |
| GET | `/api/llm/queue/stats` | Chat queue statistics | `va llm queue-stats` |

#### POST `/api/llm/chat`

```json
{
  "message": "Summarize the video",
  "context": "live",
  "job_id": "abc-123-def",
  "provider_type": "litellm",
  "provider_name": "LiteLLM",
  "model": "qwen3-27b-q8",
  "litellm_url": "http://172.16.17.3:4000/v1",
  "temperature": 0.0
}
```

### Results API

| Method | Path | Description | CLI Equivalent |
|--------|------|-------------|----------------|
| GET | `/api/results` | List stored results | `va results list` |

#### GET `/api/results`

```json
[
  {
    "job_id": "abc-123-def",
    "video_name": "video.mp4",
    "video_description": "A person giving a presentation...",
    "frame_count": 120,
    "created_at": "2026-04-27T10:00:00"
  }
]
```

### System API

| Method | Path | Description | CLI Equivalent |
|--------|------|-------------|----------------|
| GET | `/api/vram` | VRAM status | `va system vram` |
| GET | `/api/gpus` | GPU list with details | `va system gpus` |
| GET/POST | `/api/debug` | Toggle debug mode | `va system debug` |

#### GET `/api/vram`

```json
{
  "gpus": [
    {
      "index": 0,
      "name": "NVIDIA GeForce RTX 4090",
      "total_vram": 24576,
      "used_vram": 8192,
      "free_vram": 16384,
      "utilization": 33,
      "temperature": 65
    }
  ],
  "total_vram": 24576,
  "used_vram": 8192,
  "free_vram": 16384,
  "available_for_jobs": 15384,
  "jobs_running": 2,
  "jobs_queued": 1
}
```

### Knowledge Base API

| Method | Path | Description | CLI Equivalent |
|--------|------|-------------|----------------|
| GET | `/api/knowledge/status` | OpenWebUI config status | `va knowledge status` |
| POST | `/api/knowledge/config` | Save OpenWebUI config | `va knowledge config --url <url> --key <key>` |
| POST | `/api/knowledge/test` | Test OpenWebUI connection | `va knowledge test` |
| GET | `/api/knowledge/bases` | List KBs from OpenWebUI | `va knowledge bases` |
| POST | `/api/knowledge/sync/<id>` | Sync single job to KB | `va knowledge sync <id>` |
| POST | `/api/knowledge/sync-all` | Sync all jobs to KB | `va knowledge sync-all` |
| POST | `/api/knowledge/send/<id>` | Send job to specific KB | `va knowledge send <id> --kb <name>` |

---

## SocketIO Events

### Client → Server

| Event | Data | Purpose |
|-------|------|---------|
| `start_analysis` | `{video_path, provider_type, provider_name, model, priority, provider_config, params}` | Start analysis job |
| `subscribe_job` | `{job_id}` | Subscribe to job updates |
| `unsubscribe_job` | `{job_id}` | Unsubscribe from job updates |

### Server → Client

| Event | Data | Purpose |
|-------|------|---------|
| `job_created` | `{job_id, status}` | Analysis job submitted |
| `job_status` | `{job_id, stage, progress, current_frame, total_frames}` | Job progress |
| `frame_analysis` | `{job_id, frame_number, analysis, timestamp, video_ts, transcript_context}` | Vision analysis per frame |
| `frame_synthesis` | `{job_id, frame_number, combined_analysis, vision_analysis}` | Combined analysis per frame |
| `job_transcript` | `{job_id, transcript}` | Full transcript text |
| `job_description` | `{job_id, description}` | Final video description |
| `job_complete` | `{job_id, success}` | Job finished |
| `videos_updated` | `{}` | Video list changed |
| `vram_event` | `{event, job}` | VRAM manager status change |
| `system_status` | `{type, data}` | nvidia-smi / litellm proxy status output |
| `log_message` | `{level, message, timestamp}` | Server log lines |
| `video_processing_progress` | `{source, stage, progress, message}` | Upload processing (parallel) |
| `kb_sync_complete` | `{job_id, kb_id}` | OpenWebUI sync done |
| `kb_sync_error` | `{job_id, error}` | OpenWebUI sync failed |

---

## CLI Usage

The `va` CLI provides equivalent access to all API endpoints from the terminal.

### Configuration

```bash
# Set server URL
va config set url http://127.0.0.1:10001

# Set OpenRouter API key
va config set openrouter_api_key sk-or-...

# View all settings
va config show
```

Config stored at `~/.video-analyzer-cli.json`.

### Quick Examples

```bash
# List videos
va videos list

# Upload and process video
va videos upload myvideo.mp4 --whisper-model large

# Start analysis
va jobs start --video myvideo.mp4 --provider litellm --model qwen3-27b-q8

# View system status
va system vram

# Chat with LLM about a job
va llm chat "Summarize this video" --context live --job-id abc-123
```

For full CLI reference, see [CLI.md](CLI.md).

---

## WebSocket Configuration

- **Path**: `/socket.io/`
- **Transports**: `websocket`, `polling`
- **Ping interval**: 25 seconds
- **Ping timeout**: 60 seconds
- **Max buffer size**: 100MB

## CORS

Permissive CORS: `Access-Control-Allow-Origin: *`

## Rate Limits

- **Uploads**: 1GB max file size (`MAX_FILE_SIZE`)
- **Chat requests**: 5 concurrent jobs, 30 per minute (rate-limited via `chat_queue.py`)
- **Job queue**: Priority-based scheduling, max 2 concurrent per GPU
- **API requests**: No explicit rate limiting

## Examples

### List Videos (curl)
```bash
curl http://localhost:10000/api/videos
```

### Upload Video (curl)
```bash
curl -X POST http://localhost:10000/api/videos/upload \
  -F "file=@video.mp4" \
  -F "whisper_model=large"
```

### Get VRAM Status (curl)
```bash
curl http://localhost:10000/api/vram
```

### List Videos (CLI)
```bash
va videos list
```

### Start Analysis (CLI)
```bash
va --url http://127.0.0.1:10001 jobs start \
  --video video.mp4 \
  --provider litellm \
  --model qwen3-27b-q8
```
