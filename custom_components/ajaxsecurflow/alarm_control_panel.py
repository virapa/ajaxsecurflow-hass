"""Alarm panels: one per hub, plus one per group when groups mode is enabled."""
from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity, AlarmControlPanelEntityFeature, AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AjaxSecurFlowConfigEntry
from .api import AjaxSecurFlowError, PlanError
from .const import ARM_STATE_ARM, ARM_STATE_DISARM, ARM_STATE_NIGHT, DOMAIN, PLANS_WITH_CONTROL
from .coordinator import AjaxSecurFlowCoordinator
from .entity import AjaxSecurFlowHubEntity

CONTROL_FEATURES = AlarmControlPanelEntityFeature.ARM_AWAY | AlarmControlPanelEntityFeature.ARM_NIGHT


def map_state(raw: str | None, triggered: bool) -> AlarmControlPanelState | None:
    """Ajax hub/group state string → HA alarm state."""
    if triggered:
        return AlarmControlPanelState.TRIGGERED
    if not raw:
        return None
    state = raw.upper()
    if state.startswith("PARTIALLY_ARMED"):
        return AlarmControlPanelState.ARMED_CUSTOM_BYPASS
    if state == "NIGHT_MODE" or state.endswith("NIGHT_MODE_ON"):
        return AlarmControlPanelState.ARMED_NIGHT
    if state.startswith("ARMED"):
        return AlarmControlPanelState.ARMED_AWAY
    if state.startswith("DISARMED"):
        return AlarmControlPanelState.DISARMED
    return None


async def async_setup_entry(hass: HomeAssistant, entry: AjaxSecurFlowConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    rt = entry.runtime_data
    control = rt.plan in PLANS_WITH_CONTROL
    entities: list[AjaxSecurFlowAlarmPanel] = []
    for hub_id, hub_data in rt.coordinator.data.items():
        entities.append(AjaxSecurFlowAlarmPanel(rt.coordinator, hub_id, None, control))
        if hub_data.hub.get("groups_enabled"):
            entities.extend(AjaxSecurFlowAlarmPanel(rt.coordinator, hub_id, group_id, control) for group_id in hub_data.groups)
    async_add_entities(entities)


class AjaxSecurFlowAlarmPanel(AjaxSecurFlowHubEntity, AlarmControlPanelEntity):
    _attr_code_arm_required = False
    _attr_code_format = None

    def __init__(self, coordinator: AjaxSecurFlowCoordinator, hub_id: str, group_id: str | None, control: bool) -> None:
        super().__init__(coordinator, hub_id)
        self.group_id = group_id
        self._attr_supported_features = CONTROL_FEATURES if control else AlarmControlPanelEntityFeature(0)
        if group_id is None:
            self._attr_unique_id = f"{hub_id}_panel"
            self._attr_name = None  # takes the hub device name
        else:
            self._attr_unique_id = f"{hub_id}_{group_id}_panel"
            self._attr_translation_key = "group"
            self._attr_translation_placeholders = {"group": self.hub_data.groups[group_id].get("name") or group_id}

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.group_id is None or self.group_id in self.hub_data.groups

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        if self.group_id is None:
            return map_state(self.hub_data.hub.get("state"), self.hub_data.triggered)
        return map_state(self.hub_data.groups[self.group_id].get("state"), False)

    async def _send(self, arm_state: int) -> None:
        try:
            await self.coordinator.client.set_arm_state(self.hub_id, arm_state, self.group_id)
        except PlanError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="plan_required") from err
        except AjaxSecurFlowError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed", translation_placeholders={"error": str(err)}
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self._send(ARM_STATE_DISARM)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._send(ARM_STATE_ARM)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self._send(ARM_STATE_NIGHT)
