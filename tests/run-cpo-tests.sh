#!/usr/bin/env bash
# CPO Test Runner
# Submits test prompts via the dashboard API and evaluates results
# Usage: bash run-cpo-tests.sh [test-number]

set -euo pipefail

API="http://localhost:8080"
PROJECT="paladin-control-plane"
LOG="/tmp/cpo-test-run-$(date +%Y%m%dT%H%M%S).log"
PASS=0
FAIL=0
SKIP=0

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
pass() { log "PASS: $*"; ((PASS++)); }
fail() { log "FAIL: $*"; ((FAIL++)); }

submit_prompt() {
    local content="$1"
    curl -s -X POST "$API/api/projects/$PROJECT/prompt" \
        -H "Content-Type: application/json" \
        -d "{\"content\": $(echo "$content" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])"
}

wait_for_queue_empty() {
    local max_wait="${1:-300}"
    local elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        ACTIVE=$(ls ~/dev/queue/active/ 2>/dev/null | wc -l)
        PENDING=$(ls ~/dev/queue/pending/ 2>/dev/null | wc -l)
        [ "$ACTIVE" -eq 0 ] && [ "$PENDING" -eq 0 ] && return 0
        sleep 10
        elapsed=$((elapsed + 10))
    done
    return 1
}

# Clean up previous test artifacts
rm -f /tmp/cpo-test-*.txt

log "=== CPO Test Run starting ==="
log "API: $API"
log "Project: $PROJECT"
log ""

# Determine which tests to run
RUN_TEST="${1:-all}"

# TEST 1 — Simple completion
if [ "$RUN_TEST" = "all" ] || [ "$RUN_TEST" = "1" ]; then
    log "--- TEST 1: Simple completion ---"
    submit_prompt "Write the text test-01-complete to /tmp/cpo-test-01.txt then print FINISHED WORK and exit."
    if wait_for_queue_empty 120 && \
        [ -f /tmp/cpo-test-01.txt ] && \
        grep -q "test-01-complete" /tmp/cpo-test-01.txt; then
        pass "Simple completion — file created, queue cleared"
    else
        fail "Simple completion — check /tmp/cpo-test-01.txt"
    fi
fi

# TEST 2 — Sequential queue (5 prompts)
if [ "$RUN_TEST" = "all" ] || [ "$RUN_TEST" = "2" ]; then
    log "--- TEST 2: Sequential queue ---"
    for i in 1 2 3 4 5; do
        submit_prompt "Write the text sequential-${i} to /tmp/cpo-test-04-${i}.txt then print FINISHED WORK and exit."
    done
    if wait_for_queue_empty 600; then
        all_exist=true
        for i in 1 2 3 4 5; do
            if [ ! -f "/tmp/cpo-test-04-${i}.txt" ]; then
                all_exist=false
                log "  Missing: /tmp/cpo-test-04-${i}.txt"
            fi
        done
        if $all_exist; then
            pass "Sequential queue — all 5 files created in order"
        else
            fail "Sequential queue — missing files"
        fi
    else
        fail "Sequential queue — timed out waiting for queue to empty"
    fi
fi

# TEST 3 — Timing check
if [ "$RUN_TEST" = "all" ] || [ "$RUN_TEST" = "3" ]; then
    log "--- TEST 3: Exit timing ---"
    START=$(date +%s)
    submit_prompt "Write the text timing-test to /tmp/cpo-test-timing.txt then print FINISHED WORK and exit."
    wait_for_queue_empty 120
    ELAPSED=$(( $(date +%s) - START ))
    if [ $ELAPSED -lt 90 ]; then
        pass "Exit timing — cleared in ${ELAPSED}s (< 90s threshold)"
    else
        fail "Exit timing — took ${ELAPSED}s (> 90s threshold)"
    fi
fi

# Summary
log ""
log "=== Test Run Complete ==="
log "PASS: $PASS"
log "FAIL: $FAIL"
log "SKIP: $SKIP"
log "Log: $LOG"

[ $FAIL -eq 0 ] && exit 0 || exit 1
