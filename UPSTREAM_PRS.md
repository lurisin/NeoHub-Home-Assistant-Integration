# Upstream PR drafts

> **Nothing in this file has been submitted.** No PR, issue or comment may be
> opened or posted upstream without the owner's explicit OK.

Target repository: `BrianHumlicek/NeoHub-Home-Assistant-Integration`, base
branch `master` (at `6ebc3e0` when this was written; check before submitting).

No PR in this file is meant to come from the fork's working branch, which also carries
the fork's version bump and this file. Create one branch per PR from upstream
`master` and cherry-pick only the commits listed for that PR.

---

## PR A: Add `neohub.arm_home_instant` / `neohub.arm_away_instant` services

Commits to cherry-pick, in this order:

1. `Add arm_home_instant / arm_away_instant to the pyneohub client`
2. `Add neohub.arm_home_instant / neohub.arm_away_instant services`

Leave out `README: fix the partition status values` (PR B) and
`Bump version to 1.1.0` (fork only). Both commits apply cleanly to `6ebc3e0`.

Before submitting:

- Open the NeoHub PR first and put its number in place of `<NEOHUB_PR>`.
- Issue #13 also suggests an optional state attribute for "armed with no entry
  delay". This PR does not add it, so it says "Related to #13" rather than
  "Closes #13".
- Submit PR B first or together with this one. Otherwise the README's "Alarm
  Panel States" table and `full_state` status list still name `armed_stay`,
  `exit_delay` and `entry_delay`, next to this PR's new text that says the
  partition shows as Armed Home (`armed_home`).

### Title

```
Add neohub.arm_home_instant / neohub.arm_away_instant services
```

### Body

```markdown
Related to #13.

**Depends on BrianHumlicek/NeoHub#<NEOHUB_PR>**, which adds the `arm_home_instant` / `arm_away_instant` WebSocket messages to NeoHub (see BrianHumlicek/NeoHub#54). A NeoHub without them answers with an `error` message and nothing is armed.

## Summary

Two entity services on the alarm control panel entities that arm a partition with no entry delay:

| Service | WebSocket message | NeoHub arming mode | Entity state afterwards |
|---|---|---|---|
| `neohub.arm_home_instant` | `arm_home_instant` | `StayArmWithNoEntryDelay` (7), "Stay Instant" | `armed_home` |
| `neohub.arm_away_instant` | `arm_away_instant` | `AwayArmWithNoEntryDelay` (8), "Away Instant" | `armed_away` |

Supported features and entity states are unchanged, so existing automations and cards keep working.

## Changes

- `pyneohub/client.py`: `arm_home_instant()` and `arm_away_instant()`, with the same signature and payload shape as `arm_home()` (`{"type", "session_id", "partition_number", "code"}`). `README_LIBRARY.md` lists them. The pyneohub version is unchanged.
- `alarm_control_panel.py`: the services are registered with `entity_platform.async_get_current_platform().async_register_entity_service(...)` and the schema `{vol.Optional(ATTR_CODE): cv.string}`. The code goes through `self.check_code_arm_required(code)`, which is what the built-in arm actions use:
  - An empty or missing code becomes the entity's default code (the Home Assistant entity option), or `None` if none is set.
  - `None` makes NeoHub use its own default access code. NeoHub only falls back on null, so `""` is never sent.
  - It raises only if `code_arm_required` is set, and it is `False` for this entity.
  - Because they are registered by the platform, the services exist only once the config entry is loaded. Like other platform entity services, they then stay registered until Home Assistant restarts; after an unload, or while the entity is unavailable, a call does nothing. The README says so.
- `services.yaml`, `strings.json` and `translations/en.json`: service and field descriptions. The two JSON files are identical.
- `README.md`: a Features line, a new "Services" section and the two messages in the WebSocket API section.
- There is no version bump, so `manifest.json` can be bumped when you release.

## Testing

- `python -m compileall custom_components/neohub`: passes.
- Every module imports on Home Assistant 2026.11.2 (Python 3.14) and 2026.2.3 (Python 3.13).
- hassfest from HA core 2026.11.2 and 2026.2.3 with `--integration-path`: 0 invalid integrations. The only output is the warning "Config flows that are discoverable need to set a unique ID", which `master` already has.
- Functional tests on a real `hass` instance, on 2026.11.2 and 2026.2.3. Only `NeoHubClient.connect` and `NeoHubClient._send` were mocked, and `STATE_STABLE_SECONDS` was shortened. The `code_arm_required` and unavailable-entity cases set the entity's `_attr_code_arm_required` and the client's `_connected` flag directly. No NeoHub was involved. The tests cover:
  - Config entry setup. Before it, calling the services fails with "action not found".
  - Both services with code `"x"`, no code, `""`, `"0123"` and `1234`. The results were `"x"`, `None`, `None`, `"0123"` and `"1234"`.
  - The HA `default_code` entity option. With no code or `""`, the default code was sent, the same as `alarm_control_panel.alarm_arm_home`.
  - `code_arm_required` set and no code: a `ServiceValidationError`, like the built-in action.
  - The exact WebSocket payloads, with `type` first.
  - Extra keys and a missing target: rejected.
  - An unavailable entity: skipped.
  - The `services.yaml` descriptions and translations: loaded.
  - Reload, and after an unload: still registered, a call sends nothing and does not fail.
  - The built-in `alarm_control_panel.*` actions send the same payloads as on `master`, and `supported_features` is still 7.
- Most of these cases also run as a pytest-homeassistant-custom-component suite on 2026.2.3, with the same mocks (the client-argument and unload tests also mock the client's `arm_*_instant` method): registration, `supported_features`, the five code values (as client arguments and as payloads, with `type` first), extra keys, the descriptions and translations, the `default_code` option next to `alarm_arm_home`, `code_arm_required`, an unavailable entity, and unload plus setup again. 35 passed.

## Not tested

- End to end on a real panel through NeoHub. The NeoHub side is in the PR this one depends on. "Stay arm with no entry delay" (mode 7) was accepted by a PowerSeries Neo panel when sent from the NeoHub Dev Console. Afterwards, the panel's arm notification reported plain Stay arm, which is also why no extra state attribute is added. `arm_away_instant` (mode 8) has not been tried on a panel.
- The `error` reply of a NeoHub without these messages comes from reading NeoHub's source, not from running it.
- Like the existing arm commands, the calls are fire-and-forget. Home Assistant does not fail the action if NeoHub or the panel rejects it; the rejection shows up in the log as `NeoHub server error: ...`.
```

---

## PR B (optional, docs only): fix the partition status values in the README

Commit to cherry-pick: `README: fix the partition status values`. It applies
cleanly to `6ebc3e0` on its own and does not depend on PR A.

### Title

```
README: fix the partition status values
```

### Body

```markdown
The "Alarm Panel States" table and the `status` values listed under `full_state` still name `armed_stay`, `exit_delay` and `entry_delay`.

NeoHub sends its `PartitionStatus` enum (`NeoHub/NeoHub/Services/Models/PartitionStatus.cs` in BrianHumlicek/NeoHub) in snake_case. The values are `disarmed`, `armed_away`, `armed_home`, `armed_night`, `arming`, `pending` and `triggered`, plus `unknown` before NeoHub has read the partition status. `STATUS_MAP` in `alarm_control_panel.py` maps exactly those seven values.

This PR changes the docs only.
```

---

## PR C: Command results and the partition ready state

Commits to cherry-pick, in this order:

1. `pyneohub: wait for command_result when NeoHub supports it`
2. `Raise HomeAssistantError when NeoHub reports a failed command`
3. `Add the partition ready state: alarm attribute and binary sensor`
4. `Add Italian translation` (optional; drop it if the maintainer does not
   want translations beyond English; nothing else depends on it)
5. `README: command results, ready to arm, protocol additions`

Leave out `Bump version to 1.2.0` (fork only) and the `UPSTREAM_PRS.md`
commits.

Dependencies:

- **NeoHub:** this needs the NeoHub PR drafted as section D of the NeoHub
  fork's `UPSTREAM_PRS.md` (request_id / command_result, capabilities, partition
  ready). Open it first and put its number in place of `<NEOHUB_PR_D>`. Without
  it nothing breaks: the integration only uses the new features when NeoHub
  lists them in `capabilities`.
- **This repository:** the commits apply on top of PR A and PR B. In a scratch
  clone, upstream `master` (`6ebc3e0`) plus PR A plus PR B plus these five
  commits applied without conflicts, and the resulting tree equals the fork's
  tree except for the fork's version number. Without PR B, the README commit
  conflicts (it edits text that PR B introduces); without PR A, the client
  commit conflicts (it rewrites the `arm_*_instant` methods). So submit this
  after PR A and PR B are merged, and replace `<PR_A>` and `<PR_B>` below.

### Title

```
Report command results and the partition ready state
```

### Body

```markdown
**Depends on BrianHumlicek/NeoHub#<NEOHUB_PR_D>** (command results, capabilities and the partition ready state in NeoHub's WebSocket API). Applies on top of #<PR_A> and #<PR_B>.

## Summary

Today every arm and disarm action is fire-and-forget: if the panel rejects the command, for example because a zone is open, the action still succeeds and the only trace is `NeoHub server error: ...` in the log. With this PR and a NeoHub that reports command results:

- The arm and disarm actions (`alarm_control_panel.alarm_arm_home` / `alarm_arm_away` / `alarm_arm_night` / `alarm_disarm`, `neohub.arm_home_instant` / `neohub.arm_away_instant`) wait up to 10 s for NeoHub's `command_result` and raise a `HomeAssistantError` when the command fails:
  - an arm command rejected with panel response code 1: "Partition not ready to arm (zone open)" (translation key `not_ready_to_arm`);
  - any other failure: "NeoHub command failed: <NeoHub's message>" (translation key `command_failed`), including no result within 10 s or a dropped connection ("No confirmation from NeoHub within 10 s; check the alarm state").
- Each partition gets a binary sensor "<partition> ready to arm" (translation key `ready_to_arm`, unique_id `<session_id>_partition_<n>_ready`, on the panel device), and the alarm panel entity gets a `ready` attribute.

With an older NeoHub nothing changes: the command frames are byte-identical, nothing is awaited, nothing is raised, and no sensor or attribute is added.

**Behaviour change:** with a new NeoHub, a rejected or unconfirmed arm or disarm now fails the action, so a script or automation step that arms stops there unless it sets `continue_on_error: true`. The README says so.

## Changes

- `pyneohub/client.py`:
  - Reads `capabilities` from every `full_state` and forgets them when the connection drops, so they are re-read after a reconnect.
  - With `command_result` listed, each command gets a `request_id` (uuid4 hex, sent last; `type` stays first) and waits for the matching `command_result` (`COMMAND_RESULT_TIMEOUT = 10`). The future is registered before sending.
  - New `NeoHubCommandError` (`code`, `message`) and its subclass `NeoHubCommandUnconfirmedError` (timeout, connection lost or send failed; raised at once, not after the timeout).
  - Pending commands fail when the connection drops. Late or unknown `command_result` messages are ignored (debug log). `partition_update` now also updates `ready` in the client state.
  - Access codes are never logged.
- `alarm_control_panel.py`: one helper maps `NeoHubCommandError` to `HomeAssistantError` with `translation_domain="neohub"` for all six actions; the `ready` attribute is returned only while NeoHub reports it.
- `binary_sensor.py`: the ready sensor. It is created only for partitions whose state includes `ready`. If NeoHub is updated while Home Assistant runs, it is added with the first `full_state` that carries `ready` (one `full_state` callback, unregistered on unload), named after the partition name from setup like the alarm panel entity, not after a `full_state` that NeoHub sends before it has read the panel's labels. The partition name is a translation placeholder, so several partitions do not get the same name.
- `coordinator.py`: `partition_ready()`. The entities read `ready` from the client state, so a `full_state` without it (NeoHub downgraded) clears the attribute and the sensor shows unknown instead of a stale value.
- `strings.json` / `translations/en.json` (identical): `entity.binary_sensor.ready_to_arm` (name and on/off states) and `exceptions`. `translations/it.json`: Italian (optional commit).
- `README.md` / `README_LIBRARY.md`: the new behaviour, the sensor, and the protocol additions.

Existing unique_ids, entity names, supported features and the state mapping are unchanged. There is no version bump.

## Testing

- `python -m compileall custom_components/neohub` passes on Python 3.14 and 3.13. All modules import on Home Assistant 2026.11.2 and 2026.2.3.
- hassfest from HA core 2026.11.2 and 2026.2.3: 0 invalid integrations; the only output is the existing "Config flows that are discoverable need to set a unique ID" warning.
- Functional tests on a real `hass` instance (2026.11.2 and 2026.2.3) with the integration's real client and a fake NeoHub WebSocket server implementing the protocol; only timing constants were shortened. They cover: success with `request_id`; code 1 on every arm action giving `not_ready_to_arm`; disarm and other rejections giving `command_failed` with the message; the real 10 s timeout and a late answer after it; a dropped connection while waiting (error in well under a second); reconnecting from a new NeoHub to an old one and back (capabilities re-read, attribute removed, sensor unknown, byte-identical frames without waiting); `ready` following `full_state` and `partition_update` (including a ready-only update); the sensor appearing when NeoHub is updated while HA runs, with the setup-time partition name even if the first `full_state` still has default labels; no sensor with an old NeoHub; a script step that arms stopping on a rejection, and carrying on with `continue_on_error: true`; reload and unload; Italian translations; no access code in any log record.
- The previous functional test, unmodified and with an old-style fake NeoHub, gives the same results and the same recorded frames for the built-in actions as before this PR.
- Upgrade test: an installation set up with the previous version and customized (renamed entity IDs and names, labels, areas, aliases, entity options such as the default code, a hidden and a disabled zone, device name and area, entry title) was stopped, the code swapped, and started again. Every existing entity, device and config entry stayed identical in the registries and on disk, and the only change was the new ready sensor. With an old NeoHub there was no change at all. Also run with Home Assistant set to Italian: the sensor is named "<partition> pronta all'inserimento" and its entity ID is built from that name.
- Against a real NeoHub build of the dependency PR, without a panel: `capabilities` is read, a command for an unknown session raises `NeoHubCommandError` with NeoHub's message, and a frame without `request_id` still gets an `error` message.

## Not tested

- On a real panel through NeoHub. Response code 1 for an arm attempt with a zone open was seen on a real PowerSeries Neo panel (Stay arm with no entry delay, door open: rejected with code 1 three times, accepted once the door was closed), but this PR's tests use a fake NeoHub for it. The ready flag was not observed on a panel.
```
