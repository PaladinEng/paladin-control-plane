from pydantic import BaseModel
from typing import Optional


class ProjectSummary(BaseModel):
    id: str
    name: str
    path: str
    status: str  # active, idle, error
    current_state: str  # first paragraph from STATUS.md
    active_tasks: list[str]  # from WORKQUEUE Active Sprint
    last_updated: Optional[str] = None
    archived: bool = False


class ProjectDetail(ProjectSummary):
    workqueue_raw: str  # full WORKQUEUE.md content
    status_raw: str  # full STATUS.md content
    decisions_raw: Optional[str] = None
    recent_sessions: list[str] = []  # session log filenames
