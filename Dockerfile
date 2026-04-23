# Video Analyzer Web - Optimized Dockerfile

FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/usr/local/bin:${PATH}"

# Hugging Face cache defaults to /root/.cache/huggingface (NOT under volume mount)
# This ensures pre-downloaded Whisper models survive container startup

# ctranslate2/faster-whisper need the nvidia pip package lib dirs on the
# dynamic linker path in addition to the default nvidia driver paths.
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/lib/python3.10/dist-packages/nvidia/cublas/lib:/usr/local/lib/python3.10/dist-packages/nvidia/cu13/lib"

# Install system dependencies with cache mounts and no-recommends to avoid pulling unnecessary packages
# build-essential + python3-dev are required to compile C extensions (e.g. netifaces)
# curl is required for the HEALTHCHECK below
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    python3-dev \
    ffmpeg \
    build-essential \
    curl \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Ensure pip installs are available system-wide
RUN pip3 install --upgrade pip setuptools wheel

# Create app directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies with cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt

# ctranslate2 4.x dlopens libcublas.so.12 by name (CUDA 12 ABI) via the
# RPATH $ORIGIN/../ctranslate2.libs. Install the matching CUDA 12 cuBLAS pip
# package and symlink it into that RPATH directory so dlopen finds the right ABI.
RUN pip3 install --quiet nvidia-cublas-cu12 && \
    LIBS_DIR=/usr/local/lib/python3.10/dist-packages/ctranslate2.libs && \
    CUBLAS12=$(find /usr/local/lib/python3.10/dist-packages/nvidia/cublas/lib -name 'libcublas.so.12' 2>/dev/null | head -1) && \
    CUBLASLT12=$(find /usr/local/lib/python3.10/dist-packages/nvidia/cublas/lib -name 'libcublasLt.so.12' 2>/dev/null | head -1) && \
    if [ -n "$CUBLAS12" ]; then \
        ln -sf "$CUBLAS12"   "$LIBS_DIR/libcublas.so.12"; \
        ln -sf "$CUBLASLT12" "$LIBS_DIR/libcublasLt.so.12"; \
        echo "Linked libcublas.so.12 -> $CUBLAS12"; \
    else \
        echo "WARNING: nvidia-cublas-cu12 not found after install"; exit 1; \
    fi

# Pre-download Whisper models to avoid runtime downloads
# This ensures models are baked into the image for offline/air-gapped operation
RUN python3 -c "from faster_whisper import WhisperModel; \
    print('Downloading Whisper base model...'); \
    WhisperModel('base', device='cpu', compute_type='int8'); \
    print('Downloading Whisper large model...'); \
    WhisperModel('large', device='cpu', compute_type='int8'); \
    print('All models downloaded successfully')"

# Verify gunicorn is installed
RUN which gunicorn && gunicorn --version

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads thumbs jobs cache config output

# Expose port
EXPOSE 10000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:10000/api/vram || exit 1

# Start command using gunicorn with eventlet for WebSocket support
CMD ["python3", "-m", "gunicorn", "-k", "eventlet", "-w", "1", "--bind", "0.0.0.0:10000", "--timeout", "300", "--keep-alive", "5", "app:app"]
