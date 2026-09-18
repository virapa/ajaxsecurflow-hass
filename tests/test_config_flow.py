# tests/test_config_flow.py
from unittest.mock import AsyncMock, patch

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ajaxsecurflow.api import AjaxSecurFlowClient, ApiError, AuthError
from custom_components.ajaxsecurflow.const import (
    CONF_BASE_URL, CONF_SCAN_INTERVAL, CONF_TOKEN, DEFAULT_BASE_URL, DOMAIN,
)

ME_PRO = {"id": 1, "email": "User@Example.com", "subscription_plan": "pro"}
USER_INPUT = {CONF_BASE_URL: "https://api.test/", CONF_TOKEN: "asf_abc"}


def _patch_me(result):
    return patch.object(AjaxSecurFlowClient, "get_me", AsyncMock(**result))


async def _start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_form_defaults_base_url(hass):
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema_defaults = {
        k.schema: k.default()
        for k in result["data_schema"].schema
        if isinstance(k, vol.Marker) and k.default is not vol.UNDEFINED
    }
    assert schema_defaults[CONF_BASE_URL] == DEFAULT_BASE_URL


async def test_user_flow_creates_entry(hass):
    result = await _start(hass)
    with _patch_me({"return_value": ME_PRO}), patch("custom_components.ajaxsecurflow.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "User@Example.com"
    assert result["data"] == {CONF_BASE_URL: "https://api.test", CONF_TOKEN: "asf_abc"}
    assert result["result"].unique_id == "user@example.com"


async def test_basic_plan_creates_entry_with_no_control_notice(hass):
    result = await _start(hass)
    with _patch_me({"return_value": {**ME_PRO, "subscription_plan": "basic"}}), patch("custom_components.ajaxsecurflow.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["description"] == "no_control"


async def test_free_plan_shows_error(hass):
    result = await _start(hass)
    with _patch_me({"return_value": {**ME_PRO, "subscription_plan": "free"}}):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "plan_free"}


async def test_invalid_auth(hass):
    result = await _start(hass)
    with _patch_me({"side_effect": AuthError()}):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass):
    result = await _start(hass)
    with _patch_me({"side_effect": ApiError("down")}):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_account_aborts(hass):
    MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="user@example.com").add_to_hass(hass)
    result = await _start(hass)
    with _patch_me({"return_value": ME_PRO}):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_token(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BASE_URL: "https://api.test", CONF_TOKEN: "asf_old"}, unique_id="user@example.com")
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with _patch_me({"return_value": ME_PRO}), patch("custom_components.ajaxsecurflow.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: "asf_new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "asf_new"


async def test_options_flow_sets_scan_interval(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BASE_URL: "https://api.test", CONF_TOKEN: "asf_x"}, unique_id="u")
    entry.add_to_hass(hass)
    with patch("custom_components.ajaxsecurflow.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 120})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 120
