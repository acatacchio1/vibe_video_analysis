// Application initialization
document.addEventListener('DOMContentLoaded', () => {
    // Initialize socket connection
    initSocket();

    // Load initial data
    loadVideos();
    loadProviders();
    loadJobs();
    loadStoredResults();

    // Restore settings
    restoreSettings();

    // Wire up event listeners
    initUploadHandlers();

    // Provider select
    document.getElementById('provider-select')?.addEventListener('change', handleProviderChange);
    document.getElementById('model-select')?.addEventListener('change', handleModelChange);
    
    // Phase 2 provider select
    document.getElementById('phase2-provider-select')?.addEventListener('change', handlePhase2ProviderChange);
    document.getElementById('phase2-model-select')?.addEventListener('change', handlePhase2ModelChange);

    // Discover button
    document.getElementById('discover-btn')?.addEventListener('click', discoverProviders);

    // Analysis form
    document.getElementById('analysis-form')?.addEventListener('submit', (e) => {
        e.preventDefault();
        submitAnalysis();
    });

    // Video select change -> update frame browser and start button
    document.getElementById('video-select')?.addEventListener('change', () => {
        state.currentVideo = document.getElementById('video-select').value;
        updateStartButton();
        initFrameBrowserForSelectedVideo();
        // Commented out auto-dedup to prevent hanging
        // loadDedupResults();
    });

    // Dedup multi-scan button
    document.getElementById('dedup-run-multi-btn')?.addEventListener('click', runDedupMulti);

    // Frame browser controls
    document.getElementById('start-frame-slider')?.addEventListener('input', handleStartSliderChange);
    document.getElementById('end-frame-slider')?.addEventListener('input', handleEndSliderChange);
    document.getElementById('start-frame-input')?.addEventListener('change', handleStartInputChange);

    // Pipeline select change -> show/hide LinkedIn config
    document.getElementById('pipeline-select')?.addEventListener('change', handlePipelineChange);
    
    // Initialize pipeline state on page load
    handlePipelineChange();
    document.getElementById('end-frame-input')?.addEventListener('change', handleEndInputChange);
    document.getElementById('start-dec-btn')?.addEventListener('click', () => handleFrameStep('start', -1));
    document.getElementById('start-inc-btn')?.addEventListener('click', () => handleFrameStep('start', 1));
    document.getElementById('end-dec-btn')?.addEventListener('click', () => handleFrameStep('end', -1));
    document.getElementById('end-inc-btn')?.addEventListener('click', () => handleFrameStep('end', 1));

    // Main tabs
    document.querySelectorAll('.main-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchMainTab(btn.dataset.tab));
    });

    // Monitor tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchMonitorTab(btn.dataset.tab));
    });

    // Analysis tabs (within live analysis)
    document.querySelectorAll('.analysis-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchAnalysisTab(btn.dataset.tab));
    });

    // Settings
    document.getElementById('upload-settings-btn')?.addEventListener('click', toggleUploadSettings);
    document.addEventListener('click', closeUploadSettings);

    // Notifications
    document.getElementById('notifications-btn')?.addEventListener('click', requestNotificationPermission);

    // Debug toggle
    document.getElementById('debug-btn')?.addEventListener('click', toggleDebugMode);
    updateDebugButton();

    // Close modal on backdrop click
    document.getElementById('job-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'job-modal') closeModal();
    });

    // Save settings on change
    document.querySelectorAll('#temperature-input')
        .forEach(el => el.addEventListener('change', saveSettings));

    // Clear server log
    document.getElementById('clear-log-btn')?.addEventListener('click', clearServerLog);

    // Knowledge Base handlers
    initKbHandlers();

    // Ollama Instances handlers
    initOllamaInstancesHandlers();
});

async function submitAnalysis() {
    const videoSelect = document.getElementById('video-select');
    const providerSelect = document.getElementById('provider-select');
    const modelSelect = document.getElementById('model-select');

    const videoPath = videoSelect.value;
    const providerType = providerSelect.value;
    const model = modelSelect.value;
    const providerOption = providerSelect.selectedOptions[0];
    const providerName = providerOption?.dataset.name || providerType;

    if (!videoPath || !providerType || !model) {
        showToast('Please select video, provider, and model', 'error');
        return;
    }

    const fb = state.frameBrowser;
    const data = {
        video_path: videoPath,
        provider_type: providerType,
        provider_name: providerName,
        model: model,
        priority: parseInt(document.getElementById('priority-input')?.value || '0'),
        temperature: parseFloat(document.getElementById('temperature-input')?.value || '0.0'),
        start_frame: fb.startFrame > 1 ? fb.startFrame : 0,
        end_frame: fb.endFrame < fb.totalFrames ? fb.endFrame : undefined,

        user_prompt: document.getElementById('prompt-input')?.value || '',
        pipeline_type: document.getElementById('pipeline-select')?.value || 'standard_two_step',
    };

    // OpenRouter API key is handled server-side from environment variable
    if (providerType === 'ollama') {
        const ollamaUrl = providerOption?.dataset.url;
        if (ollamaUrl) {
            data.provider_config = { url: ollamaUrl };
        }
    }

    // Add LinkedIn configuration if LinkedIn pipeline is selected
    const pipelineType = data.pipeline_type;
    if (pipelineType === 'linkedin_extraction') {
        // Initialize params object if it doesn't exist
        if (!data.params) {
            data.params = {};
        }
        
        // Add LinkedIn config
        data.params.linkedin_config = {
            scoring_weights: {
                hook_strength: parseInt(document.getElementById('linkedin-hook-weight')?.value || '25'),
                self_contained_value: 20,
                clarity_and_focus: 15,
                speaker_energy: 15,
                visual_quality: 10,
                cta_potential: 10,
                duration_fit: 5,
            },
            targets: {
                ideal_duration_min: parseInt(document.getElementById('linkedin-duration-min')?.value || '30'),
                ideal_duration_max: parseInt(document.getElementById('linkedin-duration-max')?.value || '60'),
                max_duration: 90,
                min_duration: 15,
                hook_strength_threshold: 18,
                total_score_threshold: 70,
            },
            edit_preferences: {
                prefer_vertical: true,
                allow_square: true,
                auto_add_captions: document.getElementById('linkedin-add-captions')?.checked || true,
                detect_series: true,
                series_min_clips: 3,
                series_max_gap: 60,
            },
            generate_clips: document.getElementById('linkedin-generate-clips')?.checked || false,
        };
        
        console.log('LinkedIn config added:', data.params.linkedin_config);
    }

    // Add Phase 2 (synthesis) configuration
    const phase2ProviderSelect = document.getElementById('phase2-provider-select');
    const phase2ModelSelect = document.getElementById('phase2-model-select');
    const phase2TemperatureInput = document.getElementById('phase2-temperature-input');
    
    if (phase2ProviderSelect && phase2ModelSelect && phase2TemperatureInput) {
        const phase2ProviderType = phase2ProviderSelect.value;
        const phase2Model = phase2ModelSelect.value;
        const phase2Temperature = parseFloat(phase2TemperatureInput.value || '0.0');
        const phase2ProviderOption = phase2ProviderSelect.selectedOptions[0];
        
        console.log('Phase 2 config debug:', {
            phase2ProviderType,
            phase2Model,
            phase2Temperature,
            phase2ProviderOption,
            datasetUrl: phase2ProviderOption?.dataset.url,
            optionText: phase2ProviderOption?.text
        });
        
        // Only add Phase 2 config if a provider and model are selected
        if (phase2ProviderType && phase2Model) {
            // Initialize params object if it doesn't exist
            if (!data.params) {
                data.params = {};
            }
            
            data.params.two_step_enabled = true;
            data.params.phase2_provider_type = phase2ProviderType;
            data.params.phase2_model = phase2Model;
            data.params.phase2_temperature = phase2Temperature;
            
            if (phase2ProviderType === 'ollama') {
                // Get URL from selected option's data-url attribute
                const phase2OllamaUrl = phase2ProviderOption?.dataset.url;
                if (phase2OllamaUrl) {
                    data.params.phase2_provider_config = { url: phase2OllamaUrl };
                    console.log('Setting Phase 2 URL to:', phase2OllamaUrl);
                } else {
                    // Default URL if no specific instance selected
                    data.params.phase2_provider_config = { url: "http://192.168.1.237:11434" };
                    console.log('Using default Phase 2 URL');
                }
            } else if (phase2ProviderType === 'same_as_phase1') {
                // Use same provider as Phase 1
                data.params.phase2_provider_type = providerType;
                data.params.phase2_model = model;
                data.params.phase2_temperature = data.temperature; // Use same temperature
                if (providerType === 'ollama' && data.provider_config?.url) {
                    data.params.phase2_provider_config = { url: data.provider_config.url };
                    console.log('Phase 2 using same as Phase 1 URL:', data.provider_config.url);
                }
            }
            // OpenRouter for Phase 2 would use environment variable server-side
            console.log('Final Phase 2 config in params:', data.params.phase2_provider_config);
        }
    }

    // Store just the filename for thumbnail URL construction in appendFrameLog()
    state.analysisVideoName = videoPath.split('/').pop();

    startAnalysis(data);

    // Show live analysis section
    document.getElementById('live-analysis')?.classList.remove('hidden');
    document.getElementById('frames-log').innerHTML = '';

    showToast(`Analysis started (job will appear shortly)`);
}

// Handle pipeline selection change
function handlePipelineChange() {
    const pipelineSelect = document.getElementById('pipeline-select');
    const linkedinConfigSection = document.getElementById('linkedin-config-section');
    const phase2Section = document.querySelector('.form-section-separator')?.parentElement;
    
    if (!pipelineSelect || !linkedinConfigSection) return;
    
    const isLinkedIn = pipelineSelect.value === 'linkedin_extraction';
    
    // Show/hide LinkedIn config section
    if (isLinkedIn) {
        linkedinConfigSection.classList.remove('hidden');
        // Also update slider value display
        const hookWeightSlider = document.getElementById('linkedin-hook-weight');
        const hookWeightValue = document.getElementById('linkedin-hook-value');
        if (hookWeightSlider && hookWeightValue) {
            hookWeightValue.textContent = hookWeightSlider.value;
            hookWeightSlider.addEventListener('input', (e) => {
                hookWeightValue.textContent = e.target.value;
            });
        }
    } else {
        linkedinConfigSection.classList.add('hidden');
    }
    
    // Show/hide Phase 2 section (not needed for LinkedIn)
    if (phase2Section) {
        if (isLinkedIn) {
            phase2Section.classList.add('hidden');
        } else {
            phase2Section.classList.remove('hidden');
        }
    }
    
    console.log(`Pipeline changed to: ${pipelineSelect.value}, LinkedIn: ${isLinkedIn}`);
}
