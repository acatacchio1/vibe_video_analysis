# Workflow State

## Request
Fill StandardTwoStepPipeline skeleton from v0.5.1 and update worker.py to dispatch all analysis through the pipeline factory.

## Clarifications
- Do not modify LinkedInExtractionPipeline
- Aggressive cleanup acceptable — zero risk constraint removed
- Use Pydantic v2 for typed configuration models

## Acceptance Criteria
- [x] StandardTwoStepPipeline implements all skeleton methods with identical logic to worker.py inline code
- [x] Pipeline factory registers both `linkedin_extraction` and `standard_two_step`
- [x] worker.py dispatches both pipeline types through `create_pipeline()`
- [x] Inline standard analysis code removed from worker.py (pure dispatcher now)
- [x] Pydantic schemas created for JobConfig, AnalysisParams, and nested configs
- [x] Pipeline factory automatically builds typed JobConfig from raw dict
- [x] StandardTwoStepPipeline uses typed config (dot notation) instead of raw dict access
- [x] All files pass syntax checks
- [x] Pipeline instantiation works in worker subprocess context
- [x] AGENTS.md updated with new architecture

## Plan
1. Fill StandardTwoStepPipeline skeleton methods
2. Update pipeline factory registry
3. Update worker.py dispatch logic
4. Remove inline fallback from worker.py
5. Create Pydantic schemas (src/schemas/)
6. Integrate typed config into pipeline base class and factory
7. Refactor StandardTwoStepPipeline to use typed config
8. Update documentation (AGENTS.md, WORKFLOW_STATE.md)

## Implementation Notes
- StandardTwoStepPipeline fully implemented in `src/worker/pipelines/standard_two_step.py` (~1033 lines)
- All stages match inline worker.py logic: config build, audio extraction/transcription, frame preparation, frame analysis (Phase 1 + Phase 2 synthesis), video reconstruction, results save, auto-LLM queue
- `_synthesize_frame` helper kept as module-level function in standard_two_step.py
- `_safe_get_transcript_text` and `_safe_get_transcript_segments` duplicated into pipeline to avoid import issues in subprocess
- Added missing `import os` to standard_two_step.py for `APP_URL` env var fallback
- worker.py now routes both `linkedin_extraction` and `standard_two_step` through `create_pipeline()`
- worker.py reduced from ~1242 lines to ~85 lines (pure dispatcher)
- Pydantic schemas handle legacy flat fields via `model_validator(mode='before')` mapping to nested configs
- `AudioConfig.compute_type` inferred from `device` via `model_validator(mode='after')`
- Unused imports removed from standard_two_step.py (`time`, `traceback`)
- Unused `params` parameter removed from `_analyze_frames` signature

## Changed Files
- `src/worker/pipelines/standard_two_step.py` - Filled skeleton with full implementation, then refactored to typed config
- `src/worker/pipelines/__init__.py` - Registered standard_two_step, added typed config auto-build
- `src/worker/pipelines/base.py` - Added typed config support and `_get_param()` helper
- `worker.py` - Stripped to pure dispatcher (~85 lines)
- `src/schemas/config.py` - New Pydantic schemas
- `src/schemas/__init__.py` - New schema exports
- `src/worker/__init__.py` - Exports pipeline classes instead of legacy run_analysis
- `requirements.txt` - Added pydantic>=2.0
- `AGENTS.md` - Updated architecture docs

## Review Findings
- No logic changes, only relocation into class methods + type safety improvements
- Frontend already supports pipeline selection via `pipeline-select`
- WebSocket handler already passes `pipeline_type` in config

## Test Results
- Syntax check passed for all modified files
- Pipeline factory import test passed
- StandardTwoStepPipeline instantiation with typed config passed
- Legacy flat field mapping to nested configs verified

## Lint Results
- Not run (no linting tool configured)

## Commit Message Draft
refactor: dispatch standard analysis through pipeline factory + pydantic configs

Fill StandardTwoStepPipeline skeleton with full implementation matching
inline worker.py logic. Update worker.py to route both linkedin_extraction
and standard_two_step through create_pipeline(). Remove ~1150 lines of
duplicated inline code from worker.py — now a pure dispatcher.

Add Pydantic v2 schemas (JobConfig, AnalysisParams, nested configs) with
automatic legacy flat-field mapping. Pipeline factory auto-builds typed
config. StandardTwoStepPipeline refactored to use dot-notation typed
access instead of raw dict.get().
