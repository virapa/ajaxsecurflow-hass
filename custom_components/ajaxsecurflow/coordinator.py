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
from .models import HubData

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> dict[str, HubData]:
        try:
            hubs = await self.client.get_hubs()
            loaded = await asyncio.gather(*(self._load_hub(summary) for summary in hubs))
        except AuthError as err:
            raise ConfigEntryAuthFailed("Integration token rejected") from err
        except (RateLimitError, ApiError, PlanError) as err:
            raise UpdateFailed(f"AjaxSecurFlow API error: {err}") from err

        previous = self.data or {}
        data: dict[str, HubData] = {}
        for hub_data in loaded:
            hub_id = hub_data.hub["id"]
            prev = previous.get(hub_id)
            if prev is not None:
                hub_data.last_event = prev.last_event
                still_armed = not str(hub_data.hub.get("state") or "").upper().startswith("DISARMED")
                hub_data.triggered = prev.triggered and still_armed
            data[hub_id] = hub_data
        return data

    async def _load_hub(self, summary: dict[str, Any]) -> HubData:
        hub_id = str(summary["id"])
        detail, devices, groups = await asyncio.gather(
            self.client.get_hub(hub_id),
            self.client.get_devices(hub_id),
            self.client.get_groups(hub_id),
        )
        return HubData(
            hub={**summary, **detail},
            groups={str(g["id"]): g for g in groups},
            devices={str(d["id"]): d for d in devices},
        )
