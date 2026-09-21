# AjaxSecurFlow for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/virapa/ajaxsecurflow-hass/actions/workflows/validate.yml/badge.svg)](https://github.com/virapa/ajaxsecurflow-hass/actions/workflows/validate.yml)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-lightgrey.svg)](LICENSE)
[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/virapa)

Brings your Ajax Systems hubs and devices into Home Assistant through the [AjaxSecurFlow](https://www.ajaxsecurflow.com) API. Home Assistant never talks to Ajax directly and needs no Ajax API key.

## Requirements

- Home Assistant 2025.1 or newer.
- An [AjaxSecurFlow](https://www.ajaxsecurflow.com) account on the **Basic** plan or higher. **Pro** or **Premium** is required to arm/disarm.

## Installation (HACS)

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add `https://github.com/virapa/ajaxsecurflow-hass` with category **Integration**.
3. Install **AjaxSecurFlow** and restart Home Assistant.

## Setup

1. In the AjaxSecurFlow dashboard open **Perfil → Integraciones** and create a token. Copy it: it is shown only once.
2. Settings → Devices & services → **Add integration** → **AjaxSecurFlow**.
3. Paste the token. Leave the API URL as is unless you self-host the backend.

Options (⚙ on the integration card): polling interval, 30-600 s (default 60).

## What you get

| Platform | Entities |
|---|---|
| `alarm_control_panel` | one per hub; one per group when groups mode is enabled. States: disarmed, armed_away, armed_night, armed_custom_bypass (partial), triggered |
| `binary_sensor` | per device: opening, external contact, motion, glass break, leak, smoke, online, tamper, problem (with `malfunctions` attribute). Per hub: online, tamper, external power |
| `sensor` | per device: battery, signal, temperature, humidity, CO2. Per hub: battery, GSM signal, firmware, last event |

Entities are created only for the fields a device actually reports.

## Real-time events

Changes arrive within a second over Server-Sent Events; polling reconciles the full state on the configured interval. Every event also fires `ajaxsecurflow_event` on the Home Assistant bus with the backend's hybrid envelope:

```yaml
automation:
  - alias: Notify on Ajax alarm
    trigger:
      - platform: event
        event_type: ajaxsecurflow_event
        event_data:
          event_type: ALARM
    action:
      - service: notify.mobile_app_phone
        data:
          title: "{{ trigger.event.data.title }}"
          message: "{{ trigger.event.data.description }}"
```

Recognised `eventTag` values are listed in `custom_components/ajaxsecurflow/const.py`; open an issue with a diagnostics dump to add new ones.

## Troubleshooting

- **Re-authentication requested**: the token was revoked or expired. Create a new one and paste it.
- **Arming fails with "requires a Pro or Premium plan"**: upgrade the AjaxSecurFlow plan.
- **No real-time updates**: the Basic plan includes the stream; check the log for `Real-time stream not included`. Polling still works.
- Download diagnostics from the integration card before reporting an issue; tokens and emails are redacted.

## Development

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements_test.txt
python -m pytest tests -v
```

On Windows some Home Assistant dependencies have no prebuilt wheels; run the suite in Docker instead:

```bash
bash scripts/test.sh tests -v
```

## License

Proprietary. See `LICENSE`.
