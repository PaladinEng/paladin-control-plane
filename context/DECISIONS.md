# DECISIONS — Paladin Control Plane

## Decision 1: Vanilla JS frontend, no build tools
Date: 2026-03-30
Options considered:
- Option A: React/Vue/Svelte — component model, build step required, npm dependency tree
- Option B: Vanilla JS/HTML/CSS — no build tools, zero dependencies, direct browser execution
Decision: Vanilla JS/HTML/CSS
Rationale: This is a single-user operational dashboard, not a consumer product. Build toolchains add complexity with no benefit at this scale. Vanilla JS with ES modules provides clean separation without npm. Mobile responsiveness via CSS media queries is sufficient.
Consequences: No JSX, no component library, no hot module reload. JS modules loaded directly via `<script type="module">`. CSS is hand-written. This keeps the project zero-dependency on the frontend.

## Decision 2: FastAPI backend serving static files
Date: 2026-03-30
Options considered:
- Option A: Separate nginx for static + FastAPI for API — two services to manage
- Option B: FastAPI serves both static files and API — single service, single port
Decision: FastAPI serves everything on port 8080
Rationale: Single systemd service simplifies deployment and monitoring. FastAPI's StaticFiles mount handles static serving efficiently for a single-user dashboard. No need for nginx reverse proxy complexity.
Consequences: All traffic goes through FastAPI. Static file performance is adequate for single-user. If load ever matters, nginx can be added in front later.

## Decision 3: Systemd user services, not containers
Date: 2026-03-30
Options considered:
- Option A: Deploy as k8s pods on the cluster — complex for a management tool that manages the cluster
- Option B: Docker containers on UM790 — extra layer, docker dependency
- Option C: Systemd user services — simple, native, no container runtime needed
Decision: Systemd user services (loginctl enable-linger)
Rationale: The control plane monitors the k8s cluster — it should not run inside it. Systemd user services are the simplest deployment model for a single-host Python application. User services persist across logout via linger. journalctl provides native log management.
Consequences: Services run as paladinrobotics user. Requires `loginctl enable-linger paladinrobotics`. No container isolation — acceptable for a trusted single-user system.

## Decision 4: File-based project state, no database
Date: 2026-03-30
Options considered:
- Option A: SQLite database for project state — structured queries, migrations needed
- Option B: Read directly from ~/projects/*/context/ markdown files — zero setup, single source of truth
Decision: Read from context/ directories
Rationale: Project state already exists in context/STATUS.md and context/WORKQUEUE.md files maintained by Claude Code agents. Duplicating this into a database creates a sync problem. Reading markdown files directly ensures the dashboard always reflects the true agent-maintained state.
Consequences: No complex queries. Parsing markdown is the data access layer. Performance is fine for <20 projects. If structured queries become necessary, can add SQLite as a cache layer later.

## Decision 5: ntfy for all notifications
Date: 2026-03-30
Options considered:
- Option A: Email notifications — requires SMTP setup, slow delivery
- Option B: Slack/Discord webhook — external dependency, account required
- Option C: ntfy — self-hosted, iOS/Android apps, instant push, Tailscale-accessible
Decision: ntfy self-hosted on UM790
Rationale: Self-hosted means no external dependencies. ntfy iOS app supports instant push notifications. Accessible via Tailscale from anywhere. Claude Code hooks can POST directly to ntfy topics. Deep links can point back to the dashboard for needs-input scenarios.
Consequences: Requires ntfy server running as systemd service. iOS app must be configured with Tailscale-accessible server URL. No notification history beyond ntfy's built-in cache.

## Decision 6: Blocker types grow organically via patterns library
Date: 2026-04-04
Options considered:
- Option A: Hardcoded blocker type enum — requires code change to add new types
- Option B: Organic growth via patterns library — new types auto-created on first occurrence
Decision: Organic growth via patterns library at ~/projects/paladin-context-system/patterns/
Rationale: Hardcoding blocker types creates friction when new failure modes are discovered. The patterns library allows the system to learn and adapt without code changes. Each new blocker type is recorded as a structured pattern entry on first occurrence, building institutional knowledge over time.
Consequences: No central enum to validate against. Pattern files are the source of truth. 12 initial types seeded; new types emerge as the system encounters novel failures.

## Decision 7: Resolution triggers CLAUDE.md Known Issues updates
Date: 2026-04-04
Options considered:
- Option A: Manual CLAUDE.md updates — operators must remember to document fixes
- Option B: Auto-update Known Issues on resolution — future sessions have autonomous fix knowledge
Decision: Auto-update Known Issues sections in affected project CLAUDE.md files on blocker resolution
Rationale: When a blocker is resolved, the fix knowledge should be immediately available to future autonomous sessions. Embedding this in CLAUDE.md ensures every session starts with awareness of known issues and their resolutions, preventing re-discovery of solved problems.
Consequences: CLAUDE.md files grow over time with Known Issues entries. Periodic pruning may be needed for resolved-and-no-longer-relevant issues.

## Decision 8: Queue evaluator skips parked prompts, continues other work
Date: 2026-04-04
Options considered:
- Option A: Stall entire queue when any prompt is blocked — simple but wasteful
- Option B: Skip parked prompts and continue other projects' work — maximizes throughput
Decision: Skip parked prompts, continue processing other projects
Rationale: A blocker in one project should not prevent progress in unrelated projects. The queue evaluator marks blocked prompts as `parked` and moves on, returning to them when the blocker resolves. This maximizes overnight and autonomous execution throughput.
Consequences: Queue ordering becomes slightly more complex. Parked prompts need periodic re-evaluation. The AERS-013 backlog item will add parallel execution with full blocker isolation.
