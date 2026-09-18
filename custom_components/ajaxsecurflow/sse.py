"""Background task that keeps an SSE connection open and folds events into the coordinator."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .api import AjaxSecurFlowClient, AuthError, PlanError
from .const import DOMAIN, EVENT_NAME, SSE_BACKOFF_MAX, SSE_BACKOFF_MIN
from .coordinator import AjaxSecurFlowCoordinator
from .events import apply_event

_LOGGER = logging.getLogger(__name__)


class SSEListener:
    """Consumes /ajax/events/stream with exponential backoff. Stops for good on 401/403."""

    def __init__(self, hass: HomeAssistant, coordinator: AjaxSecurFlowCoordinator, client: AjaxSecurFlowClient) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._client = client
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is None:
            self._task = self._hass.async_create_background_task(self._run(), name=f"{DOMAIN}_sse")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        delay = SSE_BACKOFF_MIN
        while True:
            try:
                async for envelope in self._client.stream_events():
                    delay = SSE_BACKOFF_MIN
                    self._handle(envelope)
                _LOGGER.debug("SSE stream closed by server; reconnecting")
            except asyncio.CancelledError:
                raise
            except PlanError:
                _LOGGER.info("Real-time stream not included in your plan; using polling only")
                return
            except AuthError:
                _LOGGER.warning("Integration token rejected by the stream; polling will trigger re-authentication")
                return
            except Exception as err:  # noqa: BLE001 - keep the loop alive on any transport error
                _LOGGER.debug("SSE connection error: %s", err)
            await asyncio.sleep(delay)
            delay = min(delay * 2, SSE_BACKOFF_MAX)

    def _handle(self, envelope: dict[str, Any]) -> None:
        data = self._coordinator.data
        if data is None:
            return
        if not apply_event(data, envelope):
            _LOGGER.debug("Event for unknown hub %s; scheduling full refresh", envelope.get("hub_id"))
            self._hass.async_create_task(self._coordinator.async_request_refresh())
            return
        self._coordinator.async_set_updated_data(data)
        self._hass.bus.async_fire(EVENT_NAME, envelope)
