"""Coordinator for DSC Neo (via NeoHub) integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_CONNECTION_STATE, SIGNAL_KEYPAD_ALARM, SIGNAL_STATE_UPDATED
from .pyneohub import NeoHubClient, NeoHubConnectionError

_LOGGER = logging.getLogger(__name__)


def _neohub_time(value: Any) -> datetime | None:
    """Parse a time NeoHub sends (ISO 8601, UTC), or None if it is not one."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class NeoHubCoordinator:
    """Coordinator to manage NeoHub client and Home Assistant integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        ssl: bool,
        access_token: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self._client = NeoHubClient(
            host=host,
            port=port,
            ssl=ssl,
            access_token=access_token,
        )

        self._unregister_callbacks: list[Callable[[], None]] = []
        self._state_event = asyncio.Event()
        # Keypad alarm replay: the newest keypad alarm time (NeoHub's clock)
        # seen per session since this coordinator was created, and whether
        # a full_state has been handled yet.
        self._keypad_alarm_newest: dict[str, datetime] = {}
        self._full_state_seen = False

    @property
    def client(self) -> NeoHubClient:
        """Return the client instance."""
        return self._client

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return self._client.connected

    @property
    def state(self) -> dict[str, Any]:
        """Return the current state."""
        return self._client.state

    def _partition(
        self, session_id: str, partition_number: int
    ) -> dict[str, Any] | None:
        """Return a partition's state from the client, or None if unknown."""
        session = self.state.get(session_id)
        if session is None:
            return None
        for partition in session.get("partitions", []):
            if partition.get("partition_number") == partition_number:
                return partition
        return None

    def partition_ready(self, session_id: str, partition_number: int) -> bool | None:
        """Return whether a partition is ready to arm.

        None if NeoHub does not report it (older NeoHub) or the partition
        is unknown.
        """
        partition = self._partition(session_id, partition_number)
        ready = partition.get("ready") if partition is not None else None
        return ready if isinstance(ready, bool) else None

    def partition_troubles(
        self, session_id: str, partition_number: int
    ) -> bool | None:
        """Return whether the panel reports troubles for a partition.

        None if NeoHub does not report it (older NeoHub) or the partition
        is unknown.
        """
        partition = self._partition(session_id, partition_number)
        troubles = partition.get("troubles") if partition is not None else None
        return troubles if isinstance(troubles, bool) else None

    def partition_flag(
        self, session_id: str, partition_number: int, key: str
    ) -> bool | None:
        """Return a boolean partition flag NeoHub reports, such as "siren".

        None if NeoHub does not report it (older NeoHub), the value is not a
        bool, or the partition is unknown.
        """
        partition = self._partition(session_id, partition_number)
        value = partition.get(key) if partition is not None else None
        return value if isinstance(value, bool) else None

    def partition_trouble_types(
        self, session_id: str, partition_number: int
    ) -> list[str] | None:
        """Return the trouble types NeoHub reports for a partition.

        None if NeoHub does not send "trouble_types" or the partition is
        unknown.
        """
        partition = self._partition(session_id, partition_number)
        types = partition.get("trouble_types") if partition is not None else None
        if not isinstance(types, list):
            return None
        return [t for t in types if isinstance(t, str)]

    def async_setup(self) -> None:
        """Register callbacks with the client (idempotent)."""
        if not self._unregister_callbacks:
            self._register_callbacks()

    async def async_connect(self) -> bool:
        """Connect to NeoHub. Returns True on success."""
        try:
            await self._client.connect()
        except NeoHubConnectionError as err:
            _LOGGER.warning(
                "Failed to connect to NeoHub (%s:%s): %s",
                self._client.host,
                self._client.port,
                err,
            )
            return False
        return True

    async def async_wait_for_state_update(self, timeout: float) -> bool:
        """Wait for next full_state message. Returns True if received."""
        self._state_event.clear()
        try:
            await asyncio.wait_for(self._state_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        for unregister in self._unregister_callbacks:
            unregister()
        self._unregister_callbacks.clear()

        await self._client.disconnect()

    def _register_callbacks(self) -> None:
        """Register callbacks with the client."""
        self._unregister_callbacks.append(
            self._client.register_connection_callback(self._handle_connection)
        )
        self._unregister_callbacks.append(
            self._client.register_disconnection_callback(self._handle_disconnection)
        )
        self._unregister_callbacks.append(
            self._client.register_full_state_callback(self._handle_full_state)
        )
        self._unregister_callbacks.append(
            self._client.register_partition_update_callback(
                self._handle_partition_update
            )
        )
        self._unregister_callbacks.append(
            self._client.register_zone_update_callback(self._handle_zone_update)
        )
        self._unregister_callbacks.append(
            self._client.register_keypad_alarm_callback(self._handle_keypad_alarm)
        )

    def _handle_connection(self) -> None:
        """Handle connection event."""
        async_dispatcher_send(self.hass, SIGNAL_CONNECTION_STATE, True)

    def _handle_disconnection(self) -> None:
        """Handle disconnection event."""
        _LOGGER.warning("DSC Neo disconnected")
        async_dispatcher_send(self.hass, SIGNAL_CONNECTION_STATE, False)

    def _handle_full_state(self, data: dict[str, Any]) -> None:
        """Handle full_state message from client."""
        first_full_state = not self._full_state_seen
        self._full_state_seen = True
        for session in data.get("sessions", []):
            session_id = session.get("session_id")
            if session_id is None:
                continue

            for partition in session.get("partitions", []):
                pn = partition.get("partition_number")
                if pn is None:
                    continue
                async_dispatcher_send(
                    self.hass,
                    f"{SIGNAL_STATE_UPDATED}_partition_{session_id}_{pn}",
                    partition,
                )

            for zone in session.get("zones", []):
                zn = zone.get("zone_number")
                if zn is None:
                    continue
                async_dispatcher_send(
                    self.hass,
                    f"{SIGNAL_STATE_UPDATED}_zone_{session_id}_{zn}",
                    zone,
                )

            self._replay_keypad_alarm(session_id, session, first_full_state)

        self._state_event.set()

    def _replay_keypad_alarm(
        self, session_id: str, session: dict[str, Any], first_full_state: bool
    ) -> None:
        """Fire a keypad alarm from full_state that was missed while disconnected.

        NeoHub keeps the last keypad alarm of each session in full_state, so
        a keypad_alarm message that arrived while the WebSocket was down is
        not lost. The first full_state after the integration starts or is
        reloaded only records its time and never fires: that alarm happened
        before this run (Home Assistant restarted, or the integration was
        reloaded), and replaying it would repeat an old alarm. A later
        full_state fires it only if its time is strictly newer than the
        newest keypad alarm seen in this run. Only NeoHub's times are
        compared, never Home Assistant's clock.
        """
        alarm = session.get("last_keypad_alarm")
        if not isinstance(alarm, dict):
            return
        alarm_time = _neohub_time(alarm.get("time"))
        if alarm_time is None:
            _LOGGER.debug(
                "Ignoring last_keypad_alarm without a valid time: %s", alarm
            )
            return
        newest = self._keypad_alarm_newest.get(session_id)
        if newest is not None and alarm_time <= newest:
            return
        self._keypad_alarm_newest[session_id] = alarm_time
        if first_full_state:
            _LOGGER.debug(
                "Recorded the last keypad alarm of session %s (%s); not replayed",
                session_id,
                alarm.get("time"),
            )
            return
        _LOGGER.info(
            "Keypad alarm of session %s at %s arrived while disconnected from "
            "NeoHub; firing it now",
            session_id,
            alarm.get("time"),
        )
        self._dispatch_keypad_alarm(session_id, alarm)

    def _handle_keypad_alarm(self, data: dict[str, Any]) -> None:
        """Handle keypad_alarm message from client."""
        session_id = data["session_id"]
        alarm_time = _neohub_time(data.get("time"))
        if alarm_time is not None:
            newest = self._keypad_alarm_newest.get(session_id)
            if newest is None or alarm_time > newest:
                self._keypad_alarm_newest[session_id] = alarm_time
        self._dispatch_keypad_alarm(session_id, data)

    def _dispatch_keypad_alarm(self, session_id: str, alarm: dict[str, Any]) -> None:
        """Send a keypad alarm to its partition's event entity."""
        partition_number = alarm.get("partition")
        if (
            not isinstance(partition_number, int)
            or isinstance(partition_number, bool)
            or self._partition(session_id, partition_number) is None
        ):
            _LOGGER.warning(
                "Keypad alarm %s (code %s) for partition %s of session %s, "
                "which Home Assistant does not know; ignored",
                alarm.get("alarm_type"),
                alarm.get("code"),
                partition_number,
                session_id,
            )
            return
        _LOGGER.info(
            "Keypad alarm %s (code %s) on partition %s of session %s",
            alarm.get("alarm_type"),
            alarm.get("code"),
            partition_number,
            session_id,
        )
        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_KEYPAD_ALARM}_{session_id}_{partition_number}",
            alarm,
        )

    def _handle_partition_update(self, data: dict[str, Any]) -> None:
        """Handle partition_update message from client."""
        session_id = data.get("session_id")
        partition_number = data.get("partition_number")

        if session_id is None or partition_number is None:
            return

        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_STATE_UPDATED}_partition_{session_id}_{partition_number}",
            data,
        )

    def _handle_zone_update(self, data: dict[str, Any]) -> None:
        """Handle zone_update message from client."""
        session_id = data.get("session_id")
        zone_number = data.get("zone_number")

        if session_id is None or zone_number is None:
            return

        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_STATE_UPDATED}_zone_{session_id}_{zone_number}",
            data,
        )

