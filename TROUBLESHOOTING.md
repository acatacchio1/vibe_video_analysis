# Troubleshooting Guide

This document provides solutions to common issues encountered when using Video Analyzer Web.

## Quick Start Issues

### Application Won't Start

**Symptoms:**
- `python3 app.py` fails with import errors
- Docker container fails to start
- Port 10000 already in use

**Solutions:**

1. **Import Errors**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Check Python version (requires 3.8+)
   python3 --version
   ```

2. **Port Already in Use**
   ```bash
   # Check what's using port 10000
   sudo lsof -i :10000
   
   # Kill the process
   sudo kill -9 <PID>
   
   # Or use different port by modifying app.py:
   # socketio.run(app, host='0.0.0.0', port=10001, debug=True)
   ```

3. **Docker Issues**
   ```bash
   # Check Docker service
   sudo systemctl status docker
   
   # Rebuild container
   docker compose down
   docker compose up --build
   ```

### UI Not Loading

**Symptoms:**
- Blank page in browser
- JavaScript errors in console
- CSS not loading

**Solutions:**

1. **Check Browser Console**
   - Open Developer Tools (F12)
   - Check Console tab for errors
   - Check Network tab for failed requests

2. **Clear Browser Cache**
   ```
   Ctrl+Shift+Delete (Windows/Linux)
   Cmd+Shift+Delete (Mac)
   ```

3. **Check Static Files**
   ```bash
   # Verify static files exist
   ls -la static/css/style.css
   ls -la static/js/app.js
   
   # Check file permissions
   chmod -R 755 static/
   ```

## Video Upload Issues

### Upload Fails

**Symptoms:**
- "Upload failed" message
- File size error
- Invalid file type error

**Solutions:**

1. **File Size Limit**
   - Maximum file size: 1GB
   - Check file size: `ls -lh video.mp4`
   - Compress video if too large

2. **Invalid File Type**
   - Supported formats: MP4, AVI, MOV, MKV, WebM
   - Check file extension
   - Convert unsupported formats:
     ```bash
     ffmpeg -i input.mov -c:v libx264 -c:a aac output.mp4
     ```

3. **Permission Issues**
   ```bash
   # Check upload directory permissions
   ls -la uploads/
   
   # Fix permissions
   chmod 755 uploads/
   chown -R $USER:$USER uploads/
   ```

### Upload Stuck at 0%

**Symptoms:**
- Progress bar doesn't move
- No error messages
- Network timeout

**Solutions:**

1. **Network Issues**
   - Check internet connection
   - Try smaller file first
   - Check browser network throttling

2. **Server Configuration**
   ```bash
   # Check Flask debug mode
   # In app.py, ensure debug=True for development
   
   # Check upload timeout
   # Default is 10 minutes for large files
   ```

3. **Client-Side Issues**
   - Try different browser
   - Disable browser extensions
   - Clear browser cache

## Transcription Issues

### No Transcript Generated

**Symptoms:**
- `transcript.json` file missing
- Empty transcript
- Transcription errors in logs

**Solutions:**

1. **Check Whisper Model**
   ```bash
   # Verify model files exist
   ls -la ~/.cache/huggingface/hub/
   
   # Check Docker volume mounts
   # Models should be in /root/.cache/huggingface
   ```

2. **Audio Extraction Issues**
   ```bash
   # Check if audio.wav is created
   ls -la uploads/<video>/
   
   # Verify ffmpeg can extract audio
   ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav
   ```

3. **Memory Issues**
   - "large" model requires ~10GB VRAM
   - Use "base" model for lower memory
   - Check available VRAM: `/api/vram`

### Transcript Out of Sync

**Symptoms:**
- Transcript timestamps don't match video
- `frames_index.json` missing or incorrect
- Frame browser shows wrong transcript

**Solutions:**

1. **Regenerate Transcript**
   ```bash
   # Reprocess video with correct FPS
   curl -X POST http://localhost:10000/api/videos/reprocess \
     -H "Content-Type: application/json" \
     -d '{"filename": "video.mp4", "fps": 1.0}'
   ```

2. **Check Frames Index**
   ```bash
   # Verify frames_index.json exists
   ls -la uploads/<video>/frames_index.json
   
   # Check content
   cat uploads/<video>/frames_index.json | head -5
   ```

3. **Frame Rate Mismatch**
   - Use correct FPS during upload
   - Check video FPS: `ffprobe -v error -select_streams v -of default=noprint_wrappers=1:nokey=1 -show_entries stream=r_frame_rate video.mp4`

## GPU/VRAM Issues

### GPU Not Detected

**Symptoms:**
- "No GPU available" message
- Slow CPU-only processing
- `nvidia-smi` not working in Docker

**Solutions:**

1. **Docker GPU Access**
   ```bash
   # Check NVIDIA Container Toolkit
   docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   
   # Install NVIDIA Container Toolkit
   # Follow instructions: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
   ```

2. **Docker Compose Configuration**
   ```yaml
   # Verify docker-compose.yml has:
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: all
             capabilities: [gpu]
   ```

3. **Permission Issues**
   ```bash
   # Add user to docker group
   sudo usermod -aG docker $USER
   
   # Reboot or log out/in
   ```

### VRAM Exhausted

**Symptoms:**
- Jobs fail with CUDA out of memory
- Multiple jobs can't run concurrently
- System becomes unresponsive

**Solutions:**

1. **Monitor VRAM Usage**
   ```bash
   # Check current VRAM
   curl http://localhost:10000/api/vram
   
   # Monitor with nvidia-smi
   watch -n 1 nvidia-smi
   ```

2. **Adjust VRAM Buffer**
   ```python
   # In config/constants.py
   VRAM_BUFFER = 1024 * 1024 * 1024  # 1GB buffer
   # Reduce if needed
   VRAM_BUFFER = 512 * 1024 * 1024   # 512MB buffer
   ```

3. **Limit Concurrent Jobs**
   ```python
   # In config/constants.py
   MAX_CONCURRENT_JOBS = 3
   # Reduce if needed
   MAX_CONCURRENT_JOBS = 1
   ```

4. **Use Smaller Models**
   - Use "base" Whisper model instead of "large"
   - Use smaller LLM models (3B instead of 7B+)
   - Process fewer frames per job

## Ollama Issues

### Ollama Not Connecting

**Symptoms:**
- "Ollama provider offline" message
- Models not loading
- Connection timeout errors

**Solutions:**

1. **Verify Ollama Running**
   ```bash
   # Check Ollama service
   systemctl status ollama
   
   # Start Ollama
   systemctl start ollama
   
   # Check Ollama API
   curl http://localhost:11434/api/tags
   ```

2. **Docker Network Configuration**
   ```bash
   # For Docker, use host.docker.internal
   # Check app.py OllamaProvider initialization
   
   # Test connection from Docker
   docker exec -it video-analyzer-web curl http://host.docker.internal:11434/api/tags
   ```

3. **Firewall Issues**
   ```bash
   # Check firewall
   sudo ufw status
   
   # Allow port 11434
   sudo ufw allow 11434
   ```

### Models Not Loading

**Symptoms:**
- "Model not found" errors
- Models not appearing in UI
- VRAM insufficient for model

**Solutions:**

1. **Pull Model**
   ```bash
   # Pull model via Ollama CLI
   ollama pull llama3.2:3b
   
   # List available models
   ollama list
   ```

2. **Check Model Compatibility**
   - Verify model fits in available VRAM
   - 3B models need ~4GB VRAM
   - 7B models need ~8GB VRAM
   - 13B+ models need 16GB+ VRAM

3. **Model Cache**
   ```bash
   # Clear Ollama cache
   ollama rm $(ollama list | awk 'NR>1 {print $1}')
   
   # Restart Ollama
   systemctl restart ollama
   ```

## Job Processing Issues

### Job Stuck or Hung

**Symptoms:**
- Job progress stops
- No updates for long time
- Worker process not responding

**Solutions:**

1. **Check Worker Logs**
   ```bash
   # Find job directory
   ls -la jobs/
   
   # Check worker log
   tail -f jobs/<job_id>/worker.log
   ```

2. **Kill Stuck Process**
   ```bash
   # Find and kill worker process
   ps aux | grep worker.py
   kill -9 <PID>
   
   # Cancel job via API
   curl -X DELETE http://localhost:10000/api/jobs/<job_id>
   ```

3. **Restart Application**
   ```bash
   # Restart Flask app
   pkill -f "python3 app.py"
   python3 app.py &
   
   # Or restart Docker
   docker compose restart
   ```

### Job Fails Immediately

**Symptoms:**
- Job fails right after starting
- "Worker exited with code" error
- Missing files or permissions

**Solutions:**

1. **Check Error Details**
   ```bash
   # Get job status
   curl http://localhost:10000/api/jobs/<job_id>
   
   # Check status.json
   cat jobs/<job_id>/status.json
   ```

2. **Common Causes**
   - Video file missing or corrupted
   - Frames directory missing
   - Transcript file missing
   - Permission denied errors

3. **Verify Files Exist**
   ```bash
   # Check required files
   ls -la uploads/<video>_720p.mp4
   ls -la uploads/<video>/frames/
   ls -la uploads/<video>/transcript.json
   ```

### Slow Processing

**Symptoms:**
- Very slow frame analysis
- High CPU/GPU usage
- System lagging

**Solutions:**

1. **Optimize Settings**
   - Reduce FPS (0.5 instead of 1.0)
   - Use smaller LLM model
   - Reduce frame resolution

2. **System Resources**
   ```bash
   # Check system resources
   top
   nvidia-smi
   free -h
   
   # Close other applications
   # Add more RAM if needed
   # Consider GPU upgrade
   ```

3. **Network Latency**
   - Use local Ollama instead of OpenRouter
   - Check internet connection speed
   - Use wired instead of WiFi

## OpenWebUI Knowledge Base Issues

### Connection Failed

**Symptoms:**
- "Cannot connect to OpenWebUI" error
- Knowledge base sync fails
- API key rejected

**Solutions:**

1. **Verify OpenWebUI Running**
   ```bash
   # Check OpenWebUI
   curl http://localhost:3000/api/v1/models
   
   # Default port is 3000
   # Verify in settings
   ```

2. **Check API Key**
   ```bash
   # Test API key
   curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:3000/api/v1/models
   ```

3. **Configuration**
   ```json
   // Verify settings
   {
     "enabled": true,
     "url": "http://localhost:3000",
     "api_key": "sk-...",
     "base_name": "video-analysis"
   }
   ```

### Sync Fails

**Symptoms:**
- Job results not syncing
- "Failed to sync" error
- Duplicate entries

**Solutions:**

1. **Check Job Results**
   ```bash
   # Verify job completed
   cat jobs/<job_id>/results.json | head -5
   
   # Check results format
   ```

2. **Knowledge Base Permissions**
   - Verify API key has write access
   - Check knowledge base exists
   - Verify CORS settings in OpenWebUI

3. **Manual Sync**
   ```bash
   # Sync manually
   curl -X POST http://localhost:10000/api/knowledge/sync/<job_id>
   ```

## Docker-Specific Issues

### Volume Mount Problems

**Symptoms:**
- Files not persisting
- Permission errors in containers
- "Read-only file system" errors

**Solutions:**

1. **Check Volume Mounts**
   ```bash
   # List Docker volumes
   docker volume ls
   
   # Inspect volume
   docker volume inspect video-analyzer-web_uploads
   ```

2. **Fix Permissions**
   ```bash
   # Set correct permissions on host
   chmod -R 755 uploads/ jobs/ cache/ config/ output/
   
   # Or use Docker command
   docker compose run --rm app chmod -R 755 /app/uploads
   ```

3. **Volume Configuration**
   ```yaml
   # In docker-compose.yml
   volumes:
     - ./uploads:/app/uploads:rw
     - ./jobs:/app/jobs:rw
     - ./cache:/app/cache:rw
     - ./config:/app/config:rw
     - ./output:/app/output:rw
   ```

### Container Won't Start

**Symptoms:**
- Docker compose fails
- "Cannot start service" error
- Exit code 137 (OOM)

**Solutions:**

1. **Check Docker Logs**
   ```bash
   # Get container logs
   docker compose logs
   
   # Follow logs
   docker compose logs -f
   ```

2. **Memory Issues**
   ```bash
   # Check Docker memory limits
   docker info | grep -i memory
   
   # Increase Docker memory (Docker Desktop)
   # Settings → Resources → Memory
   ```

3. **Rebuild Container**
   ```bash
   # Clean rebuild
   docker compose down -v
   docker compose up --build
   ```

## Logging and Debugging

### Enable Debug Logging

1. **Flask Debug Mode**
   ```python
   # In app.py
   if __name__ == "__main__":
       socketio.run(app, host='0.0.0.0', port=10000, debug=True)
   ```

2. **Worker Debug Logging**
   ```bash
   # Check worker.log
   tail -f jobs/<job_id>/worker.log
   
   # Increase log level in worker.py
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **SocketIO Debug**
   ```javascript
   // In browser console
   localStorage.debug = '*';
   // Refresh page
   ```

### Common Error Messages

1. **"'dict' object has no attribute 'text'"**
   - Fixed in version 3.5.0
   - Update to latest version
   - Use `safe_get_transcript_text()` helper

2. **"CUDA out of memory"**
   - Reduce VRAM buffer
   - Use smaller models
   - Process fewer frames

3. **"Connection refused"**
   - Check service is running
   - Verify port is open
   - Check firewall settings

4. **"File not found"**
   - Verify file exists
   - Check permissions
   - Validate file path

## Getting Help

If issues persist:

1. **Check Documentation**
   - `README.md` - Basic setup
   - `AGENTS.md` - Detailed architecture
   - `DEVELOPMENT.md` - Development guide

2. **Collect Information**
   ```bash
   # System info
   python3 --version
   docker --version
   nvidia-smi
   
   # Application logs
   docker compose logs > logs.txt
   cat jobs/<job_id>/worker.log > worker_log.txt
   ```

3. **Create Issue**
   - Include version from `VERSION` file
   - Provide error logs
   - Describe steps to reproduce
   - Include system information

## Prevention Tips

1. **Regular Maintenance**
   - Clear old job files: `rm -rf jobs/*` (careful!)
   - Clean cache: `rm -rf cache/*`
   - Update dependencies regularly

2. **Monitoring**
   - Check `/api/vram` regularly
   - Monitor disk space: `df -h`
   - Watch logs for warnings

3. **Backup**
   - Backup `config/default_config.json`
   - Backup important results
   - Use version control for customizations