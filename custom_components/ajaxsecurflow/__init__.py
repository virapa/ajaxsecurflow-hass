"""AjaxSecurFlow integration for Home Assistant."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AjaxSecurFlowClient, AjaxSecurFlowError, AuthError
from .const import CONF_BASE_URL, CONF_TOKEN
from .coordinator import AjaxSecurFlowCoordinator
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
    coordinator = AjaxSecurFlowCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    rooms = await _load_room_names(client, coordinator.data)

    listener = SSEListener(hass, coordinator, client)
    entry.runtime_data = AjaxSecurFlowRuntimeData(client, coordinator, listener, plan, rooms)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    listener.start()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry) -> bool:
    await entry.runtime_data.listener.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
