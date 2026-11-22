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
4. `Add Italian translation` (leave out: the fork removed it again in
   commit 11; nothing else depends on it)
5. `README: command results, ready to arm, protocol additions`
6. `pyneohub: mark an orphaned command_result future as retrieved`
7. `Add ready sensors only for partitions with an alarm panel entity`
8. `README: ready attribute triggers, NACK results, ready sensor scope`
9. `it.json: quote the alarm state names in the service descriptions` (leave
   out, together with commit 4)
10. `Drop the ready attribute from the alarm panel entity`
11. `Remove the Italian translation` (leave out, together with commits 4 and 9)
12. `Use the neutral text "Partition not ready to arm" for code 1`

Commits 6-10 came out of review. Commit 10 removes the alarm panel entity's
`ready` attribute that commit 3 added and commits 5 and 8 documented, so the
ready flag is only on the binary sensor; the subjects of commits 3 and 8 still
name the attribute. Leave out `Bump version to 1.2.0` and `Bump version to 1.2.1` (fork only),
commits 4, 9 and 11 (the fork's code is English only) and the
`UPSTREAM_PRS.md` commits.

Commit 12 came later: the panel's description of response code 1 is generic
and names no cause, so the text no longer says "(zone open)". It goes together
with the same text change in the NeoHub PR (section D of the NeoHub fork's
`UPSTREAM_PRS.md`); only the text changes, not the mapping of code 1. Commit 5
also adds the Features line "English and Italian translations", which commit
11 removes again; when commit 11 is left out, drop that line from commit 5 on
the PR branch.

Dependencies:

- **NeoHub:** this needs the NeoHub PR drafted as section D of the NeoHub
  fork's `UPSTREAM_PRS.md` (request_id / command_result, capabilities, partition
  ready). Open it first and put its number in place of `<NEOHUB_PR_D>`. Without
  it nothing breaks: the integration only uses the new features when NeoHub
  lists them in `capabilities`.
- **This repository:** the commits apply on top of PR A and PR B. In a scratch
  clone, upstream `master` (`6ebc3e0`) plus PR A plus PR B plus these ten
  commits applied without conflicts, and the resulting tree equals the fork's
  tree except for the fork's version number and this file. Without commits 4
  and 9 (Italian) the other eight also apply cleanly. Without PR B, the README commit
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
  - an arm command rejected with panel response code 1: "Partition not ready to arm" (translation key `not_ready_to_arm`);
  - any other failure: "NeoHub command failed: <NeoHub's message>" (translation key `command_failed`), including a refusal by the panel interface (NACK), no result within 10 s or a dropped connection ("No confirmation from NeoHub within 10 s; check the alarm state").
- Each partition that has an alarm panel entity gets a binary sensor "<partition> ready to arm" (translation key `ready_to_arm`, unique_id `<session_id>_partition_<n>_ready`, on the panel device; added disabled when that partition's alarm panel entity is disabled). The alarm panel entity gets no new attribute, so state triggers on it do not fire when only the ready flag changes.

With an older NeoHub nothing changes: the command frames are byte-identical, nothing is awaited, nothing is raised, and no sensor is added.

**Behaviour change:** with a new NeoHub, a rejected or unconfirmed arm or disarm now fails the action, so a script or automation step that arms stops there unless it sets `continue_on_error: true`. The README says so.

## Changes

- `pyneohub/client.py`:
  - Reads `capabilities` from every `full_state` and forgets them when the connection drops, so they are re-read after a reconnect.
  - With `command_result` listed, each command gets a `request_id` (uuid4 hex, sent last; `type` stays first) and waits for the matching `command_result` (`COMMAND_RESULT_TIMEOUT = 10`). The future is registered before sending.
  - New `NeoHubCommandError` (`code`, `message`) and its subclass `NeoHubCommandUnconfirmedError` (timeout, connection lost or send failed; raised at once, not after the timeout).
  - Pending commands fail when the connection drops. Late or unknown `command_result` messages are ignored (debug log). If the connection drops while a send is still in progress and the send then fails, the orphaned future's exception is retrieved, so asyncio logs no "Future exception was never retrieved". `partition_update` now also updates `ready` in the client state.
  - Access codes are never logged.
- `alarm_control_panel.py`: one helper maps `NeoHubCommandError` to `HomeAssistantError` with `translation_domain="neohub"` for all six actions. The entity gets no new state attribute.
- `binary_sensor.py`: the ready sensor. It is created only for partitions that got an alarm panel entity at setup and whose state includes `ready`, and with `entity_registry_enabled_default=False` when that alarm panel entity is disabled in the entity registry. A partition or session that first appears later gets neither entity until a reload. If NeoHub is updated while Home Assistant runs, it is added with the first `full_state` that carries `ready` (one `full_state` callback, unregistered on unload), named after the partition name from setup like the alarm panel entity, not after a `full_state` that NeoHub sends before it has read the panel's labels. The partition name is a translation placeholder, so several partitions do not get the same name.
- `coordinator.py`: `partition_ready()`. The ready sensor reads `ready` from the client state, so a `full_state` without it (NeoHub downgraded) makes the sensor show unknown instead of a stale value.
- `strings.json` / `translations/en.json` (identical): `entity.binary_sensor.ready_to_arm` (name and on/off states) and `exceptions`. No other languages.
- `README.md` / `README_LIBRARY.md`: the new behaviour, the sensor, and the protocol additions.

Existing unique_ids, entity names, supported features and the state mapping are unchanged. There is no version bump.

## Testing

- `python -m compileall custom_components/neohub` passes on Python 3.14 and 3.13. All modules import on Home Assistant 2026.11.2 and 2026.2.3.
- hassfest from HA core 2026.11.2 and 2026.2.3: 0 invalid integrations; the only output is the existing "Config flows that are discoverable need to set a unique ID" warning.
- Functional tests on a real `hass` instance (2026.11.2 and 2026.2.3) with the integration's real client and a fake NeoHub WebSocket server implementing the protocol; only timing constants were shortened (76 checks per version, all passing after commits 6-10 too). They cover: success with `request_id`; code 1 on every arm action giving `not_ready_to_arm`; disarm and other rejections giving `command_failed` with the message; the real 10 s timeout and a late answer after it; a dropped connection while waiting (error in well under a second); reconnecting from a new NeoHub to an old one and back (capabilities re-read, sensor unknown, byte-identical frames without waiting); `ready` following `full_state` and `partition_update` (including a ready-only update); the sensor appearing when NeoHub is updated while HA runs, with the setup-time partition name even if the first `full_state` still has default labels; no sensor with an old NeoHub; a script step that arms stopping on a rejection, and carrying on with `continue_on_error: true`; reload and unload; no access code in any log record.
- Four ready-only `partition_update` frames: the ready sensor follows each of them, the alarm panel entity has no `ready` attribute, and a state trigger on the alarm panel entity without `to:` / `from:` fires 0 times, as with the previous version.
- The previous functional test, unmodified and with an old-style fake NeoHub, gives the same results and the same recorded frames for the built-in actions as before this PR.
- Upgrade test: an installation set up with the previous version and customized (renamed entity IDs and names, labels, areas, aliases, entity options such as the default code, a hidden and a disabled zone, device name and area, entry title) was stopped, the code swapped, and started again. Every existing entity, device and config entry stayed identical in the registries and on disk, and the only change was the new ready sensor. With an old NeoHub there was no change at all.
- Upgrade test with four partitions whose alarm panel entities 2-4 were disabled by the user: only partition 1's ready sensor is enabled; the other three are added disabled by the integration. Every existing registry entry is unchanged.
- A later `full_state` with a new partition or a second session adds no ready sensor and no device.
- A drop of the connection while a send is still in progress (forced interleaving): the action fails with "Could not send the command to NeoHub", and asyncio logs no "Future exception was never retrieved".
- Frames captured from the dependency PR's handler, replayed verbatim into a real `hass` (41 checks per version).
- Against a real NeoHub build of the dependency PR, without a panel: `capabilities` is read, a command for an unknown session raises `NeoHubCommandError` with NeoHub's message, and a frame without `request_id` still gets an `error` message (35 checks).

## Not tested

- On a real panel through NeoHub. Response code 1 for an arm attempt with a zone open was seen on a real PowerSeries Neo panel (Stay arm with no entry delay, door open: rejected with code 1 three times, accepted once the door was closed), but this PR's tests use a fake NeoHub for it. The ready flag was not observed on a panel.
```

---

## PR D: Panel trouble sensor

Commits to cherry-pick, in this order:

1. `Store the partition trouble flag from NeoHub`
2. `Add a trouble binary sensor per partition`
3. `README: panel trouble sensor, troubles in the WebSocket API`
4. `README: describe NeoHub's trouble re-reads and trouble_types accurately`

Commit 4 corrects the README text of commit 3 after review (interval 0 turns
off both NeoHub re-reads; `trouble_types` is reserved); it can be squashed into
commit 3.

Leave out `Bump version to 1.3.0` (fork only) and the `UPSTREAM_PRS.md`
commits. `Use the neutral text "Partition not ready to arm" for code 1` belongs
to PR C (commit 12), not to this PR.

Dependencies:

- **NeoHub:** this needs the NeoHub PR drafted as section E of the NeoHub fork's
  `UPSTREAM_PRS.md` (the `partition_troubles` capability and `troubles` in
  `full_state` and `partition_update`). Open it first and put its number in
  place of `<NEOHUB_PR_E>`. Without it nothing breaks: the sensor is only
  created when NeoHub lists `partition_troubles`.
- **This repository:** the commits apply on top of PR C. In a scratch clone,
  upstream `master` (`6ebc3e0`) plus PR A, PR B, the eight English-only commits
  of PR C, PR C's commit 12 and these four commits applied without conflicts;
  they also apply without commit 12. The resulting tree equals the fork's tree
  except for the version number, this file and the Features line about the
  Italian translation (see PR C). Submit this after PR C is merged and replace
  `<PR_C>` below.

### Title

```
Add a binary sensor for the panel trouble state
```

### Body

```markdown
**Depends on BrianHumlicek/NeoHub#<NEOHUB_PR_E>** (the `partition_troubles` capability and the partition `troubles` flag in NeoHub's WebSocket API). Applies on top of #<PR_C>.

## Summary

With a NeoHub that lists `partition_troubles` in `full_state.capabilities`, each partition that has an alarm panel entity gets a binary sensor "<partition> trouble":

- translation key `trouble`, device class `problem` (on = the panel reports a trouble, such as AC power loss or a low battery; not yet observed on a real panel), unique_id `<session_id>_partition_<n>_trouble`, on the same device as the alarm panel entity;
- created at setup, or with the first `full_state` that lists the capability when NeoHub is updated while Home Assistant runs, named after the setup-time partition name; added disabled when that partition's alarm panel entity is disabled;
- if NeoHub also sends `trouble_types` (a list of strings), the sensor shows it as the attribute `trouble_types`; the key is reserved for a later NeoHub version (the NeoHub PR this depends on does not send it), and without it the sensor has no extra attribute.

The alarm panel entity does not change: no new attribute, so a trouble change alone does not change its state object and does not fire state triggers on it. With an older NeoHub nothing changes and no sensor is added.

This lets an automation tell "the panel reports a trouble" apart from "a zone is open" when an arm command is rejected as not ready.

## Changes

- `pyneohub/client.py`: `CAPABILITY_PARTITION_TROUBLES = "partition_troubles"`. `partition_update` also copies `troubles` and `trouble_types` into the client state when present; an update without them keeps the last value, as for `ready`.
- `coordinator.py`: `partition_troubles()` (bool or None) and `partition_trouble_types()` (list or None), on a small shared lookup helper also used by `partition_ready()`.
- `binary_sensor.py`: `DscPartitionTroubleSensor`, created by the same code path and the same single `full_state` callback as the ready sensor (same setup-time names, same rule for disabled alarm panel entities, no sensor for a partition that appears after setup). It reads `troubles` from the client state, so a `full_state` without it (NeoHub downgraded) makes it show unknown.
- `strings.json` / `translations/en.json` (identical): `entity.binary_sensor.trouble` (name, and the `trouble_types` attribute name).
- `README.md` / `README_LIBRARY.md`: a "Panel trouble" section, the entity model table, and `partition_troubles`, `troubles` and `trouble_types` in the WebSocket API section.

Existing unique_ids, entity names, supported features, the state mapping and the command frames are unchanged. There is no version bump.

## Testing

- `python -m compileall custom_components/neohub` passes on Python 3.14 and 3.13. All modules import on Home Assistant 2026.11.2 and 2026.2.3.
- hassfest from HA core 2026.11.2 and 2026.2.3: 0 invalid integrations; the only output is the existing "Config flows that are discoverable need to set a unique ID" warning.
- A new functional test on a real `hass` instance (2026.11.2 and 2026.2.3) with the integration's real client and a fake NeoHub WebSocket server in three protocol generations (no capabilities; `command_result` + `partition_ready`; plus `partition_troubles`); only timing constants were shortened. It covers: the sensor's registry entry (unique_id, translation key, device class, device), name and states from `full_state`; `troubles` following `partition_update` frames, including troubles-only frames and frames without `status` and `ready`; an update without `troubles` keeping the last value; a non-bool value giving unknown; `trouble_types` shown on the trouble sensor only, updated, kept, and gone after a `full_state` without it; NeoHub downgraded while HA runs (unknown), a reload against an older NeoHub (unavailable, registry entry kept) and NeoHub upgraded again (sensor back); NeoHub updated while HA runs (sensors added with the setup-time names, and added disabled for a partition whose alarm panel entity was disabled); a partition that reports the capability but no `troubles` (unknown); one `full_state` callback per entry, unregistered on unload; no access code in any log record.
- Troubles-only and `trouble_types`-only frames give 0 `state_changed` events on the alarm panel entity and 0 runs of a state trigger on it without `to:` / `from:` (and with `to: null`); a status change in the same test does fire both automations. With a test-only change that adds `troubles` as an alarm panel attribute, these checks fail, as they should. Against the previous version of the integration the sensor checks fail and the alarm checks still pass.
- The existing functional tests (command results, ready sensor, adversarial probes, the ready-only trigger test, the legacy built-in actions test with byte-identical frames, and the replay of NeoHub's captured frames) give the same results as before this PR against a NeoHub without `partition_troubles`, apart from the "not ready" text of PR C's commit 12.
- Upgrade tests (stop, swap the code, start) from the previous two versions, customized as in PR C (renamed entity IDs and names, labels, areas, aliases, the default code option, a hidden and a disabled zone, device name and area, entry title, and the existing ready sensor renamed), with one partition and with four partitions whose alarm panel entities 2-4 were disabled by the user: every existing entity, device and config entry stays identical in the registries and on disk; the only new entities are the trouble sensors (plus the ready sensors when the previous version had none), on the alarm's device, enabled for partition 1 and added disabled for partitions 2-4. With a NeoHub without `partition_troubles` no trouble sensor is added; with unchanged code nothing is added.

## Not tested

- On a real panel through NeoHub. The trouble flag was not observed on a panel; the tests use a fake NeoHub. How quickly the sensor follows the panel depends on NeoHub: its connect-time read, its periodic re-read (default 60 s, at least 10 s) and its re-read after an arm rejected as not ready; with the interval at 0 neither re-read runs, and NeoHub skips re-reads while a command is waiting for the panel or the panel is being programmed.
- `trouble_types` from a real NeoHub: the tests send it from the fake server only.
```

---

## Addendum 4: PR E, PR F and PR G

Three separate drafts, one per NeoHub PR they depend on. They apply in this
order on top of PR D: PR E, then PR F, then PR G. In a scratch clone the code
commits of the three PRs, cherry-picked in that order onto the fork's previous
tip, gave the fork's current code tree exactly; PR F's first commit conflicts
without PR E (both add constants next to `CAPABILITY_PARTITION_TROUBLES`), and
PR G conflicts without PR E and PR F. So submit them in this order, each after
the previous one is merged.

The README changes of all three are in one fork commit, `README: keypad alarms,
siren and memory, trouble types, FAP, protocol`, plus the follow-up `README:
keypad alarm times in NeoHub's format` (PR F only). On the PR branches split
them as listed under each PR. Leave out `Bump version to 1.4.0` (fork only)
and the `UPSTREAM_PRS.md` commits.

Review fixes, after the drafts were written (each in its PR's commit list):
`Check that the caller may control the alarm panel before a FAP alarm`,
`Log at WARNING when NeoHub starts or stops accepting FAP commands` and
`README: FAP alarms and AI agents` (PR G); `Fire a keypad alarm once when its
replay and its message both arrive` and `Fire keypad alarms that arrive
before the event entity exists` (PR F). Squash them into the PR's commits if
preferred.

The NeoHub PRs are drafted in the NeoHub fork's `UPSTREAM_PRS.md`; their
numbers go in place of the placeholders below. The message shapes used here
are the ones decided for NeoHub 0.4.0: `code_kind` in `command_result`;
`trouble_types`, `siren` and `alarm_memory` per partition; `keypad_alarm`
messages and `last_keypad_alarm` per session; `activate_fap` with `partition`,
`fap_type` and a required `request_id`; capabilities in the order
`command_result`, `partition_ready`, `partition_troubles`, `trouble_types`,
`keypad_alarms`, `partition_siren_memory`, and `fap` last only while FAP
commands are turned on in NeoHub.

### PR E: Tell NACK codes from panel response codes

Commits to cherry-pick:

1. `pyneohub: read code_kind; "not ready" only for response code 1`
2. From the README commit, only: the paragraph about NACK codes and response
   codes at the end of "Errors", the new example text in the "Any other
   rejection" row of the Errors table, the `code_kind` bullet in
   `command_result` (without the FAP parts of the next bullet) and
   `"code_kind": "response"` in its example.

Depends on **the NeoHub PR "clearer rejection messages" (`code_kind`, text maps
for response and NACK codes)**: `<NEOHUB_PR_REJECT>`.

#### Title

```
Tell NACK codes from panel response codes in command results
```

#### Body

```markdown
**Depends on BrianHumlicek/NeoHub#<NEOHUB_PR_REJECT>** (`code_kind` in `command_result`). Applies on top of #<PR_D>.

## Summary

The panel's response codes and the panel interface's NACK codes are two number ranges that overlap with different meanings (response 1 is what the panel answers to an arm command when the partition is not ready; NACK 1 is an invalid command length). With the NeoHub PR, `command_result` reports the NACK code in `code` as well and says which kind it is in `code_kind` (`"response"`, `"nack"`, or `null` when `code` is `null`).

- `NeoHubCommandError` gets `code_kind` (`None` when NeoHub reports no code or does not send `code_kind`).
- An arm command rejected with code 1 raises "Partition not ready to arm" (`not_ready_to_arm`) only when `code_kind` is `"response"` or not reported (an older NeoHub, which only reports response codes in `code`, so its behaviour is unchanged). NACK 1 and every other failure raise "NeoHub command failed: <NeoHub's message>" (`command_failed`), for example "NeoHub command failed: Invalid access code".
- If NeoHub sends no message, the fallback text names the NACK code for a NACK.

## Testing

- `python -m compileall`, imports on Home Assistant 2026.11.2 and 2026.2.3, hassfest from both cores: 0 invalid integrations.
- Real `hass` with the real client and a fake NeoHub, on both versions: response 1 on arm -> `not_ready_to_arm`; NACK 1 on arm -> `command_failed` with NeoHub's text; code 1 without `code_kind` on arm -> `not_ready_to_arm` (as before); response 17 and NACK 9 -> `command_failed` with NeoHub's text; response 1 on disarm -> `command_failed`; an unknown `code_kind` string -> `command_failed`; `code` null -> `command_failed`; `NeoHubCommandError.code_kind` checked for each case. The previous functional tests, whose fake NeoHub sends no `code_kind`, pass unchanged.

## Notes

- An explicit `"code_kind": null` next to a numeric `code` (which the NeoHub PR never sends) is treated like a missing `code_kind`.
- Integration versions without this PR keep working with the new NeoHub, but show "Partition not ready to arm" for an arm command refused with NACK 1, because that NeoHub now reports NACK codes in `code`.
```

### PR F: Keypad alarm events, siren and alarm memory sensors

Commits to cherry-pick, in this order:

1. `Store the partition siren and alarm memory flags from NeoHub`
2. `Add siren and alarm in memory binary sensors per partition`
3. `Handle keypad_alarm messages from NeoHub`
4. `Add a keypad alarm event entity per partition`
5. From the README commit: the Features lines for trouble types, keypad
   alarms and siren and alarm memory; the "Panel trouble" changes (trouble
   types table, flag turning on sooner); the "Keypad alarms" and "Siren and
   alarm memory" sections; the three Entity Model rows; the note under "Alarm
   Panel States"; in the WebSocket API the `full_state` example and the
   capabilities list without the `fap` bullet, the `partition_update` text and
   the `keypad_alarm` message; the `state` and `register_keypad_alarm_callback`
   lines of `README_LIBRARY.md`.
6. `README: keypad alarm times in NeoHub's format` (squash it into the README
   part of item 5).
7. `Fire a keypad alarm once when its replay and its message both arrive`
8. `Fire keypad alarms that arrive before the event entity exists` (with its
   README part: the keypad alarm limits).

Depends on **the NeoHub PR "trouble types, keypad alarms, siren and alarm
memory"**: `<NEOHUB_PR_ALARMS>`.

Trouble types need no code change here: since PR D the trouble sensor shows
`trouble_types` as an attribute whenever NeoHub sends it. The `trouble_types`
capability changes nothing for the integration, which keys on the field.

#### Title

```
Add keypad alarm events and siren / alarm memory sensors
```

#### Body

```markdown
**Depends on BrianHumlicek/NeoHub#<NEOHUB_PR_ALARMS>** (trouble types, keypad alarms, siren and alarm memory in NeoHub's WebSocket API). Applies on top of #<PR_E>.

## Summary

With a NeoHub that lists the new capabilities, each partition that has an alarm panel entity gets, on the panel device:

- with `keypad_alarms`: an event entity "<partition> keypad alarm" (translation key `keypad_alarm`, unique_id `<session_id>_partition_<n>_keypad_alarm`, event types `fire` and `unknown`, event attribute `code` with the panel's raw alarm type). NeoHub's `keypad_alarm` message fires it; an alarm for a partition Home Assistant does not know (for example 0) is logged as a warning and dropped; any `alarm_type` other than `fire` gives `unknown`.
- with `partition_siren_memory`: binary sensors "<partition> siren" (`sound`, unique_id `..._siren`) and "<partition> alarm in memory" (`problem`, unique_id `..._alarm_memory`), from `siren` and `alarm_memory`; a `partition_update` without them keeps the last value.

They follow the trouble sensor's rules: created at setup or with the first `full_state` that lists the capability, named after the setup-time partition names, added disabled when the partition's alarm panel entity is disabled, unknown (sensors) when NeoHub stops sending the key, unavailable after a reload against an older NeoHub. The alarm panel entity does not change: no new attribute, no `triggered`, no state change for these frames.

**Replay rule.** NeoHub keeps the last keypad alarm per session as `last_keypad_alarm` in `full_state`, so an alarm that happened while the WebSocket was down is not lost. The coordinator remembers the newest keypad alarm time (NeoHub's clock) seen per session in this run. The first `full_state` after the integration starts or reloads only records it and never fires (a restart does not repeat an old alarm); a later `full_state` fires it only if its time is strictly newer; a `keypad_alarm` message updates the newest time. A `keypad_alarm` message whose time is that of an alarm just fired from a `full_state` is not fired again (after a reconnect NeoHub's `full_state` can arrive before its broadcast of the same alarm). Only NeoHub's times are compared.

**Alarms before the entity exists.** A keypad alarm for a partition whose event entity is not added yet (during the setup's stable-state wait, or before the entities of a newly listed capability are added) is kept, at most 10 per partition for 5 minutes, and fired by the entity when it is added, after its first state write. The first-`full_state` rule above keeps an alarm stored at NeoHub from being fired at every start.

The README states that Home Assistant shows no `triggered` for keypad or other alarms (detection relies on the event entity and the siren sensor) and gives trigger forms that skip the event entity's state changes on reconnects, reloads and entity creation: `event.received` where Home Assistant has it, or a state trigger with `not_from: unavailable`, `not_to: [unavailable, unknown]` and a `trigger.from_state is not none` condition.

## Testing

- compileall, imports and hassfest on Home Assistant 2026.11.2 and 2026.2.3: 0 invalid integrations.
- Real `hass` with the real client and a fake NeoHub in seven protocol generations (the previous three, all new capabilities, and each new capability on its own), on both versions (110 checks, 111 on 2026.11.2): each entity only with its own capability; registry entries (unique_ids, translation keys, device classes, device, names), states from `full_state` and `partition_update`, keys kept when missing, non-bool values; `trouble_types` only on the trouble sensor; keypad events for `fire`/3, `unknown`/9 and an unknown `alarm_type`, dropped for partitions 0 and 5 and an unknown session, malformed messages logged; the replay rule (no fire from the first `full_state`, none for an equal or older time, one for a strictly newer time after a reconnect, none on a repeat, a fire when the first `full_state` had none, 7-digit `Z` and `+00:00` times); a reload keeps the restored event state and does not fire; downgrade, reload against an older NeoHub, upgrade while Home Assistant runs (setup-time names, disabled for a disabled alarm entity); 0 `state_changed` events on the alarm panel entity and 0 runs of a state trigger on it without `to:`/`from:` for all new frame kinds; the recommended trigger forms ran exactly once per alarm and never for reconnects, reloads or creation in these sequences (before the review fix, a replay followed by the live message of the same alarm ran them twice).
- Home Assistant restart in two processes, on both versions: the event entity is restored (time, type, code), the first `full_state` does not fire even with a newer `last_keypad_alarm`, and a new `keypad_alarm` fires once.
- Review fixes, on both versions with real `hass` and the real setup wait: a live keypad alarm 1 s into setup fires once when the entity is added (both recommended trigger forms run once), while the older alarm of the first `full_state` does not fire (with that rule removed, it does: the test fails); an alarm for a disabled partition entity is kept and not fired; a replay and the live message of the same alarm, 0 ms and 50 ms apart, fire once; a second live message with the same time still fires.
- Upgrade tests (stop, swap the code, start) from the previous three versions, customized (renamed entity IDs and names, labels, areas, aliases, the default code option, hidden and disabled zones, device name and area, entry title, the ready and trouble sensors), with one partition and with four partitions whose alarm panel entities 2-4 were disabled: every existing entity, device and config entry identical in the registries and on disk; the only new entities are the expected ones, on the alarm's device, enabled for partition 1 and disabled by the integration for 2-4.
- Previous versions against the new NeoHub protocol: they log one warning "Unknown message type 'keypad_alarm'" per message and otherwise ignore it and the new keys.

## Not tested

- On a real panel and against a real NeoHub build of the dependency PR: the tests use a fake NeoHub with the decided message shapes (frames captured from the NeoHub PR's serializer were replayed separately). The keypad alarm type 9 is not identified yet.
- Two keypad alarms in the same millisecond have equal times: after a reconnect the second would count as already seen.
```

### PR G (experimental, only with the owner's explicit OK): `neohub.activate_fap`

Commits to cherry-pick:

1. `Add the experimental neohub.activate_fap service`
2. From the README commit: the FAP Features line, the paragraph about
   `neohub.activate_fap` under "Services", the "FAP alarms (experimental)"
   section, the `activate_fap` WebSocket message, the `fap` capability bullet,
   the FAP parts of the `command_result` bullets, and the `activate_fap` entry
   of `README_LIBRARY.md`.

Review fixes, in this order after commit 2:

3. `Check that the caller may control the alarm panel before a FAP alarm`
4. `Log at WARNING when NeoHub starts or stops accepting FAP commands`
5. `README: FAP alarms and AI agents`

Depends on **the NeoHub PR "FAP command (experimental)"**: `<NEOHUB_PR_FAP>`,
and applies on top of PR E and PR F.

This sends a real alarm and is untested on a real panel. The command layout
comes from `LawPaul/HA_DSC_Neo_ITv2` (GPL-3.0, `ModuleControlActivateFAP` in
`dsc_itv2/messages.py`) through the NeoHub PR; see that PR's draft for the
source check. Decide whether to submit it only after a supervised test with
the monitoring station on test.

#### Title

```
Add an experimental neohub.activate_fap action (Fire / Auxiliary / Panic)
```

#### Body

```markdown
**Depends on BrianHumlicek/NeoHub#<NEOHUB_PR_FAP>** (`activate_fap` and the `fap` capability). Applies on top of #<PR_E> and #<PR_F>.

> **This action triggers a REAL alarm** (as if the F, A or P keys on the keypad were pressed); a monitored panel reports it to the central station. It is experimental and has not been tested on a real panel.

## Summary

- A domain action `neohub.activate_fap`, registered in `async_setup` (with a config-entry-only `CONFIG_SCHEMA`). Every argument is checked before anything is sent; each invalid call raises `ServiceValidationError`: exactly one `alarm_control_panel` entity of a loaded entry (`entity_id` as data or as a target; no `all`, no list of several, no device, area, floor or label), `type` exactly `fire`, `auxiliary` or `panic`, and `confirm` exactly `true`.
- It raises `HomeAssistantError` if NeoHub does not list the `fap` capability (no fallback for an older NeoHub; NeoHub lists it only while FAP commands are turned on in its settings), and with NeoHub's message if the command fails or is not confirmed ("... the alarm may still have been triggered").
- pyneohub `activate_fap()` sends `{"type": "activate_fap", "session_id", "partition", "fap_type", "request_id"}` once and waits for the `command_result`; nothing retries it. The alarm kind is `fap_type` because `type` is the message type. The request and result handling of the partition commands moved into two helpers; their frames and texts are unchanged.
- Every FAP request and its result are logged at Warning, and so is every change of the `fap` capability ("NeoHub at ... accepts FAP commands ..." / "... no longer accepts FAP commands"), so the log shows whether NeoHub accepts them without a test call.
- The caller needs control permission for the alarm panel entity, as for an entity service: an unknown user raises `UnknownUser`, a user without control permission `Unauthorized`, after the arguments are checked and before anything is sent. A domain action does not get that check from Home Assistant by itself; without it a read-only user could raise a real alarm.
- `services.yaml` uses an `entity_id` field with a single-entity selector (not a `target`), so the UI offers exactly one alarm panel entity. There is no button, switch or other entity, and the alarm panel entity does not get the `TRIGGER` feature: entities may be exposed to voice assistants. That keeps it away from the Assist API, but an LLM agent given the admin-only "Home Assistant" LLM API (2026.11) can call any action, this one included; the README says so, and the action's description tells assistants never to call it (not a barrier: NeoHub's setting is).

## Testing

- compileall, imports and hassfest on Home Assistant 2026.11.2 and 2026.2.3: 0 invalid integrations.
- Real `hass` with the real client and a fake NeoHub, on both versions: without `fap` -> `HomeAssistantError`, 0 frames; 33 invalid calls (no entity, two entities, a comma list, `all`, `none`, an empty list, a zone, a number, a template alarm panel, a bare state, a missing entity, a user-disabled alarm entity, type missing / `Fire` / `FIRE` / `fires` / 0 / null / a list, confirm missing / false / `"true"` / 1 / `"yes"` / null, `device_id`, `area_id`, `label_id`, extra keys, `fap_type` instead of `type`, a device target, a target with two entities) -> `ServiceValidationError`, 0 frames each; success in data and target form -> exactly one frame with the keys in order; failures (response 23, NACK 9, setting off, NeoHub's panel timeout text) -> `HomeAssistantError` with NeoHub's message, one frame each; a silent NeoHub -> fails after the client timeout with "... the alarm may still have been triggered", one frame, none later; the socket closed while waiting -> fails at once, and after the reconnect still exactly one frame; the send itself failing -> "Could not send the command to NeoHub (...); the alarm may still have been triggered", no retry; the capability withdrawn -> 0 frames; NeoHub not connected -> 0 frames; 0 changes of the alarm panel entity.
- Review fixes, on both versions: a read-only user -> `Unauthorized` and an unknown user id -> `UnknownUser`, 0 frames each (before the fix: one frame each); a non-admin user with control permission, an admin and a call without user -> one frame each; invalid arguments from a read-only user still give `ServiceValidationError`; the `fap` WARNING once at setup, nothing on a reconnect, once when it is withdrawn and once when it is listed again, none for an entry whose NeoHub never lists it.

## Not tested

- On a real panel. The panel's answer to the command is not documented; the dependency PR's draft says what is known.
```
