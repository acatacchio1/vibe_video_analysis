// Global state for Video Analyzer Web
const state = {
    debug: new URLSearchParams(window.location.search).has('debug') ||
            localStorage.getItem('va_debug') === 'true',
    providers: {},
    currentJob: null,
    currentJobResults: null,
    settings: JSON.parse(localStorage.getItem('va_settings') || '{}'),
    analysisVideoName: '',  // filename of the video currently being / last analyzed
    frameBrowser: {
        videoName: '',
        totalFrames: 0,
        fps: 1,
        duration: 0,
        startFrame: 1,
        endFrame: 0,
        thumbCache: new Map(),
        transcript: null,
        debounceTimer: null,
    },
    socket: null,
};

function saveStateToLocalStorage() {
    if (state.settings) {
        localStorage.setItem('va_settings', JSON.stringify(state.settings));
    }
}
