// Settings persistence and UI toggles
function saveSettings() {
    const settings = {
        temperature: document.getElementById('temperature-input')?.value,
        spf: document.getElementById('spf-input')?.value,
        whisper_model: document.getElementById('whisper-select')?.value,
        language: document.getElementById('language-input')?.value,
        device: document.getElementById('device-select')?.value,
        keep_frames: document.getElementById('keep-frames-checkbox')?.checked
    };

    state.settings = settings;
    saveStateToLocalStorage();
}

function restoreSettings() {
    if (state.settings) {
        const idMap = {
            spf: 'spf-input',
        };
        Object.entries(state.settings).forEach(([key, value]) => {
            const elId = idMap[key] || key.replace(/_/g, '-') + '-input';
            const el = document.getElementById(elId) ||
                      document.getElementById(key.replace(/_/g, '-') + '-select');
            if (el) {
                if (el.type === 'checkbox') {
                    el.checked = value;
                } else {
                    el.value = value;
                }
            }
        });
    }
}

function restoreSettings() {
    if (state.settings) {
        const idMap = {
            spf: 'spf-input',
        };
        Object.entries(state.settings).forEach(([key, value]) => {
            const elId = idMap[key] || key.replace(/_/g, '-') + '-input';
            const el = document.getElementById(elId) ||
                      document.getElementById(key.replace(/_/g, '-') + '-select');
            if (el) {
                if (el.type === 'checkbox') {
                    el.checked = value;
                } else {
                    el.value = value;
                }
            }
        });
    }
}

function toggleAdvancedOptions() {
    const panel = document.getElementById('advanced-options');
    const btn = document.getElementById('advanced-toggle-btn');

    panel.classList.toggle('hidden');
    btn.textContent = panel.classList.contains('hidden') ? 'Advanced Options ▼' : 'Advanced Options ▲';
}

function toggleUploadSettings() {
    const popover = document.getElementById('upload-settings-popover');
    popover.classList.toggle('hidden');
}

function closeUploadSettings(e) {
    const popover = document.getElementById('upload-settings-popover');
    const btn = document.getElementById('upload-settings-btn');
    if (!popover || !btn) return;
    if (!popover.contains(e.target) && !btn.contains(e.target)) {
        popover.classList.add('hidden');
    }
}

async function toggleDebugMode() {
    try {
        const response = await fetch('/api/debug', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable: !state.debug }),
        });
        const result = await response.json();
        state.debug = result.debug;
        localStorage.setItem('va_debug', state.debug);
        updateDebugButton();
        showToast(result.message);
    } catch (error) {
        console.error('Failed to toggle debug:', error);
    }
}

function updateDebugButton() {
    const btn = document.getElementById('debug-btn');
    if (btn) {
        btn.style.opacity = state.debug ? '1' : '0.5';
        btn.title = state.debug ? 'Debug Mode ON - click to disable' : 'Debug Mode OFF - click to enable';
    }
}
