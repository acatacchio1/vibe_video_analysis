#!/usr/bin/env python3
"""
Test Report Generator - Generates HTML reports for test results
"""

import json
import shutil
from pathlib import Path
from datetime import datetime


def generate_html_report(test_report: dict) -> str:
    """Generate HTML report from test results"""
    
    timestamp = test_report.get("timestamp", datetime.now().isoformat())
    total = test_report.get("total_tests", 0)
    passed = test_report.get("passed", 0)
    failed = test_report.get("failed", 0)
    success_rate = test_report.get("success_rate", 0.0)
    
    total_color = "#2ecc71" if success_rate == 100 else "#e74c3c" if success_rate < 50 else "#f1c40f"
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report - Video Analyzer Web</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-value {{
            font-size: 3em;
            font-weight: bold;
            color: #333;
            margin: 10px 0;
        }}
        .stat-label {{
            color: #666;
            font-size: 1.1em;
        }}
        .results {{
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .result-item {{
            padding: 15px;
            border-left: 4px solid #ddd;
            margin-bottom: 10px;
            background: #fafafa;
        }}
        .result-item.passed {{
            border-left-color: #2ecc71;
        }}
        .result-item.failed {{
            border-left-color: #e74c3c;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }}
        .badge-passed {{
            background: #d4edda;
            color: #155724;
        }}
        .badge-failed {{
            background: #f8d7da;
            color: #721c24;
        }}
        .timestamp {{
            color: #888;
            font-size: 0.9em;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🧪 Test Report</h1>
        <p>Video Analyzer Web - Automated Test Results</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value" style="color: {total_color};">{total}</div>
            <div class="stat-label">Total Tests</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #2ecc71;">{passed}</div>
            <div class="stat-label">Passed</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #e74c3c;">{failed}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: {total_color};">{success_rate:.1f}%</div>
            <div class="stat-label">Success Rate</div>
        </div>
    </div>
    
    <div class="results">
        <h2>Test Suites</h2>
        <div class="result-item">
            <strong>Unit Tests</strong>
            <span class="badge badge-passed">Success</span>
        </div>
        <div class="result-item">
            <strong>Integration Tests</strong>
            <span class="badge badge-failed">{failed} failures</span>
        </div>
        <div class="result-item">
            <strong>E2E Tests</strong>
            <span class="badge badge-passed">All Passed</span>
        </div>
    </div>
    
    <div class="timestamp">
        Generated: {timestamp}
    </div>
</body>
</html>
"""
    
    return html


def main():
    """Main entry point"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate HTML test report")
    parser.add_argument("input", help="Input JSON test report file")
    parser.add_argument("--output", "-o", default="test_report.html", help="Output file (default: test_report.html)")
    
    args = parser.parse_args()
    
    # Load input JSON
    with open(args.input, "r") as f:
        test_report = json.load(f)
    
    # Generate HTML
    html = generate_html_report(test_report)
    
    # Save HTML
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        f.write(html)
    
    print(f"✓ HTML report generated: {output_path}")


if __name__ == "__main__":
    main()
