# Unattended Cemu integration test

Run from the repository root on Linux:

```sh
.venv-patcher/bin/python tests/cemu/run.py --output /tmp/botw-cemu-test-001
```

The runner builds the client before launching Cemu. Use a new output directory for each run. Exit code zero means that the real-game
probe observed an inventory increase and the expected location check arrived over
the local AP WebSocket. A timeout, Cemu exit, missing prerequisite or failed
assertion returns nonzero. `--prepare-only` only builds the fixture and reports
`prepared: true, passed: false`.

Requirements: Cemu, .NET 10 with client NuGet dependencies already restored, the patcher Python dependencies, Xvfb, xdotool,
ImageMagick `import`, and a graphics driver supporting OpenGL on Xvfb. No mouse,
controller or keyboard interaction is needed during the run. The private X display
keeps test input away from the user's desktop. On a machine with a hardware-backed
X display, `--display :0` uses it with Vulkan instead; this focuses the test window
and should run in a dedicated desktop session.

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
flag, and sets the saved map to MainField/D-6. It preserves unrelated save records
and rejects missing fields or unsupported save versions. The original archive is
never modified. No copyrighted save or game files are committed.

`--catalog` defaults to `out/chests-dlc-fixed.json`. The patcher verifies the map
checksum, creates one location marker and bundles the current hook with the test
seed identity. The client receives one apple (`Item_Fruit_A`).

## Execution

1. Create a separate Cemu configuration, graphic pack, MLC save and client journal.
   Installed game directories are linked into the test MLC; they are not patched.
2. Start Cemu on a private Xvfb display with OpenGL and a keyboard controller.
3. Send A presses through Continue, save selection and load confirmation, then
   use A to open the chest immediately in front of Link.
4. Attach the production memory reader to the launched PID. Require gameplay tick
   advancement and a nonzero pouch manager before starting delivery assertions.
5. Connect the production AP SDK and ClientBridge to the local WebSocket fixture.
   Require history advancement and an increased apple count/value in the pouch.
6. Require the chest location to arrive at the server through `LocationChecks`.
   The runner does not write outgoing entries or invoke the acquisition hook.
7. Stop only the processes created by the runner and retain the output directory.

The test Cemu child explicitly allows same-user tracing so its sibling client can
access `/proc/PID/mem` under Yama. No system-wide ptrace setting is changed.
`--timeout` bounds the run (default 600 seconds).

## Evidence and limits

`result.json` is the overall result. `probe.json` records the location, received
item, seed fingerprint and before/after pouch measurements. `fixture.json` records
source and generated save hashes. Cemu and client logs, the seed plan, generated
pack, journal and latest `screen.png` remain available for diagnosis.

This is a smoke test for one actor grant and one real chest acquisition. It does
not establish full-pouch behavior, progression coverage, save persistence after
delivery or the four-hour stability target. Repeated runs start from a newly
constructed save and journal. Unit checks for the save editor run with:

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
opened. The run used software OpenGL and the copied 320x180 Graphics preset.
The save-editor unit tests and client regression tests also passed. This records
one end-to-end smoke pass, not the long-session acceptance target.
