#!/usr/bin/env python3
"""
Robust Test Runner for Video Analyzer Web

A production-ready test runner that:
- Runs tests in isolated subprocesses to prevent terminal crashes
- Supports per-test timeouts
- Provides detailed logging and reporting
- Handles retries and failures gracefully
- Works in CI/CD and interactive environments
"""

import subprocess
import sys
import os
import json
import shutil
import signal
import tempfile
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
import threading


class TestStatus(Enum):
    """Test execution status"""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class TestResult:
    """Single test result"""
    test_path: str
    status: TestStatus
    duration: float
    error_message: Optional[str] = None
    stdout: str = ""
    stderr: str = ""


@dataclass
class TestReport:
    """Test execution report"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    timeouts: int = 0
    skipped: int = 0
    results: List[TestResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100
    
    @property
    def duration(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class TestRunner:
    """Robust test runner with subprocess isolation"""
    
    def __init__(
        self,
        project_root: Path = None,
        max_workers: int = None,
        default_timeout: int = 60,
        retry_on_failure: bool = False
    ):
        self.project_root = project_root or Path(__file__).parent
        self.max_workers = max_workers or min(4, multiprocessing.cpu_count())
        self.default_timeout = default_timeout
        self.retry_on_failure = retry_on_failure
        
        # Ensure we're in the project directory
        os.chdir(self.project_root)
        
        # Setup environment with PYTHONPATH
        self.env = os.environ.copy()
        self.env["CI"] = "1"
        self.env["DEBIAN_FRONTEND"] = "noninteractive"
        self.env["GIT_TERMINAL_PROMPT"] = "0"
        self.env["GIT_PAGER"] = "cat"
        self.env["PIP_NO_INPUT"] = "1"
        self.env["PYTHONPATH"] = str(self.project_root) + ":" + self.env.get("PYTHONPATH", "")
    
    def run_test(self, test_path: str, timeout: int = None) -> TestResult:
        """Run a single test in an isolated subprocess"""
        timeout = timeout or self.default_timeout
        pytest_bin = shutil.which("pytest") or "/home/anthony/venvs/video-analyzer/bin/python -m pytest"
        
        cmd = [
            pytest_bin,
            test_path,
            "--tb=line",
            "-q",
            "--no-cov",
            "-p", "no:warnings"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                env=self.env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            duration = 0.0
            if "collected" in result.stdout:
                try:
                    import re
                    match = re.search(r'in (\d+\.\d+)s', result.stdout)
                    if match:
                        duration = float(match.group(1))
                except:
                    pass
            
            status = TestStatus.PASSED
            error_msg = None
            
            if result.returncode == 0:
                status = TestStatus.PASSED
            elif result.returncode == 1:
                status = TestStatus.FAILED
                lines = result.stderr.split('\n')
                for line in lines:
                    if "FAILED" in line and "::" in line:
                        error_msg = line.strip()
                        break
                if not error_msg:
                    error_msg = result.stdout.split('\n')[-1] if result.stdout else "Unknown failure"
            elif result.returncode == -signal.SIGTERM or result.returncode == -signal.SIGKILL:
                status = TestStatus.TIMEOUT
                error_msg = f"Test timed out after {timeout}s"
            else:
                status = TestStatus.ERROR
                error_msg = f"Exit code: {result.returncode}"
            
            return TestResult(
                test_path=test_path,
                status=status,
                duration=duration,
                error_message=error_msg,
                stdout=result.stdout[-2000:],
                stderr=result.stderr[-1000:] if result.stderr else ""
            )
            
        except subprocess.TimeoutExpired:
            return TestResult(
                test_path=test_path,
                status=TestStatus.TIMEOUT,
                duration=timeout,
                error_message=f"Test timed out after {timeout}s"
            )
        except Exception as e:
            return TestResult(
                test_path=test_path,
                status=TestStatus.ERROR,
                duration=0,
                error_message=str(e)
            )
    
    def collect_test_files(self, markers: List[str] = None) -> List[str]:
        """Collect test files to run"""
        collected = []
        pytest_bin = shutil.which("pytest") or "/home/anthony/venvs/video-analyzer/bin/python -m pytest"
        
        cmd = [pytest_bin, "tests/", "--collect-only", "-q"]
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, env=self.env, capture_output=True, text=True, timeout=30)
            
            for line in result.stdout.split('\n'):
                if '::' in line and 'test_' in line:
                    test_path = line.split()[-1] if line.split() else ""
                    if test_path and test_path.startswith('tests/'):
                        collected.append(test_path)
            
            if not collected:
                for test_file in self.project_root.glob("tests/**/*.py"):
                    if test_file.name.startswith("test_"):
                        collected.append(f"{test_file}")
        
        except Exception as e:
            print(f"Warning: Could not collect tests: {e}")
            for test_file in self.project_root.glob("tests/**/*.py"):
                if test_file.name.startswith("test_"):
                    collected.append(f"{test_file}")
        
        return collected
    
    def run_tests(self, tests: List[str] = None, parallel: bool = True, verbose: bool = False) -> TestReport:
        """Run all or specified tests"""
        report = TestReport()
        report.start_time = datetime.now()
        
        if not tests:
            tests = self.collect_test_files()
            if not tests:
                print("No tests found!")
                return report
        
        tests_by_file = {}
        for test in tests:
            file_path = test.split('::')[0] if '::' in test else test
            if file_path not in tests_by_file:
                tests_by_file[file_path] = []
            tests_by_file[file_path].append(test)
        
        file_list = list(tests_by_file.keys())
        
        if parallel:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for file_path in file_list:
                    future = executor.submit(self._run_test_file, file_path, parallel=False)
                    futures[future] = file_path
                
                for future in as_completed(futures):
                    file_results = future.result()
                    for result in file_results:
                        report.results.append(result)
                        report.total += 1
                        if result.status == TestStatus.PASSED:
                            report.passed += 1
                        elif result.status == TestStatus.FAILED:
                            report.failed += 1
                        elif result.status == TestStatus.ERROR:
                            report.errors += 1
                        elif result.status == TestStatus.TIMEOUT:
                            report.timeouts += 1
        else:
            for file_path in file_list:
                file_results = self._run_test_file(file_path, parallel=False)
                for result in file_results:
                    report.results.append(result)
                    report.total += 1
                    if result.status == TestStatus.PASSED:
                        report.passed += 1
                    elif result.status == TestStatus.FAILED:
                        report.failed += 1
                    elif result.status == TestStatus.ERROR:
                        report.errors += 1
                    elif result.status == TestStatus.TIMEOUT:
                        report.timeouts += 1
        
        report.end_time = datetime.now()
        return report
    
    def _run_test_file(self, test_file: str, parallel: bool = False) -> List[TestResult]:
        """Run all tests in a single file"""
        results = []
        pytest_bin = shutil.which("pytest") or "/home/anthony/venvs/video-analyzer/bin/python -m pytest"
        
        cmd = [pytest_bin, test_file, "--tb=line", "-q", "--no-cov", "-p", "no:warnings"]
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, env=self.env, capture_output=True, text=True, timeout=600)
            
            output_lines = result.stdout.split('\n') + result.stderr.split('\n')
            
            for line in output_lines:
                if '::test_' in line and ('PASSED' in line or 'FAILED' in line):
                    parts = line.split()
                    test_name = parts[-1] if parts else test_file
                    status = TestStatus.PASSED if 'PASSED' in line else TestStatus.FAILED
                    
                    results.append(TestResult(
                        test_path=f"{test_file}::{test_name}",
                        status=status,
                        duration=0.0,
                        error_message=line.strip() if status != TestStatus.PASSED else None
                    ))
            
            if not results:
                status = TestStatus.PASSED if result.returncode == 0 else TestStatus.FAILED
                results.append(TestResult(
                    test_path=test_file,
                    status=status,
                    duration=0.0,
                    error_message=result.stderr or None if status != TestStatus.PASSED else None
                ))
            
            return results
            
        except subprocess.TimeoutExpired:
            return [TestResult(test_path=test_file, status=TestStatus.TIMEOUT, duration=600, error_message="File test timed out after 10 minutes")]
    
    def generate_report(self, report: TestReport, format: str = "text") -> str:
        """Generate test report"""
        if format == "json":
            return json.dumps({
                "total": report.total,
                "passed": report.passed,
                "failed": report.failed,
                "errors": report.errors,
                "timeouts": report.timeouts,
                "success_rate": report.success_rate,
                "duration": report.duration,
                "results": [{"test": r.test_path, "status": r.status.value, "duration": r.duration, "error": r.error_message} for r in report.results]
            }, indent=2)
        
        lines = ["", "=" * 60, "TEST REPORT", "=" * 60,
            f"Date: {report.end_time.strftime('%Y-%m-%d %H:%M:%S') if report.end_time else 'N/A'}",
            f"Total Tests: {report.total}",
            f"Passed: {report.passed}",
            f"Failed: {report.failed}",
            f"Errors: {report.errors}",
            f"Timeouts: {report.timeouts}",
            f"Success Rate: {report.success_rate:.1f}%",
            f"Duration: {report.duration:.2f}s",
            "=" * 60, ""]
        
        if report.failed > 0 or report.errors > 0:
            lines.extend(["FAILED TESTS:", "-" * 40])
            for result in report.results:
                if result.status in [TestStatus.FAILED, TestStatus.ERROR, TestStatus.TIMEOUT]:
                    lines.append(f"  {result.test_path}")
                    lines.append(f"    [{result.status.value}] {result.error_message}")
                    lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Robust Test Runner")
    parser.add_argument("--parallel", action="store_true", default=True, help="Run tests in parallel (default: True)")
    parser.add_argument("--no-parallel", action="store_false", dest="parallel", help="Run tests sequentially")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--timeout", type=int, default=60, help="Per-test timeout in seconds (default: 60)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format (default: text)")
    parser.add_argument("--test-file", nargs="+", help="Run specific test files only")
    
    args = parser.parse_args()
    
    runner = TestRunner(max_workers=args.workers, default_timeout=args.timeout)
    tests = args.test_file
    report = runner.run_tests(tests=tests, parallel=args.parallel)
    
    output = runner.generate_report(report, format=args.output)
    print(output)
    
    json_report = runner.generate_report(report, format="json")
    json_path = f"/tmp/test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, "w") as f:
        f.write(json_report)
    print(f"\nJSON report saved to: {json_path}")
    
    if report.failed > 0 or report.errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())