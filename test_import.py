#!/usr/bin/env python3
"""Test importing the test module"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from tests.unit.websocket.test_handlers import MockSocketIO
    print("Successfully imported MockSocketIO")
    
    # Try to create an instance
    mock_sio = MockSocketIO()
    print(f"Created MockSocketIO: {mock_sio}")
    
    # Try to import the actual handlers
    from src.websocket.handlers import register_socket_handlers
    print("Successfully imported register_socket_handlers")
    
    print("All imports successful!")
    
except Exception as e:
    print(f"Import error: {e}")
    import traceback
    traceback.print_exc()