"""Base entities carrying device_info for hubs and Ajax devices."""
from __future__ import annotations

import inspect
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo, DeviceRegistry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AjaxSecurFlowCoordinator
from .models import HubData

MANUFACTURER = "Ajax Systems"

# HA 2026.9 replaced DeviceInfo.via_device (identifier tuple, removed in 2027.8) with
# via_device_id (device registry id). Older cores only know via_device.
SUPPORTS_VIA_DEVICE_ID: bool = "via_device_id" in inspect.signature(DeviceRegistry.async_get_or_create).parameters


def hub_device_fields(hub_id: str, hub: dict[str, Any]) -> dict[str, Any]:
    """Device registry fields of a hub, shared by its entities and the up-front registration."""
    return {
        "identifiers": {(DOMAIN, hub_id)},
        "name": hub.get("name") or f"Hub {hub_id}",
        "manufacturer": MANUFACTURER,
        "model": hub.get("hub_subtype") or "Hub",
        "sw_version": (hub.get("firmware") or {}).get("version"),
    }


class AjaxSecurFlowHubEntity(CoordinatorEntity[AjaxSecurFlowCoordinator]):
    """Entity attached to a hub device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AjaxSecurFlowCoordinator, hub_id: str) -> None:
        super().__init__(coordinator)
        self.hub_id = hub_id
        self._attr_device_info = DeviceInfo(**hub_device_fields(hub_id, self.hub_data.hub))

    @property
    def hub_data(self) -> HubData:
        return self.coordinator.data[self.hub_id]

    @property
    def available(self) -> bool:
        return super().available and self.hub_id in (self.coordinator.data or {})


class AjaxSecurFlowDeviceEntity(AjaxSecurFlowHubEntity):
    """Entity attached to an Ajax device (child of the hub device)."""

    def __init__(
        self, coordinator: AjaxSecurFlowCoordinator, hub_id: str, device_id: str,
        rooms: dict[str, str], hub_device_ids: dict[str, str],
    ) -> None:
        super().__init__(coordinator, hub_id)
        self.device_id = device_id
        device = self.device
        via: dict[str, Any] = (
            {"via_device_id": hub_device_ids[hub_id]} if SUPPORTS_VIA_DEVICE_ID else {"via_device": (DOMAIN, hub_id)}
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{hub_id}:{device_id}")},
            name=device.get("name") or device_id,
            manufacturer=MANUFACTURER,
            model=device.get("deviceType"),
            suggested_area=rooms.get(f"{hub_id}:{device.get('roomId')}"),
            **via,
        )

    @property
    def device(self) -> dict[str, Any]:
        return self.hub_data.devices[self.device_id]

    @property
    def available(self) -> bool:
        return super().available and self.device_id in self.hub_data.devices
