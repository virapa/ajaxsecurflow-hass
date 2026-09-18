import pytest
from aioresponses import aioresponses
from yarl import URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.ajaxsecurflow.api import (
    AjaxSecurFlowClient, ApiError, AuthError, PlanError, RateLimitError, SSEParser,
)

BASE = "https://api.test"


def _client(hass):
    return AjaxSecurFlowClient(async_get_clientsession(hass), BASE, "asf_abc")


async def test_get_hubs_sends_bearer_and_user_agent(hass):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/ajax/hubs", payload=[{"id": "HUB1"}])
        hubs = await _client(hass).get_hubs()
        call = m.requests[("GET", URL(f"{BASE}/api/v1/ajax/hubs"))][0]
    assert hubs == [{"id": "HUB1"}]
    assert call.kwargs["headers"]["Authorization"] == "Bearer asf_abc"
    assert call.kwargs["headers"]["User-Agent"].startswith("ajaxsecurflow-hass/")


async def test_base_url_trailing_slash_is_normalized(hass):
    client = AjaxSecurFlowClient(async_get_clientsession(hass), BASE + "/", "asf_abc")
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/auth/me", payload={"email": "u@x.com"})
        assert (await client.get_me())["email"] == "u@x.com"


@pytest.mark.parametrize("status,exc", [(401, AuthError), (403, PlanError), (429, RateLimitError), (500, ApiError)])
async def test_status_mapping(hass, status, exc):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/ajax/hubs", status=status)
        with pytest.raises(exc):
            await _client(hass).get_hubs()


async def test_set_arm_state_body(hass):
    with aioresponses() as m:
        m.post(f"{BASE}/api/v1/ajax/hubs/HUB1/arm-state", payload={"success": True})
        await _client(hass).set_arm_state("HUB1", 1, "G1")
        call = m.requests[("POST", URL(f"{BASE}/api/v1/ajax/hubs/HUB1/arm-state"))][0]
    assert call.kwargs["json"] == {"armState": 1, "groupId": "G1"}


async def test_set_arm_state_without_group(hass):
    with aioresponses() as m:
        m.post(f"{BASE}/api/v1/ajax/hubs/HUB1/arm-state", payload={"success": True})
        await _client(hass).set_arm_state("HUB1", 0)
        call = m.requests[("POST", URL(f"{BASE}/api/v1/ajax/hubs/HUB1/arm-state"))][0]
    assert call.kwargs["json"] == {"armState": 0}


def test_sse_parser_yields_only_complete_ajax_events():
    p = SSEParser()
    assert p.feed(": connected to 2 hub channels\n") is None
    assert p.feed("event: ajax_event\n") is None
    assert p.feed('data: {"hub_id": "HUB1", "event_type": "ALARM"}\n') is None
    out = p.feed("\n")
    assert out == {"hub_id": "HUB1", "event_type": "ALARM"}


def test_sse_parser_ignores_pings_and_other_events():
    p = SSEParser()
    assert p.feed(": ping\n") is None
    assert p.feed("\n") is None
    p.feed("event: other\n")
    p.feed('data: {"x": 1}\n')
    assert p.feed("\n") is None


def test_sse_parser_data_without_event_name_is_accepted():
    p = SSEParser()
    p.feed('data: {"hub_id": "HUB1"}\n')
    assert p.feed("\n") == {"hub_id": "HUB1"}


def test_sse_parser_invalid_json_is_dropped():
    p = SSEParser()
    p.feed("event: ajax_event\n")
    p.feed("data: not-json\n")
    assert p.feed("\n") is None


async def test_stream_events_yields_envelopes(hass):
    body = (
        b": connected\n\n"
        b"event: ajax_event\n"
        b'data: {"hub_id": "HUB1", "event_type": "SECURITY"}\n\n'
        b": ping\n\n"
    )
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/ajax/events/stream", body=body)
        events = [e async for e in _client(hass).stream_events()]
    assert events == [{"hub_id": "HUB1", "event_type": "SECURITY"}]


async def test_stream_events_403_raises_plan_error(hass):
    with aioresponses() as m:
        m.get(f"{BASE}/api/v1/ajax/events/stream", status=403)
        with pytest.raises(PlanError):
            async for _ in _client(hass).stream_events():
                pass
