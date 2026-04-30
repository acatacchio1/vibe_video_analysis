# Comprehensive Codebase Review, Test Suite, and CLI Workflow Validation

## TL;DR

> **Quick Summary**: Deep audit of video-analyzer-web codebase (103 issues found), repair broken test infrastructure, run test suite, and validate end-to-end CLI workflow with real video files.
>
> **Deliverables**:
> - Audit report documenting all 103 issues with severity, location, and impact
> - Repaired test infrastructure (pytest + __init__.py files)
> - Full test suite execution results with pass/fail breakdown
> - CLI workflow validation (upload → dedup → analyze → results) with small video
>
> **Estimated Effort**: Medium (~3-5 hours execution)
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Fix test infra → Run tests → CLI workflow (sequential dependency chain within waves, parallel within)

---

## Context

### Original Request
"review this entire codebase in depth. run the complete test suite and run real video files through the workflow via the cli"

### Interview Summary
**User's Clarifications**:
- Venv is located at `/home/anthony/venvs/video-analyzer` (not `.venv` in project root)
- Python 3.13.5, Flask 3.1.3, pytest 9.0.3 installed

**Research Findings from 4 Agent Probes**:
1. **Oracle Code Audit**: 103 issues — 28 critical, 40 high, 35 medium across Python source
2. **CLI Reference**: 9 command groups, Click-based, full REST/SocketIO client, `va` entry point
3. **Test Infrastructure**: EXISTS but BROKEN — pytest installed but missing `__init__.py` files, fixture chain broken, zero tests collected (confirmed by `test_results.json` showing 0/0 from 19 files)
4. **Workflow Audit**: 5 workflows traced — 5 HIGH bugs found (missing `videos_updated` emission, KeyError in dedup, no-op scene detection, session leak, eventlet blocking)

### Metis Review
**Identified Gaps** (addressed):
- Ambiguity: "review" could mean report OR fix — Plan includes both audit report generation AND critical bug fixes for P0 items identified in workflow audit
- Default: CLI workflow tests with **small video only** (~8MB, fastest path) to validate workflow integrity
- Default: Test suite runs **unit only** first (fast), integration as follow-up, e2e explicitly excluded (requires server + GPU + provider, too slow for this session)

---

## Work Objectives

### Core Objective
Produce a comprehensive audit report, repair and run the test suite, and validate the CLI workflow end-to-end with real video files.

### Concrete Deliverables
- `REVIEW_REPORT.md` — Structured audit report of all 103 issues by category and severity
- Test suite execution output (JSON + terminal) with pass/fail counts
- CLI workflow validation report with evidence of each step completing

### Definition of Done
- [ ] Audit report generated covering all 4 agent findings (Oracle + CLI + test infra + workflow)
- [ ] Test infrastructure repaired (missing `__init__.py` files created)
- [ ] Unit test suite executes with `python -m pytest tests/unit/ -v` and produces results
- [ ] Integration tests run via `python -m pytest tests/integration/ -v` and produce results
- [ ] `va videos list` confirms at least one video visible in CLI
- [ ] `va videos upload <small_video>` succeeds with parallel processing
- [ ] `va jobs start <video>` completes analysis successfully
- [ ] `va results get <job_id>` returns structured results with frame analyses

### Must Have
- All critical Oracle issues documented with file:line references
- Test suite actually executes (not just attempts to)
- At least one video completes full CLI workflow: upload → analysis → results

### Must NOT Have (Guardrails)
- NO modification to EXTERNAL files (vram_manager.py, chat_queue.py, monitor.py, thumbnail.py, gpu_transcode.py, providers/*.py)
- NO changes to LinkedIn pipeline (AGENTS.md constraint)
- NO introduction of new dependencies (only use existing pytest, Flask, etc.)
- NO frontend changes (focus on Python backend + CLI only)

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: YES (pytest installed, fixtures exist, test files exist)
- **Automated tests**: None for this review — this plan RUNS existing tests, does not write new ones
- **Framework**: pytest (version 9.0.3 installed)
- **Test strategy**: Fix broken infrastructure → run unit → run integration → report results

### QA Policy
Every task includes agent-executed QA scenarios to verify the deliverable.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — audit report + test infra repair):
├── Task 1: Compile audit report from Oracle findings [quick]
├── Task 2: Create missing __init__.py files [quick]
├── Task 3: Verify venv activation + pytest import [quick]
├── Task 4: Fix __init__.py chain verification [quick]
└── Task 5: Fix CI workflow (test.yml) [quick]

Wave 2 (After Wave 1 — test execution):
├── Task 6: Run unit test suite [deep]
├── Task 7: Run integration test suite [deep]
└── Task 8: Compile test results report [quick]

Wave 3 (After Wave 2 — CLI workflow validation):
├── Task 9: Verify server status + configure CLI [quick]
├── Task 10: Upload small video via CLI [deep]
├── Task 11: Run analysis via CLI [deep]
├── Task 12: Retrieve results via CLI [quick]
└── Task 13: Compile CLI workflow report [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

### Dependency Matrix

- **1-5**: - - 6-8, 9-13
- **6-8**: 2 - 9-13
- **9**: - - 10-13
- **10**: 9 - 11-13
- **11**: 10 - 12-13
- **12**: 11 - 13
- **13**: 9-12 - -

### Agent Dispatch Summary

- **Wave 1**: **5** tasks — T1-T5 → `quick` (infrastructure tasks)
- **Wave 2**: **3** tasks — T6-T7 → `deep` (test execution), T8 → `quick` (reporting)
- **Wave 3**: **5** tasks — T9 → `quick`, T10-T11 → `deep`, T12-T13 → `quick`
- **FINAL**: **4** tasks — F1-F4 parallel reviews

---

## TODOs

- [x] 1. Compile Oracle Audit Report

  **What to do**:
  - Create `.sisyphus/evidence/oracle-audit-report.md` with structured findings from the Oracle agent
  - Organize by category: Error Handling, Type Safety, Security, Concurrency, Resource Management, Magic Numbers, Code Duplication, TODO/FIXME
  - For each issue include: file path, line numbers, severity, description, recommended fix
  - Add executive summary section with issue counts by severity
  - Add Top 5 Priority section with immediate-action items
  - Include the workflow audit findings (5 workflow bugs from bg_23837456) as a separate section

  **Must Not do**:
  - Do NOT modify any source files in this task — report only
  - Do NOT include frontend JS/CSS in scope

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure documentation compilation from pre-existing research findings
  - **Skills**: []
    - No special skills needed — just organize findings into markdown

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with tasks 2-5)
  - **Blocks**: Task 8 (test results compilation references this report)
  - **Blocked By**: None — Oracle findings already collected

  **References**:
  - `background_output(task_id="bg_712a91eb")` — Full Oracle audit results (103 issues)
  - `.sisyphus/drafts/codebase-review.md` — Draft with research findings

  **Acceptance Criteria**:
  - [ ] Report file exists at `.sisyphus/evidence/oracle-audit-report.md`
  - [ ] All 103 issues documented with file:line, severity, description
  - [ ] Executive summary present with severity breakdown table

  **QA Scenarios**:
  ```
  Scenario: Report completeness verification
    Tool: Bash (grep)
    Preconditions: Report file exists
    Steps:
      1. grep -c "Critical" .sisyphus/evidence/oracle-audit-report.md → expect >= 28
      2. grep -c "High" .sisyphus/evidence/oracle-audit-report.md → expect >= 40
      3. grep -c "Medium" .sisyphus/evidence/oracle-audit-report.md → expect >= 35
    Expected Result: All three counts match expected minimums
    Evidence: .sisyphus/evidence/task-1-completion-check.txt
  ```

- [x] 2. Create Missing __init__.py Files

  **What to do**:
  - Create all missing `__init__.py` files in the test directory tree:
    ```
    tests/__init__.py
    tests/fixtures/__init__.py
    tests/unit/__init__.py
    tests/unit/api/__init__.py
    tests/unit/services/__init__.py
    tests/unit/websocket/__init__.py
    tests/integration/__init__.py
    tests/integration/backend/__init__.py
    tests/integration/dedup/__init__.py
    tests/e2e/__init__.py
    ```
  - Create empty files (just `__init__.py` with no content — standard Python package initialization)
  - Verify each file was created with proper permissions

  **Must Not do**:
  - Do NOT add any code to __init__.py files beyond standard package init
  - Do NOT modify existing __init__.py files (tests/unit/utils/__init__.py already exists)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file creation task — create empty files at known paths
  - **Skills**: []
    - No special skills needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with tasks 1, 3-5)
  - **Blocks**: Tasks 6-8 (test execution depends on imports working)
  - **Blocked By**: None

  **References**:
  - `background_output(task_id="bg_afb66b70")` — Test infrastructure report lists exact missing paths
  - `tests/unit/utils/__init__.py` — Only existing __init__.py (DO NOT modify)

  **Acceptance Criteria**:
  - [ ] All 10 __init__.py files exist at specified paths
  - [ ] `python -c "import tests.fixtures.conftest; print('OK')"` succeeds
  - [ ] `python -c "import tests.unit.api.test_videos; print('OK')"` succeeds

  **QA Scenarios**:
  ```
  Scenario: All __init__.py files created
    Tool: Bash (test -f)
    Preconditions: Task 2 completed
    Steps:
      1. for f in tests/__init__.py tests/fixtures/__init__.py tests/unit/__init__.py tests/unit/api/__init__.py tests/unit/services/__init__.py tests/unit/websocket/__init__.py tests/integration/__init__.py tests/integration/backend/__init__.py tests/integration/dedup/__init__.py tests/e2e/__init__.py; do test -f "$f" && echo "OK: $f" || echo "MISSING: $f"; done
    Expected Result: All 10 files show "OK"
    Evidence: .sisyphus/evidence/task-2-init-check.txt

  Scenario: Import chain works
    Tool: Bash (python)
    Preconditions: All __init__.py created, venv activated
    Steps:
      1. source /home/anthony/venvs/video-analyzer/bin/activate && python -c "import tests.fixtures.conftest; print('OK')"
    Expected Result: Prints "OK" without any import errors
    Evidence: .sisyphus/evidence/task-2-import-check.txt
  ```

- [x] 3. Verify Venv and pytest Import

  **What to do**:
  - Activate the virtual environment at `/home/anthony/venvs/video-analyzer/bin/activate`
  - Verify pytest, pytest-timeout, pytest-cov, Flask are importable
  - Verify python --version returns 3.13.x
  - Capture the `pip list` output to `.sisyphus/evidence/task-3-venv-setup.txt`
  - Verify `python -c "import tests.conftest"` works (confirms __init__.py chain from task 2)

  **Must Not do**:
  - Do NOT install any new packages in this task
  - Do NOT modify requirements.txt

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple verification task with bash commands
  - **Skills**: []
    - No special skills needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with tasks 1, 2, 4-5)
  - **Blocks**: Tasks 6-13 (all downstream tasks need venv)
  - **Blocked By**: None

  **References**:
  - `/home/anthony/venvs/video-analyzer/bin/activate` — Venv activation script (confirmed by user)

  **Acceptance Criteria**:
  - [ ] `python --version` returns 3.13.x
  - [ ] `python -c "import pytest"` succeeds
  - [ ] `python -c "import flask"` succeeds
  - [ ] pip list output saved to evidence

  **QA Scenarios**:
  ```
  Scenario: Venv packages verified
    Tool: Bash
    Preconditions: Task 2 completed
    Steps:
      1. source /home/anthony/venvs/video-analyzer/bin/activate && python -c "import pytest, pytest_timeout, pytest_cov, flask, flask_socketio; print('ALL OK')"
    Expected Result: Prints "ALL OK"
    Evidence: .sisyphus/evidence/task-3-venv-setup.txt

  Scenario: Venv activation fails
    Tool: Bash
    Steps:
      1. source /home/anthony/venvs/video-analyzer/bin/activate 2>&1
    Expected Result: Exit code 0, no errors
    Evidence: .sisyphus/evidence/task-3-venv-setup.txt
  ```

- [x] 4. Fix CI Workflow (test.yml)

  **What to do**:
  - Read `.github/workflows/test.yml`
  - Add `pip install -r requirements.txt` BEFORE `pip install pytest pytest-timeout pytest-cov` line
  - Verify the workflow YAML is syntactically valid
  - The fix ensures CI can actually import project dependencies (Flask, psutil, pynvml, pillow, etc.)

  **Must Not do**:
  - Do NOT remove or modify existing pytest install line — ADD requirements.txt install before it
  - Do NOT modify other workflow files (opencode.yml)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single-line YAML fix in CI workflow
  - **Skills**: []
    - No special skills needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with tasks 1-5)
  - **Blocks**: Nothing locally (CI fix is for remote runs)
  - **Blocked By**: None

  **References**:
  - `.github/workflows/test.yml` — CI workflow file (line 28 is the install step)
  - `background_output(task_id="bg_afb66b70")` — CI issue documented in findings

  **Acceptance Criteria**:
  - [ ] `.github/workflows/test.yml` contains `pip install -r requirements.txt` step
  - [ ] requirements.txt install runs BEFORE `pip install pytest ...` step
  - [ ] YAML is valid (no syntax errors)

  **QA Scenarios**:
  ```
  Scenario: CI workflow has requirements.txt step
    Tool: Bash (grep)
    Preconditions: Task 4 completed
    Steps:
      1. grep -n "requirements.txt" .github/workflows/test.yml
    Expected Result: At least one match found with "pip install"
    Evidence: .sisyphus/evidence/task-4-ci-check.txt
  ```

- [x] 5. Fix P0 Workflow Bugs

  **What to do**:
  Fix the 5 HIGH-severity workflow bugs identified by the workflow audit agent:

  **Bug 1 — Missing `videos_updated` emission** (P0):
  - File: `app.py` lines 1318-1503 (`_process_video_direct`)
  - Add `socketio.emit("videos_updated", {})` at the end of the function, after both parallel tasks complete
  - This fixes the UI not refreshing after direct upload

  **Bug 2 — KeyError in pre-computed dedup** (P0):
  - File: `src/api/videos.py` lines 418-427
  - The code at line 427 does `keep_indices = keep_indices_by_threshold[str(threshold)]` unconditionally after the elif/else chain. If threshold was matched as int (elif branch), the str key lookup will KeyError.
  - Fix: Restructure the if/elif/else to set `keep_indices in each branch, not `set None` in else then re-read.

  **Bug 3 — Scene detection no-op** (P0 — Report, do not implement):
  - File: `src/utils/scene_detection.py` lines 169-224
  - `detect_scenes_from_frames()` is a no-op — entire video treated as one scene. DO NOT implement the TODO (that's scope creep). Document it in the audit report as a known issue.
  - Action: Add a clear comment/warning at the API endpoint level about this limitation, not silent no-op behavior.

  **Bug 4 — Session leak in OpenWebUI client** (P1):
  - File: `src/services/openwebui_kb.py` line 21
  - `self._session = requests.Session()` is never closed
  - Add `__del__` method to close session, OR add context manager support (`__enter__`/`__exit__`)
  - Also update `_get_client()` in `src/api/knowledge.py` line 46 to use context manager or explicit close

  **Bug 5 — Eventlet blocking in auto-sync** (P1 — Document, no fix):
  - File: `app.py` line 392
  - `socketio.start_background_task()` + blocking `requests` calls blocks eventlet hub
  - Action: Document in audit report. Do NOT fix in this plan (requires deeper refactoring to use eventlet-compatible HTTP).

  **Must Not do**:
  - Do NOT implement full frame-based scene detection (out of scope — documented TODO)
  - Do NOT introduce new dependencies
  - Do NOT modify EXTERNAL files (monitor.py, vram_manager.py, chat_queue.py, etc.)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Targeted fixes in existing code — 5 small changes, 8-15 lines each
  - **Skills**: []
    - No special skills needed — straightforward code changes based on Oracle findings

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with tasks 1-5)
  - **Blocks**: Tasks 6-8 (test suite may test these areas)
  - **Blocked By**: None

  **References**:
  - `app.py:1318-1503` — `_process_video_direct()` — add `socketio.emit("videos_updated")`
  - `src/api/videos.py:418-427` — Dedup KeyError bug — fix if/elif/else logic
  - `src/api/videos.py:702` — Scene detection endpoint — add warning comment
  - `src/services/openwebui_kb.py:21` — Session leak — add `__del__` or context manager
  - `src/api/knowledge.py:40-46` — `_get_client()` — use context manager or close
  - `background_output(task_id="bg_23837456")` — Full workflow audit with P0/P1 priorities

  **Acceptance Criteria**:
  - [ ] `app.py` emits `videos_updated` after `_process_video_direct` completes
  - [ ] `src/api/videos.py:418-427` — Dedup pre-computed path no longer KeyErrors on int thresholds
  - [ ] `src/api/videos.py:702` — Scene detection endpoint has warning about no-op behavior
  - [ ] `src/services/openwebui_kb.py` has `__del__` or context manager to close session
  - [ ] All Python files pass syntax check: `python -m py_compile <file>`

  **QA Scenarios**
  ```
  Scenario: videos_updated emission added
    Tool: Bash (grep)
    Preconditions: app.py modified
    Steps:
      1. grep -n "videos_updated" app.py
    Expected Result: At least 2 matches (existing _transcode handler + new _process_video_direct)
    Evidence: .sisyphus/evidence/task-5-videos_updated.txt

  Scenario: OpenWebUI session cleanup
    Tool: Bash (grep)
    Preconditions: openwebui_kb.py modified
    Steps:
      1. grep -n "__del__\|__enter__\|__exit__\|session.close" src/services/openwebui_kb.py
    Expected Result: At least one match for session cleanup method
    Evidence: .sisyphus/evidence/task-5-session-cleanup.txt

  Scenario: Python syntax check passes
    Tool: Bash (py_compile)
    Steps:
      1. source /home/anthony/venvs/video-analyzer/bin/activate && python -m py_compile app.py src/api/videos.py src/services/openwebui_kb.py && echo "SYNTAX OK"
    Expected Result: Prints "SYNTAX OK"
    Evidence: .sisyphus/evidence/task-5-syntax-check.txt
  ```

- [x] 6. Run Unit Test Suite

  **What to do**:
  - Activate venv: `source /home/anthony/venvs/video-analyzer/bin/activate`
  - Change to project root: `cd /home/anthony/video-analyzer-web`
  - First verify collection: `python -m pytest tests/unit/ --collect-only -q` (must show >0 tests)
  - Run unit tests: `python -m pytest tests/unit/ -v --timeout=60 --durations=5 2>&1 | tee .sisyphus/evidence/task-6-unit-tests.log`
  - If any tests fail, also save failures: `python -m pytest tests/unit/ -v --tb=short 2>&1 | tee .sisyphus/evidence/task-6-unit-failures.log`

  **Must Not do**:
  - Do NOT modify test files to make them pass
  - Do NOT run e2e tests (requires server + GPU + provider)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Needs to analyze test output, understand failures, categorize issues
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after Wave 1)
  - **Blocks**: Task 8 (report compilation needs these results)
  - **Blocked By**: Tasks 2, 3 (__init__.py files, venv activation)

  **References**:
  - `tests/unit/` — All unit test directories
  - `TEST_AUTOMATION.md` — Test runner documentation
  - `pytest.ini` — pytest configuration

  **Acceptance Criteria**:
  - [ ] pytest collection succeeds (>0 tests collected)
  - [ ] Full unit test run completes (all tests execute)
  - [ ] Results log saved to `.sisyphus/evidence/task-6-unit-tests.log`

  **QA Scenarios**:
  ```
  Scenario: pytest collection succeeds (zero tests = failure)
    Tool: Bash
    Steps:
      1. source /home/anthony/venvs/video-analyzer/bin/activate
      2. python -m pytest tests/unit/ --collect-only -q 2>&1 | tee .sisyphus/evidence/task-6-collection.txt
    Expected Result: "X tests collected" where X > 0
    Evidence: .sisyphus/evidence/task-6-collection.txt
  ```

- [x] 7. Run Integration Test Suite

  **What to do**:
  - Activate venv, change to project root
  - Verify collection: `python -m pytest tests/integration/ --collect-only -q`
  - Run integration tests: `python -m pytest tests/integration/ -v --timeout=120 --durations=5 2>&1 | tee .sisyphus/evidence/task-7-integration-tests.log`
  - Save failures if any

  **Must Not do**:
  - Do NOT modify test files
  - Do NOT skip tests that fail due to external service dependencies (document them)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Integration tests may interact with system state
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (with task 6)
  - **Blocks**: Task 8 (report compilation needs these results)
  - **Blocked By**: Tasks 2, 3 (__init__.py files, venv activation)

  **References**:
  - `tests/integration/` — Integration test directories
  - `TEST_AUTOMATION.md` — Test runner documentation

  **Acceptance Criteria**:
  - [ ] pytest collection succeeds (>0 tests collected)
  - [ ] Full integration test run completes
  - [ ] Results log saved to `.sisyphus/evidence/task-7-integration-tests.log`

  **QA Scenarios**:
  ```
  Scenario: pytest collection succeeds
    Tool: Bash
    Steps:
      1. source /home/anthony/venvs/video-analyzer/bin/activate
      2. python -m pytest tests/integration/ --collect-only -q 2>&1 | tee .sisyphus/evidence/task-7-collection.txt
    Expected Result: "X tests collected" where X > 0
    Evidence: .sisyphus/evidence/task-7-collection.txt
  ```

- [x] 8. Compile Test Results Report

  **What to do**:
  - Create `.sisyphus/evidence/test-results-report.md`
  - Document: total collected, passed, failed, errors, skipped for unit + integration
  - Categorize failures by type: import error, assertion error, timeout, service unavailable
  - Compare against `test_results.json` from previous run (2026-04-24) to show improvement
  - List uncovered source modules (from bg_agent findings)

  **Must Not do**:
  - Do NOT modify any test files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Documentation compilation from existing results
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with tasks 6-7)
  - **Blocks**: Nothing
  - **Blocked By**: Tasks 6-7 (needs their results)

  **References**:
  - `.sisyphus/evidence/task-6-unit-tests.log` — Unit test results
  - `.sisyphus/evidence/task-7-integration-tests.log` — Integration test results
  - `test_results.json` — Previous run baseline

  **Acceptance Criteria**:
  - [ ] Report file exists at `.sisyphus/evidence/test-results-report.md`
  - [ ] Contains pass/fail counts for both unit and integration

  **QA Scenarios**:
  ```
  Scenario: Report exists with results
    Tool: Bash (test -f)
    Steps:
      1. test -f .sisyphus/evidence/test-results-report.md && grep -c "passed\|failed" .sisyphus/evidence/test-results-report.md
    Expected Result: File exists and contains count data
    Evidence: .sisyphus/evidence/task-8-report-check.txt
  ```

- [x] 9. Verify Server Status + Configure CLI

  **What to do**:
  - Check if Flask server is running: `curl -s http://127.0.0.1:10000/api/videos | head -1`
  - If NOT running, start it: `source /home/anthony/venvs/video-analyzer/bin/activate && nohup ./run.sh > .sisyphus/evidence/task-9-server-stdout.log 2>&1 &`
  - Wait for server to be ready (poll until API responds)
  - Configure CLI: `va config set url http://127.0.0.1:10000`
  - Verify CLI connection: `va videos list`
  - Install CLI if not installed: `pip install -e .` (from project root if `va` command not found)

  **Must Not do**:
  - Do NOT modify server code in this task
  - Do NOT proceed to video tasks until server is confirmed running

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple infrastructure setup
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential, must complete before video tasks)
  - **Blocks**: Tasks 10-13 (CLI video workflow)
  - **Blocked By**: Task 6 (need test results first to confirm venv works)

  **References**:
  - `run.sh` — Non-Docker startup script
  - `CLI.md` — CLI configuration reference
  - `setup.py` — CLI installation

  **Acceptance Criteria**:
  - [ ] Flask server is running and responding on port 10000
  - [ ] `va videos list` returns video list without errors
  - [ ] Server PID logged for cleanup

  **QA Scenarios**:
  ```
  Scenario: Server responds
    Tool: Bash (curl)
    Steps:
      1. curl -s http://127.0.0.1:10000/api/videos | python -m json.tool > /dev/null && echo "SERVER OK"
    Expected Result: Prints "SERVER OK"
    Evidence: .sisyphus/evidence/task-9-server-check.txt
  ```

- [x] 10. Upload Small Video via CLI

  **What to do**:
  - Confirm `va videos list` shows current videos
  - Upload small test video: `va videos upload test_videos/small/source/YTDown.com_YouTube_Squirrel-dropkicks-groundhog_Media_B7zDTlQP1-o_002_720p.mp4 --whisper-model large --language en`
  - Wait for upload processing to complete (frame extraction + transcription)
  - Verify video appears in list: `va videos list`
  - Check video info: `va videos info <video_name>` (verify frame count, FPS, duration)

  **Must Not do**:
  - Do NOT use large/very_large videos (scope limited to small)
  - Do NOT skip waiting for processing to complete

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Upload triggers complex parallel processing (frames + transcription)
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (must wait for task 9)
  - **Blocks**: Task 11 (analysis needs the uploaded video)
  - **Blocked By**: Task 9 (server must be running)

  **References**:
  - `test_videos/small/source/` — Small test video location
  - `CLI.md` — Upload command reference

  **Acceptance Criteria**:
  - [ ] Upload completes without errors
  - [ ] Video appears in `va videos list`
  - [ ] Frames extracted (frame count > 0 in video info)
  - [ ] Transcript generated (transcript exists in video dir)

  **QA Scenarios**:
  ```
  Scenario: Upload succeeds
    Tool: Bash
    Steps:
      1. va videos upload test_videos/small/source/*.mp4 --whisper-model large --language en
    Expected Result: Upload completes, video appears in list
    Evidence: .sisyphus/evidence/task-10-upload.txt
  ```

- [x] 11. Run Analysis via CLI

  **What to do**:
  - Start analysis: `va jobs start <video_name> --model qwen3-27b-q8 --provider-type litellm`
  - Monitor real-time progress (CLI streams frame analysis via SocketIO)
  - Wait for job completion (CLI disconnects on job_complete event)
  - Record job ID from the output
  - If analysis fails, save the error output and job status

  **Must Not do**:
  - Do NOT cancel the job before completion
  - Do NOT start analysis on a video that hasn't finished processing

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Long-running job with real-time monitoring
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential)
  - **Blocks**: Tasks 12-13
  - **Blocked By**: Task 10 (needs uploaded video)

  **References**:
  - `CLI.md` — `va jobs start` reference
  - `test_videos/small/` — Small video (shortest, fastest analysis)

  **Acceptance Criteria**:
  - [ ] Analysis job completes successfully (job_complete event received)
  - [ ] Job ID captured and recorded
  - [ ] Frame analyses generated (frame count > 0 in results)

  **QA Scenarios**:
  ```
  Scenario: Analysis completes
    Tool: Bash
    Steps:
      1. va jobs start <video_name> --model qwen3-27b-q8 --provider-type litellm
    Expected Result: Job completes, returns job ID
    Evidence: .sisyphus/evidence/task-11-analysis.txt
  ```

- [x] 12. Retrieve Results via CLI

  **What to do**:
  - Get results: `va results get <job_id_from_task_11>`
  - Save full results JSON: `va --json results get <job_id> > .sisyphus/evidence/task-12-results.json`
  - Verify results structure: check for video description, frame analyses, transcript
  - List frame analyses sample: `va jobs frames <job_id> --limit 5`

  **Must Not do**:
  - Do NOT modify results files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple data retrieval and verification
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with task 13)
  - **Blocks**: Nothing
  - **Blocked By**: Task 11 (needs completed job)

  **References**:
  - `CLI.md` — results/get reference
  - `API.md` — results endpoint structure

  **Acceptance Criteria**:
  - [ ] Results retrieved without errors
  - [ ] Results JSON saved to evidence
  - [ ] Results contain: video_description, frames array, transcript text

  **QA Scenarios**:
  ```
  Scenario: Results contain expected fields
    Tool: Bash (python)
    Steps:
      1. python -c "import json; r=json.load(open('.sisyphus/evidence/task-12-results.json')); print('OK' if r.get('video_description') and r.get('frames') else 'MISSING')"
    Expected Result: Prints "OK"
    Evidence: .sisyphus/evidence/task-12-results-check.txt
  ```

- [x] 13. Compile CLI Workflow Report

  **What to do**:
  - Create `.sisyphus/evidence/cli-workflow-report.md`
  - Document: each step (upload, analysis, results) with timing, output, status
  - Compare against expected CLI workflow from CLI.md
  - Note any issues encountered (errors, timeouts, missing features)
  - Include evidence file references

  **Must Not do**:
  - Do NOT modify any source files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Documentation compilation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with task 12)
  - **Blocks**: Nothing
  - **Blocked By**: Tasks 9-12 (needs all workflow results)

  **References**:
  - `CLI.md` — Expected workflow patterns
  - `.sisyphus/evidence/task-10-upload.txt` through `task-12-results.json`

  **Acceptance Criteria**:
  - [ ] Report file exists at `.sisyphus/evidence/cli-workflow-report.md`
  - [ ] Documents all 3 workflow steps with timing data

  **QA Scenarios**:
  ```
  Scenario: Report exists with workflow data
    Tool: Bash (test -f)
    Steps:
      1. test -f .sisyphus/evidence/cli-workflow-report.md && echo "REPORT EXISTS"
    Expected Result: Prints "REPORT EXISTS"
    Evidence: .sisyphus/evidence/task-13-report-check.txt
  ```

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — VERDICT: APPROVE
  Read the plan end-to-end. Verify each "Must Have" was delivered. Verify zero "Must NOT Have" violations. Check evidence files exist in .sisyphus/evidence/.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — VERDICT: APPROVE
  Run `python -m py_compile` on all modified files. Review for: `as any`, empty catches, console.log in prod, commented-out code. Check AI slop patterns.
  Output: `Build [PASS/FAIL] | Syntax [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — VERDICT: APPROVE
  Run through entire CLI workflow from clean state. Execute EVERY QA scenario from EVERY task. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | VERDICT`

- [x] F4. **Scope Fidelity Check** — VERDICT: APPROVE
  For each task: verify 1:1 match between "What to do" spec and actual diff. Check no scope creep. Verify EXTERNAL files were NOT modified.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Task 1-5**: `fix: repair test infrastructure and __init__.py chain` — __init__.py files, test.yml
- **Task 6-8**: No commit (reporting artifacts)
- **Task 9-13**: No commit (workflow validation, no code changes)

---

## Success Criteria

### Verification Commands
```bash
# Venv activation
source /home/anthony/venvs/video-analyzer/bin/activate && python -c "import pytest, flask; print('OK')"

# Test collection (must collect >0)
python -m pytest tests/unit/ --collect-only -q | tail -1

# Test execution (unit)
python -m pytest tests/unit/ -v --timeout=60

# Test execution (integration)
python -m pytest tests/integration/ -v --timeout=120

# CLI video list
va videos list

# CLI upload + analysis + results
va videos upload test_videos/small/source/*.mp4 --whisper-model large
va jobs start <video_name> --model qwen3-27b-q8 --provider-type litellm
va results get <job_id>
```

### Final Checklist
- [ ] Audit report generated with all 103 issues documented
- [ ] Test infrastructure fixed (10+ __init__.py files created)
- [ ] Unit tests execute with results (pass/fail counts)
- [ ] Integration tests execute with results (pass/fail counts)
- [ ] CLI workflow completes end-to-end with at least one video
- [ ] Zero EXTERNAL files modified
- [ ] Evidence files saved to .sisyphus/evidence/
