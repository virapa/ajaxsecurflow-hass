"""Pure functions that fold an SSE hybrid envelope into HubData. No I/O."""
from __future__ import annotations

from typing import Any

from .const import (
    ARM_TAGS, DISARM_TAGS, EXT_CONTACT_TAGS, GLASS_TAGS, LEAK_TAGS, MOTION_TAGS,
    NIGHT_OFF_TAGS, NIGHT_ON_TAGS, OFFLINE_TAGS, OPENING_TAGS, SMOKE_TAGS,
)
from .models import HubData


def hub_is_armed(state: str | None) -> bool:
    """Whether an Ajax hub state string counts as armed (night mode included).

    ARMED*, PARTIALLY_ARMED*, NIGHT_MODE and *_NIGHT_MODE_ON are armed; DISARMED and
    DISARMED_NIGHT_MODE_OFF are not.
    """
    if not state:
        return False
    upper = state.upper()
    return (
        upper.startswith("ARMED")
        or upper.startswith("PARTIALLY_ARMED")
        or upper == "NIGHT_MODE"
        or upper.endswith("NIGHT_MODE_ON")
    )


def _arming_state(tag: str, event_type: str) -> str | None:
    if tag in ARM_TAGS or event_type in ("ARM", "ARMED"):
        return "ARMED"
    if tag in DISARM_TAGS or event_type in ("DISARM", "DISARMED"):
        return "DISARMED"
    if tag in NIGHT_ON_TAGS:
        return "NIGHT_MODE"
    if tag in NIGHT_OFF_TAGS:
        return "DISARMED"
    return None


def _apply_device(device: dict[str, Any], tag: str, raw_tag: str, event_type: str, recovered: bool) -> None:
    if tag in EXT_CONTACT_TAGS:
        device["extra_contact_closed"] = recovered
    elif tag in OPENING_TAGS:
        device["reed_closed"] = recovered
    elif tag in MOTION_TAGS:
        device["motion_detected"] = not recovered
    elif tag in GLASS_TAGS:
        device["glass_break_detected"] = not recovered
    elif tag in LEAK_TAGS:
        device["leak_detected"] = not recovered
    elif tag in SMOKE_TAGS:
        device["smoke_alarm_detected"] = not recovered
    elif "tamper" in tag:
        device["tampered"] = not recovered
    elif tag in OFFLINE_TAGS:
        device["online"] = recovered
    elif event_type == "MALFUNCTION" and raw_tag:
        malfunctions = list(device.get("malfunctions") or [])
        if raw_tag not in malfunctions:
            malfunctions.append(raw_tag)
        device["malfunctions"] = malfunctions
    elif event_type == "FUNCTION_RECOVERED" and raw_tag:
        device["malfunctions"] = [m for m in (device.get("malfunctions") or []) if m != raw_tag]


def apply_event(data: dict[str, HubData], envelope: dict[str, Any]) -> bool:
    """Mutate `data` with one envelope. Returns False when the hub is unknown (caller should refresh)."""
    hub_id = str(envelope.get("hub_id") or "")
    hub_data = data.get(hub_id)
    if hub_data is None:
        return False

    event = ((envelope.get("data") or {}).get("event")) or {}
    event_type = str(envelope.get("event_type") or "").upper()
    raw_tag = str(event.get("eventTag") or "")
    tag = raw_tag.lower()
    recovered = str(event.get("transition") or "").upper() == "RECOVERED"
    source_id = str(event.get("sourceObjectId") or "")
    source_type = str(event.get("sourceObjectType") or "").upper()

    hub_data.last_event = {
        "event_type": event_type,
        "tag": raw_tag,
        "timestamp": envelope.get("timestamp"),
        "description": envelope.get("description"),
        "severity": envelope.get("severity"),
    }

    new_state = _arming_state(tag, event_type)
    if new_state is not None:
        if source_type == "GROUP":
            # A group change never touches the hub: the hub may still be armed (and triggered).
            group = hub_data.groups.get(source_id)
            if group is not None:
                group["state"] = new_state
            return True
        hub_data.hub["state"] = new_state
        if new_state == "DISARMED":
            hub_data.triggered = False
        return True

    if event_type == "ALARM":
        hub_data.triggered = True

    device = hub_data.devices.get(source_id)
    if device is not None:
        _apply_device(device, tag, raw_tag, event_type, recovered)
    return True
