This is an AERS test task for verifying resume-from-checkpoint.

Steps:
1. Check if ~/dev/queue/active/{TASK_NAME}/blocker.json exists
2. If it does, read completed_steps and log them
3. Write "resume verification complete" to /tmp/aers-test-resume.txt
4. Commit: git add -A && git commit -m "test: aers resume verification [ckpt 1]"
5. Print FINISHED WORK and exit.
