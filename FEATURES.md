# Video Analyzer Web - Feature Summary

## ✅ Implemented Features

### Multi-Provider Support
- [x] **Ollama Discovery**: Auto-discovers Ollama instances on local network via subnet scanning
- [x] **Ollama Integration**: Full support for local Ollama servers with dynamic model loading
- [x] **OpenRouter Integration**: Cloud-based provider with full API support
- [x] **Provider Status**: Real-time online/offline status indicators
- [x] **Custom URLs**: Manual entry of Ollama server URLs

### OpenRouter Cost Management
- [x] **API Key Input**: Modal dialog for entering OpenRouter API key
- [x] **Balance Display**: Shows remaining API balance from OpenRouter
- [x] **Cost Estimation**: Pre-analysis cost estimate based on frame count
- [x] **Budget Validation**: Checks if estimated cost exceeds available balance
- [x] **Frame Limit Suggestion**: Calculates max affordable frames if budget insufficient
- [x] **Live Cost Updates**: Updates actual cost every 10 frames during analysis
- [x] **Pricing Cache**: Caches OpenRouter pricing for 1 hour

### VRAM Management
- [x] **VRAM Detection**: Uses NVML (pynvml) to query actual GPU memory
- [x] **VRAM Estimation**: Estimates required VRAM from Ollama model size + 2GB overhead
- [x] **Smart Queueing**: Queues jobs when insufficient VRAM available
- [x] **Priority Queueing**: Higher priority jobs run first within VRAM constraints
- [x] **Queue Position Display**: Shows position in queue with estimated start
- [x] **Multiple Concurrent Jobs**: Runs multiple jobs if VRAM permits
- [x] **VRAM-Fit Priority**: Smaller jobs can run ahead of larger queued jobs if they fit

### System Monitoring
- [x] **nvidia-smi Updates**: Every 10 seconds via background thread
- [x] **ollama ps Updates**: Every 60 seconds via background thread
- [x] **Real-time Display**: Live terminal output in web interface
- [x] **VRAM Bar**: Visual progress bar showing GPU memory usage
- [x] **Tab Switching**: Toggle between nvidia-smi and ollama ps views

### Video Management
- [x] **Drag & Drop Upload**: HTML5 drag and drop file upload
- [x] **Video List**: Display uploaded videos with metadata
- [x] **Thumbnails**: Auto-extracts thumbnail at 10% duration via ffmpeg
- [x] **Delete Videos**: Individual delete buttons with confirmation
- [x] **Video Duration**: Displays formatted duration from ffprobe
- [x] **File Size**: Human-readable file sizes (MB, GB)

### Video Transcoding
- [x] **One-Click Transcode**: 🎞️ button next to each video
- [x] **FFmpeg Parameters**: `-vf scale=-2:720 -r 10 -c:v libx264 -crf 23 -preset fast -c:a aac -b:a 128k -ar 44100`
- [x] **Output Naming**: Appends `_720p10fps` to filename
- [x] **Auto-thumbnail**: Generates thumbnail for transcoded video
- [x] **Progress Tracking**: Async transcoding with status updates

### Job Management
- [x] **Job States**: Pending → Queued → Running → Completed/Failed
- [x] **Concurrent Jobs**: Spawned as separate subprocesses
- [x] **Job Cards**: Visual cards showing status, progress, metadata
- [x] **Progress Bars**: Visual progress with percentage
- [x] **Stage Display**: Shows current stage (extracting, analyzing, etc.)
- [x] **Frame Counter**: Shows current/total frames during analysis
- [x] **ETA Display**: Estimated time remaining from timing logic
- [x] **Cancel Jobs**: Cancel queued or running jobs
- [x] **View Results**: Modal dialog with full analysis results
- [x] **Download Results**: JSON download of analysis output

### Real-Time Analysis Display
- [x] **Live Frame Log**: Shows each frame analysis as it completes
- [x] **Scrollable History**: Keeps last 50 frame entries
- [x] **Frame Metadata**: Frame number, timestamp, analysis text
- [x] **Animation**: Smooth slide-in animation for new entries
- [x] **Transcript Panel**: Expanding panel showing transcription
- [x] **Description Panel**: Expanding panel with final video description

### WebSocket Events
- [x] **Connection Management**: Auto-reconnect on disconnect
- [x] **Job Subscriptions**: Per-job rooms for targeted updates
- [x] **Status Broadcasts**: Server pushes updates to all clients
- [x] **Frame Events**: Real-time frame analysis delivery
- [x] **System Events**: VRAM and job state change notifications

### Settings Persistence
- [x] **LocalStorage**: Saves all form settings to browser
- [x] **Provider Selection**: Remembers last used provider
- [x] **Model Selection**: Remembers last used model per provider
- [x] **Advanced Options**: Saves temperature, whisper model, etc.
- [x] **API Key Storage**: OpenRouter key saved in localStorage
- [x] **Panel States**: Remembers expanded/collapsed panels

### Browser Notifications
- [x] **Permission Request**: One-click enable notifications
- [x] **Completion Alerts**: Desktop notification on job complete
- [x] **Error Alerts**: Notification on job failure
- [x] **Visual Indicator**: Bell icon shows notification status

### UI/UX Features
- [x] **Dark Theme**: Modern dark UI with accent colors
- [x] **Responsive Layout**: Adapts to different screen sizes
- [x] **Loading States**: Visual feedback during operations
- [x] **Toast Notifications**: Non-intrusive status messages
- [x] **Modal Dialogs**: Job details, confirmations
- [x] **Collapsible Panels**: Advanced options, transcript, description
- [x] **Keyboard Shortcuts**: Accessible form controls

### Docker Deployment
- [x] **Multi-stage Dockerfile**: Optimized build with CUDA base
- [x] **docker-compose.yml**: Complete orchestration with GPU support
- [x] **Volume Mounts**: Persistent storage for uploads, jobs, cache
- [x] **Network Configuration**: Host access for Ollama discovery
- [x] **Health Checks**: Automatic container health monitoring
- [x] **Restart Policy**: Auto-restart on failure
- [x] **Logging**: JSON-file logging with rotation

### Error Handling
- [x] **Graceful Degradation**: Works without GPU (CPU fallback)
- [x] **Provider Failover**: Clear error messages for offline providers
- [x] **Job Recovery**: Job status persisted in filesystem
- [x] **Validation**: Client and server-side form validation
- [x] **User Feedback**: Clear error messages in UI

## 🎯 Usage Flow

1. **Upload**: Drag video or click upload area
2. **Select**: Choose Ollama instance or OpenRouter
3. **API Key**: Enter OpenRouter key if using cloud provider
4. **Model**: Select from dynamically loaded model list
5. **Review**: Check cost estimate (OpenRouter) or VRAM requirements (Ollama)
6. **Configure**: Set max frames, duration, whisper model, temperature
7. **Priority**: Optionally increase priority for faster queue position
8. **Start**: Begin analysis and watch real-time progress
9. **Monitor**: View system status, live frame analysis, ETA updates
10. **Results**: View or download final analysis when complete

## 🔧 Technical Architecture

- **Backend**: Flask + Flask-SocketIO (Python 3.11)
- **Frontend**: Vanilla JS + Socket.IO client
- **Concurrency**: Eventlet async server + subprocess workers
- **GPU**: NVML for VRAM monitoring, CUDA for whisper
- **Video**: FFmpeg for transcoding and thumbnail extraction
- **Container**: NVIDIA Docker runtime for GPU passthrough
- **Queue**: In-memory VRAM-aware priority queue
- **State**: Filesystem-based job persistence

## 📊 Performance Characteristics

- **Max Concurrent Jobs**: Limited by GPU VRAM (typically 2-3)
- **Queue Capacity**: Unlimited (memory constrained)
- **Frame Processing**: Depends on model and provider
- **Network Scan**: ~30 seconds for full subnet
- **Transcoding**: ~1-5 min for typical video
- **WebSocket Latency**: <100ms for status updates
