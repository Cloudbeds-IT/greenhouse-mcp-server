import json
from greenhouse_mcp.server import mcp, require_auth
from greenhouse_mcp.client import greenhouse


def _slim_candidate(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "first_name": c.get("first_name"),
        "last_name": c.get("last_name"),
        "company": c.get("company"),
        "title": c.get("title"),
        "emails": [e.get("value") for e in (c.get("email_addresses") or [])],
        "phone": next((p.get("value") for p in (c.get("phone_numbers") or [])), None),
        "tags": c.get("tags"),
        "last_activity_at": c.get("last_activity_at"),
    }


def _slim_application(a: dict) -> dict:
    return {
        "id": a.get("id"),
        "candidate_id": a.get("candidate_id"),
        "job_id": a.get("job_id"),
        "status": a.get("status"),
        "stage_name": a.get("stage_name"),
        "created_at": a.get("created_at"),
        "rejected_at": a.get("rejected_at"),
    }


@mcp.tool()
async def get_candidate(candidate_id: int) -> str:
    """Get information about a specific candidate.

    Args:
        candidate_id: The Greenhouse candidate ID
    """
    require_auth()
    result = await greenhouse.get_by_id("/candidates", candidate_id)
    return json.dumps(_slim_candidate(result), indent=2)


@mcp.tool()
async def get_candidates_for_job(job_id: int, include_rejected: bool = False) -> str:
    """Get all candidates who applied to a specific job.

    Args:
        job_id: The Greenhouse job ID
        include_rejected: Whether to include rejected candidates (default False)
    """
    require_auth()
    # Cached paginated fetch — applications don't change often
    all_apps = await greenhouse.get_paginated_cached(
        "/applications", params={"per_page": 500}, max_pages=20
    )
    job_apps = [a for a in all_apps if a.get("job_id") == job_id]

    if not include_rejected:
        job_apps = [a for a in job_apps if a.get("status") != "rejected"]

    # Batch lookup candidates (up to 100 at a time via ids param)
    candidate_ids = list({a["candidate_id"] for a in job_apps if a.get("candidate_id")})

    candidates_by_id = {}
    for i in range(0, len(candidate_ids), 20):
        batch = candidate_ids[i : i + 20]
        results = await greenhouse.get_by_ids("/candidates", batch)
        for c in results:
            candidates_by_id[c["id"]] = _slim_candidate(c)

    # Merge candidates with their application info
    output = []
    for app in job_apps:
        cid = app.get("candidate_id")
        candidate = candidates_by_id.get(cid, {"candidate_id": cid})
        candidate["application"] = _slim_application(app)
        output.append(candidate)

    return json.dumps(output, indent=2)
