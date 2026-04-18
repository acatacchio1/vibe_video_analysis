// System status: GPU display, monitor tabs
function handleSystemStatus(data) {
    if (data.type === 'nvidia_smi') {
        const payload = data.data || {};
        const gpus = payload.gpus || [];
        const text = payload.text || data.error || 'No data';

        document.getElementById('nvidia-output').textContent = text;

        const vramDisplay = document.getElementById('vram-display');
        if (gpus.length > 0) {
            vramDisplay.innerHTML = gpus.map(gpu => {
                const usedGb = (gpu.mem_used_mb / 1024).toFixed(1);
                const totalGb = (gpu.mem_total_mb / 1024).toFixed(1);
                const pct = Math.round(gpu.mem_used_mb * 100 / gpu.mem_total_mb);
                const utilPct = gpu.util_pct || 0;
                return `
                    <div class="gpu-card">
                        <div class="gpu-title">GPU ${gpu.index}: ${gpu.name}</div>
                        <div class="gpu-row">
                            <span>VRAM</span>
                            <div class="mini-bar"><div class="mini-fill" style="width:${pct}%"></div></div>
                            <span class="gpu-val">${usedGb} / ${totalGb} GB</span>
                        </div>
                        <div class="gpu-row">
                            <span>Util</span>
                            <div class="mini-bar"><div class="mini-fill util-fill" style="width:${utilPct}%"></div></div>
                            <span class="gpu-val">${utilPct}%</span>
                        </div>
                    </div>`;
            }).join('');
        } else if (data.error) {
            vramDisplay.innerHTML = `<div class="gpu-error">${data.error}</div>`;
        }

    } else if (data.type === 'ollama_ps') {
        const payload = data.data || {};
        const text = payload.text || data.error || 'No data';
        document.getElementById('ollama-output').textContent = text;
    }
}

function switchMonitorTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.monitor-pre').forEach(p => p.classList.remove('active'));

    document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`${tab}-output`).classList.add('active');
}

function handleVramEvent(data) {
    console.log('VRAM event:', data.event, data.job?.job_id);
}
