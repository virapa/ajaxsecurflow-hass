"""Background task that keeps an SSE connection open and folds events into the coordinator."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from homeassistant.core import HomeAssistant

from .api import AjaxSecurFlowClient, AuthError, PlanError
from .const import DOMAIN, EVENT_NAME, SSE_BACKOFF_MAX, SSE_BACKOFF_MIN, SSE_STABLE_SECONDS
from .coordinator import AjaxSecurFlowCoordinator
from .events import apply_event

_LOGGER = logging.getLogger(__name__)

SEEN_EVENT_IDS = 200
WARN_EVERY_N_FAILURES = 5


class SSEListener:
    """Consumes /ajax/events/stream with exponential backoff. Stops for good on 401/403."""

    def __init__(self, hass: HomeAssistant, coordinator: AjaxSecurFlowCoordinator, client: AjaxSecurFlowClient) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._client = client
        self._task: asyncio.Task | None = None
        self._seen: deque[Any] = deque(maxlen=SEEN_EVENT_IDS)

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
        failures = 0
        while True:
            started = time.monotonic()
            try:
                async for envelope in self._client.stream_events():
                    delay = SSE_BACKOFF_MIN
                    failures = 0
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
                failures += 1
                if failures % WARN_EVERY_N_FAILURES == 0:
                    _LOGGER.warning("SSE connection failed %d times in a row (last error: %s); still retrying", failures, err)
                else:
                    _LOGGER.debug("SSE connection error: %s", err)
            if time.monotonic() - started >= SSE_STABLE_SECONDS:
                # The connection held for a while: this is not a flapping backend, restart the backoff.
                delay = SSE_BACKOFF_MIN
                failures = 0
            await asyncio.sleep(delay)
            delay = min(delay * 2, SSE_BACKOFF_MAX)

    def _handle(self, envelope: dict[str, Any]) -> None:
        data = self._coordinator.data
        if data is None:
            return
        event_id = (((envelope.get("data") or {}).get("event")) or {}).get("eventId")
        if event_id is not None:
            if event_id in self._seen:
                _LOGGER.debug("Ignoring duplicate event %s", event_id)
                return
            self._seen.append(event_id)
        if not apply_event(data, envelope):
            _LOGGER.debug("Event for unknown hub %s; scheduling full refresh", envelope.get("hub_id"))
            self._hass.async_create_task(self._coordinator.async_request_refresh())
            return
        # Keep the event so a poll that is already in flight can replay it over the fresh snapshot.
        self._coordinator.note_event(envelope)
        # Push the in-place change to entities without rescheduling the next poll
        # (async_set_updated_data would, starving polling under a steady event flow).
        self._coordinator.async_update_listeners()
        self._hass.bus.async_fire(EVENT_NAME, envelope)
