// Job management: creation, rendering, cancellation, results
async function loadJobs() {
    try {
        const response = await fetch('/api/jobs');
        const jobs = await response.json();
        renderJobsList(jobs);
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

function renderJobsList(jobs) {
    const container = document.getElementById('jobs-list');
    if (!container) return;

    if (jobs.length === 0) {
        container.innerHTML = '<div class="empty-state">No jobs yet. Upload a video and start an analysis.</div>';
        return;
    }

    container.innerHTML = jobs.map(job => {
        const statusClass = job.status || 'queued';
        const progress = job.progress || 0;
        const model = job.model_id || job.model || 'unknown';
        const video = job.video_path ? job.video_path.split('/').pop() : '';

        return `
            <div class="job-card ${statusClass}" data-job-id="${job.job_id}">
                <div class="job-header">
                    <span class="job-id">${job.job_id}</span>
                    <span class="job-status ${statusClass}">${statusClass.toUpperCase()}</span>
                </div>
                <div class="job-meta">
                    <span>Model: ${model}</span>
                    <span>Video: ${video}</span>
                </div>
                <div class="job-progress">
                    <div class="job-progress-bar">
                        <div class="job-progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <div class="job-progress-text">
                        <span>${job.stage || 'queued'}</span>
                        <span>${progress}%</span>
                    </div>
                </div>
                <div class="job-actions">
                    <button class="btn small secondary" onclick="viewJobDetails('${job.job_id}')">Details</button>
                    ${statusClass === 'running' || statusClass === 'queued' ? `<button class="btn small danger" onclick="cancelJob('${job.job_id}')">Cancel</button>` : ''}
                    ${statusClass === 'completed' ? `<button class="btn small primary" onclick="viewJobResults('${job.job_id}')">View Results</button>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function handleJobCreated(data) {
    if (state.debug) console.log('[DEBUG:JOBS] handleJobCreated', data);
    state.currentJob = data.job_id;
    subscribeToJob(data.job_id);
    loadJobs();
}

function handleJobUpdate(data) {
    if (state.debug) console.log('[DEBUG:JOBS] handleJobUpdate', data);
    updateJobCard(data);
}

function handleJobStatus(data) {
    if (state.debug) console.log('[DEBUG:JOBS] handleJobStatus stage=' + data.stage + ' progress=' + data.progress);
    updateJobCard(data);
    if (data.stage === 'analyzing_frames') {
        updateLiveAnalysis(data);
    }
}

function handleFrameAnalysis(data) {
    appendFrameLog(data);
}

function handleJobTranscript(data) {
    const panel = document.getElementById('transcript-panel');
    if (panel) {
        panel.querySelector('.panel-content').textContent = data.transcript;
    }
}

function handleJobDescription(data) {
    const panel = document.getElementById('description-panel');
    if (panel) {
        panel.querySelector('.panel-content').textContent = data.description;
    }
}

function handleJobComplete(data) {
    if (state.debug) console.log('[DEBUG:JOBS] handleJobComplete', data);
    if (data.success) {
        showToast(`Job ${data.job_id} completed`);
        loadStoredResults();
    } else {
        showToast(`Job ${data.job_id} failed`, 'error');
    }
    loadJobs();
}

function updateJobCard(data) {
    const card = document.querySelector(`[data-job-id="${data.job_id}"]`);
    if (!card) {
        if (state.debug) console.log('[DEBUG:JOBS] updateJobCard: no card found for job', data.job_id);
        return;
    }

    const progressFill = card.querySelector('.job-progress-fill');
    const progressText = card.querySelector('.job-progress-text');
    const statusBadge = card.querySelector('.job-status');

    if (progressFill) progressFill.style.width = `${data.progress || 0}%`;
    if (progressText) {
        progressText.innerHTML = `<span>${data.stage || 'queued'}</span><span>${data.progress || 0}%</span>`;
    }
    if (statusBadge && data.status) {
        statusBadge.className = `job-status ${data.status}`;
        statusBadge.textContent = data.status.toUpperCase();
    }
}

function updateLiveAnalysis(data) {
    // Show live analysis section if hidden
    const liveSection = document.getElementById('live-analysis');
    if (liveSection) liveSection.classList.remove('hidden');
}

function appendFrameLog(data) {
    const log = document.getElementById('frames-log');
    if (!log) {
        if (state.debug) console.log('[DEBUG:JOBS] appendFrameLog: no frames-log element');
        return;
    }

    const entry = document.createElement('div');
    entry.className = 'frame-entry';
    entry.innerHTML = `
        <div class="frame-header">
            <span class="frame-number">Frame ${data.frame_number || data.frame}</span>
        </div>
        <div class="frame-text">${formatFrameAnalysis(data.analysis || data.response || '')}</div>
    `;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

async function viewJobDetails(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();

        const modal = document.getElementById('job-modal');
        const modalBody = document.getElementById('job-detail-content');
        document.getElementById('modal-title').textContent = `Job Details: ${jobId}`;

        modalBody.innerHTML = `
            <div class="job-status-card">
                <div class="job-status-header">
                    <h3>Job: ${jobId}</h3>
                    <span class="job-status-badge ${job.status}">${(job.status || 'unknown').toUpperCase()}</span>
                </div>
                <div class="job-status-details">
                    <p><strong>Model:</strong> ${job.model_id || job.model || 'N/A'}</p>
                    <p><strong>Provider:</strong> ${job.provider_type || 'N/A'}</p>
                    <p><strong>Stage:</strong> ${job.stage || 'N/A'}</p>
                    <p><strong>Progress:</strong> ${job.progress || 0}%</p>
                    <p><strong>Priority:</strong> ${job.priority || 0}</p>
                    <p><strong>VRAM Required:</strong> ${job.vram_required ? (job.vram_required / 1024 / 1024 / 1024).toFixed(1) + ' GB' : 'N/A'}</p>
                </div>
            </div>
            <div class="form-actions">
                <button class="btn" onclick="loadJobs(); closeModal()">Close</button>
            </div>
        `;

        modal.classList.remove('hidden');
    } catch (error) {
        showToast('Failed to load job details', 'error');
    }
}

async function viewJobResults(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/results`);
        const results = await response.json();
        state.currentJobResults = results;

        // Switch to results tab and show details
        switchMainTab('results');
        loadStoredResults();
    } catch (error) {
        showToast('Failed to load job results', 'error');
    }
}

async function cancelJob(jobId) {
    if (!confirm(`Cancel job ${jobId}?`)) return;

    try {
        const response = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
        const result = await response.json();

        if (result.success) {
            showToast(`Job ${jobId} cancelled`);
            loadJobs();
        } else {
            showToast(result.error?.message || 'Failed to cancel job', 'error');
        }
    } catch (error) {
        showToast('Cancel failed: ' + error.message, 'error');
    }
}

function switchMainTab(tab) {
    document.querySelectorAll('.main-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.main-tab-content').forEach(c => c.classList.add('hidden'));

    document.querySelector(`.main-tab-btn[data-tab="${tab}"]`)?.classList.add('active');
    document.getElementById(`tab-${tab}`)?.classList.remove('hidden');
}
