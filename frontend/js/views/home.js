/**
 * home.js — Home View
 * Renders the project cards grid with health banner.
 * Active projects shown in main grid, archived projects in collapsed section.
 * Auto-refreshes on SSE events.
 */

import { getProjects, getHealth, getAuthStatus, archiveProject, restoreProject, createProject, getSystemConfig, uploadBrief } from '../api.js';

let sseRefreshHandler = null;

function statusBadge(status) {
    const map = {
        active:      { cls: 'badge-active',      label: 'Active' },
        error:       { cls: 'badge-error',        label: 'Error' },
        'in-progress': { cls: 'badge-in-progress', label: 'In Progress' },
        'needs-input': { cls: 'badge-needs-input', label: 'Needs Input' },
        idle:        { cls: 'badge-idle',         label: 'Idle' },
        inactive:    { cls: 'badge-inactive',     label: 'Inactive' },
        running:     { cls: 'badge-running',       label: 'Running' },
        queued:      { cls: 'badge-queued',        label: 'Queued' },
        provisioning:{ cls: 'badge-provisioning',  label: 'Provisioning' },
    };
    const s = map[status] || { cls: 'badge-idle', label: status || 'Unknown' };
    return `<span class="status-badge ${s.cls}"><span class="dot"></span>${s.label}</span>`;
}

function projectCard(project, { archived = false } = {}) {
    const truncated = project.current_state
        ? (project.current_state.length > 120
            ? project.current_state.slice(0, 120) + '…'
            : project.current_state)
        : 'No state information.';

    const taskCount = project.active_tasks?.length || 0;
    const taskBadge = taskCount > 0
        ? `<span class="task-count">${taskCount} task${taskCount !== 1 ? 's' : ''}</span>`
        : '';

    const actionBtn = archived
        ? `<button class="archive-btn restore-btn" data-action="restore" data-id="${escapeAttr(project.id)}" title="Restore project">Restore</button>`
        : `<button class="archive-btn" data-action="archive" data-id="${escapeAttr(project.id)}" title="Archive project">Archive</button>`;

    return `
        <article class="card card-clickable project-card${archived ? ' project-card-archived' : ''}" data-id="${escapeAttr(project.id)}" role="button" tabindex="0" aria-label="Open ${escapeAttr(project.name)}">
            <div class="project-card-header">
                <span class="project-card-title">${escapeHtml(project.name)}</span>
                ${statusBadge(project.status)}
            </div>
            <p class="project-card-body">${escapeHtml(truncated)}</p>
            <div class="project-card-footer">
                <span class="last-updated">${escapeHtml(project.last_updated || '')}</span>
                <div class="project-card-actions">
                    ${taskBadge}
                    ${actionBtn}
                </div>
            </div>
        </article>`;
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
    return String(str).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function renderHealthBanner(container) {
    try {
        const health = await getHealth();
        const dot = `<span class="dot"></span>`;
        container.innerHTML = `
            <div class="health-banner">
                ${dot}
                <span>API <strong>online</strong> — v${escapeHtml(health.version || '?')}</span>
                <span class="text-muted" style="margin-left:auto;font-size:11px">${new Date(health.timestamp).toLocaleTimeString()}</span>
            </div>`;
    } catch {
        container.innerHTML = `
            <div class="health-banner error">
                <span class="dot"></span>
                <span>API <strong>unreachable</strong></span>
            </div>`;
    }
}

async function renderAuthIndicator(el) {
    try {
        const status = await getAuthStatus();
        if (!status.authenticated) {
            el.innerHTML = '';
            return;
        }
        if (status.method === 'tailscale') {
            el.textContent = 'Local access';
        } else {
            el.innerHTML = `${escapeHtml(status.user)} · <a href="/auth/logout" style="color:#94a3b8">Sign out</a>`;
        }
    } catch {
        // Silently ignore
    }
}

function renderNewProjectForm() {
    return `
    <div class="new-project-form" id="new-project-form">
        <h3 class="form-title">New project</h3>

        <div class="form-field">
            <label>Creation mode</label>
            <div class="mode-selector" id="np-mode-selector">
                <label class="mode-radio"><input type="radio" name="np-mode" value="existing-repo"> Existing repo</label>
                <label class="mode-radio"><input type="radio" name="np-mode" value="new-repo" checked> New repo</label>
                <label class="mode-radio"><input type="radio" name="np-mode" value="imported-repo"> Import repo</label>
                <label class="mode-radio"><input type="radio" name="np-mode" value="prompted-start"> From brief</label>
            </div>
        </div>

        <div class="form-fields" id="np-mode-fields"></div>

        <div class="form-actions">
            <button id="np-cancel" class="btn-secondary" type="button">Cancel</button>
            <button id="np-submit" class="btn-primary" type="button" disabled>
                Create project
            </button>
        </div>
        <p id="np-status" class="form-status"></p>
        <p id="np-ignore-warn" class="form-status" style="color:#ea580c"></p>
    </div>`;
}

const MODE_FIELDS = {
    'existing-repo': `
        <div class="form-field">
            <label>GitHub URL</label>
            <input type="text" id="np-github-url" placeholder="https://github.com/PaladinEng/repo-name" autocomplete="off">
        </div>
        <div class="form-field">
            <label>Display name (optional)</label>
            <input type="text" id="np-name" placeholder="Defaults to repo name" autocomplete="off">
        </div>
        <div class="form-field">
            <label>Description (optional)</label>
            <input type="text" id="np-desc" placeholder="One sentence description" autocomplete="off">
        </div>`,
    'new-repo': `
        <div class="form-field">
            <label>Project name / slug</label>
            <input type="text" id="np-name" placeholder="e.g. dark-sun-rag" autocomplete="off">
        </div>
        <div class="form-field">
            <label>Owner</label>
            <select id="np-owner"><option value="PaladinEng">PaladinEng</option><option value="personal">Personal</option></select>
        </div>
        <div class="form-field">
            <label>Brief (1-3 paragraphs)</label>
            <textarea id="np-brief" rows="3" placeholder="Describe the project..."></textarea>
        </div>
        <div class="form-field">
            <label><input type="checkbox" id="np-private" checked> Private repo</label>
        </div>`,
    'imported-repo': `
        <div class="form-field">
            <label>GitHub URL (upstream)</label>
            <input type="text" id="np-github-url" placeholder="https://github.com/org/repo" autocomplete="off">
        </div>
        <div class="form-field">
            <label>Display name (optional)</label>
            <input type="text" id="np-name" placeholder="Defaults to repo name" autocomplete="off">
        </div>
        <div class="form-field">
            <label>Brief / context (optional)</label>
            <textarea id="np-brief" rows="2" placeholder="Additional context for Claude..."></textarea>
        </div>`,
    'prompted-start': `
        <div class="form-field">
            <label>Project name / slug</label>
            <input type="text" id="np-name" placeholder="e.g. inventory-service" autocomplete="off">
        </div>
        <div class="form-field">
            <label>Owner</label>
            <select id="np-owner"><option value="PaladinEng">PaladinEng</option><option value="personal">Personal</option></select>
        </div>
        <div class="form-field">
            <label><input type="checkbox" id="np-private" checked> Private repo</label>
        </div>
        <div class="form-field">
            <label>Brief</label>
            <textarea id="np-brief" rows="4" placeholder="Describe what to build..."></textarea>
            <p class="form-hint">Or upload a file:</p>
            <input type="file" id="np-brief-file" accept=".md,.txt,.pdf">
            <span id="np-file-status" class="form-status"></span>
        </div>
        <div class="form-field">
            <label>Tech preferences (optional)</label>
            <input type="text" id="np-tech" placeholder="e.g. FastAPI, PostgreSQL, vanilla JS" autocomplete="off">
        </div>`,
};

let _ignoreDirectories = [];
let _briefFilePath = null;

function setupNewProjectForm() {
    const cancelBtn = document.getElementById('np-cancel');
    const submitBtn = document.getElementById('np-submit');
    const statusEl = document.getElementById('np-status');
    const ignoreWarn = document.getElementById('np-ignore-warn');
    const modeFields = document.getElementById('np-mode-fields');
    if (!cancelBtn || !submitBtn || !modeFields) return;

    _briefFilePath = null;

    // Load ignore list
    getSystemConfig().then(cfg => {
        _ignoreDirectories = cfg.ignore_directories || [];
    }).catch(() => { _ignoreDirectories = []; });

    function getMode() {
        const checked = document.querySelector('input[name="np-mode"]:checked');
        return checked ? checked.value : 'new-repo';
    }

    function renderModeFields() {
        const mode = getMode();
        modeFields.innerHTML = MODE_FIELDS[mode] || '';
        _briefFilePath = null;
        if (ignoreWarn) ignoreWarn.textContent = '';
        setupSlugValidation();
        setupBriefFileUpload();
        validate();
    }

    function getSlug() {
        const mode = getMode();
        if (mode === 'existing-repo' || mode === 'imported-repo') {
            const url = document.getElementById('np-github-url')?.value.trim() || '';
            let slug = url.replace(/\/$/, '').split('/').pop() || '';
            if (slug.endsWith('.git')) slug = slug.slice(0, -4);
            return slug.toLowerCase();
        }
        const name = document.getElementById('np-name')?.value.trim() || '';
        return name.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/^-+|-+$/g, '');
    }

    function setupSlugValidation() {
        const nameEl = document.getElementById('np-name');
        const urlEl = document.getElementById('np-github-url');
        const target = nameEl || urlEl;
        if (!target) return;
        target.addEventListener('blur', () => {
            const slug = getSlug();
            if (ignoreWarn) {
                if (slug && _ignoreDirectories.includes(slug)) {
                    ignoreWarn.textContent = `"${slug}" is in the ignore list and cannot be used.`;
                } else {
                    ignoreWarn.textContent = '';
                }
            }
            validate();
        });
        target.addEventListener('input', validate);
    }

    function setupBriefFileUpload() {
        const fileInput = document.getElementById('np-brief-file');
        const fileStatus = document.getElementById('np-file-status');
        if (!fileInput) return;

        fileInput.addEventListener('change', async () => {
            const file = fileInput.files[0];
            if (!file) return;
            if (fileStatus) fileStatus.textContent = 'Uploading...';
            try {
                const result = await uploadBrief(file);
                _briefFilePath = result.path;
                if (fileStatus) fileStatus.textContent = `Uploaded: ${result.filename}`;
                // Clear brief textarea since file replaces it
                const brief = document.getElementById('np-brief');
                if (brief) brief.value = '';
                validate();
            } catch (err) {
                if (fileStatus) fileStatus.textContent = `Error: ${err.message}`;
                _briefFilePath = null;
            }
        });
    }

    function validate() {
        const mode = getMode();
        const slug = getSlug();
        if (_ignoreDirectories.includes(slug)) { submitBtn.disabled = true; return; }

        let valid = false;
        if (mode === 'existing-repo') {
            const url = document.getElementById('np-github-url')?.value.trim();
            valid = !!url && url.startsWith('http');
        } else if (mode === 'new-repo') {
            const name = document.getElementById('np-name')?.value.trim();
            const brief = document.getElementById('np-brief')?.value.trim();
            valid = !!name && !!brief;
        } else if (mode === 'imported-repo') {
            const url = document.getElementById('np-github-url')?.value.trim();
            valid = !!url && url.startsWith('http');
        } else if (mode === 'prompted-start') {
            const name = document.getElementById('np-name')?.value.trim();
            const brief = document.getElementById('np-brief')?.value.trim();
            valid = !!name && (!!brief || !!_briefFilePath);
        }
        submitBtn.disabled = !valid;
    }

    // Wire mode radios
    document.querySelectorAll('input[name="np-mode"]').forEach(radio => {
        radio.addEventListener('change', renderModeFields);
    });

    // Initial render
    renderModeFields();

    cancelBtn.addEventListener('click', () => {
        document.getElementById('new-project-form')?.remove();
    });

    submitBtn.addEventListener('click', async () => {
        const mode = getMode();
        const slug = getSlug();

        // Final ignore list check
        if (_ignoreDirectories.includes(slug)) {
            if (statusEl) statusEl.textContent = `"${slug}" is in the ignore list.`;
            return;
        }

        const payload = { mode };
        payload.name = document.getElementById('np-name')?.value.trim() || slug;
        payload.owner = document.getElementById('np-owner')?.value || 'PaladinEng';
        payload.private = document.getElementById('np-private')?.checked ?? true;
        payload.brief = document.getElementById('np-brief')?.value.trim() || null;
        payload.brief_file_path = _briefFilePath || null;
        payload.github_url = document.getElementById('np-github-url')?.value.trim() || null;
        payload.description = document.getElementById('np-desc')?.value.trim() || null;
        payload.tech_preferences = document.getElementById('np-tech')?.value.trim() || null;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating...';
        if (statusEl) statusEl.textContent = '';

        try {
            const data = await createProject(payload);
            if (statusEl) statusEl.textContent = 'Project creation started';
            submitBtn.textContent = 'Created';
            // Navigate to the new project detail view
            setTimeout(() => {
                window.location.hash = `#/project/${encodeURIComponent(data.project_id)}`;
            }, 500);
        } catch (err) {
            if (statusEl) statusEl.textContent = `Error: ${err.message}`;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Create project';
        }
    });
}

export async function renderHome(content) {
    // Remove previous SSE listener if any
    if (sseRefreshHandler) {
        window.removeEventListener('sse:event', sseRefreshHandler);
        sseRefreshHandler = null;
    }

    content.innerHTML = `
        <div class="page-header">
            <div style="display:flex;align-items:center;gap:12px">
                <h2>Dashboard</h2>
                <button class="new-project-btn" id="new-project-btn" type="button">+ New project</button>
            </div>
            <p class="subtitle">All monitored projects</p>
            <span id="auth-indicator" class="text-muted" style="margin-left:auto;font-size:12px"></span>
        </div>
        <div id="new-project-slot"></div>
        <div id="health-banner-container"></div>
        <div id="projects-container">
            <div class="loading-container"><div class="spinner"></div></div>
        </div>`;

    // Wire up New Project button
    const npBtn = document.getElementById('new-project-btn');
    const npSlot = document.getElementById('new-project-slot');
    if (npBtn && npSlot) {
        npBtn.addEventListener('click', () => {
            if (document.getElementById('new-project-form')) return;
            npSlot.innerHTML = renderNewProjectForm();
            setupNewProjectForm();
            document.getElementById('np-name')?.focus();
        });
    }

    // Load health banner and auth indicator (async, non-blocking)
    renderHealthBanner(document.getElementById('health-banner-container'));
    renderAuthIndicator(document.getElementById('auth-indicator'));

    // Load projects
    await loadProjects();

    // Register SSE auto-refresh
    sseRefreshHandler = () => loadProjects();
    window.addEventListener('sse:event', sseRefreshHandler);
}

async function handleArchiveAction(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;

    e.stopPropagation();
    e.preventDefault();

    const action = btn.dataset.action;
    const id = btn.dataset.id;

    btn.disabled = true;
    btn.textContent = action === 'archive' ? 'Archiving...' : 'Restoring...';

    try {
        if (action === 'archive') {
            await archiveProject(id);
        } else {
            await restoreProject(id);
        }
        await loadProjects();
    } catch (err) {
        btn.disabled = false;
        btn.textContent = action === 'archive' ? 'Archive' : 'Restore';
        console.error(`Failed to ${action} project:`, err);
    }
}

async function loadProjects() {
    const container = document.getElementById('projects-container');
    if (!container) return;

    try {
        const projects = await getProjects();

        if (!projects || projects.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>No projects found</h3>
                    <p>No context directories detected in ~/projects/</p>
                </div>`;
            return;
        }

        const active = projects.filter(p => !p.archived);
        const archived = projects.filter(p => p.archived);

        let html = '';

        // Active projects grid
        if (active.length > 0) {
            html += `<div class="projects-grid">${active.map(p => projectCard(p)).join('')}</div>`;
        } else {
            html += `<div class="empty-state"><h3>No active projects</h3><p>All projects have been archived.</p></div>`;
        }

        // Archived projects section
        if (archived.length > 0) {
            html += `
                <div class="archived-section">
                    <div class="archived-header" id="archived-toggle">
                        <span>Archived projects (${archived.length})</span>
                        <svg class="collapsible-icon" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z"/>
                        </svg>
                    </div>
                    <div class="archived-body" id="archived-body" style="display:none">
                        <div class="projects-grid">${archived.map(p => projectCard(p, { archived: true })).join('')}</div>
                    </div>
                </div>`;
        }

        container.innerHTML = html;

        // Attach archive/restore button handlers
        container.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', handleArchiveAction);
        });

        // Attach archived section toggle
        const toggle = document.getElementById('archived-toggle');
        const body = document.getElementById('archived-body');
        if (toggle && body) {
            toggle.addEventListener('click', () => {
                const isOpen = body.style.display !== 'none';
                body.style.display = isOpen ? 'none' : 'block';
                toggle.classList.toggle('open', !isOpen);
            });
        }

        // Attach click handlers for navigation
        container.querySelectorAll('.project-card').forEach(card => {
            const handler = () => {
                window.location.hash = `#/project/${encodeURIComponent(card.dataset.id)}`;
            };
            card.addEventListener('click', handler);
            card.addEventListener('keydown', e => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handler();
                }
            });
        });
    } catch (err) {
        container.innerHTML = `
            <div class="error-banner">Failed to load projects: ${escapeHtml(err.message)}</div>`;
    }
}

export function cleanupHome() {
    if (sseRefreshHandler) {
        window.removeEventListener('sse:event', sseRefreshHandler);
        sseRefreshHandler = null;
    }
}
