"""Binary sensors for Ajax devices and hubs. An entity exists only when its source field is present."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AjaxSecurFlowConfigEntry
from .coordinator import AjaxSecurFlowCoordinator
from .entity import AjaxSecurFlowDeviceEntity, AjaxSecurFlowHubEntity


@dataclass(frozen=True, kw_only=True)
class AjaxBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]
    exists_fn: Callable[[dict[str, Any]], bool]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _present(field: str) -> Callable[[dict[str, Any]], bool]:
    return lambda payload: payload.get(field) is not None


def _flag(field: str) -> Callable[[dict[str, Any]], bool | None]:
    return lambda payload: payload.get(field)


def _inverted(field: str) -> Callable[[dict[str, Any]], bool | None]:
    return lambda payload: None if payload.get(field) is None else not payload[field]


DEVICE_DESCRIPTIONS: tuple[AjaxBinarySensorDescription, ...] = (
    AjaxBinarySensorDescription(key="opening", translation_key="opening", device_class=BinarySensorDeviceClass.OPENING,
                                value_fn=_inverted("reed_closed"), exists_fn=_present("reed_closed")),
    AjaxBinarySensorDescription(key="extra_contact", translation_key="extra_contact", device_class=BinarySensorDeviceClass.OPENING,
                                value_fn=_inverted("extra_contact_closed"),
                                exists_fn=lambda d: d.get("extra_contact_aware") is True and d.get("extra_contact_closed") is not None),
    AjaxBinarySensorDescription(key="motion", translation_key="motion", device_class=BinarySensorDeviceClass.MOTION,
                                value_fn=_flag("motion_detected"), exists_fn=_present("motion_detected")),
    AjaxBinarySensorDescription(key="glass_break", translation_key="glass_break", device_class=BinarySensorDeviceClass.SOUND,
                                value_fn=_flag("glass_break_detected"), exists_fn=_present("glass_break_detected")),
    AjaxBinarySensorDescription(key="moisture", translation_key="moisture", device_class=BinarySensorDeviceClass.MOISTURE,
                                value_fn=_flag("leak_detected"), exists_fn=_present("leak_detected")),
    AjaxBinarySensorDescription(key="smoke", translation_key="smoke", device_class=BinarySensorDeviceClass.SMOKE,
                                value_fn=_flag("smoke_alarm_detected"), exists_fn=_present("smoke_alarm_detected")),
    AjaxBinarySensorDescription(key="connectivity", translation_key="connectivity", device_class=BinarySensorDeviceClass.CONNECTIVITY,
                                entity_category=EntityCategory.DIAGNOSTIC, value_fn=_flag("online"), exists_fn=_present("online")),
    AjaxBinarySensorDescription(key="tamper", translation_key="tamper", device_class=BinarySensorDeviceClass.TAMPER,
                                entity_category=EntityCategory.DIAGNOSTIC, value_fn=_flag("tampered"), exists_fn=_present("tampered")),
    AjaxBinarySensorDescription(key="problem", translation_key="problem", device_class=BinarySensorDeviceClass.PROBLEM,
                                entity_category=EntityCategory.DIAGNOSTIC,
                                value_fn=lambda d: bool(d.get("malfunctions")), exists_fn=lambda d: True,
                                attributes_fn=lambda d: {"malfunctions": list(d.get("malfunctions") or [])}),
)

HUB_DESCRIPTIONS: tuple[AjaxBinarySensorDescription, ...] = (
    AjaxBinarySensorDescription(key="connectivity", translation_key="connectivity", device_class=BinarySensorDeviceClass.CONNECTIVITY,
                                entity_category=EntityCategory.DIAGNOSTIC, value_fn=_flag("online"), exists_fn=_present("online")),
    AjaxBinarySensorDescription(key="tamper", translation_key="tamper", device_class=BinarySensorDeviceClass.TAMPER,
                                entity_category=EntityCategory.DIAGNOSTIC, value_fn=_flag("tampered"), exists_fn=_present("tampered")),
    AjaxBinarySensorDescription(key="power", translation_key="power", device_class=BinarySensorDeviceClass.POWER,
                                entity_category=EntityCategory.DIAGNOSTIC, value_fn=_flag("externallyPowered"), exists_fn=_present("externallyPowered")),
)


async def async_setup_entry(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    rt = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for hub_id, hub_data in rt.coordinator.data.items():
        entities.extend(AjaxHubBinarySensor(rt.coordinator, hub_id, desc) for desc in HUB_DESCRIPTIONS if desc.exists_fn(hub_data.hub))
        for device_id, device in hub_data.devices.items():
            entities.extend(
                AjaxDeviceBinarySensor(rt.coordinator, hub_id, device_id, rt.rooms, desc)
                for desc in DEVICE_DESCRIPTIONS if desc.exists_fn(device)
            )
    async_add_entities(entities)


class AjaxDeviceBinarySensor(AjaxSecurFlowDeviceEntity, BinarySensorEntity):
    entity_description: AjaxBinarySensorDescription

    def __init__(self, coordinator: AjaxSecurFlowCoordinator, hub_id: str, device_id: str, rooms: dict[str, str], description: AjaxBinarySensorDescription) -> None:
        super().__init__(coordinator, hub_id, device_id, rooms)
        self.entity_description = description
        self._attr_unique_id = f"{hub_id}_{device_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.device)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.device)


class AjaxHubBinarySensor(AjaxSecurFlowHubEntity, BinarySensorEntity):
    entity_description: AjaxBinarySensorDescription

    def __init__(self, coordinator: AjaxSecurFlowCoordinator, hub_id: str, description: AjaxBinarySensorDescription) -> None:
        super().__init__(coordinator, hub_id)
        self.entity_description = description
        self._attr_unique_id = f"{hub_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.hub_data.hub)
