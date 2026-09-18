# tests/test_diagnostics.py
from custom_components.ajaxsecurflow.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_secrets(hass, init_integration):
    diag = await async_get_config_entry_diagnostics(hass, init_integration)
    assert diag["entry"]["token"] == "**REDACTED**"
    assert diag["entry"]["base_url"] == "**REDACTED**"
    assert diag["plan"] == "pro"
    assert diag["hubs"]["HUB1"]["hub"]["state"] == "DISARMED"
    assert "D1" in diag["hubs"]["HUB1"]["devices"]


async def test_diagnostics_redacts_network_details(hass, mock_api, config_entry):
    mock_api.get_hub.return_value = {
        **mock_api.get_hub.return_value,
        "ethernet": {"ip": "192.168.1.10", "mask": "255.255.255.0", "gate": "192.168.1.1", "dns": "1.1.1.1", "enabled": True},
        "timeZone": "Europe/Madrid",
    }
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    hub = diag["hubs"]["HUB1"]["hub"]
    assert hub["ethernet"] == {"ip": "**REDACTED**", "mask": "**REDACTED**", "gate": "**REDACTED**", "dns": "**REDACTED**", "enabled": True}
    assert hub["timeZone"] == "**REDACTED**"
    assert hub["state"] == "DISARMED"
    assert diag["entry"]["token"] == "**REDACTED**"
