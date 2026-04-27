#!/usr/bin/env python3
"""
Simple sequential test runner - avoids parallel crashes
"""

import subprocess
import sys
import os
import json
from pathlib import Path
from datetime import datetime


def run_test_file(test_file, timeout=60):
    """Run a single test file and return results"""
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "--tb=no",
        "-q",
        "--no-cov",
        "-p", "no:warnings"
    ]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent) + ":" + env.get("PYTHONPATH", "")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=Path(__file__).parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        # Parse results
        passed = 0
        failed = 0
        errors = []
        
        # Count from summary line
        summary = result.stdout.strip().split('\n')[-1] if result.stdout else ""
        if 'passed' in summary:
            import re
            passed_match = re.search(r'(\d+) passed', summary)
            failed_match = re.search(r'(\d+) failed', summary)
            if passed_match:
                passed = int(passed_match.group(1))
            if failed_match:
                failed = int(failed_match.group(1))
        
        # Extract failures
        if failed > 0:
            for line in result.stdout.split('\n'):
                if 'FAILED' in line and '::' in line:
                    errors.append(line.strip())
        
        return {
            'file': str(test_file),
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'exit_code': result.returncode
        }
        
    except subprocess.TimeoutExpired:
        return {
            'file': str(test_file),
            'passed': 0,
            'failed': 0,
            'errors': ['Test timed out'],
            'exit_code': -1
        }


def main():
    """Run all tests sequentially"""
    project_root = Path(__file__).parent
    
    print("=" * 60)
    print("TEST SUITE - Video Analyzer Web")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Find all test files
    test_files = list(project_root.glob("tests/**/test_*.py"))
    test_files.sort()
    
    if not test_files:
        print("No test files found!")
        return 1
    
    print(f"Found {len(test_files)} test files")
    print()
    
    total_passed = 0
    total_failed = 0
    all_errors = []
    
    # Run each file
    for i, test_file in enumerate(test_files, 1):
        print(f"[{i}/{len(test_files)}] Running: {test_file.relative_to(project_root)}")
        
        result = run_test_file(test_file)
        total_passed += result['passed']
        total_failed += result['failed']
        all_errors.extend(result['errors'])
        
        status = "✓" if result['failed'] == 0 else "✗"
        print(f"  {status} {result['passed']} passed, {result['failed']} failed")
        
        if result['errors']:
            for error in result['errors'][:2]:  # Show first 2 errors
                print(f"    - {error}")
    
    # Summary
    total = total_passed + total_failed
    success_rate = (total_passed / total * 100) if total > 0 else 0
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total: {total}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Success Rate: {success_rate:.1f}%")
    print()
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "passed": total_passed,
        "failed": total_failed,
        "success_rate": success_rate
    }
    
    report_file = f"/tmp/test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"Report saved to: {report_file}")
    
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
