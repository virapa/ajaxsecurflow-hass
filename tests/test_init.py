# tests/test_init.py
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.ajaxsecurflow.api import ApiError, AuthError
from custom_components.ajaxsecurflow.const import DOMAIN


async def test_setup_and_unload(hass, init_integration):
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    rt = entry.runtime_data
    assert rt.plan == "pro"
    assert rt.rooms == {"HUB1:1": "Salón"}
    assert "HUB1" in rt.coordinator.data

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_devices_registered_with_via_device(hass, init_integration):
    registry = dr.async_get(hass)
    hub = registry.async_get_device(identifiers={(DOMAIN, "HUB1")})
    door = registry.async_get_device(identifiers={(DOMAIN, "HUB1:D1")})
    assert hub is not None and hub.manufacturer == "Ajax Systems" and hub.model == "HUB_2_PLUS"
    assert door is not None and door.via_device_id == hub.id and door.model == "DoorProtect"


async def test_auth_error_on_setup_triggers_reauth(hass, mock_api, config_entry):
    mock_api.get_me.side_effect = AuthError()
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_api_error_on_setup_retries(hass, mock_api, config_entry):
    mock_api.get_me.side_effect = ApiError("down")
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_rooms_failure_is_not_fatal(hass, mock_api, config_entry):
    mock_api.get_rooms.side_effect = ApiError("rooms down")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.runtime_data.rooms == {}
