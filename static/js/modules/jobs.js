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
        const currentFrame = job.current_frame || 0;
        const totalFrames = job.total_frames || 0;
        const frameCountHtml = (currentFrame > 0 && totalFrames > 0)
            ? `<div class="job-frame-count">Frame ${currentFrame} / ${totalFrames}</div>`
            : '';

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
                    ${frameCountHtml}
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
    // Keep analysisVideoName in sync so thumbnail URLs are correct on reconnect/replay
    if (data.video_path && !state.analysisVideoName) {
        state.analysisVideoName = data.video_path.split('/').pop();
    }
    if (data.stage === 'analyzing_frames') {
        updateLiveAnalysis(data);
    }
}

function handleFrameAnalysis(data) {
    const liveSection = document.getElementById('live-analysis');
    if (liveSection) liveSection.classList.remove('hidden');
    appendFrameLog(data);
}

function handleFrameSynthesis(data) {
    const combinedSection = document.getElementById('combined-analysis');
    if (combinedSection) combinedSection.classList.remove('hidden');
    appendCombinedLog(data);
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

    const currentFrame = data.current_frame || 0;
    const totalFrames = data.total_frames || 0;
    let frameCountEl = card.querySelector('.job-frame-count');
    if (currentFrame > 0 && totalFrames > 0) {
        if (!frameCountEl) {
            frameCountEl = document.createElement('div');
            frameCountEl.className = 'job-frame-count';
            const progressBar = card.querySelector('.job-progress');
            if (progressBar) progressBar.appendChild(frameCountEl);
        }
        frameCountEl.textContent = `Frame ${currentFrame} / ${totalFrames}`;
    } else if (frameCountEl) {
        frameCountEl.remove();
    }

    if (data.status) {
        if (statusBadge) {
            statusBadge.className = `job-status ${data.status}`;
            statusBadge.textContent = data.status.toUpperCase();
        }
        card.className = `job-card ${data.status}`;
        const cancelBtn = card.querySelector('.btn.danger');
        if (cancelBtn) {
            cancelBtn.style.display = (data.status === 'running' || data.status === 'queued') ? '' : 'none';
        }
    }
}

function updateLiveAnalysis(data) {
    // Show live analysis section if hidden
    const liveSection = document.getElementById('live-analysis');
    if (liveSection) liveSection.classList.remove('hidden');
}

function formatVideoTimestamp(seconds) {
    if (seconds === null || seconds === undefined) return null;
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) {
        return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    }
    return `${m}:${String(sec).padStart(2, '0')}`;
}

function appendFrameLog(data) {
    const log = document.getElementById('frames-log');
    if (!log) {
        if (state.debug) console.log('[DEBUG:JOBS] appendFrameLog: no frames-log element');
        return;
    }

    const frameNum = data.frame_number || data.frame;
    const origFrame = data.original_frame;
    const ts = formatVideoTimestamp(data.video_ts ?? data.timestamp);
    const origTs = data.original_ts;

    const origHtml = (origFrame && origFrame !== frameNum)
        ? `<span class="frame-original">(orig: ${origFrame}${origTs !== undefined ? ' @ ' + formatVideoTimestamp(origTs) : ''})</span>`
        : '';
    const tsHtml = ts !== null ? `<span class="frame-timestamp">${ts}</span>` : '';

    // Prefer the name captured at analysis-start time; fall back to frame browser
    // or currentVideo (extracting just the filename to avoid path-encoded 404s).
    const rawVideo = state.analysisVideoName || state.frameBrowser?.videoName || state.currentVideo || '';
    const videoName = rawVideo.split('/').pop();
    const thumbUrl = videoName ? `/api/videos/${encodeURIComponent(videoName)}/frames/${frameNum}/thumb` : '';
    const thumbHtml = thumbUrl
        ? `<div class="frame-thumbnail"><img src="${thumbUrl}" alt="Frame ${frameNum}" loading="lazy"></div>`
        : '';

    const transcriptCtx = data.transcript_context || '';
    const transcriptHtml = transcriptCtx
        ? `<div class="frame-transcript-context" onclick="this.classList.toggle('expanded')">${escapeHtml(transcriptCtx)}</div>`
        : '';

    const entry = document.createElement('div');
    entry.className = 'frame-entry';
    entry.innerHTML = `
        ${thumbHtml}
        <div class="frame-content">
            <div class="frame-header">
                <span class="frame-number">Frame ${frameNum}</span>${origHtml}${tsHtml}
            </div>
            <div class="frame-text">${formatFrameAnalysis(data.analysis || data.response || '')}</div>
            ${transcriptHtml}
        </div>
    `;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function appendCombinedLog(data) {
    const log = document.getElementById('combined-log');
    if (!log) {
        if (state.debug) console.log('[DEBUG:JOBS] appendCombinedLog: no combined-log element');
        return;
    }

    const frameNum = data.frame_number || data.frame;
    const origFrame = data.original_frame;
    const ts = formatVideoTimestamp(data.video_ts ?? data.timestamp);
    const origTs = data.original_ts;

    const origHtml = (origFrame && origFrame !== frameNum)
        ? `<span class="frame-original">(orig: ${origFrame}${origTs !== undefined ? ' @ ' + formatVideoTimestamp(origTs) : ''})</span>`
        : '';
    const tsHtml = ts !== null ? `<span class="frame-timestamp">${ts}</span>` : '';

    // Prefer the name captured at analysis-start time; fall back to frame browser
    // or currentVideo (extracting just the filename to avoid path-encoded 404s).
    const rawVideo = state.analysisVideoName || state.frameBrowser?.videoName || state.currentVideo || '';
    const videoName = rawVideo.split('/').pop();
    const thumbUrl = videoName ? `/api/videos/${encodeURIComponent(videoName)}/frames/${frameNum}/thumb` : '';
    const thumbHtml = thumbUrl
        ? `<div class="frame-thumbnail"><img src="${thumbUrl}" alt="Frame ${frameNum}" loading="lazy"></div>`
        : '';

    // Show both vision analysis and combined analysis for comparison
    const visionHtml = data.vision_analysis
        ? `<div class="vision-analysis-section">
             <div class="section-label">Vision Analysis:</div>
             <div class="vision-analysis-text">${formatFrameAnalysis(data.vision_analysis)}</div>
           </div>`
        : '';
    
    const combinedHtml = data.combined_analysis
        ? `<div class="combined-analysis-section">
             <div class="section-label">Combined Analysis:</div>
             <div class="combined-analysis-text">${formatFrameAnalysis(data.combined_analysis)}</div>
           </div>`
        : '';

    const entry = document.createElement('div');
    entry.className = 'frame-entry combined-entry';
    entry.innerHTML = `
        ${thumbHtml}
        <div class="frame-content">
            <div class="frame-header">
                <span class="frame-number">Frame ${frameNum}</span>${origHtml}${tsHtml}
            </div>
            ${visionHtml}
            ${combinedHtml}
        </div>
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

        const currentFrame = job.current_frame || 0;
        const totalFrames = job.total_frames || 0;
        const frameInfo = (currentFrame > 0 && totalFrames > 0)
            ? `<p><strong>Frame:</strong> ${currentFrame} / ${totalFrames}</p>`
            : '';

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
                    ${frameInfo}
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
    if (state.debug) console.log('[DEBUG:JOBS] cancelJob called for', jobId);
    if (!confirm(`Cancel job ${jobId}?`)) return;

    try {
        const response = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
        const result = await response.json();
        if (state.debug) console.log('[DEBUG:JOBS] cancelJob response', result);

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

let selectedDedupThreshold = null;

async function runDedupMulti() {
    const videoSelect = document.getElementById('video-select');
    const videoName = videoSelect.value;
    if (!videoName) {
        showToast('Select a video first', 'error');
        return;
    }

    const raw = document.getElementById('dedup-thresholds-input')?.value || '5, 10, 15, 20, 30';
    const thresholds = raw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n >= 0 && n <= 64);
    if (thresholds.length === 0) {
        showToast('Enter at least one valid threshold (0-64)', 'error');
        return;
    }

    const btn = document.getElementById('dedup-run-multi-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Scanning...';
    }

    try {
        const filename = videoName.split('/').pop();
        const url = `/api/videos/${encodeURIComponent(filename)}/dedup-multi`;
        console.log('[dedup] fetching:', url);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ thresholds }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error?.message || 'Dedup scan failed');
        }

        const data = await response.json();
        showDedupMultiResults(data);
        showToast(`Scan complete: ${data.original_count} original frames`);
    } catch (error) {
        showToast('Dedup scan failed: ' + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Scan';
        }
    }
}

function showDedupMultiResults(data) {
    const container = document.getElementById('dedup-results');
    if (!container) return;

    container.classList.remove('hidden');
    document.getElementById('dedup-original-count').textContent = data.original_count;

    const tbody = document.getElementById('dedup-multi-tbody');
    if (!tbody) return;

    tbody.innerHTML = data.results.map(r => `
        <tr class="dedup-row" data-threshold="${r.threshold}">
            <td>${r.threshold}</td>
            <td>${r.deduped_count}</td>
            <td>${r.dropped}</td>
            <td>${r.dropped_pct}%</td>
            <td><button type="button" class="btn secondary small dedup-apply-btn" data-threshold="${r.threshold}">Apply</button></td>
        </tr>
    `).join('');

    tbody.querySelectorAll('.dedup-row').forEach(row => {
        row.addEventListener('click', (e) => {
            if (e.target.classList.contains('dedup-apply-btn')) return;
            tbody.querySelectorAll('.dedup-row').forEach(r => r.classList.remove('dedup-row-selected'));
            row.classList.add('dedup-row-selected');
            selectedDedupThreshold = parseInt(row.dataset.threshold);
        });
    });

    tbody.querySelectorAll('.dedup-apply-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const threshold = parseInt(e.target.dataset.threshold);
            await applyDedupAtThreshold(threshold);
        });
    });
}

async function applyDedupAtThreshold(threshold) {
    const videoSelect = document.getElementById('video-select');
    const videoName = videoSelect.value;
    if (!videoName) {
        showToast('Select a video first', 'error');
        return;
    }

    const btn = document.getElementById('run-dedup-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Applying...';
    }

    try {
        const filename = videoName.split('/').pop();
        const response = await fetch(`/api/videos/${encodeURIComponent(filename)}/dedup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ threshold }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error?.message || 'Dedup failed');
        }

        const result = await response.json();
        showToast(`Dedup applied (threshold=${threshold}): ${result.original_count} → ${result.deduped_count} frames`);
        loadVideos();

        setTimeout(() => {
            const dedupVideoName = result.dedup_video;
            if (dedupVideoName) {
                const select = document.getElementById('video-select');
                for (const option of select.options) {
                    if (option.value.includes(dedupVideoName) || option.dataset.name === dedupVideoName) {
                        select.value = option.value;
                        state.currentVideo = option.value;
                        updateStartButton();
                        initFrameBrowserForSelectedVideo();
                        showToast(`Auto-selected dedup video: ${dedupVideoName}`);
                        break;
                    }
                }
            }
        }, 1000);
    } catch (error) {
        showToast('Dedup failed: ' + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Apply & Dedup';
        }
    }
}

async function loadDedupResults() {
    const videoSelect = document.getElementById('video-select');
    const videoName = videoSelect.value;
    if (!videoName) return;

    try {
        const filename = videoName.split('/').pop();
        const response = await fetch(`/api/videos/${encodeURIComponent(filename)}/dedup-multi`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ thresholds: [10] }),
        });
        if (response.ok) {
            const result = await response.json();
            showDedupMultiResults(result);
        }
    } catch (error) {
        // No dedup results yet, that's fine
    }
}

function switchMainTab(tab) {
    document.querySelectorAll('.main-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.main-tab-content').forEach(c => c.classList.add('hidden'));

    document.querySelector(`.main-tab-btn[data-tab="${tab}"]`)?.classList.add('active');
    document.getElementById(`tab-${tab}`)?.classList.remove('hidden');
}

function switchAnalysisTab(tab) {
    document.querySelectorAll('.analysis-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.analysis-tab-content').forEach(c => c.classList.add('hidden'));

    document.querySelector(`.analysis-tab-btn[data-tab="${tab}"]`)?.classList.add('active');
    document.getElementById(`${tab}-analysis-panel`)?.classList.remove('hidden');
}
