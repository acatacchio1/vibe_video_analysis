#!/usr/bin/env python3
"""Run WebSocket handler tests"""
import sys
import os
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Run pytest on the test file
test_file = "tests/unit/websocket/test_handlers.py"
print(f"Running tests from {test_file}...")

# Try to import and run tests manually
import pytest

# Run pytest programmatically
exit_code = pytest.main([
    test_file,
    "-v",
    "--tb=short"
])

sys.exit(exit_code)