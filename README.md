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
- The call is fire-and-forget: Home Assistant does not fail the action if NeoHub or the panel rejects the command. Check the log (`NeoHub server error: ...`) or the partition state.
- The services exist only once the NeoHub config entry is loaded. Until then (for example while NeoHub is unreachable at startup), calling them fails with an "action not found" error. After that they stay registered until Home Assistant restarts. If the entry is later unloaded (disabled, deleted or reloading) or the alarm panel entity is unavailable (NeoHub disconnected), a call does nothing and does not fail; at most Home Assistant logs a warning that the entity is missing or not currently available. Check the partition state.

## Entity Model

| Concept   | HA Entity Type        | Unique ID Format                                        |
|-----------|-----------------------|---------------------------------------------------------|
| Session   | Device                | `{session_id}`                                          |
| Partition | Alarm Control Panel   | `{session_id}_partition_{partition_number}`              |
| Zone      | Binary Sensor         | `{session_id}_zone_{zone_number}`                       |

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
          "status": "armed_away"
        },
        {
          "partition_number": 2,
          "name": "Garage",
          "status": "disarmed"
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
  ]
}
```

**`status`** values: `disarmed`, `armed_away`, `armed_home`, `armed_night`, `arming`, `pending`, `triggered` (`unknown` until NeoHub has read the partition's status)

**`device_class`** values: `door`, `window`, `motion`, `smoke`, `gas`, `moisture`, `vibration`, `safety`

#### `partition_update`

Pushed whenever a partition's state changes.

```json
{
  "type": "partition_update",
  "session_id": "abc123",
  "partition_number": 1,
  "status": "disarmed"
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

#### `error`

```json
{
  "type": "error",
  "message": "Invalid code"
}
```
