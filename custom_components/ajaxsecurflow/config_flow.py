"""Config, reauth and options flows."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AjaxSecurFlowClient, AjaxSecurFlowError, AuthError
from .const import (
    CONF_BASE_URL, CONF_SCAN_INTERVAL, CONF_TOKEN, DEFAULT_BASE_URL, DEFAULT_SCAN_INTERVAL,
    DOMAIN, MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL, PLANS_WITH_CONTROL, PLANS_WITH_DEVICES,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
    vol.Required(CONF_TOKEN): str,
})
STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): str})


async def _fetch_me(hass: HomeAssistant, base_url: str, token: str) -> dict[str, Any]:
    client = AjaxSecurFlowClient(async_get_clientsession(hass), base_url, token)
    return await client.get_me()


def _plan_of(me: dict[str, Any]) -> str:
    return str(me.get("subscription_plan") or "free").lower()


class AjaxSecurFlowConfigFlow(ConfigFlow, domain=DOMAIN):
    """Token-based setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].strip().rstrip("/")
            token = user_input[CONF_TOKEN].strip()
            try:
                me = await _fetch_me(self.hass, base_url, token)
            except AuthError:
                errors["base"] = "invalid_auth"
            except AjaxSecurFlowError:
                errors["base"] = "cannot_connect"
            else:
                plan = _plan_of(me)
                if plan not in PLANS_WITH_DEVICES:
                    errors["base"] = "plan_free"
                else:
                    email = str(me["email"])
                    await self.async_set_unique_id(email.lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=email,
                        data={CONF_BASE_URL: base_url, CONF_TOKEN: token},
                        description=None if plan in PLANS_WITH_CONTROL else "no_control",
                    )
        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                await _fetch_me(self.hass, entry.data[CONF_BASE_URL], token)
            except AuthError:
                errors["base"] = "invalid_auth"
            except AjaxSecurFlowError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(step_id="reauth_confirm", data_schema=STEP_REAUTH_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> AjaxSecurFlowOptionsFlow:
        return AjaxSecurFlowOptionsFlow()


class AjaxSecurFlowOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
