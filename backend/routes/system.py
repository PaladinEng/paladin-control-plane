"""
System configuration endpoints.
GET /api/system/config — returns shared .paladin-config.yaml as JSON
"""

from pathlib import Path

import yaml
from fastapi import APIRouter

router = APIRouter(prefix="/api/system")

PALADIN_CONFIG_PATH = Path.home() / "projects" / ".paladin-config.yaml"


def _load_config() -> dict:
    """Read .paladin-config.yaml. Returns defaults if file missing."""
    if not PALADIN_CONFIG_PATH.exists():
        return {
            "ignore_directories": [],
            "compliance": {"required_files": [], "meta_required_fields": []},
        }
    try:
        data = yaml.safe_load(PALADIN_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {
            "ignore_directories": [],
            "compliance": {"required_files": [], "meta_required_fields": []},
        }
    return {
        "ignore_directories": data.get("ignore_directories", []),
        "compliance": data.get("compliance", {"required_files": [], "meta_required_fields": []}),
    }


@router.get("/config")
async def get_system_config():
    """Return system configuration for client-side validation."""
    return _load_config()
