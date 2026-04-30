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
    const phase2Select = document.getElementById('phase2-provider-select');
    
    if (!select) return;

    const currentValue = select.value;
    select.innerHTML = '<option value="">Select provider...</option>' +
        '<optgroup label="LiteLLM">' +
        Object.values(state.providers)
            .filter(p => p.type === 'litellm')
            .map(p => `<option value="litellm" data-name="${p.name}" data-url="${p.url}">${p.name} (${p.status})</option>`)
            .join('') +
        '</optgroup>' +
        '<optgroup label="Cloud">' +
        '<option value="openrouter">OpenRouter</option>' +
        '</optgroup>';

    if (currentValue) select.value = currentValue;
    
    // Also update Phase 2 provider select if it exists
    if (phase2Select) {
        // Save current value
        const currentPhase2Value = phase2Select.value;
        
        // Build options for Phase 2
        let phase2Options = '<option value="">Select provider...</option>';
        
        // Add specific LiteLLM instances
        const litellmProviders = Object.values(state.providers).filter(p => p.type === 'litellm');
        if (litellmProviders.length > 0) {
            phase2Options += litellmProviders
                .map(p => `<option value="litellm" data-url="${p.url}">${p.name} (${p.status})</option>`)
                .join('');
        }
        
        // Add other options
        phase2Options += '<option value="openrouter">OpenRouter</option>' +
                         '<option value="same_as_phase1">Same as Phase 1</option>';
        
        phase2Select.innerHTML = phase2Options;
        
        // Auto-select the first LiteLLM instance for Phase 2 (if available)
        const litellmOptions = Array.from(phase2Select.options).filter(opt => opt.value === 'litellm' && opt.dataset.url);
        if (litellmOptions.length > 0) {
            // Try to select a different LiteLLM instance than Phase 1 if possible
            const phase1Select = document.getElementById('provider-select');
            const phase1SelectedOption = phase1Select?.selectedOptions[0];
            const phase1Url = phase1SelectedOption?.dataset.url;
            
            // Find a LiteLLM instance different from Phase 1, or just use the first one
            const differentOption = litellmOptions.find(opt => opt.dataset.url !== phase1Url) || litellmOptions[0];
            phase2Select.value = differentOption.value;

            
            // Trigger change event to load models
            setTimeout(() => {
                handlePhase2ProviderChange();
            }, 100);
        }
        
        // Restore previous selection if it still exists (but auto-selection above takes precedence)
        if (currentPhase2Value && !phase2Select.value) {
            // Try to find and restore the exact option
            const options = Array.from(phase2Select.options);
            const matchingOption = options.find(opt => opt.value === currentPhase2Value ||
                (currentPhase2Value === 'litellm' && opt.dataset.url && opt.text.includes(currentPhase2Value)));

            if (matchingOption) {
                phase2Select.value = matchingOption.value;
            }
        }
    }
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

    if (providerType === 'litellm') {
        const url = selectedOption?.dataset.url;
        if (!url) return;

        try {
            const response = await fetch(`/api/providers/litellm/models?server=${encodeURIComponent(url)}`);
            const data = await response.json();

            if (data.models && data.models.length > 0) {
                modelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}" data-size="${m.size || 0}">${m.name}</option>`).join('');
                modelSelect.disabled = false;
            } else {
                modelSelect.innerHTML = '<option value="">No models available</option>';
            }
        } catch (error) {
            console.error('Failed to load LiteLLM models:', error);
            modelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }

    } else if (providerType === 'openrouter') {
        try {
            const response = await fetch('/api/providers/openrouter/models');
            const data = await response.json();

            if (data.models && data.models.length > 0) {
                modelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
                modelSelect.disabled = false;
                if (costEstimate) costEstimate.classList.remove('hidden');
            } else {
                modelSelect.innerHTML = '<option value="">No models available</option>';
            }
        } catch (error) {
            console.error('Failed to load OpenRouter models:', error);
            modelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }
    }
    
    // Update Phase 2 warnings when Phase 1 changes
    handlePhase1ProviderChangeForPhase2Warning();
}

function handleModelChange() {
    const modelSelect = document.getElementById('model-select');
    const costEstimate = document.getElementById('cost-estimate');
    
    if (!modelSelect) return;
    
    const selectedOption = modelSelect.selectedOptions[0];
    if (!selectedOption) return;
    
    const modelId = modelSelect.value;
    const providerSelect = document.getElementById('provider-select');
    const providerType = providerSelect?.value;
    
    if (providerType === 'openrouter' && modelId) {
        // Estimate cost for OpenRouter
        estimateOpenRouterCost(modelId);
    } else if (costEstimate) {
        costEstimate.classList.add('hidden');
    }
    
    // Update Phase 2 warnings when Phase 1 model changes
    handlePhase1ProviderChangeForPhase2Warning();
}

// Phase 2 (synthesis) provider handling
async function handlePhase2ProviderChange() {
    const phase2ProviderSelect = document.getElementById('phase2-provider-select');
    const phase2ModelSelect = document.getElementById('phase2-model-select');
    const phase2Warning = document.getElementById('phase2-warning');
    
    if (!phase2ProviderSelect || !phase2ModelSelect) return;

    const phase2ProviderType = phase2ProviderSelect.value;
    const selectedOption = phase2ProviderSelect.selectedOptions[0];
    
    phase2ModelSelect.innerHTML = '<option value="">Loading models...</option>';
    phase2ModelSelect.disabled = true;
    if (phase2Warning) phase2Warning.classList.add('hidden');

    // Get Phase 1 provider for warning checking
    const phase1ProviderSelect = document.getElementById('provider-select');
    const phase1ModelSelect = document.getElementById('model-select');
    const phase1ProviderType = phase1ProviderSelect?.value;
    const phase1Model = phase1ModelSelect?.value;

    if (phase2ProviderType === 'same_as_phase1') {
        if (phase1ProviderType && phase1Model) {
            // Use Phase 1 settings
            phase2ModelSelect.innerHTML = `<option value="${phase1Model}" selected>${phase1Model} (same as Phase 1)</option>`;
            phase2ModelSelect.disabled = false;
        } else {
            phase2ModelSelect.innerHTML = '<option value="">Phase 1 not configured</option>';
        }
        return;
    }

    if (phase2ProviderType === 'litellm') {
        const url = selectedOption?.dataset.url || "http://172.16.17.3:4000/v1";
        
        try {
            const response = await fetch(`/api/providers/litellm/models?server=${encodeURIComponent(url)}`);
            const data = await response.json();

            if (data.models && data.models.length > 0) {
                phase2ModelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
                phase2ModelSelect.disabled = false;
            } else {
                phase2ModelSelect.innerHTML = '<option value="">No models available</option>';
            }
        } catch (error) {
            console.error('Failed to load Phase 2 LiteLLM models:', error);
            phase2ModelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }
        
    } else if (phase2ProviderType === 'openrouter') {
        try {
            const response = await fetch('/api/providers/openrouter/models');
            const data = await response.json();

            if (data.models && data.models.length > 0) {
                phase2ModelSelect.innerHTML = '<option value="">Select model...</option>' +
                    data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
                phase2ModelSelect.disabled = false;
                
                // Set default Phase 2 model if available
                const defaultModel = data.models.find(m => m.id.includes('gpt-4') || m.id.includes('claude'));
                if (defaultModel && !phase2ModelSelect.value) {
                    phase2ModelSelect.value = defaultModel.id;
                }
            } else {
                phase2ModelSelect.innerHTML = '<option value="">No models available</option>';
            }
        } catch (error) {
            console.error('Failed to load Phase 2 OpenRouter models:', error);
            phase2ModelSelect.innerHTML = '<option value="">Failed to load models</option>';
        }
    }
    
    // Check for warnings
    if (phase2ProviderType === phase1ProviderType && phase1ProviderType) {
        phase2Warning.textContent = 'Warning: Using the same provider for both phases may overload the system. Consider using a secondary LiteLLM instance for Phase 2.';
        phase2Warning.classList.remove('hidden');
    }
}

function handlePhase2ModelChange() {
    // Update any warnings or UI based on Phase 2 model selection
    const phase2ModelSelect = document.getElementById('phase2-model-select');
    const phase2Warning = document.getElementById('phase2-warning');
    
    if (!phase2ModelSelect || !phase2Warning) return;
    
    const phase2Model = phase2ModelSelect.value;
    const phase1ModelSelect = document.getElementById('model-select');
    const phase1Model = phase1ModelSelect?.value;
    
    // Show warning if using same model (only relevant when Phase 2 provider is "same as Phase 1")
    const phase2ProviderSelect = document.getElementById('phase2-provider-select');
    const phase2ProviderType = phase2ProviderSelect?.value;
    
    if (phase2ProviderType === 'same_as_phase1' && phase2Model === phase1Model) {
        phase2Warning.textContent = 'Note: Using identical model for both phases may not provide additional insight.';
        phase2Warning.classList.remove('hidden');
    }
    // Other warnings could be added here based on model selection
}

// Check for warnings when Phase 1 changes
function handlePhase1ProviderChangeForPhase2Warning() {
    const phase1ProviderSelect = document.getElementById('provider-select');
    const phase1ModelSelect = document.getElementById('model-select');
    const phase2ProviderSelect = document.getElementById('phase2-provider-select');
    const phase2Warning = document.getElementById('phase2-warning');
    
    if (!phase1ProviderSelect || !phase2ProviderSelect || !phase2Warning) return;
    
    const phase1ProviderType = phase1ProviderSelect.value;
    const phase1Model = phase1ModelSelect?.value;
    const phase2ProviderType = phase2ProviderSelect.value;
    
    // If Phase 2 is set to "same as Phase 1" and Phase 1 changes, update Phase 2
    if (phase2ProviderType === 'same_as_phase1' && phase1Model) {
        const phase2ModelSelect = document.getElementById('phase2-model-select');
        if (phase2ModelSelect) {
            phase2ModelSelect.innerHTML = `<option value="${phase1Model}" selected>${phase1Model} (same as Phase 1)</option>`;
            phase2ModelSelect.disabled = false;
        }
    }
    
    // Show warning if using same provider (but don't block)
    if (phase2ProviderType === phase1ProviderType && phase1ProviderType) {
        phase2Warning.textContent = 'Warning: Using the same provider for both phases may overload the system. Consider using a secondary LiteLLM instance for Phase 2.';
        phase2Warning.classList.remove('hidden');
    }
}