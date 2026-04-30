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

                <div class="results-actions">
                    <button class="btn secondary" onclick="openSendKbModal('${jobId}')">Send to Knowledge Base</button>
                    <button class="btn secondary" onclick="downloadResultsAsMarkdown('${jobId}')">Download as Markdown</button>
                </div>

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
                            <label for="results-chat-temp-input">Temperature</label>
                            <input type="number" id="results-chat-temp-input" value="0.1" min="0" max="2" step="0.1">
                        </div>
                        <div class="form-group">
                            <label>Content to send</label>
                            <select id="results-chat-content-select">
                                <option value="all">Analysis + Transcript + Summary</option>
                                <option value="transcript">Transcript only</option>
                                <option value="description">Summary only</option>
                                <option value="frames">Frame Analysis only</option>
                                <option value="transcript_description">Transcript + Summary</option>
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
        '<optgroup label="LiteLLM">' +
        Object.values(state.providers)
            .filter(p => p.type === 'litellm')
            .map(p => `<option value="litellm" data-url="${p.url}">${p.name} (${p.status})</option>`)
            .join('') +
        '</optgroup>' +
        '<optgroup label="Cloud">' +
        '<option value="openrouter">OpenRouter</option>' +
        '</optgroup>';
}

async function downloadResultsAsMarkdown(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/results`);
        const results = await response.json();

        // Format as markdown
        const content = formatResultsAsMarkdown(results, jobId);

        // Create and trigger download
        const blob = new Blob([content], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `job-${jobId}-results.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast('Download started');
    } catch (error) {
        showToast('Failed to download results', 'error');
    }
}

function formatResultsAsMarkdown(results, jobId) {
    const lines = [];

    // Title
    lines.push('# Video Analysis Results');
    lines.push('');

    // Job info
    lines.push(`**Job ID:** ${jobId}`);
    lines.push(`**Date:** ${new Date().toISOString()}`);
    lines.push('');

    // Video description
    const descObj = results.video_description;
    if (descObj) {
        const descText = typeof descObj === 'string' ? descObj : (descObj.response || descObj.text || JSON.stringify(descObj, null, 2));
        if (descText) {
            lines.push('## Video Description');
            lines.push('');
            lines.push(descText);
            lines.push('');
        }
    }

    // Transcript
    if (results.transcript?.text) {
        lines.push('## Transcript');
        lines.push('');
        const lang = results.transcript.language || 'unknown';
        const whisper = results.transcript.whisper_model || 'unknown';
        lines.push(`*Language: ${lang} (Whisper model: ${whisper})*`);
        lines.push('');
        lines.push(results.transcript.text);
        lines.push('');

        // Transcript segments with timestamps
        const segments = results.transcript.segments || [];
        if (segments.length > 0) {
            lines.push('### Transcript Segments');
            lines.push('');
            for (const seg of segments) {
                const ts = seg.start || 0;
                const mins = Math.floor(ts / 60);
                const secs = Math.floor(ts % 60);
                lines.push(`- [${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}] ${seg.text}`);
            }
            lines.push('');
        }
    }

    // Frame analyses
    const frames = results.frame_analyses || [];
    if (frames.length > 0) {
        lines.push('## Frame Analyses');
        lines.push('');
        for (const frame of frames) {
            const frameNum = frame.frame_number || frame.frame;
            const ts = frame.video_ts !== undefined ? frame.video_ts : 0;
            const mins = Math.floor(ts / 60);
            const secs = Math.floor(ts % 60);
            const analysis = frame.response || frame.analysis || '';
            if (analysis) {
                lines.push(`### Frame ${frameNum} (${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')})`);
                lines.push('');
                lines.push(analysis);
                lines.push('');
            }
        }
    }

    // Token usage
    if (results.token_usage) {
        lines.push('## Token Usage');
        lines.push('');
        lines.push(`- Prompt tokens: ${results.token_usage.prompt_tokens || 'N/A'}`);
        lines.push(`- Completion tokens: ${results.token_usage.completion_tokens || 'N/A'}`);
        lines.push(`- Total tokens: ${results.token_usage.total_tokens || 'N/A'}`);
        lines.push('');
    }

    return lines.join('\n');
}
