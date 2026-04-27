# Video Analyzer Web - GUI Documentation

## Overview

Video Analyzer Web uses a single-page interface (`templates/index.html`) with modular JavaScript modules and CSS custom properties. The layout has a left sidebar for video management and system monitoring, and a main content area with tabbed panels for analysis and results.

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  APP HEADER: Title / v0.6.0           [📚][🌐][🐛][🔔]│
├──────────────────┬──────────────────────────────────────┤
│  LEFT SIDEBAR    │  MAIN CONTENT                        │
│                  │                                      │
│  [Upload Area]   │  ┌──────────┬──────────┐             │
│  [Server Log]    │  │ New An.  │ Results  │  MainTabs  │
│  [Proc Videos]   │  ├──────────────────────┤             │
│  [Source Videos] │  │ Jobs List               │          │
│                  │  │ New Analysis Form        │          │
│  System Status   │  │ (Video / Pipeline /     │          │
│  ┌─────────────┐ │  │  Provider / Phase 2)     │          │
│  │ nvidia-smi  │ │  │ Live Analysis Display    │          │
│  └─────────────┘ │  │ (Vision / Combined tabs) │          │
│  ┌─────────────┐ │  │ Transcript / Description │          │
│  │  ollama ps  │ │  └──────────────────────────┘          │
│  └─────────────┘ │                                          │
└──────────────────┴──────────────────────────────────────┘
```

## Header Actions

| Button | Action | Handler |
|--------|--------|---------|
| 📚 | Open OpenWebUI Knowledge Base settings modal | `knowledge.js` |
| 🌐 | Open Ollama Instances management modal | `ollama-settings.js` |
| 🐛 | Toggle debug mode (enables detailed server log) | `settings.js` |
| 🔔 | Enable browser notifications for job completion | `settings.js` |

## Left Sidebar

### 1. Upload Video

Drag-and-drop or click to upload video files. Upload settings (⚙️) control:
- **Whisper Model**: `tiny`, `base`, `small`, `medium`, `large` — used for the initial upload transcript

**Upload Processing** (`videos.js`):
1. Video uploaded via XHR to `POST /api/videos/upload`
2. Parallel frame extraction and audio transcription
3. Progress shown in real-time with two track bars (Frame Extraction + Audio Transcription)
4. On completion, `videos_updated` event refreshes both video lists

### 2. Server Log

Scrollable log panel receiving `log_message` SocketIO events from the server. Shows `DEBUG`, `INFO`, `WARNING`, and `ERROR` levels. Clearable via the 🗑️ button.

### 3. Processed Videos

Videos that have been extracted (frames + transcript). Each entry shows filename, duration, frame count, and has:
- **Remove** button — deletes video, frames, and associated data
- **Click** — selects as the analysis target video

### 4. Source Videos

Original uploaded files (preserved source). Supports bulk deletion via "Delete All" button. Click a source video to reprocess (extract frames + transcribe).

### 5. System Status

- **VRAM Display**: Per-GPU VRAM usage cards with bar indicators
- **Monitor Tabs**: Toggle between `nvidia-smi` output (10s polling) and `ollama ps` output (15s polling)
- Powered by `system.js` which subscribes to `system_status` and `vram_event` SocketIO events

## Main Content Tabs

### Tab 1: New Analysis

#### Analysis Jobs List

Shows all active and completed jobs with status indicators:
- **Queued**: Waiting for GPU availability
- **Running**: Active analysis with progress bar
- **Complete**: Finished — click to view results modal
- **Failed**: Error with description

Supports cancellation via DELETE `/api/jobs/<id>`.

#### New Analysis Form

The form is built in sections:

**Video Selection**
- Video dropdown populated from processed videos list
- Pipeline selector: `standard_two_step` (default) or `linkedin_extraction`
- Dedup preview table with multi-scan support (thresholds 5, 10, 15, 20, 30)
- "Scan" button triggers `POST /api/videos/<name>/dedup-multi`

**Scene Detection** (`scene-detection.js`)
- Threshold input + "Detect Scenes" button
- Scene-aware deduplication checkbox — preserves scene-boundary frames
- Results show scene count, frame ranges, and time spans
- "Apply to Analysis" integrates scene info into the analysis pipeline

**Frame Range** (`frame-browser.js`)
- Dual-range slider for selecting start/end frames
- Thumbnail preview cards with step controls (-1 / +1)
- Timestamp display synced to `frames_index.json`
- Transcript context shown for selected frames

**Vision Analysis (Phase 1)**
- Provider selector (Ollama instances + OpenRouter)
- Model dropdown — populated dynamically after provider selection
- Cost/VRAM estimate display for OpenRouter providers
- Priority (0-100, higher = runs sooner)
- Temperature (0.0-2.0)

**Combined Analysis (Phase 2)**
- Phase 2 Provider selector — can differ from Phase 1
- Phase 2 Model dropdown — loaded from selected provider
- Phase 2 Temperature
- Warning shown if Phase 1 and Phase 2 use the same provider/model
- Powered by `providers.js` phase2 handlers

**LinkedIn Pipeline** (shown only when `linkedin_extraction` selected)
- Hook Strength Weight slider (0-25)
- Ideal duration min/max (seconds)
- Generate video clips checkbox (ffmpeg trimming)
- Auto-suggest captions checkbox

**User Question / Prompt**
- Text area for custom analysis questions

**Start Analysis**
- Disabled until all required fields filled
- Triggers `start_analysis` SocketIO event with full config payload

#### Live Analysis Display

Appears after starting analysis. Contains:
- **Analysis Tabs**: "Vision Analysis" (Phase 1) / "Combined Analysis" (Phase 2)
- **Frames Log**: Scrollable panel receiving `frame_analysis` / `frame_synthesis` events
- **Transcript Panel**: Populated by `job_transcript` event
- **Description Panel**: Populated by `job_description` event

### Tab 2: Stored Results

Sidebar list of completed analysis results with detail view panel. Powered by `results.js`:
- Refresh button reloads from `GET /api/results`
- Each result shows video name, completion time, frame count
- Click a result to view full detail (frames, transcript, description, combined analysis)
- Includes LLM chat integration for querying stored results
- "Send to Knowledge Base" button — opens modal for KB selection

## Modals

### 1. Knowledge Base Settings (`knowledge.js`)

OpenWebUI integration configuration:
- Enable/disable KB sync toggle
- URL, API Key (with visibility toggle), Knowledge Base Name
- Auto-sync after analysis checkbox
- Test Connection / Save Settings buttons
- Manual "Sync All Results" action

### 2. Send to Knowledge Base (`knowledge.js`)

For individual job results:
- KB selector dropdown (populated from existing bases)
- Option to create new KB by name
- Job ID display
- Refresh / Send buttons

### 3. Ollama Instances (`ollama-settings.js`)

Manage known Ollama URLs:
- Multi-line textarea for URLs (one per line)
- Save to `config/default_config.json`
- Force Network Scan triggers `discovery.py` subnet scan
- Discovered instances list (read-only)

### 4. Job Details (`jobs.js`)

Detailed job information:
- Job ID, status, stage, progress
- Provider/model configuration
- Phase 1 and Phase 2 settings
- Frame analyses, transcript, description
- Close button dismisses

### 5. Re-dedup Video (`init.js` + `videos.js`)

Re-run deduplication with a custom threshold on already-processed frames:
- Threshold input (0-64)
- Uses existing extracted frames, no re-extraction needed

## JavaScript Module Architecture

Modules loaded in strict dependency order via `<script>` tags in `index.html`:

| Order | Module | Responsibility |
|-------|--------|----------------|
| 1 | `state.js` | Global `state` object, localStorage persistence |
| 2 | `ui.js` | `escapeHtml()`, `showToast()`, `formatBytes()`, `formatFrameAnalysis()` |
| 3 | `socket.js` | Socket.IO connection, all event registration |
| 4 | `videos.js` | Upload, video lists, processing progress, server log |
| 5 | `providers.js` | Provider/model selects, Phase 2 provider handling, discovery |
| 6 | `jobs.js` | Job cards, live updates, detail modal, tab switching |
| 7 | `llm.js` | Chat across 3 contexts (live/modal/results), polling |
| 8 | `frame-browser.js` | Dual-range sliders, thumbnails, transcript context, scene markers |
| 9 | `scene-detection.js` | PySceneDetect integration, scene-aware dedup UI |
| 10 | `system.js` | GPU status display, monitor tab switching |
| 11 | `results.js` | Stored results browser, detail view, LLM chat in results |
| 12 | `settings.js` | Settings persistence, debug toggle, advanced options |
| 13 | `ollama-settings.js` | Ollama instances management modal |
| 14 | `knowledge.js` | OpenWebUI KB settings, send-to-KB modal |
| 15 | `init.js` | DOMContentLoaded bootstrap, event wiring, `submitAnalysis()` |

**No build step**: All modules are plain scripts loaded via `<script>` tags. No ES modules, no bundler.

## Global State Object (`state.js`)

```
state {
  debug:            boolean  — debug mode flag
  providers:        array    — loaded provider list
  currentJob:       object   — active analysis job
  currentJobResults: object  — job analysis results
  settings:         object   — persisted user settings
  analysisVideoName: string  — selected video for analysis
  frameBrowser:     object   — frame range slider state
  currentVideo:     object   — selected video metadata
  socket:           object   — Socket.IO client instance
}
```

State is persisted to localStorage via `saveStateToLocalStorage()`.

## CSS Styling

All styles in `static/css/style.css` (~3339 lines). Uses CSS custom properties:

```css
:root {
  --color-bg-primary: #0f0f0f;
  --color-bg-secondary: #1a1a1a;
  --color-bg-card: #242424;
  --color-text-primary: #e8e8e8;
  --color-text-muted: #888;
  --color-accent: #4a9eff;
  --color-accent-hover: #3a8eef;
  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
}
```

Dark theme throughout. No inline styles (except dynamic toast positioning via `Object.assign`).
