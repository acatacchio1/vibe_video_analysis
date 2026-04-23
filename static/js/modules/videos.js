// Video management: upload, list, delete, transcode
async function loadVideos() {
    try {
        const response = await fetch('/api/videos');
        const videos = await response.json();
        renderVideosList(videos);
        updateVideoSelect(videos);
    } catch (error) {
        console.error('Failed to load videos:', error);
    }
}

function renderVideosList(videos) {
    const container = document.getElementById('videos-list');
    if (!container) return;

    if (videos.length === 0) {
        container.innerHTML = '<div class="empty-state">No videos uploaded yet.</div>';
        return;
    }

    container.innerHTML = videos.map(video => `
        <div class="video-item" data-name="${video.name}" data-path="${video.path}">
            <div class="video-thumbnail">
                ${video.thumbnail ? `<img src="${video.thumbnail}" alt="">` : '<span class="placeholder">🎬</span>'}
            </div>
            <div class="video-info">
                <div class="video-name" title="${video.name}">${video.name}</div>
                <div class="video-meta">
                    <span>${video.size_human}</span>
                    <span>${video.duration_formatted}</span>
                </div>
            </div>
            <div class="video-actions">
                <button onclick="openReprocessModal('${video.name}', '${video.path}')" title="Reprocess with new settings">🔄</button>
                <button onclick="deleteVideo('${video.name}')" title="Delete video">🗑️</button>
            </div>
        </div>
    `).join('');
}

function updateVideoSelect(videos) {
    const select = document.getElementById('video-select');
    if (!select) return;

    const currentValue = select.value;
    select.innerHTML = '<option value="">Select a video...</option>' +
        videos.map(v => `<option value="${v.path}" data-name="${v.name}">${v.name} (${v.duration_formatted})</option>`).join('');

    if (currentValue) {
        select.value = currentValue;
    }
}

async function deleteVideo(name) {
    if (!confirm(`Delete "${name}" and all associated data?`)) return;

    try {
        const response = await fetch(`/api/videos/${encodeURIComponent(name)}`, { method: 'DELETE' });
        const result = await response.json();

        if (result.success) {
            showToast('Video deleted');
            loadVideos();
        } else {
            showToast(result.error?.message || 'Failed to delete video', 'error');
        }
    } catch (error) {
        showToast('Delete failed: ' + error.message, 'error');
    }
}

function initUploadHandlers() {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('video-upload');
    if (!uploadArea || !fileInput) return;

    uploadArea.addEventListener('click', () => fileInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleVideoUpload(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleVideoUpload(e.target.files[0]);
        }
    });
}

async function handleVideoUpload(file) {
    const formData = new FormData();
    formData.append('video', file);
    formData.append('whisper_model', document.getElementById('upload-whisper-select')?.value || 'base');
    formData.append('language', document.getElementById('upload-language-input')?.value || 'en');

    const uploadArea = document.getElementById('upload-area');
    const progress = uploadArea?.querySelector('.upload-progress');
    const progressBar = progress?.querySelector('.progress-fill');
    const progressText = progress?.querySelector('.progress-text');

    if (progress) progress.hidden = false;

    try {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/videos/upload');

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                if (progressBar) progressBar.style.width = `${pct}%`;
                if (progressText) progressText.textContent = `${pct}%`;
            }
        });

        xhr.onload = () => {
            const result = JSON.parse(xhr.responseText);
            if (result.success) {
                showToast(`Uploaded: ${result.filename}`);
                loadVideos();
            } else {
                showToast(result.error?.message || 'Upload failed', 'error');
            }
            if (progress) progress.hidden = true;
        };

        xhr.onerror = () => {
            showToast('Upload failed', 'error');
            if (progress) progress.hidden = true;
        };

        xhr.send(formData);
    } catch (error) {
        showToast('Upload failed: ' + error.message, 'error');
        if (progress) progress.hidden = true;
    }
}

function handleTranscodeProgress(data) {
    // Old transcode progress - keep for backward compatibility
    const status = document.getElementById('transcode-status');
    const label = document.getElementById('transcode-label');
    const pct = document.getElementById('transcode-pct');
    const fill = document.getElementById('transcode-fill');

    if (!status) return;

    status.classList.remove('hidden');
    if (label) label.textContent = `${data.stage}: ${data.source}`;
    if (pct) pct.textContent = `${data.progress}%`;
    if (fill) fill.style.width = `${data.progress}%`;

    if (data.stage === 'complete' || data.stage === 'failed') {
        setTimeout(() => status.classList.add('hidden'), 3000);
    }
}

function handleVideoProcessingProgress(data) {
    // New parallel processing progress
    const status = document.getElementById('video-processing-status');
    const overallLabel = document.getElementById('processing-label');
    const overallPct = document.getElementById('overall-pct');
    
    // Frame extraction progress
    const framesPct = document.getElementById('frames-pct');
    const framesFill = document.getElementById('frames-fill');
    const framesDetails = document.getElementById('frames-details');
    
    // Transcription progress  
    const transcriptionPct = document.getElementById('transcription-pct');
    const transcriptionFill = document.getElementById('transcription-fill');
    const transcriptionDetails = document.getElementById('transcription-details');

    if (!status) return;
    
    // Check if this is a frame extraction or transcription specific update
    if (data.source && data.source.endsWith('_frames')) {
        // Frame extraction specific update
        const progress = data.progress || 0;
        const stage = data.stage || 'waiting';
        const details = data.error || data.message || `Frame extraction: ${stage}`;
        
        if (framesPct) framesPct.textContent = `${progress}%`;
        if (framesFill) framesFill.style.width = `${progress}%`;
        if (framesDetails) framesDetails.textContent = details;
        
        // Update overall progress (frames are ~70% of total work)
        const overallProgress = Math.min(100, Math.round(progress * 0.7));
        updateOverallProgress(overallProgress, stage);
        
    } else if (data.source && data.source.endsWith('_transcription')) {
        // Transcription specific update
        const progress = data.progress || 0;
        const stage = data.stage || 'waiting';
        const details = data.error || data.message || `Transcription: ${stage}`;
        
        if (transcriptionPct) transcriptionPct.textContent = `${progress}%`;
        if (transcriptionFill) transcriptionFill.style.width = `${progress}%`;
        if (transcriptionDetails) transcriptionDetails.textContent = details;
        
        // Update overall progress (transcription is ~30% of total work)
        const overallProgress = 70 + Math.round(progress * 0.3);
        updateOverallProgress(overallProgress, stage);
        
    } else {
        // Overall update
        const stage = data.stage || 'unknown';
        const progress = data.progress || 0;
        
        updateOverallProgress(progress, stage);
        
        if (overallLabel) overallLabel.textContent = `${stage}: ${data.source || 'video'}`;
    }
    
    // Show/hide status based on stage
    status.classList.remove('hidden');
    
    if (data.stage === 'complete' || data.stage === 'failed') {
        if (overallLabel && data.stage === 'complete') {
            overallLabel.textContent = `Processing complete: ${data.source || 'video'}`;
        }
        if (overallLabel && data.stage === 'failed') {
            overallLabel.textContent = `Processing failed: ${data.source || 'video'}`;
            if (overallPct) overallPct.textContent = "Failed";
        }
        setTimeout(() => status.classList.add('hidden'), 5000);
    }
}

function updateOverallProgress(progress, stage) {
    const overallPct = document.getElementById('overall-pct');
    if (overallPct) {
        if (stage === 'failed') {
            overallPct.textContent = "Failed";
        } else if (stage === 'complete') {
            overallPct.textContent = "100%";
        } else {
            overallPct.textContent = `${progress}%`;
        }
    }
}

function handleFrameExtractionProgress(data) {
    // Legacy frame extraction progress - convert to new format
    const stage = data.stage || 'extracting_frames';
    const progress = data.progress || 0;
    const details = data.error || `Extracting frames: ${progress}%`;
    
    handleVideoProcessingProgress({
        source: `${data.source}_frames`,
        stage: stage,
        progress: progress,
        message: details
    });
}

function handleTranscriptionProgress(data) {
    // Legacy transcription progress - convert to new format
    const stage = data.stage || 'transcribing';
    const progress = data.progress || 0;
    const details = data.error || `Transcribing audio: ${progress}%`;
    
    handleVideoProcessingProgress({
        source: `${data.source}_transcription`,
        stage: stage,
        progress: progress,
        message: details
    });
}

function appendServerLog(data) {
    const container = document.getElementById('server-log-content');
    if (!container) return;

    const entry = document.createElement('div');
    entry.className = `log-entry log-${data.level}`;

    const ts = data.timestamp ? data.timestamp.split('.')[0].split(' ')[1] || data.timestamp : '';
    entry.innerHTML = `<span class="log-timestamp">${ts}</span><span class="log-level">[${data.level}]</span>${escapeHtml(data.message)}`;

    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;

    while (container.children.length > 500) {
        container.removeChild(container.firstChild);
    }
}

function clearServerLog() {
    const container = document.getElementById('server-log-content');
    if (container) container.innerHTML = '';
}

function openReprocessModal(name, path) {
    const modal = document.getElementById('reprocess-modal');
    document.getElementById('reprocess-video-name').textContent = name;
    document.getElementById('reprocess-video-path').value = path;
    modal.classList.remove('hidden');
}

async function submitReprocess() {
    const path = document.getElementById('reprocess-video-path').value;
    const whisper = document.getElementById('reprocess-whisper').value || 'base';
    const language = document.getElementById('reprocess-language').value || 'en';

    try {
        const response = await fetch('/api/videos/reprocess', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_path: path,
                whisper_model: whisper,
                language: language,
            }),
        });
        const result = await response.json();
        if (result.success) {
            showToast(`Reprocessing started for ${path.split('/').pop()}`);
            closeModal();
        } else {
            showToast(result.error?.message || 'Reprocess failed', 'error');
        }
    } catch (error) {
        showToast('Reprocess failed: ' + error.message, 'error');
    }
}


