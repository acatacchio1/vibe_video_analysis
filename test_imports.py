#!/usr/bin/env python3
"""
Test imports for API tests
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("Testing imports...")

try:
    from src.api.jobs import jobs_bp
    print("✅ Imported jobs_bp")
except Exception as e:
    print(f"❌ Failed to import jobs_bp: {e}")

try:
    from src.api.videos import videos_bp
    print("✅ Imported videos_bp")
except Exception as e:
    print(f"❌ Failed to import videos_bp: {e}")

try:
    from src.api.llm import llm_bp
    print("✅ Imported llm_bp")
except Exception as e:
    print(f"❌ Failed to import llm_bp: {e}")

try:
    from src.api.providers import providers_bp
    print("✅ Imported providers_bp")
except Exception as e:
    print(f"❌ Failed to import providers_bp: {e}")

print("\nAll imports tested.")