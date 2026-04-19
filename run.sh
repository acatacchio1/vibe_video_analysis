#!/bin/bash
# Run video-analyzer-web directly on port 10000 (no Docker)

cd "$(dirname "$0")"

LOG=/tmp/video-analyzer.log
PID_FILE=/tmp/video-analyzer.pid

# Use virtual environment if available, otherwise fall back to system python
if [ -d "/home/anthony/venvs/video-analyzer" ]; then
    PYTHON="/home/anthony/venvs/video-analyzer/bin/python"
else
    PYTHON="python3"
fi

# Kill existing instance if running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping existing instance (PID $OLD_PID)..."
        kill "$OLD_PID"
        sleep 1
    fi
fi

mkdir -p uploads thumbs jobs cache output

# Set CUDA library path for GPU acceleration (faster-whisper)
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH

echo "Starting video-analyzer-web on port 10000..."
echo "Using Python: $PYTHON"
setsid "$PYTHON" app.py >> "$LOG" 2>&1 &
echo $! > "$PID_FILE"
echo "Started PID $(cat $PID_FILE) — logs at $LOG"
