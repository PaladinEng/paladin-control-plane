# Paladin Control Plane — Smoke Test Report
Date: 2026-04-02
Tester: Claude Code (autonomous)

## Results Summary

| Test | Component | Result | Notes |
|---|---|---|---|
| 1 | Service: paladin-api | PASS | systemd user service active |
| 1 | Service: paladin-supervisor | PASS | systemd user service active |
| 1 | Service: ntfy | PASS | systemd system service active |
| 1 | Service: cloudflared | PASS* | system service (not user) — active since 2026-04-01 |
| 1 | Service: paladin-overnight.timer | PASS | next trigger 2026-04-02 23:00 UTC |
| 2 | API: GET /health | PASS | {"status":"ok","version":"0.1.0"} |
| 2 | API: GET /api/projects | PASS | 2 projects: homelab-infra, paladin-control-plane |
| 2 | API: GET /api/projects/{id} | PASS | Returns full project detail |
| 2 | API: GET /auth/status | PASS | Tailscale bypass returns authenticated:true |
| 2 | API: GET /api/projects/{id}/thread | PASS | 26 thread entries for PCP |
| 2 | API: POST /archive | PASS | Returns {"status":"archived"} |
| 2 | API: POST /restore | PASS | Returns {"status":"active"} |
| 2 | API: POST /needs-input | PASS | Creates needs-input thread entry with UUID |
| 2 | API: POST /respond | PASS | Creates response thread entry |
| 3 | Project scanner | PASS | homelab-infra and paladin-control-plane both found |
| 4 | ntfy: send notification | PASS | Notification posted to paladin-alerts |
| 4 | ntfy: topic accessible | PASS | paladin-alerts/json?poll=1 responds |
| 5 | CPO queue: structure | PASS | All 4 queue dirs exist |
| 5 | CPO queue: active items | PASS | 1 item (this smoke test task) |
| 5 | CPO queue: queue-run-codex.sh | NOTE | Script at ~/dev/projects/codex-project-orchestrator/scripts/, uses `codex` CLI |
| 6 | Meta-supervisor: PATH | PASS | npm-global in service PATH |
| 6 | Meta-supervisor: activity | PASS | Recent log entries show task creation |
| 6 | Meta-supervisor: data dirs | PASS | Exist for both projects |
| 7 | Overnight timer: listed | PASS | Timer active in systemd |
| 7 | Overnight timer: syntax | PASS | overnight.py compiles cleanly |
| 7 | Overnight timer: parser | PASS | 0 overnight-ready tasks (expected) |
| 8 | OAuth: client ID | PASS | Loaded in service environment |
| 8 | OAuth: AuthMiddleware | PASS | Registered in main.py |
| 8 | OAuth: Tailscale bypass | PASS | TAILSCALE_PREFIXES in auth_service.py |
| 9 | Frontend: files | PASS | All 6 expected files present |
| 9 | Frontend: archive functions | PASS | archiveProject/restoreProject in api.js |
| 10 | Cloudflare: service | PASS* | System service active (not user service) |
| 10 | Cloudflare: public URL | PASS | dashboard.paladinrobotics.com responds |

## Failed Tests

None — all tests passed.

## Notes

- cloudflared runs as a system service at `/etc/systemd/system/cloudflared.service`, not as a systemd user service. Previous documentation implied user service. This is functioning correctly.
- `queue-run-codex.sh` has moved to `~/dev/projects/codex-project-orchestrator/scripts/` (not `~/dev/scripts/`). The script uses the `codex` CLI command, not `claude`. The CLAUDE_BIN/npm-global PATH fix from PCP-011 was applied to the supervisor service environment, not to the script itself.
- Supervisor log shows duplicate log lines for task creation/routing — cosmetic, not a functional issue.

## Recommended Fixes

1. Update documentation to reflect cloudflared is a system service
2. Update any references to queue-run-codex.sh path
3. Investigate duplicate supervisor log entries (low priority)

## System Health: HEALTHY

All core services operational. All API endpoints responding correctly. Authentication, notifications, and tunnel access verified working.
