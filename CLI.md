# Video Analyzer Web - CLI Documentation

The `va` CLI provides full access to all video-analyzer-web functionality from the terminal.

## Installation

```bash
# Option 1: Install as pip package (creates `va` entry point)
cd /path/to/video-analyzer-web
pip install -e .

# Option 2: Run without install
python -m src.cli.main --help
```

## Configuration

The CLI uses a persistent config file at `~/.video-analyzer-cli.json`:

```json
{
  "url": "http://127.0.0.1:10000",
  "openrouter_api_key": "sk-or-...",
  "openwebui_url": "http://192.168.1.237:8080",
  "openwebui_api_key": "sk-ow-..."
}
```

### Setting Values
```bash
va config set url http://127.0.0.1:10001
va config set openrouter_api_key sk-or-your-key-here
va config show
```

### Override Flags
Every command accepts `--url` to override the configured server URL for that invocation:
```bash
va --url http://192.168.1.237:10001 videos list
va videos --url http://local:10001 list   # or at group level
```

### Machine-Readable Output
Use `--json` at any group level for raw JSON output:
```bash
va --json videos list
va providers --json list
```

---

## Video Commands

### List Videos
```bash
va videos list
va videos list --json
```
Shows source and processed videos with thumbnails, sizes, and analysis status.

### Upload Video
```bash
va videos upload /path/to/video.mp4
va videos upload video.mp4 --whisper-model large --language en
```

### Delete Video
```bash
va videos delete video.mp4
```

### Video Info (Frame Metadata)
```bash
va videos info video.mp4
```

### View Transcript
```bash
va videos transcript video.mp4
```

### View Frame Index
```bash
va videos frames-index video.mp4
```

### Dedup (Single Threshold)
```bash
va videos dedup video.mp4 --threshold 10
```

### Dedup (Multi-Threshold Scan)
```bash
va videos dedup-multi video.mp4
va videos dedup-multi video.mp4 --thresholds 5,10,15,20,30
```

### Scene Detection
```bash
va videos scenes video.mp4
va videos scenes video.mp4 --detector-type content --threshold 30.0 --min-scene-len 15
```

### Scene-Aware Dedup
```bash
va videos scene-dedup video.mp4 --threshold 10 --scene-threshold 30.0
```

---

## Job Commands

### List Jobs
```bash
va jobs list
```

### Check Job Status
```bash
va jobs status <job_id>
```

### Cancel Job
```bash
va jobs cancel <job_id>
```

### Set Job Priority
```bash
va jobs priority <job_id> <priority>
```

### View Job Results
```bash
va results get <job_id>
va results list
```

### View Job Frame Analyses
```bash
va jobs frames <job_id> --limit 50
va jobs frames <job_id> --limit 10 --offset 0
```

### Start Analysis (SocketIO)
```bash
va jobs start video.mp4 --model qwen3-27b-q8 --provider-type litellm
va jobs start video.mp4 --model meta-llama/llama-3.2-11b-vision-instruct --provider-type openrouter
va jobs start video.mp4 --model qwen3-27b-q8 --provider-type litellm \
  --priority 5 \
  --whisper-model large --language en \
  --frames-per-minute 60 --similarity-threshold 10
```

The `start` command connects via SocketIO for real-time progress (frame-by-frame updates, transcript, final description). Press Ctrl+C to stop monitoring without canceling the job.

---

## Provider Commands

### List Providers
```bash
va providers list
```

### Configure LiteLLM Proxy
```bash
va config set litellm_api_base http://172.16.17.3:4000/v1
```

---

## Model Commands

### List LiteLLM Models
```bash
va models litellm
```

### List OpenRouter Models
```bash
va models openrouter
```

### Estimate Cost (OpenRouter)
```bash
va cost meta-llama/llama-3.2-11b 50
```

### Check Balance (OpenRouter)
```bash
va balance
```

---

## System Commands

### VRAM Status
```bash
va system vram
```

### GPU List
```bash
va system gpus
```

### Debug Mode
```bash
va system debug
va system debug --enable
va system debug --disable
```

---

## LLM Chat Commands

### Send Chat Message
```bash
va llm chat qwen3-27b-q8 "Summarize this video" --provider-type litellm
va llm chat qwen3-27b-q8 "What are the key points?" --provider-type litellm
```

The chat command submits to the rate-limited queue (30 req/min, 5 concurrent) and polls for completion.

### Check Chat Status
```bash
va llm status <chat_job_id>
```

### Cancel Chat
```bash
va llm cancel <chat_job_id>
```

### Queue Statistics
```bash
va llm queue-stats
```

---

## Knowledge Base Commands

### Check Status
```bash
va knowledge status
```

### Configure OpenWebUI KB
```bash
va knowledge config --enable --url http://237:8080 --api-key sk-ow-key --kb-name "Video Analyzer"
```

### Test Connection
```bash
va knowledge test --url http://237:8080 --api-key sk-ow-key
```

### Sync Single Job to KB
```bash
va knowledge sync <job_id>
```

### Sync All Jobs to KB
```bash
va knowledge sync-all
```

### List Knowledge Bases
```bash
va knowledge bases
```

### Send Job to Specific KB
```bash
va knowledge send <job_id> --kb-id <kb_id>
va knowledge send <job_id> --kb-name "Custom KB"
```

---

## Common Patterns

### Full Analysis Pipeline
```bash
# 1. Upload
va videos upload presentation.mp4

# 2. Optional: scene-detect then dedup
va videos scenes presentation.mp4
va videos scene-dedup presentation.mp4 --threshold 10

# 3. Start analysis
va jobs start presentation_dedup.mp4 --model qwen3-27b-q8 --provider-type litellm

# 4. View results
va results get <job_id>

# 5. Sync to KB
va knowledge sync <job_id>
```

### Batch from Cron
```bash
#!/bin/bash
for vid in /data/videos/*.mp4; do
  va videos upload "$vid" --whisper-model large
  # Wait a bit for processing
  sleep 30
  va jobs start "$(basename $vid)" --model qwen3-27b-q8 --provider-type litellm &
done
wait
echo "All jobs submitted"
```
