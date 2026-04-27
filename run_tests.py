#!/usr/bin/env python3
"""
Sequential test runner - runs one test file at a time to avoid crashes
"""
import subprocess
import sys
import os
import re
from pathlib import Path
from datetime import datetime

def main():
    os.chdir(Path(__file__).parent)
    os.environ["PYTHONPATH"] = str(Path(__file__).parent)
    
    test_files = sorted(Path("tests").rglob("test_*.py"))
    
    print("=" * 60)
    print("TEST SUITE - Video Analyzer Web")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Files: {len(test_files)}")
    print()
    
    total_passed = 0
    total_failed = 0
    
    for i, tf in enumerate(test_files, 1):
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", str(tf), "--tb=no", "-q", "--no-cov", "-p", "no:warnings"],
                capture_output=True, text=True, timeout=30
            )
            
            summary = r.stdout.strip().split('\n')[-1] if r.stdout else ''
            p = int(re.search(r'(\d+) passed', summary).group(1)) if re.search(r'(\d+) passed', summary) else 0
            f = int(re.search(r'(\d+) failed', summary).group(1)) if re.search(r'(\d+) failed', summary) else 0
            
            total_passed += p
            total_failed += f
            
            status = "OK" if f == 0 else "FAIL"
            print(f"{i:3d}. [{status:4s}] {str(tf):60s} p={p} f={f}")
            
            if f > 0:
                for line in r.stdout.split('\n'):
                    if 'FAILED' in line and '::' in line:
                        print(f"     {line.strip()}")
                        
        except subprocess.TimeoutExpired:
            total_failed += 1
            print(f"{i:3d}. [TIME] {str(tf):60s} timed out")
        except Exception as e:
            total_failed += 1
            print(f"{i:3d}. [ERR ] {str(tf):60s} {e}")
    
    total = total_passed + total_failed
    rate = (total_passed / total * 100) if total > 0 else 0
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total: {total}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Success Rate: {rate:.1f}%")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "passed": total_passed,
        "failed": total_failed,
        "success_rate": round(rate, 1)
    }
    
    report_file = f"/tmp/test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import json
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport: {report_file}")
    
    return 0 if total_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
