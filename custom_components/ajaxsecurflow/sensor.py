"""Sensors for Ajax devices and hubs."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION, PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AjaxSecurFlowConfigEntry
from .const import SIGNAL_LEVELS
from .coordinator import AjaxSecurFlowCoordinator
from .entity import AjaxSecurFlowDeviceEntity, AjaxSecurFlowHubEntity
from .models import HubData

SIGNAL_OPTIONS = [level.lower() for level in SIGNAL_LEVELS]


@dataclass(frozen=True, kw_only=True)
class AjaxSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Any], Any]
    exists_fn: Callable[[Any], bool]
    attributes_fn: Callable[[Any], dict[str, Any]] | None = None


def _get(field: str) -> Callable[[dict[str, Any]], Any]:
    return lambda payload: payload.get(field)


def _present(field: str) -> Callable[[dict[str, Any]], bool]:
    return lambda payload: payload.get(field) is not None


def _signal(raw: Any) -> str | None:
    value = str(raw or "").lower()
    return value if value in SIGNAL_OPTIONS else None


DEVICE_DESCRIPTIONS: tuple[AjaxSensorDescription, ...] = (
    AjaxSensorDescription(key="battery", translation_key="battery", device_class=SensorDeviceClass.BATTERY,
                          native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
                          entity_category=EntityCategory.DIAGNOSTIC, value_fn=_get("battery_level"), exists_fn=_present("battery_level")),
    AjaxSensorDescription(key="signal_level", translation_key="signal_level", device_class=SensorDeviceClass.ENUM,
                          options=SIGNAL_OPTIONS, entity_category=EntityCategory.DIAGNOSTIC,
                          value_fn=lambda d: _signal(d.get("signal_level")), exists_fn=_present("signal_level")),
    AjaxSensorDescription(key="temperature", translation_key="temperature", device_class=SensorDeviceClass.TEMPERATURE,
                          native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT,
                          value_fn=_get("temperature"), exists_fn=_present("temperature")),
    AjaxSensorDescription(key="humidity", translation_key="humidity", device_class=SensorDeviceClass.HUMIDITY,
                          native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
                          value_fn=_get("humidity"), exists_fn=_present("humidity")),
    AjaxSensorDescription(key="co2", translation_key="co2", device_class=SensorDeviceClass.CO2,
                          native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION, state_class=SensorStateClass.MEASUREMENT,
                          value_fn=_get("co2"), exists_fn=_present("co2")),
)

HUB_DESCRIPTIONS: tuple[AjaxSensorDescription, ...] = (
    AjaxSensorDescription(key="battery", translation_key="battery", device_class=SensorDeviceClass.BATTERY,
                          native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
                          entity_category=EntityCategory.DIAGNOSTIC,
                          value_fn=lambda hd: (hd.hub.get("battery") or {}).get("chargeLevelPercentage"),
                          exists_fn=lambda hd: (hd.hub.get("battery") or {}).get("chargeLevelPercentage") is not None),
    AjaxSensorDescription(key="gsm_signal", translation_key="gsm_signal", device_class=SensorDeviceClass.ENUM,
                          options=SIGNAL_OPTIONS, entity_category=EntityCategory.DIAGNOSTIC,
                          value_fn=lambda hd: _signal((hd.hub.get("gsm") or {}).get("signalLevel")),
                          exists_fn=lambda hd: (hd.hub.get("gsm") or {}).get("signalLevel") is not None),
    AjaxSensorDescription(key="firmware_version", translation_key="firmware_version", entity_category=EntityCategory.DIAGNOSTIC,
                          value_fn=lambda hd: (hd.hub.get("firmware") or {}).get("version"),
                          exists_fn=lambda hd: (hd.hub.get("firmware") or {}).get("version") is not None),
    AjaxSensorDescription(key="last_event", translation_key="last_event",
                          value_fn=lambda hd: (hd.last_event or {}).get("event_type"),
                          exists_fn=lambda hd: True,
                          attributes_fn=lambda hd: {k: (hd.last_event or {}).get(k) for k in ("tag", "timestamp", "description", "severity")}),
)


async def async_setup_entry(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    rt = entry.runtime_data
    entities: list[SensorEntity] = []
    for hub_id, hub_data in rt.coordinator.data.items():
        entities.extend(AjaxHubSensor(rt.coordinator, hub_id, desc) for desc in HUB_DESCRIPTIONS if desc.exists_fn(hub_data))
        for device_id, device in hub_data.devices.items():
            entities.extend(
                AjaxDeviceSensor(rt.coordinator, hub_id, device_id, rt.rooms, desc)
                for desc in DEVICE_DESCRIPTIONS if desc.exists_fn(device)
            )
    async_add_entities(entities)


class AjaxDeviceSensor(AjaxSecurFlowDeviceEntity, SensorEntity):
    entity_description: AjaxSensorDescription

    def __init__(self, coordinator: AjaxSecurFlowCoordinator, hub_id: str, device_id: str, rooms: dict[str, str], description: AjaxSensorDescription) -> None:
        super().__init__(coordinator, hub_id, device_id, rooms)
        self.entity_description = description
        self._attr_unique_id = f"{hub_id}_{device_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device)


class AjaxHubSensor(AjaxSecurFlowHubEntity, SensorEntity):
    entity_description: AjaxSensorDescription

    def __init__(self, coordinator: AjaxSecurFlowCoordinator, hub_id: str, description: AjaxSensorDescription) -> None:
        super().__init__(coordinator, hub_id)
        self.entity_description = description
        self._attr_unique_id = f"{hub_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.hub_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.hub_data)
