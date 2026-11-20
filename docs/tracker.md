# BotW map tracker

The client serves a local browser tracker at `http://127.0.0.1:38282/`. Checks are
overlaid on the actual in-game terrain map, extracted from your installed Wii U
game. The map works offline and loads automatically. There are no themes, personal
pins, notes, stars, manual checkmarks, image uploads, or browser storage.

## Start the tracker

From the repository root:

```sh
dotnet run --project src/client -- --tracker-only
```

This previews all catalog checks without Cemu or AP. For your seed's enabled
checks, automatic completion updates, and received items, add `--tracker` to the
normal client command:

```sh
dotnet run --project src/client -- --server archipelago.gg:12345 --slot Link --tracker
```

Use your real server/slot and normal client options. Cemu must already be running
with the matching seed pack. Open the printed URL. `--tracker-port 38283` changes
the port; `--tracker-map-dir /path/to/tracker` selects a prepared map directory.

## Prepare the game map once

In the Archipelago Launcher, open **BotW Client → Tracker → Generate map**. The
client uses the content folders from seed pack setup or asks for the base game
content folder. When generation finishes, open the tracker or refresh its page.
**Open tracker in browser** opens the live tracker when connected with tracking
enabled and a catalog preview otherwise. The Launcher uses an available
loopback port and displays the URL for you to copy.

To generate the map from a repository checkout:

```sh
.venv-patcher/bin/pip install -r src/patcher/requirements-tracker.txt
.venv-patcher/bin/python -m src.patcher.build_tracker_map
```

The default looks for BotW under `~/.local/share/Cemu/mlc01/usr/title/`. For other
installations, pass `--cemu-data /path/to/Cemu`, or supply extracted content roots:

```sh
.venv-patcher/bin/python -m src.patcher.build_tracker_map \
  --base /path/to/base/content --update /path/to/update/content
```

The exporter decodes the game's fully revealed `MapTex1` tiles, writes a
6720×5600 WebP background, and extracts shrine/tower map landmarks into `map.json`.
Fog variants are excluded. Use `--lod 2` or `--lod 3` for smaller backgrounds.
The exporter writes both files to the installed client's map directory by default.
On Linux this is `$XDG_DATA_HOME/BotWAP/tracker/`, with `~/.local/share` as the
default data directory. On Windows it is `%LOCALAPPDATA%\BotWAP\tracker\`.
For repository previews, the client also checks `out/tracker/` relative to the
working directory and executable's ancestors. Use `--output out/tracker` if you
want to export there. Restart the tracker after rebuilding the map.

The full map's X ±6000, Z ±5000 bounds agree with the
[BotW Object Map coordinate system](https://github.com/zeldamods/objmap/blob/master/src/util/map.ts).
Game artwork belongs to Nintendo.

## Map and checks

Drag to pan; scroll or use +/− to zoom. Arrow keys pan; keyboard +/− also zoom.
Search by check name or region, and filter by region, check type, item conditions,
or completion. Hover over markers for names. Selecting a list entry focuses it.

Overworld markers use catalog X/Z coordinates. Shrine chests are anchored to the
shrine's actual overworld entrance, labeled as interior checks in their details.
A numbered marker groups checks at the same entrance; click it to select an
individual check. Markers remain aligned with the map while panning and zooming.
Checks with no verified world landmark remain available in the list.

Completion comes from the client's journal and Archipelago. The browser cannot
submit checks, grant items, or change the game. The current catalog has 416 checks;
387 have verified world or entrance positions with the installed game data.
The remaining 29 are list-only. A live seed may enable a smaller subset.

## Progression and item conditions

The item panel displays received AP items and statically applied starting items,
counting starting items once when replayed in the AP history. Native delivery can
still be queued; the processed-receipt counter and delivery status reflect that.
These are logical counts, not a scan of consumable items or weapon durability.

Check details show item/category counts, including progressive requirements and
AND/OR alternatives. Unsupported or unknown rules show a review message. Tower
items are ignored as access items; champion items are also ignored in Champions'
Ballad item expressions, matching the world rules.

Item hints do not compute full reachability. Region entrances, story events,
environmental supplies, extra tower traversal rules, DLC gates, and goal
prerequisites can impose additional conditions. Randomized item placements are
not exposed.

The loopback server exposes read-only snapshots. HTTP handlers never access Cemu
or submit AP commands. Snapshots update roughly once per second; the browser polls
every 1.5 seconds. Reconnect waits can delay updates.

## Verification

```sh
dotnet build src/client
dotnet run --project src/client --no-build -- --self-test-tracker
.venv-patcher/bin/python -m pytest tests/tracker/test_map_export.py -q
node tests/tracker/logic.test.cjs
```

The API tests cover active-seed filtering, snapshot isolation, map bounds,
entrance-only interior pins, and read-only routes. Exporter tests prevent selecting
fog variants. Hint tests cover grammar, counts, and category logic.

For browser tests, start `--tracker-only` with a prepared default LOD 1 map and a
local Chrome session with `--remote-debugging-port=9223`, then run:

```sh
node tests/tracker/browser.test.cjs
```

Browser tests verify loading the game map, absence of personalization controls,
search/type filters, zoom alignment, grouped marker selection, and mobile layout.
They save screenshots under `out/tracker/preview-desktop.png` and
`out/tracker/preview-mobile.png`. Live Cemu tracking and the four-hour gameplay
stress test require separate validation.
