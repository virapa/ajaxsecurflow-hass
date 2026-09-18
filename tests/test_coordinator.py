# tests/test_coordinator.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ajaxsecurflow.api import ApiError, AuthError, RateLimitError
from custom_components.ajaxsecurflow.const import CONF_BASE_URL, CONF_SCAN_INTERVAL, CONF_TOKEN, DOMAIN
from custom_components.ajaxsecurflow.coordinator import AjaxSecurFlowCoordinator

HUBS = [{"id": "HUB1", "name": "Casa", "role": "MASTER"}]
HUB = {"id": "HUB1", "state": "ARMED", "online": True, "groups_enabled": True}
DEVICES = [{"id": "D1", "name": "Puerta", "reed_closed": True}]
GROUPS = [{"id": "G1", "name": "Planta baja", "state": "ARMED"}]


def _client(**overrides):
    client = MagicMock()
    client.get_hubs = AsyncMock(return_value=HUBS)
    client.get_hub = AsyncMock(return_value=HUB)
    client.get_devices = AsyncMock(return_value=DEVICES)
    client.get_groups = AsyncMock(return_value=GROUPS)
    for name, value in overrides.items():
        setattr(client, name, value)
    return client


def _entry(hass, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BASE_URL: "https://api.test", CONF_TOKEN: "asf_x"}, options=options or {})
    entry.add_to_hass(hass)
    return entry


async def test_update_builds_hub_data(hass):
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client())
    data = await coordinator._async_update_data()
    hub = data["HUB1"]
    assert hub.hub["name"] == "Casa"          # merged from list
    assert hub.hub["state"] == "ARMED"        # from detail
    assert hub.devices["D1"]["reed_closed"] is True
    assert hub.groups["G1"]["name"] == "Planta baja"
    assert hub.triggered is False


async def test_scan_interval_from_options(hass):
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass, {CONF_SCAN_INTERVAL: 120}), _client())
    assert coordinator.update_interval.total_seconds() == 120


async def test_auth_error_raises_reauth(hass):
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client(get_hubs=AsyncMock(side_effect=AuthError())))
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.parametrize("exc", [RateLimitError(), ApiError("boom")])
async def test_transport_errors_raise_update_failed(hass, exc):
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client(get_hubs=AsyncMock(side_effect=exc)))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_triggered_persists_until_disarmed(hass):
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client())
    coordinator.data = await coordinator._async_update_data()
    coordinator.data["HUB1"].triggered = True

    data = await coordinator._async_update_data()
    assert data["HUB1"].triggered is True  # hub still ARMED

    coordinator.client.get_hub = AsyncMock(return_value={**HUB, "state": "DISARMED"})
    coordinator.data = data
    data = await coordinator._async_update_data()
    assert data["HUB1"].triggered is False


async def test_triggered_persists_in_night_mode(hass):
    """Night mode is an armed state for Ajax; a poll returning DISARMED_NIGHT_MODE_ON must not clear `triggered`."""
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client())
    coordinator.data = await coordinator._async_update_data()
    coordinator.data["HUB1"].triggered = True

    coordinator.client.get_hub = AsyncMock(return_value={**HUB, "state": "DISARMED_NIGHT_MODE_ON"})
    data = await coordinator._async_update_data()
    assert data["HUB1"].triggered is True

    coordinator.client.get_hub = AsyncMock(return_value={**HUB, "state": "DISARMED_NIGHT_MODE_OFF"})
    coordinator.data = data
    data = await coordinator._async_update_data()
    assert data["HUB1"].triggered is False


async def test_event_during_poll_is_replayed(hass):
    """An ARM event noted while the poll is in flight wins over the (stale) DISARMED detail the poll returned."""
    client = _client(get_hub=AsyncMock(return_value={**HUB, "state": "DISARMED"}))
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), client)
    arm = {"hub_id": "HUB1", "event_type": "SECURITY", "data": {"event": {"eventTag": "Arm", "sourceObjectType": "HUB", "sourceObjectId": "HUB1"}}}

    async def devices_then_event(hub_id):
        coordinator.note_event(arm)
        return DEVICES

    client.get_devices = AsyncMock(side_effect=devices_then_event)
    data = await coordinator._async_update_data()
    assert data["HUB1"].hub["state"] == "ARMED"
    assert data["HUB1"].last_event["tag"] == "Arm"

    # The replay buffer is consumed: a later poll with no events reflects the backend again.
    coordinator.data = data
    client.get_devices = AsyncMock(return_value=DEVICES)
    data = await coordinator._async_update_data()
    assert data["HUB1"].hub["state"] == "DISARMED"


async def test_malformed_device_row_is_skipped(hass):
    devices = [{"name": "sin id"}, {"id": None, "name": "id nulo"}, {"id": 7, "name": "numerico"}, *DEVICES]
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client(get_devices=AsyncMock(return_value=devices)))
    data = await coordinator._async_update_data()
    assert set(data["HUB1"].devices) == {"7", "D1"}
    assert data["HUB1"].devices["D1"]["name"] == "Puerta"


async def test_hub_detail_without_id_uses_summary_id(hass):
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client(get_hub=AsyncMock(return_value={"state": "ARMED"})))
    data = await coordinator._async_update_data()
    assert list(data) == ["HUB1"]
    assert data["HUB1"].hub["id"] == "HUB1"
    assert data["HUB1"].hub["state"] == "ARMED"


@pytest.mark.parametrize(
    "overrides",
    [
        {"get_hubs": AsyncMock(return_value=[{"name": "sin id"}])},   # KeyError
        {"get_devices": AsyncMock(return_value=None)},                # TypeError
        {"get_groups": AsyncMock(return_value=[None])},               # AttributeError/TypeError
    ],
)
async def test_malformed_payload_raises_update_failed(hass, overrides):
    coordinator = AjaxSecurFlowCoordinator(hass, _entry(hass), _client(**overrides))
    with pytest.raises(UpdateFailed, match="Malformed"):
        await coordinator._async_update_data()
