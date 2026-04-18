// Stored results browser
async function loadStoredResults() {
    try {
        const response = await fetch('/api/results');
        const results = await response.json();
        renderResultsList(results);
    } catch (error) {
        console.error('Failed to load stored results:', error);
    }
}

function renderResultsList(results) {
    const container = document.getElementById('results-list');
    if (!container) return;

    if (results.length === 0) {
        container.innerHTML = '<div class="empty-state">No results yet.</div>';
        return;
    }

    container.innerHTML = results.map(r => `
        <div class="result-item" data-job-id="${r.job_id}" onclick="showResultDetail('${r.job_id}')">
            <div class="result-title">Job: ${r.job_id}</div>
            <div class="result-meta">
                <span>${r.model}</span>
                <span>${r.frame_count} frames</span>
            </div>
            <div class="result-preview">${r.desc_preview || 'No description'}</div>
        </div>
    `).join('');
}

async function showResultDetail(jobId) {
    try {
        document.querySelectorAll('.result-item').forEach(el => el.classList.remove('active'));
        document.querySelector(`.result-item[data-job-id="${jobId}"]`)?.classList.add('active');

        const response = await fetch(`/api/jobs/${jobId}/results`);
        const results = await response.json();
        state.currentJobResults = results;

        const detail = document.getElementById('results-detail');
        detail.innerHTML = `
            <div class="results-detail-content">
                <h3>Job: ${jobId}</h3>

                <h3>Video Description</h3>
                <pre>${escapeHtml(typeof results.video_description === 'string' ? results.video_description : JSON.stringify(results.video_description, null, 2))}</pre>

                <h3>Transcript</h3>
                <pre>${escapeHtml(results.transcript?.text || 'No transcript')}</pre>

                <h3>Frame Analyses (${results.frame_analyses?.length || 0})</h3>
                ${results.frame_analyses?.map((f, i) => `
                    <pre><strong>Frame ${f.frame}:</strong> ${escapeHtml(f.response || '')}</pre>
                `).join('') || '<pre>No frame analyses</pre>'}

                <div class="llm-chat-panel">
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
