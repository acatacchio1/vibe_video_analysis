#!/bin/bash
set -e

# Conditional Whisper model downloader
# If HF cache volume mount has models, use them.
# Otherwise, download at container startup.

HF_HOME="${HF_HOME:-/root/.cache/huggingface}"
MODELS_DIR="$HF_HOME/hub"

# Check if faster-whisper models appear to be present
has_models() {
    # Look for model directories that faster-whisper creates
    if [ -d "$MODELS_DIR" ]; then
        # Check for symlinks or directories matching faster-whisper model names
        if find "$MODELS_DIR" -maxdepth 2 -name '*whisper*' -print -quit 2>/dev/null | grep -q .; then
            return 0
        fi
    fi
    return 1
}

if has_models; then
    echo "[entrypoint] Whisper models found in HF cache ($HF_HOME). Skipping download."
else
    echo "[entrypoint] No Whisper models found in HF cache. Downloading now..."
    python3 -c "
from faster_whisper import WhisperModel
import sys

models = ['base', 'large']
for m in models:
    try:
        print(f'Downloading Whisper {m} model...')
        WhisperModel(m, device='cpu', compute_type='int8')
        print(f'Whisper {m} ready.')
    except Exception as e:
        print(f'Failed to download {m}: {e}', file=sys.stderr)
        sys.exit(1)
print('All models downloaded successfully.')
"
    echo "[entrypoint] Downloads complete."
fi

# Start the application
exec python3 -m gunicorn \
    -k eventlet \
    -w 1 \
    --bind 0.0.0.0:10000 \
    --timeout 300 \
    --keep-alive 5 \
    app:app
