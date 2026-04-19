// Provider management: discovery, model loading, OpenRouter
async function loadProviders() {
    try {
        const response = await fetch('/api/providers');
        const providers = await response.json();
        state.providers = {};
        providers.forEach(p => { state.providers[p.name] = p; });
        renderProviderStatus();
        updateProviderSelect();
        initChatProviderSelect('live');
    } catch (error) {
        console.error('Failed to load providers:', error);
    }
}

function renderProviderStatus() {
    const container = document.getElementById('provider-status');
    if (!container) return;

    const online = Object.values(state.providers).filter(p => p.status === 'online');
    const errors = Object.values(state.providers).filter(p => p.status === 'error');

    let html = '';
    if (online.length > 0) {
        html += `<div class="provider-status online">✓ ${online.length} provider(s) online</div>`;
    }
    if (errors.length > 0) {
        html += `<div class="provider-status error">✗ ${errors.length} provider(s) offline</div>`;
    }
    container.innerHTML = html;
}

function updateProviderSelect() {
    const select = document.getElementById('provider-select');
    if (!select) return;

    const currentValue = select.value;
    select.innerHTML = '<option value="">Select provider...</option>' +
        '<optgroup label="Ollama">' +
        Object.values(state.providers)
            .filter(p => p.type === 'ollama')
            .map(p => `<option value="ollama" data-name="${p.name}" data-url="${p.url}">${p.name} (${p.status})</option>`)
            .join('') +
        '</optgroup>' +
        '<optgroup label="Cloud">' +
        '<option value="openrouter">OpenRouter</option>' +
        '</optgroup>';

    if (currentValue) select.value = currentValue;
}

async function discoverProviders() {
    try {
        const response = await fetch('/api/providers/discover');
        const result = await response.json();
        showToast(`Discovered ${result.discovered} provider(s)`);
        loadProviders();
    } catch (error) {
        showToast('Discovery failed: ' + error.message, 'error');
    }
}

async function handleProviderChange() {
    const select = document.getElementById('provider-select');
    const modelSelect = document.getElementById('model-select');
    const costEstimate = document.getElementById('cost-estimate');

    if (!select || !modelSelect) return;

    modelSelect.innerHTML = '<option value="">Loading models...</option>';
    modelSelect.disabled = true;
    if (costEstimate) costEstimate.classList.add('hidden');

    const providerType = select.value;
    const selectedOption = select.selectedOptions[0];

    if (providerType === 'ollama') {
        const url = selectedOption?.dataset.url;
        if (!url) return;

        try {
            const response = await fetch(`/api/providers/ollama/models?server=${encodeURIComponent(url)}`);
            const data = await response.json();

            if (data.models && data.models.length > 0) {
                modelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}" data-size="${m.size || 0}">${m.name}</option>`).join('');
                modelSelect.disabled = false;
            } else {
                modelSelect.innerHTML = '<option value="">No models available</option>';
            }
        } catch (error) {
            console.error('Failed to load Ollama models:', error);
            modelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }

    } else if (providerType === 'openrouter') {
        if (!state.openRouterKey) {
            promptForOpenRouterKey();
            if (!state.openRouterKey) {
                select.value = '';
                return;
            }
        }

        try {
            const response = await fetch(`/api/providers/openrouter/models?api_key=${encodeURIComponent(state.openRouterKey)}`);
            const data = await response.json();

            if (data.models && data.models.length > 0) {
                modelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
                modelSelect.disabled = false;
            } else {
                modelSelect.innerHTML = '<option value="">No models available</option>';
            }
        } catch (error) {
            console.error('Failed to load OpenRouter models:', error);
            modelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }
    }

    updateStartButton();
}

async function handleModelChange() {
    const modelSelect = document.getElementById('model-select');
    const costEstimate = document.getElementById('cost-estimate');
    if (!modelSelect || !costEstimate) return;

    const providerType = document.getElementById('provider-select')?.value;
    const modelId = modelSelect.value;

    if (providerType === 'openrouter' && modelId && state.openRouterKey) {
        try {
            const videoSelect = document.getElementById('video-select');
            const videoOption = videoSelect?.selectedOptions[0];
            const videoName = videoOption?.dataset.name || '';

            const response = await fetch(`/api/providers/openrouter/cost?api_key=${encodeURIComponent(state.openRouterKey)}&model=${encodeURIComponent(modelId)}&frames=50`);
            const cost = await response.json();

            if (cost.estimated_cost) {
                document.getElementById('cost-value').textContent = `$${cost.estimated_cost.toFixed(4)}`;
                document.getElementById('vram-required').textContent = 'N/A (Cloud)';
                costEstimate.classList.remove('hidden');
            }
        } catch (error) {
            console.error('Failed to estimate cost:', error);
        }
    } else if (providerType === 'ollama' && modelId) {
        const provider = Object.values(state.providers).find(p => p.type === 'ollama');
        if (provider) {
            const model = provider.models?.find(m => m.id === modelId);
            if (model?.size) {
                const sizeGb = (model.size / 1024 / 1024 / 1024).toFixed(1);
                document.getElementById('vram-required').textContent = `~${sizeGb} GB`;
                document.getElementById('cost-value').textContent = '$0.0000 (Local)';
                costEstimate.classList.remove('hidden');
            }
        }
    }

    updateStartButton();
}

function promptForOpenRouterKey() {
    const key = prompt('Enter your OpenRouter API key:');
    if (key) {
        state.openRouterKey = key;
        saveStateToLocalStorage();
        showToast('API key saved');
    }
}

async function checkOpenRouterBalance() {
    if (!state.openRouterKey) {
        promptForOpenRouterKey();
        if (!state.openRouterKey) return;
    }

    try {
        const response = await fetch(`/api/providers/openrouter/balance?api_key=${encodeURIComponent(state.openRouterKey)}`);
        const data = await response.json();

        if (data.balance !== undefined) {
            showToast(`OpenRouter balance: $${data.balance.toFixed(4)}`);
        } else if (data.error) {
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('Failed to check balance: ' + error.message, 'error');
    }
}
