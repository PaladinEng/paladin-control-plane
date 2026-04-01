/**
 * home.js — Home View
 * Renders the project cards grid with health banner.
 * Auto-refreshes on SSE events.
 */

import { getProjects, getHealth, getAuthStatus } from '../api.js';

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

function projectCard(project) {
    const truncated = project.current_state
        ? (project.current_state.length > 120
            ? project.current_state.slice(0, 120) + '…'
            : project.current_state)
        : 'No state information.';

    const taskCount = project.active_tasks?.length || 0;
    const taskBadge = taskCount > 0
        ? `<span class="task-count">${taskCount} task${taskCount !== 1 ? 's' : ''}</span>`
        : '';

    return `
        <article class="card card-clickable project-card" data-id="${escapeAttr(project.id)}" role="button" tabindex="0" aria-label="Open ${escapeAttr(project.name)}">
            <div class="project-card-header">
                <span class="project-card-title">${escapeHtml(project.name)}</span>
                ${statusBadge(project.status)}
            </div>
            <p class="project-card-body">${escapeHtml(truncated)}</p>
            <div class="project-card-footer">
                <span class="last-updated">${escapeHtml(project.last_updated || '')}</span>
                ${taskBadge}
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

export async function renderHome(content) {
    // Remove previous SSE listener if any
    if (sseRefreshHandler) {
        window.removeEventListener('sse:event', sseRefreshHandler);
        sseRefreshHandler = null;
    }

    content.innerHTML = `
        <div class="page-header">
            <h2>Dashboard</h2>
            <p class="subtitle">All monitored projects</p>
            <span id="auth-indicator" class="text-muted" style="margin-left:auto;font-size:12px"></span>
        </div>
        <div id="health-banner-container"></div>
        <div id="projects-container">
            <div class="loading-container"><div class="spinner"></div></div>
        </div>`;

    // Load health banner and auth indicator (async, non-blocking)
    renderHealthBanner(document.getElementById('health-banner-container'));
    renderAuthIndicator(document.getElementById('auth-indicator'));

    // Load projects
    await loadProjects();

    // Register SSE auto-refresh
    sseRefreshHandler = () => loadProjects();
    window.addEventListener('sse:event', sseRefreshHandler);
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

        container.innerHTML = `<div class="projects-grid">${projects.map(projectCard).join('')}</div>`;

        // Attach click handlers
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
