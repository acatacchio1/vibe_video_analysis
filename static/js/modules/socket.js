// Socket.IO connection and event handlers
function debugLog(tag, data) {
    if (state.debug) {
        console.log(`[DEBUG:${tag}]`, data);
    }
}

function initSocket() {
    state.socket = io();

    state.socket.on('connect', () => {
        debugLog('SOCKET', 'connect');
        console.log('Connected to server');
    });

    state.socket.on('job_created', (data) => {
        debugLog('RECV:job_created', data);
        handleJobCreated(data);
    });

    state.socket.on('job_update', (data) => {
        debugLog('RECV:job_update', data);
        handleJobUpdate(data);
    });

    state.socket.on('job_status', (data) => {
        debugLog('RECV:job_status', data);
        handleJobStatus(data);
    });

    state.socket.on('frame_analysis', (data) => {
        debugLog('RECV:frame_analysis', { frame: data.frame_number || data.frame, analysis_len: (data.analysis || data.response || '').length });
        handleFrameAnalysis(data);
    });

    state.socket.on('frame_synthesis', (data) => {
        debugLog('RECV:frame_synthesis', { frame: data.frame_number || data.frame, combined_len: (data.combined_analysis || '').length });
        handleFrameSynthesis(data);
    });

    state.socket.on('job_transcript', (data) => {
        debugLog('RECV:job_transcript', { job_id: data.job_id, text_len: (data.transcript || '').length });
        handleJobTranscript(data);
    });

    state.socket.on('job_description', (data) => {
        debugLog('RECV:job_description', { job_id: data.job_id, text_len: (data.description || '').length });
        handleJobDescription(data);
    });

    state.socket.on('job_complete', (data) => {
        debugLog('RECV:job_complete', data);
        handleJobComplete(data);
    });

    state.socket.on('videos_updated', () => {
        debugLog('RECV:videos_updated', {});
        loadVideos();
    });

    state.socket.on('transcode_progress', (data) => {
        debugLog('RECV:transcode_progress', data);
        handleTranscodeProgress(data);
    });

    state.socket.on('video_processing_progress', (data) => {
        debugLog('RECV:video_processing_progress', data);
        handleVideoProcessingProgress(data);
    });

    state.socket.on('frame_extraction_progress', (data) => {
        debugLog('RECV:frame_extraction_progress', data);
        handleFrameExtractionProgress(data);
    });

    state.socket.on('transcription_progress', (data) => {
        debugLog('RECV:transcription_progress', data);
        handleTranscriptionProgress(data);
    });

    state.socket.on('system_status', (data) => {
        debugLog('RECV:system_status', { type: data.type });
        handleSystemStatus(data);
    });

    state.socket.on('vram_event', (data) => {
        debugLog('RECV:vram_event', data);
        handleVramEvent(data);
    });

    state.socket.on('log_message', (data) => {
        appendServerLog(data);
    });

    state.socket.on('kb_sync_complete', (data) => {
        debugLog('RECV:kb_sync_complete', data);
        showToast(`Synced to OpenWebUI KB (job: ${data.job_id?.substring(0, 8)}...)`, 'success');
    });

    state.socket.on('kb_sync_error', (data) => {
        debugLog('RECV:kb_sync_error', data);
        showToast(`KB sync failed: ${data.error}`, 'error');
    });
}

function subscribeToJob(jobId) {
    if (state.socket) {
        debugLog('EMIT:subscribe_job', { job_id: jobId });
        state.socket.emit('subscribe_job', { job_id: jobId });
    }
}

function unsubscribeFromJob(jobId) {
    if (state.socket) {
        debugLog('EMIT:unsubscribe_job', { job_id: jobId });
        state.socket.emit('unsubscribe_job', { job_id: jobId });
    }
}

function startAnalysis(data) {
    if (state.socket) {
        debugLog('EMIT:start_analysis', data);
        state.socket.emit('start_analysis', data);
    }
}
