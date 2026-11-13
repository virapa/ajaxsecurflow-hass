"""AjaxSecurFlow integration for Home Assistant."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AjaxSecurFlowClient, AjaxSecurFlowError, AuthError
from .const import CONF_BASE_URL, CONF_TOKEN, PLANS_WITH_DEVICES
from .coordinator import AjaxSecurFlowCoordinator
from .entity import hub_device_fields
from .models import HubData
from .sse import SSEListener

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SENSOR]


@dataclass
class AjaxSecurFlowRuntimeData:
    client: AjaxSecurFlowClient
    coordinator: AjaxSecurFlowCoordinator
    listener: SSEListener
    plan: str
    rooms: dict[str, str]  # "<hub_id>:<room_id>" -> room name
    hub_device_ids: dict[str, str]  # hub_id -> device registry id


type AjaxSecurFlowConfigEntry = ConfigEntry[AjaxSecurFlowRuntimeData]


async def _load_room_names(client: AjaxSecurFlowClient, data: dict[str, HubData]) -> dict[str, str]:
    rooms: dict[str, str] = {}
    for hub_id in data:
        try:
            for room in await client.get_rooms(hub_id):
                rooms[f"{hub_id}:{room.get('id')}"] = str(room.get("roomName") or "")
        except AjaxSecurFlowError as err:
            _LOGGER.debug("Rooms unavailable for hub %s: %s", hub_id, err)
    return rooms


async def async_setup_entry(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry) -> bool:
    client = AjaxSecurFlowClient(async_get_clientsession(hass), entry.data[CONF_BASE_URL], entry.data[CONF_TOKEN])
    try:
        me = await client.get_me()
    except AuthError as err:
        raise ConfigEntryAuthFailed("Integration token rejected") from err
    except AjaxSecurFlowError as err:
        raise ConfigEntryNotReady(f"Cannot reach AjaxSecurFlow: {err}") from err

    plan = str(me.get("subscription_plan") or "free").lower()
    if plan not in PLANS_WITH_DEVICES:
        raise ConfigEntryError("The Free plan does not include device access; upgrade to Basic or higher")
    coordinator = AjaxSecurFlowCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    rooms = await _load_room_names(client, coordinator.data)

    # Hubs are registered first so Ajax devices can point at them through via_device_id.
    registry = dr.async_get(hass)
    hub_device_ids = {
        hub_id: registry.async_get_or_create(
            config_entry_id=entry.entry_id, **hub_device_fields(hub_id, hub_data.hub)
        ).id
        for hub_id, hub_data in coordinator.data.items()
    }

    listener = SSEListener(hass, coordinator, client)
    entry.runtime_data = AjaxSecurFlowRuntimeData(client, coordinator, listener, plan, rooms, hub_device_ids)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    listener.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry) -> bool:
    await entry.runtime_data.listener.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
