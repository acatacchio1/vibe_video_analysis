// OpenWebUI Knowledge Base integration
const kbState = {
    enabled: false,
    url: '',
    apiKey: '',
    kbName: 'Video Analyzer',
    autoSync: true,
};

const sendKbState = {
    bases: [],
    selectedJobId: null,
};

// ===== Settings Modal =====

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

// ===== Send to KB Modal =====

function closeSendKbModal() {
    document.getElementById('send-kb-modal')?.classList.add('hidden');
}

function openSendKbModal(jobId) {
    const modal = document.getElementById('send-kb-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    sendKbState.selectedJobId = jobId || state.currentJob;
    document.getElementById('send-kb-job-id').textContent = sendKbState.selectedJobId?.substring(0, 12) || '--';
    document.getElementById('send-kb-status')?.classList.add('hidden');
    document.getElementById('send-kb-new-row')?.classList.add('hidden');
    loadSendKbBases();
}

async function loadSendKbBases() {
    const select = document.getElementById('send-kb-select');
    if (!select) return;

    select.innerHTML = '<option value="">Loading...</option>';

    try {
        const resp = await fetch('/api/knowledge/bases');
        const data = await resp.json();

        if (data.error) {
            select.innerHTML = `<option value="">Error: ${data.error}</option>`;
            return;
        }

        sendKbState.bases = data.bases || [];
        select.innerHTML = '<option value="">-- Select existing --</option>' +
            sendKbState.bases.map(b => `<option value="${b.id}">${b.name}</option>`).join('') +
            '<option value="__new__">+ Create new knowledge base</option>';
    } catch (e) {
        select.innerHTML = '<option value="">Failed to load</option>';
    }
}

async function submitSendToKb() {
    const select = document.getElementById('send-kb-select');
    const value = select?.value;
    const statusEl = document.getElementById('send-kb-status');

    if (!value) {
        showSendKbStatus('error', 'Select or create a knowledge base');
        return;
    }

    const jobId = sendKbState.selectedJobId;
    if (!jobId) {
        showSendKbStatus('error', 'No job selected');
        return;
    }

    showSendKbStatus('info', 'Sending to knowledge base...');

    let kbId, kbName;
    if (value === '__new__') {
        kbName = document.getElementById('send-kb-name-input')?.value.trim();
        if (!kbName) {
            showSendKbStatus('error', 'Enter a name for the new knowledge base');
            return;
        }
    } else {
        kbId = value;
        const base = sendKbState.bases.find(b => b.id === kbId);
        kbName = base?.name || '';
    }

    try {
        const resp = await fetch(`/api/knowledge/send/${encodeURIComponent(jobId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kb_id: kbId !== '__new__' ? kbId : undefined, kb_name: kbName }),
        });
        const data = await resp.json();

        if (data.success) {
            showSendKbStatus('success', `Sent to "${data.kb_name}"`);
            showToast(`Sent to knowledge base "${data.kb_name}"`);
        } else {
            showSendKbStatus('error', data.error || 'Failed to send');
        }
    } catch (e) {
        showSendKbStatus('error', `Error: ${e.message}`);
    }
}

function showSendKbStatus(type, message) {
    const el = document.getElementById('send-kb-status');
    if (!el) return;
    el.className = `kb-status ${type}`;
    el.textContent = message;
    el.classList.remove('hidden');
}

// ===== Init =====

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

    document.getElementById('kb-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'kb-modal') closeKbModal();
    });

    // Send to KB modal
    document.getElementById('send-to-kb-btn')?.addEventListener('click', () => openSendKbModal());
    document.getElementById('send-kb-submit-btn')?.addEventListener('click', submitSendToKb);
    document.getElementById('send-kb-refresh-btn')?.addEventListener('click', loadSendKbBases);
    document.getElementById('send-kb-select')?.addEventListener('change', (e) => {
        const newRow = document.getElementById('send-kb-new-row');
        if (newRow) {
            if (e.target.value === '__new__') {
                newRow.classList.remove('hidden');
            } else {
                newRow.classList.add('hidden');
            }
        }
    });

    document.getElementById('send-kb-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'send-kb-modal') closeSendKbModal();
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
