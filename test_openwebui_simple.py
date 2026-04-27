#!/usr/bin/env python3
"""
Simple test to verify OpenWebUI KB tests work
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the test module
from tests.unit.services.test_openwebui_kb import TestOpenWebUIClient, TestFormatResultsAsMarkdown

print("Testing OpenWebUIClient class...")
client_tests = TestOpenWebUIClient()
client = client_tests.test_init()
print("✓ test_init passed")

# Test format_results_as_markdown
print("\nTesting format_results_as_markdown function...")
format_tests = TestFormatResultsAsMarkdown()

# Test basic formatting
results = {
    "metadata": {
        "date": "2024-01-01",
        "model": "llama3.2",
        "provider": "ollama",
        "frames_processed": 10,
    }
}
markdown = format_tests.test_format_results_basic()
print("✓ test_format_results_basic passed")

print("\nAll basic tests passed!")