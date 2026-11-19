# Live goal acceptance tests

## Sequential Divine Beast route

```sh
.venv-patcher/bin/python tests/cemu/beasts.py --output /tmp/botw-beast-route --display :0
```

This check-only route preserves the client journal across early Ganon, Windblight,
Fireblight, Waterblight, Thunderblight, and repeated Ganon encounters. It requests
a real menu save after each Blight and uses that save for the next position edit.
It stops if no changed save is written or if previously defeated Blight flags
are absent from disk. Encounter assistance reduces native actor life; completion
flags and AP checks must come from the game's death lifecycle.
Each encounter starts with 30 full hearts. Before opening the save menu it waits
90 seconds without controller input after observing the check. Override this with
`--post-fight-wait SECONDS` if another encounter takes longer.

Victory must remain locked through the first three Blights. With the current
production semantics, the fourth Blight unlocks Victory because the early Ganon
check is already recorded; the final Ganon encounter verifies the repeated kill.
This is Blight defeat coverage, not activation of each Beast's post-fight terminal.
The save/menu handoff is under validation; a failed handoff leaves the route
incomplete and must not be reported as a successful full route.

## Automated live smoke tests

Run both Dark Beast Ganon encounter cases automatically:

```sh
.venv-patcher/bin/python tests/cemu/goals.py --output /tmp/botw-ganon-goals --display :0
```

This positions an isolated save at Dark Beast Ganon and uses native zero-life
assistance, then requires the actual death flag and physical AP check. It tests
Victory with no prerequisites and withholding Victory with an uncollected chest
prerequisite. This validates the encounter lifecycle and client gate, rather than
normal bow combat or the generated Divine Beast/trial requirement lists.
The combined `result.json` only passes when both cases pass.

Shader and GPU driver caches persist in `out/cemu-test-cache` by default; override
with `--shader-cache PATH`. Saves, journals and packs remain isolated per run.
The first visit to new shader variants still compiles them. Keep the graphics
backend, driver and resolution consistent to maximize cache reuse.

The Cemu runner can test completion and locking automatically, using a real
physical chest as a fixture goal and the real AP SDK against its local WebSocket
server:

```sh
.venv-patcher/bin/python tests/cemu/run.py --goal-test complete --output /tmp/botw-goal-complete
.venv-patcher/bin/python tests/cemu/run.py --goal-test locked --output /tmp/botw-goal-locked
```

The complete case requires server status 30 after the physical check. The locked
case includes an uncollected prerequisite and pumps the production bridge for
ten seconds after delivery, failing if any goal status arrives. Both retain the
normal item delivery assertions and record `goal_test` in `probe.json`. Each
command needs a fresh output directory. `--prepare-only` does not execute tests.
These fixtures certify live check-to-goal reporting and prerequisite gating;
they do not certify the Dark Beast encounter, production option requirements,
reconnects, or save/load. The cases below cover those additional behaviors.

These are manual integration tests against a running Cemu game and a real
Archipelago server. They have not been executed merely by creating this file.
Goal locking means withholding AP Victory until the required checks are recorded.
It does not block entering or fighting Ganon (see `worlds/botw/Options.py`).

## Setup and evidence

Use disposable seeds, saves, and client journal directories, never an ongoing
multiworld save. Back up the save before each branch. Enable the generated pack
for that seed, connect the production client, and retain its console log and the
server log. Record seed, slot, options, client revision, save snapshot, and time
for every case. Use the generated slot data's `goal_location_id` and
`goal_required_location_ids` as the exact expected IDs; do not infer requirements
from the option label alone.

Observe server-side checked locations and client status (CLIENT_GOAL = 30).
The client message `Reported CLIENT_GOAL to Archipelago after the goal location
check.` is supporting evidence; server status is the completion oracle. Record
before/after checked sets and status for every step. Allow at least ten seconds
of connected active gameplay for negative assertions. A disconnect, stalled
mailbox, or missing server evidence makes a case inconclusive, never passed.
Do not use server check commands, edit completion flags, or inject mailbox events
to certify a physical completion. A prepared save may shorten travel, but the
tested final interaction must occur in gameplay.

## Cases

| ID | Fixture and action | Required result |
| --- | --- | --- |
| G01 | `dark_beast_ganon`; perform an unrelated check, then physically defeat Dark Beast Ganon. | Unrelated check does not finish the slot. Goal check reaches server before status 30; slot then finishes. |
| G02 | `all_divine_beasts`, `boss_sanity: false`; defeat Ganon while at least one Blight defeat check is missing. | Goal check arrives, but status stays below 30. Required Blight checks remain in slot data despite boss sanity being off. |
| G03 | Continue G02; physically complete missing Blight checks, leaving one until last. | Every intermediate state stays unfinished. The last prerequisite causes status 30 without a second Ganon defeat. |
| G04 | Fresh beasts seed; complete all prerequisites before Ganon. Wait, then defeat Ganon. | Prerequisites alone do not finish; Ganon check then finishes. |
| G05 | `all_divine_beasts_and_trials`, Master Trials DLC and Trial of the Sword enabled; complete Ganon and Blights but leave trial completion missing. Then physically complete the trial. | Locked before trial completion; status 30 after the final trial check. Merely receiving a trial-related item does not substitute for the check. |
| G06 | Repeat G05 with Trial of the Sword disabled; separately repeat with Master Trials DLC disabled. | Trial objective is absent from required IDs; recorded Ganon and all required Blights finish each slot. |
| G07 | `all_checks`; prepare a branch with Ganon and every enabled check except one accessible chest checked. Open that chest. | Locked while the chest is missing; chest check unlocks Victory. Disabled checks never appear in required IDs. |
| G08 | From a locked branch, disconnect/reconnect the client, then restart it using the same journal directory. | Goal and existing checks persist; missing prerequisite stays missing; no status 30. Complete the missing physical prerequisite and verify Victory. |
| G09 | From a finished branch, reconnect and restart with the same journal. | Server remains finished; replay sends checks before goal status. Replayed status is allowed; no duplicate physical rewards or new checks. |
| G10 | From a locked branch, save/load and die/reload before completing the missing check. | Slot remains locked and game remains stable. Complete the missing check after reload and verify Victory. |

For G07, preparing all prior checks is expensive. If that fixture is unavailable,
mark G07 not run; a reduced check set does not certify the full all-checks goal.
For G02/G03 use a disposable save capable of continuing after an early Ganon
fight; preserve the client journal across any necessary pre-fight save restore.

## Result record

For each ID record PASS, FAIL, NOT RUN, or INCONCLUSIVE, with evidence paths,
missing prerequisite IDs, goal check timestamp, final prerequisite timestamp,
and first server status-30 timestamp. A premature status 30 is a failure even
if the run eventually completes. Missing required DLC or unavailable save
fixtures must remain NOT RUN. Report overall completion only when all applicable
cases pass; include explicit exclusions for unavailable fixtures.
