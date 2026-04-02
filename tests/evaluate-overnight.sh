#!/usr/bin/env bash
# Evaluate overnight test results
# Run this in the morning to check what passed

echo "=== Overnight Test Evaluation ==="
echo "Date: $(date)"
echo ""

PASS=0
FAIL=0

check() {
    local name="$1"
    local file="$2"
    local expected="$3"

    if [ ! -f "$file" ]; then
        echo "FAIL: $name — file not found: $file"
        ((FAIL++))
        return
    fi

    if grep -q "$expected" "$file" 2>/dev/null; then
        echo "PASS: $name"
        ((PASS++))
    else
        echo "FAIL: $name — expected '$expected' in $file"
        echo "  Actual content: $(head -3 "$file")"
        ((FAIL++))
    fi
}

check "Test 1 - Simple completion" \
    /tmp/overnight-test-1.txt "cpo-overnight-test-1"

check "Test 2 - Sequential verification" \
    /tmp/overnight-test-2.txt "verified"

check "Test 3 - Long running task" \
    /tmp/overnight-test-3.txt "end"

check "Test 4 - Git operations" \
    /tmp/overnight-test-4.txt "branch"

check "Test 5 - API verification" \
    /tmp/overnight-test-5.txt "paladin-control-plane"

check "Test 6 - Cluster health" \
    /tmp/overnight-test-6.txt "Ready"

echo ""
echo "=== Results ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
echo ""

# Show supervisor log summary
echo "=== Supervisor log summary ==="
grep -E "completed|failed|FINISHED WORK|Hang detected" \
    ~/projects/paladin-control-plane/logs/supervisor.log | tail -20

# Show timing stats
echo ""
echo "=== Queue timing ==="
grep "cleared in\|elapsed" /tmp/cpo-test-run-*.log 2>/dev/null | tail -10
