/**
 * project.js — Project Detail View
 * Shows status, active task queue, session logs, and raw workqueue.
 */

import { getProject, getThread, postPrompt, postResponse } from '../api.js';

let sseRefreshHandler = null;
let sseThreadHandler = null;
let currentProjectId = null;
let threadEntryIds = new Set();

// ============================================================
// Simple Markdown-to-HTML Converter (no library)
// ============================================================

function renderMarkdown(md) {
    if (!md) return '';

    let html = escapeHtml(md);

    // Code blocks (``` ... ```) — must come before inline code
    html = html.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) => {
        return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Inline code `...`
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // Bold **text**
    html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');

    // Italic *text* (single, not part of **)
    html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>');

    // Links [text](url)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // Process line by line for headers and lists
    const lines = html.split('\n');
    const result = [];
    let inList = false;
    let listItems = [];

    function flushList() {
        if (listItems.length > 0) {
            result.push(`<ul>${listItems.join('')}</ul>`);
            listItems = [];
            inList = false;
        }
    }

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // h2 ##
        if (/^## /.test(line)) {
            flushList();
            result.push(`<h2>${line.slice(3).trim()}</h2>`);
            continue;
        }

        // h3 ###
        if (/^### /.test(line)) {
            flushList();
            result.push(`<h3>${line.slice(4).trim()}</h3>`);
            continue;
        }

        // h4 ####
        if (/^#### /.test(line)) {
            flushList();
            result.push(`<h4>${line.slice(5).trim()}</h4>`);
            continue;
        }

        // List items (- item or * item) — skip checkbox items handled elsewhere
        const listMatch = line.match(/^[-*] (.+)$/);
        if (listMatch) {
            inList = true;
            listItems.push(`<li>${listMatch[1]}</li>`);
            continue;
        }

        // Checkbox list items - [ ] or - [x]
        const checkMatch = line.match(/^- \[([ x])\] (.+)$/i);
        if (checkMatch) {
            inList = true;
            const checked = checkMatch[1].toLowerCase() === 'x' ? 'checked' : '';
            const itemText = checkMatch[2];
            const strikeClass = checked ? ' class="done"' : '';
            listItems.push(`<li style="list-style:none;display:flex;gap:6px;align-items:flex-start;margin-bottom:4px"><input type="checkbox" ${checked} disabled style="margin-top:3px;flex-shrink:0"><span${strikeClass}>${itemText}</span></li>`);
            continue;
        }

        // Empty line — flush list, start paragraph break
        if (line.trim() === '') {
            flushList();
            result.push('');
            continue;
        }

        // Regular text — flush list first
        flushList();
        result.push(line);
    }

    flushList();

    // Wrap consecutive non-tag lines in paragraphs
    const finalLines = result.join('\n').split('\n');
    let output = '';
    let paraLines = [];

    function flushPara() {
        const text = paraLines.join(' ').trim();
        if (text) output += `<p>${text}</p>`;
        paraLines = [];
    }

    for (const fl of finalLines) {
        if (!fl.trim()) {
            flushPara();
        } else if (/^<(h[2-4]|ul|pre|p)/.test(fl.trim())) {
            flushPara();
            output += fl + '\n';
        } else {
            paraLines.push(fl);
        }
    }
    flushPara();

    return output;
}

// ============================================================
// Helpers
// ============================================================

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function statusBadge(status) {
    const map = {
        active:        { cls: 'badge-active',      label: 'Active' },
        error:         { cls: 'badge-error',        label: 'Error' },
        'in-progress': { cls: 'badge-in-progress',  label: 'In Progress' },
        'needs-input': { cls: 'badge-needs-input',  label: 'Needs Input' },
        idle:          { cls: 'badge-idle',          label: 'Idle' },
        inactive:      { cls: 'badge-inactive',      label: 'Inactive' },
    };
    const s = map[status] || { cls: 'badge-idle', label: status || 'Unknown' };
    return `<span class="status-badge ${s.cls}"><span class="dot"></span>${s.label}</span>`;
}

function backArrow() {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>`;
}

function docIcon() {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
}

function chevronRight() {
    return `<svg class="collapsible-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>`;
}

function renderTaskList(tasks) {
    if (!tasks || tasks.length === 0) {
        return '<p class="text-muted" style="font-size:13px">No active tasks.</p>';
    }
    const items = tasks.map(t => `
        <li class="task-item">
            <input type="checkbox" disabled>
            <span class="task-text">${escapeHtml(t)}</span>
        </li>`).join('');
    return `<ul class="task-list">${items}</ul>`;
}

function renderSessions(sessions, projectId) {
    if (!sessions || sessions.length === 0) {
        return '<p class="text-muted" style="font-size:13px">No session logs found.</p>';
    }
    const items = sessions.map(s => {
        const filename = typeof s === 'string' ? s : s.filename;
        const size = s.size ? ` (${Math.round(s.size / 1024)}kb)` : '';
        return `
        <li class="session-item">
            ${docIcon()}
            <a class="session-link"
               href="/api/projects/${encodeURIComponent(projectId)}/logs/${encodeURIComponent(filename)}"
               download="${escapeHtml(filename)}"
               target="_blank">
                ${escapeHtml(filename)}
            </a>
            <span class="session-size">${escapeHtml(size)}</span>
        </li>`;
    }).join('');
    return `<ul class="session-list">${items}</ul>`;
}

function collapsible(id, title, bodyHtml, open = false) {
    const openClass = open ? ' open' : '';
    return `
        <div class="collapsible${openClass}" id="collapsible-${id}">
            <div class="collapsible-header">
                <span>${title}</span>
                ${chevronRight()}
            </div>
            <div class="collapsible-body">
                <div class="collapsible-body-inner">
                    ${bodyHtml}
                </div>
            </div>
        </div>`;
}

function attachCollapsibles(container) {
    container.querySelectorAll('.collapsible-header').forEach(header => {
        header.addEventListener('click', () => {
            header.closest('.collapsible').classList.toggle('open');
        });
    });
}

// ============================================================
// Chat Thread Helpers
// ============================================================

function relativeTime(isoStr) {
    const now = Date.now();
    const then = new Date(isoStr).getTime();
    const diff = Math.max(0, now - then);
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

function renderThreadEntry(entry) {
    const time = relativeTime(entry.timestamp);

    if (entry.type === 'event') {
        return `<div class="thread-entry thread-event">
            <span class="thread-event-time">${escapeHtml(time)}</span>
            <span class="thread-event-text">${escapeHtml(entry.content)}</span>
        </div>`;
    }

    if (entry.type === 'system') {
        return `<div class="thread-entry thread-system">${escapeHtml(entry.content)}</div>`;
    }

    if (entry.type === 'prompt' && entry.author === 'user') {
        return `<div class="thread-entry thread-user">
            <div class="thread-bubble thread-bubble-user">
                <div class="thread-bubble-header">
                    <span class="thread-author">You</span>
                    <span class="thread-time">${escapeHtml(time)}</span>
                </div>
                <div class="thread-bubble-content">${escapeHtml(entry.content)}</div>
            </div>
        </div>`;
    }

    if (entry.type === 'needs-input') {
        const responded = entry.responded;
        if (responded) {
            return `<div class="thread-entry thread-needs-input thread-needs-input-resolved">
                <div class="thread-bubble thread-bubble-needs-input">
                    <div class="thread-bubble-header">
                        <span class="thread-author">Supervisor</span>
                        <span class="thread-time">${escapeHtml(time)}</span>
                        <span class="needs-input-resolved-badge">Resolved</span>
                    </div>
                    <div class="thread-bubble-content">${escapeHtml(entry.content)}</div>
                </div>
            </div>`;
        }
        return `<div class="thread-entry thread-needs-input" data-entry-id="${escapeHtml(entry.id)}">
            <div class="thread-bubble thread-bubble-needs-input">
                <div class="thread-bubble-header">
                    <span class="thread-author">Supervisor</span>
                    <span class="thread-time">${escapeHtml(time)}</span>
                    <span class="needs-input-badge">Needs your input</span>
                </div>
                <div class="thread-bubble-content">${escapeHtml(entry.content)}</div>
                <div class="needs-input-response-form">
                    <textarea class="needs-input-textarea"
                        placeholder="Your response..."
                        rows="2"></textarea>
                    <div class="needs-input-actions">
                        <span class="needs-input-error"></span>
                        <button class="needs-input-submit" type="button">Respond</button>
                    </div>
                </div>
            </div>
        </div>`;
    }

    // response from supervisor or other
    const authorLabel = entry.author === 'supervisor' ? 'Supervisor' : escapeHtml(entry.author || 'System');
    return `<div class="thread-entry thread-supervisor">
        <div class="thread-bubble thread-bubble-supervisor">
            <div class="thread-bubble-header">
                <span class="thread-author">${authorLabel}</span>
                <span class="thread-time">${escapeHtml(time)}</span>
            </div>
            <div class="thread-bubble-content">${escapeHtml(entry.content)}</div>
        </div>
    </div>`;
}

function renderThread(entries) {
    if (!entries || entries.length === 0) {
        return '<p class="thread-empty">No messages yet</p>';
    }
    return entries.map(renderThreadEntry).join('');
}

async function loadThread(projectId) {
    const threadContainer = document.getElementById('thread-messages');
    if (!threadContainer) return;

    try {
        const entries = await getThread(projectId);
        threadEntryIds = new Set(entries.map(e => e.id));
        threadContainer.innerHTML = renderThread(entries);
        threadContainer.scrollTop = threadContainer.scrollHeight;
        setupNeedsInputHandlers(currentProjectId);
    } catch (err) {
        threadContainer.innerHTML = `<p class="text-muted">Failed to load thread.</p>`;
    }
}

function setupPromptInput(projectId) {
    const form = document.getElementById('prompt-form');
    const textarea = document.getElementById('prompt-textarea');
    const submitBtn = document.getElementById('prompt-submit');
    const errorEl = document.getElementById('prompt-error');

    if (!form || !textarea || !submitBtn) return;

    function updateSubmitState() {
        submitBtn.disabled = !textarea.value.trim();
    }

    textarea.addEventListener('input', updateSubmitState);

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const content = textarea.value.trim();
        if (!content) return;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Sending...';
        if (errorEl) errorEl.textContent = '';

        // Optimistic update
        const threadContainer = document.getElementById('thread-messages');
        const emptyMsg = threadContainer?.querySelector('.thread-empty');
        if (emptyMsg) emptyMsg.remove();

        const optimisticEntry = {
            id: 'optimistic-' + Date.now(),
            timestamp: new Date().toISOString(),
            type: 'prompt',
            author: 'user',
            content: content,
        };
        if (threadContainer) {
            threadContainer.insertAdjacentHTML('beforeend', renderThreadEntry(optimisticEntry));
            threadContainer.scrollTop = threadContainer.scrollHeight;
        }

        textarea.value = '';

        try {
            await postPrompt(projectId, content);
            submitBtn.textContent = 'Send';
            updateSubmitState();
        } catch (err) {
            if (errorEl) errorEl.textContent = `Error: ${err.message}`;
            submitBtn.textContent = 'Send';
            updateSubmitState();
        }
    });
}

function setupNeedsInputHandlers(projectId) {
    const thread = document.getElementById('thread-messages');
    if (!thread) return;

    thread.querySelectorAll('.needs-input-response-form').forEach(form => {
        const btn = form.querySelector('.needs-input-submit');
        const textarea = form.querySelector('.needs-input-textarea');
        const errorEl = form.querySelector('.needs-input-error');
        if (!btn || !textarea) return;

        btn.addEventListener('click', async () => {
            const content = textarea.value.trim();
            if (!content) return;
            btn.disabled = true;
            btn.textContent = 'Sending...';
            if (errorEl) errorEl.textContent = '';
            try {
                await postResponse(projectId, content);
                await loadThread(projectId);
            } catch (err) {
                if (errorEl) errorEl.textContent = `Error: ${err.message}`;
                btn.disabled = false;
                btn.textContent = 'Respond';
            }
        });
    });
}

// ============================================================
// Main Render
// ============================================================

export async function renderProject(content, projectId) {
    currentProjectId = projectId;
    threadEntryIds = new Set();

    // Clean up previous SSE listeners
    if (sseRefreshHandler) {
        window.removeEventListener('sse:event', sseRefreshHandler);
        sseRefreshHandler = null;
    }
    if (sseThreadHandler) {
        window.removeEventListener('sse:thread_update', sseThreadHandler);
        sseThreadHandler = null;
    }

    content.innerHTML = `
        <a href="#/" class="back-link">${backArrow()} Back to Dashboard</a>
        <div class="loading-container"><div class="spinner"></div></div>`;

    await loadProject(content, projectId);

    // Auto-refresh project data on SSE events
    sseRefreshHandler = () => {
        if (currentProjectId === projectId) {
            loadProject(content, projectId);
        }
    };
    window.addEventListener('sse:event', sseRefreshHandler);

    // Thread-specific SSE handler
    sseThreadHandler = (e) => {
        if (currentProjectId === projectId && e.detail?.project_id === projectId) {
            loadThread(projectId);
        }
    };
    window.addEventListener('sse:thread_update', sseThreadHandler);
}

async function loadProject(content, projectId) {
    try {
        const project = await getProject(projectId);
        renderProjectData(content, project);
    } catch (err) {
        content.innerHTML = `
            <a href="#/" class="back-link">${backArrow()} Back to Dashboard</a>
            <div class="error-banner">Failed to load project: ${escapeHtml(err.message)}</div>`;
    }
}

function renderProjectData(content, project) {
    // Left panel content
    const leftPanel = `
        <div class="project-left-panel">
            <!-- Current State -->
            <div class="panel-section">
                <p class="section-title">Current State</p>
                <p class="current-state-text">${escapeHtml(project.current_state || 'No state available.')}</p>
            </div>

            <!-- Active Tasks -->
            <div class="panel-section">
                <p class="section-title">Active Sprint</p>
                ${renderTaskList(project.active_tasks)}
            </div>

            <!-- Full Status (collapsible) -->
            <div class="panel-section">
                ${collapsible(
                    'status',
                    'Full Status',
                    `<div class="markdown-body">${renderMarkdown(project.status_raw || '')}</div>`
                )}
            </div>
        </div>`;

    // Right panel content
    const rightPanel = `
        <div class="project-right-panel">
            <!-- Session Logs -->
            <div class="panel-section">
                <p class="section-title">Session Logs</p>
                ${renderSessions(project.recent_sessions, project.id)}
            </div>

            <!-- Raw Workqueue (collapsible) -->
            <div class="panel-section">
                ${collapsible(
                    'workqueue',
                    'Workqueue',
                    `<div class="workqueue-raw">${escapeHtml(project.workqueue_raw || 'No workqueue data.')}</div>
                     <button class="add-task-btn" type="button"
                             onclick="showAddTaskForm('${escapeHtml(project.id)}')">
                         + Add task
                     </button>`
                )}
            </div>

            <!-- Decisions (collapsible, if available) -->
            ${project.decisions_raw ? collapsible(
                'decisions',
                'Decisions',
                `<div class="markdown-body">${renderMarkdown(project.decisions_raw)}</div>`
            ) : ''}
        </div>`;

    // Chat thread panel
    const threadPanel = `
        <div class="thread-panel">
            <p class="section-title">Chat Thread</p>
            <div class="thread-messages" id="thread-messages">
                <div class="loading-container"><div class="spinner"></div></div>
            </div>
            <form class="prompt-form" id="prompt-form">
                <textarea id="prompt-textarea" class="prompt-textarea"
                    placeholder="Send instruction to supervisor..."
                    rows="3"></textarea>
                <div class="prompt-actions">
                    <span id="prompt-error" class="prompt-error"></span>
                    <button type="submit" id="prompt-submit" class="prompt-submit" disabled>Send</button>
                </div>
            </form>
            <div class="batch-upload-section">
                <details class="batch-details">
                    <summary class="batch-summary">
                        Upload batch prompts (.md or .txt)
                    </summary>
                    <div class="batch-body">
                        <p class="batch-hint">
                            Each ## section or blank-line paragraph becomes
                            a separate queued prompt, executed in order.
                        </p>
                        <input type="file" id="batch-file-input"
                               accept=".md,.txt,text/plain,text/markdown"
                               class="batch-file-input">
                        <div id="batch-preview" class="batch-preview"></div>
                        <button id="batch-submit" class="batch-submit"
                                disabled type="button">
                            Queue prompts
                        </button>
                        <span id="batch-status" class="batch-status"></span>
                    </div>
                </details>
            </div>
        </div>`;

    content.innerHTML = `
        <a href="#/" class="back-link">${backArrow()} Back to Dashboard</a>
        <div class="project-detail">
            <div class="project-detail-header">
                <h2>${escapeHtml(project.name)}</h2>
                <div class="project-meta">
                    ${statusBadge(project.status)}
                    <span class="project-path">${escapeHtml(project.path || '')}</span>
                    <span class="last-updated">Updated: ${escapeHtml(project.last_updated || '?')}</span>
                </div>
            </div>
            <div class="project-detail-body">
                ${leftPanel}
                ${rightPanel}
            </div>
            ${threadPanel}
        </div>`;

    attachCollapsibles(content);
    loadThread(project.id);
    setupPromptInput(project.id);
    setupNeedsInputHandlers(project.id);
    setupBatchUpload(project.id);
}

// ============================================================
// Add Task Form (PCP-015)
// ============================================================

function renderAddTaskForm(projectId) {
    return `
    <div class="add-task-form" id="add-task-form">
        <div class="form-row">
            <select id="task-priority" class="task-select">
                <option value="P1">P1 — Do next</option>
                <option value="P2">P2 — Soon</option>
                <option value="P3" selected>P3 — Backlog</option>
            </select>
            <select id="task-blast" class="task-select">
                <option value="NONE">No blast radius</option>
                <option value="LOW" selected>LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
            </select>
            <label class="task-overnight">
                <input type="checkbox" id="task-overnight">
                Overnight-ready
            </label>
        </div>
        <input type="text" id="task-title"
               placeholder="Task title"
               class="task-title-input">
        <input type="text" id="task-desc"
               placeholder="Description (optional)"
               class="task-desc-input">
        <div class="form-actions">
            <button id="task-cancel" class="btn-secondary" type="button">
                Cancel
            </button>
            <button id="task-submit" class="btn-primary"
                    type="button" disabled>
                Add task
            </button>
        </div>
        <span id="task-status" class="form-status"></span>
    </div>`;
}

function setupAddTaskForm(projectId) {
    const submitBtn = document.getElementById('task-submit');
    const cancelBtn = document.getElementById('task-cancel');
    const titleInput = document.getElementById('task-title');
    const descInput = document.getElementById('task-desc');
    const prioritySelect = document.getElementById('task-priority');
    const blastSelect = document.getElementById('task-blast');
    const overnightCheck = document.getElementById('task-overnight');
    const statusEl = document.getElementById('task-status');
    if (!submitBtn || !cancelBtn) return;

    titleInput?.addEventListener('input', () => {
        submitBtn.disabled = !titleInput.value.trim();
    });

    cancelBtn.addEventListener('click', () => {
        document.getElementById('add-task-form')?.remove();
    });

    submitBtn.addEventListener('click', async () => {
        const title = titleInput.value.trim();
        if (!title) return;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Adding...';

        try {
            const res = await fetch(
                `/api/projects/${encodeURIComponent(projectId)}/workqueue/add`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title,
                        priority: prioritySelect?.value || 'P3',
                        description: descInput?.value.trim() || '',
                        overnight_ready: overnightCheck?.checked || false,
                        blast_radius: blastSelect?.value || 'LOW',
                    }),
                }
            );
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            if (statusEl) statusEl.textContent =
                `Task added to ${data.priority}`;
            titleInput.value = '';
            if (descInput) descInput.value = '';
            submitBtn.textContent = 'Add task';
        } catch (err) {
            if (statusEl) statusEl.textContent = `Error: ${err.message}`;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add task';
        }
    });
}

window.showAddTaskForm = function(projectId) {
    const existing = document.getElementById('add-task-form');
    if (existing) { existing.remove(); return; }
    const btn = document.querySelector('.add-task-btn');
    if (btn) {
        btn.insertAdjacentHTML('afterend', renderAddTaskForm(projectId));
        setupAddTaskForm(projectId);
    }
};

function setupBatchUpload(projectId) {
    const fileInput = document.getElementById('batch-file-input');
    const submitBtn = document.getElementById('batch-submit');
    const preview = document.getElementById('batch-preview');
    const status = document.getElementById('batch-status');
    if (!fileInput || !submitBtn) return;

    let parsedPrompts = [];

    fileInput.addEventListener('change', async () => {
        const file = fileInput.files[0];
        if (!file) return;
        const text = await file.text();
        parsedPrompts = text.includes('\n## ')
            ? text.split(/\n(?=## )/).map(s => s.trim()).filter(Boolean)
            : text.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);

        if (parsedPrompts.length === 0) {
            preview.style.display = 'none';
            submitBtn.disabled = true;
            if (status) status.textContent = 'No prompts found in file.';
            return;
        }

        preview.style.display = 'block';
        preview.innerHTML = `<strong>${parsedPrompts.length} prompt(s) found:</strong><br>` +
            parsedPrompts.map((p, i) =>
                `${i + 1}. ${escapeHtml(p.slice(0, 60))}${p.length > 60 ? '\u2026' : ''}`
            ).join('<br>');
        submitBtn.disabled = false;
        if (status) status.textContent = '';
    });

    submitBtn.addEventListener('click', async () => {
        if (!parsedPrompts.length) return;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Queuing...';
        if (status) status.textContent = '';

        try {
            const res = await fetch(
                `/api/projects/${encodeURIComponent(projectId)}/prompts/batch`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompts: parsedPrompts }),
                }
            );
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (status) status.textContent =
                `Queued ${data.queued} prompt(s) successfully`;
            fileInput.value = '';
            preview.style.display = 'none';
            parsedPrompts = [];
            await loadThread(projectId);
        } catch (err) {
            if (status) status.textContent = `Error: ${err.message}`;
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Queue prompts';
        }
    });
}

export function cleanupProject() {
    if (sseRefreshHandler) {
        window.removeEventListener('sse:event', sseRefreshHandler);
        sseRefreshHandler = null;
    }
    if (sseThreadHandler) {
        window.removeEventListener('sse:thread_update', sseThreadHandler);
        sseThreadHandler = null;
    }
    currentProjectId = null;
    threadEntryIds = new Set();
}
