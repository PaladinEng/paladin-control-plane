#!/usr/bin/env bash
# ntfy-hooks.sh — Claude Code hook helper for Paladin Control Plane
#
# Usage: source this file or call it directly with an event type.
#
# ntfy topic names used by this project:
#   paladin-alerts   — critical alerts and important events
#   paladin-sessions — session lifecycle events (start, end, subagent activity)
#   paladin-errors   — errors and failures
#
# ntfy server: http://localhost:8090  (also reachable at http://10.1.10.50:8090 via Tailscale)
#
# Called by Claude Code hooks in .claude/settings.json.
# All functions are silent on failure (|| true) so hooks never block Claude.

NTFY_BASE="http://localhost:8090"

# post_ntfy <topic> <message> [title] [priority] [tags]
post_ntfy() {
    local topic="${1:?topic required}"
    local message="${2:?message required}"
    local title="${3:-Paladin Control Plane}"
    local priority="${4:-default}"
    local tags="${5:-}"

    local args=(
        -s
        -o /dev/null
        -X POST
        -H "Title: ${title}"
        -H "Priority: ${priority}"
        -d "${message}"
    )
    [[ -n "${tags}" ]] && args+=(-H "Tags: ${tags}")

    curl "${args[@]}" "${NTFY_BASE}/${topic}" 2>/dev/null || true
}

# Convenience wrappers
ntfy_alert()   { post_ntfy "paladin-alerts"   "$1" "${2:-Alert}"   "high"    "${3:-warning}"; }
ntfy_session() { post_ntfy "paladin-sessions" "$1" "${2:-Session}" "default" "${3:-robot}"; }
ntfy_error()   { post_ntfy "paladin-errors"   "$1" "${2:-Error}"   "urgent"  "${3:-x,rotating_light}"; }

# If called directly, dispatch on first argument
case "${1:-}" in
    session_end)
        ntfy_session "Session ended at $(date '+%Y-%m-%d %H:%M:%S')" "Session End" "wave"
        ;;
    session_start)
        ntfy_session "Session started at $(date '+%Y-%m-%d %H:%M:%S')" "Session Start" "wave"
        ;;
    subagent_stop)
        ntfy_session "Subagent '${CLAUDE_SUBAGENT_NAME:-unknown}' stopped at $(date '+%Y-%m-%d %H:%M:%S')" "Subagent Stop" "robot"
        ;;
    error)
        ntfy_error "${2:-Unspecified error} at $(date '+%Y-%m-%d %H:%M:%S')"
        ;;
    alert)
        ntfy_alert "${2:-Unspecified alert} at $(date '+%Y-%m-%d %H:%M:%S')"
        ;;
    test)
        post_ntfy "paladin-alerts" "ntfy hook test OK at $(date '+%Y-%m-%d %H:%M:%S')" "Test" "default" "white_check_mark"
        echo "Test notification sent to paladin-alerts"
        ;;
    *)
        # No-op when sourced or called with unknown event
        ;;
esac
