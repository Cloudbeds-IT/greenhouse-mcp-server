import os
import time
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BASE_URL = "https://harvest.greenhouse.io/v3"
AUTH_URL = "https://auth.greenhouse.io/token"


class GreenhouseAuth:
    """OAuth client credentials flow for Greenhouse Harvest API v3.

    Supports per-user scoping via the `sub` claim. After Okta authentication,
    call set_user_id() to scope all subsequent API calls to that user's
    Greenhouse permissions.
    """

    def __init__(self):
        self.client_id = os.environ.get("GREENHOUSE_CLIENT_ID", "")
        self.client_secret = os.environ.get("GREENHOUSE_CLIENT_SECRET", "")
        self.user_id: str = ""
        self._access_token: str | None = None
        self._expires_at: float = 0
        # Service account token (no sub claim) for user lookups
        self._service_token: str | None = None
        self._service_token_expires_at: float = 0

    @property
    def is_user_authenticated(self) -> bool:
        """Whether a user has been identified and a scoped token can be issued."""
        return bool(self.user_id)

    def set_user_id(self, user_id: str) -> None:
        """Set the Greenhouse user ID for per-user scoping.
        Clears the cached token so the next request gets a user-scoped one."""
        self.user_id = user_id
        self._access_token = None
        self._expires_at = 0

    def clear_session(self) -> None:
        """Reset authentication state."""
        self.user_id = ""
        self._access_token = None
        self._expires_at = 0

    async def get_token(self) -> str:
        """Get a user-scoped access token (requires set_user_id first)."""
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        return await self._request_token()

    async def _get_service_token(self) -> str:
        """Get a service account token (no sub claim) for admin operations."""
        if self._service_token and time.time() < self._service_token_expires_at - 60:
            return self._service_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                AUTH_URL,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
            )
            response.raise_for_status()
            data = response.json()

        self._service_token = data["access_token"]
        self._service_token_expires_at = time.time() + data.get("expires_in", 3600)
        return self._service_token

    async def lookup_greenhouse_user(self, email: str) -> dict:
        """Look up a Greenhouse user by email using the service account.

        Returns the user dict with id, first_name, last_name, etc.
        Raises RuntimeError if the user is not found.
        """
        token = await self._get_service_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/users",
                params={"primary_email": email, "per_page": 1},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            users = response.json()

        if not users:
            raise RuntimeError(
                f"No Greenhouse user found with email '{email}'. "
                "Make sure your Okta email matches your Greenhouse account."
            )

        return users[0]

    async def _request_token(self) -> str:
        async with httpx.AsyncClient() as client:
            data = {"grant_type": "client_credentials"}
            if self.user_id:
                data["sub"] = self.user_id
            response = await client.post(
                AUTH_URL,
                auth=(self.client_id, self.client_secret),
                data=data,
            )
            response.raise_for_status()
            data = response.json()

        self._access_token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)
        return self._access_token


auth = GreenhouseAuth()
