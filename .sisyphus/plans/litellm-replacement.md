# LiteLLM Provider Replacement Plan

## TL;DR

> **Quick Summary**: Replace native Ollama integration with a LiteLLM proxy at `http://172.16.17.3:4000/v1`. The proxy is OpenAI-compatible, so all LiteLLM calls follow the same pattern as OpenRouter (POST `/v1/chat/completions`, `image_url` content format). Delete all Ollama-specific infrastructure. Keep OpenRouterProvider completely untouched.
>
> **Deliverables**: providers/litellm.py, updated providers/__init__.py, 4 file deletions, 30+ file updates, 7 doc updates
>
> **Estimated Effort**: XL (38 tasks across 5 waves)
> **Parallel Execution**: YES — 5 waves, up to 8 concurrent tasks per wave
> **Critical Path**: litellm.py → app.py → handlers.py → pipelines → verification

---

## Context

### Original Request
Replace OllamaProvider with LiteLLMProvider at 172.16.17.3:4000/v1. Keep OpenRouterProvider fully intact. Remove discovery.py and all Ollama-specific code. Models: qwen3-27b-q8, qwen3-27b-best, vision-best.

### Interview Summary
Migration from direct Ollama integration to LiteLLM proxy. Proxy is OpenAI-compatible (GET /v1/models, POST /v1/chat/completions with image_url content format). Key challenge: provider_type == "ollama" checks exist in 30+ locations across 13 files with branching logic requiring new litellm branches.

### Metis Review
- VRAM: DO NOT modify vram_manager.py internals. LiteLLMProvider estimates ~4GB VRAM for local processing overhead.
- Vision format: GenericOpenAIAPIClient sends OpenAI image_url format compatible with LiteLLM proxy.
- Phase 2 synthesis: Must add explicit litellm branch in 4 locations. Cannot rely on fallthrough to OpenRouter.
- Auth: Proxy is auth-less but maintain Authorization header with empty key for compatibility.
- Monitor: Remove dead ollama_ps tab from frontend. monitor.py left untouched (EXTERNAL).

---

## Work Objectives

### Core Objective
Replace all native Ollama integration with LiteLLM proxy-based provider while maintaining zero regressions for OpenRouterProvider and zero changes to external dependencies.

### Must Have
- LiteLLMProvider implements ALL BaseProvider ABC methods
- All provider_type == "ollama" checks updated to "litellm" with proper branching logic
- Phase 2 synthesis routes through LiteLLM proxy (not OpenRouter)
- Chat queue routes through LiteLLM proxy (not OpenRouter)
- VRAM scheduling maintained (non-zero vram_required for litellm jobs)
- OpenRouterProvider completely untouched and fully functional

### Must NOT Have (Guardrails)
- NO modifications to providers/openrouter.py (zero bytes changed)
- NO internal modifications to vram_manager.py
- NO modifications to monitor.py (EXTERNAL)
- NO new features (no cost tracking for litellm, no new endpoints)
- NO `from providers.ollama import` in any active Python file
- NO `from discovery import` in any active Python file
- NO 192.168.1.237:11434 or 192.168.1.241:11434 hardcoded in active code
- NO "ollama_instances" or "remote_ollama_models" in default_config.json

---

## Verification Strategy

### Test Decision
- Infrastructure exists: YES — tests/ directory with pytest
- Automated tests: Tests-after (update existing tests)
- Framework: pytest (existing)

### QA Policy
Every task MUST include agent-executed QA scenarios. Evidence saved to .sisyphus/evidence/task-{N}-{scenario-slug}.{ext}.
- Python files: Bash (pytest subset, file existence checks, grep)
- API endpoints: Bash (curl requests with status code assertions)
- Frontend: Playwright (verify no dead UI elements)

---

## Execution Strategy

### Parallel Execution Waves
```
Wave 1: 7 independent foundation tasks [quick]
Wave 2: 8 backend core tasks [quick]
Wave 3: 7 pipeline + frontend tasks [deep/quick]
Wave 4: 8 frontend cleanup + docs [visual-engineering/quick/writing]
Wave 5: 8 test suite tasks [quick]
Wave FINAL: 4 parallel reviews [oracle/unspecified-high/deep]
```

### Dependency Matrix
- 1-7: - - 8-22 (Foundation)
- 8-15: 1-7 - 16-22 (Backend Core)
- 16-22: 8-15 - 23-30 (Pipelines + Frontend)
- 23-30: 8-22 - 31-38 (Cleanup + Docs)
- 31-38: ALL - F1-F4 (Test Suite)
- F1-F4: ALL - user okay (Reviews)

### Agent Dispatch Summary
- Wave 1: 7 x quick
- Wave 2: 8 x quick
- Wave 3: 2 x deep + 7 x quick
- Wave 4: 1 x visual-engineering + 1 x quick + 6 x writing
- Wave 5: 8 x quick
- FINAL: 1 x oracle + 2 x unspecified-high + 1 x deep

---

## TODOs

- [x] 1. Create providers/litellm.py

  Implement LiteLLMProvider(BaseProvider). Methods: __init__(name, api_url), _test_connection() via GET {api_url}/models, test_connection(), get_models(), get_model_info(), estimate_vram() returning 4GB per model, analyze_frame() via POST {api_url}/chat/completions with OpenAI image_url format, to_dict().

  **Must Not**: Import ollama package, use /api/chat or /api/tags endpoints, use images array format.
  **Agent**: quick. **Wave**: 1. **Blocks**: 8-38. **Blocked by**: None.
  **Refs**: providers/openrouter.py:210-270 (analyze_frame pattern), providers/base.py (ABC signatures).
  **Acceptance**: File exists, import works, subclass BaseProvider.
  **QA**: python3 import test, proxy connection test, vision smoke test.

  **Commit**: YES (with Task 2)

- [x] 2. Update providers/__init__.py

  Replace from .ollama import OllamaProvider with from .litellm import LiteLLMProvider. Update __all__.

  **Must Not**: Keep both imports. **Agent**: quick. **Wave**: 1. **Blocks**: 8-38. **Blocked by**: 1.
  **Refs**: providers/__init__.py (5 lines).
  **Acceptance**: All three imports work, no OllamaProvider reference.
  **QA**: python3 import + grep check.

  **Commit**: YES (with Task 1)

- [x] 3. Delete providers/ollama.py

  rm providers/ollama.py.

  **Must Not**: Move to archive. **Agent**: quick. **Wave**: 1. **Blocked by**: 2.
  **Acceptance**: test ! -f providers/ollama.py.
  **QA**: File deletion + grep check.

  **Commit**: YES

- [x] 4. Delete discovery.py

  rm discovery.py.

  **Must Not**: Move to archive. **Agent**: quick. **Wave**: 1. **Blocked by**: 3.
  **Acceptance**: test ! -f discovery.py.
  **QA**: File deletion + grep check.

  **Commit**: YES

- [x] 5. Update config/default_config.json

  Replace ollama with litellm everywhere. Remove ollama_instances array, remote_ollama_models dict. Update Phase 2 to litellm/qwen3-27b-best.

  **Must Not**: Change OpenRouter section, Whisper config. **Agent**: quick. **Wave**: 1.
  **Refs**: config/default_config.json.
  **Acceptance**: No ollama string, default==litellm, no orphaned keys.
  **QA**: python3 JSON validation.

  **Commit**: YES

- [x] 6. Update src/schemas/config.py + src/schemas/__init__.py

  Rename OllamaProviderConfig to LiteLLMProviderConfig. Update Literal types from "ollama" to "litellm". Update provider_type Literal unions.

  **Must Not**: Change OpenRouterProviderConfig. **Agent**: quick. **Wave**: 1.
  **Refs**: src/schemas/config.py, src/schemas/__init__.py.
  **Acceptance**: Import works, no OllamaProviderConfig remaining.
  **QA**: python3 import + grep check.

  **Commit**: YES

- [x] 7. Delete worker.py.backup

  rm worker.py.backup.

  **Agent**: quick. **Wave**: 1.
  **Acceptance**: test ! -f worker.py.backup.
  **QA**: File deletion check.

  **Commit**: YES

---

- [x] 8. Update app.py - init_providers, imports, monitor integration

  Remove from discovery import discovery, replace OllamaProvider import with LiteLLMProvider. Rewrite init_providers() to only create LiteLLM and OpenRouter providers. Remove get_loaded_ollama_models(), set_ollama_running_models_provider, _get_monitor_ollama_url(), set_ollama_url_provider.

  **Must Not**: Modify providers/openrouter.py. **Agent**: quick. **Wave**: 2. **Blocks**: 15-18,23-30. **Blocked by**: 1-7.
  **Refs**: app.py:1767-1849, providers/litellm.py.
  **Acceptance**: No OllamaProvider/discovery/192.168.1.237 references. Import works.
  **QA**: grep dead refs, provider init test.

  **Commit**: YES

- [x] 9. Update src/api/providers.py - remove ollama routes

  Remove OllamaProvider import and discovery import. DELETE 4 old routes: /api/providers/discover, /api/providers/ollama-instances (GET+POST), /api/providers/ollama/models. ADD /api/providers/litellm/models route.

  **Must Not**: Modify OpenRouter routes. **Agent**: quick. **Wave**: 2. **Blocks**: 19-22. **Blocked by**: 1-7.
  **Refs**: src/api/providers.py (full file).
  **Acceptance**: No OllamaProvider/discovery/ollama endpoint references.
  **QA**: grep endpoint removal check.

  **Commit**: YES

- [x] 10. Update src/api/llm.py - parameter updates

  Replace ollama_url with litellm_url, replace default provider_type "ollama" with "litellm".

  **Must Not**: Add new logic. **Agent**: quick. **Wave**: 2. **Blocked by**: 1-7.
  **Refs**: src/api/llm.py.
  **Acceptance**: No ollama_url or "ollama" string.
  **QA**: grep check.

  **Commit**: YES

- [x] 11. Update src/websocket/handlers.py - provider_type updates

  Replace provider_type=="ollama" with provider_type=="litellm" for VRAM estimation.

  **Must Not**: Modify OpenRouter handling. **Agent**: quick. **Wave**: 2. **Blocks**: 15-18. **Blocked by**: 1-7.
  **Refs**: src/websocket/handlers.py:155-165.
  **Acceptance**: litellm check present, no ollama remaining.
  **QA**: grep check.

  **Commit**: YES

- [x] 12. Update chat_queue.py - provider_type updates

  Update comments, rename ollama_url to litellm_url, update provider_type check, rewrite litellm branch to use OpenAI-compatible POST.

  **Must Not**: Modify OpenRouter code path. **Agent**: quick. **Wave**: 2. **Blocks**: 15-18. **Blocked by**: 1-7.
  **Refs**: chat_queue.py:161-194, providers/openrouter.py (format reference).
  **Acceptance**: litellm branch present, no ollama_url remaining.
  **QA**: grep check.

  **Commit**: YES

- [x] 13. Update src/services/synthesis_queue.py - provider_type updates

  Update comment, replace phase2_provider_type=="ollama" with =="litellm", rewrite litellm branch.

  **Must Not**: Modify OpenRouter path. **Agent**: quick. **Wave**: 2. **Blocks**: 15-18. **Blocked by**: 1-7.
  **Refs**: src/services/synthesis_queue.py:190-227.
  **Acceptance**: litellm check present, no ollama remaining.
  **QA**: grep check.

  **Commit**: YES

- [x] 14. Update vram_manager.py - minimal VRAM check update

  Lines 43,149,215,387: Replace provider_type=="ollama" with provider_type in ("ollama","litellm").

  **Must Not**: Modify any other vram_manager.py logic. **Agent**: quick. **Wave**: 2. **Blocks**: 15-18. **Blocked by**: 1-7.
  **Refs**: vram_manager.py lines 43,149,215,387.
  **Acceptance**: 4 locations updated.
  **QA**: grep count==4.

  **Commit**: YES

- [x] 15. Update src/cli/api_client.py - rename methods

  Rename/remove ollama methods.

  **Must Not**: Add new endpoints. **Agent**: quick. **Wave**: 2. **Blocks**: 16-17. **Blocked by**: 8-14.
  **Refs**: src/cli/api_client.py:181-190.
  **Acceptance**: No "ollama" string.
  **QA**: grep check.

  **Commit**: YES

---

- [x] 16. Update src/worker/pipelines/standard_two_step.py

  Replace all provider_type=="ollama" with =="litellm". Rewrite Phase 2 synthesis and all client creation to use GenericOpenAIAPIClient instead of OllamaClient. Update URL defaults from 192.168.1.237 to 172.16.17.3.

  **Must Not**: Modify OpenRouter code paths. **Agent**: deep. **Wave**: 3. **Blocks**: 31-38. **Blocked by**: 8-15.
  **Refs**: src/worker/pipelines/standard_two_step.py (full 1080 lines), providers/openrouter.py (format).
  **Acceptance**: No ollama/OllamaClient, GenericOpenAIAPIClient used for litellm.
  **QA**: grep ollama==0, grep OllamaClient==0, grep GenericOpenAIAPIClient>=2.

  **Commit**: YES

- [x] 17. Update src/worker/pipelines/linkedin_extraction.py

  Same pattern as Task 16. Replace provider_type checks and OllamaClient with GenericOpenAIAPIClient.

  **Must Not**: Modify OpenRouter code paths. **Agent**: deep. **Wave**: 3. **Blocks**: 31-38. **Blocked by**: 8-15.
  **Refs**: src/worker/pipelines/linkedin_extraction.py.
  **Acceptance**: No ollama/OllamaClient remaining.
  **QA**: grep check.

  **Commit**: YES

- [x] 18. Update CLI commands (providers.py, jobs.py, llm.py, main.py)

  Remove ollama-instances commands, update click.Choice to litellm, update provider_type defaults.

  **Must Not**: Add new CLI commands. **Agent**: quick. **Wave**: 3. **Blocks**: 31-38. **Blocked by**: 8-15.
  **Refs**: src/cli/commands/providers.py jobs.py llm.py, src/cli/main.py.
  **Acceptance**: No ollama string in CLI files.
  **QA**: grep check.

  **Commit**: YES

- [x] 19. Update static/js/modules/providers.js

   Replace all 'ollama' type checks with 'litellm'. Remove Ollama-specific UI logic.

   **Must Not**: Change OpenRouter handling. **Agent**: quick. **Wave**: 3. **Blocks**: 23-24. **Blocked by**: 8-9.
   **Refs**: static/js/modules/providers.js.
   **Acceptance**: No 'ollama' string, at least one 'litellm'.
   **QA**: grep check.

   **Commit**: YES

- [x] 20. Update static/js/modules/init.js

   Update provider type defaults from 'ollama' to 'litellm'.

   **Must Not**: Change OpenRouter handling. **Agent**: quick. **Wave**: 3. **Blocks**: 23-24. **Blocked by**: 8-9.
   **Refs**: static/js/modules/init.js.
   **Acceptance**: No 'ollama' string.
   **QA**: grep check.

   **Commit**: YES

- [x] 21. Update static/js/modules/llm.js

   Update provider type checks from 'ollama' to 'litellm'.

   **Must Not**: Change OpenRouter handling. **Agent**: quick. **Wave**: 3. **Blocks**: 23-24. **Blocked by**: 8-9.
   **Refs**: static/js/modules/llm.js.
   **Acceptance**: No 'ollama' string.
   **QA**: grep check.

    **Commit**: YES

- [x] 22. Update static/js/modules/results.js

  Update provider type checks from 'ollama' to 'litellm'.

  **Agent**: quick. **Wave**: 3. **Blocks**: 23-24. **Blocked by**: 8-9.
  **Refs**: static/js/modules/results.js.
  **Acceptance**: No 'ollama' string.
  **QA**: grep check.

  **Commit**: YES

---

- [x] 23. Update templates/index.html

   Remove ollama-settings.js script tag. Remove ollama-instances-btn, ollama-instances-modal, ollama ps tab button, ollama-output pre, ollama-discovered-list div, small about ollama ps.

   **Must Not**: Change other scripts or UI elements. **Agent**: visual-engineering. **Wave**: 4. **Blocks**: 31-38. **Blocked by**: 19-22.
   **Refs**: templates/index.html.
   **Acceptance**: No ollama references in HTML.
   **QA**: grep check.

   **Commit**: YES

- [x] 24. Delete ollama-settings.js + update CSS

  rm static/js/modules/ollama-settings.js. Remove .ollama-instance-* CSS selectors from style.css.

  **Must Not**: Change other CSS. **Agent**: quick. **Wave**: 4. **Blocks**: 31-38. **Blocked by**: 19-22.
  **Refs**: static/js/modules/ollama-settings.js, static/css/style.css:3044-3110.
  **Acceptance**: File deleted, no CSS selectors remaining.
  **QA**: file deletion + grep check.

  **Commit**: YES

- [x] 25. Update README.md

  Replace Ollama with LiteLLM. Remove Ollama setup instructions. Add LiteLLM proxy notes.

  **Agent**: writing. **Wave**: 4. **Blocked by**: 8-22.
  **Refs**: README.md.
  **Acceptance**: No "Ollama" references (except maybe in changelog).

  **Commit**: YES

- [x] 26. Update API.md

  Remove ollama-specific endpoints. Add litellm endpoints.

  **Agent**: writing. **Wave**: 4. **Blocked by**: 8-22.
  **Refs**: API.md.
  **Acceptance**: Updated endpoint table.

  **Commit**: YES

- [x] 27. Update DEVELOPMENT.md

  Update architecture, remove ollama references.

  **Agent**: writing. **Wave**: 4. **Blocked by**: 8-22.
  **Refs**: DEVELOPMENT.md.
  **Acceptance**: No ollama provider references.

  **Commit**: YES

- [x] 28. Update AGENTS.md

  Update provider descriptions.

  **Agent**: writing. **Wave**: 4. **Blocked by**: 8-22.
  **Refs**: AGENTS.md.
  **Acceptance**: No ollama provider references.

  **Commit**: YES

- [x] 29. Update GUI.md

  Update UI description.

  **Agent**: writing. **Wave**: 4. **Blocked by**: 8-22.
  **Refs**: GUI.md.
  **Acceptance**: No ollama references.

  **Commit**: YES

- [x] 30. Update TROUBLESHOOTING.md + CLI.md

  Replace Ollama troubleshooting with LiteLLM notes.

  **Agent**: writing. **Wave**: 4. **Blocked by**: 8-22.
  **Refs**: TROUBLESHOOTING.md, CLI.md.
  **Acceptance**: Updated.

  **Commit**: YES

---

- [x] 31. Update tests/fixtures/conftest.py

  Update provider_type defaults from "ollama" to "litellm". Update URL defaults.

  **Agent**: quick. **Wave**: 5. **Blocked by**: ALL preceding.
  **Refs**: tests/fixtures/conftest.py.
  **Acceptance**: provider_type=="litellm" in fixtures.

  **Commit**: YES

- [x] 32. Update tests/unit/api/ (providers, llm, jobs)

  Rewrite provider tests for litellm. Remove ollama-specific endpoint tests.

  **Agent**: quick. **Wave**: 5. **Blocked by**: ALL preceding.
  **Refs**: tests/unit/api/*.py.
  **Acceptance**: No ollama references.

  **Commit**: YES

- [x] 33. Update tests/unit/ (chat_queue, chat_utils)

  Update provider_type and URL defaults.

  **Agent**: quick. **Wave**: 5. **Blocked by**: 31.
  **Refs**: tests/unit/test_chat_queue.py, tests/unit/test_chat_utils.py.
  **Acceptance**: Updated.

  **Commit**: YES

- [x] 34. Update tests/unit/services/ (openwebui_kb)

   Update fixture provider_type.

   **Agent**: quick. **Wave**: 5. **Blocked by**: 31.
   **Refs**: tests/unit/services/test_openwebui_kb.py.
   **Acceptance**: Updated.

   **Commit**: YES

- [x] 35. Update tests/unit/websocket/ (handlers)

   Update provider_type in tests.

   **Agent**: quick. **Wave**: 5. **Blocked by**: 31.
   **Refs**: tests/unit/websocket/test_handlers.py.
   **Acceptance**: Updated.

   **Commit**: YES

- [x] 36. Update tests/integration/ (upload, vram, job)

   Update provider_type in integration tests.

   **Agent**: quick. **Wave**: 5. **Blocked by**: 31.
   **Refs**: tests/integration/*.py tests/integration/test_backend/*.py.
   **Acceptance**: Updated.

   **Commit**: YES

- [x] 37. Update tests/e2e/ (full_workflow)

   Update provider_type in e2e tests.

   **Agent**: quick. **Wave**: 5. **Blocked by**: 31.
   **Refs**: tests/e2e/test_full_workflow.py.
   **Acceptance**: Updated.

   **Commit**: YES

- [x] 38. Update tests/test_pipelines.py

   Update provider_type in pipeline tests.

   **Agent**: quick. **Wave**: 5. **Blocked by**: 31.
   **Refs**: tests/test_pipelines.py.
   **Acceptance**: Updated.

   **Commit**: YES

---

## Final Verification Wave (after ALL implementation tasks)

4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before marking complete.

- [x] F1. **Plan Compliance Audit** — oracle ✅ APPROVED (after init.js IP fix)
  **Output**: `Must Have [6/6] | Must NOT Have [8/8] | Tasks [38/38] | Evidence [0/4] | VERDICT: APPROVE (after fix)`

- [x] F2. **Code Quality Review** — unspecified-high ✅ APPROVED

  Run `python3 -m py_compile` on all modified Python files. Run linter on all modified Python files. Review all changed files for: `as any`/`@ts-ignore` (N/A for Python), empty catches, console.log in prod, commented-out code, unused imports. Check AI slop patterns: excessive comments, over-abstraction, generic names (data/result/item/temp). Verify no dead code left behind (e.g., orphaned function definitions).

  Specific checks:
  - `python3 -c "import providers.litellm; import src.api.providers; import src.api.llm; import chat_queue"` → all imports succeed
  - `grep -rn "@ts-ignore\|as any\|TODO:\|FIXME:\|# TODO" providers/litellm.py` → 0 matches
  - Verify no commented-out Ollama code remains: `grep -rn "^#.*OllamaProvider\|^#.*ollama_url" src/api/providers.py app.py` → 0 matches
  - Check providers/litellm.py follows OpenRouterProvider pattern (consistent style)

  **Output**: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Imports [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — unspecified-high ✅ APPROVED (offline + proxy checks)

  **Prerequisite**: Verify app can start. `python3 app.py &` (or gunicorn command). Wait 5 seconds.

  End-to-end verification:
  1. **Provider list**: `curl http://localhost:10000/api/providers | python3 -m json.tool` → verify litellm present, no ollama
  2. **Dead endpoints removed**: `curl -o /dev/null -w "%{http_code}" http://localhost:10000/api/providers/discover` → 404
  3. **Dead endpoints removed**: `curl -o /dev/null -w "%{http_code}" http://localhost:10000/api/providers/ollama-instances` → 404
  4. **Proxy model check**: `curl http://172.16.17.3:4000/v1/models | python3 -c "import sys,json; data=json.load(sys.stdin); assert any(m['id']=='qwen3-27b-q8' for m in data['data']); print('qwen3-27b-q8 available')"
  5. **Provider connection**: `python3 -c "from providers.litellm import LiteLLMProvider; p=LiteLLMProvider('t','http://172.16.17.3:4000/v1'); assert p.status=='online'; print(p.get_models())"`
  6. **Vision smoke test**: Create test image, call analyze_frame, verify non-empty response
  7. **CLI smoke**: `va providers list` should work and show litellm
  8. **Frontend check**: Playwright — open http://localhost:10000, verify no console errors, click providers tab, verify litellm dropdown option

  Save all evidence to `.sisyphus/evidence/final-qa/`.

  **Output**: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — deep

  For each task 1-38: read "What to do" description, read actual diff (`git diff` or file compare). Verify 1:1 compliance — everything in spec was built AND nothing beyond spec was built (no scope creep). Check "Must NOT do" guardrail compliance per task. Detect cross-task contamination: Task N should only touch its own listed files. Flag any unaccounted changes.

  Specific checks:
  - `git diff --stat` to see all changed files — verify each file is within scope
  - Verify providers/openrouter.py has ZERO changes: `git diff providers/openrouter.py | wc -l` → 0
  - Verify vram_manager.py only has the 4 string match expansions: `git diff vram_manager.py` → only 4 lines changed
  - Verify monitor.py has ZERO changes: `git diff monitor.py | wc -l` → 0
  - Verify no new files created beyond litellm.py: `git ls-files --others --exclude-standard | grep -v "sisyphus\|evidence"` → 0
  - Verify all deleted files actually gone: `test ! -f providers/ollama.py`, `test ! -f discovery.py`, `test ! -f static/js/modules/ollama-settings.js`, `test ! -f worker.py.backup`

  **Output**: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | Guardrails [N/N] | VERDICT`

---

## Commit Strategy
- Wave 1: `refactor(providers): replace OllamaProvider with LiteLLMProvider`
- Wave 2: `refactor(backend): update all backend modules for litellm provider`
- Wave 3: `refactor(pipelines): update worker pipelines for litellm provider`
- Wave 4: `refactor(frontend): remove ollama UI elements, update docs`
- Wave 5: `refactor(tests): update all tests for litellm provider`

---

## Success Criteria
- curl /api/providers shows litellm type, no ollama type
- curl /api/providers/discover returns 404
- curl /api/providers/ollama-instances returns 404
- Proxy returns qwen3-27b-q8 model
- providers/ollama.py does not exist
- discovery.py does not exist
- ollama-settings.js does not exist
- Single-frame vision test produces non-empty analysis
- Full pipeline produces non-empty frames.jsonl and synthesis.jsonl