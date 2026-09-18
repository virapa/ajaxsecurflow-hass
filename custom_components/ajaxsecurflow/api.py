"""HTTP client for the AjaxSecurFlow API."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from .const import API_PREFIX, REQUEST_TIMEOUT, STREAM_READ_TIMEOUT, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class AjaxSecurFlowError(Exception):
    """Base error."""


class AuthError(AjaxSecurFlowError):
    """401: token invalid or revoked."""


class PlanError(AjaxSecurFlowError):
    """403: feature not in the user's plan."""


class RateLimitError(AjaxSecurFlowError):
    """429: rate limited."""


class ApiError(AjaxSecurFlowError):
    """Any other transport or HTTP error."""


class SSEParser:
    """Incremental text/event-stream parser. Feed one line at a time; get an envelope on blank line."""

    def __init__(self) -> None:
        self._event: str | None = None
        self._data: list[str] = []

    def feed(self, line: str) -> dict[str, Any] | None:
        line = line.rstrip("\r\n")
        if line == "":
            return self._flush()
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value
        elif field == "data":
            self._data.append(value)
        return None

    def _flush(self) -> dict[str, Any] | None:
        event, data = self._event, self._data
        self._event, self._data = None, []
        if not data or event not in (None, "ajax_event"):
            return None
        try:
            parsed = json.loads("\n".join(data))
        except json.JSONDecodeError:
            _LOGGER.debug("Dropping non-JSON SSE payload")
            return None
        return parsed if isinstance(parsed, dict) else None


class AjaxSecurFlowClient:
    """Async client over Home Assistant's shared aiohttp session."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}{API_PREFIX}{path}"

    @staticmethod
    def _raise_for_status(resp: aiohttp.ClientResponse) -> None:
        if resp.status == 401:
            raise AuthError("Invalid or revoked token")
        if resp.status == 403:
            raise PlanError("Not available in your plan")
        if resp.status == 429:
            raise RateLimitError("Rate limit exceeded")
        if resp.status >= 400:
            raise ApiError(f"HTTP {resp.status}")

    async def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.request(
                method,
                self._url(path),
                headers=self._headers,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                self._raise_for_status(resp)
                return await resp.json()
        except aiohttp.ClientError as err:
            raise ApiError(str(err)) from err
        except TimeoutError as err:
            raise ApiError("Request timed out") from err

    async def get_me(self) -> dict[str, Any]:
        return await self._request("GET", "/auth/me")

    async def get_hubs(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/ajax/hubs")

    async def get_hub(self, hub_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/ajax/hubs/{hub_id}")

    async def get_devices(self, hub_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", f"/ajax/hubs/{hub_id}/devices")

    async def get_groups(self, hub_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", f"/ajax/hubs/{hub_id}/groups")

    async def get_rooms(self, hub_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", f"/ajax/hubs/{hub_id}/rooms")

    async def set_arm_state(self, hub_id: str, arm_state: int, group_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"armState": arm_state}
        if group_id:
            body["groupId"] = group_id
        return await self._request("POST", f"/ajax/hubs/{hub_id}/arm-state", body)

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield hybrid-envelope dicts from the SSE stream until the connection closes."""
        headers = {**self._headers, "Accept": "text/event-stream"}
        try:
            async with self._session.get(
                self._url("/ajax/events/stream"),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=None, sock_read=STREAM_READ_TIMEOUT),
            ) as resp:
                self._raise_for_status(resp)
                parser = SSEParser()
                async for raw_line in resp.content:
                    envelope = parser.feed(raw_line.decode("utf-8", "ignore"))
                    if envelope is not None:
                        yield envelope
        except aiohttp.ClientError as err:
            raise ApiError(str(err)) from err
        except TimeoutError as err:
            raise ApiError("Stream read timed out") from err
