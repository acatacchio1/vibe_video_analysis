#!/usr/bin/env python3
"""Simple test runner for WebSocket handlers"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Set environment variable for OpenRouter test
os.environ["OPENROUTER_API_KEY"] = "test-key"

# Import the test module
from tests.unit.websocket.test_handlers import *

# Run a simple test
print("Testing get_openrouter_api_key...")
result = get_openrouter_api_key()
print(f"Result: {result}")
print("Success!" if result == "test-key" else "Failed!")