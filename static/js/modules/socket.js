// Socket.IO connection and event handlers
function initSocket() {
    state.socket = io();

    state.socket.on('connect', () => {
        console.log('Connected to server');
    });

    state.socket.on('job_created', (data) => {
        handleJobCreated(data);
    });

    state.socket.on('job_update', (data) => {
        handleJobUpdate(data);
    });

    state.socket.on('job_status', (data) => {
        handleJobStatus(data);
    });

    state.socket.on('frame_analysis', (data) => {
        handleFrameAnalysis(data);
    });

    state.socket.on('job_transcript', (data) => {
        handleJobTranscript(data);
    });

    state.socket.on('job_description', (data) => {
        handleJobDescription(data);
    });

    state.socket.on('job_complete', (data) => {
        handleJobComplete(data);
    });

    state.socket.on('videos_updated', () => {
        loadVideos();
    });

    state.socket.on('transcode_progress', (data) => {
        handleTranscodeProgress(data);
    });

    state.socket.on('frame_extraction_progress', (data) => {
        handleFrameExtractionProgress(data);
    });

    state.socket.on('transcription_progress', (data) => {
        handleTranscriptionProgress(data);
    });

    state.socket.on('system_status', (data) => {
        handleSystemStatus(data);
    });

    state.socket.on('vram_event', (data) => {
        handleVramEvent(data);
    });
}

function subscribeToJob(jobId) {
    if (state.socket) {
        state.socket.emit('subscribe_job', { job_id: jobId });
    }
}

function unsubscribeFromJob(jobId) {
    if (state.socket) {
        state.socket.emit('unsubscribe_job', { job_id: jobId });
    }
}

function startAnalysis(data) {
    if (state.socket) {
        state.socket.emit('start_analysis', data);
    }
}
