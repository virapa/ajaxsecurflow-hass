"""Diagnostics dump with secrets redacted."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AjaxSecurFlowConfigEntry
from .const import CONF_BASE_URL, CONF_TOKEN

TO_REDACT = {CONF_TOKEN, CONF_BASE_URL, "email", "login", "phone"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry) -> dict[str, Any]:
    rt = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "plan": rt.plan,
        "rooms": rt.rooms,
        "sse_running": rt.listener.running,
        "hubs": {hub_id: asdict(hub_data) for hub_id, hub_data in (rt.coordinator.data or {}).items()},
    }
