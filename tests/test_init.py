# tests/test_init.py
import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.ajaxsecurflow.api import AjaxSecurFlowClient, ApiError, AuthError
from custom_components.ajaxsecurflow.const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN


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


async def test_free_plan_setup_error(hass, mock_api, config_entry):
    """Free plan is a permanent condition: SETUP_ERROR, no retry loop and no reauth prompt."""
    mock_api.get_me.return_value = {"id": 1, "email": "user@example.com", "subscription_plan": "free"}
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []
    mock_api.get_hubs.assert_not_awaited()


async def test_unload_cancels_running_sse_task(hass, mock_api, config_entry):
    async def forever(self):
        await asyncio.Event().wait()
        yield  # pragma: no cover

    with patch.object(AjaxSecurFlowClient, "stream_events", forever):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        listener = config_entry.runtime_data.listener
        assert listener.running is True

        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
    assert listener.running is False
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_options_update_reloads_only_when_interval_changes(hass, init_integration):
    entry = init_integration
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        hass.config_entries.async_update_entry(entry, options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL})
        await hass.async_block_till_done()
        reload.assert_not_awaited()

        hass.config_entries.async_update_entry(entry, options={CONF_SCAN_INTERVAL: 120})
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
