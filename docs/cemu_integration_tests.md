# Unattended Cemu integration test

Run from the repository root on Linux, selecting the coverage with `--items`:

```sh
# Fast smoke check: one arrow bundle.
.venv-patcher/bin/python tests/cemu/run.py --items simplified --output /tmp/botw-live-simple

# One item type from each delivery category, including its progressive tiers.
.venv-patcher/bin/python tests/cemu/run.py --items partial --output /tmp/botw-live-partial

# Every implemented item type and every native progressive tier.
.venv-patcher/bin/python tests/cemu/run.py --items full --output /tmp/botw-live-full
```

The default is `simplified`. Current coverage is 1 receipt / 1 type for simplified,
36 receipts / 27 types for partial, and 194 receipts / 181 types for full. Categories
represent delivery behavior: melee, bows, shields, armor, arrows, materials, key
items, rupees, each stat/pouch upgrade, towers, dungeon controls/completion, runes
and their upgrades, camera, sensor, abilities and their upgrades, armor/Master Sword
upgrades, Travel Medallion, motorcycle, and One-Hit Obliterator. Full mode derives
its item list from the production world reference and shares the client's native
profiles; new items therefore cannot silently disappear from coverage.

Use a new output directory for every run. The runner builds the client and uses
one Cemu launch for the entire selected suite. Exit zero requires every planned
receipt to pass independent live-state assertions and a real chest location check
to reach the local AP server. Failure stops immediately and preserves completed
item evidence; remaining receipts are not reported as passed. `--prepare-only`
creates the fixture without running Cemu and reports `prepared: true, passed: false`.

Requirements: Cemu, .NET 10 with client NuGet dependencies already restored, the
patcher Python dependencies, an X11 display, xdotool and ImageMagick `import`.
The runner uses `DISPLAY` by default and starts Cemu with Vulkan. It focuses the
Cemu window to send controller input, so the screen appears while the test runs.
No manual input is needed. Use `--display :0` to select another X display. Pass
`--headless` only when no usable display is available; that mode uses Xvfb and
software OpenGL.

## Fixture

The runner reads the installed European Wii U v208 base game, update and DLC under
`~/.local/share/Cemu/mlc01/usr/title`. It reads settings from `~/.config/Cemu`.
When the installed community Graphics pack is available, the runner copies it
into the test profile and selects 320x180 rendering to reduce software GPU load.
Override these roots with `--cemu-data` and `--cemu-config`.

The default save source is the existing local backup
`out/botw-save-backup-20261005-014705.zip`; override it with `--save-source`.
This is a source save, not a prebuilt test save. The runner creates a custom copy
of slot 0, positions Link in front of stone chest `2009260213`, resets its opened
flag, and sets the saved map to MainField/D-6. In this isolated save, it clears the
pouch, native item ownership/unlock flags and wallet, initializes hearts/stamina
and inventory slot counts, and resets fountain revival flags (armor rank itself
is transient). This prevents an existing inventory or capped upgrade from masking
a delivery failure. It preserves unrelated save records
and rejects missing fields or unsupported save versions. The original archive is
never modified. No copyrighted save or game files are committed.

`--catalog` defaults to `out/chests-dlc-fixed.json`. The patcher verifies the map
checksum, creates one location marker and bundles the current hook with the test
seed identity. The selected suite is written into `scenario.json` with item IDs, names, categories, receipts and production delivery mappings.

## Execution

1. Create a separate Cemu configuration, graphic pack, MLC save and client journal.
   Installed game directories are linked into the test MLC; they are not patched.
2. Start Cemu on the selected X display with Vulkan and a keyboard controller.
3. Send A presses through Continue, save selection and load confirmation, then
   use A to open the chest immediately in front of Link.
4. Attach the production memory reader to the launched PID as soon as possible.
   Require a changing gameplay heartbeat and a live pouch manager.
5. Connect the production AP SDK and ClientBridge to the local WebSocket fixture,
   then wait for the chest's real `LocationChecks`. Continue A presses through the chest reward popup, stopping
   after the first receipt is verified.
6. Release one AP receipt at a time. Before delivery, independently read its pouch
   values or native GameData flags. Wait for the production bridge to acknowledge
   delivery, then verify the expected pouch quantity/durability, wallet/stat delta,
   or selected native tier's flags. After verification, armor is removed through
   the native pouch API and its absence is checked, keeping full coverage within
   the game's armor capacity without relaunching Cemu. Verify upgraded key items exist and replaced
   champion base items are absent. Record explicitly when a shared earlier grant
   already owns the highest tier.
7. Stop only the processes created by the runner and retain the output directory.

Efficiency: the probe starts immediately instead of waiting 25 seconds; it polls
acknowledgements every 10 ms and advances on observed state, without per-item sleeps.
Observation RPCs execute only between receipts while the production ring is empty.
The controller uses short presses while navigating/loading and stops after the
first verified receipt. Optional screenshots have a short timeout and cannot mask a probe
failure. `--item-timeout` bounds one receipt including observation (default 15
seconds); `--timeout` bounds the entire run including launch (default 600 seconds).
Timeouts are upper bounds, not delays on successful items.

The test Cemu child explicitly allows same-user tracing so its sibling client can
access `/proc/PID/mem` under Yama. No system-wide ptrace setting is changed.
`--timeout` bounds the run (default 600 seconds).

## Evidence and limits

`result.json` is the overall result. `probe.json` contains planned/completed counts,
per-receipt names, categories, elapsed time, capped/cleanup status and before/after
native observations. Armor pouch sums count active pieces as one each, since their
native value field can hold a sentinel rather than a quantity. It is checkpointed after each success, so partial evidence survives a
later failure. `progress.json` reports the current stage and tells the runner when
to stop controller input. `fixture.json` records source/generated save hashes.
Cemu/client logs, scenario, seed plan, generated pack, journal and latest
`screen.png` remain available for diagnosis.

These are live delivery-state tests. Flag ownership and pouch values do not prove
all player-visible effects: banners, ability cooldowns/activation, map visuals and
travel, equipped weapon behavior, persistence across save/reload, full-pouch
queuing and four-hour stability require additional gameplay assertions. A full
suite failure must not be described as full live validation passing.

Run the save-editor and scenario-selection regression tests with:

```sh
.venv-patcher/bin/python -m pytest tests/cemu/test_save.py
```

The save record layout was checked against the
[BotW save editor source](https://github.com/marcrobledo/savegame-editors/blob/master/zelda-botw/zelda-botw.js).
Keyboard mapping uses Cemu's raw Linux key codes; see
[Cemu input handling](https://github.com/cemu-project/Cemu/blob/main/src/gui/wxgui/CemuApp.cpp).

## Recorded validation

On 2026-11-03, an isolated real-game run passed in 223 seconds using the local
v208 installation and generated save. The apple measurement changed from zero
to one, and the AP fixture received location `3074647772` after the chest was
opened. The run used software OpenGL and the copied 320x180 Graphics preset. Hardware
acceleration is now the default; `--headless` opts into the slower fallback.
The save-editor unit tests and client regression tests also passed. This records
one end-to-end smoke pass, not the long-session acceptance target.

On 2026-11-04, the default-display Vulkan run passed in 141 seconds on an NVIDIA
GeForce RTX 4050 Laptop GPU. The Cemu log confirms Vulkan selected that GPU. The
runner exited without leaving Cemu or Xvfb processes behind.

On 2026-11-04, the comprehensive `--items full` suite passed all 194 receipts,
covering 181 item types and 27 delivery categories in 68.82 seconds including
startup and shutdown (65.34 seconds in the probe). Median receipt validation took
0.132 seconds; the slowest took 0.475 seconds. All 107 armor pieces were verified
and removed through the native cleanup path. Evidence is in
`/tmp/botw-live-full-20261104-06/{result,probe,progress}.json` and the accompanying
logs. The live rollout exposed and corrected GameData core pointer indirection,
the typed setter's event permission argument, and armor sentinel measurement.
Earlier failed runs retain their evidence in the preceding numbered directories.

The smaller modes also passed live on the same date: `--items partial` verified
36/36 receipts in 46.96 seconds (`/tmp/botw-live-partial-20261104-01`), and
`--items simplified` verified 1/1 receipt in 38.76 seconds
(`/tmp/botw-live-simplified-20261104-01`). Most time in these modes is game startup.
The five save/scenario regression tests and the client self-tests passed as well.

On 2026-11-05, the live Dungeon009 rune-terminal test passed in 49.28 seconds.
The fixture sent one A press; Link moved about 0.12 m from his spawn position.
`IsGet_Obj_StopTimer` was 0 before AP delivery and became 1 after the
Progressive Stasis receipt. Evidence is in
`out/rune-terminal-live-minwalk-20261105/{result,probe,scenario,fixture}.json`.

## Physical location routes

The item-only commands above remain the fastest delivery regression checks.
For the requested combined location-and-delivery suite, use:

```sh
# One physical chest and one reward type.
.venv-patcher/bin/python tests/cemu/route.py --mode simplified --output /tmp/botw-route-simple

# All delivery categories, then a chest, shrine, tower, miniboss and boss.
.venv-patcher/bin/python tests/cemu/route.py --mode partial --output /tmp/botw-route-partial

# All 194 receipts / 181 types, then every supported location.
.venv-patcher/bin/python tests/cemu/route.py --mode full --output out/botw-route-full

# Full shrine, tower, miniboss and boss coverage, without repeating chest visits.
.venv-patcher/bin/python tests/cemu/route.py --mode full --kinds shrine,tower,miniboss,boss --output out/botw-non-chest-full

# Retry failures and unvisited locations, preserving completed evidence.
.venv-patcher/bin/python tests/cemu/route.py --mode full --output out/botw-route-full --resume
```

Full coverage derives its 415-location manifest from the production catalogs:
187 bound chests, 120 shrine completions, fifteen towers and 93 encounters,
including DLC. It rotates all 181 reward types through the visits and exercises
all progressive tiers of each selected reward. Partial mode first runs the
36-receipt item suite; simplified first runs one receipt. The route's initial
item suite also enables all combat watches and rejects false checks on incoming
grants.

`--kinds` accepts a comma-separated subset of `chest,shrine,tower,miniboss,boss`
while retaining full item coverage and full coverage of the selected location
kinds. This is useful for exercising shrine, tower and combat fixtures after
chest bindings have already been validated.

For each visit, the runner creates an isolated save in the actual target scene,
waits for Link to arrive within six world units of the fixture position, and
physically interacts with the chest, monk or terminal. Combat visits locate the
real nearby enemy and use a **test-pack-only native zero-life aid**, then wait
for its normal death lifecycle to produce the tracked defeat flag. No synthetic
death flag or AP check packet can satisfy a visit. Only after the local AP server
receives the real location check does it send that visit's reward; native pouch,
wallet or progression state must then verify delivery.

To validate rune randomization against the live Great Plateau terminal, run:

```sh
.venv-patcher/bin/python tests/cemu/run.py --rune-terminal Dungeon009 --items simplified --output /tmp/botw-rune-stasis-live
```

The fixture places Link 0.9 m from Owa Daim's terminal and sends one A press.
It verifies that the vanilla Stasis ownership flag remains clear before
releasing the AP `Progressive Stasis` receipt, then confirms the flag changes
through AP delivery. The test expects no physical location check from the rune
terminal. Use a fresh output directory for each run.

Travel positioning, story/spawn prerequisites, night-time Stalnox setup, the
combat life aid and shortened monk cinematics are fixture assistance. This suite
validates physical bindings, event dispatch and delivery; it does not certify
natural puzzle traversal, combat tactics or the AP logical access rules. Those
rules have separate world tests. Production packs contain neither the test RPC
helpers nor the shortened cinematic entry. The ordinary monk cinematic also has
a separate live regression case.

Each visit uses a fresh emulator/save so unrelated inventory, previously opened
chests and boss progression cannot mask errors. The default per-location deadline
is 120 seconds; success advances immediately. Override it with
`--location-timeout`. A full physical run takes substantially longer than the
single-session item-only full suite because loading hundreds of scenes costs
real time. Use partial during development and resume full runs to avoid repeating
successful visits.

The route currently starts a fresh Cemu/game process for each physical visit.
Changing only Link's live position is not a safe substitute: v208 actor position
fields are physics outputs and are overwritten, while repeated calls to
`Player::SetPosition` destabilize the player. The game has a `GameRomCamera`
`Demo_Warp` cinematic action, but the harness has no verified way to invoke that
action as a test command or to use it for a map transition. Until a game-owned
warp path is proven in a live session, per-visit startup remains the reliable
fixture. The item-only full suite already reuses one session for all receipts.

Successful visits discard their extracted emulator profiles to bound disk use;
the generated pack zip, logs, screenshots, journals and JSON evidence remain.
Failures retain their complete runtime. Use `--keep-runtime` to retain everything.
Prefer a disk-backed output such as `out/botw-route-full` for exhaustive runs.

`manifest.json` records every planned location/reward. `result.json` records each
visit's name, kind, evidence file, pass/failure and totals. A full pass requires
**every** manifest entry to pass. Failed or unvisited locations are never counted
as successes. `--manifest-only` enumerates coverage without starting Cemu and does
not claim live validation. Resume rejects changes to the location/reward manifest, native delivery contract
or hook/client source; use a fresh output directory after changing those.

A focused physical test can be run with:

```sh
.venv-patcher/bin/python tests/cemu/run.py --location-id 0xC0100000 --fast-fixtures --output /tmp/botw-one-shrine
.venv-patcher/bin/python tests/cemu/run.py --location-id 0xC2000000 --assisted-combat --output /tmp/botw-one-boss
```

`--reward 'item name'` chooses the post-check reward; the default is Arrows (10).
`--completion tower` retains the separate negative regression: receiving the
tower item first must emit no check, then physical terminal activation must do so.

## Live expansion evidence (2026-11-04)

The full item suite passed again with all 93 defeat watches enabled: 194 receipts,
181 types, 70.5 seconds including startup, and no false encounter checks.
A physical tower activation passed after its AP tower grant. A normal physical
Tah Muhl monk completion passed without a vanilla Spirit Orb; its assigned arrow
reward verified after the check (107.2 seconds including startup). The shortened
fixture also passed. A native-assisted Hinox defeat and a Windblight defeat each
produced their real AP check and verified the subsequent reward (36.8 seconds
each including startup).

These representative passes do not certify every location or the four-hour
stability target. Consult the aggregate route result for exhaustive visit status.

The all-checks production overlay loaded and passed the combined item isolation
probe on 2026-11-04: all 194 receipts and 181 item types, with the 415-location
pack enabled, completed in 110.4 seconds including startup and shutdown. This
also verified that incoming tower items and unrelated completion flags do not
emit checks. The final overlay is built from the current catalogs by
`/tmp/botw_build_all_checks.py` and written to
`out/all-checks-validation-20261104.zip`.

Representative native-assisted combat validation also passed for a Stone Talus,
Molduga, Hinox, Fireblight, Thunderblight and Dark Beast Ganon. Stalnox,
Waterblight, Calamity Ganon and Maz Koshia remain unresolved in the automated
fixtures: their real actors did not reach a valid active/death state or the
fixture could not establish the game's spawn prerequisites before timeout.
Those cases are recorded as failures under
`out/encounter-validation-20261104/`; they are not counted as validated kills.
The production location signals are still native save-backed death indicators,
and the deterministic catalog, hook and world tests pass, but these four live
scenarios need a game-valid fixture before claiming complete physical coverage.
