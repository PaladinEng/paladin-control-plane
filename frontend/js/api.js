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
