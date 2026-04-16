#!/bin/bash
# Video Analyzer Web - Startup Script

echo "🎬 Video Analyzer Web - Starting up..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker compose is available (newer Docker CLI plugin)
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose plugin is not installed. Please install Docker Compose."
    echo "   Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads thumbs jobs cache config output

# Check for NVIDIA runtime
if nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA GPU detected"
else
    echo "⚠️  No NVIDIA GPU detected. GPU features will be disabled."
fi

# Build and start containers
echo "🐳 Building and starting Docker containers..."
docker compose up --build -d

# Wait for service to be ready
echo "⏳ Waiting for service to be ready..."
sleep 5

# Check if service is running
if curl -s http://localhost:10000 > /dev/null; then
    echo ""
    echo "✅ Video Analyzer Web is running!"
    echo ""
    echo "🌐 Web Interface: http://localhost:10000"
    echo ""
    echo "📊 View logs: docker compose logs -f"
    echo "🛑 Stop: docker compose down"
    echo ""
else
    echo "⚠️  Service may still be starting. Check logs with: docker compose logs -f"
fi
