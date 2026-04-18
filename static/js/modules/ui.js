// UI utilities: toasts, modals, formatting, helpers
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatFrameAnalysis(text, maxLength = 300) {
    if (!text) return '';

    const escaped = escapeHtml(text);
    if (text.length <= maxLength) {
        return escaped;
    }

    const short = escaped.substring(0, maxLength);
    const full = escaped;
    const id = 'frame_' + Math.random().toString(36).substr(2, 9);

    return `
        <span id="${id}_short">${short}... <a href="javascript:void(0)" onclick="toggleFrameAnalysis('${id}', true)" style="color:var(--accent-primary);font-size:0.85rem;">Show More</a></span>
        <span id="${id}_full" style="display:none;">${full} <a href="javascript:void(0)" onclick="toggleFrameAnalysis('${id}', false)" style="color:var(--accent-primary);font-size:0.85rem;">Show Less</a></span>
    `;
}

function toggleFrameAnalysis(id, showFull) {
    const shortEl = document.getElementById(id + '_short');
    const fullEl = document.getElementById(id + '_full');

    if (shortEl && fullEl) {
        if (showFull) {
            shortEl.style.display = 'none';
            fullEl.style.display = 'inline';
        } else {
            shortEl.style.display = 'inline';
            fullEl.style.display = 'none';
        }
    }
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    Object.assign(toast.style, {
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        padding: '1rem 1.5rem',
        background: type === 'error' ? 'var(--error)' : type === 'success' ? 'var(--success)' : 'var(--info)',
        color: 'white',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        zIndex: '10000',
        animation: 'slideInRight 0.3s ease'
    });

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function closeModal() {
    document.getElementById('job-modal').classList.add('hidden');
}

function updateStartButton() {
    const video = document.getElementById('video-select')?.value;
    const provider = document.getElementById('provider-select')?.value;
    const model = document.getElementById('model-select')?.value;

    const btn = document.getElementById('start-btn');
    if (btn) btn.disabled = !(video && provider && model);
}

function requestNotificationPermission() {
    if (!('Notification' in window)) {
        showToast('Notifications not supported', 'warning');
        return;
    }

    Notification.requestPermission().then(permission => {
        const btn = document.getElementById('notifications-btn');
        if (permission === 'granted') {
            btn.textContent = '🔔';
            btn.title = 'Notifications enabled';
            showToast('Notifications enabled');
        } else {
            btn.textContent = '🔕';
            btn.title = 'Notifications disabled';
        }
    });
}
