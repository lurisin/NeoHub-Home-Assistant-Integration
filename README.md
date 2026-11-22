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
- **Panel trouble**: a binary sensor per partition that is on while the panel reports a trouble (needs a NeoHub that reports it, see [Panel trouble](#panel-trouble))
- **Trouble types**: with a NeoHub that reports them, the trouble sensor shows which troubles are active in its attribute `trouble_types` (see [Panel trouble](#panel-trouble))
- **Keypad alarms**: an event entity per partition that fires when the panel reports a keypad Fire, Auxiliary or Panic alarm (needs a NeoHub that reports them, see [Keypad alarms](#keypad-alarms))
- **Siren and alarm memory**: two binary sensors per partition, on while the siren sounds and while the panel holds an alarm in memory (needs a NeoHub that reports them, see [Siren and alarm memory](#siren-and-alarm-memory))
- **Command results**: with a NeoHub that reports them, an arm or disarm action that the panel rejects (for example because a zone is open) or that NeoHub does not confirm fails with an error instead of passing silently (see [Errors](#errors))
- **FAP alarms (experimental, sends a real alarm)**: the action `neohub.activate_fap` sends a Fire, Auxiliary or Panic alarm like the keypad keys; it only works when FAP commands are turned on in NeoHub (see [FAP alarms](#fap-alarms-experimental))
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

The integration also adds the experimental action `neohub.activate_fap`, which **sends a real alarm**; see [FAP alarms](#fap-alarms-experimental). Unlike the two services above, it is registered when Home Assistant loads the integration and fails with a validation error (sending nothing) when its alarm panel entity is not loaded.

## Errors

A NeoHub that lists `command_result` in its `capabilities` (see the [WebSocket API](#websocket-api-specification)) reports the outcome of every command. With such a NeoHub, the arm actions (`alarm_control_panel.alarm_arm_home`, `alarm_arm_away`, `alarm_arm_night`, `neohub.arm_home_instant`, `neohub.arm_away_instant`) and `alarm_control_panel.alarm_disarm` wait up to 10 seconds for the result:

| Outcome | Result of the action |
|---|---|
| The panel accepted the command | Succeeds |
| The panel rejected an arm command with response code 1 (partition not ready to arm, for example because a zone is open; the panel's description of code 1 is generic and names no cause, so other causes are possible) | Fails: "Partition not ready to arm" |
| Any other rejection (for example a wrong code), a refusal by the panel interface (a NACK, for example because it is busy) or a NeoHub error | Fails: "NeoHub command failed: ..." with NeoHub's message, for example "NeoHub command failed: Invalid access code" or "NeoHub command failed: Keypad locked out" (an older NeoHub words them differently, for example "Command refused by the panel interface (NACK: SystemBusy)") |
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

The panel interface's NACK codes and the panel's response codes are two different number ranges that overlap with different meanings. A newer NeoHub says which one `code` is (`code_kind`, see [`command_result`](#command_result)): only response code 1 on an arm command means "not ready". NACK code 1 (an invalid command length) and every other code give "NeoHub command failed: ..." with NeoHub's text. A NeoHub that does not send `code_kind` only reports response codes, so code 1 on an arm command still gives "Partition not ready to arm".

## Ready to arm

A newer NeoHub (one that lists `partition_ready` in its `capabilities`) sends the panel's "ready" flag as `ready` for each partition. The partition is ready to arm when it is disarmed and nothing prevents arming, typically when all of its zones are closed. NeoHub sends `false` while the partition is not disarmed (armed, exit or entry delay, alarm). The integration then adds a binary sensor per partition that has an alarm panel entity, named "*partition* ready to arm" (on = ready, off = not ready), on the same device as the alarm panel entity. If that partition's alarm panel entity is disabled, the sensor is added disabled too.

With an older NeoHub there is no sensor. If NeoHub is updated while Home Assistant runs, the sensors appear when the integration reconnects. If NeoHub stops reporting the flag while Home Assistant runs, the sensor shows Unknown. After a Home Assistant restart or a reload of the integration with an older NeoHub, the sensor is no longer provided: it shows as unavailable and can be deleted.

## Panel trouble

A newer NeoHub (one that lists `partition_troubles` in its `capabilities`) sends the panel's "troubles present" flag as `troubles` for each partition: on while the panel reports a trouble, such as AC power loss, an open cabinet (tamper) or a disconnected backup battery. The integration then adds a binary sensor per partition that has an alarm panel entity, named "*partition* trouble", with device class `problem` (on = the panel reports a trouble, shown as Problem; off = OK), on the same device as the alarm panel entity. If that partition's alarm panel entity is disabled, the sensor is added disabled too.

NeoHub reads the flag when it connects to the panel, re-reads it periodically (by default every 60 seconds; the interval is a NeoHub connection setting, and values below 10 seconds count as 10) and about half a second after the panel rejects an arm command as not ready. Setting the interval to 0 turns off both re-reads, so the flag is then read only when NeoHub connects. So the sensor usually lags behind the panel by up to that interval, and longer while NeoHub is busy with a command or programming, or cannot read the status. A NeoHub that also lists `trouble_types` turns the flag on as soon as the panel reports a trouble, without waiting for the next re-read; it still turns it off only when a read of the panel status reports no troubles.

**Trouble types.** A NeoHub that lists `trouble_types` sends `trouble_types`, the list of active troubles, and the sensor shows it as its attribute `trouble_types` (the integration shows the key whenever NeoHub sends it, so the capability changes nothing for it; integration 1.3.0 already does the same). The troubles are panel-wide, so the list is the same for every partition, and it is empty while that partition's `troubles` is off. The names:

| Name | Meaning |
|---|---|
| `ac_failure` | AC power failure |
| `tamper` | Cabinet tamper (panel cabinet open) |
| `battery_disconnected` | Backup battery disconnected |
| `unknown_<a>_<b>_<c>` | A trouble the panel reported with a code NeoHub has no name for, in hex, for example `unknown_00_8a_00` (a low battery probably shows up like this) |
| `unknown` | The panel reports a trouble but NeoHub has not received its details, for example a trouble that was already active when NeoHub connected to the panel |

The names are stable: new names may be added, existing ones are not renamed. With an older NeoHub the attribute is missing and the sensor only says that a trouble is present: the keypad shows the details.

The alarm panel entity does not change: it gets no new attribute, and a change of the trouble flag alone does not change its state or fire state triggers on it.

The sensor follows the same rules as the ready to arm sensor when NeoHub is older or changes version while Home Assistant runs: with an older NeoHub there is no sensor; if NeoHub is updated while Home Assistant runs, the sensors appear when the integration reconnects; if NeoHub stops reporting the flag while Home Assistant runs, the sensor shows Unknown; after a restart or a reload with an older NeoHub it shows as unavailable and can be deleted.

## Keypad alarms

A NeoHub that lists `keypad_alarms` in its `capabilities` reports the alarms of the keypad's alarm keys (the F, A and P key pairs: Fire, Auxiliary, Panic). The integration then adds an event entity per partition that has an alarm panel entity, named "*partition* keypad alarm", on the same device as the alarm panel entity. It follows the trouble sensor's rules: added disabled when that partition's alarm panel entity is disabled, none with an older NeoHub, added when NeoHub is updated while Home Assistant runs, unavailable after a restart or reload with an older NeoHub.

- Event types: `fire` (the Fire key, panel alarm type 3) and `unknown` (any other alarm type; type 9, which the Auxiliary and Panic keys can produce, is not identified yet and may get its own event type later).
- Event attribute `code`: the panel's alarm type number (3, 9, ...).
- The event fires once per keypad alarm. The panel restores a keypad alarm within milliseconds, so it is a momentary event, not a state.
- If the connection to NeoHub was down when the alarm happened, the event fires when the integration reconnects (NeoHub keeps the last keypad alarm, see `last_keypad_alarm` in the [WebSocket API](#full_state)). After a Home Assistant restart or a reload of the integration an earlier alarm is not fired again, and the entity keeps showing the last event from before.
- An alarm that arrives while the integration is still setting up (about 10 seconds after Home Assistant starts or the integration is reloaded), or before the event entity is added, fires when the entity is added.
- Limits: NeoHub keeps only the last keypad alarm per panel, so of several alarms during a connection outage only the last one fires after the reconnect. NeoHub forgets it when the panel disconnects normally or NeoHub restarts, and alarms while Home Assistant itself is down are never fired. Use the [siren and alarm in memory sensors](#siren-and-alarm-memory) as a fallback: the alarm memory stays on until the next arming.
- An `unknown` keypad alarm is not a confirmed Auxiliary or Panic key press: on some panels the same message also reports conditions that are not key presses.
- An alarm for a partition that Home Assistant does not know (for example partition 0) is logged as a warning and dropped.

**Home Assistant shows no `triggered` for keypad or other alarms.** During a keypad alarm the alarm panel entity stays Disarmed or Armed: many automations react to that entity's states, and a momentary alarm has no defined end for `triggered`. NeoHub does not report `triggered` while other alarms are going on either (it only reads the panel's "in alarm" flag when it connects to the panel). Detect alarms with the keypad alarm event entity and the [siren sensor](#siren-and-alarm-memory).

The event entity's state is the time of its last event, and it also changes when NeoHub disconnects and reconnects (to unavailable and back), when the integration is reloaded and when the entity is created. To react only to keypad alarms, use the `event.received` trigger where Home Assistant has it (2026.11 does, 2026.2 does not):

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.example_keypad_alarm
    options:
      event_type:
        - fire
        - unknown
```

or, with any version, a state trigger that skips those changes:

```yaml
triggers:
  - trigger: state
    entity_id: event.example_keypad_alarm
    not_from: unavailable
    not_to:
      - unavailable
      - unknown
conditions:
  - condition: template
    value_template: "{{ trigger.from_state is not none }}"
actions:
  - action: notify.notify
    data:
      message: >-
        Keypad alarm: {{ trigger.to_state.attributes.event_type }}
        (code {{ trigger.to_state.attributes.code }})
```

A plain state trigger without `not_from` / `not_to` also runs on every NeoHub reconnect (twice) and reload.

## Siren and alarm memory

A NeoHub that lists `partition_siren_memory` in its `capabilities` sends `siren` and `alarm_memory` for each partition. The integration then adds two binary sensors per partition that has an alarm panel entity, with the same rules as the trouble sensor:

- "*partition* siren", device class `sound`: on (Detected) while the partition's siren (bell) sounds. NeoHub takes it from the panel's bell notifications and also turns it off when the partition is armed or disarmed, so a missed "off" cannot hide the next alarm.
- "*partition* alarm in memory", device class `problem`: on (Problem) while the panel holds an alarm in memory for the partition. DSC panels clear the alarm memory at the next arming.

A `partition_update` without these keys keeps the last value; if NeoHub stops sending them, the sensors show Unknown. The alarm panel entity does not change: no new attribute, no state change and no state trigger for these flags.

## FAP alarms (experimental)

> **WARNING: `neohub.activate_fap` triggers a REAL alarm.** It makes the panel raise a Fire, Auxiliary or Panic alarm as if the F, A or P keys on the keypad had been pressed. On a monitored panel the alarm is reported to the central station, which may send the fire brigade, an ambulance or the police. Test it only with the monitoring station informed and the account on test.

- **Experimental and untested on a real panel.** The command layout comes from another open-source ITv2 implementation and has not been confirmed on a panel; the panel's answer is not documented. The panel may reject the command (the action then fails with NeoHub's message) or handle it differently.
- **Off by default.** It needs a NeoHub that supports it, with FAP commands turned on in NeoHub's settings (the setting `AllowFapCommands` on NeoHub's settings page, off by default). Only then does NeoHub list the `fap` capability. Without it the action fails with "NeoHub does not offer FAP commands ..." and nothing is sent; there is no fallback for an older NeoHub. Turn the setting off again after testing.
- The action takes exactly one alarm panel entity of this integration (`entity_id`, as data or as a target; not a list of several, a device, an area or a label), `type` (`fire`, `auxiliary` or `panic`, exactly) and `confirm`, which must be `true`. Anything else fails with a validation error, and nothing is sent.
- The caller needs control permission for that alarm panel entity, as for disarming it: a read-only user (or an unknown user) gets an "unauthorized" error and nothing is sent. Automations and scripts started without a user are not limited.
- It is sent once and never retried, not even after a timeout or a reconnect. It waits up to 10 seconds for NeoHub's result and fails with NeoHub's message if the panel rejects it. If no answer arrives it fails with "... the alarm may still have been triggered": check the keypad and the monitoring station before trying again.
- Every FAP request and its result are logged as warnings. The Home Assistant log also shows a warning when NeoHub starts accepting FAP commands ("NeoHub at ... accepts FAP commands ...") and when it stops ("... no longer accepts FAP commands"). After the test, turn the NeoHub setting off, press Save on NeoHub's settings page, and check that the log shows "no longer accepts FAP commands".
- There is deliberately no button, switch or other entity for it, and the alarm panel entity does not get the `trigger` feature: entities may be exposed to voice assistants, and a stray call would send a real alarm. That keeps it away from the Assist API, which works on exposed entities, but not from every AI agent: from Home Assistant 2026.11, an LLM conversation agent or MCP client that is given the admin-only "Home Assistant" LLM API can search for and call any action, `neohub.activate_fap` included, and it fills in `confirm: true` like any other field. Keep NeoHub's FAP setting off except during the supervised test, and do not give that API to an agent while it is on. NeoHub's setting is the real barrier; the action's description, which tells assistants never to call it, is not.

```yaml
action: neohub.activate_fap
data:
  entity_id: alarm_control_panel.example
  type: fire
  confirm: true
```

## Entity Model

| Concept   | HA Entity Type        | Unique ID Format                                        |
|-----------|-----------------------|---------------------------------------------------------|
| Session   | Device                | `{session_id}`                                          |
| Partition | Alarm Control Panel   | `{session_id}_partition_{partition_number}`              |
| Zone      | Binary Sensor         | `{session_id}_zone_{zone_number}`                       |
| Partition ready to arm | Binary Sensor | `{session_id}_partition_{partition_number}_ready` (only with a NeoHub that sends `ready`) |
| Partition trouble | Binary Sensor (device class `problem`) | `{session_id}_partition_{partition_number}_trouble` (only with a NeoHub that lists `partition_troubles`) |
| Partition siren | Binary Sensor (device class `sound`) | `{session_id}_partition_{partition_number}_siren` (only with a NeoHub that lists `partition_siren_memory`) |
| Partition alarm in memory | Binary Sensor (device class `problem`) | `{session_id}_partition_{partition_number}_alarm_memory` (only with a NeoHub that lists `partition_siren_memory`) |
| Partition keypad alarm | Event (event types `fire`, `unknown`) | `{session_id}_partition_{partition_number}_keypad_alarm` (only with a NeoHub that lists `keypad_alarms`) |

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

`arming` means the exit delay is running and `pending` means the entry delay is running. Before NeoHub has read a partition's status it reports `unknown`, which shows as Unknown in Home Assistant. NeoHub does not report `triggered` while an alarm is going on, only when it connects to a panel that is in alarm (see [Keypad alarms](#keypad-alarms)).

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

#### `activate_fap` (experimental, sends a real alarm)

Sends a FAP alarm for a partition, like the keypad's F, A or P keys (see [FAP alarms](#fap-alarms-experimental)). Only a NeoHub that lists `fap` in `capabilities` accepts it. `partition`, `fap_type` (exactly `fire`, `auxiliary` or `panic`) and `request_id` are required (without `request_id` NeoHub answers with an `error` message and sends nothing); the alarm kind is `fap_type` because `type` is the message type. There is no access code. NeoHub answers with a [`command_result`](#command_result); a NeoHub whose FAP commands are turned off answers `success: false` with "FAP commands are disabled in the NeoHub settings" and sends nothing to the panel. The integration sends it once and never retries it.

```json
{
  "type": "activate_fap",
  "session_id": "abc123",
  "partition": 1,
  "fap_type": "fire",
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
          "ready": false,
          "troubles": false,
          "trouble_types": [],
          "siren": false,
          "alarm_memory": false
        },
        {
          "partition_number": 2,
          "name": "Garage",
          "status": "disarmed",
          "ready": true,
          "troubles": true,
          "trouble_types": ["ac_failure"],
          "siren": false,
          "alarm_memory": true
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
      ],
      "last_keypad_alarm": {
        "partition": 2,
        "alarm_type": "fire",
        "code": 3,
        "time": "2026-01-01T10:00:00.000Z"
      }
    }
  ],
  "capabilities": ["command_result", "partition_ready", "partition_troubles", "trouble_types", "keypad_alarms", "partition_siren_memory"]
}
```

**`capabilities`** (newer NeoHub only), in this order:

- `command_result`: NeoHub answers commands that carry a `request_id` with a `command_result`.
- `partition_ready`: each partition has **`ready`** (`true` when the partition is disarmed and ready to arm, `false` otherwise).
- `partition_troubles`: each partition has **`troubles`** (`true` while the panel reports a trouble).
- `trouble_types`: each partition has **`trouble_types`** next to `troubles`: the list of active troubles (see [Panel trouble](#panel-trouble) for the names), the same panel-wide list on every partition, `[]` whenever that partition's `troubles` is `false`.
- `keypad_alarms`: NeoHub sends a [`keypad_alarm`](#keypad_alarm) message for each keypad alarm, and each session has **`last_keypad_alarm`**: the last keypad alarm of that session as `{"partition", "alarm_type", "code", "time"}` (the fields of `keypad_alarm`), or `null`. NeoHub keeps it in memory only (not across a NeoHub restart).
- `partition_siren_memory`: each partition has **`siren`** (`true` while the partition's siren sounds) and **`alarm_memory`** (`true` while the panel holds an alarm in memory for the partition).
- `fap` (last, only while FAP commands are turned on in NeoHub's settings): NeoHub accepts [`activate_fap`](#activate_fap-experimental-sends-a-real-alarm). When the setting changes, NeoHub sends a new `full_state` to every client.

An older NeoHub sends neither `capabilities` nor these keys, and a NeoHub that lists only some of these capabilities sends only the matching keys. The integration reads `capabilities` again from every `full_state` and forgets them when the connection drops. It reads `trouble_types`, `siren` and `alarm_memory` whenever they are present.

**`status`** values: `disarmed`, `armed_away`, `armed_home`, `armed_night`, `arming`, `pending`, `triggered` (`unknown` until NeoHub has read the partition's status)

**`device_class`** values: `door`, `window`, `motion`, `smoke`, `gas`, `moisture`, `vibration`, `safety`

#### `partition_update`

Pushed whenever a partition's state changes. A newer NeoHub also sends `ready` (with `partition_ready`), `troubles` (with `partition_troubles`), `trouble_types` (with `trouble_types`) and `siren` and `alarm_memory` (with `partition_siren_memory`), and pushes an update when only one of them changes. A key that is missing from an update keeps its last value.

```json
{
  "type": "partition_update",
  "session_id": "abc123",
  "partition_number": 1,
  "status": "disarmed",
  "ready": true,
  "troubles": false
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

#### `keypad_alarm`

Sent by a NeoHub that lists `keypad_alarms` when the panel reports a keypad alarm (the F, A and P keys). `alarm_type` is `fire` (panel alarm type 3) or `unknown` (any other type, including 9); `code` is the panel's alarm type number; `time` is when NeoHub received it (UTC, ISO 8601 with milliseconds and `Z`, NeoHub's clock). `partition` may be a partition the client does not know (for example 0). The partition's `status` does not change.

```json
{
  "type": "keypad_alarm",
  "session_id": "abc123",
  "partition": 1,
  "alarm_type": "fire",
  "code": 3,
  "time": "2026-01-01T10:00:00.000Z"
}
```

The integration fires the partition's keypad alarm event for each message. From `full_state` it fires `last_keypad_alarm` only when its `time` is strictly newer than the newest keypad alarm it has seen since it started, and never from the first `full_state` after it starts or is reloaded.

#### `command_result`

Sent only to the connection that sent the command, once per command that carried a `request_id`, when the command completes or fails for any reason.

```json
{
  "type": "command_result",
  "request_id": "6f1c0e8d2b7a4b0f9c3e5a1d2f4b6c8e",
  "success": false,
  "code": 1,
  "code_kind": "response",
  "message": "Partition not ready to arm"
}
```

- On success `code` and `message` are `null`.
- When the panel rejects the command, `code` is the panel's numeric response code. For an arm command, `1` means the partition is not ready to arm (for example a zone is open).
- A newer NeoHub also sends **`code_kind`** next to `code`: `"response"` when `code` is the panel's response code, `"nack"` when it is the code of a NACK from the panel interface (the two ranges overlap with different meanings: NACK 1 is not "not ready"), and `null` whenever `code` is `null`. An older NeoHub does not send `code_kind`, reports a NACK with `code` `null` and only reports response codes in `code`.
- When the command fails before or around the panel (session not found, no access code, timeout, FAP commands turned off, or with an older NeoHub a NACK), `code` is `null` and `message` describes the failure. NeoHub waits up to 8 seconds for the panel; after that it reports "No confirmation from the panel within 8 s; check the partition state" (the panel may still have acted; for `activate_fap`: "No answer from the panel: the alarm may still have been triggered").

#### `error`

Sent for invalid messages and, for commands without `request_id`, when the command fails.

```json
{
  "type": "error",
  "message": "Invalid code"
}
```
