"""
Constant configuration values for Video Analyzer Web
"""

import os

# Application
APP_NAME = "Video Analyzer Web"
VERSION = "1.0.0"

# VRAM Manager
VRAM_BUFFER = 1.2  # 20% safety buffer
CHECK_INTERVAL = 5  # seconds between queue checks
MAX_JOBS_PER_GPU = 2  # Maximum concurrent jobs per GPU

# Chat Queue
MAX_CONCURRENT_JOBS = 5  # Maximum concurrent chat jobs
MAX_JOBS_PER_MINUTE = 30  # Rate limit
CHECK_INTERVAL_CHATS = 1  # seconds between queue checks

# LLM Configuration
LLM_TIMEOUT = 300  # seconds (5 minutes)
MIN_NUM_PREDICT = 2048
DEFAULT_TEMPERATURE = 0.2

# Video Processing
MAX_FRAMES_PER_JOB = 10000  # Maximum frames in frames.jsonl per job
DEFAULT_FRAMES_PER_MINUTE = 60
DEFAULT_FRAMERATE = None  # Detect original framerate by default
DEFAULT_SIMILARITY_THRESHOLD = 10

# Frame Extraction
FRAME_ANALYSIS_BATCH_SIZE = 10  # Batch size for frame analysis
FRAME_RETENTION_DAYS = 30  # Days to keep frame data

# Upload Limits
MAX_UPLOAD_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

# Transcoding
MAX_TRANSCODE_TIMEOUT = 3600  # 1 hour max for transcoding
DEFAULT_TRANSCODE_WIDTH = 1280  # 720p width
DEFAULT_TRANSCODE_HEIGHT = 720  # 720p height
DEFAULT_TRANSCODE_FPS = None  # Detect original framerate by default

# WebSocket Configuration
SOCKETIO_MAX_BUFFER_SIZE = 16 * 1024 * 1024  # 16MB per room
SOCKETIO_HEARTBEAT_TIMEOUT = 60
SOCKETIO_PING_INTERVAL = 5

# Job Limits
MAX_JOBS_PER_USER = 10
MAX_CONCURRENT_JOBS_PER_USER = 3

# API Rate Limiting
API_REQUEST_LIMIT = 100
API_REQUEST_WINDOW = 60  # seconds

# Parallel Deduplication
USE_PARALLEL_DEDUP = os.environ.get("USE_PARALLEL_DEDUP", "").lower() in ("1", "true", "yes")
MAX_DEDUP_WORKERS = int(os.environ.get("MAX_DEDUP_WORKERS", "30"))
DEDUP_CHUNK_SIZE = 100  # Frames per worker batch
DEDUP_MIN_FRAMES_FOR_PARALLEL = 50  # Minimum frames to use parallel
DEDUP_PARALLEL_FALLBACK = True  # Fallback to sequential if parallel fails
DEDUP_ERROR_RATE_THRESHOLD = 1.0  # Maximum 1% error rate

# Performance Monitoring
LOG_DEDUP_PERFORMANCE = True
MONITOR_DEDUP_RESOURCES = True

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
