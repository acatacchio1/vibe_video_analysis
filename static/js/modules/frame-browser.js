// Frame browser: range selection, thumbnails, transcript context
async function initFrameBrowserForSelectedVideo() {
    const select = document.getElementById('video-select');
    const option = select.selectedOptions[0];
    if (!option || !select.value) {
        hideFrameBrowser();
        return;
    }
    const videoName = option.dataset.name || option.textContent;
    await initFrameBrowser(videoName);
}

async function initFrameBrowser(videoName) {
    const section = document.getElementById('frame-range-section');
    const fb = state.frameBrowser;

    fb.videoName = videoName;
    fb.thumbCache.clear();
    fb.transcript = null;

    try {
        const response = await fetch(`/api/videos/${encodeURIComponent(videoName)}/frames`);
        const meta = await response.json();

        if (!meta.frame_count || meta.frame_count === 0) {
            section.classList.add('hidden');
            document.getElementById('frame-range-summary').textContent = 'No frames extracted yet for this video';
            return;
        }

        fb.totalFrames = meta.frame_count;
        fb.fps = meta.fps || 1;
        fb.duration = meta.duration || 0;
        fb.startFrame = 1;
        fb.endFrame = fb.totalFrames;

        const startSlider = document.getElementById('start-frame-slider');
        const endSlider = document.getElementById('end-frame-slider');
        const startInput = document.getElementById('start-frame-input');
        const endInput = document.getElementById('end-frame-input');

        startSlider.min = 1;
        startSlider.max = fb.totalFrames;
        startSlider.value = 1;
        endSlider.min = 1;
        endSlider.max = fb.totalFrames;
        endSlider.value = fb.totalFrames;

        startInput.min = 1;
        startInput.max = fb.totalFrames;
        startInput.value = 1;
        endInput.min = 1;
        endInput.max = fb.totalFrames;
        endInput.value = fb.totalFrames;

        section.classList.remove('hidden');
        updateRangeHighlight();
        updateFrameRangeSummary();
        loadFrameThumb('start', 1);
        loadFrameThumb('end', fb.totalFrames);

        try {
            const transcriptResp = await fetch(`/api/videos/${encodeURIComponent(videoName)}/transcript`);
            fb.transcript = await transcriptResp.json();
        } catch (e) {
            console.warn('Failed to load transcript for frame browser:', e);
            fb.transcript = null;
        }

        updateTranscriptContext('start', 1);
        updateTranscriptContext('end', fb.totalFrames);
    } catch (error) {
        console.error('Failed to load frame metadata:', error);
        section.classList.add('hidden');
    }
}

function hideFrameBrowser() {
    const section = document.getElementById('frame-range-section');
    section.classList.add('hidden');
    state.frameBrowser.totalFrames = 0;
}

function updateRangeHighlight() {
    const fb = state.frameBrowser;
    if (fb.totalFrames === 0) return;

    const startPct = ((fb.startFrame - 1) / fb.totalFrames) * 100;
    const endPct = ((fb.endFrame - 1) / fb.totalFrames) * 100;

    const highlight = document.getElementById('range-highlight');
    if (highlight) {
        highlight.style.left = `${startPct}%`;
        highlight.style.width = `${endPct - startPct}%`;
    }
}

function updateFrameRangeSummary() {
    const fb = state.frameBrowser;
    const summary = document.getElementById('frame-range-summary');
    if (!summary) return;

    const rangeCount = fb.endFrame - fb.startFrame + 1;
    const rangeDuration = rangeCount / fb.fps;
    summary.textContent = `Selected: ${rangeCount} frames (${formatDurationShort(rangeDuration)}) of ${fb.totalFrames} total`;
}

function formatDurationShort(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    if (m < 60) return `${m}m ${s}s`;
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return `${h}h ${rm}m`;
}

function handleStartSliderChange(e) {
    const fb = state.frameBrowser;
    let val = parseInt(e.target.value);
    if (val >= fb.endFrame) val = fb.endFrame - 1;
    if (val < 1) val = 1;
    fb.startFrame = val;
    document.getElementById('start-frame-input').value = val;
    e.target.value = val;
    updateRangeHighlight();
    updateFrameRangeSummary();
    updateFrameTime('start', val);
    debouncedLoadFrameThumb('start', val);
    updateTranscriptContext('start', val);
}

function handleEndSliderChange(e) {
    const fb = state.frameBrowser;
    let val = parseInt(e.target.value);
    if (val <= fb.startFrame) val = fb.startFrame + 1;
    if (val > fb.totalFrames) val = fb.totalFrames;
    fb.endFrame = val;
    document.getElementById('end-frame-input').value = val;
    e.target.value = val;
    updateRangeHighlight();
    updateFrameRangeSummary();
    updateFrameTime('end', val);
    debouncedLoadFrameThumb('end', val);
    updateTranscriptContext('end', val);
}

function handleStartInputChange(e) {
    const fb = state.frameBrowser;
    let val = parseInt(e.target.value) || 1;
    val = Math.max(1, Math.min(val, fb.endFrame - 1));
    fb.startFrame = val;
    document.getElementById('start-frame-slider').value = val;
    e.target.value = val;
    updateRangeHighlight();
    updateFrameRangeSummary();
    updateFrameTime('start', val);
    loadFrameThumb('start', val);
    updateTranscriptContext('start', val);
}

function handleEndInputChange(e) {
    const fb = state.frameBrowser;
    let val = parseInt(e.target.value) || fb.totalFrames;
    val = Math.max(fb.startFrame + 1, Math.min(val, fb.totalFrames));
    fb.endFrame = val;
    document.getElementById('end-frame-slider').value = val;
    e.target.value = val;
    updateRangeHighlight();
    updateFrameRangeSummary();
    updateFrameTime('end', val);
    loadFrameThumb('end', val);
    updateTranscriptContext('end', val);
}

function handleFrameStep(which, direction) {
    const fb = state.frameBrowser;
    if (which === 'start') {
        let val = fb.startFrame + direction;
        val = Math.max(1, Math.min(val, fb.endFrame - 1));
        fb.startFrame = val;
        document.getElementById('start-frame-input').value = val;
        document.getElementById('start-frame-slider').value = val;
        updateFrameTime('start', val);
        loadFrameThumb('start', val);
        updateTranscriptContext('start', val);
    } else {
        let val = fb.endFrame + direction;
        val = Math.max(fb.startFrame + 1, Math.min(val, fb.totalFrames));
        fb.endFrame = val;
        document.getElementById('end-frame-input').value = val;
        document.getElementById('end-frame-slider').value = val;
        updateFrameTime('end', val);
        loadFrameThumb('end', val);
        updateTranscriptContext('end', val);
    }
    updateRangeHighlight();
    updateFrameRangeSummary();
}

function updateFrameTime(which, frameNum) {
    const fb = state.frameBrowser;
    const seconds = (frameNum - 1) / fb.fps;
    const el = document.getElementById(`${which}-frame-time`);
    if (el) el.textContent = formatDurationShort(seconds);
}

function debouncedLoadFrameThumb(which, frameNum) {
    clearTimeout(state.frameBrowser.debounceTimer);
    state.frameBrowser.debounceTimer = setTimeout(() => {
        loadFrameThumb(which, frameNum);
    }, 100);
}

function loadFrameThumb(which, frameNum) {
    const fb = state.frameBrowser;
    const img = document.getElementById(`${which}-frame-thumb`);
    const placeholder = document.getElementById(`${which}-thumb-placeholder`);
    if (!img || !fb.videoName) return;

    if (fb.thumbCache.has(frameNum)) {
        img.src = fb.thumbCache.get(frameNum);
        img.style.display = 'block';
        if (placeholder) placeholder.style.display = 'none';
        return;
    }

    const thumbUrl = `/api/videos/${encodeURIComponent(fb.videoName)}/frames/${frameNum}/thumb`;
    img.src = thumbUrl;
    img.style.display = 'block';
    if (placeholder) placeholder.style.display = 'none';
    fb.thumbCache.set(frameNum, thumbUrl);

    if (fb.thumbCache.size > 200) {
        const oldest = fb.thumbCache.keys().next().value;
        fb.thumbCache.delete(oldest);
    }
}

function updateTranscriptContext(which, frameNum) {
    const fb = state.frameBrowser;
    const el = document.getElementById(`${which}-frame-transcript`);
    if (!el) return;

    if (!fb.transcript || !fb.transcript.segments || fb.transcript.segments.length === 0) {
        el.textContent = '';
        el.classList.add('empty');
        return;
    }

    const timestamp = (frameNum - 1) / fb.fps;
    const windowBefore = 3;
    const windowAfter = 3;
    const windowStart = timestamp - windowBefore;
    const windowEnd = timestamp + windowAfter;

    const matching = fb.transcript.segments.filter(seg => {
        return seg.start >= windowStart && seg.start <= windowEnd;
    });

    if (matching.length === 0) {
        el.textContent = 'No speech at this point';
        el.classList.add('empty');
        return;
    }

    el.classList.remove('empty');
    el.textContent = matching.map(s => s.text.trim()).join(' ');
}
