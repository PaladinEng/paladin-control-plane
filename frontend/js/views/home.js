/**
 * home.js — Home View
 * Renders the project cards grid with health banner.
 * Active projects shown in main grid, archived projects in collapsed section.
 * Auto-refreshes on SSE events.
 */

import { getProjects, getHealth, getAuthStatus, archiveProject, restoreProject, createProject } from '../api.js';

let sseRefreshHandler = null;

function statusBadge(status) {
    const map = {
        active:      { cls: 'badge-active',      label: 'Active' },
        error:       { cls: 'badge-error',        label: 'Error' },
        'in-progress': { cls: 'badge-in-progress', label: 'In Progress' },
        'needs-input': { cls: 'badge-needs-input', label: 'Needs Input' },
        idle:        { cls: 'badge-idle',         label: 'Idle' },
        inactive:    { cls: 'badge-inactive',     label: 'Inactive' },
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
        <div class="form-fields">
            <div class="form-field">
                <label>Display name</label>
                <input type="text" id="np-name"
                       placeholder="e.g. Dark Sun RAG"
                       autocomplete="off">
            </div>
            <div class="form-field">
                <label>GitHub repo</label>
                <input type="text" id="np-repo"
                       placeholder="PaladinEng/repo-name"
                       autocomplete="off">
            </div>
            <div class="form-field">
                <label>Description</label>
                <input type="text" id="np-desc"
                       placeholder="One sentence description"
                       autocomplete="off">
            </div>
        </div>
        <div class="form-actions">
            <button id="np-cancel" class="btn-secondary" type="button">Cancel</button>
            <button id="np-submit" class="btn-primary" type="button" disabled>
                Create project
            </button>
        </div>
        <p id="np-status" class="form-status"></p>
    </div>`;
}

function setupNewProjectForm() {
    const cancelBtn = document.getElementById('np-cancel');
    const submitBtn = document.getElementById('np-submit');
    const nameInput = document.getElementById('np-name');
    const repoInput = document.getElementById('np-repo');
    const descInput = document.getElementById('np-desc');
    const statusEl = document.getElementById('np-status');
    if (!cancelBtn || !submitBtn) return;

    function validate() {
        const name = nameInput?.value.trim();
        const repo = repoInput?.value.trim();
        const desc = descInput?.value.trim();
        const repoValid = /^PaladinEng\/[a-zA-Z0-9][a-zA-Z0-9\-]*$/.test(repo);
        submitBtn.disabled = !(name && repoValid && desc);
    }

    [nameInput, repoInput, descInput].forEach(el =>
        el?.addEventListener('input', validate)
    );

    cancelBtn.addEventListener('click', () => {
        document.getElementById('new-project-form')?.remove();
    });

    submitBtn.addEventListener('click', async () => {
        const name = nameInput.value.trim();
        const repo = repoInput.value.trim();
        const description = descInput.value.trim();

        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating...';
        if (statusEl) statusEl.textContent = '';

        try {
            const data = await createProject(name, repo, description);
            if (statusEl) statusEl.textContent = `\u2713 ${data.message}`;
            submitBtn.textContent = 'Created';
            setTimeout(() =>
                document.getElementById('new-project-form')?.remove(), 3000
            );
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
