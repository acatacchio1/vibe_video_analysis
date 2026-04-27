#!/usr/bin/env python3
"""
Simple test runner for API tests
"""
import sys
import pytest
import os

# Add tests directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Run the API tests
    test_files = [
        "tests/unit/api/test_jobs.py",
        "tests/unit/api/test_videos.py", 
        "tests/unit/api/test_llm.py",
        "tests/unit/api/test_providers.py"
    ]
    
    print("Running API tests...")
    for test_file in test_files:
        print(f"\n{'='*60}")
        print(f"Running {test_file}")
        print('='*60)
        
        # Run pytest on the test file
        exit_code = pytest.main([
            test_file,
            "-v",
            "--tb=short"
        ])
        
        if exit_code != 0:
            print(f"\n❌ Tests in {test_file} failed with exit code {exit_code}")
            sys.exit(exit_code)
        else:
            print(f"\n✅ All tests in {test_file} passed!")
    
    print("\n" + "="*60)
    print("✅ All API tests passed!")
    print("="*60)