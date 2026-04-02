import json
import httpx
import fitz  # pymupdf
from greenhouse_mcp.server import mcp, require_auth
from greenhouse_mcp.client import greenhouse


async def _extract_resume_text(url: str) -> str:
    """Download a resume PDF and extract its text content."""
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=30)
        r.raise_for_status()

    doc = fitz.open(stream=r.content, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()


@mcp.tool()
async def get_candidate_resume(candidate_id: int) -> str:
    """Get the resume text content for a specific candidate.

    Downloads the resume PDF server-side and extracts the text.

    Args:
        candidate_id: The Greenhouse candidate ID
    """
    require_auth()
    all_attachments = await greenhouse.get_paginated_cached(
        "/attachments", params={"type": "resume", "per_page": 500}, max_pages=20
    )
    resumes = [a for a in all_attachments if a.get("candidate_id") == candidate_id]

    if not resumes:
        return json.dumps({"error": f"No resume found for candidate {candidate_id}"})

    r = resumes[0]
    try:
        text = await _extract_resume_text(r["url"])
    except Exception as e:
        return json.dumps({
            "candidate_id": candidate_id,
            "filename": r.get("filename"),
            "error": f"Could not extract text: {e}",
        })

    return json.dumps({
        "candidate_id": candidate_id,
        "filename": r.get("filename"),
        "resume_text": text,
    }, indent=2)


@mcp.tool()
async def get_resumes_for_job(job_id: int) -> str:
    """Get all resume filenames for candidates who applied to a specific job.

    Returns candidate IDs and filenames. Use get_candidate_resume to
    read a specific candidate's resume text.

    Args:
        job_id: The Greenhouse job ID
    """
    require_auth()
    all_apps = await greenhouse.get_paginated_cached(
        "/applications", params={"per_page": 500}, max_pages=20
    )
    job_candidate_ids = {
        a.get("candidate_id")
        for a in all_apps
        if a.get("job_id") == job_id and a.get("candidate_id")
    }

    if not job_candidate_ids:
        return json.dumps({"error": f"No applications found for job {job_id}"})

    all_resumes = await greenhouse.get_paginated_cached(
        "/attachments", params={"type": "resume", "per_page": 500}, max_pages=20
    )

    results = []
    for r in all_resumes:
        cid = r.get("candidate_id")
        if cid in job_candidate_ids:
            results.append({
                "candidate_id": cid,
                "filename": r.get("filename"),
            })

    return json.dumps(results, indent=2)
