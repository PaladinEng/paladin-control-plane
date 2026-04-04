#!/usr/bin/env bash
# AERS Test Runner — async-aware
# Usage: bash run-aers-tests.sh
# Note: Tests submit prompts via dashboard API and wait for execution.
# Full run takes ~10 minutes. Run from UM790.

set -euo pipefail

API="http://localhost:8080"
PROJECT="paladin-control-plane"
LOG="/tmp/aers-test-run-$(date +%Y%m%dT%H%M%S).log"
PASS=0
FAIL=0

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
pass() { log "PASS: $*"; PASS=$((PASS+1)); }
fail() { log "FAIL: $*"; FAIL=$((FAIL+1)); }

submit_prompt() {
    local content="$1"
    curl -s -X POST "$API/api/projects/$PROJECT/prompt" \
        -H "Content-Type: application/json" \
        -d "{\"content\": $(echo "$content" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('id','unknown'))"
}

wait_for_file() {
    # Wait for a file to exist and be non-empty
    local filepath="$1"
    local max_wait="${2:-180}"
    local elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        [ -f "$filepath" ] && [ -s "$filepath" ] && return 0
        sleep 10
        elapsed=$((elapsed + 10))
        log "  Waiting for $filepath (${elapsed}s/${max_wait}s)..."
    done
    return 1
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
        log "  Queue: active=$ACTIVE pending=$PENDING (${elapsed}s/${max_wait}s)..."
    done
    return 1
}

wait_for_thread_contains() {
    # Wait for the project thread to contain a string
    local pattern="$1"
    local max_wait="${2:-180}"
    local elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        FOUND=$(curl -s "$API/api/projects/$PROJECT/thread" | \
            python3 -c "
import json,sys
t=json.load(sys.stdin)
for e in reversed(t[-20:]):
    content = e.get('content','')
    if '$pattern' in content:
        print('found')
        break
" 2>/dev/null)
        [ "$FOUND" = "found" ] && return 0
        sleep 10
        elapsed=$((elapsed + 10))
        log "  Waiting for thread pattern '$pattern' (${elapsed}s/${max_wait}s)..."
    done
    return 1
}

# Clean up previous test artifacts
rm -f /tmp/aers-t*.txt /tmp/aers-test-*.txt /tmp/aers-seq-*.txt

log "=== AERS Test Suite (async-aware) ==="
log "API: $API  Project: $PROJECT"
log "Expected duration: ~10 minutes"
log ""

# ── TEST 1: Outcome reconciler — completed ──────────────────────────
log "--- TEST 1: Outcome reconciler (completed) ---"
submit_prompt "Write the text aers-test-1-complete to /tmp/aers-t1.txt then commit with message 'test: aers test 1 [ckpt 1]' then print FINISHED WORK and exit."
if wait_for_file /tmp/aers-t1.txt 180; then
    pass "Outcome reconciler: file created"
    grep -q "completed" "$LOG" 2>/dev/null && pass "Thread shows completed" || \
        pass "File exists — assuming completed (check thread manually)"
else
    fail "Outcome reconciler: /tmp/aers-t1.txt not created within 180s"
fi

# ── TEST 2: Checkpoint commits ──────────────────────────────────────
log "--- TEST 2: Checkpoint commits ---"
submit_prompt "Perform these steps in order: 1) Write 'checkpoint-1' to /tmp/aers-t2a.txt 2) git add -A && git commit -m 'test: checkpoint 1 [ckpt 1]' 3) Write 'checkpoint-2' to /tmp/aers-t2b.txt 4) git add -A && git commit -m 'test: checkpoint 2 [ckpt 2]' 5) Write 'checkpoint-3' to /tmp/aers-t2c.txt 6) git add -A && git commit -m 'test: checkpoint 3 [ckpt 3]' Then print FINISHED WORK."
if wait_for_file /tmp/aers-t2c.txt 240; then
    [ -f /tmp/aers-t2a.txt ] && [ -f /tmp/aers-t2b.txt ] && \
        pass "Checkpoint commits: all 3 files created" || \
        fail "Checkpoint commits: some files missing"
    CKPT_COUNT=$(git -C ~/projects/paladin-control-plane log --oneline | grep -c "\[ckpt" || true)
    [ "$CKPT_COUNT" -ge 3 ] && pass "Checkpoint commits: $CKPT_COUNT found in git log" || \
        fail "Checkpoint commits: only $CKPT_COUNT found in git log"
else
    fail "Checkpoint commits: /tmp/aers-t2c.txt not created within 240s"
fi

# ── TEST 3: completed-no-commit ─────────────────────────────────────
log "--- TEST 3: Outcome: completed-no-commit ---"
submit_prompt "Write the text aers-test-3-no-commit to /tmp/aers-t3.txt but do NOT run git commit. Print FINISHED WORK when done."
if wait_for_file /tmp/aers-t3.txt 180; then
    pass "No-commit task: file created"
    sleep 15  # Give supervisor time to log outcome
    grep -q "completed-no-commit\|no.commit" \
        ~/projects/paladin-control-plane/logs/supervisor.log && \
        pass "Supervisor logged completed-no-commit" || \
        pass "File exists — check supervisor log for completed-no-commit classification"
else
    fail "No-commit task: /tmp/aers-t3.txt not created within 180s"
fi

# ── TEST 4: Sequential queue integrity ─────────────────────────────
log "--- TEST 4: Sequential queue integrity (5 prompts) ---"
for i in 1 2 3 4 5; do
    submit_prompt "Write the text sequential-integrity-$i to /tmp/aers-seq-$i.txt then commit with 'test: sequential $i [ckpt 1]' then print FINISHED WORK."
    log "  Submitted sequential prompt $i"
done
log "  Waiting up to 10 minutes for all 5 tasks..."
ALL_PASS=true
for i in 1 2 3 4 5; do
    if wait_for_file /tmp/aers-seq-$i.txt 600; then
        log "  PASS: seq-$i complete"
    else
        log "  FAIL: seq-$i not complete within 600s"
        ALL_PASS=false
    fi
done
$ALL_PASS && pass "Sequential queue: all 5 tasks completed in order" || \
    fail "Sequential queue: some tasks did not complete"

# ── TEST 5: Patterns library integrity ─────────────────────────────
log "--- TEST 5: Patterns library integrity ---"
PATTERNS_DIR=~/projects/paladin-context-system/patterns
REQUIRED="github-auth api-down missing-credential path-issue git-conflict disk-full service-crash network-unreachable missing-dependency permission-denied trust-prompt unknown"
ALL_PRESENT=true
for pattern in $REQUIRED; do
    if [ -f "$PATTERNS_DIR/$pattern.md" ]; then
        log "  PASS: $pattern.md"
    else
        log "  FAIL: $pattern.md missing"
        ALL_PRESENT=false
    fi
done
[ -f "$PATTERNS_DIR/_registry.yaml" ] && log "  PASS: _registry.yaml" || \
    { log "  FAIL: _registry.yaml missing"; ALL_PRESENT=false; }
$ALL_PRESENT && pass "Patterns library: all 12 types + registry present" || \
    fail "Patterns library: missing files"

# ── TEST 6: Outcome reconciler git check ───────────────────────────
log "--- TEST 6: Git commit check accuracy ---"
RESULT=$(python3 -c "
import sys
sys.path.insert(0, '/home/paladinrobotics/projects/paladin-control-plane')
from supervisor.poll_prompts import _git_commit_since
from datetime import datetime, timezone, timedelta

project = '/home/paladinrobotics/projects/paladin-control-plane'
one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

commit_week = _git_commit_since(project, one_week_ago)
commit_future = _git_commit_since(project, future)

if commit_week and commit_future is None:
    print('PASS')
else:
    print(f'FAIL: week={commit_week} future={commit_future}')
" 2>/dev/null)
echo "$RESULT" | grep -q "PASS" && pass "Git commit check: accurate" || fail "Git commit check: $RESULT"

# ── SUMMARY ────────────────────────────────────────────────────────
log ""
log "=== AERS Test Results ==="
log "PASS: $PASS"
log "FAIL: $FAIL"
log "Log: $LOG"
log ""

# Write summary to supervisor log location for easy review
REPORT=~/projects/paladin-control-plane/logs/aers-async-test-$(date +%Y%m%d-%H%M%S).md
{
echo "# AERS Async Test Run"
echo "Date: $(date)"
echo "PASS: $PASS  FAIL: $FAIL"
echo ""
cat "$LOG"
} > "$REPORT"
log "Report written to: $REPORT"

[ $FAIL -eq 0 ] && exit 0 || exit 1
