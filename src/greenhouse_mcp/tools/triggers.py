import json
import httpx
from greenhouse_mcp.server import mcp, require_auth
from greenhouse_mcp.client import greenhouse


@mcp.tool()
async def trigger_stage_change(
    application_id: int,
    target_stage_id: int,
    add_note: str | None = None,
) -> str:
    """Trigger a stage change for an application and optionally add a note.
    Combines moving the application and logging the action.

    Args:
        application_id: The Greenhouse application ID
        target_stage_id: The stage ID to move to
        add_note: Optional note to add explaining the stage change
    """
    require_auth()
    results: dict = {}

    move_result = await greenhouse.post(
        f"/applications/{application_id}/move",
        json_data={"stage_id": target_stage_id},
    )
    results["move"] = move_result

    if add_note:
        app = await greenhouse.get_by_id("/applications", application_id)
        candidate_id = app.get("candidate_id")
        if candidate_id:
            note_result = await greenhouse.post(
                f"/candidates/{candidate_id}/activity_feed/notes",
                json_data={"body": add_note},
            )
            results["note"] = note_result

    return json.dumps(results, indent=2)


@mcp.tool()
async def trigger_bulk_tag(
    candidate_ids: list[int],
    tag: str,
) -> str:
    """Apply a tag to multiple candidates at once.
    Useful for batch operations like tagging all candidates from a sourcing campaign.

    Args:
        candidate_ids: List of Greenhouse candidate IDs
        tag: Tag name to apply to all candidates
    """
    require_auth()
    results = []
    for cid in candidate_ids:
        try:
            result = await greenhouse.put(
                f"/candidates/{cid}",
                json_data={"tags": [tag]},
            )
            results.append({"candidate_id": cid, "status": "success", "result": result})
        except Exception as e:
            results.append({"candidate_id": cid, "status": "error", "error": str(e)})

    return json.dumps(results, indent=2)


@mcp.tool()
async def trigger_reject_batch(
    application_ids: list[int],
    rejection_reason_id: int | None = None,
    notes: str | None = None,
) -> str:
    """Reject multiple applications in batch.
    Use with caution - this action affects multiple candidates.

    Args:
        application_ids: List of Greenhouse application IDs to reject
        rejection_reason_id: Optional rejection reason ID to apply to all
        notes: Optional notes to include with each rejection
    """
    require_auth()
    payload: dict = {}
    if rejection_reason_id:
        payload["rejection_reason_id"] = rejection_reason_id
    if notes:
        payload["notes"] = notes

    results = []
    for app_id in application_ids:
        try:
            result = await greenhouse.post(
                f"/applications/{app_id}/reject",
                json_data=payload,
            )
            results.append(
                {"application_id": app_id, "status": "success", "result": result}
            )
        except Exception as e:
            results.append(
                {"application_id": app_id, "status": "error", "error": str(e)}
            )

    return json.dumps(results, indent=2)


@mcp.tool()
async def trigger_webhook(
    url: str,
    payload: dict,
    method: str = "POST",
) -> str:
    """Send an outbound webhook/API call to an external system.
    Useful for triggering actions in scheduling tools, notification systems, etc.

    Args:
        url: The webhook URL to call
        payload: JSON payload to send
        method: HTTP method (POST or PUT, default POST)
    """
    require_auth()
    if method.upper() not in ("POST", "PUT"):
        return json.dumps({"error": "Only POST and PUT methods are supported"})

    async with httpx.AsyncClient() as client:
        if method.upper() == "POST":
            response = await client.post(url, json=payload, timeout=30)
        else:
            response = await client.put(url, json=payload, timeout=30)

    return json.dumps(
        {
            "status_code": response.status_code,
            "response": response.text[:1000],
        },
        indent=2,
    )


@mcp.tool()
async def trigger_reactivate_candidates(
    candidate_ids: list[int],
    job_id: int,
    tag: str | None = None,
    note: str | None = None,
) -> str:
    """Reactivate dormant candidates by unrejecting their applications and
    optionally tagging them and adding a note. Great for re-engagement campaigns.

    Args:
        candidate_ids: List of candidate IDs to reactivate
        job_id: The job to reactivate them for
        tag: Optional tag to apply (e.g., 'reengagement-2024-q1')
        note: Optional note to add to each candidate
    """
    require_auth()
    results = []
    for cid in candidate_ids:
        candidate_result: dict = {"candidate_id": cid}
        try:
            # Find their application for this job
            apps = await greenhouse.get_paginated(
                "/applications",
                params={"candidate_id": cid, "job_id": job_id, "per_page": 10},
                max_pages=1,
            )
            rejected_apps = [a for a in apps if a.get("status") == "rejected"]

            if rejected_apps:
                app_id = rejected_apps[0]["id"]
                unreject = await greenhouse.post(
                    f"/applications/{app_id}/unreject"
                )
                candidate_result["unreject"] = "success"
            else:
                candidate_result["unreject"] = "no_rejected_application_found"

            if tag:
                await greenhouse.put(
                    f"/candidates/{cid}",
                    json_data={"tags": [tag]},
                )
                candidate_result["tag"] = "success"

            if note:
                await greenhouse.post(
                    f"/candidates/{cid}/activity_feed/notes",
                    json_data={"body": note},
                )
                candidate_result["note"] = "success"

            candidate_result["status"] = "success"
        except Exception as e:
            candidate_result["status"] = "error"
            candidate_result["error"] = str(e)

        results.append(candidate_result)

    return json.dumps(results, indent=2)
