import time
import httpx
from greenhouse_mcp.auth import auth

BASE_URL = "https://harvest.greenhouse.io/v3"

# In-memory cache for expensive paginated data that rarely changes mid-session
_cache: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 300  # 5 minutes


def _get_cached(key: str) -> list | None:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return data
    return None


def _set_cached(key: str, data: list) -> None:
    _cache[key] = (time.time(), data)


class GreenhouseClient:
    """Async HTTP client for Greenhouse Harvest API v3."""

    async def _headers(self) -> dict:
        token = await auth.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def get(self, path: str, params: dict | None = None) -> dict | list:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{path}",
                params=params,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

    async def get_by_id(self, resource: str, resource_id: int) -> dict:
        """Get a single resource by ID using the v3 list+ids pattern."""
        results = await self.get(resource, params={"ids": str(resource_id), "per_page": 1})
        if not results:
            raise RuntimeError(f"No {resource.strip('/')} found with ID {resource_id}")
        return results[0]

    async def get_by_ids(self, resource: str, resource_ids: list[int]) -> list:
        """Get multiple resources by IDs in a single request."""
        if not resource_ids:
            return []
        ids_str = ",".join(str(rid) for rid in resource_ids)
        return await self.get(resource, params={"ids": ids_str, "per_page": len(resource_ids)})

    async def get_paginated(
        self, path: str, params: dict | None = None, max_pages: int = 10
    ) -> list:
        """Fetch all pages using cursor-based pagination."""
        headers = await self._headers()
        results = []
        url = f"{BASE_URL}{path}"
        current_params = params or {}
        page = 0

        async with httpx.AsyncClient() as client:
            while url and page < max_pages:
                response = await client.get(
                    url,
                    params=current_params if page == 0 else None,
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)

                url = self._parse_next_link(response.headers.get("Link", ""))
                page += 1

        return results

    async def get_paginated_cached(
        self, path: str, params: dict | None = None, max_pages: int = 10
    ) -> list:
        """Like get_paginated but with in-memory caching."""
        cache_key = f"{path}:{params}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached
        results = await self.get_paginated(path, params, max_pages)
        _set_cached(cache_key, results)
        return results

    async def post(self, path: str, json_data: dict | None = None) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}{path}",
                json=json_data,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def put(self, path: str, json_data: dict | None = None) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{BASE_URL}{path}",
                json=json_data,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def delete(self, path: str) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{BASE_URL}{path}",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None


greenhouse = GreenhouseClient()
