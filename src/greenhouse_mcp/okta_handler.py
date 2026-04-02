"""
Okta OIDC handler for browser-based user authentication.

Uses Authorization Code + PKCE flow to authenticate users via Okta SSO.
After authentication, the user's email is extracted from the ID token
and used to look up their Greenhouse user ID for per-user API scoping.

Environment variables:
  OKTA_ISSUER       - Okta authorization server URL (e.g. https://cloudbeds.okta.com/oauth2/default)
  OKTA_CLIENT_ID    - OIDC app client ID from Okta
  OKTA_REDIRECT_URI - Must match the redirect URI registered in Okta
                      (e.g. http://localhost:8080/callback)
"""

import asyncio
import base64
import hashlib
import html
import os
import secrets
import urllib.parse
from http import HTTPStatus
from urllib.parse import urlparse, parse_qs

import httpx
import jwt
from dotenv import load_dotenv

load_dotenv()


class OktaAuthError(Exception):
    pass


_SUCCESS_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Greenhouse Auth</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
  <div style="text-align:center">
    <h1>Authenticated!</h1>
    <p>You can close this tab and return to Claude.</p>
  </div>
</body>
</html>
"""

_ERROR_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Greenhouse Auth Error</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
  <div style="text-align:center">
    <h1>Authentication Failed</h1>
    <p>{error}</p>
    <p>Please try again.</p>
  </div>
</body>
</html>
"""


class OktaOIDCHandler:
    """Okta OIDC Authorization Code + PKCE flow handler."""

    SCOPES = "openid email profile"

    def __init__(self):
        self.issuer = os.environ.get("OKTA_ISSUER", "")
        self.client_id = os.environ.get("OKTA_CLIENT_ID", "")
        self.redirect_uri = os.environ.get(
            "OKTA_REDIRECT_URI", "http://localhost:8080/callback"
        )

        # PKCE + state
        self._code_verifier: str | None = None
        self._code_challenge: str | None = None
        self._state: str | None = None

        # Callback server state
        self._id_token_claims: dict | None = None
        self._token_event: asyncio.Event | None = None
        self._server: asyncio.Server | None = None

    def _generate_pkce(self) -> None:
        """Generate PKCE code_verifier and code_challenge (S256)."""
        self._code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(self._code_verifier.encode("ascii")).digest()
        self._code_challenge = (
            base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        )

    def _generate_state(self) -> None:
        """Generate a random state parameter for CSRF protection."""
        self._state = secrets.token_urlsafe(32)

    def get_authorization_url(self) -> str:
        """Build the Okta OIDC authorization URL with PKCE."""
        if not self.issuer:
            raise OktaAuthError(
                "OKTA_ISSUER is not set. Add it to your .env file."
            )
        if not self.client_id:
            raise OktaAuthError(
                "OKTA_CLIENT_ID is not set. Add it to your .env file."
            )

        self._generate_pkce()
        self._generate_state()

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.SCOPES,
            "state": self._state,
            "code_challenge": self._code_challenge,
            "code_challenge_method": "S256",
        }
        base = f"{self.issuer.rstrip('/')}/v1/authorize"
        return f"{base}?{urllib.parse.urlencode(params)}"

    def extract_code(self, code_or_url: str) -> str:
        """Extract the authorization code from a redirect URL or bare code."""
        if code_or_url.startswith("http"):
            parsed = urlparse(code_or_url)
            qs = parse_qs(parsed.query)
            codes = qs.get("code", [])
            if not codes:
                raise OktaAuthError(
                    "Could not find 'code' parameter in the redirect URL."
                )
            return codes[0]
        return code_or_url

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens and return decoded ID token claims."""
        if not self._code_verifier:
            raise OktaAuthError("No PKCE verifier. Call get_authorization_url first.")

        token_url = f"{self.issuer.rstrip('/')}/v1/token"
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": self._code_verifier,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            raise OktaAuthError(
                f"Token exchange failed ({resp.status_code}). "
                "Check Okta app configuration and try again."
            )

        data = resp.json()
        id_token = data.get("id_token")
        if not id_token:
            raise OktaAuthError("Token exchange succeeded but no id_token in response.")

        # Decode without signature verification — token received directly
        # from Okta over TLS (per OIDC spec, this is acceptable).
        claims = jwt.decode(
            id_token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )

        if not claims.get("email"):
            raise OktaAuthError(
                "ID token does not contain an email claim. "
                "Ensure the Okta app includes the 'email' scope."
            )

        self._id_token_claims = claims
        return claims

    # -- Callback server -------------------------------------------------------

    @property
    def id_token_claims(self) -> dict | None:
        """ID token claims captured by the callback server, if any."""
        return self._id_token_claims

    async def start_callback_server(self) -> None:
        """Start a temporary HTTP server to capture the OAuth callback."""
        self._id_token_claims = None
        self._token_event = asyncio.Event()

        parsed = urlparse(self.redirect_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8080

        self._server = await asyncio.start_server(
            self._handle_connection, host, port
        )

    async def wait_for_callback(self, timeout: float = 300) -> dict:
        """Block until the callback server captures claims (or timeout)."""
        if self._token_event is None:
            raise OktaAuthError("Callback server not started.")
        try:
            await asyncio.wait_for(self._token_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            await self._stop_server()
            raise OktaAuthError("Timed out waiting for Okta callback.")
        if self._id_token_claims is None:
            raise OktaAuthError("Okta callback failed — no token received.")
        return self._id_token_claims

    async def _stop_server(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    _READ_TIMEOUT = 10  # seconds

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single HTTP connection on the callback port."""
        try:
            request_line = await asyncio.wait_for(
                reader.readline(), timeout=self._READ_TIMEOUT
            )
            # Read remaining headers
            while True:
                line = await asyncio.wait_for(
                    reader.readline(), timeout=self._READ_TIMEOUT
                )
                if line in (b"\r\n", b"\n", b""):
                    break

            parts = request_line.decode().split()
            if len(parts) < 2:
                self._send_response(writer, 400, "Bad request")
                return

            path = parts[1]
            parsed = urlparse(path)
            qs = parse_qs(parsed.query)
            codes = qs.get("code", [])

            if not codes:
                error_msg = qs.get(
                    "error_description", qs.get("error", ["Unknown error"])
                )[0]
                self._send_response(
                    writer, 400,
                    _ERROR_HTML.format(error=html.escape(error_msg)),
                    content_type="text/html",
                )
                return

            # Validate state parameter
            returned_state = qs.get("state", [None])[0]
            if returned_state != self._state:
                self._send_response(
                    writer, 400,
                    _ERROR_HTML.format(error="State mismatch — possible CSRF attack."),
                    content_type="text/html",
                )
                return

            # Exchange code for tokens
            try:
                self._id_token_claims = await self.exchange_code(codes[0])
                self._send_response(
                    writer, 200, _SUCCESS_HTML, content_type="text/html"
                )
            except OktaAuthError as e:
                self._send_response(
                    writer, 500,
                    _ERROR_HTML.format(error=html.escape(str(e))),
                    content_type="text/html",
                )
        finally:
            writer.close()
            await writer.wait_closed()
            if self._token_event is not None:
                self._token_event.set()
            await self._stop_server()

    @staticmethod
    def _send_response(
        writer: asyncio.StreamWriter,
        status: int,
        body: str,
        content_type: str = "text/plain",
    ) -> None:
        reason = HTTPStatus(status).phrase
        header = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body.encode())}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(header.encode() + body.encode())
