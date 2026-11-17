# Upstream PR drafts

> **Nothing in this file has been submitted.** No PR, issue or comment may be
> opened or posted upstream without the owner's explicit OK.

Target repository: `BrianHumlicek/NeoHub-Home-Assistant-Integration`, base
branch `master` (at `6ebc3e0` when this was written; check before submitting).

Neither PR is meant to come from the fork's working branch, which also carries
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
