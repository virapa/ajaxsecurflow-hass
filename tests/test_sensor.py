from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.helpers import entity_registry as er

from custom_components.ajaxsecurflow.const import DOMAIN


def _state(hass, unique_id):
    eid = er.async_get(hass).async_get_entity_id(SENSOR_DOMAIN, DOMAIN, unique_id)
    return hass.states.get(eid) if eid else None


async def test_device_sensors(hass, init_integration):
    assert _state(hass, "HUB1_D1_battery").state == "88"
    assert _state(hass, "HUB1_D1_signal_level").state == "strong"
    assert _state(hass, "HUB1_D1_temperature").state == "21.5"
    assert _state(hass, "HUB1_D1_humidity") is None
    assert _state(hass, "HUB1_D1_co2") is None
    assert _state(hass, "HUB1_D2_temperature") is None


async def test_hub_sensors(hass, init_integration):
    assert _state(hass, "HUB1_battery").state == "100"
    assert _state(hass, "HUB1_gsm_signal").state == "strong"
    assert _state(hass, "HUB1_firmware_version").state == "2.20.1"
    assert _state(hass, "HUB1_last_event").state == "unknown"


async def test_last_event_reflects_sse(hass, init_integration):
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["HUB1"].last_event = {"event_type": "ALARM", "tag": "MotionDetected", "timestamp": "2026-09-18T10:00:00+00:00", "description": "Movimiento", "severity": "critical"}
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    state = _state(hass, "HUB1_last_event")
    assert state.state == "ALARM"
    assert state.attributes["tag"] == "MotionDetected"
    assert state.attributes["timestamp"] == "2026-09-18T10:00:00+00:00"


async def test_unknown_signal_value_is_unknown(hass, mock_api, config_entry):
    devices = mock_api.get_devices.return_value
    mock_api.get_devices.return_value = [{**devices[0], "signal_level": "SOMETHING_NEW"}, devices[1]]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "HUB1_D1_signal_level").state == "unknown"
