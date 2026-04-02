import json
from greenhouse_mcp.server import mcp, require_auth
from greenhouse_mcp.client import greenhouse


@mcp.tool()
async def list_applications(
    status: str | None = None,
    job_id: int | None = None,
    candidate_id: int | None = None,
    created_after: str | None = None,
    per_page: int = 100,
) -> str:
    """List applications from Greenhouse with optional filters.

    Args:
        status: Filter by status (active, rejected, hired)
        job_id: Filter by specific job ID
        candidate_id: Filter by specific candidate ID
        created_after: ISO datetime - only applications created after this date
        per_page: Results per page (1-500, default 100)
    """
    require_auth()
    params: dict = {"per_page": min(per_page, 500)}
    if status:
        params["status"] = status
    if job_id:
        params["job_id"] = job_id
    if candidate_id:
        params["candidate_id"] = candidate_id
    if created_after:
        params["created_at"] = f"gte|{created_after}"

    results = await greenhouse.get_paginated(
        "/applications", params=params, max_pages=3
    )
    return json.dumps(results, indent=2)


@mcp.tool()
async def get_application(application_id: int) -> str:
    """Get detailed information about a specific application.

    Args:
        application_id: The Greenhouse application ID
    """
    require_auth()
    result = await greenhouse.get_by_id("/applications", application_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def move_application_stage(application_id: int, stage_id: int) -> str:
    """Move an application to a different stage in the pipeline.

    Args:
        application_id: The Greenhouse application ID
        stage_id: The target stage ID to move the application to
    """
    require_auth()
    result = await greenhouse.post(
        f"/applications/{application_id}/move",
        json_data={"stage_id": stage_id},
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def reject_application(
    application_id: int,
    rejection_reason_id: int | None = None,
    notes: str | None = None,
) -> str:
    """Reject an application.

    Args:
        application_id: The Greenhouse application ID
        rejection_reason_id: Optional ID of the rejection reason
        notes: Optional rejection notes
    """
    require_auth()
    payload: dict = {}
    if rejection_reason_id:
        payload["rejection_reason_id"] = rejection_reason_id
    if notes:
        payload["notes"] = notes

    result = await greenhouse.post(
        f"/applications/{application_id}/reject",
        json_data=payload,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def unreject_application(application_id: int) -> str:
    """Unreject a previously rejected application to reactivate the candidate.

    Args:
        application_id: The Greenhouse application ID
    """
    require_auth()
    result = await greenhouse.post(f"/applications/{application_id}/unreject")
    return json.dumps(result, indent=2)


@mcp.tool()
async def hire_application(application_id: int) -> str:
    """Mark an application as hired, advancing it to the final stage.

    Args:
        application_id: The Greenhouse application ID
    """
    require_auth()
    result = await greenhouse.post(f"/applications/{application_id}/hire")
    return json.dumps(result, indent=2)


@mcp.tool()
async def transfer_application(application_id: int, new_job_id: int) -> str:
    """Transfer an application to a different job.

    Args:
        application_id: The Greenhouse application ID
        new_job_id: The target job ID to transfer to
    """
    require_auth()
    result = await greenhouse.post(
        f"/applications/{application_id}/transfer_to_job",
        json_data={"new_job_id": new_job_id},
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_application_scorecards(application_id: int) -> str:
    """Get all scorecards for an application.

    Args:
        application_id: The Greenhouse application ID
    """
    require_auth()
    # v3 uses top-level /scorecards endpoint, filter client-side
    all_scorecards = await greenhouse.get_paginated("/scorecards", max_pages=5)
    scorecards = [s for s in all_scorecards if s.get("application_id") == application_id]
    return json.dumps(scorecards, indent=2)
