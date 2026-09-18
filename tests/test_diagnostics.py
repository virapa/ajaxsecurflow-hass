# tests/test_diagnostics.py
from custom_components.ajaxsecurflow.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_secrets(hass, init_integration):
    diag = await async_get_config_entry_diagnostics(hass, init_integration)
    assert diag["entry"]["token"] == "**REDACTED**"
    assert diag["entry"]["base_url"] == "**REDACTED**"
    assert diag["plan"] == "pro"
    assert diag["hubs"]["HUB1"]["hub"]["state"] == "DISARMED"
    assert "D1" in diag["hubs"]["HUB1"]["devices"]
