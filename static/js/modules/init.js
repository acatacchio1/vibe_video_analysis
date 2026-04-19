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
        loadDedupResults();
    });

    // Run Dedup button
    document.getElementById('run-dedup-btn')?.addEventListener('click', runDedup);

    // Dedup threshold input change -> update dedup results display
    document.getElementById('dedup-threshold-input')?.addEventListener('change', () => {
        const videoSelect = document.getElementById('video-select');
        if (videoSelect.value) {
            loadDedupResults();
        }
    });

    // Frame browser controls
    document.getElementById('start-frame-slider')?.addEventListener('input', handleStartSliderChange);
    document.getElementById('end-frame-slider')?.addEventListener('input', handleEndSliderChange);
    document.getElementById('start-frame-input')?.addEventListener('change', handleStartInputChange);
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

    // Settings
    document.getElementById('advanced-toggle-btn')?.addEventListener('click', toggleAdvancedOptions);
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
    document.querySelectorAll('#spf-input, #temperature-input, #dedup-sensitivity-input, #whisper-select, #language-input, #device-select, #keep-frames-checkbox')
        .forEach(el => el.addEventListener('change', saveSettings));

    // Clear server log
    document.getElementById('clear-log-btn')?.addEventListener('click', clearServerLog);

    // Knowledge Base handlers
    initKbHandlers();
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
        fps: parseFloat(document.getElementById('spf-input')?.value || '1'),
        similarity_threshold: parseInt(document.getElementById('dedup-sensitivity-input')?.value || '10'),
        whisper_model: document.getElementById('whisper-select')?.value || 'large',
        language: document.getElementById('language-input')?.value || 'en',
        device: document.getElementById('device-select')?.value || 'gpu',
        keep_frames: document.getElementById('keep-frames-checkbox')?.checked || false,
        user_prompt: document.getElementById('prompt-input')?.value || '',
    };

    // OpenRouter API key is handled server-side from environment variable
    if (providerType === 'ollama') {
        const ollamaUrl = providerOption?.dataset.url;
        if (ollamaUrl) {
            data.provider_config = { url: ollamaUrl };
        }
    }

    startAnalysis(data);

    // Show live analysis section
    document.getElementById('live-analysis')?.classList.remove('hidden');
    document.getElementById('frames-log').innerHTML = '';

    showToast(`Analysis started (job will appear shortly)`);
}
