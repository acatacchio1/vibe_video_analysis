# API Documentation

This document provides comprehensive documentation for the Video Analyzer Web REST API.

**Base URL**: `http://localhost:10000"># API Documentation

Video Analyzer Web provides a REST API for video upload, analysis, and management. All endpoints are prefixed with `/api/`.

## Base URL
```
http://localhost:10000/api/
```

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

## Endpoints

### Videos API

#### GET `/api/videos`
List all uploaded videos.

**Response:**
```json
[
  {
    "filename": "video.mp4",
    "size": 10485760,
    "duration": 120.5,
    "frames_count": 3600,
    "transcoded": true,
    "uploaded_at": "2026-04-22T12:00:00Z"
  }
]
```

#### POST `/api/videos/upload`
Upload a video file.

**Request:** `multipart/form-data`
- `file`: Video file (MP4, AVI, MOV, MKV, WebM)
- `fps`: Optional, frames per second for extraction (default: 1.0)
- `whisper_model`: Optional, transcription model (base, large, etc.)
- `language`: Optional, transcription language (en, es, fr, etc.)

**Response:**
```json
{
  "success": true,
  "filename": "video_720p.mp4",
  "size": 10485760,
  "duration": 120.5
}
```

#### DELETE `/api/videos/<filename>`
Delete a video and all associated files.

**Response:**
```json
{
  "success": true,
  "message": "Video deleted"
}
```

#### GET `/api/videos/<filename>/frames`
Get frames for a video.

**Query Parameters:**
- `limit`: Maximum frames to return (default: 100)
- `offset`: Starting offset (default: 0)

**Response:**
```json
[
  {
    "frame_num": 1,
    "timestamp": 0.0,
    "path": "frames/video/frame_000001.jpg",
    "hash": "abc123..."
  }
]
```

#### GET `/api/videos/<filename>/frames_index`
Get frame index mapping.

**Response:**
```json
{
  "1": 0.0,
  "2": 1.0,
  "3": 2.0,
  ...
}
```

#### GET `/api/videos/<filename>/transcript`
Get video transcript.

**Response:**
```json
[
  {
    "start": 0.0,
    "end": 5.0,
    "text": "Hello, welcome to this video."
  }
]
```

#### GET `/api/videos/<filename>/scenes`
Get scene detection results.

**Response:**
```json
{
  "scenes": [
    {
      "scene_num": 1,
      "start_frame": 1,
      "end_frame": 150,
      "start_time": 0.0,
      "end_time": 5.0
    }
  ],
  "statistics": {
    "total_scenes": 10,
    "avg_duration": 12.5
  }
}
```

#### POST `/api/videos/<filename>/dedup`
Create deduplicated version of video.

**Request Body:**
```json
{
  "threshold": 10,
  "fps": 1.0
}
```

**Response:**
```json
{
  "success": true,
  "dedup_filename": "video_dedup_720p.mp4",
  "original_frames": 3600,
  "dedup_frames": 1200,
  "reduction_percent": 66.7
}
```

#### POST `/api/videos/<filename>/scene-aware-dedup`
Create scene-aware deduplicated version.

**Request Body:**
```json
{
  "threshold": 10,
  "fps": 1.0,
  "min_scene_frames": 30,
  "max_scene_frames": 300
}
```

#### POST `/api/videos/<filename>/dedup-multi`
Create multiple dedup versions with different thresholds.

**Request Body:**
```json
{
  "thresholds": [5, 10, 15],
  "fps": 1.0
}
```

#### POST `/api/videos/transcode`
Transcode a video file (background task).

**Request Body:**
```json
{
  "input_path": "/path/to/video.mp4",
  "output_path": "/path/to/output.mp4"
}
```

#### POST `/api/videos/reprocess`
Reprocess a video (extract frames, transcribe).

**Request Body:**
```json
{
  "filename": "video.mp4",
  "fps": 1.0,
  "whisper_model": "base",
  "language": "en"
}
```

### Jobs API

#### GET `/api/jobs`
List all jobs.

**Response:**
```json
[
  {
    "job_id": "abc123",
    "video_filename": "video.mp4",
    "status": "running",
    "progress": 45,
    "created_at": "2026-04-22T12:00:00Z",
    "updated_at": "2026-04-22T12:01:00Z"
  }
]
```

#### GET `/api/jobs/running`
Get running jobs.

#### GET `/api/jobs/queued`
Get queued jobs.

#### GET `/api/jobs/<job_id>`
Get job details.

**Response:**
```json
{
  "job_id": "abc123",
  "video_filename": "video.mp4",
  "status": "running",
  "progress": 45,
  "frames_analyzed": 450,
  "total_frames": 1000,
  "created_at": "2026-04-22T12:00:00Z",
  "started_at": "2026-04-22T12:00:05Z",
  "updated_at": "2026-04-22T12:01:00Z",
  "settings": {
    "fps": 1.0,
    "provider": "Ollama-Local",
    "model": "llama3.2:3b"
  }
}
```

#### GET `/api/jobs/<job_id>/frames`
Get frames analyzed by job.

**Query Parameters:**
- `limit`: Maximum frames to return (default: 100)
- `offset`: Starting offset (default: 0)

**Response:**
```json
[
  {
    "frame_num": 1,
    "timestamp": 0.0,
    "analysis": "A person is speaking...",
    "provider": "Ollama-Local",
    "model": "llama3.2:3b"
  }
]
```

#### GET `/api/jobs/<job_id>/results`
Get job results.

**Response:**
```json
{
  "job_id": "abc123",
  "video_filename": "video.mp4",
  "status": "completed",
  "video_description": "This video shows...",
  "frame_analyses": [
    {
      "frame_num": 1,
      "timestamp": 0.0,
      "analysis": "A person is speaking..."
    }
  ],
  "statistics": {
    "total_frames": 1000,
    "frames_analyzed": 1000,
    "processing_time": 125.5,
    "frames_per_second": 8.0
  },
  "created_at": "2026-04-22T12:00:00Z",
  "completed_at": "2026-04-22T12:02:05Z"
}
```

#### DELETE `/api/jobs/<job_id>`
Cancel a job.

**Response:**
```json
{
  "success": true,
  "message": "Job cancelled"
}
```

#### POST `/api/jobs/<job_id>/priority`
Update job priority.

**Request Body:**
```json
{
  "priority": "high"
}
```

**Priority values:** `low`, `normal`, `high`

### Providers API

#### GET `/api/providers`
List available AI providers.

**Response:**
```json
[
  {
    "name": "Ollama-Local",
    "type": "ollama",
    "url": "http://host.docker.internal:11434",
    "status": "online"
  },
  {
    "name": "OpenRouter",
    "type": "openrouter",
    "url": "https://openrouter.ai/api/v1",
    "status": "online"
  }
]
```

#### POST `/api/providers/discover`
Discover Ollama instances on network.

**Response:**
```json
{
  "discovered": [
    "http://192.168.1.100:11434",
    "http://192.168.1.101:11434"
  ]
}
```

#### GET `/api/providers/ollama-instances`
Get known Ollama instances.

#### POST `/api/providers/ollama-instances`
Add Ollama instance.

**Request Body:**
```json
{
  "url": "http://192.168.1.100:11434"
}
```

#### GET `/api/providers/ollama/models`
Get available Ollama models.

**Response:**
```json
[
  {
    "name": "llama3.2:3b",
    "size": "3.2B",
    "modified": "2026-04-20T10:00:00Z",
    "vram_required": 4096
  }
]
```

#### GET `/api/providers/openrouter/models`
Get available OpenRouter models.

#### GET `/api/providers/openrouter/cost`
Estimate cost for OpenRouter model.

**Query Parameters:**
- `model`: Model name
- `prompt_tokens`: Number of prompt tokens
- `completion_tokens`: Number of completion tokens

**Response:**
```json
{
  "model": "anthropic/claude-3.5-sonnet",
  "prompt_cost": 0.003,
  "completion_cost": 0.015,
  "total_cost": 0.018,
  "currency": "USD"
}
```

#### GET `/api/providers/openrouter/balance`
Check OpenRouter balance.

**Response:**
```json
{
  "balance": 10.5,
  "currency": "USD",
  "last_updated": "2026-04-22T12:00:00Z"
}
```

### LLM Chat API

#### POST `/api/llm/chat`
Send chat message.

**Request Body:**
```json
{
  "message": "What is in this video?",
  "context": "job",
  "job_id": "abc123",
  "provider": "Ollama-Local",
  "model": "llama3.2:3b",
  "stream": false
}
```

**Context values:** `job`, `live`, `modal`

**Response (non-streaming):**
```json
{
  "response": "The video shows...",
  "provider": "Ollama-Local",
  "model": "llama3.2:3b",
  "tokens": 150,
  "time": 2.5
}
```

#### GET `/api/llm/chat/<job_id>`
Get chat history for job.

**Response:**
```json
[
  {
    "role": "user",
    "content": "What is in this video?",
    "timestamp": "2026-04-22T12:00:00Z"
  },
  {
    "role": "assistant",
    "content": "The video shows...",
    "timestamp": "2026-04-22T12:00:02Z"
  }
]
```

#### DELETE `/api/llm/chat/<job_id>`
Clear chat history for job.

#### GET `/api/llm/queue/stats`
Get chat queue statistics.

**Response:**
```json
{
  "queue_length": 2,
  "running_jobs": 1,
  "max_concurrent_jobs": 3,
  "jobs_per_minute": 5
}
```

### Results API

#### GET `/api/results`
Get stored analysis results.

**Query Parameters:**
- `limit`: Maximum results to return (default: 50)
- `offset`: Starting offset (default: 0)

**Response:**
```json
[
  {
    "job_id": "abc123",
    "video_filename": "video.mp4",
    "video_description": "This video shows...",
    "created_at": "2026-04-22T12:00:00Z",
    "duration": 120.5,
    "frames_analyzed": 1000
  }
]
```

### Knowledge Base API

#### GET `/api/knowledge/status`
Get OpenWebUI Knowledge Base status.

**Response:**
```json
{
  "enabled": true,
  "url": "http://localhost:3000",
  "connected": true,
  "bases": ["video-analysis", "transcripts"]
}
```

#### POST `/api/knowledge/config`
Configure OpenWebUI Knowledge Base.

**Request Body:**
```json
{
  "enabled": true,
  "url": "http://localhost:3000",
  "api_key": "sk-...",
  "base_name": "video-analysis",
  "auto_sync": true
}
```

#### POST `/api/knowledge/test`
Test OpenWebUI Knowledge Base connection.

**Response:**
```json
{
  "success": true,
  "message": "Connected successfully"
}
```

#### GET `/api/knowledge/bases`
Get available knowledge bases.

#### POST `/api/knowledge/sync/<job_id>`
Sync job results to knowledge base.

**Response:**
```json
{
  "success": true,
  "message": "Synced to knowledge base",
  "documents_added": 2
}
```

#### POST `/api/knowledge/sync-all`
Sync all completed jobs to knowledge base.

#### POST `/api/knowledge/send/<job_id>`
Send job context to LLM via knowledge base.

**Request Body:**
```json
{
  "message": "Summarize this video",
  "provider": "Ollama-Local",
  "model": "llama3.2:3b"
}
```

### System API

#### GET `/api/vram`
Get GPU VRAM information.

**Response:**
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

#### GET `/api/gpus`
Get GPU information.

#### GET `/api/debug`
Debug endpoint (development only).

### Thumbnail API

#### GET `/api/thumbnail/<filename>`
Get video thumbnail.

**Query Parameters:**
- `time`: Timestamp in seconds (default: 0)
- `width`: Width in pixels (default: 320)
- `height`: Height in pixels (default: 180)

**Response:** JPEG image

## SocketIO Events

### Client → Server Events

#### `connect`
Client connects to SocketIO.

#### `disconnect`
Client disconnects.

#### `subscribe_job`
Subscribe to job updates.

**Data:**
```json
{
  "job_id": "abc123"
}
```

#### `unsubscribe_job`
Unsubscribe from job updates.

**Data:**
```json
{
  "job_id": "abc123"
}
```

#### `start_analysis`
Start video analysis job.

**Data:**
```json
{
  "video_filename": "video.mp4",
  "fps": 1.0,
  "provider": "Ollama-Local",
  "model": "llama3.2:3b",
  "prompt": "Describe what you see in this frame.",
  "priority": "normal"
}
```

#### `cancel_job`
Cancel a running job.

**Data:**
```json
{
  "job_id": "abc123"
}
```

### Server → Client Events

#### `job_progress`
Job progress update.

**Data:**
```json
{
  "job_id": "abc123",
  "progress": 45,
  "status": "running",
  "current_frame": 450,
  "total_frames": 1000,
  "message": "Analyzing frame 450/1000"
}
```

#### `job_complete`
Job completed.

**Data:**
```json
{
  "job_id": "abc123",
  "status": "completed",
  "results_path": "jobs/abc123/results.json",
  "video_description": "This video shows...",
  "processing_time": 125.5
}
```

#### `job_error`
Job error.

**Data:**
```json
{
  "job_id": "abc123",
  "status": "failed",
  "error": "Error description",
  "traceback": "..."
}
```

#### `frame_analysis`
Frame analysis result.

**Data:**
```json
{
  "job_id": "abc123",
  "frame_num": 1,
  "timestamp": 0.0,
  "analysis": "A person is speaking...",
  "progress": 0.1
}
```

#### `videos_updated`
Video list updated.

**Data:**
```json
{
  "action": "upload",
  "filename": "video.mp4"
}
```

#### `system_monitor`
System monitoring data.

**Data:**
```json
{
  "timestamp": "2026-04-22T12:00:00Z",
  "gpu_usage": 33,
  "vram_used": 8192,
  "vram_total": 24576,
  "cpu_percent": 45,
  "memory_percent": 60,
  "ollama_instances": 2,
  "chat_queue_length": 1
}
```

#### `log_message`
Server log message.

**Data:**
```json
{
  "level": "INFO",
  "message": "Video uploaded: video.mp4",
  "timestamp": "2026-04-22T12:00:00Z"
}
```

## Rate Limits

- **Uploads**: 1GB max file size
- **Chat requests**: 3 concurrent jobs max
- **Job queue**: Priority-based scheduling
- **API requests**: No explicit rate limiting

## CORS

CORS is enabled for all origins:
```
Access-Control-Allow-Origin: *
```

## WebSocket

- **Path**: `/socket.io/`
- **Transports**: `websocket`, `polling`
- **Ping interval**: 25 seconds
- **Ping timeout**: 60 seconds
- **Max buffer size**: 100MB

## Examples

### Upload Video
```bash
curl -X POST http://localhost:10000/api/videos/upload \
  -F "file=@video.mp4" \
  -F "fps=1.0" \
  -F "whisper_model=base"
```

### Start Analysis
```bash
curl -X POST http://localhost:10000/api/llm/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is in this video?",
    "context": "job",
    "job_id": "abc123",
    "provider": "Ollama-Local",
    "model": "llama3.2:3b"
  }'
```

### Get Job Results
```bash
curl http://localhost:10000/api/jobs/abc123/results
```

### Monitor GPU
```bash
curl http://localhost:10000/api/vram
```