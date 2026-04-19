// OpenWebUI Knowledge Base integration
const kbState = {
    enabled: false,
    url: '',
    apiKey: '',
    kbName: 'Video Analyzer',
    autoSync: true,
};

function closeKbModal() {
    document.getElementById('kb-modal')?.classList.add('hidden');
}

function openKbModal() {
    const modal = document.getElementById('kb-modal');
    if (modal) modal.classList.remove('hidden');
    loadKbSettings();
}

async function loadKbSettings() {
    try {
        const resp = await fetch('/api/knowledge/status');
        const data = await resp.json();
        kbState.enabled = data.enabled || false;
        kbState.url = data.url || '';
        kbState.kbName = data.knowledge_base_name || 'Video Analyzer';
        kbState.autoSync = data.auto_sync !== undefined ? data.auto_sync : true;

        document.getElementById('kb-enabled-checkbox').checked = kbState.enabled;
        document.getElementById('kb-url-input').value = kbState.url;
        document.getElementById('kb-api-key-input').value = kbState.apiKey;
        document.getElementById('kb-name-input').value = kbState.kbName;
        document.getElementById('kb-auto-sync-checkbox').checked = kbState.autoSync;

        toggleKbFields(kbState.enabled);
    } catch (e) {
        console.error('Failed to load KB settings:', e);
    }
}

function toggleKbFields(enabled) {
    const fields = document.getElementById('kb-config-fields');
    if (fields) {
        fields.style.opacity = enabled ? '1' : '0.4';
        fields.style.pointerEvents = enabled ? 'auto' : 'none';
    }
}

async function testKbConnection() {
    const url = document.getElementById('kb-url-input').value.trim();
    const apiKey = document.getElementById('kb-api-key-input').value.trim();
    const statusEl = document.getElementById('kb-status');

    if (!url || !apiKey) {
        showKbStatus('error', 'URL and API key are required');
        return;
    }

    showKbStatus('info', 'Testing connection...');

    try {
        const resp = await fetch('/api/knowledge/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, api_key: apiKey }),
        });
        const data = await resp.json();

        if (data.ok) {
            showKbStatus('success', `Connected! Found ${data.knowledge_bases || 0} knowledge bases.`);
        } else {
            showKbStatus('error', data.error || 'Connection failed');
        }
    } catch (e) {
        showKbStatus('error', `Connection error: ${e.message}`);
    }
}

async function saveKbSettings() {
    const enabled = document.getElementById('kb-enabled-checkbox').checked;
    const url = document.getElementById('kb-url-input').value.trim();
    const apiKey = document.getElementById('kb-api-key-input').value.trim();
    const kbName = document.getElementById('kb-name-input').value.trim();
    const autoSync = document.getElementById('kb-auto-sync-checkbox').checked;
    const statusEl = document.getElementById('kb-status');

    if (enabled && (!url || !apiKey)) {
        showKbStatus('error', 'URL and API key are required when enabled');
        return;
    }

    showKbStatus('info', 'Saving settings...');

    try {
        const resp = await fetch('/api/knowledge/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled, url, api_key: apiKey,
                knowledge_base_name: kbName || 'Video Analyzer',
                auto_sync: autoSync,
            }),
        });
        const data = await resp.json();

        if (data.success) {
            kbState.enabled = enabled;
            kbState.url = url;
            kbState.apiKey = apiKey;
            kbState.kbName = kbName || 'Video Analyzer';
            kbState.autoSync = autoSync;
            toggleKbFields(enabled);
            showKbStatus('success', 'Settings saved successfully!');
            showToast('Knowledge Base settings saved');
        } else {
            showKbStatus('error', data.error || 'Failed to save settings');
        }
    } catch (e) {
        showKbStatus('error', `Save error: ${e.message}`);
    }
}

async function syncAllResults() {
    const syncStatusEl = document.getElementById('kb-sync-status');
    showKbSyncStatus('info', 'Syncing all results to OpenWebUI...');

    try {
        const resp = await fetch('/api/knowledge/sync-all', { method: 'POST' });
        const data = await resp.json();

        if (data.success) {
            let msg = `Synced ${data.synced}/${data.total} results.`;
            if (data.failed > 0) msg += ` ${data.failed} failed.`;
            if (data.skipped > 0) msg += ` ${data.skipped} skipped (no results).`;
            showKbSyncStatus(data.failed > 0 ? 'error' : 'success', msg);
            showToast(msg);
        } else {
            showKbSyncStatus('error', data.error || 'Sync failed');
        }
    } catch (e) {
        showKbSyncStatus('error', `Sync error: ${e.message}`);
    }
}

function showKbStatus(type, message) {
    const el = document.getElementById('kb-status');
    if (!el) return;
    el.className = `kb-status ${type}`;
    el.textContent = message;
    el.classList.remove('hidden');
}

function showKbSyncStatus(type, message) {
    const el = document.getElementById('kb-sync-status');
    if (!el) return;
    el.className = `kb-status ${type}`;
    el.textContent = message;
    el.classList.remove('hidden');
}

function initKbHandlers() {
    document.getElementById('kb-settings-btn')?.addEventListener('click', openKbModal);
    document.getElementById('kb-test-btn')?.addEventListener('click', testKbConnection);
    document.getElementById('kb-save-btn')?.addEventListener('click', saveKbSettings);
    document.getElementById('kb-sync-all-btn')?.addEventListener('click', syncAllResults);
    document.getElementById('kb-enabled-checkbox')?.addEventListener('change', (e) => {
        toggleKbFields(e.target.checked);
    });
    document.getElementById('kb-toggle-visibility-btn')?.addEventListener('click', () => {
        const input = document.getElementById('kb-api-key-input');
        const btn = document.getElementById('kb-toggle-visibility-btn');
        if (input.type === 'password') {
            input.type = 'text';
            btn.textContent = '🔒';
        } else {
            input.type = 'password';
            btn.textContent = '👁️';
        }
    });

    // Close KB modal on backdrop click
    document.getElementById('kb-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'kb-modal') closeKbModal();
    });
}

// SocketIO event handlers for KB sync notifications
function registerKbSocketHandlers() {
    if (!state.socket) return;

    state.socket.on('kb_sync_complete', (data) => {
        showToast(`Synced to OpenWebUI KB (job: ${data.job_id?.substring(0, 8)}...)`, 'success');
    });

    state.socket.on('kb_sync_error', (data) => {
        showToast(`KB sync failed: ${data.error}`, 'error');
    });
}
