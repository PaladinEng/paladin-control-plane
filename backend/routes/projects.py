from fastapi import APIRouter, HTTPException

from backend.models.project import ProjectDetail, ProjectSummary
from backend.services.project_scanner import get_project_by_id, scan_all_projects

router = APIRouter(prefix="/api/projects")


@router.get("", response_model=list[ProjectSummary])
async def list_projects():
    """Return all projects with summary status."""
    projects = scan_all_projects()
    return [ProjectSummary(**p.model_dump()) for p in projects]


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str):
    """Return full detail for a single project."""
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project
