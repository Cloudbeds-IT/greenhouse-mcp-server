import json
from greenhouse_mcp.server import mcp, require_auth
from greenhouse_mcp.client import greenhouse


@mcp.tool()
async def get_candidate_outreach_context(candidate_id: int) -> str:
    """Gather all context needed to craft a personalized outreach message for a candidate.
    Returns the candidate profile, application history, activity feed, and relationship type.

    This gives Claude everything needed to write tailored outreach based on
    whether this is a new candidate, old applicant, or previously engaged candidate.

    Args:
        candidate_id: The Greenhouse candidate ID
    """
    require_auth()
    candidate = await greenhouse.get_by_id("/candidates", candidate_id)
    apps = await greenhouse.get_paginated(
        "/applications", params={"candidate_id": candidate_id, "per_page": 500}
    )

    # v3 has no path-based GET — fetch notes and filter client-side
    try:
        all_notes = await greenhouse.get_paginated("/notes", max_pages=5)
        activity = [n for n in all_notes if n.get("candidate_id") == candidate_id]
    except Exception:
        activity = []

    # Determine relationship type
    if not apps:
        relationship = "new_candidate"
    elif any(a.get("status") == "active" for a in apps):
        relationship = "active_candidate"
    elif any(a.get("status") == "hired" for a in apps):
        relationship = "past_hire"
    else:
        # All applications are rejected/inactive
        most_recent = max(
            apps, key=lambda a: a.get("created_at", ""), default={}
        )
        relationship = "past_applicant"

    # Enrich apps with job names
    for app in apps:
        job_id = app.get("job_id")
        if job_id:
            try:
                job = await greenhouse.get_by_id("/jobs", job_id)
                app["job_name"] = job.get("name")
            except Exception:
                pass

    context = {
        "candidate": candidate,
        "relationship_type": relationship,
        "applications": apps,
        "activity_feed": activity,
        "outreach_guidance": _outreach_guidance(relationship),
    }
    return json.dumps(context, indent=2)


def _outreach_guidance(relationship: str) -> str:
    guidance = {
        "new_candidate": (
            "This is a brand new candidate with no prior relationship. "
            "Focus on the role opportunity and company value proposition. "
            "Keep it warm but professional."
        ),
        "active_candidate": (
            "This candidate has an active application. "
            "Reference their current application status and next steps. "
            "Be encouraging and provide clear timeline expectations."
        ),
        "past_applicant": (
            "This candidate applied previously but was not hired. "
            "Acknowledge their past interest in the company. "
            "Highlight what's new or different about this opportunity. "
            "Be respectful of their time and previous experience with us."
        ),
        "past_hire": (
            "This person was previously hired by the company. "
            "They are a boomerang candidate. Reference their past tenure positively. "
            "Emphasize what's changed and why now is a great time to return."
        ),
    }
    return guidance.get(relationship, "Personalize based on available context.")


@mcp.tool()
async def draft_outreach_note(
    candidate_id: int,
    job_id: int,
    message: str,
) -> str:
    """Save a personalized outreach message as a note on the candidate's profile.
    This creates a record of the outreach in Greenhouse's activity feed.

    Args:
        candidate_id: The Greenhouse candidate ID
        job_id: The job ID the outreach is for (for context in the note)
        message: The outreach message to save
    """
    require_auth()
    try:
        job = await greenhouse.get_by_id("/jobs", job_id)
        job_name = job.get("name", f"Job #{job_id}")
    except Exception:
        job_name = f"Job #{job_id}"

    note_body = f"**Outreach for: {job_name}**\n\n{message}"

    result = await greenhouse.post(
        f"/candidates/{candidate_id}/activity_feed/notes",
        json_data={"body": note_body},
    )
    return json.dumps(result, indent=2)
