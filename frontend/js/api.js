/**
 * api.js — API Client for Paladin Control Plane
 * Thin fetch wrapper for all backend endpoints.
 */

const API_BASE = '';  // same origin

export async function getHealth() {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json();
}

export async function getProjects() {
    const res = await fetch(`${API_BASE}/api/projects`);
    if (!res.ok) throw new Error(`Failed to load projects: ${res.status}`);
    return res.json();
}

export async function getProject(id) {
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error(`Project ${id} not found`);
    return res.json();
}

export async function getThread(projectId) {
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(projectId)}/thread`);
    if (!res.ok) throw new Error(`Failed to load thread: ${res.status}`);
    return res.json();
}

export async function postResponse(projectId, content) {
    const res = await fetch(
        `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/respond`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        }
    );
    if (!res.ok) throw new Error(`Failed to submit response: ${res.status}`);
    return res.json();
}

export async function getAuthStatus() {
    const res = await fetch(`${API_BASE}/auth/status`);
    if (!res.ok) return { authenticated: false };
    return res.json();
}

export async function postPrompt(projectId, content) {
    const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(projectId)}/prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
    });
    if (!res.ok) throw new Error(`Failed to send prompt: ${res.status}`);
    return res.json();
}
