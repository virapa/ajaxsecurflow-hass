"""In-memory state shared by the coordinator, the SSE listener and the entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HubData:
    """Everything known about one hub. Dict payloads are the backend's JSON as-is."""

    hub: dict[str, Any]
    groups: dict[str, dict[str, Any]] = field(default_factory=dict)
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    triggered: bool = False
    last_event: dict[str, Any] | None = None
