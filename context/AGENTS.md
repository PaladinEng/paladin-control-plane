# AGENTS — Paladin Control Plane

## Session Start
1. Read context/STATUS.md — what is deployed, what is blocked
2. Read context/WORKQUEUE.md — pick top unblocked item from Active Sprint
3. Check ~/projects/WORKQUEUE-MASTER.md — cross-project PCP-* priorities
4. Run service health check: `systemctl --user status paladin-api 2>/dev/null; curl -s localhost:8080/health 2>/dev/null`

## Access Patterns
- UM790 (this machine): direct shell — all services run here
- Backend API: localhost:8080
- ntfy: localhost:8090
- Python venv: source ~/projects/paladin-control-plane/.venv/bin/activate
- Project state: ~/projects/*/context/STATUS.md and WORKQUEUE.md
- Systemd user services: systemctl --user {start|stop|status|restart} <service>
- Logs: journalctl --user -u <service> --no-pager -n 50

## Rules
- Always check service health before modifying backend code
- Always run backend with venv activated
- Frontend changes are static files — no build step, just edit and reload
- Never modify other projects' context/ files from this project's agents
- Test all API endpoints with curl before marking tasks complete
- Mobile responsiveness must be verified (use Chrome DevTools device mode)

## Do NOT
- Do not install npm, webpack, or any JS build tools
- Do not create a database — read project state from context/ files
- Do not run services as root — use systemd user units only
- Do not modify k8s cluster resources from this project
- Do not store secrets in git — use environment variables or systemd EnvironmentFile

## Prompt Authoring

When writing prompts for the dashboard, follow these principles:

- **Describe intent, not implementation** — prompts should say WHAT to build
  and the acceptance criteria, not provide inline code or step-by-step HOW.
- **Structure prompts in sections** — the agent reads and implements one
  section at a time, committing after each. Front-load the most important work.
- **Include acceptance criteria** — specify how to verify the work is correct
  (e.g. curl commands, grep checks, test commands).
- **Specify blast radius** — if the change touches shared infrastructure or
  services, note the expected blast radius (LOW/MEDIUM/HIGH).
- **Reference files by path** — point to specific files that need changes
  rather than describing them abstractly.
- **One concern per prompt** — if you have three unrelated tasks, submit
  three prompts. The agent commits incrementally and each prompt should
  be a coherent unit of work.

## Session End Checklist
- [ ] `curl -s localhost:8080/health` returns 200 (if API is deployed)
- [ ] `systemctl --user status paladin-api` shows active (if deployed)
- [ ] context/STATUS.md updated with what was done
- [ ] context/WORKQUEUE.md updated (check off completed items)
- [ ] All code committed to git
- [ ] Session log written to logs/session-YYYY-MM-DD-NNN.md
