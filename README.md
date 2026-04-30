# Video Analyzer Web

> **Version 0.6.0**

A web-based video analysis platform with multi-provider AI support (LiteLLM + OpenRouter), multi-GPU VRAM-aware job scheduling, real-time frame-by-frame analysis, and a comprehensive CLI for headless operation.

---

## Features

- **Multi-Provider AI**: LiteLLM proxy and OpenRouter (cloud) with dynamic model discovery
- **Two-Step Video Analysis**: Phase 1 (frame vision) + Phase 2 (vision + transcript synthesis via secondary LLM)
- **Multi-GPU VRAM-Aware Queueing**: Jobs distributed across GPUs based on available memory
- **Parallel Upload Processing**: Frame extraction and audio transcription run concurrently
- **Parallel Deduplication**: GPU-accelerated frame dedup with multiple sensitivity thresholds
- **Scene Detection**: PySceneDetect integration for content-aware frame selection
- **LLM Chat Queue**: Rate-limited queue for standalone LLM queries against analysis results
- **Real-Time Updates**: WebSocket-powered live frame analysis with auto-reconnect
- **OpenWebUI Knowledge Base**: Auto-sync analysis results to OpenWebUI KB after completion
- **CLI Interface**: Full-featured `va` command-line tool for headless automation
- **Source Video Preservation**: Original uploads preserved alongside processed versions
- **Cost Estimation**: Pre-flight cost estimates for OpenRouter with budget validation

## Quick Start

### Prerequisites

- Docker with Docker Compose plugin
- NVIDIA Docker runtime (for GPU support)
- LiteLLM proxy at `http://172.16.17.3:4000/v1` or OpenRouter API key

### Docker Installation

```bash
# Clone the repository
git clone https://github.com/acatacchio1/vibe_video_analysis.git
cd vibe_video_analysis

# Start the service
./start.sh
# Or manually:
docker compose up --build -d
```

### Direct Installation (No Docker)

```bash
pip install -r requirements.txt
./run.sh
```

This runs the app directly on port 10000.

### CLI Installation

```bash
pip install -e .
va --help
```

### Access

- Web UI: http://localhost:10000
- API: http://localhost:10000/api/
- CLI: `va videos list`

## Documentation

| Document | Description |
|----------|-------------|
| [CLI.md](CLI.md) | Command-line interface reference |
| [GUI.md](GUI.md) | Web interface functionality guide |
| [API.md](API.md) | REST API + SocketIO endpoint reference |
| [TEST_AUTOMATION.md](TEST_AUTOMATION.md) | Test suite structure and execution |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Architecture guide for contributors |
| [CHANGELOG.md](CHANGELOG.md) | Version history and upgrade notes |
| [SECURITY.md](SECURITY.md) | Security considerations and best practices |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues and solutions |

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│   Web Browser (GUI) │◄────│   Flask + SocketIO  │
│                     │────►│   (app.py)          │
└─────────────────────┘     └────────┬────────────┘
                                      │
                    ┌─────────────────┼───────────────┐
                    │                 │               │
              ┌─────▼─────┐   ┌──────▼──────┐   ┌────▼────┐
              │ VRAM      │   │  Worker     │   │  Chat   │
              │ Manager   │   │  (worker.py)│   │  Queue  │
              │ (multi-   │   │  → pipelines│   │ (rate-  │
              │  GPU)     │   └──────┬──────┘   │  limit) │
              └───────────┘          │          └─────────┘
                                     │
                           ┌─────────▼─────────┐
                           │  LiteLLM /        │
                           │  OpenRouter       │
                           │  LLM Providers    │
                           └───────────────────┘
```

**Tech Stack**: Flask + Gunicorn (eventlet) | Vanilla JS + CSS custom properties | NVIDIA CUDA + pynvml | FFmpeg + faster-whisper

## Configuration

### LiteLLM Proxy Setup

The app uses a LiteLLM proxy to route LLM requests to backend GPU instances. The proxy runs at `http://172.16.17.3:4000/v1` and handles load balancing, rate limiting, and context management across deployed models.

**Available Models:**
- `qwen3-27b-q8` — standard vision + text analysis
- `qwen3-27b-best` — higher quality analysis (load balanced)
- `vision-best` — optimized for frame analysis

The app authenticates to the LiteLLM proxy without an API key (network-trusted deployment). To configure a custom proxy URL:

```bash
va config set litellm_api_base http://your-litellm:4000/v1
```

VRAM estimation uses model size + 2GB overhead for the KV cache.

### OpenRouter Setup

1. Get an API key from [openrouter.ai](https://openrouter.ai)
2. Configure: `va config set openrouter_api_key sk-or-...`
3. Balance and pricing are checked before each analysis job

### Default Configuration

See `config/default_config.json` for all defaults. Key settings:
- Default LiteLLM model: `qwen3-27b-q8`
- Default OpenRouter model: `meta-llama/llama-3.2-11b-vision-instruct`
- Default Whisper model: `large`
- Default frames per minute: 60
- Default temperature: 0.0

### GPU & Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `LITELLM_API_BASE` | `http://172.16.17.3:4000/v1` | LiteLLM proxy endpoint |
| `NVIDIA_VISIBLE_DEVICES` | `all` | GPU visibility |
| `APP_URL` | `http://localhost:10000` | Internal API URL (for auto-LLM) |

The app supports **multiple GPUs** and assigns jobs to the GPU with the most available VRAM. Up to 2 concurrent jobs per GPU.

## License

MIT License
