# tests/test_alarm_control_panel.py
import pytest
from homeassistant.components.alarm_control_panel import (
    DOMAIN as ALARM_DOMAIN, AlarmControlPanelEntityFeature, AlarmControlPanelState,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.ajaxsecurflow.alarm_control_panel import map_state
from custom_components.ajaxsecurflow.api import PlanError
from custom_components.ajaxsecurflow.const import DOMAIN

from .conftest import ME


@pytest.mark.parametrize("raw,triggered,expected", [
    ("DISARMED", False, AlarmControlPanelState.DISARMED),
    ("ARMED", False, AlarmControlPanelState.ARMED_AWAY),
    ("NIGHT_MODE", False, AlarmControlPanelState.ARMED_NIGHT),
    ("ARMED_NIGHT_MODE_ON", False, AlarmControlPanelState.ARMED_NIGHT),
    ("ARMED_NIGHT_MODE_OFF", False, AlarmControlPanelState.ARMED_AWAY),
    ("DISARMED_NIGHT_MODE_ON", False, AlarmControlPanelState.ARMED_NIGHT),
    ("DISARMED_NIGHT_MODE_OFF", False, AlarmControlPanelState.DISARMED),
    ("PARTIALLY_ARMED_NIGHT_MODE_OFF", False, AlarmControlPanelState.ARMED_CUSTOM_BYPASS),
    ("ARMED", True, AlarmControlPanelState.TRIGGERED),
    (None, False, None),
    ("WEIRD", False, None),
])
def test_map_state(raw, triggered, expected):
    assert map_state(raw, triggered) == expected


def _eid(hass, unique_id):
    return er.async_get(hass).async_get_entity_id(ALARM_DOMAIN, DOMAIN, unique_id)


async def test_hub_and_group_panels_created(hass, init_integration):
    hub_eid = _eid(hass, "HUB1_panel")
    group_eid = _eid(hass, "HUB1_G1_panel")
    assert hub_eid and group_eid
    assert hass.states.get(hub_eid).state == AlarmControlPanelState.DISARMED
    assert hass.states.get(group_eid).state == AlarmControlPanelState.DISARMED
    features = hass.states.get(hub_eid).attributes["supported_features"]
    assert features == AlarmControlPanelEntityFeature.ARM_AWAY | AlarmControlPanelEntityFeature.ARM_NIGHT


async def test_no_group_panels_when_groups_disabled(hass, mock_api, config_entry):
    mock_api.get_hub.return_value = {**mock_api.get_hub.return_value, "groups_enabled": False}
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _eid(hass, "HUB1_panel")
    assert _eid(hass, "HUB1_G1_panel") is None


async def test_arm_away_sends_command(hass, init_integration, mock_api):
    await hass.services.async_call(ALARM_DOMAIN, "alarm_arm_away", {"entity_id": _eid(hass, "HUB1_panel")}, blocking=True)
    mock_api.set_arm_state.assert_awaited_once_with("HUB1", 1, None)


async def test_group_disarm_sends_group_id(hass, init_integration, mock_api):
    await hass.services.async_call(ALARM_DOMAIN, "alarm_disarm", {"entity_id": _eid(hass, "HUB1_G1_panel")}, blocking=True)
    mock_api.set_arm_state.assert_awaited_once_with("HUB1", 0, "G1")


async def test_arm_night_sends_command(hass, init_integration, mock_api):
    await hass.services.async_call(ALARM_DOMAIN, "alarm_arm_night", {"entity_id": _eid(hass, "HUB1_panel")}, blocking=True)
    mock_api.set_arm_state.assert_awaited_once_with("HUB1", 2, None)


async def test_plan_error_raises_translated_error(hass, init_integration, mock_api):
    mock_api.set_arm_state.side_effect = PlanError()
    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(ALARM_DOMAIN, "alarm_arm_away", {"entity_id": _eid(hass, "HUB1_panel")}, blocking=True)
    assert excinfo.value.translation_key == "plan_required"


async def test_basic_plan_has_no_control_features(hass, mock_api, config_entry):
    mock_api.get_me.return_value = {**ME, "subscription_plan": "basic"}
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(_eid(hass, "HUB1_panel")).attributes["supported_features"] == 0
