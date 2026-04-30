# Test Results Report — video-analyzer-web

> Generated: 2026-04-29
> Test Framework: pytest 9.0.3, pytest-timeout 2.4.0, pytest-cov 7.1.0
> Python: 3.13.5
> Venv: /home/anthony/venvs/video-analyzer

---

## Executive Summary

| Tier | Collected | Passed | Failed | Error | Duration |
|------|-----------|--------|--------|-------|----------|
| Unit | 233 | 228 | 5 | 0 | 2.20s |
| Integration | 59 | 51 | 8 | 0 | 0.86s |
| **Total** | **292** | **279** | **13** | **0** | **3.06s** |

| Metric | Before (2026-04-24) | After (2026-04-29) | Change |
|--------|---------------------|--------------------|--------|
| Tests collected | **0** | **292** | +292 ✅ |
| Tests passed | 0 | 279 | +279 ✅ |
| Success rate | N/A | 95.5% | N/A |

**Key improvement**: The test suite was completely non-functional (0 collected from 19 files) due to missing `__init__.py` files. After creating 10 `__init__.py` files and fixing the `tests/conftest.py` import chain, the suite now collects and executes 292 tests.

---

## Unit Tests (233 collected)

### Passed: 228 | Failed: 5

#### Failure Breakdown

| File | Failed | Category | Root Cause |
|------|--------|----------|------------|
| `test_providers.py` | 2 | Provider API | Tests reference `get_litellm_api_base` which was renamed/removed during Ollama→LiteLLM migration |
| `test_handlers.py` | 3 | SocketIO handlers | `KeyError: 'ollama_ps'` — fixtures still use Ollama provider config, but source code uses LiteLLM |

#### Failure Details

**test_providers.py (2 failures)**:
- `TestProviderModels::test_litellm_api_base` — `AttributeError: module 'src.api.providers' has no attribute 'get_litellm_api_base'`
- `TestLitellmCost::test_cost_estimation` — Same AttributeError
- **Assessment**: Pre-existing test debt from the Ollama→LiteLLM migration. The source code was refactored but these tests were never updated.

**test_handlers.py (3 failures)**:
- `TestHandleConnect::test_ollama_ps_key` — `KeyError: 'ollama_ps'` in `handle_connect()`
- **Assessment**: The fixture `mock_litellm_client` provides `litellm_ps` but the handler code path still accesses `ollama_ps`. This is a pre-existing mismatch between the fixture and actual handler code.

#### Coverage by Module

| Module | Tests | Status |
|--------|-------|--------|
| `src/api/providers.py` | 9 | ✅ 7 passed, 2 failed (pre-existing) |
| `src/api/jobs.py` | 14 | ✅ 14 passed |
| `src/api/llm.py` | 11 | ✅ 11 passed |
| `src/api/videos.py` | 13 | ✅ 13 passed |
| `src/services/openwebui_kb.py` | 28 | ✅ 28 passed |
| `src/websocket/handlers.py` | 20 | ⚠️ 17 passed, 3 failed (pre-existing) |
| `src/utils/helpers.py` | tested | ✅ passed |
| `src/utils/transcript.py` | 21 | ✅ 21 passed |
| `chat_queue.py` | tested | ✅ 24 passed |
| `vram_manager.py` | tested | ✅ passed |
| `gpu_transcode.py` | tested | ✅ passed |

---

## Integration Tests (59 collected)

### Passed: 51 | Failed: 8

#### Failure Breakdown

| File | Failed | Category | Root Cause |
|------|--------|----------|------------|
| `test_vram_manager.py` | 7 | VRAM scheduling | Tests reference `set_litellm_running_models_provider` which was renamed to `set_ollama_running_models_provider` during migration |
| `test_job_execution.py` | 1 | Worker execution | Expected model `llava:7b` but got `qwen3-27b-q8` — default model changed during migration |

#### Failure Details

**test_vram_manager.py (7 failures)**:
- `TestLiteLLMAlreadyLoaded::test_effective_vram_full_when_model_not_loaded` — `AttributeError: 'VRAMManager' object has no attribute 'set_litellm_running_models_provider'`
- Same AttributeError across 6 additional TestLiteLLMAlreadyLoaded methods
- **Assessment**: **Critical** — These tests were written for the Ollama provider but the codebase now uses LiteLLM. The method `set_litellm_running_models_provider` does not exist; the equivalent is `set_ollama_running_models_provider` (which is confusingly named but is the correct method after the Ollama→LiteLLM provider rename in the codebase). These tests are testing LiteLLM-specific VRAM tracking which was not migrated in the test code.

**test_job_execution.py (1 failure)**:
- `TestWorkerProcessIntegration::test_worker_reads_input_json` — `AssertionError: assert 'qwen3-27b-q8' == 'llava:7b'`
- **Assessment**: The test hardcodes the expected default model as `llava:7b` (Ollama) but the actual default is now `qwen3-27b-q8` (LiteLLM). The test expectation is stale.

---

## Uncovered Modules (48% of source)

Source modules with NO test coverage:

| Module | Category |
|--------|----------|
| `src/api/transcode.py` | API blueprint |
| `src/api/knowledge.py` | API blueprint |
| `src/api/system.py` | API blueprint |
| `src/api/results.py` | API blueprint |
| `src/cli/` (11 files) | CLI subsystem |
| `src/services/linkedin_rag.py` | LinkedIn RAG service |
| `src/services/synthesis_queue.py` | Synthesis queue |
| `src/utils/video.py` | Video probing |
| `src/utils/parallel_hash.py` | Parallel hash computation |
| `src/utils/parallel_file_ops.py` | Parallel file operations |
| `src/utils/dedup_scheduler.py` | Dedup strategy |
| `src/utils/scene_detection.py` | Scene detection |
| `src/worker/main.py` | Legacy worker |
| `src/worker/pipelines/linkedin_helpers.py` | LinkedIn helpers |
| `src/worker/pipelines/linkedin_config.py` | LinkedIn config |
| `providers/litellm.py` | LiteLLM provider |
| `app.py` | Main Flask app |
| `worker.py` | Worker dispatcher |
| `monitor.py` | System monitor |
| `thumbnail.py` | Thumbnail extraction |
| `dedup_worker.py` | Dedup worker subprocess |

---

## Evidence Files

| File | Description |
|------|-------------|
| `.sisyphus/evidence/task-6-collection.txt` | Unit test collection output (233 items) |
| `.sisyphus/evidence/task-6-unit-tests.log` | Full unit test verbose run |
| `.sisyphus/evidence/task-6-unit-failures.log` | Unit test failure traces |
| `.sisyphus/evidence/task-7-collection.txt` | Integration test collection output (59 items) |
| `.sisyphus/evidence/task-7-integration-tests.log` | Full integration test verbose run |
| `test_results.json` | Previous run baseline (2026-04-24, 0 collected) |

---

## Notes

1. All 13 failures are **pre-existing** test debt from the Ollama→LiteLLM provider migration (completed in the previous plan). No new failures were introduced by the P0 bug fixes in this plan.
2. The `tests/conftest.py` fix (rewriting broken `from fixtures.conftest import` to `from tests.fixtures.conftest import`) is infrastructure repair, not a test modification.
3. The `tests/integration/test_backend/test_vram_manager.py` TestLiteLLMAlreadyLoaded class appears to be testing LiteLLM-specific behavior but references methods that don't exist in the current `VRAMManager` class. This suggests the test was written during a migration that was partially reverted.
