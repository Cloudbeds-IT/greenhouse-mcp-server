# Greenhouse MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that connects Claude AI to the [Greenhouse](https://www.greenhouse.io) Applicant Tracking System (ATS). It enables Claude to search candidates, manage applications, draft personalized outreach, and trigger bulk actions — all in real time against your live Greenhouse data.

## What You Can Do

- **Search & discover candidates** — filter by tags, company, title, status, or date range
- **Rediscover dormant talent** — surface candidates inactive for 180+ days for re-engagement
- **Stack rank applicants** — pull scorecards and application details for any job
- **Manage applications** — move stages, reject, unreject, hire, or transfer applications
- **Craft personalized outreach** — generate context-aware messages and save them to candidate activity feeds
- **Trigger bulk actions** — batch tag, batch reject, or reactivate multiple candidates at once
- **Extract resumes** — download and read resume PDFs for any candidate

## Prerequisites

- Python 3.10 or higher
- [`uv`](https://docs.astral.sh/uv/) package manager (recommended)
- An Okta OIDC application configured for your organization
- Greenhouse OAuth credentials (service account)

## Installation

```bash
git clone https://github.com/Cloudbeds-IT/greenhouse-mcp-server.git
cd greenhouse-mcp-server
uv sync
```

## Configuration

Copy the environment template and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Okta OIDC — browser-based user authentication
OKTA_ISSUER=https://your-org.okta.com/oauth2/default
OKTA_CLIENT_ID=your_okta_client_id
OKTA_REDIRECT_URI=http://localhost:8080/callback

# Greenhouse OAuth — service account for API access
GREENHOUSE_CLIENT_ID=your_client_id_here
GREENHOUSE_CLIENT_SECRET=your_client_secret_here
```

## Usage with Claude Desktop

Add the server to your Claude Desktop configuration at `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "greenhouse": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/greenhouse-mcp-server",
        "-m",
        "greenhouse_mcp"
      ]
    }
  }
}
```

Replace `/path/to/greenhouse-mcp-server` with the absolute path to your clone.

## Authentication Flow

Before using any tools, you must authenticate:

1. Ask Claude to call `greenhouse_authenticate` — it will return an Okta login URL
2. Open that URL in your browser and complete the SSO login
3. Tell Claude you're done — it will call `greenhouse_complete_auth` to finish

All subsequent tool calls run under your Greenhouse user identity.

## Available Tools

### Authentication
| Tool | Description |
|------|-------------|
| `greenhouse_authenticate` | Start Okta SSO login flow |
| `greenhouse_complete_auth` | Complete authentication after browser login |

### Jobs
| Tool | Description |
|------|-------------|
| `list_jobs` | List jobs with optional status/department filters |
| `get_job` | Get detailed job info by ID |

### Candidates
| Tool | Description |
|------|-------------|
| `get_candidate` | Get a candidate's full profile |
| `get_candidate_applications_history` | Get a candidate's full application history across all jobs |
| `get_candidate_resume` | Download and extract text from a candidate's resume PDF |

### Applications
| Tool | Description |
|------|-------------|
| `list_applications` | List applications with status, date, and candidate filters |
| `get_application` | Get detailed application info |
| `get_application_scorecards` | Get interview scorecards for an application |
| `get_candidates_for_job` | Get all applicants for a specific job |
| `move_application_stage` | Move an application to a different pipeline stage |
| `reject_application` | Reject an application with optional reason and notes |
| `unreject_application` | Unreject a previously rejected application |
| `hire_application` | Mark an application as hired |
| `transfer_application` | Transfer an application to a different job |

### Search & Discovery
| Tool | Description |
|------|-------------|
| `search_candidates_by_criteria` | Filter candidates by tags, company, title, status, or date range |
| `find_dormant_candidates` | Find candidates inactive for 180+ days for re-engagement |
| `get_resumes_for_job` | List resume filenames for all applicants on a job |

### Outreach
| Tool | Description |
|------|-------------|
| `get_candidate_outreach_context` | Pull full candidate context including history, relationship type, and outreach guidance |
| `draft_outreach_note` | Save a personalized outreach message to a candidate's activity feed |

### Bulk Actions
| Tool | Description |
|------|-------------|
| `trigger_stage_change` | Move an application to a new stage and add a note in one call |
| `trigger_bulk_tag` | Apply a tag to multiple candidates at once |
| `trigger_reject_batch` | Batch reject multiple applications |
| `trigger_reactivate_candidates` | Unreject, tag, and add a note to dormant candidates in bulk |
| `trigger_webhook` | Send an HTTP request to an external webhook or system |

## Architecture

```
src/greenhouse_mcp/
├── __main__.py         # Entry point
├── server.py           # MCP server setup and auth tools
├── auth.py             # Greenhouse OAuth implementation
├── client.py           # Greenhouse Harvest API v3 async client
├── okta_handler.py     # Okta OIDC browser auth handler
└── tools/
    ├── jobs.py         # Job listing and retrieval
    ├── candidates.py   # Candidate lookup
    ├── applications.py # Application management
    ├── resumes.py      # Resume extraction
    ├── search.py       # Candidate search and discovery
    ├── outreach.py     # Outreach drafting
    └── triggers.py     # Bulk actions
```

**Key technical details:**
- Async HTTP client with automatic pagination (cursor-based, up to 10 pages)
- 5-minute in-memory cache for paginated data
- Resume PDFs are fetched and parsed server-side using PyMuPDF
- All API calls are scoped to the authenticated Greenhouse user
- Token refresh handled automatically with a 60-second buffer before expiry

## Development

Run the server directly for testing:

```bash
uv run -m greenhouse_mcp
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `mcp[cli]` | Model Context Protocol server framework |
| `httpx` | Async HTTP client for Greenhouse API |
| `python-dotenv` | Load credentials from `.env` |
| `PyJWT` | Decode Okta ID tokens |
| `pymupdf` | Extract text from resume PDFs |
