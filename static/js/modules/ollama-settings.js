// Ollama Instances Settings Modal
function openOllamaInstancesModal() {
    const modal = document.getElementById('ollama-instances-modal');
    if (modal) modal.classList.remove('hidden');
    loadOllamaInstances();
}

function closeOllamaInstancesModal() {
    const modal = document.getElementById('ollama-instances-modal');
    if (modal) modal.classList.add('hidden');
}

async function loadOllamaInstances() {
    try {
        const response = await fetch('/api/providers/ollama-instances');
        const data = await response.json();
        const textarea = document.getElementById('ollama-instances-textarea');
        if (textarea) {
            textarea.value = data.instances.join('\n');
        }
    } catch (error) {
        console.error('Failed to load Ollama instances:', error);
    }
}

async function saveOllamaInstances() {
    const textarea = document.getElementById('ollama-instances-textarea');
    if (!textarea) return;

    const instances = textarea.value
        .split('\n')
        .map(url => url.trim())
        .filter(url => url.length > 0);

    const statusEl = document.getElementById('ollama-instances-status');

    try {
        const response = await fetch('/api/providers/ollama-instances', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instances }),
        });
        const data = await response.json();

        if (data.ok) {
            if (statusEl) {
                statusEl.textContent = 'Saved successfully!';
                statusEl.classList.remove('hidden', 'kb-status-error');
                statusEl.classList.add('kb-status-success');
            }
            showToast('Ollama instances saved');
        } else {
            throw new Error(data.error || 'Failed to save');
        }
    } catch (error) {
        if (statusEl) {
            statusEl.textContent = `Error: ${error.message}`;
            statusEl.classList.remove('hidden', 'kb-status-success');
            statusEl.classList.add('kb-status-error');
        }
        showToast(`Failed to save: ${error.message}`, 'error');
    }
}

async function forceOllamaScan() {
    const statusEl = document.getElementById('ollama-instances-status');
    const discoveredList = document.getElementById('ollama-discovered-list');

    if (statusEl) {
        statusEl.textContent = 'Scanning network... this may take a minute.';
        statusEl.classList.remove('hidden', 'kb-status-error', 'kb-status-success');
    }

    try {
        const response = await fetch('/api/providers/discover');
        const data = await response.json();

        if (discoveredList) {
            if (data.discovered === 0) {
                discoveredList.innerHTML = '<small>No new instances found.</small>';
            } else {
                const html = data.urls.map(url => {
                    const status = discovery.status?.[url] || 'unknown';
                    const badge = status === 'online' ? '🟢' : '🔴';
                    return `<div class="ollama-instance-row">${badge} <code>${escapeHtml(url)}</code></div>`;
                }).join('');
                discoveredList.innerHTML = html;
            }
        }

        if (statusEl) {
            statusEl.textContent = `Scan complete. Found ${data.discovered} instances.`;
            statusEl.classList.remove('hidden', 'kb-status-error');
            statusEl.classList.add('kb-status-success');
        }

        // Reload providers list
        loadProviders();
    } catch (error) {
        if (statusEl) {
            statusEl.textContent = `Scan failed: ${error.message}`;
            statusEl.classList.remove('hidden', 'kb-status-success');
            statusEl.classList.add('kb-status-error');
        }
        showToast(`Scan failed: ${error.message}`, 'error');
    }
}

function initOllamaInstancesHandlers() {
    document.getElementById('ollama-instances-btn')?.addEventListener('click', openOllamaInstancesModal);
    document.getElementById('ollama-save-btn')?.addEventListener('click', saveOllamaInstances);
    document.getElementById('ollama-force-scan-btn')?.addEventListener('click', forceOllamaScan);

    // Close modal on backdrop click
    document.getElementById('ollama-instances-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'ollama-instances-modal') closeOllamaInstancesModal();
    });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeOllamaInstancesModal();
        }
    });
}
