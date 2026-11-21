"""Binary sensor platform for DSC Neo integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_CONNECTION_STATE, SIGNAL_STATE_UPDATED
from .coordinator import NeoHubCoordinator
from .pyneohub.client import (
    CAPABILITY_PARTITION_SIREN_MEMORY,
    CAPABILITY_PARTITION_TROUBLES,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_CLASS_MAP: dict[str, BinarySensorDeviceClass] = {
    "door": BinarySensorDeviceClass.DOOR,
    "window": BinarySensorDeviceClass.WINDOW,
    "motion": BinarySensorDeviceClass.MOTION,
    "smoke": BinarySensorDeviceClass.SMOKE,
    "gas": BinarySensorDeviceClass.GAS,
    "moisture": BinarySensorDeviceClass.MOISTURE,
    "vibration": BinarySensorDeviceClass.VIBRATION,
    "safety": BinarySensorDeviceClass.SAFETY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DSC Neo binary sensor entities."""
    coordinator: NeoHubCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []
    for session_id, session in coordinator.state.items():
        session_name = session.get("name", f"DSC Neo {session_id}")
        for zone in session.get("zones", []):
            entities.append(
                DscZoneSensor(
                    coordinator=coordinator,
                    session_id=session_id,
                    session_name=session_name,
                    zone_number=zone["zone_number"],
                    zone_name=zone.get(
                        "name", f"Zone {zone['zone_number']}"
                    ),
                    device_class_str=zone.get("device_class", ""),
                    initial_open=zone.get("open", False),
                    initial_bypassed=zone.get("bypassed", False),
                    partition_list=zone.get("partitions", []),
                )
            )

    # A "ready to arm" sensor for every partition that gets an alarm panel
    # entity at setup and whose state includes "ready". An older NeoHub does
    # not send it, so there is none. If NeoHub is updated while Home
    # Assistant runs, the sensors are added when the first full_state with
    # "ready" arrives. They are named after the partition names in the state
    # used now, at setup (the same names the alarm panel entities get), not
    # after a full_state that NeoHub may send before it has read the panel's
    # labels. A partition that first appears later gets neither entity until
    # the entry is reloaded. If the partition's alarm panel entity is
    # disabled, its ready sensor is added disabled too.
    #
    # A "trouble" sensor per partition follows the same rules, except that
    # it is created when NeoHub lists the "partition_troubles" capability
    # (from the setup state, or from the first full_state that lists it).
    # The "siren" and "alarm in memory" sensors follow the trouble sensor's
    # rules with the "partition_siren_memory" capability.
    ready_sensors: set[tuple[str, int]] = set()
    trouble_sensors: set[tuple[str, int]] = set()
    siren_memory_sensors: set[tuple[str, int]] = set()
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
    def _new_partition_sensors() -> list[BinarySensorEntity]:
        new: list[BinarySensorEntity] = []
        troubles_reported = (
            CAPABILITY_PARTITION_TROUBLES in coordinator.client.capabilities
        )
        siren_memory_reported = (
            CAPABILITY_PARTITION_SIREN_MEMORY in coordinator.client.capabilities
        )
        for session_id, session in coordinator.state.items():
            session_name = session.get("name", f"DSC Neo {session_id}")
            for partition in session.get("partitions", []):
                key = (session_id, partition.get("partition_number"))
                if key not in setup_names:
                    continue
                if "ready" in partition and key not in ready_sensors:
                    ready_sensors.add(key)
                    new.append(
                        DscPartitionReadySensor(
                            coordinator=coordinator,
                            session_id=session_id,
                            session_name=session_name,
                            partition_number=key[1],
                            partition_name=setup_names[key],
                            enabled_default=_alarm_enabled(key),
                        )
                    )
                if troubles_reported and key not in trouble_sensors:
                    trouble_sensors.add(key)
                    new.append(
                        DscPartitionTroubleSensor(
                            coordinator=coordinator,
                            session_id=session_id,
                            session_name=session_name,
                            partition_number=key[1],
                            partition_name=setup_names[key],
                            enabled_default=_alarm_enabled(key),
                        )
                    )
                if siren_memory_reported and key not in siren_memory_sensors:
                    siren_memory_sensors.add(key)
                    enabled_default = _alarm_enabled(key)
                    new.extend(
                        sensor_class(
                            coordinator=coordinator,
                            session_id=session_id,
                            session_name=session_name,
                            partition_number=key[1],
                            partition_name=setup_names[key],
                            enabled_default=enabled_default,
                        )
                        for sensor_class in (
                            DscPartitionSirenSensor,
                            DscPartitionAlarmMemorySensor,
                        )
                    )
        return new

    entities.extend(_new_partition_sensors())
    async_add_entities(entities)

    @callback
    def _handle_full_state(_data: dict[str, Any]) -> None:
        if new := _new_partition_sensors():
            async_add_entities(new)

    entry.async_on_unload(
        coordinator.client.register_full_state_callback(_handle_full_state)
    )


class DscZoneSensor(BinarySensorEntity):
    """Representation of a DSC Neo zone as a binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeoHubCoordinator,
        session_id: str,
        session_name: str,
        zone_number: int,
        zone_name: str,
        device_class_str: str,
        initial_open: bool,
        initial_bypassed: bool,
        partition_list: list[int],
    ) -> None:
        """Initialize the binary sensor entity."""
        self._coordinator = coordinator
        self._session_id = session_id
        self._zone_number = zone_number
        self._bypassed = initial_bypassed
        self._partition_list = partition_list
        self._attr_unique_id = f"{session_id}_zone_{zone_number}"
        self._attr_name = zone_name
        self._attr_is_on = initial_open
        self._attr_device_class = DEVICE_CLASS_MAP.get(device_class_str)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, session_id)},
            name=session_name,
            manufacturer="DSC",
            model="Neo",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "bypassed": self._bypassed,
            "partitions": self._partition_list,
        }

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._coordinator.connected

    async def async_added_to_hass(self) -> None:
        """Register dispatch listeners when added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_STATE_UPDATED}_zone_{self._session_id}_{self._zone_number}",
                self._handle_update,
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
    def _handle_update(self, data: dict[str, Any]) -> None:
        """Handle a zone state update."""
        if "open" in data:
            self._attr_is_on = data["open"]
        if "bypassed" in data:
            self._bypassed = data["bypassed"]
        if "partitions" in data:
            self._partition_list = data["partitions"]
        self.async_write_ha_state()

    @callback
    def _handle_connection_state(self, connected: bool) -> None:
        """Handle a connection state change."""
        self.async_write_ha_state()


class DscPartitionReadySensor(BinarySensorEntity):
    """Whether a DSC Neo partition is ready to arm (as reported by NeoHub)."""

    _attr_has_entity_name = True
    _attr_translation_key = "ready_to_arm"

    def __init__(
        self,
        coordinator: NeoHubCoordinator,
        session_id: str,
        session_name: str,
        partition_number: int,
        partition_name: str,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the binary sensor entity."""
        self._coordinator = coordinator
        self._session_id = session_id
        self._partition_number = partition_number
        self._attr_unique_id = f"{session_id}_partition_{partition_number}_ready"
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_translation_placeholders = {"partition": partition_name}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, session_id)},
            name=session_name,
            manufacturer="DSC",
            model="Neo",
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the partition is ready to arm."""
        return self._coordinator.partition_ready(
            self._session_id, self._partition_number
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
                f"{SIGNAL_STATE_UPDATED}_partition_{self._session_id}_{self._partition_number}",
                self._handle_update,
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
    def _handle_update(self, data: dict[str, Any]) -> None:
        """Handle a partition state update (full_state or partition_update)."""
        self.async_write_ha_state()

    @callback
    def _handle_connection_state(self, connected: bool) -> None:
        """Handle a connection state change."""
        self.async_write_ha_state()


class DscPartitionTroubleSensor(BinarySensorEntity):
    """Whether the panel reports a trouble for a DSC Neo partition."""

    _attr_has_entity_name = True
    _attr_translation_key = "trouble"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: NeoHubCoordinator,
        session_id: str,
        session_name: str,
        partition_number: int,
        partition_name: str,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the binary sensor entity."""
        self._coordinator = coordinator
        self._session_id = session_id
        self._partition_number = partition_number
        self._attr_unique_id = f"{session_id}_partition_{partition_number}_trouble"
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_translation_placeholders = {"partition": partition_name}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, session_id)},
            name=session_name,
            manufacturer="DSC",
            model="Neo",
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the panel reports troubles for the partition."""
        return self._coordinator.partition_troubles(
            self._session_id, self._partition_number
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the trouble types, if NeoHub reports them."""
        types = self._coordinator.partition_trouble_types(
            self._session_id, self._partition_number
        )
        return None if types is None else {"trouble_types": types}

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._coordinator.connected

    async def async_added_to_hass(self) -> None:
        """Register dispatch listeners when added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_STATE_UPDATED}_partition_{self._session_id}_{self._partition_number}",
                self._handle_update,
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
    def _handle_update(self, data: dict[str, Any]) -> None:
        """Handle a partition state update (full_state or partition_update)."""
        self.async_write_ha_state()

    @callback
    def _handle_connection_state(self, connected: bool) -> None:
        """Handle a connection state change."""
        self.async_write_ha_state()


class DscPartitionFlagSensor(BinarySensorEntity):
    """A boolean partition flag that NeoHub reports, read from its state.

    Subclasses set the state key, the unique_id suffix, the translation key
    and the device class. A partition_update without the key keeps the last
    value; a full_state without it (NeoHub downgraded) gives unknown.
    """

    _attr_has_entity_name = True
    _flag_key: str
    _unique_id_suffix: str

    def __init__(
        self,
        coordinator: NeoHubCoordinator,
        session_id: str,
        session_name: str,
        partition_number: int,
        partition_name: str,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the binary sensor entity."""
        self._coordinator = coordinator
        self._session_id = session_id
        self._partition_number = partition_number
        self._attr_unique_id = (
            f"{session_id}_partition_{partition_number}_{self._unique_id_suffix}"
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
    def is_on(self) -> bool | None:
        """Return the flag as NeoHub reports it."""
        return self._coordinator.partition_flag(
            self._session_id, self._partition_number, self._flag_key
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
                f"{SIGNAL_STATE_UPDATED}_partition_{self._session_id}_{self._partition_number}",
                self._handle_update,
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
    def _handle_update(self, data: dict[str, Any]) -> None:
        """Handle a partition state update (full_state or partition_update)."""
        self.async_write_ha_state()

    @callback
    def _handle_connection_state(self, connected: bool) -> None:
        """Handle a connection state change."""
        self.async_write_ha_state()


class DscPartitionSirenSensor(DscPartitionFlagSensor):
    """Whether the partition's siren (bell) is sounding, as NeoHub reports it."""

    _attr_translation_key = "siren"
    _attr_device_class = BinarySensorDeviceClass.SOUND
    _flag_key = "siren"
    _unique_id_suffix = "siren"


class DscPartitionAlarmMemorySensor(DscPartitionFlagSensor):
    """Whether the panel holds an alarm in memory for the partition."""

    _attr_translation_key = "alarm_memory"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _flag_key = "alarm_memory"
    _unique_id_suffix = "alarm_memory"
