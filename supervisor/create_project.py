"""
create_project.py — Generates the full Claude Code task prompt for project creation.

Called by the backend POST /api/projects/create endpoint to produce the task.md
content that the CPO queue runner feeds to Claude Code.

Reads .paladin-config.yaml at generation time so the self-validation checklist
matches the live compliance schema — not hardcoded.
"""

import json
from pathlib import Path
from textwrap import dedent

import yaml

PALADIN_CONFIG_PATH = Path.home() / "projects" / ".paladin-config.yaml"


def _load_config() -> dict:
    """Read .paladin-config.yaml. Falls back to hardcoded defaults if missing."""
    if PALADIN_CONFIG_PATH.exists():
        try:
            return yaml.safe_load(PALADIN_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    # Hardcoded fallback — log warning in prompt
    return {
        "_fallback": True,
        "ignore_directories": ["ChatGPT-History", "scratch", "chatgpt-to-claude-migration"],
        "compliance": {
            "required_files": [
                "context/AGENTS.md", "context/STATUS.md", "context/WORKQUEUE.md",
                "context/DECISIONS.md", "context/meta.yaml", "CLAUDE.md",
            ],
            "meta_required_fields": ["id", "name", "repo", "entity", "priority", "status"],
        },
    }


def _pre_flight_section(payload: dict, config: dict) -> str:
    ignore_list = config.get("ignore_directories", [])
    ignore_str = ", ".join(f'"{d}"' for d in ignore_list)
    slug = payload["slug"]
    mode = payload["mode"]

    config_warning = ""
    if config.get("_fallback"):
        config_warning = (
            "\nWARNING: .paladin-config.yaml was not found at ~/projects/.paladin-config.yaml. "
            "Using hardcoded fallback ignore list. Log this warning.\n"
        )

    github_dedupe = ""
    if mode in ("new-repo", "prompted-start"):
        owner = payload.get("owner", "PaladinEng")
        github_dedupe = f"""
6. GitHub dedupe: run `gh repo view {owner}/{slug}`. If repo exists, emit needs-input and halt.
"""
    else:
        github_dedupe = """
6. GitHub dedupe: SKIP (repo expected to exist for this mode).
"""

    local_dedupe = ""
    if mode == "existing-repo":
        github_url = payload.get("github_url", "")
        local_dedupe = f"""4. Local directory check: if ~/projects/{slug}/ exists:
   a. Run `cd ~/projects/{slug} && git remote get-url origin` to get the current remote URL.
   b. If the remote URL matches "{github_url}" — this is the expected repo. Log "Local clone found with matching remote — will reuse." and CONTINUE (do not halt).
   c. If the remote URL does NOT match — emit needs-input via POST http://localhost:8080/api/projects/{slug}/needs-input
      with {{"question": "Directory ~/projects/{slug}/ exists but its remote URL does not match {github_url}. Found: <actual_url>. Please resolve the conflict.", "task_id": "{payload['task_id']}"}}
      and HALT.
   d. If ~/projects/{slug}/ does not exist — continue to step 5 (clone will happen in execution)."""
    else:
        local_dedupe = f"""4. Local dedupe: check if ~/projects/{slug}/ exists. If found, emit needs-input and halt."""

    return f"""{config_warning}
## Pre-flight Checks (MANDATORY — execute in order, halt on first failure)

1. Parse creation payload (provided below).
2. Read ~/projects/.paladin-config.yaml — extract ignore_directories list.
   If file missing, use this fallback list and log warning: [{ignore_str}]
3. Ignore list check: if target slug "{slug}" matches any entry in ignore_directories,
   emit needs-input via POST http://localhost:8080/api/projects/{slug}/needs-input
   with {{"question": "Slug '{slug}' is in the ignore list", "task_id": "{payload['task_id']}"}}
   and HALT. Do not create any files.
{local_dedupe}
5. Runtime dedupe: check ~/paladin-control/data/projects/ for meta.json with matching id or github_url.
   If found, emit needs-input and halt.
{github_dedupe}
After all checks pass, emit SSE progress:
  curl -s -X POST http://localhost:8080/api/events -H 'Content-Type: application/json' \\
    -d '{{"type": "thread_update", "project_id": "{slug}", "message": "Pre-flight checks passed — beginning creation"}}'
"""


def _intake_pass_section(slug: str) -> str:
    """Generate the intake pass instructions for existing-repo and imported-repo modes.

    Scans the project root for existing context files, documentation, and config
    files before generating any context files — enriching the output with everything
    learned from the project.
    """
    return f"""### Intake Pass — Run BEFORE any context file generation

Scan ~/projects/{slug}/ and collect information from the following sources.
All information gathered here informs the context files generated in later steps.

#### 1. Context System Files

Scan the project root for these files and handle as specified:

| File(s) at root | Action |
|-----------------|--------|
| CONTEXT.md, DEV_GUIDE.md, MERGE_NOTES.md, CONTENT_REPLACE_CONFLICTS.md | If context/CONTEXT.md does NOT exist: synthesize a single CONTEXT.md from all of these combined. If context/CONTEXT.md already exists: read these files and append any non-redundant information to context/CONTEXT.md. |
| AGENTS.md | If context/AGENTS.md does NOT exist: copy to context/. If it exists: read and merge non-redundant content. |
| DECISIONS.md | If context/DECISIONS.md does NOT exist: copy to context/. If it exists: read and merge non-redundant content. |
| STATUS.md | If context/STATUS.md does NOT exist: copy to context/. If it exists: read and merge non-redundant content. |
| WORKQUEUE.md | If context/WORKQUEUE.md does NOT exist: copy to context/. If it exists: read and merge non-redundant content. |
| meta.yaml | If context/meta.yaml does NOT exist: read and migrate — update field names to match supervisor schema (id, name, repo, entity, priority, status). If context/meta.yaml exists: skip. |
| CLAUDE.md, codex.md | Read as additional context to inform generation. Do NOT copy — CLAUDE.md will be generated fresh at project root per spec. |

#### 2. Project Documentation

Read these files if present and use their content to enrich context/CONTEXT.md:

- **README.md** — primary source for project overview, goals, architecture
- Any other .md files at the project root not already covered above (e.g. CONTRIBUTING.md, CHANGELOG.md, LICENSE.md)

#### 3. Project Config Files

Read these files if present to infer tech stack, architecture, and operational commands:

- **package.json** — dependencies, scripts (build/test/lint/dev commands), project name
- **pnpm-workspace.yaml / pnpm-lock.yaml** — monorepo structure, workspace packages
- **tsconfig.base.json / tsconfig.json** — TypeScript configuration
- **pyproject.toml / setup.py / setup.cfg** — Python project metadata
- **requirements.txt / Pipfile** — Python dependencies
- **Cargo.toml** — Rust project
- **go.mod** — Go module
- **Makefile** — build targets
- **Dockerfile / docker-compose.yml** — container config
- **Any other config files at root** (.eslintrc, .prettierrc, nx.json, turbo.json, etc.)

Record the following from config files for use in context generation:
- **Tech stack**: languages, frameworks, key dependencies
- **Validation commands**: build, test, lint, format commands from package.json scripts / Makefile targets / pyproject.toml scripts
- **Monorepo structure**: workspace packages and their purposes
- **Key directories**: src/, lib/, apps/, packages/, etc. and their roles

#### 4. Root CONTEXT.md Copy

After processing all files above, check for a root-level CONTEXT.md:

- If ~/projects/{slug}/CONTEXT.md exists AND ~/projects/{slug}/context/CONTEXT.md does NOT exist:
  copy ~/projects/{slug}/CONTEXT.md to ~/projects/{slug}/context/CONTEXT.md
- If ~/projects/{slug}/context/CONTEXT.md already exists: skip — do not overwrite.

This step runs unconditionally during intake, regardless of which decision tree case (A, B, or C) applies.

After the intake pass, proceed to the context file decision tree using the enriched understanding.
"""


def _mode_steps(payload: dict) -> str:
    mode = payload["mode"]
    slug = payload["slug"]
    owner = payload.get("owner", "PaladinEng")
    private_flag = "--private" if payload.get("private", True) else "--public"
    github_url = payload.get("github_url", "")
    brief = payload.get("brief", "") or ""
    brief_file = payload.get("brief_file_path", "")
    tech_prefs = payload.get("tech_preferences", "") or ""

    if mode == "existing-repo":
        compliance = _load_config().get("compliance", {})
        required_files = compliance.get("required_files", [])
        required_files_str = ", ".join(f'`{f}`' for f in required_files)

        intake = _intake_pass_section(slug)

        return f"""## Mode: existing-repo

### Step 1 — Determine local state

Check whether ~/projects/{slug}/ already exists (it may have been confirmed in pre-flight).

**If ~/projects/{slug}/ does NOT exist:**
- Clone: `git clone {github_url} ~/projects/{slug}`
- Then proceed to Step 1b.

**If ~/projects/{slug}/ DOES exist (local clone confirmed in pre-flight):**
- Do NOT clone — the repo is already present.
- Proceed to Step 1b.

### Step 1b — Intake Pass

{intake}

### Step 2 — Context file decision tree

The required compliance files are: {required_files_str}

**Case A — context/ exists and ALL required files are present and non-empty:**
- Skip context generation entirely.
- Log: "Existing compliant project — registering with dashboard only."
- Proceed directly to Step 3 (self-validate and register).

**Case B — context/ exists but some required files are missing or empty:**
- Do NOT regenerate files that already exist and are non-empty.
- Read README and any docs/ — build understanding of project purpose.
- Generate ONLY the missing or empty files (see Context File Standards below).
- Log which files were generated and which were skipped.
- Commit only the newly generated files:
  ```
  cd ~/projects/{slug}
  git add context/ CLAUDE.md
  git commit -m 'chore: add missing paladin context files'
  git push
  ```

**Case C — context/ directory does not exist:**
- Read README and any docs/ — build understanding of project purpose.
- Generate all context files (see Context File Standards below).
- Commit context files:
  ```
  cd ~/projects/{slug}
  git add context/ CLAUDE.md
  git commit -m 'chore: add paladin context files'
  git push
  ```

### Step 3 — Validate and register

1. Self-validate against compliance checklist (see Self-Validation below).
2. Register (see Registration Contract below).
3. Call provisioning-complete: `curl -s -X POST http://localhost:8080/api/projects/{slug}/provisioning-complete`
4. Print FINISHED WORK
"""

    elif mode == "new-repo":
        return f"""## Mode: new-repo

1. Create GitHub repo: `gh repo create {owner}/{slug} {private_flag} --description '{brief[:72]}'`
2. Clone: `git clone git@github.com:{owner}/{slug}.git ~/projects/{slug}`
3. Scaffold: README.md, .gitignore, basic directory structure implied by brief.
4. Generate context files (see Context File Standards below).
5. Self-validate against compliance checklist.
6. Initial commit and push (scaffold + context files together):
   ```
   cd ~/projects/{slug}
   git add -A
   git commit -m 'chore: initial project scaffold with paladin context'
   git push
   ```
7. Register (see Registration Contract below).
8. Call provisioning-complete: `curl -s -X POST http://localhost:8080/api/projects/{slug}/provisioning-complete`
9. Print FINISHED WORK
"""

    elif mode == "imported-repo":
        fork_note = ""
        if payload.get("fork", False):
            fork_note = f"\n1a. Fork: `gh repo fork {github_url} --org PaladinEng --clone=false`"
        intake = _intake_pass_section(slug)

        return f"""## Mode: imported-repo

1. Clone: `git clone {github_url} ~/projects/{slug}`{fork_note}

### Step 1b — Intake Pass

{intake}

2. Apply the context file decision tree (Cases A/B/C from existing-repo logic) using enriched understanding from the intake pass.
   - If context/ exists with all required compliance files: skip generation, register only.
   - If context/ exists with gaps: generate only missing files, enriched by intake data.
   - If no context/: generate all context files reflecting actual codebase architecture.
3. Self-validate against compliance checklist.
4. Commit context files (skip if no fork — read-only import):
   ```
   cd ~/projects/{slug}
   git add context/ CLAUDE.md
   git commit -m 'chore: add paladin context files'
   git push
   ```
5. Register (see Registration Contract below).
6. Call provisioning-complete: `curl -s -X POST http://localhost:8080/api/projects/{slug}/provisioning-complete`
7. Print FINISHED WORK
"""

    elif mode == "prompted-start":
        brief_section = ""
        if brief_file:
            brief_section = f"\nRead the brief from file: {brief_file}"
        elif brief:
            brief_section = f"\nProject brief:\n{brief}"
        tech_section = f"\nTech preferences: {tech_prefs}" if tech_prefs else ""

        return f"""## Mode: prompted-start
{brief_section}{tech_section}

1. Create GitHub repo: `gh repo create {owner}/{slug} {private_flag} --description '{(brief or "")[:72]}'`
2. Clone: `git clone git@github.com:{owner}/{slug}.git ~/projects/{slug}`
3. Read the brief. Make all architecture decisions from brief alone — no clarifying questions.
   If an ambiguity cannot be reasonably resolved, emit needs-input BEFORE starting scaffold.
4. Write ARCHITECTURE.md to ~/projects/{slug}/docs/ before writing any code.
5. Scaffold full codebase per brief and architecture decisions.
6. Generate context files reflecting the scaffolded architecture.
7. Self-validate against compliance checklist.
8. Initial commit and push:
   ```
   cd ~/projects/{slug}
   git add -A
   git commit -m 'chore: initial scaffold from brief with paladin context'
   git push
   ```
9. Register (see Registration Contract below).
10. Call provisioning-complete: `curl -s -X POST http://localhost:8080/api/projects/{slug}/provisioning-complete`
11. Print FINISHED WORK
"""
    return ""


def _self_validation_section(config: dict, slug: str) -> str:
    compliance = config.get("compliance", {})
    required_files = compliance.get("required_files", [])
    meta_fields = compliance.get("meta_required_fields", [])

    file_checks = "\n".join(
        f"  - [ ] {f} exists at ~/projects/{slug}/{f} and is non-empty"
        for f in required_files
    )
    field_checks = "\n".join(
        f"  - [ ] {f} is present and non-empty in context/meta.yaml"
        for f in meta_fields
    )

    return f"""## Self-Validation Checklist (MANDATORY before calling provisioning-complete)

Run through EVERY check. If any fails, attempt to fix. If fix fails, emit needs-input.

Required files:
{file_checks}

CLAUDE.md placement:
  - [ ] CLAUDE.md is at ~/projects/{slug}/CLAUDE.md (ROOT, not in context/)

meta.yaml required fields:
{field_checks}

Dashboard registration:
  - [ ] ~/paladin-control/data/projects/{slug}/meta.json exists and is valid JSON
"""


def _registration_section(payload: dict) -> str:
    slug = payload["slug"]
    mode = payload["mode"]
    owner = payload.get("owner", "PaladinEng")
    github_url = payload.get("github_url", f"https://github.com/{owner}/{slug}")

    return f"""## Registration Contract

After self-validation passes, update the runtime registration:

1. Update ~/paladin-control/data/projects/{slug}/meta.json:
   ```json
   {{
     "id": "{slug}",
     "name": "{payload['name']}",
     "mode": "{mode}",
     "github_url": "{github_url}",
     "local_path": "~/projects/{slug}",
     "created_at": "{payload.get('created_at', '')}",
     "status": "provisioning"
   }}
   ```
   (Note: provisioning-complete endpoint will set status to idle)

2. Ensure thread.jsonl and prompt-queue.json exist (they should from API creation step).

project_scanner.py picks up meta.json on next 30s poll — no restart needed.
"""


def _context_file_standards(payload: dict) -> str:
    slug = payload["slug"]
    mode = payload["mode"]
    owner = payload.get("owner", "PaladinEng")
    name = payload["name"]
    brief = payload.get("brief", "") or payload.get("description", "") or ""
    today = payload.get("created_at", "")[:10] or "today"

    return f"""## Context File Content Standards

### File Placement (NON-NEGOTIABLE)
- CLAUDE.md → ~/projects/{slug}/CLAUDE.md (ROOT — NOT in context/)
- All other context files → ~/projects/{slug}/context/
- NEVER place context files at project root (this causes structural-gap compliance failure)

### meta.yaml — Required Fields
```yaml
id: {slug}
name: {name}
repo: {owner}/{slug}
entity: paladin-robotics
priority: P2
status: active
```

### CLAUDE.md — Minimum Content
- Project name and one-sentence purpose
- Local path: ~/projects/{slug}
- GitHub repo URL: https://github.com/{owner}/{slug}
- Standard session start: cd to project, read STATUS.md and WORKQUEUE.md
- Session end: update STATUS.md, commit, print FINISHED WORK
- **From intake pass (if available):**
  - Validation commands (e.g. `npm test`, `make lint`, `pytest`) inferred from package.json scripts, Makefile targets, or pyproject.toml
  - Monorepo structure notes if pnpm-workspace.yaml or similar was found
  - Key directories and their purposes from the file tree scan
  - Tech stack summary (languages, frameworks, key dependencies)
  - Any operational notes from existing CLAUDE.md or codex.md that should carry forward
- **Paladin Orchestration section** — add this section after the project identity/purpose section:
  ```markdown

  ## Paladin Orchestration

  This project is managed by the Paladin Control Plane (PCP).
  Dashboard: https://dashboard.paladinrobotics.com

  ### Execution conventions
  - Print FINISHED WORK as your absolute last action — after all commits
  - Commit at each logical checkpoint during a task, not at the end
  - Use conventional commit format: type(scope): description [ckpt N]
  - Write blocker.json to the active task directory if you cannot proceed
  - Read context/AGENTS.md and context/STATUS.md at every session start
  - Update context/STATUS.md and context/WORKQUEUE.md before exiting

  ### Blocker reporting
  If blocked, write ~/dev/queue/active/{{task_name}}/blocker.json:
    type: one of github-auth, api-down, missing-credential, path-issue,
          git-conflict, disk-full, service-crash, network-unreachable,
          missing-dependency, permission-denied, trust-prompt, unknown
    description: one sentence — what failed and why
    fix_instructions: exact steps to resolve
    resumable: true
    checkpoint_commit: last commit hash before blocker, or null
    completed_steps: list of steps already done
    remaining_steps: list of steps still to do
  Then print FINISHED WORK and exit cleanly.

  ### Context schema
  paladin-context-system v1.0
  Schema reference: ~/projects/paladin-context-system/SCHEMA.md
  Patterns library: ~/projects/paladin-context-system/patterns/

  ### Known Issues
  <!-- Auto-updated by AERS on blocker resolution. Do not remove. -->
  _No known issues at this time._
  ```

- **Known Issues and Resolutions section** — add this scaffold at the end of every generated CLAUDE.md:
  ```markdown

  ## Known Issues and Resolutions

  <!-- Entries are added automatically by the supervisor when blockers are resolved. -->
  ```

### STATUS.md — Initial Content
- Phase 0 — Project created via PCP on {today}
- Creation mode: {mode}
- GitHub repo URL
- No active work yet

### WORKQUEUE.md — Initial Content
- P1: Initial working session — read CONTEXT.md and define first sprint
- P2, P3 sections present but empty

### DECISIONS.md — Initial Content
- Decision #1: Project created via PCP {mode} mode on {today}

### AGENTS.md — Initial Content
- Project purpose (from brief or codebase reading)
- Key paths and commands
- Link to context/ files

### CONTEXT.md (best practice, not enforced)
- Architecture overview
- Tech stack (inferred from config files during intake)
- Key components and directory structure
- **From intake pass (if available):**
  - Content synthesized from CONTEXT.md, DEV_GUIDE.md, MERGE_NOTES.md found at root
  - Architecture details from README.md
  - Dependency summary from package.json / pyproject.toml / Cargo.toml / go.mod
  - Monorepo workspace layout from pnpm-workspace.yaml / nx.json / turbo.json
"""


def _checkpoint_section(payload: dict) -> str:
    task_id = payload["task_id"]
    return f"""## Checkpoint Model

Write checkpoints to ~/dev/queue/active/{task_id}/checkpoints.json as you complete steps.
Each step appends its name and UTC timestamp. On re-run, read this file and skip completed steps.

Format:
```json
[
  {{"step": "pre-flight", "completed_at": "2026-04-02T18:00:00Z"}},
  {{"step": "clone", "completed_at": "2026-04-02T18:01:00Z"}}
]
```
"""


def _error_recovery_section(payload: dict) -> str:
    slug = payload["slug"]
    task_id = payload["task_id"]
    return f"""## Error Recovery

If any step fails:
1. Log the failure to the checkpoint file
2. Attempt recovery per the step type:
   - Pre-flight failure: halt, needs-input (nothing written yet)
   - GitHub repo created but clone failed: retry; if retry fails, delete repo and needs-input
   - Clone done but scaffold failed: retry from checkpoint
   - Self-validation failed: attempt to regenerate the missing file
   - Push failed: retry git push
   - Registration failed: retry meta.json write
3. If recovery fails, emit needs-input with:
   - failed_step
   - error_detail
   - completed_steps
   - resume_instruction

Needs-input endpoint:
  POST http://localhost:8080/api/projects/{slug}/needs-input
  Body: {{"question": "<describe what failed and what to do>", "task_id": "{task_id}"}}
"""


def generate_creation_prompt(payload: dict) -> str:
    """Generate the full task.md content for a project creation CPO task."""
    config = _load_config()
    slug = payload["slug"]
    mode = payload["mode"]

    header = f"""# Project Creation Task — {slug}

Mode: {mode}
Task ID: {payload['task_id']}
Created: {payload.get('created_at', '')}

## Creation Payload
```json
{json.dumps(payload, indent=2)}
```
"""

    sections = [
        header,
        _pre_flight_section(payload, config),
        _mode_steps(payload),
        _context_file_standards(payload),
        _self_validation_section(config, slug),
        _registration_section(payload),
        _checkpoint_section(payload),
        _error_recovery_section(payload),
    ]

    footer = f"""
## Final Instructions

- Do NOT ask clarifying questions — make decisions and document them in DECISIONS.md
- Complete ALL steps including self-validation before calling provisioning-complete
- The dashboard is watching for SSE events — emit progress updates via POST /api/events
- Print FINISHED WORK as your final output line
- Exit cleanly after printing FINISHED WORK — do not wait for further input

## Exit Instruction
When all work is complete:
1. Call provisioning-complete endpoint
2. Print FINISHED WORK
3. Exit immediately
"""

    return "\n".join(sections) + footer
