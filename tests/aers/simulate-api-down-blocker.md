This is an AERS test task. Simulate an api-down blocker.

Steps:
1. Write "api-down test start" to /tmp/aers-test-api-down.txt
2. Simulate API down by writing blocker.json to the active task directory:

Write to ~/dev/queue/active/{TASK_NAME}/blocker.json:
{
  "type": "api-down",
  "fingerprint": "api-down-paladin-control-plane",
  "description": "AERS TEST: Simulated API down condition",
  "symptoms": ["curl: (7) Failed to connect to localhost port 8080"],
  "fix_instructions": "This is a test blocker. Reply 'cleared' in dashboard.",
  "resumable": true,
  "checkpoint_commit": null,
  "completed_steps": ["Wrote test file"],
  "remaining_steps": ["API health check (blocked)", "Continue with task"],
  "affects_projects": ["paladin-control-plane"],
  "timestamp": "REPLACE_WITH_ISO_TIMESTAMP"
}

3. Print FINISHED WORK and exit.
