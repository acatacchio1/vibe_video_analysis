#!/bin/bash
set -e

cd /home/anthony/video-analyzer-web
export PYTHONPATH=/home/anthony/video-analyzer-web:$PYTHONPATH

PASSED=0
FAILED=0

echo "=== TEST SUITE ==="
echo "Date: $(date)"
echo ""

for test_file in $(find tests -name "test_*.py" -type f | sort); do
    output=$(timeout 30 python -m pytest "$test_file" --tb=no -q --no-cov -p no:warnings 2>&1) || true
    
    if echo "$output" | grep -q "passed"; then
        p=$(echo "$output" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo "0")
        f=$(echo "$output" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")
        [ -z "$p" ] && p=0
        [ -z "$f" ] && f=0
        PASSED=$((PASSED + p))
        FAILED=$((FAILED + f))
        
        if [ "$f" -eq 0 ]; then
            echo "OK   $test_file ($p passed)"
        else
            echo "FAIL $test_file ($p passed, $f failed)"
        fi
    else
        echo "ERR  $test_file (no results)"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "=== SUMMARY ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
TOTAL=$((PASSED + FAILED))
if [ $TOTAL -gt 0 ]; then
    RATE=$((PASSED * 100 / TOTAL))
    echo "Success Rate: ${RATE}% ($PASSED / $TOTAL)"
fi

exit $([ $FAILED -gt 0 ] && echo 1 || echo 0)
