// LLM chat functionality
async function handleChatProviderChange(context = 'live') {
    const isLivePanel = context === 'live' && document.getElementById('live-chat-provider-select');
    const selectId = context === 'modal' ? 'modal-chat-provider-select' :
                     context === 'results' ? 'results-chat-provider-select' :
                     isLivePanel ? 'live-chat-provider-select' : 'chat-provider-select';
    const modelSelectId = context === 'modal' ? 'modal-chat-model-select' :
                         context === 'results' ? 'results-chat-model-select' :
                         isLivePanel ? 'live-chat-model-select' : 'chat-model-select';

    const providerSelect = document.getElementById(selectId);
    const modelSelect = document.getElementById(modelSelectId);
    if (!providerSelect || !modelSelect) return;

    const providerName = providerSelect.value;
    modelSelect.innerHTML = '<option value="">Loading models...</option>';
    modelSelect.disabled = true;

    if (providerName === 'openrouter') {
        try {
            const response = await fetch('/api/providers/openrouter/models');
            const data = await response.json();

            if (data.error) {
                modelSelect.innerHTML = `<option value="">${data.error}</option>`;
            } else if (data.models && data.models.length > 0) {
                modelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
                modelSelect.disabled = false;
            } else {
                modelSelect.innerHTML = '<option value="">No models available</option>';
            }
        } catch (error) {
            console.error('Failed to load OpenRouter models for chat:', error);
            modelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }

    } else if (providerName === 'ollama') {
        const selectedOption = providerSelect.selectedOptions[0];
        const ollamaUrl = selectedOption?.dataset.url;
        if (ollamaUrl) {
            try {
                const response = await fetch(`/api/providers/ollama/models?server=${encodeURIComponent(ollamaUrl)}`);
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
    const isLivePanel = context === 'live' && document.getElementById('live-chat-provider-select');
    const providerSelectId = context === 'modal' ? 'modal-chat-provider-select' :
                            context === 'results' ? 'results-chat-provider-select' :
                            isLivePanel ? 'live-chat-provider-select' : 'chat-provider-select';
    const modelSelectId = context === 'modal' ? 'modal-chat-model-select' :
                         context === 'results' ? 'results-chat-model-select' :
                         isLivePanel ? 'live-chat-model-select' : 'chat-model-select';
    const contentSelectId = context === 'modal' ? 'modal-chat-content-select' :
                           context === 'results' ? 'results-chat-content-select' :
                           isLivePanel ? 'live-chat-content-select' : 'chat-content-select';
    const promptTextareaId = context === 'modal' ? 'modal-chat-prompt' :
                            context === 'results' ? 'results-chat-prompt' :
                            isLivePanel ? 'live-chat-prompt' : 'chat-prompt';
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

    let content = '';
    if (jobId) {
        try {
            const response = await fetch(`/api/jobs/${jobId}/results`);
            const results = await response.json();
            content = formatContentForLLM(results, contentType);
        } catch (error) {
            showToast('Failed to load job results', 'error');
            return;
        }
    } else if (context === 'live' && state.currentJobResults) {
        content = formatContentForLLM(state.currentJobResults, contentType);
    } else {
        showToast('No content available to send', 'error');
        return;
    }

    if (!content) {
        showToast(`Selected content type (${contentType}) not available`, 'error');
        return;
    }

    const requestData = {
        provider_type: providerType,
        model: modelId,
        prompt: prompt,
        content: content,
    };

    if (providerType === 'ollama') {
        const selectedOption = providerSelect.selectedOptions[0];
        const ollamaUrl = selectedOption?.dataset.url;
        if (ollamaUrl) {
            requestData.ollama_url = ollamaUrl;
        }
    }

    responseText.textContent = 'Submitting to LLM queue...';
    responseDiv.classList.remove('hidden');
    responseText.classList.add('loading-state');

    try {
        const response = await fetch('/api/llm/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();

        if (result.job_id) {
            responseText.textContent = `Chat job submitted (ID: ${result.job_id}). Queue position: ${result.queue_position || 'pending'}.`;
            pollChatJobStatus(result.job_id, responseText, responseDiv);

            if (context === 'modal') {
                const modalBody = document.querySelector('.modal-body');
                const jobButton = document.createElement('button');
                jobButton.className = 'btn small secondary';
                jobButton.textContent = `Track Job ${result.job_id}`;
                jobButton.onclick = () => openJobStatusModal(result.job_id, 'chat');
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
    const transcript = results.transcript?.text || '';
    const descObj = results.video_description;
    const description = typeof descObj === 'string' ? descObj :
                       (descObj?.response || descObj?.text || JSON.stringify(descObj, null, 2) || '');
    const frames = results.frame_analyses || [];
    const framesText = frames.map((f) => {
        const num = f.frame_number || f.frame;
        const ts = (f.video_ts !== undefined && f.video_ts !== null) ? ` [${formatVideoTimestamp(f.video_ts)}]` : '';
        return `Frame ${num}${ts}: ${f.response || f.analysis || ''}`;
    }).join('\n');

    if (contentType === 'transcript') {
        return transcript;
    } else if (contentType === 'description') {
        return description;
    } else if (contentType === 'transcript_description') {
        return `TRANSCRIPT:\n${transcript}\n\nVIDEO SUMMARY:\n${description}`;
    } else if (contentType === 'frames') {
        return framesText;
    } else if (contentType === 'all') {
        const parts = [];
        if (framesText) parts.push(`FRAME ANALYSIS:\n${framesText}`);
        if (transcript) parts.push(`TRANSCRIPT:\n${transcript}`);
        if (description) parts.push(`VIDEO SUMMARY:\n${description}`);
        return parts.join('\n\n');
    }
    if (contentType === 'both') {
        return `TRANSCRIPT:\n${transcript}\n\nVIDEO SUMMARY:\n${description}`;
    }
    return '';
}

async function pollChatJobStatus(jobId, responseText, responseDiv) {
    const maxAttempts = 300;
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
    const modal = document.getElementById('job-modal');
    const modalBody = document.querySelector('.modal-body');

    if (jobType === 'chat') {
        modal.querySelector('.modal-header h2').textContent = `Chat Job Status: ${jobId}`;
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
        const response = await fetch(`/api/llm/chat/${jobId}`, { method: 'DELETE' });
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
