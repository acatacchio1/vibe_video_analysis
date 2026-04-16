# Video Analyzer Web - Complete Code Documentation

**Purpose**: This documentation provides a comprehensive reference for code review purposes, detailing all functions, requirements, and implementation details across the video-analyzer-web codebase.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Dependencies & Requirements](#dependencies--requirements)
4. [Core Python Modules](#core-python-modules)
5. [Provider Implementations](#provider-implementations)
6. [Frontend Implementation](#frontend-implementation)
7. [Configuration](#configuration)
8. [Deployment](#deployment)
9. [API Reference](#api-reference)
10. [Data Flow & Workflow](#data-flow--workflow)

---

## 1. Project Overview

**Video Analyzer Web** is a Flask-based web application that provides a GUI for analyzing videos using AI/LLM models. Key features include:

- Video upload with automatic transcoding to 720p@1fps
- Frame-by-frame video analysis using vision-capable LLMs
- Audio transcription using Whisper
- Multi-GPU VRAM management for local model inference
- Support for both local (Ollama) and cloud (OpenRouter) AI providers
- Real-time progress tracking via WebSockets
- Chat interface for post-analysis queries

**Technology Stack**:
- Backend: Python 3, Flask, Flask-SocketIO
- AI Providers: Ollama (local), OpenRouter (cloud)
- Video Processing: FFmpeg, video-analyzer library
- GPU Management: NVIDIA NVML (pynvml)
- Frontend: Vanilla JavaScript, Socket.IO client
- Deployment: Docker with Docker Compose

---

## 2. Architecture

### 2.1 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Browser)                      │
│  HTML/CSS + JavaScript (Socket.IO client for real-time)    │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/WebSocket
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                     Flask Application                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐    │
│  │   app.py    │ │  Routes     │ │   WebSocket Events  │    │
│  │  (Main App) │ │   Handlers  │ │   (SocketIO)        │    │
│  └──────┬──────┘ └──────┬──────┘ └──────────┬──────────┘    │
└─────────┼───────────────┼───────────────────┼────────────────┘
          │               │                   │
          ▼               ▼                   ▼
┌─────────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  vram_manager.py│ │  provider    │ │   Worker Process     │
│  (VRAM/Job Mgmt)│ │   modules    │ │   (Subprocess)       │
└────────┬────────┘ │  (Ollama,    │ └──────────┬───────────┘
         │          │    OpenRouter)│             │
         │          └──────────────┘             │
         │                                    ┌───┴───┐
         │                                    │video- │
         │                                    │analyzer│
         │                                    │library │
┌────────┴────────────┐                      └─────────┘
│  discovery.py       │
│  (Find Ollama svrs) │
└─────────────────────┘
```

### 2.2 File Structure

```
video-analyzer-web/
├── app.py                     # Main Flask application
├── worker.py                  # Worker subprocess for analysis
├── vram_manager.py            # GPU VRAM and job queue management
├── chat_queue.py              # LLM chat request queue manager
├── discovery.py               # Ollama instance discovery
├── gpu_transcode.py           # GPU transcoding utilities
├── monitor.py                 # System monitoring (nvidia-smi, ollama ps)
├── thumbnail.py               # Thumbnail extraction
├── providers/
│   ├── base.py                # Abstract provider base class
│   ├── ollama.py              # Ollama provider implementation
│   └── openrouter.py          # OpenRouter provider implementation
├── static/
│   ├── css/
│   │   ├── style.css          # Main styles
│   │   └── style-additions.css# Additional styles
│   └── js/
│       └── app.js             # Frontend application logic
├── templates/
│   └── index.html             # Main HTML template
├── config/
│   └── default_config.json    # Default analysis configuration
├── tests/                     # Test directory (if any)
├── uploads/                   # Uploaded video storage (Docker volume)
├── jobs/                      # Job data and results (Docker volume)
├── cache/                     # API response caching (Docker volume)
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker build configuration
└── docker-compose.yml         # Docker Compose orchestration
```

---

## 3. Dependencies & Requirements

### 3.1 Python Dependencies (requirements.txt)

| Package | Version | Purpose |
|---------|---------|---------|
| flask | 3.0.0 | Web framework |
| flask-socketio | 5.3.6 | WebSocket support |
| gunicorn | 21.2.0 | WSGI HTTP server |
| eventlet | 0.33.3 | Async framework for Socket.IO |
| requests | 2.31.0 | HTTP client for API calls |
| python-socketio | 5.9.0 | Socket.IO client/server library |
| psutil | 5.9.6 | System monitoring |
| ffmpeg-python | 0.2.0 | FFmpeg binding |
| pillow | 10.1.0 | Image processing |
| netifaces | 0.11.0 | Network interface detection |
| pynvml | 11.5.0 | NVIDIA Management Library |
| video-analyzer | latest | Core video analysis library |

### 3.2 System Requirements

- **OS**: Linux/Ubuntu 22.04
- **GPU**: NVIDIA GPU with CUDA capability (for local model inference)
- **Docker**: Version 20+ with NVIDIA Container Toolkit
- **FFmpeg**: Video processing and transcoding
- **Optional**: Ollama server for local LLM inference

### 3.3 Dockerfile Dependencies

- Base image: `nvidia/cuda:12.1.0-base-ubuntu22.04`
- Python: 3.11
- System packages: ffmpeg, libsndfile1, libgomp1, curl, net-tools

---

## 4. Core Python Modules

### 4.1 `app.py` - Main Flask Application

**Purpose**: Core web application handling all HTTP routes, WebSocket events, and orchestration.

#### 4.1.1 Route Handlers

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main page |
| `/api/videos` | GET | List uploaded videos |
| `/api/videos/upload` | POST | Upload video file |
| `/api/videos/<filename>` | DELETE | Delete video |
| `/api/thumbnail/<filename>` | GET | Get video thumbnail |
| `/api/providers` | GET | List configured providers |
| `/api/providers/discover` | GET | Trigger Ollama discovery |
| `/api/providers/ollama/models` | GET | List Ollama models |
| `/api/providers/openrouter/models` | GET | List OpenRouter models |
| `/api/providers/openrouter/cost` | GET | Estimate analysis cost |
| `/api/providers/openrouter/balance` | GET | Get API balance |
| `/api/jobs` | GET | List all jobs |
| `/api/jobs/running` | GET | List running jobs |
| `/api/jobs/queued` | GET | List queued jobs |
| `/api/jobs/<job_id>` | GET | Get job details |
| `/api/jobs/<job_id>/frames` | GET | Get frame analyses |
| `/api/jobs/<job_id>/results` | GET | Get final results |
| `/api/jobs/<job_id>` | DELETE | Cancel job |
| `/api/jobs/<job_id>/priority` | POST | Update job priority |
| `/api/vram` | GET | Get VRAM status |
| `/api/gpus` | GET | Get GPU list |
| `/api/videos/transcode` | POST | Manual transcode |
| `/api/llm/chat` | POST | Submit chat request |
| `/api/llm/chat/<job_id>` | GET | Get chat job status |
| `/api/llm/chat/<job_id>` | DELETE | Cancel chat job |
| `/api/llm/queue/stats` | GET | Get queue statistics |
| `/api/results` | GET | List stored results |

#### 4.1.2 Key Functions

```python
def index():
    """Main page template render"""
    return render_template("index.html")

def list_videos():
    """
    Lists all uploaded videos with metadata.
    
    Returns: JSON list of video objects containing:
        - name: filename
        - path: full path
        - size: file size in bytes
        - size_human: human-readable size
        - created: ISO timestamp
        - duration: duration in seconds
        - duration_formatted: human-readable duration
        - thumbnail: thumbnail path if exists
        - has_analysis: boolean if analysis exists
    """

def upload_video():
    """
    Handles video file upload.
    
    Processes:
    1. Validates file presence
    2. Sanitizes filename
    3. Handles duplicate naming
    4. Saves to uploads directory
    5. Triggers background transcoding
    
    Returns: {"success": True, "filename": str, "path": str}
    """

def delete_video(filename):
    """
    Deletes video and associated data.
    
    Removes:
    - Video file
    - Thumbnail
    - All job directories
    """

def list_providers():
    """Returns registered AI providers with status"""

def discover_ollama():
    """
    Triggers network discovery of Ollama instances.
    
    Uses discovery.scan() to find Ollama servers.
    Creates OllamaProvider instances for each found server.
    """

def get_ollama_models(server):
    """Fetches available models from specified Ollama server"""

def get_openrouter_models(api_key):
    """Fetches models from OpenRouter with pricing info"""

def estimate_openrouter_cost(model, frames, api_key):
    """
    Estimates analysis cost for OpenRouter.
    
    Calculates based on:
    - Per-frame token estimates (500-1500 prompt, 200-800 completion)
    - Image upload costs
    - Transcript processing
    - Video reconstruction
    
    Returns: {"min": float, "max": float, "avg": float, "currency": "USD"}
    """

def list_jobs():
    """Returns all jobs from VRAM manager"""

def get_job(job_id):
    """
    Gets detailed job information.
    
    Combines:
    - Job object from vram_manager
    - Status data from job/status.json
    """

def get_job_frames(job_id):
    """Reads and returns frame analyses from frames.jsonl"""

def get_job_results(job_id):
    """Returns final analysis results from results.json"""

def cancel_job(job_id):
    """
    Cancels job and terminates process tree.
    
    Process termination:
    1. Reads PGID from job directory
    2. Sends SIGTERM to entire process group
    3. Falls back to PID if PGID unavailable
    """

def update_priority(job_id, priority):
    """Updates job priority and re-sorts queue"""

def llm_chat():
    """
    Submits LLM chat request to chat queue.
    
    Accepts:
        - provider_type: "ollama" or "openrouter"
        - model: model identifier
        - prompt: user prompt
        - content: document/video content
        - api_key: API key for OpenRouter
        - ollama_url: URL for Ollama instance
    
    Returns: {"job_id": str, "message": str}
    """

# WebSocket Event Handlers

def handle_connect():
    """Client WebSocket connection"""

def handle_disconnect():
    """Client WebSocket disconnection"""

def handle_subscribe_job(data):
    """Subscribe client to job room for real-time updates"""

def handle_start_analysis(data):
    """
    Creates new analysis job and submits to VRAM manager.
    
    Parameters:
        - video_path: path to video file
        - provider_type, provider_name, model_id
        - priority, temperature, duration
        - max_frames, frames_per_minute
        - whisper_model, language, device
        - keep_frames, user_prompt
    
    Creates job directory, writes config, submits to queue.
    """

def spawn_worker(job_id, job_dir, gpu_assigned):
    """
    Spawns worker subprocess for analysis.
    
    Steps:
    1. Logs worker output to job/worker.log
    2. Saves GPU assignment to gpu_assigned.txt
    3. Sets CUDA_VISIBLE_DEVICES if GPU assigned
    4. Starts worker.py subprocess in new process group
    5. Saves PID and PGID to job directory
    6. Starts monitor_job background task
    """

def monitor_job(job_id, job_dir, proc):
    """
    Monitors worker subprocess and emits updates.
    
    Watches for:
    - status.json updates (progress, stage, frame count)
    - frames.jsonl new lines (frame analysis)
    - job completion or failure
    
    Emits WebSocket events:
        - job_status
        - job_transcript  
        - job_description
        - frame_analysis
        - job_complete
    """

def on_vram_event(event, job):
    """VRAM manager callback - spawns worker when job starts"""

def _transcode_and_delete(src_path):
    """
    Background task: transcode video to 720p@1fps.
    
    Steps:
    1. Probes video for duration
    2. Builds FFmpeg transcoding command
    3. Parses progress output
    4. Emits progress updates via WebSocket
    5. Generates thumbnail
    6. Deletes source file on success
    """

def secure_filename(filename):
    """Sanitizes filename by removing special characters"""

def format_bytes(size):
    """Converts bytes to human-readable format (B, KB, MB, GB, TB)"""

def format_duration(seconds):
    """Converts seconds to human-readable format (s, m, s, h, m)"""

def init_providers():
    """
    Initializes default providers on startup.
    
    Creates:
        - Ollama-Local pointing to host.docker.internal:11434
        - Discovered Ollama instances from discovery.scan()
    """
```

### 4.2 `worker.py` - Analysis Worker Process

**Purpose**: Subprocess that performs actual video analysis. Communicates via job directory files.

#### 4.2.1 Key Functions

```python
def update_status(job_dir, updates):
    """
    Writes status updates to job/status.json.
    
    Merges with existing status, adds timestamp.
    Handles JSON decode errors gracefully.
    """

def run_analysis(job_dir):
    """
    Main analysis pipeline.
    
    Pipeline stages:
    1. **Initializing** - Load config, create output directories
    2. **Extracting Audio** - Extract audio using Whisper processor
    3. **Transcribing** - Transcribe audio to text
    4. **Extracting Frames** - Extract keyframes at configured rate
    5. **Analyzing Frames** - Send each frame to LLM for analysis
    6. **Reconstructing** - Generate video description from analyses
    7. **Complete** - Save results, mark job complete
    
    Config loading:
        - Reads input.json for job parameters
        - Creates Config for video-analyzer library
        - Patches Ollama client for thinking model compatibility
    """

def run_analysis().detailed_steps:
    # Stage 1: Audio extraction
    update_status({"stage": "extracting_audio", "progress": 5})
    audio_processor = AudioProcessor(...)
    audio_path = audio_processor.extract_audio(...)
    transcript = audio_processor.transcribe(...)
    
    # Stage 2: Frame extraction
    update_status({"stage": "extracting_frames", "progress": 15})
    processor = VideoProcessor(...)
    frames = processor.extract_keyframes(...)
    total_frames = len(frames)
    
    # Stage 3: Frame analysis
    update_status({"stage": "analyzing_frames", "progress": 20})
    client = OllamaClient(...)  # or GenericOpenAIAPIClient
    prompt_loader = PromptLoader(...)
    analyzer = VideoAnalyzer(...)
    
    for i, frame in enumerate(frames):
        analysis = analyzer.analyze_frame(frame)
        # Write to frames.jsonl
        update_status({"progress": progress, "current_frame": i + 1})
    
    # Stage 4: Video reconstruction
    update_status({"stage": "reconstructing", "progress": 85})
    video_description = analyzer.reconstruct_video(...)
    
    # Save results
    results = {...}
    results_file.write_text(json.dumps(results))
    update_status({"stage": "complete", "progress": 100})
```

**Ollama Client Patching**:
```python
# Patches generate() to use /api/chat with think:false
# This prevents thinking models from consuming tokens on <think> blocks
@functools.wraps(client.generate)
def _patched_generate(...):
    msg = {"role": "user", "content": prompt}
    if image_path:
        msg["images"] = [self_inner.encode_image(image_path)]
    
    data = {
        "model": model,
        "messages": [msg],
        "stream": False,
        "think": False,  # Top-level: disables reasoning mode
        "options": {...}
    }
    resp = _req.post(_chat_url, json=data, timeout=300)
    return {"response": resp.json()["message"]["content"], ...}
```

### 4.3 `vram_manager.py` - GPU VRAM & Job Queue Manager

**Purpose**: Manages GPU VRAM allocation and implements priority-based job queueing across multiple GPUs.

#### 4.3.1 Data Structures

```python
class JobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class GPUInfo:
    index: int
    name: str
    total_vram: int  # bytes
    used_vram: int
    free_vram: int

@dataclass
class Job:
    job_id: str
    provider_type: str
    provider_name: str
    model_id: str
    vram_required: int  # 0 for cloud providers
    priority: int  # Higher = runs sooner
    status: JobStatus
    queue_position: int
    gpu_assigned: Optional[int]
    created_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    video_path: str
    params: Dict
```

#### 4.3.2 Class: VRAMManager

**Constants**:
- `VRAM_BUFFER = 1.2` - 20% safety buffer for VRAM allocation
- `CHECK_INTERVAL = 5` - seconds between queue checks
- `MAX_JOBS_PER_GPU = 2` - maximum concurrent jobs per GPU

**Key Methods**:

```python
def _init_nvml():
    """
    Initializes NVML and detects all GPUs.
    
    Populates self.gpus with GPUInfo for each detected GPU.
    Logs GPU names and VRAM capacity.
    Sets HAS_NVML = False if initialization fails.
    """

def _get_gpu_status():
    """
    Returns current VRAM usage for all GPUs.
    
    Calls pynvml for each GPU:
        - nvmlDeviceGetMemoryInfo(handle)
    Returns list of GPUInfo objects.
    """

def _find_best_gpu(vram_required, vram_allocated=None):
    """
    Finds GPU with most free VRAM that can fit the job.
    
    Algorithm:
    1. Calculate required VRAM with buffer (vram_required * 1.2)
    2. For each GPU:
        - Get actual free VRAM
        - Subtract VRAM used by running jobs
        - Subtract VRAM allocated to jobs in current batch
        - Skip if at MAX_JOBS_PER_GPU limit
    3. Return GPU with most free VRAM that fits requirement
    4. Return 0 for cloud providers (vram_required = 0)
    """

def _can_fit(vram_required):
    """Checks if job can fit on any GPU"""

def submit_job(job_id, provider_type, provider_name, model_id, 
               vram_required, video_path, params, priority=0):
    """
    Submits new job to queue or starts immediately.
    
    Steps:
    1. Create Job object
    2. If vram_required = 0 or job fits:
        - Assign GPU
        - Start job immediately
    3. Else:
        - Add to priority queue
    4. Notify callbacks
    """

def _add_to_queue(job):
    """
    Adds job to priority queue.
    
    Insertion order:
    1. Higher priority jobs first
    2. Among same priority: earlier creation time first
    
    Updates queue_position for all queued jobs.
    """

def _start_job(job, gpu_id=None):
    """
    Marks job as running and assigns GPU.
    
    Updates:
        - status = RUNNING
        - started_at = time.time()
        - gpu_assigned
        - Moves from queue to running dict
    """

def _process_queue():
    """
    Background worker that checks queue every 5 seconds.
    
    Algorithm:
    1. Get current GPU status
    2. Calculate VRAM allocated to running jobs per GPU
    3. For each queued job:
        - Find GPU with enough free VRAM
        - Track VRAM allocation for batch processing
        - Start job if GPU found
    4. Update queue with remaining jobs
    """

def complete_job(job_id, success=True):
    """
    Marks job as completed or failed.
    
    Actions:
    1. Update job status to COMPLETED or FAILED
    2. Set completed_at timestamp
    3. Remove from running dict and GPU tracking
    4. Notify callbacks
    5. Trigger queue processing for waiting jobs
    """

def cancel_job(job_id):
    """
    Cancels pending or queued job.
    
    Cannot cancel running/completed jobs.
    Removes from queue or running dict.
    Notifies callbacks.
    """

def update_priority(job_id, new_priority):
    """Updates priority and re-sorts job in queue"""

def get_job(job_id):
    """Returns Job object or None"""

def get_all_jobs():
    """Returns all Job objects"""

def get_running_jobs():
    """Returns currently running jobs"""

def get_queued_jobs():
    """Returns queued Job objects"""

def get_status():
    """
    Returns comprehensive VRAM status.
    
    Structure:
    {
        "gpus": [...],
        "total_vram": bytes,
        "available_vram": bytes,
        "used_vram": bytes,
        "total_gb": float,
        "available_gb": float,
        "used_gb": float,
        "running_count": int,
        "queued_count": int,
        "nvml_available": bool
    }
    """

def register_callback(callback):
    """Registers callback for job status events"""

def _notify_callbacks(event, job):
    """Notifies all registered callbacks with event type and job"""

def _start_monitor():
    """Starts background thread that calls _process_queue()"""
```

### 4.4 `chat_queue.py` - LLM Chat Queue Manager

**Purpose**: Manages LLM chat requests with rate limiting and concurrency control.

#### 4.4.1 Constants & Data Structures

```python
class ChatJobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class ChatJob:
    job_id: str
    provider_type: str
    model_id: str
    prompt: str
    content: str
    api_key: str
    ollama_url: str
    created_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    status: ChatJobStatus
    queue_position: int
    result: Optional[str]
    error: Optional[str]
    priority: int

# Class constants
MAX_CONCURRENT_JOBS = 5
MAX_JOBS_PER_MINUTE = 30
CHECK_INTERVAL = 1  # second
```

#### 4.4.2 Key Methods

```python
def _start_worker():
    """Starts background worker thread"""

def _worker_loop():
    """
    Main worker loop calling _process_queue() every second.
    """

def _clean_rate_limit_window():
    """Removes timestamps older than 1 minute"""

def _check_rate_limit():
    """Returns True if under 30 jobs per minute limit"""

def _process_queue():
    """
    Processes chat job queue.
    
    Steps:
    1. Check rate limit (30/min)
    2. Check concurrency limit (5 concurrent)
    3. Start next job in queue
    4. Spawn background thread to process job
    """

def _process_job(job):
    """
    Processes single chat job.
    
    For Ollama:
        POST /api/chat
        {model, messages, stream: false, think: false}
    
    For OpenRouter:
        POST /chat/completions
        Headers: Authorization: Bearer {api_key}, Content-Type: application/json
    
    Stores result or error in job object.
    """

def submit_job(provider_type, model_id, prompt, content, 
               api_key, ollama_url, priority=0):
    """
    Submits chat job and returns job_id.
    
    Generates job_id: f"chat_{uuid4().hex[:8]}"
    Inserts into queue by priority (higher first).
    """

def get_job_status(job_id):
    """Returns job dict or None"""

def cancel_job(job_id):
    """Cancels pending/queued job only"""

def get_queue_stats():
    """
    Returns statistics:
    {
        "total_jobs": int,
        "queued": int,
        "running": int,
        "recent_completed": int (last 5 min),
        "rate_limit_window": int,
        "max_concurrent": int,
        "max_per_minute": int
    }
    """
```

### 4.5 `discovery.py` - Ollama Instance Discovery

**Purpose**: Discovers Ollama servers on local network.

```python
class OllamaDiscovery:
    COMMON_HOSTS = ["localhost", "127.0.0.1", "ollama", "host.docker.internal"]
    PORT = 11434
    SCAN_TIMEOUT = 2  # seconds
    REFRESH_INTERVAL = 30  # seconds

    def scan(self):
        """
        Scans for Ollama instances.
        
        Steps:
        1. Check common hosts (localhost, etc.)
        2. Detect local subnet via netifaces
        3. Scan subnet 1-254 with 50 concurrent threads
        4. Verify each found instance via /api/tags
        5. Returns list of working URLs
        """

    def _check_server(url, timeout=3):
        """
        Quick health check via GET /api/tags.
        Returns True if HTTP 200.
        Updates internal status dict.
        """

    def _start_refresh_thread():
        """Background thread refreshes status every 30 seconds"""

    def get_servers():
        """Returns list of discovered servers with status"""

    def get_online_servers():
        """Returns only online server URLs"""
```

### 4.6 `gpu_transcode.py` - GPU Transcoding Utilities

**Purpose**: Provides FFmpeg command building with GPU encoder detection.

```python
def detect_gpu_encoders():
    """
    Detects available GPU encoders via ffmpeg -encoders.
    
    Returns dict:
    {
        "nvenc": bool,   # NVIDIA NVENC
        "qsv": bool,     # Intel Quick Sync
        "vaapi": bool,   # VAAPI (AMD/Intel)
        "cuda": bool     # CUDA acceleration
    }
    """

def get_gpu_vram_available(gpu_index=0):
    """
    Returns available VRAM in bytes via pynvml.
    Returns None if NVML unavailable.
    """

def check_gpu_vram_required(video_path, gpu_index=0):
    """
    Checks if enough VRAM available for transcoding.
    
    Estimates:
        VRAM = width * height * 1.5 bytes * 3 buffers * 1.1 (safety)
    """

def get_cpu_thread_count():
    """
    Returns optimal CPU thread count.
    Rules:
        - 30 threads if CPU count >= 40
        - 75% of CPU cores otherwise
        - Minimum 1 thread
    """

def get_best_encoder(video_path, gpu_index=0):
    """
    Returns (encoder_type, ffmpeg_args).
    
    NOTE: Currently forces CPU encoding (libx264) to avoid NVENC driver issues.
    """

def build_transcode_command(input_path, output_path, width=1280, height=720,
                           fps=1, gpu_index=0):
    """
    Builds FFmpeg command for 720p@1fps transcoding.
    
    Command structure:
    ffmpeg -y -i <input> \
           -vf "scale=1280:720,fps=1" \
           -c:v libx264 -preset fast -crf 23 \
           -threads <cpu_count> \
           -c:a aac -b:a 128k -ar 44100 \
           -progress pipe:1 -nostats \
           <output>
    """

def get_transcode_progress_parser(encoder_type):
    """
    Returns progress parsing function.
    Parses "out_time_ms=" lines to calculate percentage.
    """
```

### 4.7 `monitor.py` - System Monitor

**Purpose**: Monitors GPU and Ollama status via nvidia-smi and Ollama API.

```python
class SystemMonitor:
    nvidia_smi_interval = 10  # seconds
    ollama_ps_interval = 15  # seconds

    def _get_nvidia_stats():
        """
        Parses nvidia-smi output for:
        - GPU utilization %
        - VRAM used/total
        - Per-process memory usage
        - GPU UUIDs
        
        Returns (gpus_list, error).
        """

    def _format_nvidia(gpus):
        """
        Formats GPU stats as ASCII text:
        
        GPU 0: NVIDIA GeForce RTX 3080
          Util: [████████░░░░░░░░░░]  40%
          VRAM:  4096 / 10240 MiB  (40%)
          Processes:
            PID   12345    400 MiB  python3
        """

    def _nvidia_smi_loop():
        """Polls nvidia-smi every 10 seconds, notifies callbacks"""

    def _ollama_ps_loop():
        """
        Polls Ollama /api/ps endpoint every 15 seconds.
        Returns loaded models with size, VRAM, expiry.
        """

    def start():
        """Starts both monitor threads"""

    def get_latest():
        """Returns latest nvidia_smi and ollama_ps data"""
```

### 4.8 `thumbnail.py` - Thumbnail Extraction

**Purpose**: Extracts thumbnails from videos using FFmpeg.

```python
def extract_thumbnail(video_path, output_path, time_percent=0.1):
    """
    Extracts thumbnail at 10% of video duration.
    
    FFmpeg command:
    ffmpeg -y -ss <position>s -i <video> \
           -vframes 1 -q:v 2 \
           -vf "scale=320:-1" \
           <output>
    
    Returns True on success, False on failure.
    """

def get_thumbnail_path(video_path, thumbs_dir="uploads/thumbs"):
    """Returns expected thumbnail path"""

def ensure_thumbnail(video_path):
    """
    Ensures thumbnail exists, creates if not.
    
    Returns thumbnail path if exists/created, None otherwise.
    """
```

---

## 5. Provider Implementations

### 5.1 `providers/base.py` - Abstract Base Provider

```python
class BaseProvider(ABC):
    def __init__(self, name, provider_type):
        self.name = name
        self.provider_type = provider_type
        self.status = "unknown"
        self.last_error = None

    @abstractmethod
    def get_models() -> List[Dict]:
        """Returns list of available models with metadata"""

    @abstractmethod
    def test_connection() -> bool:
        """Tests provider connectivity"""

    @abstractmethod
    def get_model_info(model_id) -> Optional[Dict]:
        """Returns detailed info for specific model"""

    @abstractmethod
    def estimate_vram(model_id) -> Optional[int]:
        """Estimates VRAM required in bytes"""

    def to_dict() -> Dict:
        """Returns provider info dict"""
```

### 5.2 `providers/ollama.py` - Ollama Provider

```python
class OllamaProvider(BaseProvider):
    def __init__(self, name, base_url):
        super().__init__(name, "ollama")
        self.base_url = base_url.rstrip("/")
        self.models = []
        self._test_connection()

    def _test_connection():
        """
        GET <base_url>/api/tags
        On success:
            - status = "online"
            - Populates self.models
        On failure:
            - status = "offline" or "error"
            - Sets last_error
        """

    def get_models():
        """
        Returns enriched model list:
        {
            "id": model_name,
            "name": model_name,
            "size": bytes,
            "parameter_size": e.g., "7B",
            "quantization": e.g., "Q4_0",
            "vram_required": bytes (size + 2GB),
            "modified": timestamp
        }
        """

    def estimate_vram(model_id):
        """Returns model_size + 2GB overhead"""

    def get_running_models():
        """
        GET <base_url>/api/ps
        Returns currently loaded models with memory usage.
        """

    def to_dict():
        """Extends base with url and models_count"""
```

### 5.3 `providers/openrouter.py` - OpenRouter Provider

```python
class OpenRouterProvider(BaseProvider):
    API_URL = "https://openrouter.ai/api/v1"
    CACHE_FILE = Path("cache/openrouter_pricing.json")
    CACHE_TTL = 3600  # seconds

    def __init__(self, name, api_key):
        super().__init__(name, "openrouter")
        self.api_key = api_key
        self.pricing_cache = {}
        self._load_cached_pricing()
        self._test_connection()

    def _test_connection():
        """
        GET /models with Authorization header.
        On success:
            - status = "online"
            - Updates pricing cache
        On 401:
            - status = "error"
            - last_error = "Invalid API key"
        """

    def _load_cached_pricing():
        """Loads pricing from cache if within TTL"""

    def _update_pricing_cache(models_data):
        """
        Extracts pricing info:
        {
            model_id: {
                "name": str,
                "description": str,
                "context_length": int,
                "pricing": {
                    "prompt": float,
                    "completion": float,
                    "image": float
                }
            }
        }
        """

    def get_models():
        """
        Returns all models with pricing:
        {
            "id": model_id,
            "name": str,
            "description": str,
            "context_length": int,
            "pricing_prompt": $/M tokens,
            "pricing_completion": $/M tokens,
            "pricing_image": $/image,
            "vram_required": null (cloud)
        }
        Sorted by name.
        """

    def get_pricing(model_id):
        """Returns pricing dict for model"""

    def estimate_cost(model_id, frame_count, include_transcript=True):
        """
        Estimates analysis cost range.
        
        Assumptions:
        - Per frame: 500-1500 prompt tokens, 200-800 completion tokens
        - Image upload cost per frame
        - Transcript: 1000-3000 prompt, 500-1500 completion tokens
        - Reconstruction: 2000-5000 prompt, 500-2000 completion tokens
        
        Returns: {"min": float, "max": float, "avg": float, "currency": "USD"}
        """

    def calculate_cost(model_id, prompt_tokens, completion_tokens, image_count=0):
        """Calculates actual cost from token counts"""

    def estimate_vram(model_id):
        """Returns 0 (cloud provider, no local VRAM)"""

    def to_dict():
        """Extends base with pricing cache info"""
```

---

## 6. Frontend Implementation

### 6.1 `templates/index.html` - HTML Structure

**Main Sections**:
1. **Header** - App title, notifications button
2. **Sidebar** - Upload area, videos list, system status
3. **Main Content** - Two tabs:
   - **Analyze** - Job creation form, job list, live analysis
   - **Results** - Stored results browser

**Key Elements**:

```html
<!-- Upload Area -->
<div class="upload-area" id="upload-area">
    <input type="file" id="video-upload" accept="video/*" hidden>
    <div class="upload-prompt">Drag & drop or click to upload</div>
    <div class="upload-progress" hidden>
        <div class="progress-bar">
            <div class="progress-fill"></div>
        </div>
    </div>
</div>

<!-- Transcode Progress -->
<div id="transcode-status" class="transcode-status hidden">
    <div class="transcode-header">
        <span id="transcode-label">Transcoding...</span>
        <span id="transcode-pct">0%</span>
    </div>
    <div class="transcode-bar">
        <div id="transcode-fill"></div>
    </div>
</div>

<!-- Video List -->
<div id="videos-list" class="videos-list">
    <!-- Dynamically populated -->
</div>

<!-- Analysis Form -->
<form id="analysis-form" class="analysis-form">
    <select id="video-select" required>Select video...</select>
    <select id="provider-select" required>Select provider...</select>
    <button id="discover-btn">Discover</button>
    <select id="model-select" required disabled>Select model...</select>
    
    <div id="cost-estimate" class="hidden">
        <div>Estimated Cost: <span id="cost-value">$--.--</span></div>
        <div>VRAM Required: <span id="vram-required">-- GB</span></div>
    </div>
    
    <input type="number" id="priority-input" value="0">
    
    <button id="advanced-toggle-btn">Advanced Options ▼</button>
    <div id="advanced-options" class="hidden">
        <input id="duration-input" value="0">
        <input id="max-frames-input" value="50">
        <input id="fpm-input" value="60">
        <input id="temperature-input" value="0.0">
        <select id="whisper-select">tiny | base | small | medium | large</select>
        <select id="device-select">GPU | CPU</select>
        <input id="language-input" value="en">
        <textarea id="prompt-input"></textarea>
        <input type="checkbox" id="keep-frames-checkbox">
    </div>
    
    <button id="start-btn" disabled>Start Analysis</button>
</form>

<!-- Jobs List -->
<div id="jobs-list">
    <!-- Job cards with status, progress, actions -->
</div>

<!-- Live Analysis Panel -->
<div id="live-analysis" class="hidden">
    <div id="frames-log"></div>
    <div id="transcript-panel"></div>
    <div id="description-panel"></div>
    
    <!-- LLM Chat Interface -->
    <div id="live-llm-panel">
        <select id="chat-provider-select"></select>
        <select id="chat-model-select"></select>
        <select id="chat-content-select">
            <option value="transcript">Transcript</option>
            <option value="description">Video Description</option>
            <option value="both">Both</option>
            <option value="frames">Frames</option>
        </select>
        <textarea id="chat-prompt"></textarea>
        <button onclick="sendToLLM('live')">Send to LLM</button>
        <div id="live-llm-response" class="hidden"></div>
    </div>
</div>
```

### 6.2 `static/js/app.js` - Frontend Logic

#### 6.2.1 State Management

```javascript
const state = {
    socket: null,             // Socket.IO connection
    videos: [],               // Video list
    providers: {},            // Provider info
    jobs: [],                 // Job list
    storedResults: [],        // Stored analysis results
    currentJob: null,         // Currently active job ID
    systemStatus: {},         // Current system status
    selectedProvider: null,   // Selected provider name
    selectedModel: null,      // Selected model ID
    selectedResult: null,     // Selected result ID
    openRouterKey: string,    // API key from localStorage
    settings: {},             // User settings from localStorage
    expandedPanels: [],       // Expanded UI panels
    transcodeActive: false    // Transcode in progress
};
```

#### 6.2.2 Initialization

```javascript
document.addEventListener('DOMContentLoaded', () => {
    initSocket();          // Setup WebSocket
    initUI();              // Setup event listeners
    loadVideos();          // Fetch videos
    loadProviders();       // Fetch providers
    loadJobs();            // Fetch jobs
    loadStoredResults();   // Fetch results
    restoreSettings();     // Restore UI settings
    initChatProviderSelect();
    requestNotificationPermission();
});
```

#### 6.2.3 Socket.IO Setup

```javascript
function initSocket() {
    state.socket = io();
    
    // Connection events
    state.socket.on('connect', () => showToast('Connected'));
    state.socket.on('disconnect', () => showToast('Disconnected', 'warning'));
    
    // System status
    state.socket.on('system_status', handleSystemStatus);
    
    // Job events
    state.socket.on('job_created', handleJobCreated);
    state.socket.on('job_status', handleJobStatus);
    state.socket.on('job_complete', handleJobComplete);
    state.socket.on('job_transcript', handleJobTranscript);
    state.socket.on('job_description', handleJobDescription);
    state.socket.on('frame_analysis', handleFrameAnalysis);
    state.socket.on('vram_event', handleVRAMEvent);
    
    // Transcode events
    state.socket.on('transcode_progress', handleTranscodeProgress);
    state.socket.on('videos_updated', () => loadVideos());
}
```

#### 6.2.4 Key Functions

```javascript
// Upload & Transcode
function handleDragOver(e) { e.currentTarget.classList.add('dragover'); }
function handleDragLeave(e) { e.currentTarget.classList.remove('dragover'); }
function handleDrop(e) { uploadFile(e.dataTransfer.files[0]); }
function handleFileSelect(e) { uploadFile(e.target.files[0]); }

async function uploadFile(file) {
    // XMLHttpRequest for progress tracking
    xhr.upload.addEventListener('progress', (event) => {
        percent = (event.loaded / event.total) * 100;
        progressFill.style.width = `${percent}%`;
    });
    
    xhr.send(formData);
    // On success: auto-transcoding starts
}

function handleTranscodeProgress(data) {
    // Updates transcode progress UI
    // data: { source, output, stage, progress, error }
}

// Video Management
async function loadVideos() {
    response = await fetch('/api/videos');
    state.videos = await response.json();
    renderVideos();
}

function renderVideos() {
    // Renders video list and populates video-select dropdown
}

async function deleteVideo(filename) {
    await fetch(`/api/videos/${filename}`, { method: 'DELETE' });
    loadVideos();
}

// Provider & Model Management
async function loadProviders() {
    response = await fetch('/api/providers');
    state.providers = Object.fromEntries(response.map(p => [p.name, p]));
    renderProviderSelect();
}

function renderProviderSelect() {
    // Populates provider-select with Ollama providers
    // and OpenRouter option
}

async function discoverProviders() {
    await fetch('/api/providers/discover');
    loadProviders();
}

async function handleProviderChange(e) {
    // Loads models for selected provider
    if (provider_type === 'ollama') {
        response = await fetch(`/api/providers/ollama/models?server=${url}`);
    } else if (provider === 'openrouter') {
        promptForOpenRouterKey();
        loadOpenRouterModels();
    }
}

function promptForOpenRouterKey() {
    // Prompts for API key if not stored
    // Stores in localStorage
}

async function loadOpenRouterModels() {
    response = await fetch(`/api/providers/openrouter/models?api_key=${key}`);
    // Populate model-select
    loadOpenRouterBalance();
}

async function handleModelChange(e) {
    // Updates VRAM/cost display
    if (provider_type === 'ollama') {
        vram = e.target.dataset.vram;
        cost = 'Free (local)';
    } else if (provider === 'openrouter') {
        updateCostEstimate();
    }
}

async function updateCostEstimate() {
    // Calls /api/providers/openrouter/cost
    // Updates cost display
}

// Analysis Job Management
async function handleStartAnalysis(e) {
    e.preventDefault();
    
    // Validate OpenRouter balance for cloud provider
    if (provider === 'openrouter' && costEstimate) {
        response = await fetch(`/api/providers/openrouter/balance?api_key=${key}`);
        balance = response.balance;
        if (maxCost > balance) {
            affordableFrames = Math.floor(balance / costPerFrame);
            proceed = confirm(`Insufficient balance! afford ${affordableFrames} frames?`);
        }
    }
    
    // Send to WebSocket
    state.socket.emit('start_analysis', params);
    // Show live analysis panel
}

function handleJobCreated(data) {
    state.socket.emit('subscribe_job', { job_id: data.job_id });
    state.currentJob = data.job_id;
}

function handleJobStatus(data) {
    updateJobCard(data);
}

function handleJobComplete(data) {
    // Show notification
    // Fetch and display results
    state.currentJobResults = results;
    loadJobs();
    loadStoredResults();
}

function handleFrameAnalysis(data) {
    // Appends to frames-log
    // Keeps last 50 entries
}

async function loadJobs() {
    response = await fetch('/api/jobs');
    state.jobs = await response.json();
    renderJobs();
}

function renderJobs() {
    // Renders job cards with:
    // - Status badge (running/queued/completed/failed)
    // - Progress bar for running jobs
    // - Queue position for queued jobs
    // - Action buttons (cancel, view results, download)
}

function cancelJob(jobId) {
    await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
    loadJobs();
}

async function viewResults(jobId) {
    response = await fetch(`/api/jobs/${jobId}/results`);
    results = await response.json();
    
    // Populate modal with:
    // - Transcript
    // - Video description
    // - Frame analyses (truncated)
    // - LLM chat interface for results
}

// Stored Results Browser
async function loadStoredResults() {
    response = await fetch('/api/results');
    state.storedResults = await response.json();
    renderStoredResults();
}

function renderStoredResults() {
    // Renders result list with:
    // - Video name
    // - Provider info
    // - Creation date
    // - Description preview
}

async function selectStoredResult(jobId) {
    response = await fetch(`/api/jobs/${jobId}/results`);
    results = await response.json();
    
    // Display full results with LLM chat interface
}

// LLM Chat Functions
function initChatProviderSelect(context) {
    // Initializes provider select for specific context
    // (modal, results, live)
}

async function handleChatProviderChange(context) {
    // Loads models for selected chat provider
}

async function sendToLLM(context, jobId) {
    // Build request:
    // - Get selected content (transcript, description, frames)
    // - Format content
    // - POST /api/llm/chat
    // - Start polling for job status
    
    // For modal context:
    // - Add "Track Job" button
   
    response = await fetch('/api/llm/chat', {
        method: 'POST',
        body: JSON.stringify({
            provider_type, model, prompt, content,
            ...(provider_type === 'ollama') ? { ollama_url } : { api_key }
        })
    });
    
    result = await response.json();
    if (result.job_id) {
        pollChatJobStatus(result.job_id, responseText, responseDiv);
    }
}

async function pollChatJobStatus(jobId, responseText, responseDiv) {
    // Polls /api/llm/chat/<job_id> every second
    // Updates responseText with status or final result
}
```

#### 6.2.5 Utility Functions

```javascript
function showToast(message, type='info') {
    // Creates toast notification
    // Auto-removes after 3 seconds
}

function switchMainTab(tabName) {
    // Toggles main tab visibility
}

function formatBytes(size) {
    // Converts bytes to human-readable format
}

function formatDuration(seconds) {
    // Converts seconds to h:m:s or m:s
}

function formatFrameAnalysis(text, maxLength) {
    // Truncates analysis text for preview
}

function formatContentForLLM(results, contentType) {
    // Formats job results for LLM chat:
    // - transcript: transcripts.text
    // - description: video_description
    // - both: transcript + description
    // - frames: all frame analyses
}
```

---

## 7. Configuration

### 7.1 `config/default_config.json`

```json
{
  "clients": {
    "default": "ollama",           // Default provider type
    "temperature": 0.0,            // LLM temperature
    "ollama": {
      "url": "http://host.docker.internal:11434",
      "model": "gemma4-180k"
    },
    "openai_api": {
      "api_key": "",               // OpenRouter API key
      "model": "meta-llama/llama-3.2-11b-vision-instruct",
      "api_url": "https://openrouter.ai/api/v1"
    }
  },
  "prompt_dir": "prompts",        // Prompt templates directory
  "prompts": [
    {
      "name": "Frame Analysis",
      "path": "frame_analysis/frame_analysis.txt"
    },
    {
      "name": "Video Reconstruction",
      "path": "frame_analysis/describe.txt"
    }
  ],
  "output_dir": "output",         // Output directory
  "frames": {
    "per_minute": 60,            // Extraction rate
    "analysis_threshold": 10.0,  // Keyframe difference threshold
    "min_difference": 5.0,       // Minimum frame difference
    "max_count": 30,             // Maximum keyframes
    "start_stage": 1,            // Start stage for extraction
    "max_frames": 2147483647     // Maximum frames to process
  },
  "response_length": {
    "frame": 1500,               // Max tokens per frame analysis
    "reconstruction": 1500,      // Max tokens for video description
    "narrative": 1000            // Max tokens for narrative
  },
  "audio": {
    "whisper_model": "large",    // Whisper model size
    "sample_rate": 16000,        // Audio sample rate
    "channels": 1,               // Mono audio
    "quality_threshold": 0.2,    // Audio quality threshold
    "chunk_length": 30,          // Transcription chunk length (seconds)
    "language_confidence_threshold": 0.8,
    "language": "en",            // Default audio language
    "device": "gpu"              // Transcription device
  },
  "keep_frames": false,          // Keep extracted frames
  "prompt": ""                   // User custom prompt
}
```

### 7.2 User Settings (localStorage)

```javascript
// Saved in browser:
state.openRouterKey      // API key
state.settings           // User preferences
state.expandedPanels     // UI panel states
```

---

## 8. Deployment

### 8.1 Dockerfile

```dockerfile
FROM nvidia/cuda:12.1.0-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 python3-pip ffmpeg libsndfile1 libgomp1 curl \
    net-tools iputils-ping

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

# Create directories
RUN mkdir -p uploads thumbs jobs cache config output

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:10000/api/vram || exit 1

CMD ["python3", "-m", "gunicorn", "-k", "eventlet", "-w", "1", 
     "--bind", "0.0.0.0:10000", "--timeout", "300", "--keep-alive", "5", 
     "app:app"]
```

### 8.2 docker-compose.yml

```yaml
version: '3.8'

services:
  video-analyzer-web:
    build: .
    container_name: video-analyzer-web
    ports:
      - "0.0.0.0:10000:10000"
    volumes:
      - ./uploads:/app/uploads
      - ./jobs:/app/jobs
      - ./cache:/app/cache
      - ./config:/app/config
      - ./output:/app/output
    environment:
      - PYTHONUNBUFFERED=1
      - NVIDIA_VISIBLE_DEVICES=all
      - OLLAMA_HOST=http://host.docker.internal:11434
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - video-analyzer-net
    restart: unless-stopped
```

### 8.3 NVIDIA Container Toolkit Requirements

To enable GPU access:
1. Install NVIDIA Container Toolkit:
   ```bash
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
       sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```

---

## 9. API Reference

### 9.1 Video APIs

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/api/videos` | GET | - | `[{name, path, size, size_human, created, duration, duration_formatted, thumbnail, has_analysis}]` |
| `/api/videos/upload` | POST | `multipart/form-data` | `{"success": boolean, filename: string, path: string}` |
| `/api/videos/<filename>` | DELETE | - | `{"success": boolean}` |
| `/api/thumbnail/<filename>` | GET | - | `binary/jpeg` or `404` |
| `/api/videos/transcode` | POST | `{"video_path": string}` | `{"success": boolean, message: string}` |

### 9.2 Provider APIs

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/api/providers` | GET | - | `[{name, type, status, url, models_count}]` |
| `/api/providers/discover` | GET | - | `{"discovered": int, urls: [string]}` |
| `/api/providers/ollama/models?server=<url>` | GET | - | `{"server": string, models: [...], status: string}` |
| `/api/providers/openrouter/models?api_key=<key>` | GET | - | `{"models": [...], status: string}` |
| `/api/providers/openrouter/cost?api_key=<key>&model=<id>&frames=<n>` | GET | - | `{"min": float, "max": float, "avg": float, "currency": "USD"}` |
| `/api/providers/openrouter/balance?api_key=<key>` | GET | - | `{"balance": float, "usage": float, "limit": int|null}` |

### 9.3 Job APIs

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/api/jobs` | GET | - | `[{job_id, provider_type, provider_name, model_id, vram_required, status, ...}]` |
| `/api/jobs/running` | GET | - | `[{job_id, ...}]` (running jobs only) |
| `/api/jobs/queued` | GET | - | `[{job_id, ...}]` (queued jobs only) |
| `/api/jobs/<job_id>` | GET | - | `job details + status data` |
| `/api/jobs/<job_id>/frames` | GET | - | `[{frame_number, total_frames, timestamp, analysis, tokens}]` |
| `/api/jobs/<job_id>/results` | GET | - | `{"metadata": {...}, "transcript": {...}, "frame_analyses": [...], "video_description": {...}, "token_usage": {...}}` |
| `/api/jobs/<job_id>` | DELETE | - | `{"success": boolean}` |
| `/api/jobs/<job_id>/priority` | POST | `{"priority": int}` | `{"success": boolean}` |

### 9.4 System APIs

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/api/vram` | GET | - | `{"gpus": [...], "total_vram": int, "available_vram": int, "used_vram": int, ...}` |
| `/api/gpus` | GET | - | `[{index, name, total_gb, used_gb, free_gb}]` |
| `/api/results` | GET | - | `[{job_id, video_path, model, provider, created_at, mtime, has_transcript, frame_count, desc_preview}]` |

### 9.5 LLM Chat APIs

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/api/llm/chat` | POST | `{"provider_type, model, prompt, content, api_key, ollama_url}` | `{"job_id": string, "message": string}` |
| `/api/llm/chat/<job_id>` | GET | - | `{"job_id, provider_type, model_id, status, queue_position, ...}` |
| `/api/llm/chat/<job_id>` | DELETE | - | `{"success": boolean, "message": string}` |
| `/api/llm/queue/stats` | GET | - | `{"total_jobs": int, "queued": int, "running": int, ...}` |

### 9.6 WebSocket Events

**Client → Server**:
- `subscribe_job {job_id}` - Subscribe to job updates
- `unsubscribe_job {job_id}` - Unsubscribe from job updates
- `start_analysis {...}` - Create new analysis job

**Server → Client**:
- `connected {message}` - Client connected acknowledgment
- `job_created {job_id, status}` - New job created
- `job_status {job_id, ...}` - Job status update
- `job_complete {job_id, success, ...}` - Job completed
- `job_transcript {job_id, transcript}` - Transcript available
- `job_description {job_id, description}` - Description available
- `frame_analysis {job_id, frame_number, analysis, ...}` - New frame analysis
- `vram_event {event, job}` - VRAM manager event
- `system_status {type, data, timestamp}` - System monitor update
- `transcode_progress {source, output, stage, progress, error}` - Transcode update
- `videos_updated {}` - Videos refreshed

---

## 10. Data Flow & Workflow

### 10.1 Video Upload Flow

```
1. User uploads video via drag-and-drop or file picker
2. JavaScript: XMLHttpRequest with progress tracking
3. Server: /api/videos/upload receives file
4. Server: Saves file to uploads/ with unique name
5. Server: Starts background task _transcode_and_delete()
   a. Probes video for duration
   b. Builds FFmpeg command for 720p@1fps
   c. Runs transcode, parsing progress
   d. Emits progress updates via WebSocket
   e. Generates thumbnail
   f. Deletes source file
6. Server: Emits videos_updated event
7. JavaScript: Reloads video list
```

### 10.2 Analysis Job Creation Flow

```
1. User fills analysis form and clicks "Start Analysis"
2. JavaScript: Validates form, checks OpenRouter balance if applicable
3. JavaScript: state.socket.emit('start_analysis', params)
4. Server (app.py): handle_start_analysis()
   a. Creates job_id (UUID)
   b. Creates jobs/<job_id>/ directory
   c. Writes input.json with all parameters
   d. Calls vram_manager.submit_job()
   e. Emits job_created event
5. VRAM Manager:
   a. Checks if job fits on any GPU
   b. If yes: calls _start_job() with GPU assignment
   c. If no: adds to priority queue
   d. on_vram_event("started", job) callback fires
6. Server: spawn_worker()
   a. Creates jobs/<job_id>/worker.log
   b. Writes gpu_assigned.txt
   c. Sets CUDA_VISIBLE_DEVICES env var
   d. Starts worker.py subprocess
   e. Saves PID and PGID
   f. Starts monitor_job() background task
7. Worker process:
   a. Loads input.json config
   b. Stage 1: Extract audio (Whisper)
   c. Stage 2: Extract keyframes
   d. Stage 3: Analyze each frame via LLM
      - Writes to frames.jsonl
      - Updates status.json
   e. Stage 4: Reconstruct video description
   f. Saves results.json
   g. Exits with code 0 or 1
8. monitor_job() detects completion
   a. Verifies job not already finalized
   b. Calls vram_manager.complete_job()
   c. Emits job_complete, job_transcript, job_description
9. Server: loadJobs() and loadStoredResults() called by client
```

### 10.3 LLM Chat Flow

```
1. User selects results, chooses LLM provider and model
2. User enters prompt, clicks "Send to LLM"
3. JavaScript: Formats content (transcript/description/frames)
4. JavaScript: POST /api/llm/chat
5. Server: llm_chat() submits to chat_queue_manager
6. Chat Queue Manager:
   a. Creates job_id: "chat_<uuid>"
   b. Inserts into priority queue
   c. _process_queue() starts job if under rate/concurrency limits
   d. Spawns background thread
7. Worker thread:
   a. POST to Ollama /api/chat or OpenRouter /chat/completions
   b. Stores result or error in job
   c. Marks job complete
   d. Notifies callbacks (if any)
8. Client: pollChatJobStatus() polls /api/llm/chat/<job_id>
9. When complete, displays result
```

### 10.4 Job Status State Machine

```
PENDING → (fits on GPU) → RUNNING
         → (no GPU available) → QUEUED → (GPU available) → RUNNING

RUNNING → (worker exits 0) → COMPLETED
        → (worker exits 1) → FAILED

QUEUED → (cancel) → CANCELLED

Running → (cancel) → CANCELLED
```

### 10.5 File Format Specifications

**jobs/<job_id>/input.json**:
```json
{
    "job_id": "abc12345",
    "video_path": "/app/uploads/video.mp4",
    "provider_type": "ollama",
    "provider_name": "Ollama-Local",
    "provider_config": {"url": "http://host.docker.internal:11434"},
    "model": "llava-ngl3",
    "params": {
        "temperature": 0.0,
        "duration": 0,
        "max_frames": 50,
        "frames_per_minute": 60,
        "whisper_model": "large",
        "language": "en",
        "device": "gpu",
        "keep_frames": false,
        "user_prompt": ""
    }
}
```

**jobs/<job_id>/status.json** (incrementally updated):
```json
{
    "status": "running",
    "stage": "analyzing_frames",
    "progress": 45,
    "current_frame": 23,
    "total_frames": 75,
    "last_update": 1234567890.0,
    "last_frame_analysis": "..."
}
```

**jobs/<job_id>/frames.jsonl** (newline-delimited JSON):
```json
{"frame_number": 1, "total_frames": 75, "timestamp": 2.5, "analysis": "A dog running in a park...", "tokens": {"prompt_tokens": 500, "completion_tokens": 250}}
{"frame_number": 2, ...}
```

**jobs/<job_id>/output/results.json**:
```json
{
    "metadata": {
        "job_id": "abc12345",
        "provider": "ollama",
        "model": "llava-ngl3",
        "frames_processed": 75,
        "transcription_successful": true
    },
    "transcript": {
        "text": "Full transcript text...",
        "segments": [{"start": 0.5, "end": 3.2, "text": "..."}]
    },
    "frame_analyses": [...],
    "video_description": {
        "response": "Full video description..."
    },
    "token_usage": {
        "prompt_tokens": 125000,
        "completion_tokens": 45000,
        "total_tokens": 170000
    }
}
```

**jobs/<job_id>/pid** and **jobs/<job_id>/pgid**:
- Text files containing process ID and process group ID for termination

---

## 11. Implementation Notes & Known Issues

### 11.1 Thoughtful Implementation Workaround

In `worker.py:177-217`, there's a patch for Ollama's `/api/chat` endpoint:

```python
# Patches generate() to use /api/chat with think:false at top level
# This prevents thinking models (qwen3, deepseek-r1) from consuming
# all tokens on <think> blocks and returning empty "response"
```

This is a workaround for Ollama 0.20.x behavior where `think:false` in the "options" object was ignored, but works as a top-level field on `/api/chat`.

### 11.2 GPU Transcoding Currently Disabled

In `gpu_transcode.py:150-173`, GPU encoding is deliberately disabled:

```python
# Force CPU encoding for now to avoid NVENC driver issues
# TODO: Restore GPU encoding when driver compatibility is fixed
```

The code builds FFmpeg commands with `libx264` on CPU regardless of GPU availability.

### 11.3 Worker Process Isolation

Worker processes run in new process groups (`start_new_session=True`) to enable cleanup of all child processes (ffmpeg, whisper) via `os.killpg(pgid, signal.SIGTERM)`.

### 11.4 VRAM Allocation Safety

VRAM manager uses `VRAM_BUFFER = 1.2` (20% buffer) to prevent OOM errors. Jobs are only started if:

```python
actual_free >= vram_required * VRAM_BUFFER
```

### 11.5 Rate Limiting

Chat queue enforces:
- Maximum 5 concurrent jobs
- Maximum 30 jobs per minute
- Timestamps cleaned from window every check

---

## 12. Code Review Considerations

### Security

1. **Filename sanitization**: `secure_filename()` uses basic regex - consider `werkzeug.security.secure_filename()`
2. **API key storage**: OpenRouter key in `localStorage` - consider encrypted storage
3. **File path validation**: Ensure uploaded files don't escape intended directories
4. **Process injection**: Worker subprocess uses path from config - validate paths

### Performance

1. **Frame handling**: Frames.jsonl grows unbounded - consider rotation or cleanup
2. **WebSocket memory**: Frame analysis events accumulate - throttle if needed
3. **GPU discovery**: Network scan uses 50 concurrent threads - consider limiting
4. **Caching**: OpenRouter pricing cached for 1 hour - could extend

### Reliability

1. **Error handling**: Worker `try/except` saves error to status.json but doesn't clean up
2. **Double-spawn guard**: `_spawned_jobs` set prevents duplicate spawn - good
3. **Monitor race condition**: `monitor_job` checks if job already finalized
4. **Queue consistency**: `_process_queue` uses locks but some race conditions possible

### Maintainability

1. **Code organization**: Some code moved to `providers/` but `video-analyzer` library dependencies unclear
2. **Configuration**: Settings spread across JSON, localStorage, code constants
3. **Testing**: No visible test files - test coverage unknown
4. **Logging**: Consistent logging but no log rotation configured

### Architecture

1. **Separation of concerns**: Good separation between app.py, worker.py, managers
2. **Extensibility**: Provider interface well-designed with base class
3. **Real-time**: WebSocket approach efficient for push notifications
4. **State management**: Client state object is monolithic - consider structured approach

---

*End of Documentation*
