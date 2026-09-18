# tests/test_binary_sensor.py
from homeassistant.components.binary_sensor import DOMAIN as BS_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er

from custom_components.ajaxsecurflow.const import DOMAIN
from tests.conftest import DEVICE_MOTION


def _state(hass, unique_id):
    eid = er.async_get(hass).async_get_entity_id(BS_DOMAIN, DOMAIN, unique_id)
    return hass.states.get(eid) if eid else None


async def test_door_sensors(hass, init_integration):
    assert _state(hass, "HUB1_D1_opening").state == STATE_OFF          # reed_closed True → not open
    assert _state(hass, "HUB1_D1_extra_contact").state == STATE_OFF
    assert _state(hass, "HUB1_D1_connectivity").state == STATE_ON
    assert _state(hass, "HUB1_D1_tamper").state == STATE_OFF
    assert _state(hass, "HUB1_D1_problem").state == STATE_OFF
    assert _state(hass, "HUB1_D1_motion") is None                       # DoorProtect reports no motion field


async def test_motion_sensor_and_problem_attribute(hass, init_integration):
    assert _state(hass, "HUB1_D2_motion").state == STATE_OFF
    assert _state(hass, "HUB1_D2_opening") is None
    problem = _state(hass, "HUB1_D2_problem")
    assert problem.state == STATE_ON
    assert problem.attributes["malfunctions"] == ["BATTERY_MALFUNCTION"]


async def test_hub_sensors(hass, init_integration):
    assert _state(hass, "HUB1_connectivity").state == STATE_ON
    assert _state(hass, "HUB1_tamper").state == STATE_OFF
    assert _state(hass, "HUB1_power").state == STATE_ON


async def test_extra_contact_not_created_when_unaware(hass, mock_api, config_entry):
    devices = mock_api.get_devices.return_value
    mock_api.get_devices.return_value = [{**devices[0], "extra_contact_aware": False}, devices[1]]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "HUB1_D1_extra_contact") is None


async def test_state_follows_coordinator_update(hass, init_integration):
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["HUB1"].devices["D1"]["reed_closed"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    assert _state(hass, "HUB1_D1_opening").state == STATE_ON


async def test_device_removed_becomes_unavailable(hass, init_integration, mock_api):
    """A device that disappears from the backend goes unavailable; siblings keep reporting."""
    coordinator = init_integration.runtime_data.coordinator
    mock_api.get_devices.return_value = [DEVICE_MOTION]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "HUB1_D1_opening").state == STATE_UNAVAILABLE
    assert _state(hass, "HUB1_D1_problem").state == STATE_UNAVAILABLE
    assert _state(hass, "HUB1_D2_motion").state == STATE_OFF
