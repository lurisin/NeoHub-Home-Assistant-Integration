# This repository is currently under development, and is NOT fully functional yet.
#
# NeoHub Integration for Home Assistant

A Home Assistant integration for [NeoHub](https://github.com/BrianHumlicek/NeoHub) - connects DSC Neo alarm panels to Home Assistant via WebSocket.

This integration uses the [`pyneohub`](https://github.com/BrianHumlicek/NeoHub-Home-Assistant-Integration) Python library for all communication with the alarm panel.

## Architecture

- **`pyneohub`** - Standalone Python library on PyPI that handles WebSocket communication with NeoHub
- **Home Assistant Integration** - Lightweight glue code that bridges `pyneohub` with Home Assistant's entity system

## Features

- **Alarm Control Panel** entities for each partition (arm away, arm home, arm night, disarm)
- **Instant arming services** `neohub.arm_home_instant` and `neohub.arm_away_instant` (arm with no entry delay; optional `code`, see [Services](#services)). The partition still shows as Armed Home / Armed Away.
- **Binary Sensor** entities for each zone (door, window, motion, smoke, etc.)
- **Ready to arm**: a binary sensor per partition (needs a NeoHub that reports it, see [Ready to arm](#ready-to-arm))
- **Command results**: with a NeoHub that reports them, an arm or disarm action that the panel rejects (for example because a zone is open) or that NeoHub does not confirm fails with an error instead of passing silently (see [Errors](#errors))
- Real-time push updates via WebSocket — no polling
- Automatic reconnection with exponential backoff
- HACS compatible

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for **NeoHub** and install
5. Restart Home Assistant

### Manual

Copy the `custom_components/neohub` directory into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **NeoHub**
3. Enter your NeoHub connection details:
   - **Host**: hostname or IP address of NeoHub server
   - **Port**: WebSocket port (default `8080`)
   - **Use SSL**: enable for `wss://` connections
   - **Access Token**: optional bearer token for authentication

## Services

Besides the standard alarm control panel actions, the integration adds two entity services that arm a partition with no entry delay:

| Service                   | What it does                                                                              | Partition shows as |
|---------------------------|-------------------------------------------------------------------------------------------|--------------------|
| `neohub.arm_home_instant` | Stay arm with no entry delay ("Stay Instant", ITv2 arming mode `StayArmWithNoEntryDelay`) | Armed Home         |
| `neohub.arm_away_instant` | Away arm with no entry delay ("Away Instant", ITv2 arming mode `AwayArmWithNoEntryDelay`) | Armed Away         |

Both take an optional `code`. If it is left out or empty, the entity's default code is used if one is set in Home Assistant, otherwise NeoHub's default access code. The entity's supported features and states are unchanged; there is no separate "instant" state.

```yaml
action: neohub.arm_home_instant
target:
  entity_id: alarm_control_panel.example
```

Notes:

- These services **require a NeoHub build with `arm_home_instant` / `arm_away_instant` support**. An older NeoHub replies with an error and nothing is armed.
- `arm_away_instant` (arming mode 8) is untested on a real panel.
- With a NeoHub that reports command results, the action waits for the result and fails if the panel rejects the command or NeoHub does not confirm it, like the standard arm and disarm actions (see [Errors](#errors)). With an older NeoHub the call is fire-and-forget: Home Assistant does not fail the action if NeoHub or the panel rejects the command. Check the log (`NeoHub server error: ...`) or the partition state.
- The services exist only once the NeoHub config entry is loaded. Until then (for example while NeoHub is unreachable at startup), calling them fails with an "action not found" error. After that they stay registered until Home Assistant restarts. If the entry is later unloaded (disabled, deleted or reloading) or the alarm panel entity is unavailable (NeoHub disconnected), a call does nothing and does not fail; at most Home Assistant logs a warning that the entity is missing or not currently available. Check the partition state.

## Errors

A NeoHub that lists `command_result` in its `capabilities` (see the [WebSocket API](#websocket-api-specification)) reports the outcome of every command. With such a NeoHub, the arm actions (`alarm_control_panel.alarm_arm_home`, `alarm_arm_away`, `alarm_arm_night`, `neohub.arm_home_instant`, `neohub.arm_away_instant`) and `alarm_control_panel.alarm_disarm` wait up to 10 seconds for the result:

| Outcome | Result of the action |
|---|---|
| The panel accepted the command | Succeeds |
| The panel rejected an arm command with response code 1 (partition not ready to arm, for example a zone is open) | Fails: "Partition not ready to arm (zone open)" |
| Any other rejection (for example a wrong code), a refusal by the panel interface (a NACK, for example because it is busy) or a NeoHub error | Fails: "NeoHub command failed: ..." with NeoHub's message, for example "Command refused by the panel interface (NACK: SystemBusy)" |
| No result within 10 seconds, or the connection to NeoHub drops while waiting | Fails: "NeoHub command failed: No confirmation from NeoHub within 10 s; check the alarm state" (or "Connection to NeoHub lost before the command was confirmed; ..."). The panel may still have carried out the command, so check the partition state. |

**Behaviour change in 1.2.0:** before 1.2.0, these actions always succeeded and a rejection only showed up in the log. Now a rejected or unconfirmed arm or disarm raises an error, so a script or automation step that arms or disarms stops there and the following steps do not run. If the automation should carry on anyway, set `continue_on_error: true` on that step:

```yaml
actions:
  - action: alarm_control_panel.alarm_arm_home
    target:
      entity_id: alarm_control_panel.example
    continue_on_error: true
  - action: notify.notify
    data:
      message: "Arm command sent"
```

This only matters for scripts and automations that arm or disarm themselves and should carry on afterwards. An automation that only reacts to an arm action (for example one triggered by the `call_service` event that waits for the armed state and reports when it does not come) keeps working unchanged, and the person who pressed the button now also sees the error right away.

With an older NeoHub that does not list `command_result`, nothing changes: the actions return as soon as the command is sent and never fail because of the panel's answer.

## Ready to arm

A newer NeoHub (one that lists `partition_ready` in its `capabilities`) sends the panel's "ready" flag as `ready` for each partition. The partition is ready to arm when it is disarmed and nothing prevents arming, typically when all of its zones are closed. NeoHub sends `false` while the partition is not disarmed (armed, exit or entry delay, alarm). The integration then adds a binary sensor per partition that has an alarm panel entity, named "*partition* ready to arm" (on = ready, off = not ready), on the same device as the alarm panel entity. If that partition's alarm panel entity is disabled, the sensor is added disabled too.

With an older NeoHub there is no sensor. If NeoHub is updated while Home Assistant runs, the sensors appear when the integration reconnects. If NeoHub stops reporting the flag while Home Assistant runs, the sensor shows Unknown. After a Home Assistant restart or a reload of the integration with an older NeoHub, the sensor is no longer provided: it shows as unavailable and can be deleted.

## Entity Model

| Concept   | HA Entity Type        | Unique ID Format                                        |
|-----------|-----------------------|---------------------------------------------------------|
| Session   | Device                | `{session_id}`                                          |
| Partition | Alarm Control Panel   | `{session_id}_partition_{partition_number}`              |
| Zone      | Binary Sensor         | `{session_id}_zone_{zone_number}`                       |
| Partition ready to arm | Binary Sensor | `{session_id}_partition_{partition_number}_ready` (only with a NeoHub that sends `ready`) |

Zones are session-level entities that can be associated with one or more partitions. Each zone appears as a single binary sensor with its partition associations listed in the entity attributes.

## Alarm Panel States

| API Status     | HA State        |
|----------------|-----------------|
| `disarmed`     | Disarmed        |
| `armed_away`   | Armed Away      |
| `armed_home`   | Armed Home      |
| `armed_night`  | Armed Night     |
| `arming`       | Arming          |
| `pending`      | Pending         |
| `triggered`    | Triggered       |

`arming` means the exit delay is running and `pending` means the entry delay is running. Before NeoHub has read a partition's status it reports `unknown`, which shows as Unknown in Home Assistant.

---

## WebSocket API Specification

This section defines the WebSocket protocol between this integration and NeoHub. The endpoint is:

```
ws://{host}:{port}/api/ws
```

Authentication is via an optional `Authorization: Bearer {token}` header on the WebSocket upgrade request.

### Client → Server Messages

#### `get_full_state`

Request the complete state of all sessions, partitions, and zones. Sent on initial connection and after every reconnect.

```json
{
  "type": "get_full_state"
}
```

#### `arm_away`

```json
{
  "type": "arm_away",
  "session_id": "abc123",
  "partition_number": 1,
  "code": "1234"
}
```

#### `arm_home`

```json
{
  "type": "arm_home",
  "session_id": "abc123",
  "partition_number": 1,
  "code": "1234"
}
```

#### `arm_night`

```json
{
  "type": "arm_night",
  "session_id": "abc123",
  "partition_number": 1,
  "code": "1234"
}
```

#### `arm_home_instant`

Stay arm with no entry delay (ITv2 arming mode `StayArmWithNoEntryDelay`). NeoHub reports the partition as `armed_home`. Requires a NeoHub build that supports this message.

```json
{
  "type": "arm_home_instant",
  "session_id": "abc123",
  "partition_number": 1,
  "code": "1234"
}
```

#### `arm_away_instant`

Away arm with no entry delay (ITv2 arming mode `AwayArmWithNoEntryDelay`). NeoHub reports the partition as `armed_away`. Requires a NeoHub build that supports this message.

```json
{
  "type": "arm_away_instant",
  "session_id": "abc123",
  "partition_number": 1,
  "code": "1234"
}
```

#### `disarm`

```json
{
  "type": "disarm",
  "session_id": "abc123",
  "partition_number": 1,
  "code": "1234"
}
```

> `code` may be `null` if the panel does not require a code for the given action.

#### `request_id` (optional, on every command)

The commands above (and NeoHub's `bypass_zone`) accept an optional `request_id`: a string chosen by the client, at most 64 characters. `type` stays the first property. NeoHub then answers that command, on the same connection only, with exactly one [`command_result`](#command_result) and no `error` message. Without `request_id`, NeoHub answers as before: an `error` message on failure and nothing on success.

The integration sends `request_id` (a uuid4 in hex) only when the last `full_state` of the current connection listed `command_result` in `capabilities`; otherwise it sends the frames above unchanged.

```json
{
  "type": "arm_home",
  "session_id": "abc123",
  "partition_number": 1,
  "code": "1234",
  "request_id": "6f1c0e8d2b7a4b0f9c3e5a1d2f4b6c8e"
}
```

### Server → Client Messages

#### `full_state`

Sent in response to `get_full_state`. Contains the complete hierarchy.

```json
{
  "type": "full_state",
  "sessions": [
    {
      "session_id": "abc123",
      "name": "Home Panel",
      "partitions": [
        {
          "partition_number": 1,
          "name": "Main",
          "status": "armed_away",
          "ready": false
        },
        {
          "partition_number": 2,
          "name": "Garage",
          "status": "disarmed",
          "ready": true
        }
      ],
      "zones": [
        {
          "zone_number": 1,
          "name": "Front Door",
          "device_class": "door",
          "open": false,
          "partitions": [1, 2]
        },
        {
          "zone_number": 2,
          "name": "Living Room Motion",
          "device_class": "motion",
          "open": false,
          "partitions": [1]
        }
      ]
    }
  ],
  "capabilities": ["command_result", "partition_ready"]
}
```

**`capabilities`** (newer NeoHub only): `command_result` means NeoHub answers commands that carry a `request_id` with a `command_result`; `partition_ready` means each partition has **`ready`** (`true` when the partition is disarmed and ready to arm, `false` otherwise). An older NeoHub sends neither `capabilities` nor `ready`. The integration reads `capabilities` again from every `full_state` and forgets them when the connection drops.

**`status`** values: `disarmed`, `armed_away`, `armed_home`, `armed_night`, `arming`, `pending`, `triggered` (`unknown` until NeoHub has read the partition's status)

**`device_class`** values: `door`, `window`, `motion`, `smoke`, `gas`, `moisture`, `vibration`, `safety`

#### `partition_update`

Pushed whenever a partition's state changes. A newer NeoHub also sends `ready`, and pushes an update when only `ready` changes.

```json
{
  "type": "partition_update",
  "session_id": "abc123",
  "partition_number": 1,
  "status": "disarmed",
  "ready": true
}
```

#### `zone_update`

Pushed whenever a zone's state changes.

```json
{
  "type": "zone_update",
  "session_id": "abc123",
  "zone_number": 1,
  "open": true
}
```

#### `command_result`

Sent only to the connection that sent the command, once per command that carried a `request_id`, when the command completes or fails for any reason.

```json
{
  "type": "command_result",
  "request_id": "6f1c0e8d2b7a4b0f9c3e5a1d2f4b6c8e",
  "success": false,
  "code": 1,
  "message": "Partition not ready to arm (zone open)"
}
```

- On success `code` and `message` are `null`.
- When the panel rejects the command, `code` is the panel's numeric response code. For an arm command, `1` means the partition is not ready to arm (for example a zone is open).
- When the command fails before or around the panel (session not found, no access code, timeout, or the panel interface refused it with a NACK), `code` is `null` and `message` describes the failure. NeoHub waits up to 8 seconds for the panel; after that it reports "No confirmation from the panel within 8 s; check the partition state" (the panel may still have acted).

#### `error`

Sent for invalid messages and, for commands without `request_id`, when the command fails.

```json
{
  "type": "error",
  "message": "Invalid code"
}
```
