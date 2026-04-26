#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Video Analyzer Web E2E Tests ==="
echo "Running tests/e2e/test_e2e_real_video.py"
echo "======================================="

pytest tests/e2e/test_e2e_real_video.py -v --tb=short \
  --timeout=120 \
  -p no:warnings \
  "$@"
