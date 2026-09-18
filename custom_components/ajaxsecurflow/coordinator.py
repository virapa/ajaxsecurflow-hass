"""Polling coordinator: hubs → (hub detail, devices, groups) per hub."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AjaxSecurFlowClient, ApiError, AuthError, PlanError, RateLimitError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .events import apply_event, hub_is_armed
from .models import HubData

_LOGGER = logging.getLogger(__name__)


def _by_id(rows: list[dict[str, Any]], kind: str, hub_id: str) -> dict[str, dict[str, Any]]:
    """Key rows by their stringified id, dropping rows that carry none."""
    keyed: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row.get("id")
        if row_id is None:
            _LOGGER.debug("Skipping %s without id on hub %s: %s", kind, hub_id, row)
            continue
        keyed[str(row_id)] = row
    return keyed


class AjaxSecurFlowCoordinator(DataUpdateCoordinator[dict[str, HubData]]):
    """Fetches the full state of every hub on a fixed interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: AjaxSecurFlowClient) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self._events_since_poll: list[dict[str, Any]] = []

    def note_event(self, envelope: dict[str, Any]) -> None:
        """Remember an SSE event so a poll in flight can replay it over the snapshot it fetched."""
        self._events_since_poll.append(envelope)

    async def _async_update_data(self) -> dict[str, HubData]:
        self._events_since_poll = []
        try:
            hubs = await self.client.get_hubs()
            loaded = await asyncio.gather(*(self._load_hub(summary) for summary in hubs))

            previous = self.data or {}
            data: dict[str, HubData] = {}
            for hub_data in loaded:
                hub_id = hub_data.hub["id"]
                prev = previous.get(hub_id)
                if prev is not None:
                    hub_data.last_event = prev.last_event
                    hub_data.triggered = prev.triggered and hub_is_armed(hub_data.hub.get("state"))
                data[hub_id] = hub_data
        except AuthError as err:
            raise ConfigEntryAuthFailed("Integration token rejected") from err
        except (RateLimitError, ApiError, PlanError) as err:
            raise UpdateFailed(f"AjaxSecurFlow API error: {err}") from err
        except (KeyError, TypeError, AttributeError) as err:
            raise UpdateFailed(f"Malformed AjaxSecurFlow payload: {err!r}") from err

        # Events that arrived while the requests above were in flight are newer than the snapshot.
        for envelope in self._events_since_poll:
            apply_event(data, envelope)
        self._events_since_poll = []
        return data

    async def _load_hub(self, summary: dict[str, Any]) -> HubData:
        hub_id = str(summary["id"])
        detail, devices, groups = await asyncio.gather(
            self.client.get_hub(hub_id),
            self.client.get_devices(hub_id),
            self.client.get_groups(hub_id),
        )
        hub = {**summary, **detail}
        hub["id"] = hub_id
        return HubData(
            hub=hub,
            groups=_by_id(groups, "group", hub_id),
            devices=_by_id(devices, "device", hub_id),
        )
