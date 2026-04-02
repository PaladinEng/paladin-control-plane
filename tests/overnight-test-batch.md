## Test 1 — Simple completion
Write the text cpo-overnight-test-1 to /tmp/overnight-test-1.txt
Print FINISHED WORK when done.

## Test 2 — Sequential verification
First check that /tmp/overnight-test-1.txt exists and contains
cpo-overnight-test-1. Write "verified" to /tmp/overnight-test-2.txt
if it does, or "failed" if it doesn't.
Print FINISHED WORK when done.

## Test 3 — Long running task
Write "start" to /tmp/overnight-test-3.txt
Run: sleep 45
Append "middle" to /tmp/overnight-test-3.txt
Run: sleep 45
Append "end" to /tmp/overnight-test-3.txt
Print FINISHED WORK when done.

## Test 4 — Git operations
In ~/projects/paladin-control-plane, run git status and write
the output to /tmp/overnight-test-4.txt
Print FINISHED WORK when done.

## Test 5 — API verification
Run: curl -s http://localhost:8080/api/projects
Write the project IDs found to /tmp/overnight-test-5.txt
Print FINISHED WORK when done.

## Test 6 — Cluster health check
Run: kubectl get nodes
Write the output to /tmp/overnight-test-6.txt
Print FINISHED WORK when done.

## Test 7 — Final summary
Read all /tmp/overnight-test-*.txt files that exist.
Write a summary of what passed and failed to
/tmp/overnight-test-summary.txt
Print FINISHED WORK when done.
