/**
 * app.js — Main Application Entry Point
 * Hash-based routing, health check, SSE initialization.
 */

import { getHealth } from './api.js';
import { initSSE } from './sse.js';
import { renderHome, cleanupHome } from './views/home.js';
import { renderProject, cleanupProject } from './views/project.js';

const content = document.getElementById('content');

// ============================================================
// Routing
// ============================================================

function parseRoute(hash) {
    const h = hash || window.location.hash || '#/';

    // #/project/{id}
    const projectMatch = h.match(/^#\/project\/(.+)$/);
    if (projectMatch) {
        return { view: 'project', id: decodeURIComponent(projectMatch[1]) };
    }

    // #/ or empty
    return { view: 'home' };
}

function cleanupCurrentView() {
    cleanupHome();
    cleanupProject();
}

async function navigate(hash) {
    const route = parseRoute(hash);

    cleanupCurrentView();
    updateNavLinks(route);

    if (route.view === 'project') {
        await renderProject(content, route.id);
    } else {
        await renderHome(content);
    }
}

function updateNavLinks(route) {
    // Sidebar nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.view === route.view);
    });
    // Bottom nav links
    document.querySelectorAll('.bottom-nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.view === route.view);
    });
}

// ============================================================
// Init
// ============================================================

async function initHealthCheck() {
    const versionEl = document.getElementById('api-version');
    try {
        const health = await getHealth();
        if (versionEl) versionEl.textContent = `v${health.version || '?'}`;
    } catch {
        if (versionEl) versionEl.textContent = 'offline';
    }
}

async function init() {
    // Fire health check and SSE in parallel
    initHealthCheck();
    initSSE();

    // Initial route
    await navigate(window.location.hash);

    // Handle browser navigation
    window.addEventListener('hashchange', (e) => {
        const newHash = new URL(e.newURL).hash;
        navigate(newHash);
    });
}

init();
