/**
 * Video Analyzer Web - Main Application
 */

// ========================================
// Global State
// ========================================

const state = {
    socket: null,
    videos: [],
    providers: {},
    jobs: [],
    storedResults: [],
    currentJob: localStorage.getItem('va_current_job') || null,
    systemStatus: {},
    selectedProvider: null,
    selectedProviderType: null,
    selectedModel: null,
    selectedResult: null,
    openRouterKey: localStorage.getItem('openrouter_api_key') || '',
    settings: JSON.parse(localStorage.getItem('va_settings') || '{}'),
    expandedPanels: JSON.parse(localStorage.getItem('va_expanded_panels') || '[]'),
    transcodeActive: false
};

// ========================================
// Initialization
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    initSocket();
    initUI();
    loadVideos();
    loadProviders();
    loadJobs();
    loadStoredResults();
    restoreSettings();
    initChatProviderSelect();
    requestNotificationPermission();

    // Restore live analysis panel if there's a current job
    if (state.currentJob) {
        const livePanel = document.getElementById('live-analysis');
        if (livePanel) {
            livePanel.classList.remove('hidden');
            const framesLog = document.getElementById('frames-log');
            if (framesLog) {
                framesLog.innerHTML = '<div class="loading">Reconnecting to job...</div>';
            }
        }
        const llmPanel = document.getElementById('live-llm-panel');
        if (llmPanel) {
            llmPanel.style.display = 'block';
        }
    }
});

function initSocket() {
    state.socket = io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        pingTimeout: 60000,
        pingInterval: 25000
    });

    state.socket.on('connect', () => {
        console.log('Connected to server');
        showToast('Connected to Video Analyzer');

        // Re-subscribe to current job if we were monitoring one
        if (state.currentJob) {
            console.log(`Re-subscribing to job ${state.currentJob} after reconnect`);
            state.socket.emit('subscribe_job', { job_id: state.currentJob });
        }

        // Reload data
        loadVideos();
        loadJobs();
    });

    state.socket.on('disconnect', (reason) => {
        console.log('Disconnected from server:', reason);
        showToast(`Disconnected: ${reason}`, 'warning');
    });

    state.socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
        showToast('Connection error, retrying...', 'warning');
    });

    state.socket.on('reconnect', (attemptNumber) => {
        console.log('Reconnected after', attemptNumber, 'attempts');
        showToast('Reconnected!', 'success');
    });

    state.socket.on('reconnect_attempt', (attemptNumber) => {
        console.log('Reconnection attempt', attemptNumber);
    });

    state.socket.on('reconnect_error', (error) => {
        console.error('Reconnection error:', error);
    });

    state.socket.on('reconnect_failed', () => {
        console.error('Failed to reconnect');
        showToast('Failed to reconnect', 'error');
    });

    state.socket.on('system_status', handleSystemStatus);
    state.socket.on('job_created', handleJobCreated);
    state.socket.on('job_status', handleJobStatus);
    state.socket.on('job_complete', handleJobComplete);
    state.socket.on('job_transcript', handleJobTranscript);
    state.socket.on('job_description', handleJobDescription);
    state.socket.on('frame_analysis', handleFrameAnalysis);
    state.socket.on('vram_event', handleVRAMEvent);
    state.socket.on('transcode_progress', handleTranscodeProgress);
    state.socket.on('video_transcoded', handleVideoTranscoded);
    state.socket.on('videos_updated', () => loadVideos());
}

function initUI() {
    // Upload area
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('video-upload');
    
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', handleFileSelect);
    
    // Main tabs
    document.querySelectorAll('.main-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchMainTab(btn.dataset.tab));
    });
    
    // Provider discovery
    document.getElementById('discover-btn').addEventListener('click', discoverProviders);
    
    // Provider selection
    document.getElementById('provider-select').addEventListener('change', handleProviderChange);
    
    // Model selection
    document.getElementById('model-select').addEventListener('change', handleModelChange);
    
    // Advanced options toggle
    document.getElementById('advanced-toggle-btn').addEventListener('click', toggleAdvancedOptions);
    
    // Analysis form
    document.getElementById('analysis-form').addEventListener('submit', handleStartAnalysis);
    
    // Monitor tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchMonitorTab(btn.dataset.tab));
    });
    
    // Notifications
    document.getElementById('notifications-btn').addEventListener('click', requestNotificationPermission);
    
    // Modal close
    document.querySelector('.close-btn').addEventListener('click', closeModal);
    document.getElementById('job-modal').addEventListener('click', (e) => {
        if (e.target.id === 'job-modal') closeModal();
    });
    
    // Save settings on change
    document.querySelectorAll('#analysis-form input, #analysis-form select, #analysis-form textarea').forEach(el => {
        el.addEventListener('change', saveSettings);
    });
}

// ========================================
// Main Tabs
// ========================================

function switchMainTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.main-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.main-tab-content').forEach(c => c.classList.add('hidden'));
    
    // Activate selected tab
    document.querySelector(`.main-tab-btn[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.remove('hidden');
}

// ========================================
// Video Upload & Transcoding
// ========================================

function handleDragOver(e) {
    e.preventDefault();
    e.currentTarget.classList.add('dragover');
}

function handleDragLeave(e) {
    e.currentTarget.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) uploadFile(files[0]);
}

function handleFileSelect(e) {
    if (e.target.files.length > 0) uploadFile(e.target.files[0]);
}

async function uploadFile(file) {
    const uploadArea = document.getElementById('upload-area');
    const progressBar = uploadArea.querySelector('.upload-progress');
    const progressFill = uploadArea.querySelector('.progress-fill');
    const progressText = uploadArea.querySelector('.progress-text');
    
    uploadArea.querySelector('.upload-prompt').hidden = true;
    progressBar.hidden = false;
    
    const formData = new FormData();
    formData.append('video', file);
    
    // Use XMLHttpRequest for upload progress
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        
        xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) {
                const percent = Math.round((event.loaded / event.total) * 100);
                progressFill.style.width = `${percent}%`;
                progressText.textContent = `${percent}%`;
            }
        });
        
        xhr.addEventListener('load', () => {
            try {
                const result = JSON.parse(xhr.responseText);
                
                if (xhr.status >= 200 && xhr.status < 300) {
                    if (result.success) {
                        showToast(`Uploaded: ${result.filename}`);
                        resolve(result);
                    } else {
                        showToast(result.error || 'Upload failed', 'error');
                        reject(new Error(result.error || 'Upload failed'));
                    }
                } else {
                    showToast(`Upload failed: ${result.error || xhr.statusText}`, 'error');
                    reject(new Error(result.error || xhr.statusText));
                }
            } catch (error) {
                showToast('Upload response error: ' + error.message, 'error');
                reject(error);
            } finally {
                uploadArea.querySelector('.upload-prompt').hidden = false;
                progressBar.hidden = true;
                progressFill.style.width = '0%';
                progressText.textContent = '0%';
                document.getElementById('video-upload').value = '';
            }
        });
        
        xhr.addEventListener('error', () => {
            showToast('Upload failed: Network error', 'error');
            uploadArea.querySelector('.upload-prompt').hidden = false;
            progressBar.hidden = true;
            progressFill.style.width = '0%';
            progressText.textContent = '0%';
            document.getElementById('video-upload').value = '';
            reject(new Error('Network error'));
        });
        
        xhr.addEventListener('abort', () => {
            showToast('Upload cancelled', 'warning');
            uploadArea.querySelector('.upload-prompt').hidden = false;
            progressBar.hidden = true;
            progressFill.style.width = '0%';
            progressText.textContent = '0%';
            document.getElementById('video-upload').value = '';
            reject(new Error('Upload cancelled'));
        });
        
        xhr.open('POST', '/api/videos/upload');
        xhr.send(formData);
    });
}

function handleTranscodeProgress(data) {
    const statusDiv = document.getElementById('transcode-status');
    const labelSpan = document.getElementById('transcode-label');
    const pctSpan = document.getElementById('transcode-pct');
    const fillDiv = document.getElementById('transcode-fill');
    
    if (!statusDiv || !labelSpan || !pctSpan || !fillDiv) return;
    
    if (data.stage === 'complete') {
        statusDiv.classList.add('hidden');
        state.transcodeActive = false;
        showToast(`Transcoded ${data.source} → ${data.output}`, 'success');
    } else if (data.stage === 'failed') {
        statusDiv.classList.add('hidden');
        state.transcodeActive = false;
        showToast(`Transcode failed for ${data.source}: ${data.error}`, 'error');
    } else {
        state.transcodeActive = true;
        statusDiv.classList.remove('hidden');
        labelSpan.textContent = `Transcoding ${data.source} → ${data.output}`;
        pctSpan.textContent = `${data.progress}%`;
        fillDiv.style.width = `${data.progress}%`;
        
        // Update stage-specific messages
        if (data.stage === 'starting') labelSpan.textContent = `Starting transcode: ${data.source}`;
        if (data.stage === 'transcoding') labelSpan.textContent = `Transcoding ${data.source} → ${data.output}`;
        if (data.stage === 'finalizing') labelSpan.textContent = `Finalizing ${data.output}`;
    }
}

function handleVideoTranscoded(data) {
    showToast(`Transcoded: ${data.transcoded}`, 'success');
    loadVideos();
}

// ========================================
// Video Management
// ========================================

async function loadVideos() {
    try {
        const response = await fetch('/api/videos');
        state.videos = await response.json();
        renderVideos();
    } catch (error) {
        console.error('Failed to load videos:', error);
    }
}

function renderVideos() {
    const container = document.getElementById('videos-list');
    const select = document.getElementById('video-select');
    
    if (state.videos.length === 0) {
        container.innerHTML = '<div class="empty-state">No videos uploaded yet</div>';
        select.innerHTML = '<option value="">Select a video...</option>';
        return;
    }
    
    // Render list
    container.innerHTML = state.videos.map(video => `
        <div class="video-item" data-path="${video.path}">
            <div class="video-thumbnail">
                ${video.thumbnail 
                    ? `<img src="/api/thumbnail/${encodeURIComponent(video.name)}" alt="">`
                    : '<div class="placeholder">🎬</div>'
                }
            </div>
            <div class="video-info">
                <div class="video-name" title="${video.name}">${video.name}</div>
                <div class="video-meta">${video.size_human} • ${video.duration_formatted}</div>
            </div>
            <div class="video-actions">
                <button class="analyze-btn" title="Analyze" onclick="selectVideoForAnalysis('${video.path}', '${video.name}')">▶️</button>
                <button class="transcode-btn" title="Transcode to 720p" onclick="transcodeVideo('${video.path}')">🎞️</button>
                <button class="delete-btn" title="Delete" onclick="deleteVideo('${video.name}')">🗑️</button>
            </div>
        </div>
    `).join('');
    
    // Update select
    select.innerHTML = '<option value="">Select a video...</option>' +
        state.videos.map(v => `<option value="${v.path}">${v.name}</option>`).join('');
}

async function deleteVideo(filename) {
    if (!confirm(`Delete "${filename}"?`)) return;
    
    try {
        const response = await fetch(`/api/videos/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Video deleted');
            loadVideos();
        } else {
            showToast('Failed to delete video', 'error');
        }
    } catch (error) {
        showToast('Delete failed: ' + error.message, 'error');
    }
}

function selectVideoForAnalysis(path, name) {
    document.getElementById('video-select').value = path;
    switchMainTab('analyze');
    document.getElementById('new-analysis-section').scrollIntoView({ behavior: 'smooth' });
    showToast(`Selected: ${name}`);
}

async function transcodeVideo(videoPath) {
    if (!confirm('Manually transcode video to 720p@1fps? (Source will be deleted)')) return;
    
    try {
        const response = await fetch('/api/videos/transcode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_path: videoPath })
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('Transcoding started');
        } else {
            showToast('Transcoding failed: ' + result.error, 'error');
        }
    } catch (error) {
        showToast('Transcoding error: ' + error.message, 'error');
    }
}

// ========================================
// Providers & Models
// ========================================

async function loadProviders() {
    try {
        const response = await fetch('/api/providers');
        const providerList = await response.json();
        
        state.providers = {};
        providerList.forEach(p => {
            state.providers[p.name] = p;
        });
        
        renderProviderSelect();
        initChatProviderSelect();
    } catch (error) {
        console.error('Failed to load providers:', error);
    }
}

function renderProviderSelect() {
    const select = document.getElementById('provider-select');
    
    select.innerHTML = '<option value="">Select provider...</option>' +
        '<optgroup label="Ollama">' +
        Object.values(state.providers)
            .filter(p => p.type === 'ollama')
            .map(p => `<option value="${p.name}" data-type="ollama">${p.name} (${p.status})</option>`)
            .join('') +
        '</optgroup>' +
        '<optgroup label="Cloud">' +
        '<option value="openrouter" data-type="openrouter">OpenRouter (API)</option>' +
        '</optgroup>';
}

async function discoverProviders() {
    const btn = document.getElementById('discover-btn');
    btn.disabled = true;
    btn.textContent = '🔄 Scanning...';
    
    try {
        const response = await fetch('/api/providers/discover');
        const result = await response.json();
        
        showToast(`Discovered ${result.discovered} Ollama instances`);
        await loadProviders();
    } catch (error) {
        showToast('Discovery failed: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 Discover';
    }
}

async function handleProviderChange(e) {
    const providerName = e.target.value;
    const providerType = e.target.selectedOptions[0]?.dataset.type;
    const modelSelect = document.getElementById('model-select');
    const statusDiv = document.getElementById('provider-status');
    const costEstimate = document.getElementById('cost-estimate');

    state.selectedProvider = providerName;
    state.selectedProviderType = providerType || 'openrouter';
    state.selectedModel = null;
    
    modelSelect.innerHTML = '<option value="">Loading models...</option>';
    modelSelect.disabled = true;
    
    if (providerType === 'ollama') {
        costEstimate.classList.add('hidden');
        
        const provider = state.providers[providerName];
        if (provider) {
            statusDiv.textContent = `Status: ${provider.status}`;
            statusDiv.className = 'provider-status ' + provider.status;
            
            if (provider.status === 'online') {
                try {
                    const response = await fetch(`/api/providers/ollama/models?server=${encodeURIComponent(provider.url)}`);
                    const data = await response.json();
                    
                    if (data.models) {
                        modelSelect.innerHTML = '<option value="">Select model...</option>' +
                            data.models.map(m => 
                                `<option value="${m.id}" data-vram="${m.vram_required}">${m.name} (${formatBytes(m.size)})</option>`
                            ).join('');
                        modelSelect.disabled = false;
                    }
                } catch (error) {
                    statusDiv.textContent = 'Error loading models';
                    statusDiv.className = 'provider-status error';
                }
            }
        }
    } else if (providerName === 'openrouter') {
        promptForOpenRouterKey();
    }
    
    updateStartButton();
}

function promptForOpenRouterKey() {
    const existingKey = state.openRouterKey;
    const key = prompt(
        'Enter your OpenRouter API key:' + 
        (existingKey ? '\n\n(Leave empty to use saved key)' : ''),
        existingKey || ''
    );
    
    if (key === null) {
        document.getElementById('provider-select').value = '';
        return;
    }
    
    if (key) {
        state.openRouterKey = key;
        localStorage.setItem('openrouter_api_key', key);
    }
    
    if (!state.openRouterKey) {
        showToast('API key required for OpenRouter', 'error');
        document.getElementById('provider-select').value = '';
        return;
    }
    
    loadOpenRouterModels();
}

async function loadOpenRouterModels() {
    const modelSelect = document.getElementById('model-select');
    const statusDiv = document.getElementById('provider-status');
    const costEstimate = document.getElementById('cost-estimate');
    
    try {
        const response = await fetch(`/api/providers/openrouter/models?api_key=${encodeURIComponent(state.openRouterKey)}`);
        const data = await response.json();
        
        if (data.models) {
            modelSelect.innerHTML = '<option value="">Select model...</option>' +
                data.models.map(m => 
                    `<option value="${m.id}" data-prompt="${m.pricing_prompt}" data-completion="${m.pricing_completion}">${m.name}</option>`
                ).join('');
            modelSelect.disabled = false;
            
            statusDiv.textContent = 'Status: online';
            statusDiv.className = 'provider-status online';
            
            costEstimate.classList.remove('hidden');
            loadOpenRouterBalance();
        } else {
            throw new Error('No models returned');
        }
    } catch (error) {
        statusDiv.textContent = 'Error: Invalid API key or connection failed';
        statusDiv.className = 'provider-status error';
        showToast('Failed to load OpenRouter models', 'error');
    }
}

async function loadOpenRouterBalance() {
    try {
        const response = await fetch(`/api/providers/openrouter/balance?api_key=${encodeURIComponent(state.openRouterKey)}`);
        const data = await response.json();
        
        const costDiv = document.getElementById('cost-estimate');
        const balanceInfo = document.createElement('div');
        balanceInfo.id = 'openrouter-balance';
        balanceInfo.className = 'balance-info';
        balanceInfo.innerHTML = `
            <div class="cost-row">
                <span>API Balance:</span>
                <span id="balance-value">$${data.balance?.toFixed(2) || '0.00'}</span>
            </div>
        `;
        
        const existing = document.getElementById('openrouter-balance');
        if (existing) existing.remove();
        costDiv.insertBefore(balanceInfo, costDiv.firstChild);
    } catch (error) {
        console.error('Failed to load balance:', error);
    }
}

async function handleModelChange(e) {
    const modelId = e.target.value;
    state.selectedModel = modelId;
    
    if (!modelId) {
        updateStartButton();
        return;
    }
    
    const providerType = document.getElementById('provider-select').selectedOptions[0]?.dataset.type;
    
    if (providerType === 'ollama') {
        const vram = e.target.selectedOptions[0]?.dataset.vram;
        document.getElementById('vram-required').textContent = vram ? formatBytes(parseInt(vram)) : '--';
        document.getElementById('cost-estimate').classList.remove('hidden');
        document.getElementById('cost-value').textContent = 'Free (local)';
    } else if (state.selectedProvider === 'openrouter') {
        updateCostEstimate();
    }
    
    updateStartButton();
}

async function updateCostEstimate() {
    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect.value;
    const maxFrames = parseInt(document.getElementById('max-frames-input').value) || 10000;
    
    if (!modelId || !state.openRouterKey) return;
    
    try {
        const response = await fetch(`/api/providers/openrouter/cost?api_key=${encodeURIComponent(state.openRouterKey)}&model=${encodeURIComponent(modelId)}&frames=${maxFrames}`);
        const data = await response.json();
        
        document.getElementById('cost-value').textContent = `$${data.min.toFixed(2)} - $${data.max.toFixed(2)}`;
        document.getElementById('vram-required').textContent = 'Cloud (no local VRAM)';
        
        state.costEstimate = data;
    } catch (error) {
        console.error('Failed to get cost estimate:', error);
    }
}

// ========================================
// Analysis Job Management
// ========================================

async function handleStartAnalysis(e) {
    e.preventDefault();
    
    const videoPath = document.getElementById('video-select').value;
    const providerSelect = document.getElementById('provider-select');
    const modelSelect = document.getElementById('model-select');
    
    if (!videoPath || !providerSelect.value || !modelSelect.value) {
        showToast('Please fill in all required fields', 'error');
        return;
    }
    
    const providerType = providerSelect.selectedOptions[0].dataset.type || 'openrouter';
    const providerName = providerSelect.value;
    const modelId = modelSelect.value;
    
    // For OpenRouter, validate budget
    if (providerName === 'openrouter' && state.costEstimate) {
        const balanceResponse = await fetch(`/api/providers/openrouter/balance?api_key=${encodeURIComponent(state.openRouterKey)}`);
        const balanceData = await balanceResponse.json();
        
        const balance = balanceData.balance || 0;
        const maxCost = state.costEstimate.max;
        
        if (maxCost > balance) {
            const costPerFrame = maxCost / parseInt(document.getElementById('max-frames-input').value);
            const affordableFrames = Math.floor(balance / costPerFrame);
            
            const proceed = confirm(
                `⚠️ Insufficient API balance!\n\n` +
                `Estimated cost: $${maxCost.toFixed(2)}\n` +
                `Your balance: $${balance.toFixed(2)}\n\n` +
                `You can afford approximately ${affordableFrames} frames with the current model.\n\n` +
                `Do you want to adjust max frames to ${affordableFrames} and continue?`
            );
            
            if (proceed) {
                document.getElementById('max-frames-input').value = Math.max(1, affordableFrames);
                updateCostEstimate();
            } else {
                return;
            }
        }
    }
    
    const params = {
        video_path: videoPath,
        provider_type: providerType,
        provider_name: providerName,
        provider_config: providerType === 'ollama' 
            ? { url: state.providers[providerName].url }
            : { api_key: state.openRouterKey },
        model: modelId,
        priority: parseInt(document.getElementById('priority-input').value) || 0,
        temperature: parseFloat(document.getElementById('temperature-input').value) || 0.0,
        duration: parseInt(document.getElementById('duration-input').value) || 0,
        max_frames: parseInt(document.getElementById('max-frames-input').value) || 10000,
        frames_per_minute: parseInt(document.getElementById('fpm-input').value) || 60,
        whisper_model: document.getElementById('whisper-select').value,
        language: document.getElementById('language-input').value,
        device: document.getElementById('device-select').value,
        keep_frames: document.getElementById('keep-frames-checkbox').checked,
        user_prompt: document.getElementById('prompt-input').value
    };
    
    state.socket.emit('start_analysis', params);
    
    // Show live analysis panel
    document.getElementById('live-analysis').classList.remove('hidden');
    document.getElementById('frames-log').innerHTML = '<div class="loading">Starting analysis...</div>';
    document.getElementById('live-llm-panel').style.display = 'block';
    
    showToast('Analysis job created');
}

function handleJobCreated(data) {
    showToast(`Job created: ${data.job_id}`);

    // Add job to state immediately so it appears in UI
    const newJob = {
        job_id: data.job_id,
        status: 'queued',
        provider_type: state.selectedProviderType || 'ollama',
        provider_name: state.selectedProvider || '',
        model_id: state.selectedModel || '',
        progress: 0,
        current_frame: 0,
        total_frames: 0,
        vram_required: 0,
        vram_gb: 0,
        priority: 0,
        queue_position: 0
    };
    state.jobs = [newJob, ...state.jobs];
    renderJobs();

    // Also refresh from server to get accurate data
    setTimeout(loadJobs, 500);

    // Subscribe to job updates
    state.socket.emit('subscribe_job', { job_id: data.job_id });
    state.currentJob = data.job_id;

    // Persist to localStorage for reconnect
    localStorage.setItem('va_current_job', data.job_id);
}

function handleJobStatus(data) {
    updateJobCard(data);
}

function handleJobComplete(data) {
    // Save whether this was the current job BEFORE clearing it
    const wasCurrentJob = data.job_id === state.currentJob;

    showToast(`Job ${data.job_id} ${data.success ? 'completed' : 'failed'}!`, data.success ? 'success' : 'error');

    // Clear current job from storage if this was the tracked job
    if (wasCurrentJob) {
        localStorage.removeItem('va_current_job');
        state.currentJob = null;
    }

    if (data.success && Notification.permission === 'granted') {
        new Notification('Video Analysis Complete', {
            body: `Job ${data.job_id} has finished`,
            icon: '🎬'
        });
    }

    // Load final results into live panels if this is the current job
    if (data.success && wasCurrentJob) {
        fetch(`/api/jobs/${data.job_id}/results`)
            .then(r => r.json())
            .then(results => {
                if (results.transcript?.text) {
                    handleJobTranscript({ transcript: results.transcript.text });
                }
                const descObj = results.video_description;
                const descText = typeof descObj === 'string'
                    ? descObj
                    : (descObj?.response || descObj?.text || '');
                if (descText) {
                    handleJobDescription({ description: descText });
                }
                
                // Store results in state for LLM chat
                state.currentJobResults = results;
                document.getElementById('live-llm-panel').style.display = 'block';
            })
            .catch(() => {});
    }
    
    loadJobs();
    loadStoredResults();
}

function handleFrameAnalysis(data) {
    // Show live analysis panel if hidden
    const liveAnalysis = document.getElementById('live-analysis');
    if (liveAnalysis && liveAnalysis.classList.contains('hidden')) {
        liveAnalysis.classList.remove('hidden');
    }

    const log = document.getElementById('frames-log');
    if (!log) return;

    // Remove loading message
    if (log.querySelector('.loading')) {
        log.innerHTML = '';
    }

    const entry = document.createElement('div');
    entry.className = 'frame-entry';
    entry.innerHTML = `
        <div class="frame-header">
            <span class="frame-number">Frame ${data.frame_number}/${data.total_frames}</span>
            <span class="frame-time">@${data.timestamp?.toFixed(2) || 0}s</span>
        </div>
        <div class="frame-text">${data.analysis}</div>
    `;

    log.insertBefore(entry, log.firstChild);

    // Keep only last 50 entries
    while (log.children.length > 50) {
        log.removeChild(log.lastChild);
    }
}

function handleJobTranscript(data) {
    const panel = document.getElementById('transcript-panel');
    if (panel) {
        panel.querySelector('.panel-content').textContent = data.transcript || '(empty)';
        document.getElementById('live-analysis').classList.remove('hidden');
    }
}

function handleJobDescription(data) {
    const panel = document.getElementById('description-panel');
    if (panel) {
        panel.querySelector('.panel-content').textContent = data.description || '(empty)';
        document.getElementById('live-analysis').classList.remove('hidden');
    }
}

function handleVRAMEvent(data) {
    loadJobs();
}

// ========================================
// Jobs List
// ========================================

async function loadJobs() {
    try {
        const response = await fetch('/api/jobs');
        state.jobs = await response.json();
        renderJobs();
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

function renderJobs() {
    const container = document.getElementById('jobs-list');
    
    if (state.jobs.length === 0) {
        container.innerHTML = '<div class="empty-state">No jobs yet. Upload a video and start an analysis.</div>';
        return;
    }
    
    container.innerHTML = state.jobs.map(job => `
        <div class="job-card ${job.status}" data-job-id="${job.job_id}">
            <div class="job-header">
                <span class="job-id">${job.job_id}</span>
                <span class="job-status ${job.status}">${job.status.toUpperCase()}</span>
            </div>
            <div class="job-meta">
                <span>${job.provider_name} • ${job.model_id}</span>
                <span>${formatBytes(job.vram_required) || 'Cloud'}</span>
            </div>
            ${job.status === 'running' || job.status === 'queued' ? `
                <div class="job-progress">
                    <div class="job-progress-bar">
                        <div class="job-progress-fill" style="width: ${job.progress || 0}%"></div>
                    </div>
                    <div class="job-progress-text">
                        <span>${job.stage || 'processing...'}</span>
                        <span>${job.progress || 0}%</span>
                    </div>
                </div>
                <div class="job-stats">
                    <span class="job-stat">Frame ${job.current_frame || 0}/${job.total_frames || '?'}</span>
                    ${job.queue_position > 0 ? `<span class="job-stat">Queue #${job.queue_position}</span>` : ''}
                </div>
            ` : ''}
            ${job.status === 'queued' ? `
                <div class="job-stats">
                    <span class="job-stat">Queue position: ${job.queue_position}</span>
                    <span class="job-stat">VRAM needed: ${job.vram_gb} GB</span>
                </div>
            ` : ''}
            <div class="job-actions">
                ${job.status === 'running' || job.status === 'queued' ? `
                    <button class="btn small danger" onclick="cancelJob('${job.job_id}')">Cancel</button>
                ` : ''}
                ${job.status === 'completed' ? `
                    <button class="btn small" onclick="viewResults('${job.job_id}')">View Results</button>
                    <button class="btn small" onclick="downloadResults('${job.job_id}')">Download</button>
                ` : ''}
            </div>
        </div>
    `).join('');
}

function updateJobCard(data) {
    const card = document.querySelector(`.job-card[data-job-id="${data.job_id}"]`);
    if (card) {
        const progressFill = card.querySelector('.job-progress-fill');
        if (progressFill) {
            progressFill.style.width = `${data.progress || 0}%`;
        }
        
        const progressText = card.querySelector('.job-progress-text span:last-child');
        if (progressText) {
            progressText.textContent = `${data.progress || 0}%`;
        }
        
        const stageText = card.querySelector('.job-progress-text span:first-child');
        if (stageText) {
            stageText.textContent = data.stage || 'processing...';
        }
        
        // Update frame counter
        const frameStat = card.querySelector('.job-stat');
        if (frameStat && data.current_frame !== undefined) {
            frameStat.textContent = `Frame ${data.current_frame}/${data.total_frames || '?'}`;
        }
    }
}

async function cancelJob(jobId) {
    if (!confirm(`Cancel job ${jobId}?`)) return;
    
    try {
        const response = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('Job cancelled');
            loadJobs();
        }
    } catch (error) {
        showToast('Failed to cancel job', 'error');
    }
}

async function viewResults(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/results`);
        const results = await response.json();
        
        const modal = document.getElementById('job-modal');
        const content = document.getElementById('job-detail-content');
        const title = document.getElementById('modal-title');
        
        title.textContent = `Job ${jobId} Results`;
        
        const descObj = results.video_description;
        const descText = typeof descObj === 'string'
            ? descObj
            : (descObj?.response || descObj?.text || JSON.stringify(descObj, null, 2) || 'No description');

        content.innerHTML = `
            <div class="results-detail-content">
                <h3>Transcript</h3>
                <pre style="white-space:pre-wrap;max-height:200px;overflow-y:auto">${results.transcript?.text || 'No transcript'}</pre>
                
                <h3>Video Description</h3>
                <pre style="white-space:pre-wrap;max-height:300px;overflow-y:auto">${descText}</pre>
                
                <h3>Frame Analyses (${results.frame_analyses?.length || 0})</h3>
                <div style="max-height:400px;overflow-y:auto" id="frame-analyses-list">
                ${results.frame_analyses?.map((f, i) => `
                    <div class="frame-result" style="margin-bottom:0.75rem;padding:0.5rem;background:var(--bg-tertiary);border-radius:4px">
                        <strong>Frame ${i+1}:</strong> ${formatFrameAnalysis(f.response || f.analysis || '', 300)}
                    </div>
                `).join('') || 'No analyses'}
                </div>
                
                <div id="modal-llm-panel" style="margin-top: 2rem;">
                    <h3>Send to LLM</h3>
                    <div class="llm-chat-controls">
                        <div class="form-row">
                            <div class="form-group">
                                <label>Provider</label>
                                <select id="modal-chat-provider-select" onchange="handleChatProviderChange('modal')">
                                    <option value="">Select provider...</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Model</label>
                                <select id="modal-chat-model-select" disabled>
                                    <option value="">Select provider first...</option>
                                </select>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Content to send</label>
                            <select id="modal-chat-content-select">
                                <option value="transcript">Transcript</option>
                                <option value="description">Video Description</option>
                                <option value="both">Transcript + Description</option>
                                <option value="frames">All Frame Analyses</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Prompt / Instruction</label>
                            <textarea id="modal-chat-prompt" rows="3" placeholder="e.g. Summarize this into 5 bullet points..."></textarea>
                        </div>
                        <button class="btn primary" onclick="sendToLLM('modal', '${jobId}')">Send to LLM</button>
                    </div>
                    <div id="modal-llm-response" class="llm-response hidden">
                        <div class="llm-response-header">
                            <span>Response</span>
                            <button class="link-btn" onclick="document.getElementById('modal-llm-response').classList.add('hidden')">✕</button>
                        </div>
                        <div id="modal-llm-text" class="llm-response-text"></div>
                    </div>
                </div>
            </div>
        `;
        
        // Init chat provider select in modal
        initChatProviderSelect('modal');
        
        modal.classList.remove('hidden');
    } catch (error) {
        showToast('Failed to load results', 'error');
    }
}

function downloadResults(jobId) {
    window.open(`/api/jobs/${jobId}/results`, '_blank');
}

// ========================================
// Stored Results Browser
// ========================================

async function loadStoredResults() {
    try {
        const response = await fetch('/api/results');
        state.storedResults = await response.json();
        renderStoredResults();
    } catch (error) {
        console.error('Failed to load stored results:', error);
    }
}

function renderStoredResults() {
    const container = document.getElementById('results-list');
    
    if (!state.storedResults.length) {
        container.innerHTML = '<div class="empty-state">No stored results yet</div>';
        return;
    }
    
    container.innerHTML = state.storedResults.map(result => `
        <div class="result-item ${result.job_id === state.selectedResult ? 'active' : ''}" 
             onclick="selectStoredResult('${result.job_id}')">
            <div class="result-title">${result.video_path?.split('/').pop() || result.job_id}</div>
            <div class="result-meta">
                <span>${result.provider}</span>
                <span>${new Date(result.created_at * 1000).toLocaleDateString()}</span>
            </div>
            <div class="result-preview">${result.desc_preview || ''}</div>
        </div>
    `).join('');
}

async function selectStoredResult(jobId) {
    state.selectedResult = jobId;
    renderStoredResults();
    
    try {
        const response = await fetch(`/api/jobs/${jobId}/results`);
        const results = await response.json();
        
        const container = document.getElementById('results-detail');
        const descObj = results.video_description;
        const descText = typeof descObj === 'string'
            ? descObj
            : (descObj?.response || descObj?.text || JSON.stringify(descObj, null, 2) || 'No description');
        
        container.innerHTML = `
            <div class="results-detail-content">
                <h2>${jobId}</h2>
                <p><strong>Video:</strong> ${results.metadata?.video_path?.split('/').pop() || 'Unknown'}</p>
                <p><strong>Model:</strong> ${results.metadata?.model || 'Unknown'}</p>
                <p><strong>Provider:</strong> ${results.metadata?.provider || 'Unknown'}</p>
                
                <h3>Transcript</h3>
                <pre>${results.transcript?.text || 'No transcript'}</pre>
                
                <h3>Video Description</h3>
                <pre>${descText}</pre>
                
                <h3>Frame Analyses (${results.frame_analyses?.length || 0})</h3>
                <div style="max-height:400px;overflow-y:auto" id="results-frame-analyses">
                ${results.frame_analyses?.map((f, i) => `
                    <div class="frame-result" style="margin-bottom:0.75rem;padding:0.5rem;background:var(--bg-tertiary);border-radius:4px">
                        <strong>Frame ${i+1}:</strong> ${formatFrameAnalysis(f.response || f.analysis || '', 300)}
                    </div>
                `).join('') || 'No analyses'}
                </div>
                
                <div class="llm-chat-panel" style="margin-top: 2rem;">
                    <h3>Send to LLM</h3>
                    <div class="llm-chat-controls">
                        <div class="form-row">
                            <div class="form-group">
                                <label>Provider</label>
                                <select id="results-chat-provider-select" onchange="handleChatProviderChange('results')">
                                    <option value="">Select provider...</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Model</label>
                                <select id="results-chat-model-select" disabled>
                                    <option value="">Select provider first...</option>
                                </select>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Content to send</label>
                            <select id="results-chat-content-select">
                                <option value="transcript">Transcript</option>
                                <option value="description">Video Description</option>
                                <option value="both">Transcript + Description</option>
                                <option value="frames">All Frame Analyses</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Prompt / Instruction</label>
                            <textarea id="results-chat-prompt" rows="3" placeholder="e.g. Summarize this into 5 bullet points..."></textarea>
                        </div>
                        <button class="btn primary" onclick="sendToLLM('results', '${jobId}')">Send to LLM</button>
                    </div>
                    <div id="results-llm-response" class="llm-response hidden">
                        <div class="llm-response-header">
                            <span>Response</span>
                            <button class="link-btn" onclick="document.getElementById('results-llm-response').classList.add('hidden')">✕</button>
                        </div>
                        <div id="results-llm-text" class="llm-response-text"></div>
                    </div>
                </div>
            </div>
        `;
        
        initChatProviderSelect('results');
    } catch (error) {
        showToast('Failed to load result details', 'error');
    }
}

// ========================================
// LLM Chat Functions
// ========================================

function initChatProviderSelect(context = 'live') {
    const selectId = context === 'modal' ? 'modal-chat-provider-select' :
                     context === 'results' ? 'results-chat-provider-select' : 'chat-provider-select';
    
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = '<option value="">Select provider...</option>' +
        '<optgroup label="Ollama">' +
        Object.values(state.providers)
            .filter(p => p.type === 'ollama')
            .map(p => `<option value="ollama" data-url="${p.url}">${p.name} (${p.status})</option>`)
            .join('') +
        '</optgroup>' +
        '<optgroup label="Cloud">' +
        '<option value="openrouter">OpenRouter</option>' +
        '</optgroup>';
}

async function handleChatProviderChange(context = 'live') {
    const selectId = context === 'modal' ? 'modal-chat-provider-select' :
                     context === 'results' ? 'results-chat-provider-select' : 'chat-provider-select';
    const modelSelectId = context === 'modal' ? 'modal-chat-model-select' :
                         context === 'results' ? 'results-chat-model-select' : 'chat-model-select';
    
    const providerSelect = document.getElementById(selectId);
    const modelSelect = document.getElementById(modelSelectId);
    const providerName = providerSelect.value;
    
    modelSelect.innerHTML = '<option value="">Loading models...</option>';
    modelSelect.disabled = true;
    
    if (providerName === 'openrouter') {
        // For OpenRouter in chat, use the same API key as analysis
        if (!state.openRouterKey) {
            promptForOpenRouterKey();
            if (!state.openRouterKey) {
                providerSelect.value = '';
                return;
            }
        }
        
        try {
            const response = await fetch(`/api/providers/openrouter/models?api_key=${encodeURIComponent(state.openRouterKey)}`);
            const data = await response.json();
            
            if (data.models) {
                modelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
                modelSelect.disabled = false;
            }
        } catch (error) {
            console.error('Failed to load OpenRouter models for chat:', error);
            modelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }
        
    } else if (providerName === 'ollama') {
        // Use the first Ollama provider URL
        const ollamaProvider = Object.values(state.providers).find(p => p.type === 'ollama');
        if (ollamaProvider?.status === 'online') {
            try {
                const response = await fetch(`/api/providers/ollama/models?server=${encodeURIComponent(ollamaProvider.url)}`);
                const data = await response.json();
                
                if (data.models) {
                    modelSelect.innerHTML = '<option value="">Select model...</option>' +
                        data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
                    modelSelect.disabled = false;
                }
            } catch (error) {
                console.error('Failed to load Ollama models for chat:', error);
                modelSelect.innerHTML = '<option value="">Failed to load models</option>';
            }
        }
    }
}

async function sendToLLM(context, jobId = null) {
    const providerSelectId = context === 'modal' ? 'modal-chat-provider-select' :
                            context === 'results' ? 'results-chat-provider-select' : 'chat-provider-select';
    const modelSelectId = context === 'modal' ? 'modal-chat-model-select' :
                         context === 'results' ? 'results-chat-model-select' : 'chat-model-select';
    const contentSelectId = context === 'modal' ? 'modal-chat-content-select' :
                           context === 'results' ? 'results-chat-content-select' : 'chat-content-select';
    const promptTextareaId = context === 'modal' ? 'modal-chat-prompt' :
                            context === 'results' ? 'results-chat-prompt' : 'chat-prompt';
    const responseDivId = context === 'modal' ? 'modal-llm-response' :
                         context === 'results' ? 'results-llm-response' : 'live-llm-response';
    const responseTextId = context === 'modal' ? 'modal-llm-text' :
                          context === 'results' ? 'results-llm-text' : 'live-llm-text';
    
    const providerSelect = document.getElementById(providerSelectId);
    const modelSelect = document.getElementById(modelSelectId);
    const contentSelect = document.getElementById(contentSelectId);
    const promptTextarea = document.getElementById(promptTextareaId);
    const responseDiv = document.getElementById(responseDivId);
    const responseText = document.getElementById(responseTextId);
    
    const providerType = providerSelect.value;
    const modelId = modelSelect.value;
    const prompt = promptTextarea.value;
    const contentType = contentSelect.value;
    
    if (!providerType || !modelId || !prompt) {
        showToast('Please select provider, model, and enter a prompt', 'error');
        return;
    }
    
    // Get content to send
    let content = '';
    if (jobId) {
        // Load results from specific job
        try {
            const response = await fetch(`/api/jobs/${jobId}/results`);
            const results = await response.json();
            content = formatContentForLLM(results, contentType);
        } catch (error) {
            showToast('Failed to load job results', 'error');
            return;
        }
    } else if (context === 'live' && state.currentJobResults) {
        // Use current job results
        content = formatContentForLLM(state.currentJobResults, contentType);
    } else {
        showToast('No content available to send', 'error');
        return;
    }    
    if (!content) {
        showToast(`Selected content type (${contentType}) not available`, 'error');
        return;
    }    
    // Prepare request
    const requestData = {
        provider_type: providerType,
        model: modelId,
        prompt: prompt,
        content: content,
    };    
    if (providerType === 'ollama') {
        const ollamaProvider = Object.values(state.providers).find(p => p.type === 'ollama');
        if (ollamaProvider) {
            requestData.ollama_url = ollamaProvider.url;
        }
    } else if (providerType === 'openrouter') {
        requestData.api_key = state.openRouterKey;
    }    
    // Show loading
    responseText.textContent = 'Submitting to LLM queue...';
    responseDiv.classList.remove('hidden');
    responseText.classList.add('loading-state');
    
    try {
        // Submit to queue and get job ID
        const response = await fetch('/api/llm/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });        
        const result = await response.json();
        
        if (result.job_id) {
            responseText.textContent = `Chat job submitted (ID: ${result.job_id}). Queue position: ${result.queue_position || 'pending'}.`;
            
            // Start polling for job status
            pollChatJobStatus(result.job_id, responseText, responseDiv);
            
            // Add job tracking button if modal context

            if (context === 'modal') {
                const modalBody = document.querySelector('.modal-body');
                const jobButton = document.createElement('button');
                jobButton.className = 'btn small secondary';
                jobButton.textContent = `Track Job ${result.job_id}`;
                jobButton.onclick = () => {
                    openJobStatusModal(result.job_id, 'chat');
                };
                responseDiv.appendChild(jobButton);
            }
        } else if (result.error) {
            responseText.textContent = `Error: ${result.error}`;
            responseText.classList.remove('loading-state');
        } else {
            responseText.textContent = 'Unknown error occurred';
            responseText.classList.remove('loading-state');
        }
    } catch (error) {
        responseText.textContent = `Network error: ${error.message}`;
        responseText.classList.remove('loading-state');
    }
}

function formatContentForLLM(results, contentType) {
    if (contentType === 'transcript') {
        return results.transcript?.text || '';
    } else if (contentType === 'description') {
        const descObj = results.video_description;
        return typeof descObj === 'string' ? descObj : 
               (descObj?.response || descObj?.text || JSON.stringify(descObj, null, 2) || '');
    } else if (contentType === 'both') {
        const transcript = results.transcript?.text || '';
        const descObj = results.video_description;
        const description = typeof descObj === 'string' ? descObj : 
                           (descObj?.response || descObj?.text || JSON.stringify(descObj, null, 2) || '');
        return `TRANSCRIPT:\n${transcript}\n\nVIDEO DESCRIPTION:\n${description}`;
    } else if (contentType === 'frames') {
        const frames = results.frame_analyses || [];
        return frames.map((f, i) => `Frame ${i}: ${f.response || f.analysis || ''}`).join('\n');
    }
    return '';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatFrameAnalysis(text, maxLength = 300) {
    if (!text) return '';
    
    const escaped = escapeHtml(text);
    if (text.length <= maxLength) {
        return escaped;
    }
    
    const short = escaped.substring(0, maxLength);
    const full = escaped;
    const id = 'frame_' + Math.random().toString(36).substr(2, 9);
    
    return `
        <span id="${id}_short">${short}... <a href="javascript:void(0)" onclick="toggleFrameAnalysis('${id}', true)" style="color:var(--accent-primary);font-size:0.85rem;">Show More</a></span>
        <span id="${id}_full" style="display:none;">${full} <a href="javascript:void(0)" onclick="toggleFrameAnalysis('${id}', false)" style="color:var(--accent-primary);font-size:0.85rem;">Show Less</a></span>
    `;
}

function toggleFrameAnalysis(id, showFull) {
    const shortEl = document.getElementById(id + '_short');
    const fullEl = document.getElementById(id + '_full');
    
    if (shortEl && fullEl) {
        if (showFull) {
            shortEl.style.display = 'none';
            fullEl.style.display = 'inline';
        } else {
            shortEl.style.display = 'inline';
            fullEl.style.display = 'none';
        }
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatFrameAnalysis(text, maxLength = 300) {
    if (!text) return '';
    
    const escaped = escapeHtml(text);
    if (text.length <= maxLength) {
        return escaped;
    }
    
    const short = escaped.substring(0, maxLength);
    const full = escaped;
    const id = 'frame_' + Math.random().toString(36).substr(2, 9);
    
    return `
        <span id="${id}_short">${short}... <a href="javascript:void(0)" onclick="toggleFrameAnalysis('${id}', true)" style="color:var(--accent-primary);font-size:0.85rem;">Show More</a></span>
        <span id="${id}_full" style="display:none;">${full} <a href="javascript:void(0)" onclick="toggleFrameAnalysis('${id}', false)" style="color:var(--accent-primary);font-size:0.85rem;">Show Less</a></span>
    `;
}

function toggleFrameAnalysis(id, showFull) {
    const shortEl = document.getElementById(id + '_short');
    const fullEl = document.getElementById(id + '_full');
    
    if (shortEl && fullEl) {
        if (showFull) {
            shortEl.style.display = 'none';
            fullEl.style.display = 'inline';
        } else {
            shortEl.style.display = 'inline';
            fullEl.style.display = 'none';
        }
    }
}

// ========================================
// System Status
// ========================================

function handleSystemStatus(data) {
    if (data.type === 'nvidia_smi') {
        const payload = data.data || {};
        const gpus = payload.gpus || [];
        const text = payload.text || data.error || 'No data';

        document.getElementById('nvidia-output').textContent = text;

        // Render per-GPU VRAM bars
        const vramDisplay = document.getElementById('vram-display');
        if (gpus.length > 0) {
            vramDisplay.innerHTML = gpus.map(gpu => {
                const usedGb = (gpu.mem_used_mb / 1024).toFixed(1);
                const totalGb = (gpu.mem_total_mb / 1024).toFixed(1);
                const pct = Math.round(gpu.mem_used_mb * 100 / gpu.mem_total_mb);
                const utilPct = gpu.util_pct || 0;
                return `
                    <div class="gpu-card">
                        <div class="gpu-title">GPU ${gpu.index}: ${gpu.name}</div>
                        <div class="gpu-row">
                            <span>VRAM</span>
                            <div class="mini-bar"><div class="mini-fill" style="width:${pct}%"></div></div>
                            <span class="gpu-val">${usedGb} / ${totalGb} GB</span>
                        </div>
                        <div class="gpu-row">
                            <span>Util</span>
                            <div class="mini-bar"><div class="mini-fill util-fill" style="width:${utilPct}%"></div></div>
                            <span class="gpu-val">${utilPct}%</span>
                        </div>
                    </div>`;
            }).join('');
        } else if (data.error) {
            vramDisplay.innerHTML = `<div class="gpu-error">${data.error}</div>`;
        }

    } else if (data.type === 'ollama_ps') {
        const payload = data.data || {};
        const text = payload.text || data.error || 'No data';
        document.getElementById('ollama-output').textContent = text;
    }
}

function switchMonitorTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.monitor-pre').forEach(p => p.classList.remove('active'));
    
    document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`${tab}-output`).classList.add('active');
}

// ========================================
// Settings & Persistence
// ========================================

function saveSettings() {
    const settings = {
        temperature: document.getElementById('temperature-input').value,
        max_frames: document.getElementById('max-frames-input').value,
        frames_per_minute: document.getElementById('fpm-input').value,
        whisper_model: document.getElementById('whisper-select').value,
        language: document.getElementById('language-input').value,
        device: document.getElementById('device-select').value,
        keep_frames: document.getElementById('keep-frames-checkbox').checked
    };
    
    localStorage.setItem('va_settings', JSON.stringify(settings));
}

function restoreSettings() {
    if (state.settings) {
        Object.entries(state.settings).forEach(([key, value]) => {
            const el = document.getElementById(key.replace(/_/g, '-') + '-input') ||
                      document.getElementById(key.replace(/_/g, '-') + '-select');
            if (el) {
                if (el.type === 'checkbox') {
                    el.checked = value;
                } else {
                    el.value = value;
                }
            }
        });
    }
}

function toggleAdvancedOptions() {
    const panel = document.getElementById('advanced-options');
    const btn = document.getElementById('advanced-toggle-btn');
    
    panel.classList.toggle('hidden');
    btn.textContent = panel.classList.contains('hidden') ? 'Advanced Options ▼' : 'Advanced Options ▲';
}

// ========================================
// Notifications
// ========================================

function requestNotificationPermission() {
    if (!('Notification' in window)) {
        showToast('Notifications not supported', 'warning');
        return;
    }
    
    Notification.requestPermission().then(permission => {
        const btn = document.getElementById('notifications-btn');
        if (permission === 'granted') {
            btn.textContent = '🔔';
            btn.title = 'Notifications enabled';
            showToast('Notifications enabled');
        } else {
            btn.textContent = '🔕';
            btn.title = 'Notifications disabled';
        }
    });
}

// ========================================
// Utilities
// ========================================

function updateStartButton() {
    const video = document.getElementById('video-select').value;
    const provider = document.getElementById('provider-select').value;
    const model = document.getElementById('model-select').value;
    
    document.getElementById('start-btn').disabled = !(video && provider && model);
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    Object.assign(toast.style, {
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        padding: '1rem 1.5rem',
        background: type === 'error' ? 'var(--error)' : type === 'success' ? 'var(--success)' : 'var(--info)',
        color: 'white',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        zIndex: '10000',
        animation: 'slideInRight 0.3s ease'
    });
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function closeModal() {
    document.getElementById('job-modal').classList.add('hidden');
}

// Chat job polling
async function pollChatJobStatus(jobId, responseText, responseDiv) {
    const maxAttempts = 300; // 5 minutes at 1 second intervals
    let attempts = 0;
    
    const poll = async () => {
        attempts++;
        if (attempts > maxAttempts) {
            responseText.textContent = 'Polling timeout - job may still be processing';
            responseText.classList.remove('loading-state');
            return;
        }
        
        try {
            const response = await fetch(`/api/llm/chat/${jobId}`);
            const result = await response.json();
            
            if (result.status === 'completed') {
                responseText.textContent = result.result || 'No response from LLM';
                responseText.classList.remove('loading-state');
                return;
            } else if (result.status === 'failed') {
                responseText.textContent = `Failed: ${result.error || 'Unknown error'}`;
                responseText.classList.remove('loading-state');
                return;
            } else if (result.status === 'running') {
                responseText.textContent = `Processing... (Queue position: ${result.queue_position || 'running'})`;
                setTimeout(poll, 1000);
            } else if (result.status === 'queued') {
                responseText.textContent = `Queued... (Position: ${result.queue_position})`;
                setTimeout(poll, 2000);
            } else {
                responseText.textContent = `Status: ${result.status}`;
                setTimeout(poll, 2000);
            }
        } catch (error) {
            responseText.textContent = `Polling error: ${error.message}`;
            responseText.classList.remove('loading-state');
        }
    };
    
    poll();
}

function openJobStatusModal(jobId, jobType = 'chat') {
    // Create or show modal for job status
    const modal = document.getElementById('job-modal');
    const modalBody = document.querySelector('.modal-body');
    
    if (jobType === 'chat') {
        modal.querySelector('.modal-header h2').textContent = `Chat Job Status: ${jobId}`;
        
        // Create content for chat job status
        modalBody.innerHTML = `
            <div id="chat-job-status">
                <div class="loading">Loading job status...</div>
            </div>
            <div class="form-actions">
                <button class="btn" onclick="refreshChatJobStatus('${jobId}')">Refresh</button>
                <button class="btn danger" onclick="cancelChatJob('${jobId}')">Cancel Job</button>
                <button class="btn secondary" onclick="closeModal()">Close</button>
            </div>
        `;
        
        // Load initial status
        refreshChatJobStatus(jobId);
    }
    
    modal.classList.remove('hidden');
}

async function refreshChatJobStatus(jobId) {
    const statusDiv = document.getElementById('chat-job-status');
    if (!statusDiv) return;
    
    try {
        const response = await fetch(`/api/llm/chat/${jobId}`);
        const result = await response.json();
        
        let statusHtml = `
            <div class="job-status-card">
                <div class="job-status-header">
                    <h3>Chat Job: ${jobId}</h3>
                    <span class="job-status-badge ${result.status}">${result.status.toUpperCase()}</span>
                </div>
                <div class="job-status-details">
                    <p><strong>Provider:</strong> ${result.provider_type}</p>
                    <p><strong>Model:</strong> ${result.model_id}</p>
                    <p><strong>Queue Position:</strong> ${result.queue_position || 'N/A'}</p>
                    <p><strong>Created:</strong> ${new Date(result.created_at * 1000).toLocaleString()}</p>
        `;
        
        if (result.started_at) {
            statusHtml += `<p><strong>Started:</strong> ${new Date(result.started_at * 1000).toLocaleString()}</p>`;
        }
        
        if (result.completed_at) {
            statusHtml += `<p><strong>Completed:</strong> ${new Date(result.completed_at * 1000).toLocaleString()}</p>`;
        }
        
        if (result.error) {
            statusHtml += `<p><strong>Error:</strong> ${result.error}</p>`;
        }
        
        if (result.result) {
            statusHtml += `
                <div class="chat-result">
                    <h4>Response:</h4>
                    <pre style="white-space:pre-wrap;max-height:300px;overflow-y:auto">${result.result}</pre>
                </div>
            `;
        }
        
        statusHtml += `</div></div>`;
        statusDiv.innerHTML = statusHtml;
        
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Failed to load job status: ${error.message}</div>`;
    }
}

async function cancelChatJob(jobId) {
    if (!confirm('Cancel this chat job?')) return;
    
    try {
        const response = await fetch(`/api/llm/chat/${jobId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        if (result.success) {
            showToast('Chat job cancelled');
            refreshChatJobStatus(jobId);
        } else {
            showToast('Failed to cancel job: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Cancel failed: ' + error.message, 'error');
    }
}

// Add animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOutRight {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    
    .loading-state {
        color: var(--text-secondary);
        font-style: italic;
    }
    
    .job-status-card {
        background: var(--bg-card);
        border-radius: var(--border-radius);
        padding: var(--spacing-md);
        margin-bottom: var(--spacing-md);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .job-status-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: var(--spacing-md);
    }
    
    .job-status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    
    .job-status-badge.completed {
        background: rgba(46, 160, 67, 0.1);
        color: var(--success);
    }
    
    .job-status-badge.running {
        background: rgba(88, 166, 255, 0.1);
        color: var(--info);
    }
    
    .job-status-badge.queued {
        background: rgba(210, 153, 34, 0.1);
        color: var(--warning);
    }
    
    .job-status-badge.failed {
        background: rgba(248, 81, 73, 0.1);
        color: var(--error);
    }
    
    .chat-result {
        margin-top: var(--spacing-md);
        padding-top: var(--spacing-md);
        border-top: 1px solid rgba(255, 255, 255, 0.1);
    }
`;
document.head.appendChild(style);