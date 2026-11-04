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
