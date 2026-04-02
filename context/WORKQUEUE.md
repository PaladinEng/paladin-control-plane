# WORKQUEUE — Paladin Control Plane
Last updated: 2026-04-02T23:15Z

## Active Sprint

(empty — all PCP items complete)

## Recently Completed

## P3 Backlog

### Code quality fixes from session 003 review
project: paladin-control-plane
parallel: YES
blast-radius: NONE
overnight-ready: YES
preconditions: none
done-when:
  - Path traversal guards on all file-serving endpoints
  - Atomic writes for thread.jsonl and prompt-queue.json
  - Dead code removed from project_scanner.py

### [PCP-016] Per-prompt execution log (Option A logging)
project: paladin-control-plane
parallel: YES
blast-radius: NONE
overnight-ready: YES
preconditions: PCP-012 complete
done-when:
  - Every dashboard prompt execution generates a structured log file
    at ~/projects/{project}/logs/prompt-{timestamp}-{id}.md
  - Log contains: prompt text, execution start/end time, files changed,
    git commits made, outcome (success/fail/retry), claude output summary
  - Log files appear as downloadable links in the dashboard project view
    alongside existing session logs
  - Thread completion message links to the execution log
  - CPO execution log from ~/dev/logs/ is referenced or copied into
    the prompt log for full detail

### Future enhancements
- Mobile push notification improvements
- Dashboard search/filter for projects
- Session log viewer with syntax highlighting

## Blocked
- Nothing blocked

## Known Issues
- **cloudflared service location**: Runs as system service at `/etc/systemd/system/cloudflared.service` rather than user service. Works correctly but differs from initial documentation assuming user-only services.
- **queue-run-codex.sh location**: Located at `~/dev/projects/codex-project-orchestrator/scripts/queue-run-codex.sh`, not `~/dev/scripts/`. Update any documentation or scripts that reference the old path.

## Completed
- [x] 2026-03-30 Bootstrap: CLAUDE.md, context files, subagents, settings.json, WORKQUEUE-MASTER integration
- [x] 2026-03-31 PCP-001: ntfy v2.14.0 on port 8090 — paladin-alerts/sessions/errors topics, Claude Code hooks configured
- [x] 2026-03-31 PCP-002: FastAPI backend on port 8080 — /health, /api/projects, /api/projects/{id}, /api/events SSE, systemd user service, boot persistence
- [x] 2026-03-31 PCP-003: Frontend dashboard — dark theme, project cards, detail views, SSE auto-refresh, mobile-responsive
- [x] 2026-04-01 PCP-004: Chat thread and prompt input — per-project thread.jsonl + prompt-queue.json, GET /thread + POST /prompt, frontend chat UI with bubbles and prompt textarea
- [x] 2026-04-01 PCP-005: Meta-supervisor prompt handler — polls prompt-queue.json every 60s, routes prompts to CPO tasks, systemd service paladin-supervisor
- [x] 2026-04-01 PCP-006: Needs-input handling — POST /needs-input + POST /respond, response file mechanism, ntfy deep link notification, amber badge + response form in dashboard, request_input.py helper for pauseable tasks
- [x] 2026-04-01 PCP-007: Cloudflare Tunnel — cloudflared systemd service, public HTTPS at dashboard.paladinrobotics.com
- [x] 2026-04-01 PCP-008: GitHub OAuth authentication — login page, OAuth flow, session cookies, Tailscale bypass, auth middleware, security hardening (header spoof prevention, open redirect fix, XSS escaping)
- [x] 2026-04-01 PCP-009: Overnight meta-supervisor — fixed task.md generation (full objectives, not just acknowledgement), auto-execution via queue-worker-full-pass.sh, overnight.py + systemd timer at 23:00, blast radius enforcement (LOW/NONE only)
- [x] 2026-04-01 PCP-010: Add project archive and restore — archive/restore buttons, collapsed section on home view
- [x] 2026-04-01 PCP-011: Fix claude CLI PATH — systemd override adds ~/.npm-global/bin to PATH, queue-run-codex.sh uses CLAUDE_BIN fallback, end-to-end test passed
- [x] 2026-04-02 PCP-011a: Morning briefing (superseded by PCP-009) — functionality covered by PCP-009 overnight timer and ntfy notifications
- [x] 2026-04-02 PCP-011: Unify notifications, timeout handling, hang detection — unified notify(), timeout thread entries, hang detector with git commit check, prompt pre-marking, FINISHED WORK signal, exit instruction in task templates, 10-min hang threshold
- [x] 2026-04-02 PCP-012: Session log download — clickable download links in project view, GET /api/projects/{id}/logs/{filename} endpoint
- [x] 2026-04-02 PCP-013: Batch prompt upload — file upload (.md/.txt) with ##-section and paragraph parsing, batch/upload endpoints, dashboard UI with preview
- [x] 2026-04-02 PCP-014: Spawn new projects from dashboard — New Project button, form with project name/repo/description, creates local directory and context files
- [x] 2026-04-02 PCP-015: WORKQUEUE web editor — add/edit/reprioritize WORKQUEUE items from project view form
- [x] 2026-04-02 PCP-017: Project creation system v1.1 — 4-mode creation (existing-repo, new-repo, imported-repo, prompted-start), .paladin-config.yaml shared config, provisioning status badge, CPO task generation, file upload for briefs
- [x] 2026-04-02 FIX: Sequential queue execution — prompts executed in order, not parallel
- [x] 2026-04-02 FIX: Heartbeat log every poll cycle — supervisor logs heartbeat each poll iteration
- [x] 2026-04-02 FIX: Poll interval reduced to 30 seconds — faster prompt pickup
- [x] 2026-04-02 FIX: Runtime status (running/queued/idle) — dashboard shows live execution state
- [x] 2026-04-02 FIX: StreamHandler removed, log dedup fixed — no more duplicate log lines
- [x] 2026-04-02 FIX: CPO retry path — exponential backoff (0/60/120/300/600s), max 5 attempts, manual-only warning in queue-handoff.sh, hang detector with exponential backoff in poll_prompts.py
- [x] 2026-04-02 PCP-016: Fix SSE broadcast code duplication — extracted broadcast_project_update() helper, eliminated duplicate broadcast logic from publish_event and all route files
- [x] 2026-04-02 PCP-017b: Fix respond endpoint double-tap race — submit_response checks already-responded atomically, returns 409 on duplicate, frontend button disabled on click
- [x] 2026-04-02 PCP-018: Fix hardcoded DATA_ROOT paths — created backend/config.py as single source of truth, all 6 files (3 backend services, 1 route, 2 supervisor scripts) import from it, supports PALADIN_DATA_ROOT env var override
