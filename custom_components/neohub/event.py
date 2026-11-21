"""Event platform for DSC Neo integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_CONNECTION_STATE, SIGNAL_KEYPAD_ALARM
from .coordinator import NeoHubCoordinator
from .pyneohub.client import CAPABILITY_KEYPAD_ALARMS

_LOGGER = logging.getLogger(__name__)

KEYPAD_ALARM_FIRE = "fire"
KEYPAD_ALARM_UNKNOWN = "unknown"
KEYPAD_ALARM_EVENT_TYPES = [KEYPAD_ALARM_FIRE, KEYPAD_ALARM_UNKNOWN]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DSC Neo event entities."""
    coordinator: NeoHubCoordinator = hass.data[DOMAIN][entry.entry_id]

    # A "keypad alarm" event entity per partition, with the same rules as
    # the trouble sensor in binary_sensor.py: only for partitions that get
    # an alarm panel entity at setup, created when NeoHub lists the
    # "keypad_alarms" capability (from the setup state, or from the first
    # full_state that lists it), named after the setup-time partition
    # names, and added disabled when the partition's alarm panel entity is
    # disabled.
    keypad_alarm_entities: set[tuple[str, int]] = set()
    registry = er.async_get(hass)
    setup_names: dict[tuple[str, int], str] = {
        (session_id, partition["partition_number"]): partition.get(
            "name", f"Partition {partition['partition_number']}"
        )
        for session_id, session in coordinator.state.items()
        for partition in session.get("partitions", [])
        if partition.get("partition_number") is not None
    }

    @callback
    def _alarm_enabled(key: tuple[str, int]) -> bool:
        alarm_entity_id = registry.async_get_entity_id(
            "alarm_control_panel", DOMAIN, f"{key[0]}_partition_{key[1]}"
        )
        alarm_entry = registry.async_get(alarm_entity_id) if alarm_entity_id else None
        return alarm_entry is None or not alarm_entry.disabled

    @callback
    def _new_entities() -> list[EventEntity]:
        if CAPABILITY_KEYPAD_ALARMS not in coordinator.client.capabilities:
            return []
        new: list[EventEntity] = []
        for session_id, session in coordinator.state.items():
            session_name = session.get("name", f"DSC Neo {session_id}")
            for partition in session.get("partitions", []):
                key = (session_id, partition.get("partition_number"))
                if key not in setup_names or key in keypad_alarm_entities:
                    continue
                keypad_alarm_entities.add(key)
                new.append(
                    DscPartitionKeypadAlarmEvent(
                        coordinator=coordinator,
                        session_id=session_id,
                        session_name=session_name,
                        partition_number=key[1],
                        partition_name=setup_names[key],
                        enabled_default=_alarm_enabled(key),
                    )
                )
        return new

    async_add_entities(_new_entities())

    @callback
    def _handle_full_state(_data: dict[str, Any]) -> None:
        if new := _new_entities():
            async_add_entities(new)

    entry.async_on_unload(
        coordinator.client.register_full_state_callback(_handle_full_state)
    )


class DscPartitionKeypadAlarmEvent(EventEntity):
    """A keypad alarm (Fire / Auxiliary / Panic keys) on a DSC Neo partition.

    Event type "fire" for the Fire key, "unknown" for any other alarm type
    NeoHub reports (the panel's code for the Auxiliary and Panic keys is
    not identified yet). The event attribute "code" is the panel's raw
    alarm type number. The alarm panel entity does not change.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "keypad_alarm"
    _attr_event_types = KEYPAD_ALARM_EVENT_TYPES

    def __init__(
        self,
        coordinator: NeoHubCoordinator,
        session_id: str,
        session_name: str,
        partition_number: int,
        partition_name: str,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the event entity."""
        self._coordinator = coordinator
        self._session_id = session_id
        self._partition_number = partition_number
        self._attr_unique_id = (
            f"{session_id}_partition_{partition_number}_keypad_alarm"
        )
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_translation_placeholders = {"partition": partition_name}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, session_id)},
            name=session_name,
            manufacturer="DSC",
            model="Neo",
        )

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._coordinator.connected

    async def async_added_to_hass(self) -> None:
        """Register dispatch listeners when added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_KEYPAD_ALARM}_{self._session_id}_{self._partition_number}",
                self._handle_keypad_alarm,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION_STATE,
                self._handle_connection_state,
            )
        )

    @callback
    def _handle_keypad_alarm(self, alarm: dict[str, Any]) -> None:
        """Fire the event for a keypad alarm of this partition."""
        alarm_type = alarm.get("alarm_type")
        event_type = (
            KEYPAD_ALARM_FIRE
            if alarm_type == KEYPAD_ALARM_FIRE
            else KEYPAD_ALARM_UNKNOWN
        )
        code = alarm.get("code")
        if not isinstance(code, int) or isinstance(code, bool):
            code = None
        self._trigger_event(event_type, {"code": code})
        self.async_write_ha_state()

    @callback
    def _handle_connection_state(self, connected: bool) -> None:
        """Handle a connection state change."""
        self.async_write_ha_state()
