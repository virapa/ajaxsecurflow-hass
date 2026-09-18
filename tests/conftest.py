"""Shared fixtures: a fully mocked API client and a configured entry."""
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ajaxsecurflow.api import AjaxSecurFlowClient, PlanError
from custom_components.ajaxsecurflow.const import CONF_BASE_URL, CONF_TOKEN, DOMAIN

ME = {"id": 1, "email": "user@example.com", "subscription_plan": "pro"}
HUBS = [{"id": "HUB1", "name": "Casa", "role": "MASTER"}]
HUB = {
    "id": "HUB1", "name": "Casa", "online": True, "state": "DISARMED", "hub_subtype": "HUB_2_PLUS",
    "groups_enabled": True, "tampered": False, "externallyPowered": True,
    "firmware": {"version": "2.20.1"}, "battery": {"chargeLevelPercentage": 100, "state": "OK"},
    "gsm": {"signalLevel": "STRONG"},
}
DEVICE_DOOR = {
    "id": "D1", "hubId": "HUB1", "name": "Puerta principal", "deviceType": "DoorProtect", "roomId": "1",
    "online": True, "battery_level": 88, "signal_level": "STRONG", "temperature": 21.5, "tampered": False,
    "malfunctions": [], "reed_closed": True, "extra_contact_aware": True, "extra_contact_closed": True,
}
DEVICE_MOTION = {
    "id": "D2", "hubId": "HUB1", "name": "Salón", "deviceType": "MotionProtect", "roomId": "1",
    "online": True, "battery_level": 100, "signal_level": "NORMAL", "motion_detected": False,
    "malfunctions": ["BATTERY_MALFUNCTION"],
}
DEVICES = [DEVICE_DOOR, DEVICE_MOTION]
GROUPS = [{"id": "G1", "hub_id": "HUB1", "name": "Planta baja", "state": "DISARMED"}]
ROOMS = [{"id": "1", "roomName": "Salón"}]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _no_stream(self):
    raise PlanError("no stream in tests")
    yield  # pragma: no cover


@pytest.fixture
def mock_api():
    """Patch every client method. `stream_events` ends immediately so no background task lingers."""
    mocks = SimpleNamespace(
        get_me=AsyncMock(return_value=ME),
        get_hubs=AsyncMock(return_value=HUBS),
        get_hub=AsyncMock(return_value=HUB),
        get_devices=AsyncMock(return_value=DEVICES),
        get_groups=AsyncMock(return_value=GROUPS),
        get_rooms=AsyncMock(return_value=ROOMS),
        set_arm_state=AsyncMock(return_value={"success": True}),
    )
    with ExitStack() as stack:
        for name, mock in vars(mocks).items():
            stack.enter_context(patch.object(AjaxSecurFlowClient, name, mock))
        stack.enter_context(patch.object(AjaxSecurFlowClient, "stream_events", _no_stream))
        yield mocks


@pytest.fixture
def config_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        data={CONF_BASE_URL: "https://api.test", CONF_TOKEN: "asf_test"},
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def init_integration(hass, mock_api, config_entry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
