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
    formData.append('fps', document.getElementById('spf-input')?.value || '1');
    formData.append('whisper_model', document.getElementById('upload-whisper-select')?.value || 'base');
    formData.append('language', document.getElementById('upload-language-input')?.value || 'en');
    formData.append('dedup_threshold', document.getElementById('upload-dedup-input')?.value || '10');

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

function handleFrameExtractionProgress(data) {
    // Frame extraction progress - could show in transcode status or separate UI
    console.log(`Frame extraction: ${data.stage} - ${data.progress}%`);
}

function handleTranscriptionProgress(data) {
    console.log(`Transcription: ${data.stage} - ${data.progress}%`);
}
