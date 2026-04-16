# 🎬 Video Analyzer Web

A web-based GUI for video-analyzer with support for multiple AI providers (Ollama and OpenRouter), real-time monitoring, VRAM-aware job queueing, and cost estimation.

## Features

- **Multi-Provider Support**: Ollama (local) and OpenRouter (cloud) providers
- **Automatic Discovery**: Auto-discovers Ollama instances on local network
- **VRAM-Aware Queueing**: Intelligently queues jobs based on GPU memory availability
- **Cost Estimation**: Real-time cost estimates for OpenRouter with budget validation
- **System Monitoring**: Live nvidia-smi and ollama ps updates
- **Video Transcoding**: One-click transcoding to 720p/10fps for faster processing
- **Real-time Updates**: WebSocket-powered live frame analysis display
- **Job Management**: Priority-based queueing, concurrent job support

## Quick Start

### Prerequisites

- Docker with Docker Compose plugin
- NVIDIA Docker runtime (for GPU support)
- At least one Ollama instance or OpenRouter API key

### Installation

```bash
# Clone or create the directory
mkdir -p ~/video-analyzer-web
cd ~/video-analyzer-web

# Start the service
./start.sh
```

Or manually:

```bash
docker compose up --build -d
```

### Access

- Web Interface: http://localhost:10000
- Accessible from local network at http://your-ip:10000

## Configuration

### Ollama Setup

1. Ensure Ollama is running on your machine or network
2. The app will auto-discover Ollama instances, or you can add manually

### OpenRouter Setup

1. Get an API key from [openrouter.ai](https://openrouter.ai)
2. Enter the API key in the web interface when selecting OpenRouter
3. Your balance will be displayed and validated before starting analysis

### GPU Support

The Docker container includes NVIDIA runtime support. Ensure you have:

```bash
# Install nvidia-docker2
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

## Usage

1. **Upload Video**: Drag & drop or click to upload a video file
2. **Select Provider**: Choose an Ollama instance or OpenRouter
3. **Select Model**: Models are dynamically loaded from the provider
4. **Configure**: Set max frames, duration, whisper model, etc.
5. **Start Analysis**: Click "Start Analysis" to begin

### VRAM Queueing

- Jobs requiring more VRAM than available are queued
- Queue is processed automatically when VRAM becomes available
- Smaller VRAM jobs can run concurrently if they fit
- Manually set job priority to control queue order

### Cost Estimation (OpenRouter)

- Cost is estimated based on frame count before starting
- System checks your API balance against estimated cost
- If insufficient funds, suggests max affordable frames
- Cost updates every 10 frames during analysis

### Video Transcoding

Click the 🎞️ button next to any video to transcode to:
- Resolution: 720p (scaled proportionally)
- Frame rate: 10 fps
- Codec: H.264 (fast preset)
- Audio: AAC 128kbps

This reduces processing time and VRAM usage.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/videos` | GET | List uploaded videos |
| `/api/videos/upload` | POST | Upload video file |
| `/api/videos/transcode` | POST | Transcode video |
| `/api/providers` | GET | List providers |
| `/api/providers/discover` | GET | Discover Ollama instances |
| `/api/providers/openrouter/balance` | GET | Get OpenRouter balance |
| `/api/jobs` | GET | List all jobs |
| `/api/jobs/<id>` | GET | Get job details |
| `/api/vram` | GET | Current VRAM status |

## Directory Structure

```
~/video-analyzer-web/
├── uploads/          # Uploaded videos
├── jobs/             # Job working directories
├── cache/            # Cached data (OpenRouter pricing)
├── config/           # Configuration files
└── output/           # Analysis results
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Default Ollama host |
| `NVIDIA_VISIBLE_DEVICES` | `all` | GPU visibility |

## Troubleshooting

### No GPU detected

Ensure nvidia-docker2 is installed and Docker daemon is restarted.

### Ollama not discovered

- Check Ollama is running: `ollama serve`
- Try accessing directly: `curl http://localhost:11434/api/tags`
- Add manually via "Custom..." option

### OpenRouter balance shows 0

- Verify API key is correct
- Check key has credit at openrouter.ai

### Jobs stuck in queue

- Check VRAM usage in System Status panel
- Ensure no zombie processes are holding GPU memory
- Check logs: `docker compose logs -f`

## License

MIT License - See original video-analyzer project for details.
