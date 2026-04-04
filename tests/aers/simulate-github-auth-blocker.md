This is an AERS test task. Simulate a github-auth blocker.

Steps:
1. Write "step 1 complete" to /tmp/aers-test-github-auth.txt
2. Commit: git add -A && git commit -m "test: aers github-auth simulation [ckpt 1]"
3. Simulate a blocked git push by writing blocker.json:

Write the following to ~/dev/queue/active/{TASK_NAME}/blocker.json:
{
  "type": "github-auth",
  "fingerprint": "github-auth-paladin-control-plane",
  "description": "AERS TEST: Simulated GitHub auth failure",
  "symptoms": ["fatal: The requested URL returned error: 403"],
  "fix_instructions": "This is a test blocker. Reply 'cleared' in the dashboard to resume.",
  "resumable": true,
  "checkpoint_commit": "REPLACE_WITH_ACTUAL_COMMIT_HASH",
  "completed_steps": ["Wrote test file", "Made checkpoint commit"],
  "remaining_steps": ["Push to origin (blocked)", "Verify push succeeded"],
  "affects_projects": ["paladin-control-plane"],
  "timestamp": "REPLACE_WITH_ISO_TIMESTAMP"
}

Replace REPLACE_WITH_ACTUAL_COMMIT_HASH with the output of: git rev-parse HEAD
Replace REPLACE_WITH_ISO_TIMESTAMP with: date -u +%Y-%m-%dT%H:%M:%SZ

4. After writing blocker.json, print FINISHED WORK and exit.
