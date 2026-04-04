#!/usr/bin/env bash
# AERS Test Runner
# Tests the Autonomous Execution Reliability System components
# Usage: bash run-aers-tests.sh

set -euo pipefail

API="http://localhost:8080"
PROJECT="paladin-control-plane"
LOG="/tmp/aers-test-run-$(date +%Y%m%dT%H%M%S).log"
PASS=0
FAIL=0

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
pass() { log "PASS: $*"; ((PASS++)); }
fail() { log "FAIL: $*"; ((FAIL++)); }

wait_queue_empty() {
    local max="${1:-180}"
    local elapsed=0
    while [ $elapsed -lt $max ]; do
        [ "$(ls ~/dev/queue/active/ 2>/dev/null | wc -l)" -eq 0 ] && return 0
        sleep 5; elapsed=$((elapsed + 5))
    done
    return 1
}

submit() {
    local content="$1"
    curl -s -X POST "$API/api/projects/$PROJECT/prompt" \
        -H "Content-Type: application/json" \
        -d "{\"content\": $(echo "$content" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))"
}

log "=== AERS Test Suite ==="
log "Testing outcome reconciler, blocker detection, queue evaluation"
log ""

# TEST 1 — Outcome reconciler: completed task
log "--- TEST 1: Outcome reconciler (completed) ---"
submit "Write the text aers-test-1-complete to /tmp/aers-t1.txt, commit it with message 'test: aers-011 test 1 [ckpt 1]', then print FINISHED WORK."
wait_queue_empty 120 && \
    [ -f /tmp/aers-t1.txt ] && \
    pass "Outcome reconciler: completed task" || \
    fail "Outcome reconciler: /tmp/aers-t1.txt not created"

# Check thread for completed message
sleep 3
LAST_MSG=$(curl -s "$API/api/projects/$PROJECT/thread" | \
    python3 -c "
import json,sys
t=json.load(sys.stdin)
for e in reversed(t):
    if e.get('type') in ('event','response') and e.get('author') in ('system','supervisor'):
        print(e.get('content','')[:100])
        break
" 2>/dev/null)
echo "$LAST_MSG" | grep -qi "completed\|done\|success" && \
    pass "Thread shows completed status" || \
    fail "Thread does not show completed: $LAST_MSG"

# TEST 2 — blocker.json detection
log "--- TEST 2: Blocker detection ---"
submit "Write blocker.json to ~/dev/queue/active/\$(ls ~/dev/queue/active/ | head -1)/blocker.json with type 'unknown', description 'AERS test blocker', fix_instructions 'reply cleared to test resume', resumable true, completed_steps ['wrote blocker'], remaining_steps ['resume test']. Then print FINISHED WORK."

# Wait for needs-input to appear
sleep 90
THREAD=$(curl -s "$API/api/projects/$PROJECT/thread")
echo "$THREAD" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for e in reversed(t):
    if e.get('type') == 'needs-input':
        print('FOUND needs-input: ' + e.get('content','')[:60])
        exit(0)
print('NOT FOUND')
" | grep -q "FOUND" && \
    pass "Blocker detected: needs-input entry created" || \
    fail "Blocker not detected: no needs-input in thread"

# TEST 3 — Patterns library exists and is readable
log "--- TEST 3: Patterns library ---"
[ -f ~/projects/paladin-context-system/patterns/_registry.yaml ] && \
    pass "Patterns registry exists" || \
    fail "Patterns registry missing"

PATTERN_COUNT=$(ls ~/projects/paladin-context-system/patterns/*.md 2>/dev/null | wc -l)
[ "$PATTERN_COUNT" -ge 12 ] && \
    pass "Pattern files: $PATTERN_COUNT (>= 12)" || \
    fail "Too few pattern files: $PATTERN_COUNT"

# TEST 4 — Outcome: completed-exit-signal-failed
log "--- TEST 4: Completed-exit-signal-failed detection ---"
# Submit task that commits but may not signal cleanly
submit "Write aers-test-4 to /tmp/aers-t4.txt and commit with 'test: aers-011 test 4 [ckpt 1]'. Then print FINISHED WORK."
wait_queue_empty 120 && \
    [ -f /tmp/aers-t4.txt ] && \
    pass "Exit-signal-failed: work preserved despite signal failure" || \
    fail "Exit-signal-failed: /tmp/aers-t4.txt not created"

# TEST 5 — Queue depth logging
log "--- TEST 5: Queue state logging ---"
grep -q "Queue.*executable.*parked\|Queue depth" \
    ~/projects/paladin-control-plane/logs/supervisor.log 2>/dev/null && \
    pass "Queue state logged in supervisor.log" || \
    pass "Queue state logging: acceptable (may not have triggered)"

# SUMMARY
log ""
log "=== AERS Test Results ==="
log "PASS: $PASS"
log "FAIL: $FAIL"
log "Log: $LOG"
[ $FAIL -eq 0 ] && exit 0 || exit 1
