import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.ajaxsecurflow.api import AuthError, PlanError
from custom_components.ajaxsecurflow.const import EVENT_NAME
from custom_components.ajaxsecurflow.models import HubData
from custom_components.ajaxsecurflow.sse import SSEListener

# Captured before any test patches asyncio.sleep, so _spin keeps yielding to the loop
# (and the patched mock only records the listener's own backoff awaits).
_real_sleep = asyncio.sleep


def _coordinator():
    coordinator = MagicMock()
    coordinator.data = {"HUB1": HubData(hub={"id": "HUB1", "state": "DISARMED"}, devices={"D1": {"id": "D1", "motion_detected": False}})}
    coordinator.async_set_updated_data = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _stream_of(*envelopes, then=None):
    async def gen():
        for env in envelopes:
            yield env
        if then is not None:
            raise then
        await asyncio.Event().wait()  # keep the connection "open"
    return gen


async def _spin(n=10):
    for _ in range(n):
        await _real_sleep(0)


async def test_event_updates_state_and_fires_bus_event(hass):
    coordinator = _coordinator()
    client = MagicMock()
    envelope = {"hub_id": "HUB1", "event_type": "ALARM", "data": {"event": {"eventTag": "MotionDetected", "sourceObjectId": "D1", "transition": "TRIGGERED"}}}
    client.stream_events = _stream_of(envelope)
    captured = async_capture_events(hass, EVENT_NAME)

    listener = SSEListener(hass, coordinator, client)
    listener.start()
    await _spin()

    assert coordinator.data["HUB1"].devices["D1"]["motion_detected"] is True
    assert coordinator.data["HUB1"].triggered is True
    coordinator.async_set_updated_data.assert_called_once_with(coordinator.data)
    assert len(captured) == 1
    assert captured[0].data["hub_id"] == "HUB1"
    await listener.stop()


async def test_unknown_hub_requests_refresh(hass):
    coordinator = _coordinator()
    client = MagicMock()
    client.stream_events = _stream_of({"hub_id": "NEW", "event_type": "SECURITY", "data": {}})

    listener = SSEListener(hass, coordinator, client)
    listener.start()
    await _spin()

    coordinator.async_request_refresh.assert_awaited_once()
    coordinator.async_set_updated_data.assert_not_called()
    await listener.stop()


async def test_plan_error_stops_listener_without_retry(hass):
    coordinator = _coordinator()
    client = MagicMock()
    client.stream_events = _stream_of(then=PlanError())
    with patch("custom_components.ajaxsecurflow.sse.asyncio.sleep", AsyncMock()) as sleep:
        listener = SSEListener(hass, coordinator, client)
        listener.start()
        await _spin()
        assert listener.running is False
        sleep.assert_not_awaited()


async def test_auth_error_stops_listener(hass):
    coordinator = _coordinator()
    client = MagicMock()
    client.stream_events = _stream_of(then=AuthError())
    listener = SSEListener(hass, coordinator, client)
    listener.start()
    await _spin()
    assert listener.running is False


async def test_transport_error_backs_off_exponentially(hass):
    coordinator = _coordinator()
    client = MagicMock()
    attempts = 0

    async def failing():
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise ConnectionError("down")
        await asyncio.Event().wait()
        yield  # pragma: no cover

    client.stream_events = failing
    with patch("custom_components.ajaxsecurflow.sse.asyncio.sleep", AsyncMock()) as sleep:
        listener = SSEListener(hass, coordinator, client)
        listener.start()
        await _spin(30)
        delays = [call.args[0] for call in sleep.await_args_list]
        assert delays[:3] == [5, 10, 20]
        await listener.stop()
