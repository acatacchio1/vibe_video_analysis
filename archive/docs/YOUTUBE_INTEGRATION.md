# YouTube Download Integration Guide

This document provides complete instructions for integrating the YouTube download module into the Video Analyzer Web UI.

---

## 1. Backend Integration

### 1.1 Create API Blueprint

Create `src/api/youtube.py`:

```python
"""YouTube Video Download API"""

import uuid
import logging
from flask import Blueprint, jsonify, request

from yt_downloader import download_video, DownloadError

youtube_bp = Blueprint("youtube", __name__)
logger = logging.getLogger(__name__)


@youtube_bp.route("/api/youtube/download", methods=["POST"])
def download_youtube_video():
    """
    Download video from YouTube URL and start analysis pipeline.

    Request body:
    {
        "url": "https://youtube.com/watch?v=...",
        "fps": 1.0,
        "whisper_model": "base",
        "language": "en"
    }

    Returns:
    {
        "success": true,
        "job_id": "uuid-...",
        "video_path": "/path/to/video.mp4",
        "title": "Video Title"
    }
    """
    from app import socketio, _transcode_and_delete_with_cleanup

    data = request.get_json(silent=True) or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": {"code": 400, "message": "URL is required"}}), 400

    fps = float(data.get("fps", 1.0))
    whisper_model = data.get("whisper_model", "base")
    language = data.get("language", "en")

    job_id = str(uuid.uuid4())

    try:
        video_path, info = download_video(
            url=url,
            socketio=socketio,
        )

        socketio.emit("youtube_download_complete", {
            "source": info.get("title", "youtube_video"),
            "path": str(video_path),
            "job_id": job_id,
        })

        socketio.start_background_task(
            _transcode_and_delete_with_cleanup,
            str(video_path),
            fps,
            whisper_model,
            language,
        )

        return jsonify({
            "success": True,
            "job_id": job_id,
            "video_path": str(video_path),
            "title": info.get("title", "youtube_video"),
        })

    except DownloadError as e:
        logger.error(f"YouTube download failed: {e}")
        return jsonify({"error": {"code": 500, "message": str(e)}}), 500
    except Exception as e:
        logger.error(f"YouTube download error: {e}")
        return jsonify({"error": {"code": 500, "message": f"Download failed: {str(e)}"}}), 500
```

### 1.2 Register Blueprint in `app.py`

Add to imports section (around line 104-111):

```python
from src.api.youtube import youtube_bp
```

Add to blueprint registration section (after line 120):

```python
app.register_blueprint(youtube_bp)
```

### 1.3 Add yt-dlp to `requirements.txt`

Add this line to `requirements.txt`:

```
yt-dlp
```

---

## 2. Frontend Integration

### 2.1 Create YouTube Module

Create `static/js/modules/youtube.js`:

```javascript
/**
 * YouTube Download Module
 * Handles YouTube video download UI and SocketIO event listeners
 */

function downloadYouTubeVideo() {
    const urlInput = document.getElementById("youtube-url-input");
    const url = url.value.trim();

    if (!url) {
        showToast("Please enter a YouTube URL", "error");
        return;
    }

    const progressDiv = document.getElementById("youtube-progress");
    const progressBar = document.getElementById("youtube-progress-bar");
    const progressText = document.getElementById("youtube-progress-text");
    const downloadBtn = document.getElementById("youtube-download-btn");

    progressDiv.style.display = "block";
    progressBar.style.width = "0%";
    progressText.textContent = "Starting download...";
    downloadBtn.disabled = true;

    fetch("/api/youtube/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            url: url,
            fps: 1.0,
            whisper_model: "base",
            language: "en"
        }),
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            progressText.textContent = `Download started: ${data.title}`;
        } else {
            const errorMsg = data.error?.message || data.error || "Download failed";
            showToast(errorMsg, "error");
            resetYouTubeUI();
        }
    })
    .catch(err => {
        showToast("Download failed: " + err.message, "error");
        resetYouTubeUI();
    });
}

function resetYouTubeUI() {
    document.getElementById("youtube-progress").style.display = "none";
    document.getElementById("youtube-download-btn").disabled = false;
}

function setupYouTubeSocketHandlers(socket) {
    socket.on("youtube_download_progress", (data) => {
        const progressBar = document.getElementById("youtube-progress-bar");
        const progressText = document.getElementById("youtube-progress-text");

        if (progressBar && progressText) {
            progressBar.style.width = `${data.progress}%`;
            progressText.textContent = `Downloading: ${data.progress}% (${data.speed})`;
        }
    });

    socket.on("youtube_download_complete", (data) => {
        const progressText = document.getElementById("youtube-progress-text");
        if (progressText) {
            progressText.textContent = `Download complete: ${data.source}`;
        }
        showToast(`Download complete: ${data.source}`, "success");
    });

    socket.on("youtube_download_error", (data) => {
        showToast(`Download error: ${data.error}`, "error");
        resetYouTubeUI();
    });
}
```

### 2.2 Add HTML to `templates/index.html`

Add this section at the **top of the page** (before the existing upload section):

```html
<!-- YouTube Download Section -->
<div id="youtube-download-section" class="card" style="margin-bottom: 20px;">
    <h3>Download from YouTube</h3>
    <div class="youtube-download-form">
        <input
            type="text"
            id="youtube-url-input"
            placeholder="https://youtube.com/watch?v=..."
            class="youtube-url-input"
        />
        <button id="youtube-download-btn" class="btn btn-primary" onclick="downloadYouTubeVideo()">
            Download
        </button>
    </div>
    <div id="youtube-progress" class="youtube-progress" style="display: none;">
        <div class="youtube-progress-bar-container">
            <div id="youtube-progress-bar" class="youtube-progress-bar"></div>
        </div>
        <p id="youtube-progress-text" class="youtube-progress-text"></p>
    </div>
</div>
```

### 2.3 Add CSS to `static/css/style.css`

Add these styles to the end of the CSS file:

```css
/* YouTube Download Styles */
.youtube-download-form {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-top: 10px;
}

.youtube-url-input {
    flex: 1;
    padding: 10px;
    border: 1px solid var(--border-color, #ddd);
    border-radius: 4px;
    font-size: 14px;
}

.youtube-progress {
    margin-top: 10px;
}

.youtube-progress-bar-container {
    background: var(--bg-secondary, #f0f0f0);
    border-radius: 4px;
    overflow: hidden;
    height: 20px;
}

.youtube-progress-bar {
    width: 0%;
    height: 100%;
    background: var(--color-primary, #4CAF50);
    transition: width 0.3s ease;
}

.youtube-progress-text {
    margin: 5px 0 0;
    font-size: 14px;
    color: var(--text-secondary, #666);
}
```

### 2.4 Update Script Loading Order in `templates/index.html`

Add `youtube.js` to the script tags **before** `init.js` and **before** `videos.js`:

```html
<!-- Add this line before videos.js -->
<script src="/static/js/modules/youtube.js"></script>
```

The loading order should be:
```html
<script src="/static/js/modules/state.js"></script>
<script src="/static/js/modules/ui.js"></script>
<script src="/static/js/modules/youtube.js"></script>
<script src="/static/js/modules/videos.js"></script>
<!-- ... other modules ... -->
<script src="/static/js/modules/init.js"></script>
```

### 2.5 Integrate SocketIO Handlers in `static/js/modules/socket.js`

Add this to the socket initialization section (where other handlers are set up):

```javascript
// YouTube download handlers
if (typeof setupYouTubeSocketHandlers === 'function') {
    setupYouTubeSocketHandlers(socket);
}
```

---

## 3. Testing

### 3.1 Test the Module Standalone

```python
# Test script (run from project root)
from yt_downloader import download_video

video_path, info = download_video(
    url="https://www.youtube.com/watch?v=dQw4wR9XwRc",
    socketio=None,  # No socketio for testing
)

print(f"Downloaded: {video_path}")
print(f"Title: {info.get('title')}")
```

### 3.2 Test the API Endpoint

```bash
curl -X POST http://localhost:10000/api/youtube/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4wR9XwRc"}'
```

### 3.3 Verify SocketIO Events

Open browser console and watch for:
- `youtube_download_progress` events during download
- `youtube_download_complete` when finished
- `transcode_progress` events from the existing pipeline
- `job_status` events from the analysis worker

---

## 4. Error Handling

| Stage | SocketIO Event | Cleanup |
|-------|---------------|---------|
| Download fails | `youtube_download_error` | Temp file deleted |
| Transcode fails | `transcode_progress` (stage="failed") | Video kept in uploads |
| Frame extraction fails | `frame_extraction_progress` (stage="failed") | Video kept |
| Transcription fails | `transcription_progress` (stage="failed") | Non-fatal, continues |

---

## 5. File Changes Summary

| File | Change |
|------|--------|
| `yt_downloader/__init__.py` | **NEW** - Module exports |
| `yt_downloader/config.py` | **NEW** - Configuration |
| `yt_downloader/progress.py` | **NEW** - SocketIO progress hook |
| `yt_downloader/downloader.py` | **NEW** - Core download logic |
| `src/api/youtube.py` | **NEW** - API blueprint |
| `app.py` | **MODIFY** - Import and register blueprint |
| `requirements.txt` | **MODIFY** - Add yt-dlp |
| `templates/index.html` | **MODIFY** - Add HTML section, add script tag |
| `static/js/modules/youtube.js` | **NEW** - Frontend module |
| `static/js/modules/socket.js` | **MODIFY** - Add socket handler call |
| `static/css/style.css` | **MODIFY** - Add YouTube styles |

---

## 6. Complete Flow

```
User enters URL → Clicks Download
    ↓
POST /api/youtube/download
    ↓
Generate job_id → Return immediately to UI
    ↓
Download to yt_downloader/temp/ → Emit youtube_download_progress (0-100%)
    ↓
Move to uploads/ → Emit youtube_download_complete
    ↓
Start _transcode_and_delete_with_cleanup() → Existing pipeline
    ↓
Transcode → Extract frames → Transcribe → Queue job
    ↓
Worker analyzes frames → Existing SocketIO events
    ↓
Results saved → Job complete
```
