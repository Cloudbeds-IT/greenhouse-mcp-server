import json
from greenhouse_mcp.server import mcp, require_auth
from greenhouse_mcp.client import greenhouse


@mcp.tool()
async def find_dormant_candidates(
    days_inactive: int = 180,
    original_job_id: int | None = None,
    status: str = "rejected",
    per_page: int = 100,
) -> str:
    """Find dormant/past candidates who haven't been active recently.
    Useful for re-engagement campaigns to rediscover old talent in Greenhouse.

    Args:
        days_inactive: Minimum days since last activity (default 180)
        original_job_id: Optional - only find candidates who applied to this job
        status: Candidate status to search (default 'rejected' to find past applicants)
        per_page: Results per page (1-500)
    """
    require_auth()
    from datetime import datetime, timedelta

    cutoff = (datetime.utcnow() - timedelta(days=days_inactive)).isoformat() + "Z"

    params: dict = {
        "per_page": min(per_page, 500),
        "updated_at": f"lte|{cutoff}",
    }
    if status:
        params["status"] = status

    candidates = await greenhouse.get_paginated(
        "/candidates", params=params, max_pages=5
    )

    # If filtering by job, get applications and cross-reference
    if original_job_id:
        app_params = {"job_id": original_job_id, "per_page": 500}
        apps = await greenhouse.get_paginated(
            "/applications", params=app_params, max_pages=5
        )
        app_candidate_ids = {a.get("candidate_id") for a in apps}
        candidates = [c for c in candidates if c.get("id") in app_candidate_ids]

    return json.dumps(candidates, indent=2)


@mcp.tool()
async def search_candidates_by_criteria(
    tags: list[str] | None = None,
    company: str | None = None,
    title: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    status: str | None = None,
    per_page: int = 100,
) -> str:
    """Search and filter candidates based on multiple criteria.
    Results can be used for stack ranking by Claude.

    Args:
        tags: Filter by candidate tags
        company: Filter by company name (searches in candidate data)
        title: Filter by job title (searches in candidate data)
        created_after: ISO datetime - candidates created after this date
        created_before: ISO datetime - candidates created before this date
        status: Filter by status (active, rejected, hired, converted)
        per_page: Results per page (1-500)
    """
    require_auth()
    params: dict = {"per_page": min(per_page, 500)}
    if status:
        params["status"] = status
    if created_after:
        params["created_at"] = f"gte|{created_after}"
    if created_before:
        params["created_at"] = f"lte|{created_before}"

    candidates = await greenhouse.get_paginated(
        "/candidates", params=params, max_pages=5
    )

    # Client-side filtering for fields not supported by API filters
    if tags:
        tag_set = {t.lower() for t in tags}
        candidates = [
            c
            for c in candidates
            if tag_set.intersection(
                t.lower() for t in (c.get("tags") or [])
            )
        ]
    if company:
        company_lower = company.lower()
        candidates = [
            c
            for c in candidates
            if company_lower in (c.get("company") or "").lower()
        ]
    if title:
        title_lower = title.lower()
        candidates = [
            c
            for c in candidates
            if title_lower in (c.get("title") or "").lower()
        ]

    return json.dumps(candidates, indent=2)


@mcp.tool()
async def get_candidates_for_job(job_id: int, include_rejected: bool = False) -> str:
    """Get all candidates who have applied to a specific job.
    Useful for reviewing the applicant pool and stack ranking.

    Args:
        job_id: The Greenhouse job ID
        include_rejected: Whether to include rejected candidates (default False)
    """
    require_auth()
    params: dict = {"job_id": job_id, "per_page": 500}
    apps = await greenhouse.get_paginated("/applications", params=params, max_pages=5)

    if not include_rejected:
        apps = [a for a in apps if a.get("status") != "rejected"]

    # Enrich with candidate data
    results = []
    for app in apps:
        cid = app.get("candidate_id")
        if cid:
            try:
                candidate = await greenhouse.get_by_id("/candidates", cid)
                candidate["application"] = app
                results.append(candidate)
            except Exception:
                results.append({"candidate_id": cid, "application": app})

    return json.dumps(results, indent=2)


@mcp.tool()
async def get_candidate_applications_history(candidate_id: int) -> str:
    """Get the full application history for a candidate across all jobs.
    Useful for understanding a candidate's relationship with the company.

    Args:
        candidate_id: The Greenhouse candidate ID
    """
    require_auth()
    apps = await greenhouse.get_paginated(
        "/applications", params={"candidate_id": candidate_id, "per_page": 500}
    )

    # Enrich with job info
    for app in apps:
        job_id = app.get("job_id")
        if job_id:
            try:
                job = await greenhouse.get_by_id("/jobs", job_id)
                app["job_details"] = {
                    "name": job.get("name"),
                    "status": job.get("status"),
                    "departments": job.get("departments"),
                    "offices": job.get("offices"),
                }
            except Exception:
                pass

    return json.dumps(apps, indent=2)
