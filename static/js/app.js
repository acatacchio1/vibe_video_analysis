// Video Analyzer Web - Module Loader
// This file loads all modular JS files. The monolithic app.js has been split into:
//   modules/state.js         - Global state management
//   modules/socket.js        - Socket.IO connection and events
//   modules/videos.js        - Video upload, list, delete, transcode
//   modules/providers.js     - Provider discovery, model loading, OpenRouter
//   modules/jobs.js          - Job creation, rendering, cancellation
//   modules/llm.js           - LLM chat functionality
//   modules/frame-browser.js - Frame range selection and thumbnails
//   modules/system.js        - GPU status and monitor tabs
//   modules/results.js       - Stored results browser
//   modules/settings.js      - Settings persistence
//   modules/ui.js            - Toasts, modals, formatting utilities
//   modules/init.js          - Application bootstrap and event wiring
