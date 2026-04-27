# Test Automation Guide

## Overview

Video Analyzer Web has a comprehensive test suite organized in three tiers: unit tests, integration tests, and end-to-end (E2E) tests, with shared fixtures and automated CI execution.

## Quick Start

### Option 1: Direct pytest (Recommended for Development)

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific tier
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v
python -m pytest tests/e2e/ -v

# Run specific test file
python -m pytest tests/unit/api/test_providers.py -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing

# Run with tags
python -m pytest -m unit
python -m pytest -m integration
python -m pytest -m e2e
```

## Test Structure

### Directory Layout

```
tests/
├── conftest.py                    # Root conftest (shared markers, base fixtures)
├── fixtures/
│   └── conftest.py                # ~30 shared fixtures (mock GPU, mock client, sample data)
│
├── unit/                          # Fast, isolated — <60s total
│   ├── api/
│   │   ├── test_videos.py         # Video CRUD endpoints
│   │   ├── test_providers.py      # Provider model discovery, cost estimation
│   │   ├── test_jobs.py           # Job lifecycle management
│   │   └── test_llm.py            # LLM chat queue endpoints
│   ├── utils/
│   │   ├── test_helpers.py        # format_bytes(), format_duration(), map_exit_code_to_status()
│   │   └── test_transcript.py     # Transcript loading, segment extraction
│   ├── services/
│   │   └── test_openwebui_kb.py   # OpenWebUI KB client sync, CRUD operations
│   ├── websocket/
│   │   └── test_handlers.py       # SocketIO event handlers
│   └── *.py                       # Legacy unit tests
│
├── integration/                   # Component interactions — <5min total
│   ├── test_upload_pipeline.py    # Full upload → extract → transcribe flow
│   ├── test_backend/
│   │   └── test_vram_manager.py   # VRAM-aware GPU scheduling
│   └── dedup/
│       └── test_api_dedup.py      # Dedup API endpoint testing
│
└── e2e/                           # Full workflow — slowest
    └── test_full_workflow.py      # Upload → analyze → results → KB sync
```

### Fixtures (`tests/fixtures/conftest.py`)

Approximately 30 shared fixtures providing:
- **Mock Flask context** (`app_context`, `client`)
- **Mock GPU state** (`mock_gpu_info`, `mock_vram_status`)
- **Mock video data** (`sample_video`, `sample_transcript`, `sample_frames`)
- **Mock job state** (`sample_job`, `mock_job_dir`)
- **Mock providers** (`mock_ollama_provider`, `mock_openrouter_provider`)
- **Mock SocketIO** (`mock_socketio`)

## Configuration

### pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --tb=line
    -q
    --no-cov
    -p no:warnings
    --timeout=60
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow running tests
    api: API endpoint tests
filterwarnings =
    ignore::DeprecationWarning
    ignore::FutureWarning
    ignore::EventletDeprecationWarning
```

### Key Settings

- **Timeout**: 60 seconds per test (override: `--timeout=120`)
- **Coverage**: Disabled by default (enable: `--cov=src --cov-report=term-missing`)
- **Warnings**: Filtered to reduce noise from eventlet/future deprecations
- **Markers**: `unit`, `integration`, `e2e`, `slow`, `api`

## Expected Results

### Passing Tests
- Unit tests should pass consistently (< 60s)
- Integration tests may occasionally fail due to external dependencies
- E2E tests require a running server and GPU resources

### Common Failure Reasons
1. **Missing imports**: Check module paths and PYTHONPATH
2. **Missing fixtures**: Verify `tests/fixtures/conftest.py` is in the test discovery path
3. **Timeouts**: Increase via `--timeout` flag or optimize test
4. **Environment**: Tests may require `app.py` imports that need GPU/CUDA

## CI/CD Integration

Automated via `.github/workflows/test.yml`:
- **Push** to `main` or `develop`: Run unit + integration tests
- **Pull request** to `main`: Run full suite (unit + integration, skip e2e)
- **Daily** at 6 AM UTC: Run full suite including E2E
- View status at: https://github.com/acatacchio1/vibe_video_analysis/actions

## Debugging Failed Tests

### Verbose Mode
```bash
python -m pytest tests/unit/api/test_providers.py -v --tb=long
```

### Single Test
```bash
python -m pytest tests/unit/api/test_providers.py::TestProviderModels::test_model_list -v
```

### With Coverage
```bash
python -m pytest tests/unit/utils/test_helpers.py --cov=src.utils.helpers --cov-report=term-missing
```

## Adding New Tests

### 1. Create Test File

Place in appropriate directory:
- `tests/unit/<component>/test_*.py` — unit tests for specific modules
- `tests/integration/<component>/test_*.py` — integration tests
- `tests/e2e/test_*.py` — end-to-end tests

### 2. Name Convention

- Filename: `test_<module>.py`
- Classes: `Test<Name>`
- Methods: `test_<behavior>`

### 3. Example Unit Test

```python
# tests/unit/api/test_videos.py
import pytest

class TestVideoList:
    def test_returns_video_list(self, client):
        response = client.get('/api/videos')
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)
```

### 4. Shared Fixtures

Define in `tests/fixtures/conftest.py` for reuse across tiers.

## Troubleshooting

### Import Errors
```python
ModuleNotFoundError: No module named 'src'
```
Solution: Run from project root or set PYTHONPATH:
```bash
export PYTHONPATH=/path/to/video-analyzer-web:$PYTHONPATH
```

### Timeout Issues
1. Check for blocking operations or infinite loops
2. Increase timeout: `pytest --timeout=120`
3. Check GPU memory exhaustion in VRAM tests

### Stale Cache
```bash
rm -rf .pytest_cache tests/__pycache__ tests/**/__pycache__
```
