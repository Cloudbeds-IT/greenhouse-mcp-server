import json
from greenhouse_mcp.server import mcp, require_auth
from greenhouse_mcp.client import greenhouse


def _slim_job(job: dict) -> dict:
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "status": job.get("status"),
        "department_id": job.get("department_id"),
        "office_ids": job.get("office_ids"),
        "opened_at": job.get("opened_at"),
        "closed_at": job.get("closed_at"),
    }


@mcp.tool()
async def list_jobs(
    status: str | None = None,
    department_id: int | None = None,
    per_page: int = 100,
) -> str:
    """List jobs from Greenhouse with optional filters.

    Args:
        status: Filter by status (open, closed, draft)
        department_id: Filter by department ID
        per_page: Results per page (1-500, default 100)
    """
    require_auth()
    params: dict = {"per_page": min(per_page, 500)}
    if status:
        params["status"] = status
    if department_id:
        params["department_id"] = department_id

    results = await greenhouse.get_paginated("/jobs", params=params, max_pages=3)
    return json.dumps([_slim_job(j) for j in results], indent=2)


@mcp.tool()
async def get_job(job_id: int) -> str:
    """Get detailed information about a specific job.

    Args:
        job_id: The Greenhouse job ID
    """
    require_auth()
    result = await greenhouse.get_by_id("/jobs", job_id)
    return json.dumps(_slim_job(result), indent=2)
