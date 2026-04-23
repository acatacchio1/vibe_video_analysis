# Contributing to Video Analyzer Web

Thank you for your interest in contributing to Video Analyzer Web! This document provides guidelines and instructions for contributing to the project.

## Development Environment

### Prerequisites
- Python 3.8+
- Node.js 14+ (for frontend development)
- Docker and Docker Compose
- NVIDIA GPU with CUDA 12.1+ (for GPU acceleration)
- ffmpeg and ffprobe installed

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/video-analyzer-web.git
   cd video-analyzer-web
   ```

2. **Set up Python environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run locally**
   ```bash
   python3 app.py
   ```
   Access at: http://localhost:10000

4. **Run with Docker**
   ```bash
   docker compose up --build
   ```
   Access at: http://localhost:10000

## Project Structure

```
video-analyzer-web/
├── app.py                 # Main Flask application (monolithic, needs refactoring)
├── worker.py              # Worker entry point
├── src/                   # Refactored modules
│   ├── api/              # Flask blueprints (routes)
│   ├── websocket/        # SocketIO event handlers
│   ├── worker/           # Analysis worker logic
│   └── utils/            # Utility functions
├── static/               # Frontend assets
│   ├── css/
│   └── js/modules/      # Modular JavaScript
├── config/              # Configuration files
├── tests/               # Test suite
└── archive/             # Archived code and documentation
```

## Code Style

### Python
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use type hints for function signatures
- Maximum line length: 100 characters
- Use `black` for code formatting (configuration in `pyproject.toml`)
- Use `isort` for import sorting

### JavaScript
- Vanilla JavaScript (no frameworks)
- Modular structure (see `static/js/modules/`)
- Use `prettier` for formatting
- Follow ESLint rules

### Commit Messages
Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Example:
```
feat: add OpenWebUI Knowledge Base integration
fix: resolve transcript parsing error in worker
docs: update API documentation
```

## Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, documented code
   - Add tests for new functionality
   - Update documentation as needed

3. **Run tests**
   ```bash
   python -m pytest tests/
   ```

4. **Check code quality**
   ```bash
   black .
   isort .
   flake8 .
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: description of your changes"
   ```

6. **Push and create a pull request**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a PR on GitHub.

## Testing

### Running Tests
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/unit/test_file_utils.py

# Run with coverage
python -m pytest --cov=src tests/
```

### Test Structure
- **Unit tests**: `tests/unit/` - Test individual functions
- **Integration tests**: `tests/integration/` - Test component interactions
- **API tests**: `tests/api/` - Test REST endpoints

### Writing Tests
- Use pytest fixtures for setup/teardown
- Mock external dependencies (API calls, file system)
- Test both success and failure cases
- Aim for >80% code coverage

## External Dependencies (DO NOT MODIFY)

The following files are part of external packages or critical infrastructure:

```
vram_manager.py      # GPU-aware job scheduler
chat_queue.py        # LLM chat queue manager  
monitor.py           # System monitoring
discovery.py         # Ollama network discovery
thumbnail.py         # Thumbnail extraction
gpu_transcode.py     # GPU/CPU transcoding
providers/           # AI provider implementations
```

**Important**: These files are maintained separately. If you find bugs, report them rather than modifying directly.

## Architecture Guidelines

### Backend
- **Flask blueprints**: All routes go in `src/api/*.py`
- **SocketIO handlers**: Event handlers in `src/websocket/handlers.py`
- **Worker logic**: Job execution in `src/worker/main.py`
- **Error handling**: Use `api_error()` helper for consistent error responses

### Frontend
- **Modular JavaScript**: Each feature in its own module
- **Global state**: Use `state` object in `state.js`
- **SocketIO**: Connection management in `socket.js`
- **CSS custom properties**: All styling via CSS variables

### Configuration
- **Constants**: Store in `config/constants.py`
- **Paths**: Define in `config/paths.py`
- **Environment variables**: Use `APP_ROOT` for custom installation paths

## Common Tasks

### Adding a New API Endpoint
1. Create route in appropriate `src/api/*.py` blueprint
2. Register blueprint in `app.py` (if new blueprint)
3. Add corresponding frontend call in appropriate JS module
4. Write tests for the endpoint

### Adding a New SocketIO Event
1. Add handler in `src/websocket/handlers.py`
2. Handler must accept `auth=None` parameter
3. Add client-side listener in `static/js/modules/socket.js`
4. Add handler function in appropriate module

### Modifying Worker Logic
1. Update `src/worker/main.py` for core logic
2. Update `worker.py` for entry point changes
3. Test with actual video analysis
4. Update `AGENTS.md` if behavior changes

## Documentation

### Required Updates
When making changes, update:
- `CHANGELOG.md` for version changes
- `AGENTS.md` for internal developer guide
- `README.md` for user-facing changes
- Appropriate `.md` files for new features

### Writing Documentation
- Use clear, concise language
- Include code examples
- Document breaking changes
- Update version numbers

## Release Process

1. **Update version** in `VERSION` file
2. **Update changelog** in `CHANGELOG.md`
3. **Run tests** to ensure everything works
4. **Create git tag** for the release
5. **Update documentation** with new version
6. **Deploy** following deployment guide

## Getting Help

- Check `AGENTS.md` for detailed architecture guide
- Review existing code for patterns
- Open an issue for questions or bugs
- Reference `CODE_REVIEW_DOCUMENTATION.md` in archive/ for historical context

## Code of Conduct

Please be respectful and constructive. We welcome contributions from everyone.

Thank you for contributing to Video Analyzer Web!