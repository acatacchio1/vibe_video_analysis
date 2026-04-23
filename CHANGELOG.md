# Changelog

All notable changes to Video Analyzer Web will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-04-23

### Added
- **Two-step video analysis system**: Concurrent Phase 1 (vision-only) + Phase 2 (vision+transcript synthesis) processing
- **Separate provider configuration**: Users can select different Ollama instances/models/temperature for each phase
- **Dual view interface**: "Vision Analysis" tab shows Phase 1 results, "Combined Analysis" tab shows Phase 2 synthesized results
- **Live concurrent monitoring**: Real-time updates for both analysis phases via SocketIO events
- **Phase 2 provider selection UI**: Dynamic dropdowns for selecting secondary LLM provider, model, and temperature
- **Warning system**: Alerts users when using same provider for both phases without blocking
- **Synthesis queue system**: Concurrent execution of Phase 2 analysis alongside Phase 1 completion

### Changed
- **Worker architecture**: Modified `worker.py` to support concurrent synthesis via `synthesize_frame()` function
- **WebSocket event handling**: Added `frame_synthesis` event for real-time Phase 2 updates
- **Frontend job handling**: Enhanced `jobs.js` with `appendCombinedLog()` and tab switching functionality
- **Configuration management**: Updated `config/default_config.json` with `analysis_pipeline` settings
- **Documentation**: Updated AGENTS.md and ARCHITECTURE_DECISIONS.md with two-step analysis details
- **Default models**: Changed Phase 2 default to `qwen3.5:9b-q8-128k` (available model)

### Fixed
- **Phase 2 provider selection**: Fixed duplicate function definitions and missing event listeners in `providers.js`
- **WebSocket parameter passing**: Updated `src/websocket/handlers.py` to correctly pass Phase 2 config from frontend
- **Docker container issues**: Fixed default Phase 2 URL from `localhost:11434` to `192.168.1.237:11434` (reachable instance)
- **Configuration serialization**: Fixed Phase 2 config not being included in job `params` object
- **Thumbnail display**: Fixed blank thumbnails in combined analysis view
- **Model availability**: Changed default from non-existent `llama3.1:8b` to available `qwen3.5:9b-q8-128k`

### Performance
- **Concurrent execution**: Phase 2 synthesis starts as soon as each frame's Phase 1 analysis completes
- **Resource distribution**: Work can be distributed across multiple Ollama instances (e.g., .237 for vision, .241 for synthesis)
- **Memory efficiency**: Synthesis uses separate provider configuration without loading additional models unnecessarily

## [0.4.0] - 2026-04-23

## [0.4.0] - 2026-04-23

### Added
- **Comprehensive documentation suite**: API.md, DEVELOPMENT.md, SECURITY.md, TROUBLESHOOTING.md, CONTRIBUTING.md
- **Parallel deduplication** with `dedup_worker.py` for improved performance
- **Scene detection integration** using PySceneDetect (`src/utils/scene_detection.py`)
- **Frame metadata repair utility** (`repair_metadata.py`, `fix_frames_index.py`)
- **New frontend modules**: `scene-detection.js`, `ollama-settings.js`
- **Dedup scheduler** (`src/utils/dedup_scheduler.py`) for intelligent frame selection
- **Parallel file operations** (`src/utils/parallel_file_ops.py`) and hashing (`src/utils/parallel_hash.py`)
- **Robust transcript utilities** (`src/utils/transcript.py`) with consistent path resolution

### Changed
- **Documentation overhaul**: Archived outdated docs to `archive/docs/`, consolidated active documentation
- **Enhanced monitor.py** with improved Ollama instance discovery and monitoring
- **Updated providers API** for better model discovery and VRAM estimation
- **Improved Docker configuration** with better caching and layer optimization
- **Frontend UI enhancements** with better progress tracking and error handling
- **Transcode API improvements** with better progress reporting and error recovery

### Fixed
- **Critical transcript handling bug** that caused "'dict' object has no attribute 'text'" errors
- **Dedup integration** with transcript copy consistency
- **Frame browser timestamp accuracy** using `frames_index.json`
- **Ollama connection error handling** in monitor.py
- **Various UI bugs** in frame browser and video management

### Removed
- **Dead code**: YouTube downloader module (`yt_downloader/`), empty directories
- **Unused re-export modules**: `src/utils/file.py`, `src/utils/transcode.py`
- **Scaffolded unused code**: `src/core/`, `src/queue/` directories
- **Outdated documentation**: `CODE_REVIEW_DOCUMENTATION.md`, `IMPROVEMENTS_SUMMARY.md`, `YOUTUBE_INTEGRATION.md`

### Security
- **Enhanced security documentation** with best practices in SECURITY.md
- **Improved input validation** in API routes
- **Better path security** with `verify_path()` utility

## [3.5.0] - Previous Release (now superseded by 0.4.0)

### Added
- **Transcript utility module** (`src/utils/transcript.py`) with consistent path resolution
- **Unified transcript injection** in worker prompts with `{TRANSCRIPT_RECENT}`/`{TRANSCRIPT_PRIOR}` tokens
- **Better validation** for transcript segments with end times
- **Dedup integration** - Transcript copy during dedup process

### Fixed
- Path inconsistency between frontend API and workers for transcript location
- Missing prompt token handling causing silent failures
- Dedup transcript copy race condition
- Missing end times in transcript segments

### Changed
- **Refactored transcription flow** for consistency between upload and analysis phases
- **Frame renumbering** with `frames_index.json` for accurate transcript sync
- **Robust transcript injection** with fallback when tokens not found in prompts

## [0.3.3] - Previous Release

### Added
- **OpenWebUI Knowledge Base integration** with auto-sync after job completion
- **Knowledge Base API client** in `src/services/openwebui_kb.py`
- **Knowledge Base settings UI** in frontend modules
- **Test connection** functionality for OpenWebUI KB

### Fixed
- Various bug fixes and stability improvements
- Improved error handling for external API calls

## [0.3.2] - Previous Release

### Added
- **Scene detection integration** with PySceneDetect
- **Scene-aware deduplication** for more intelligent frame selection
- **Scene statistics** and visualization in results
- **Scene detection configuration** in settings

### Changed
- **Dedup scheduler** now considers scene boundaries
- **Frame browser** shows scene transitions

## [0.2.0] - Major Refactor

### Added
- **Modular architecture** with `src/` directory structure
- **Flask blueprints** for API endpoints (`src/api/*.py`)
- **SocketIO handlers** in `src/websocket/handlers.py`
- **Worker module** in `src/worker/main.py`
- **Utility modules** for security, video, helpers
- **Frontend modularization** with 13 JS modules
- **Source video preservation** (originals no longer deleted after transcode)

### Changed
- **Monolithic app.py split** into logical modules
- **Frontend refactored** from 2267-line monolith to modular JS
- **Directory structure** reorganized for maintainability
- **Port changed** to 10000 (non-privileged)

### Removed
- Legacy code organization
- Inline frontend JavaScript
- Hardcoded paths and constants

## Breaking Changes

### Version 3.5.0
- No breaking changes

### Version 0.3.4
- Transcript format now requires end times for all segments
- `{TRANSCRIPT_RECENT}` and `{TRANSCRIPT_PRIOR}` token support required for full functionality

### Version 0.2.0
- API routes moved under `/api/` prefix
- Frontend JavaScript completely refactored
- Port changed from 1000 to 10000
- Source videos preserved (not deleted after transcode)

## Upgrade Notes

### From 3.5.0 to 0.4.0
1. Update VERSION file to 0.4.0
2. Restart application
3. No data migration required - new features automatically available

### From 0.2.x to 0.3.4
1. Update prompts to include `{TRANSCRIPT_RECENT}` and `{TRANSCRIPT_PRIOR}` tokens
2. Ensure transcript segments have end times
3. Verify frame_index.json exists for accurate timestamp mapping

### From pre-0.2.0 to 0.2.0
1. Update API client to use `/api/` prefix
2. Update bookmarks to use port 10000
3. Verify source videos are preserved as expected

## Known Issues

- No authentication/authorization system
- Permissive CORS configuration (`cors_allowed_origins="*"`)
- Input validation gaps in some API routes
- Monolithic app.py violates Single Responsibility Principle

## Deprecated Features

- YouTube downloader integration (removed in 3.5.0)
- Direct port 1000 access (changed to 10000 in 0.2.0)
- Legacy monolithic JavaScript (refactored in 0.2.0)