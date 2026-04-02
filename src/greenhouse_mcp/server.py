import asyncio
import logging
import sys

from mcp.server.fastmcp import FastMCP

from greenhouse_mcp.auth import auth
from greenhouse_mcp.okta_handler import OktaOIDCHandler, OktaAuthError

logger = logging.getLogger("greenhouse-mcp")

mcp = FastMCP(
    "greenhouse",
    instructions=(
        "Greenhouse ATS talent acquisition server. Use these tools to search, "
        "filter, and manage candidates and applications in Greenhouse. You can "
        "rediscover dormant talent, stack rank candidates for roles, craft "
        "personalized outreach, and trigger bulk actions. All changes sync "
        "back to Greenhouse in real time.\n\n"
        "IMPORTANT: You must call `greenhouse_authenticate` before using any "
        "other tools. After calling it, WAIT for the user to complete the "
        "browser login and then call `greenhouse_complete_auth` to finish. "
        "Do NOT call any other tools until authentication is confirmed."
    ),
)

# -- Auth state ----------------------------------------------------------------

okta = OktaOIDCHandler()
_authenticated: bool = False
_callback_task: asyncio.Task | None = None


def require_auth() -> None:
    """Gate function — call at the top of every tool that needs authentication."""
    if not _authenticated:
        raise RuntimeError(
            "Not authenticated. Use the `greenhouse_authenticate` tool first, "
            "then call `greenhouse_complete_auth` after the user logs in."
        )


async def _resolve_greenhouse_user(email: str) -> str:
    """Look up Greenhouse user by email and set the auth user ID."""
    global _authenticated

    user = await auth.lookup_greenhouse_user(email)
    greenhouse_user_id = str(user["id"])
    auth.set_user_id(greenhouse_user_id)
    _authenticated = True
    name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    logger.info("Authenticated as %s (%s) — Greenhouse user %s", name, email, greenhouse_user_id)
    return f"Authenticated as {name} ({email}). You can now use the Greenhouse tools."


async def _await_okta_callback() -> None:
    """Background task: wait for callback and capture claims silently."""
    try:
        await okta.wait_for_callback(timeout=300)
        logger.info("Okta callback captured (claims ready for complete_auth).")
    except OktaAuthError as e:
        logger.warning("Okta callback did not capture token: %s", e)
    except Exception as e:
        logger.error("Error waiting for callback: %s", e)


# -- Auth tools ----------------------------------------------------------------

@mcp.tool()
async def greenhouse_authenticate() -> str:
    """Start the Okta SSO authentication flow.

    Returns a URL for the user to visit in their browser. After the user
    has logged in via Okta, you MUST call `greenhouse_complete_auth` to
    finish authentication. Do NOT attempt to use any other tools until
    `greenhouse_complete_auth` confirms success.
    """
    global _callback_task

    auth_url = okta.get_authorization_url()
    await okta.start_callback_server()
    _callback_task = asyncio.create_task(_await_okta_callback())

    return (
        f"Please visit the following URL to authenticate:\n\n"
        f"{auth_url}\n\n"
        f"After logging in, tell me you're done and I will call "
        f"`greenhouse_complete_auth` to finish."
    )


@mcp.tool()
async def greenhouse_complete_auth(confirmation: str = "done") -> str:
    """Complete authentication after the user has logged in via Okta.

    Call this after the user confirms they have completed the browser login.
    The callback server will have already captured the token automatically.

    Args:
        confirmation: Any text from the user confirming they logged in.
    """
    if _authenticated:
        return "Already authenticated. You can use the Greenhouse tools."

    # Wait briefly for the background callback task to finish if still running
    if _callback_task and not _callback_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(_callback_task), timeout=10)
        except (asyncio.TimeoutError, Exception):
            pass

    # Check if callback captured claims
    if okta.id_token_claims is not None:
        email = okta.id_token_claims.get("email")
        if email:
            return await _resolve_greenhouse_user(email)

    return (
        "Authentication not yet received. Please make sure you completed "
        "the Okta login in your browser. If the page showed 'Authenticated!', "
        "try calling this tool again in a few seconds."
    )


# Import tools to register them with the server
import greenhouse_mcp.tools  # noqa: E402,F401
