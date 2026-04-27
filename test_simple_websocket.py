#!/usr/bin/env python3
"""Simple test for WebSocket handlers"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Test get_openrouter_api_key function
from src.websocket.handlers import get_openrouter_api_key

# Test with environment variable
import os
os.environ["OPENROUTER_API_KEY"] = "test-key-123"
result = get_openrouter_api_key()
print(f"get_openrouter_api_key with env var: {result}")
assert result == "test-key-123"

# Test without environment variable
del os.environ["OPENROUTER_API_KEY"]
result = get_openrouter_api_key()
print(f"get_openrouter_api_key without env var: {result}")
assert result == ""

print("✓ get_openrouter_api_key tests passed")

# Test MockSocketIO class
from tests.unit.websocket.test_handlers import MockSocketIO

mock_sio = MockSocketIO()
print(f"Created MockSocketIO: {mock_sio}")

# Test on decorator
@mock_sio.on("test_event")
def test_handler(data):
    return "handled"

print(f"Registered handlers: {list(mock_sio.handlers.keys())}")
assert "test_event" in mock_sio.handlers

# Test emit
mock_sio.emit("test_event", {"data": "test"}, room="test_room")
print(f"Emit calls: {mock_sio.emit_calls}")
assert len(mock_sio.emit_calls) == 1
assert mock_sio.emit_calls[0][0] == "test_event"

print("✓ MockSocketIO tests passed")

print("\n✅ All simple tests passed!")