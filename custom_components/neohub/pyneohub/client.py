"""NeoHub WebSocket client library."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

RECONNECT_INTERVAL = 10
MAX_RECONNECT_INTERVAL = 300

# Seconds to wait for the command_result of a command. NeoHub itself gives
# up waiting for the panel after 8 seconds and then reports a failure.
COMMAND_RESULT_TIMEOUT = 10

# Capability listed in full_state by a NeoHub that answers commands that
# carry a request_id with a command_result message.
CAPABILITY_COMMAND_RESULT = "command_result"


class NeoHubError(Exception):
    """Base exception for NeoHub client."""


class NeoHubConnectionError(NeoHubError):
    """Connection error."""


class NeoHubCommandError(NeoHubError):
    """NeoHub reported that a command failed.

    ``code`` is the panel's numeric response code when the panel rejected
    the command, otherwise ``None``. ``message`` is NeoHub's description.
    """

    def __init__(self, message: str, code: int | None = None) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.message = message
        self.code = code


class NeoHubCommandUnconfirmedError(NeoHubCommandError):
    """No command_result arrived (timeout or connection lost).

    The panel may still have carried out the command.
    """


class NeoHubClient:
    """WebSocket client for NeoHub."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        ssl: bool = False,
        access_token: str | None = None,
    ) -> None:
        """Initialize the client.
        
        Args:
            host: Hostname or IP address
            port: Port number
            ssl: Use SSL/TLS
            access_token: Optional bearer token for authentication
        """
        self.host = host
        self.port = port
        self.ssl = ssl
        self.access_token = access_token
        
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._state: dict[str, Any] = {}
        self._connected = False
        self._listen_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._shutdown = False
        # Capabilities from the last full_state of the current connection.
        self._capabilities: frozenset[str] = frozenset()
        # Commands waiting for their command_result, keyed by request_id.
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        
        # Callbacks
        self._on_connect: list[Callable[[], None]] = []
        self._on_disconnect: list[Callable[[], None]] = []
        self._on_full_state: list[Callable[[dict[str, Any]], None]] = []
        self._on_partition_update: list[Callable[[dict[str, Any]], None]] = []
        self._on_zone_update: list[Callable[[dict[str, Any]], None]] = []
        self._on_error: list[Callable[[str], None]] = []

    @property
    def connected(self) -> bool:
        """Return True if connected to WebSocket."""
        return self._connected

    @property
    def state(self) -> dict[str, Any]:
        """Return the current state dictionary keyed by session_id."""
        return self._state

    @property
    def capabilities(self) -> frozenset[str]:
        """Return the capabilities NeoHub listed in the last full_state.

        Empty while disconnected and for NeoHub versions that do not list
        any capabilities.
        """
        return self._capabilities

    @property
    def ws_url(self) -> str:
        """Return the WebSocket URL."""
        scheme = "wss" if self.ssl else "ws"
        return f"{scheme}://{self.host}:{self.port}/api/ws"

    def register_connection_callback(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register a callback for connection events.
        
        Returns:
            A function to unregister the callback
        """
        self._on_connect.append(callback)
        return lambda: self._on_connect.remove(callback)

    def register_disconnection_callback(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register a callback for disconnection events.
        
        Returns:
            A function to unregister the callback
        """
        self._on_disconnect.append(callback)
        return lambda: self._on_disconnect.remove(callback)

    def register_full_state_callback(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for full_state messages.
        
        Returns:
            A function to unregister the callback
        """
        self._on_full_state.append(callback)
        return lambda: self._on_full_state.remove(callback)

    def register_partition_update_callback(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for partition_update messages.
        
        Returns:
            A function to unregister the callback
        """
        self._on_partition_update.append(callback)
        return lambda: self._on_partition_update.remove(callback)

    def register_zone_update_callback(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for zone_update messages.
        
        Returns:
            A function to unregister the callback
        """
        self._on_zone_update.append(callback)
        return lambda: self._on_zone_update.remove(callback)

    def register_error_callback(
        self, callback: Callable[[str], None]
    ) -> Callable[[], None]:
        """Register a callback for error messages.
        
        Returns:
            A function to unregister the callback
        """
        self._on_error.append(callback)
        return lambda: self._on_error.remove(callback)

    async def connect(self, _from_reconnect: bool = False) -> bool:
        """Connect to the WebSocket server and request initial state."""
        self._shutdown = False

        # Cancel any stale reconnect task before starting a fresh connection,
        # but only when called externally (not from within _reconnect itself).
        if not _from_reconnect:
            if self._reconnect_task is not None and not self._reconnect_task.done():
                self._reconnect_task.cancel()
                self._reconnect_task = None

        # Clean up any leftover session from a previous attempt.
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

        try:
            self._session = aiohttp.ClientSession()
            headers: dict[str, str] = {}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"

            self._ws = await asyncio.wait_for(
                self._session.ws_connect(
                    self.ws_url,
                    headers=headers,
                    heartbeat=30,
                ),
                timeout=10,
            )
            self._connected = True

            for callback in self._on_connect:
                callback()

            await self._send({"type": "get_full_state"})

            self._listen_task = asyncio.create_task(self._listen())

            _LOGGER.info("Connected to NeoHub at %s:%s", self.host, self.port)
            return True

        except Exception as err:
            _LOGGER.error("Failed to connect to NeoHub: %s", err)
            await self._cleanup()
            raise NeoHubConnectionError(f"Connection failed: {err}") from err

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._shutdown = True
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._listen_task is not None:
            self._listen_task.cancel()
            self._listen_task = None
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up the WebSocket and HTTP session."""
        was_connected = self._connected
        self._connected = False
        self._capabilities = frozenset()
        self._fail_pending_commands()

        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

        if was_connected:
            for callback in self._on_disconnect:
                try:
                    callback()
                except Exception:
                    _LOGGER.exception("Error in disconnection callback")

    async def _send(self, data: dict[str, Any]) -> None:
        """Send a JSON message over the WebSocket."""
        if self._ws is not None and not self._ws.closed:
            await self._ws.send_json(data)
        else:
            _LOGGER.warning("Cannot send message, WebSocket not connected")

    async def _send_command(
        self,
        command_type: str,
        session_id: str,
        partition_number: int,
        code: str | None,
    ) -> None:
        """Send a partition command and wait for its result if NeoHub reports one.

        If the last full_state of this connection listed the
        "command_result" capability, the command carries a request_id and
        this waits up to COMMAND_RESULT_TIMEOUT seconds for the matching
        command_result. It raises NeoHubCommandError if NeoHub reports a
        failure, and NeoHubCommandUnconfirmedError if no result arrives
        (timeout, connection lost, or the command could not be sent).

        Otherwise (older NeoHub, or not connected) the command is sent as
        before, without a request_id, and nothing is awaited or raised: a
        failure only shows up as an "error" message from NeoHub.
        """
        message: dict[str, Any] = {
            "type": command_type,
            "session_id": session_id,
            "partition_number": partition_number,
            "code": code,
        }

        if CAPABILITY_COMMAND_RESULT not in self._capabilities:
            await self._send(message)
            _LOGGER.debug(
                "NeoHub does not report command results; %s sent without "
                "waiting for confirmation",
                command_type,
            )
            return

        request_id = uuid.uuid4().hex
        message["request_id"] = request_id
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        # Register before sending: the result can arrive while send_json
        # is still being awaited.
        self._pending[request_id] = future
        try:
            ws = self._ws
            if ws is None or ws.closed:
                raise NeoHubCommandUnconfirmedError(
                    "Not connected to NeoHub; the command was not sent"
                )
            try:
                await ws.send_json(message)
            except (aiohttp.ClientError, ConnectionError) as err:
                raise NeoHubCommandUnconfirmedError(
                    f"Could not send the command to NeoHub: {err}"
                ) from err
            try:
                result = await asyncio.wait_for(future, COMMAND_RESULT_TIMEOUT)
            except TimeoutError:
                raise NeoHubCommandUnconfirmedError(
                    f"No confirmation from NeoHub within "
                    f"{COMMAND_RESULT_TIMEOUT} s; check the alarm state"
                ) from None
        finally:
            self._pending.pop(request_id, None)
            # If the connection-drop cleanup failed the future while the
            # send was still running and the send then raised, nobody
            # awaits the future: mark its exception as retrieved so asyncio
            # does not log "Future exception was never retrieved".
            if future.done() and not future.cancelled():
                future.exception()

        if result.get("success") is True:
            _LOGGER.debug("NeoHub confirmed %s", command_type)
            return

        code_value = result.get("code")
        result_code = (
            code_value
            if isinstance(code_value, int) and not isinstance(code_value, bool)
            else None
        )
        text = result.get("message")
        if not isinstance(text, str) or not text:
            text = (
                f"The panel rejected the command (response code {result_code})"
                if result_code is not None
                else "NeoHub reported that the command failed"
            )
        raise NeoHubCommandError(text, result_code)

    def _fail_pending_commands(self) -> None:
        """Fail every command still waiting for its command_result."""
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(
                    NeoHubCommandUnconfirmedError(
                        "Connection to NeoHub lost before the command was "
                        "confirmed; check the alarm state"
                    )
                )

    async def _listen(self) -> None:
        """Listen for incoming WebSocket messages."""
        try:
            assert self._ws is not None
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        self._handle_message(data)
                    except json.JSONDecodeError:
                        _LOGGER.error("Invalid JSON received: %s", msg.data)
                    except Exception:
                        _LOGGER.exception("Error handling message")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.error("WebSocket error: %s", self._ws.exception())
                    break
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    _LOGGER.warning(
                        "WebSocket closed by server (code=%s)",
                        getattr(msg, 'data', 'N/A'),
                    )
                    break
        except asyncio.CancelledError:
            return
        except Exception:
            _LOGGER.exception("WebSocket listen error")

        await self._cleanup()
        if not self._shutdown:
            self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        interval = RECONNECT_INTERVAL
        try:
            while not self._shutdown:
                _LOGGER.warning(
                    "NeoHub disconnected. Reconnecting in %s seconds...", interval
                )
                await asyncio.sleep(interval)
                if self._shutdown:
                    return
                try:
                    if await self.connect(_from_reconnect=True):
                        return
                except NeoHubConnectionError:
                    pass
                interval = min(interval * 2, MAX_RECONNECT_INTERVAL)
        except asyncio.CancelledError:
            _LOGGER.debug("Reconnect task cancelled")

    def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming WebSocket message."""
        msg_type = data.get("type")

        if msg_type == "full_state":
            self._handle_full_state(data)
        elif msg_type == "partition_update":
            self._handle_partition_update(data)
        elif msg_type == "zone_update":
            self._handle_zone_update(data)
        elif msg_type == "command_result":
            self._handle_command_result(data)
        elif msg_type == "error":
            error_msg = data.get("message", "Unknown error")
            _LOGGER.error("NeoHub server error: %s", error_msg)
            for callback in self._on_error:
                try:
                    callback(error_msg)
                except Exception:
                    _LOGGER.exception("Error in error callback")
        else:
            _LOGGER.warning("Unknown message type '%s': %s", msg_type, data)

    def _handle_full_state(self, data: dict[str, Any]) -> None:
        """Process a full_state message."""
        self._state = {}
        for session in data.get("sessions", []):
            session_id = session.get("session_id")
            if session_id is None:
                _LOGGER.error("Session missing session_id: %s", session)
                continue
            self._state[session_id] = session

        capabilities = data.get("capabilities")
        self._capabilities = (
            frozenset(c for c in capabilities if isinstance(c, str))
            if isinstance(capabilities, list)
            else frozenset()
        )
        _LOGGER.debug("NeoHub capabilities: %s", sorted(self._capabilities))

        _LOGGER.info(
            "Received full state: %d session(s), %d partition(s), %d zone(s)",
            len(self._state),
            sum(len(s.get("partitions", [])) for s in self._state.values()),
            sum(len(s.get("zones", [])) for s in self._state.values()),
        )

        for callback in self._on_full_state:
            try:
                callback(data)
            except Exception:
                _LOGGER.exception("Error in full_state callback")

    def _handle_partition_update(self, data: dict[str, Any]) -> None:
        """Process a partition_update message."""
        session_id = data.get("session_id")
        partition_number = data.get("partition_number")

        if session_id is None or partition_number is None:
            _LOGGER.error(
                "Received partition_update missing required fields. Data: %s",
                data,
            )
            return

        if session_id in self._state:
            for partition in self._state[session_id].get("partitions", []):
                if partition["partition_number"] == partition_number:
                    if "status" in data:
                        partition["status"] = data["status"]
                    if "ready" in data:
                        partition["ready"] = data["ready"]
                    break

        for callback in self._on_partition_update:
            try:
                callback(data)
            except Exception:
                _LOGGER.exception("Error in partition_update callback")

    def _handle_zone_update(self, data: dict[str, Any]) -> None:
        """Process a zone_update message."""
        session_id = data.get("session_id")
        zone_number = data.get("zone_number")

        if session_id is None or zone_number is None:
            _LOGGER.error(
                "Received zone_update missing required fields. Data: %s",
                data,
            )
            return

        if session_id in self._state:
            for zone in self._state[session_id].get("zones", []):
                if zone["zone_number"] == zone_number:
                    if "open" in data:
                        zone["open"] = data["open"]
                    if "bypassed" in data:
                        zone["bypassed"] = data["bypassed"]
                    if "partitions" in data:
                        zone["partitions"] = data["partitions"]
                    break

        for callback in self._on_zone_update:
            try:
                callback(data)
            except Exception:
                _LOGGER.exception("Error in zone_update callback")

    def _handle_command_result(self, data: dict[str, Any]) -> None:
        """Process a command_result message."""
        request_id = data.get("request_id")
        future = (
            self._pending.get(request_id) if isinstance(request_id, str) else None
        )
        if future is None or future.done():
            # Late answer after a timeout, or a result for another client.
            _LOGGER.debug(
                "Ignoring command_result for unknown request_id %s", request_id
            )
            return
        future.set_result(data)

    # ── Commands ────────────────────────────────────────────────────────
    #
    # With a NeoHub that lists the "command_result" capability, each command
    # waits for the result and raises NeoHubCommandError on failure (see
    # _send_command). With an older NeoHub it returns as soon as the command
    # is sent.

    async def arm_away(
        self, session_id: str, partition_number: int, code: str | None = None
    ) -> None:
        """Send an arm-away command."""
        await self._send_command("arm_away", session_id, partition_number, code)

    async def arm_home(
        self, session_id: str, partition_number: int, code: str | None = None
    ) -> None:
        """Send an arm-home (stay) command."""
        await self._send_command("arm_home", session_id, partition_number, code)

    async def arm_night(
        self, session_id: str, partition_number: int, code: str | None = None
    ) -> None:
        """Send an arm-night command."""
        await self._send_command("arm_night", session_id, partition_number, code)

    async def disarm(
        self, session_id: str, partition_number: int, code: str | None = None
    ) -> None:
        """Send a disarm command."""
        await self._send_command("disarm", session_id, partition_number, code)

    async def arm_home_instant(
        self, session_id: str, partition_number: int, code: str | None = None
    ) -> None:
        """Send an arm-home (stay) command with no entry delay (Stay Instant)."""
        await self._send_command(
            "arm_home_instant", session_id, partition_number, code
        )

    async def arm_away_instant(
        self, session_id: str, partition_number: int, code: str | None = None
    ) -> None:
        """Send an arm-away command with no entry delay (Away Instant)."""
        await self._send_command(
            "arm_away_instant", session_id, partition_number, code
        )
