/**
 * sse.js — SSE Connection Manager
 * Connects to /api/events, auto-reconnects with exponential backoff,
 * dispatches typed custom events on window for views to consume.
 */

const SSE_URL = '/api/events';

let eventSource = null;
let reconnectDelay = 1000;  // start at 1s
const MAX_DELAY = 30000;    // cap at 30s

const sseStatus = document.getElementById('sse-status');
const sseStatusMobile = document.getElementById('sse-status-mobile');

function setStatus(state, text) {
    const statusText = sseStatus?.querySelector('.status-text');
    if (sseStatus) {
        sseStatus.className = `connection-status ${state}`;
        if (statusText) statusText.textContent = text;
    }
    if (sseStatusMobile) {
        sseStatusMobile.className = `bottom-nav-status ${state}`;
    }
}

function connect() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    setStatus('connecting', 'Connecting...');

    eventSource = new EventSource(SSE_URL);

    eventSource.onopen = () => {
        reconnectDelay = 1000;  // reset backoff on success
        setStatus('connected', 'Connected');
    };

    eventSource.onmessage = (event) => {
        // Ignore heartbeats (empty or ping data)
        if (!event.data || event.data === '' || event.data === 'ping') return;

        let parsed;
        try {
            parsed = JSON.parse(event.data);
        } catch {
            // Not JSON, ignore
            return;
        }

        const type = parsed.type || 'message';
        window.dispatchEvent(new CustomEvent(`sse:${type}`, { detail: parsed }));
        // Also dispatch a generic sse:event for catch-all listeners
        window.dispatchEvent(new CustomEvent('sse:event', { detail: parsed }));
    };

    eventSource.onerror = () => {
        setStatus('disconnected', 'Disconnected');
        eventSource.close();
        eventSource = null;

        const delay = reconnectDelay;
        reconnectDelay = Math.min(reconnectDelay * 2, MAX_DELAY);

        setTimeout(connect, delay);
    };
}

export function initSSE() {
    connect();
}

export function closeSSE() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    setStatus('disconnected', 'Disconnected');
}
