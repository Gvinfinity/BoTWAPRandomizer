# Breath of the Wild APWorld beta

The APWorld generates solo or multiworld seeds for Wii U v208 and writes a
player-specific `.apbotw` patch. Applying that patch to the player's extracted
game produces a Cemu Graphic Pack with seed-bound chest, shrine, tower and
encounter checks, plus the AP engine hook. The .NET client connects to
Archipelago and delivers the supported actor, rupee, capacity, and native
progression items through the shared-memory mailbox.

The beta covers the currently bound catalogs and item table; it does not add
shop checks. The automated suite has verified restrictive fill, generated
patch round-tripping, item delivery state, physical check dispatch, rune
randomization and shrine/tower/combat routes. Four-hour stability, full-pouch
queue behavior, all player-visible banners and natural traversal/combat remain
outside the verified beta scope.

## Chest identity and hook contract

### Goal requirements

The YAML `goal` option controls Victory: `dark_beast_ganon`,
`all_divine_beasts`, `all_divine_beasts_and_trials` (default), or `all_checks`.
All choices require Dark Beast Ganon's defeat. The Beast goals also require
the four Blight defeat checks. With the default goal, The Master Trials DLC,
and `trial_of_the_sword: true` (default), Victory also requires the new
`Trial of the Sword - Completed` check, watched through the saved
`100enemy_Clear_Senior` flag set by the final trial completion event.
Receiving Beast Cleared items or Master Sword upgrades does not complete these
defeat/trial checks. The four Blight checks remain enabled with boss checks off
when required by a Beast goal. `all_checks` requires every check selected by
the check/DLC options. See the [README YAML example](../README.md).

The APWorld applies these prerequisites to goal reachability, and the client
requires their journaled check IDs before sending CLIENT_GOAL. Defeating Dark
Beast early is recorded, but Victory is withheld until all prerequisites are
complete; this does not physically block the Ganon encounter. Use the updated
client and regenerate the seed and Graphic Pack. Old seeds retain their original
goal contract. With both DLC options enabled, the catalog now selects 415 checks
with default options, including the trial completion reward.

Use `trial_of_the_sword: false` to remove the trial chests and completion check
from generation and goal requirements while retaining other enabled DLC content.

Each tracked chest drops a distinct actor named `AP_Check_XXXXXXXX`, where
`XXXXXXXX` is its unsigned 32-bit **AP location ID**, as eight uppercase hex
digits. For example, location `0xB1234567` drops `AP_Check_B1234567`. The visible
item name is `Archipelago Item [B1234567]`. The placed reward's item ID and owner
are separate: a foreign player's reward still uses the local chest's location ID.

The static engine creates an actor pack, ActorLink, GeneralParamList, ActorInfo
entry, UI name/description, and RSTB allocations for each marker. The current
visual prototype shares the diamond model and icon; its buying/selling prices
are zero. Model, physics, and AI resources remain shared to keep each additional
pack small. All installed language packs receive the AP labels (currently English).

The bundled acquisition hook now:

1. Recognizes exactly `AP_Check_` followed by eight uppercase hexadecimal digits.
2. Decodes the location ID and verify it against the current slot's `locations`
   allowlist, supplied in slot data or the local patch manifest.
3. Queues that ID with a zero high word in the mailbox's 64-bit location field.
4. Suppresses native marker insertion into the pouch, while completing the chest
   acquisition normally. A full outgoing queue retains the check as pending.
5. Keeps received-item injection separate from outgoing check detection. Repeated
   acquisitions of the same marker refer to the same AP check.

Unknown or malformed marker names must not generate synthetic check IDs. The
hook consumes the raw actor name, not the UI label. The generated pack includes
the matching ASM and seed table; see `docs/mailbox_protocol.md` for protocol v2.

## File formats and patch application

BotwRandomizer patches chest **instances** in `.smubin` map BYML:
`Objs -> !Parameters -> DropActor`. `.bdrop` and `.bshop` are shared AAMP
resources; treating them as map BYML cannot identify individual chests. The new
patcher operates on real BotW map records and removes the tracked chest's
`DropTable` fallback. It does not add an unsupported `AP_LocationID` parameter.

The APWorld writes a copyright-free `.apbotw` custom `APPatch` container with
`archipelago.json` and `botw_patch.json`. Apply that plan locally to produce a
Graphic Pack zip containing modified game resources. Generation therefore needs
the catalog, while application needs the player's own extracted base/update
content. Original game files are read only. Source map checksums, missing chest
identities, duplicate IDs, unsafe paths, and existing outputs cause a failure.

Base and update roots are combined with update precedence. With `--dlc`, DLC
maps take precedence and output uses `aoc/0010`; packed maps are rebuilt inside
their original SARC rather than disabling `AocMainField.pack`. Discover against
the same base/update/DLC combination that the player will run.

## Running it

Use Python 3.12; the `oead` wheels are not available for the repository's original
Python 3.14 virtual environment. `roead` is a Rust library; the Python bindings
used here are `oead`.

```sh
python3.12 -m venv .venv-patcher
.venv-patcher/bin/pip install -r src/patcher/requirements.txt

# Create a catalog; add --dlc /path/to/dlc/content when appropriate.
.venv-patcher/bin/python -m src.patcher discover \
  --base /path/to/base/content \
  --update /path/to/update/content \
  --bind-reference --output out/chests.json

# Package the currently bundled catalog and world for Archipelago.
.venv-patcher/bin/python -m src.patcher bundle-world --output out/botw.apworld

# After Archipelago generation, apply this player's seed.
.venv-patcher/bin/python -m src.patcher apply AP_seed_P1_Player.apbotw \
  --base /path/to/base/content \
  --update /path/to/update/content \
  --output out/BotW_AP_P1.zip
```

Install `botw.apworld` in Archipelago's `custom_worlds` directory and generate
with game `Breath of the Wild`. Extract the locally applied zip into Cemu's
`graphicPacks` directory. Enable only that generated AP pack; disable the standalone
AP hook pack to avoid patching the same native entrypoints twice. Regenerate older
seeds and packs to obtain protocol v2 slot data and a configured hook.

Minimal player YAML:

```yaml
name: Player
game: Breath of the Wild
Breath of the Wild:
  progression_balancing: 50
  accessibility: full
  chest_sanity: true
  skip_great_plateau: true
  enable_the_master_trials_dlc: false
  enable_the_champions_ballad_dlc: false
```

## Catalog and first logic scope

The bundled catalog has 187 bound chest checks, 120 shrine completion checks,
15 tower checks and 93 miniboss/boss checks. The chest count includes seven
Master Trials and fifteen Champions' Ballad chests; DLC options control whether
those are included in a seed. The 181 item mappings have concrete delivery
implementations: 129 actor grants, 43 native grants, five progression
operations and four rupee grants. Every chest
identity includes its map resource, map checksum, actor HashId, original loot,
position, and binding provenance. Location IDs derive from the logical map path
and HashId and do not depend on the seed or scan order. Discovery rejects hash
collisions instead of renumbering checks.

The Manual release provides item/region/requirement data, not physical HashIds.
Shrine numbers are resolved through the game's English messages. Multiple
numbered chests bind automatically only when their requirements agree and the
number of physical chests matches the reference. Those automatic numbered names
follow HashId order; physical numbering can be curated later without changing IDs.
Unbound checks and excluded checks are explicitly recorded. Dungeon-local small
keys, Treasure Chest Shop minigames, Master Mode actors, and chests without a
direct `DropActor` await dedicated handling.

Add reviewed bindings by setting the candidate's `name`, `region`, `requires`,
and `category` in `worlds/botw/data/chests.json`; keep its ID, resource, HashId,
and checksum. A newly discovered catalog can be reviewed before replacing the
bundled catalog. DLC options reject catalogs without mapped DLC checks.

Rules support the Manual's `|Item|`, `|Item:count|`, `|@Category|`, parentheses,
`AND`, and `OR` without `eval`. Regions retain the reference's tower gates, with
Paraglider additionally required outside the Plateau. The item pool includes
all enabled progression copies, subtracts precollected inventory, samples optional
items into the remaining slots, and fills spare slots with arrows. Insufficient
checks and enabled items without a delivery implementation fail generation.

The fresh-save starting inventory is precollected in AP logic and initialized
in game resources. With the default Plateau skip, the Plateau tower, Sheikah
Slate, hearts and pouch capacities are initialized; the Paraglider remains in
the randomized pool. Dark Beast Ganon remains the logical goal event and its
physical defeat check is the required AP completion signal, even when optional
boss checks are disabled. The client sends `CLIENT_GOAL` after reporting that
check. Shop patching is not included in this beta.

## Validation performed

Solo and two-player worlds passed Archipelago restrictive fill and beatability
using the local AP installation. Generated `.apbotw` files round-trip through
the same production plan validator used by the patcher. The applied validation
zip was parsed back to
verify encoded drops, ActorLinks, GeneralParamLists, sorted ActorInfo hashes,
resource-size entries, and UI labels in all seven installed language packs.
The current patcher/hook/startup and APWorld test suites pass. The patcher and
APWorld tests cover the static pipeline; protocol tests additionally
exercise the actual hook instructions against simulated guest memory. C# self-tests
cover seed verification, native acknowledgements, queue limits, journal recovery,
and a real AP SDK exchange against a local WebSocket fixture.
Coverage includes chest identity, unmatched mappings, archive preservation,
initial access, rune rules, fill, hook backpressure, and partial native grants.
The live item suite verified all 194 receipts across 181 item types. The live
Stasis terminal test confirmed the rune remains absent until AP delivery. These
checks do not establish four-hour Cemu stability, sub-150 ms check latency,
player-visible UI behavior, full-pouch queuing, or natural gameplay traversal;
those acceptance checks remain before a non-beta release.

## References

- `external/BotwRandomizer/BotwRandoLib/Randomizer.cs`: per-instance chest patches.
- `external/BotwRandomizer/BotwRandoLib/LibHelpers.cs`: Plateau hashes and RSTB.
- `external/BotW-APManual`: community logic, extracted from release v1.1.0.
- `external/uking/src/KingSystem/Resource/resResourceActorLink.cpp`: ActorLink users.
- Local Archipelago `worlds/Files.py`: custom `APPatch` output convention.

## Network client

Build with the installed .NET 10 SDK, then start after loading the generated pack:

```sh
dotnet build src/client
dotnet run --project src/client -- --server localhost:38281 --slot Player
dotnet run --project src/client -- --self-test
```

Use `--password`, `--state-dir`, and `--verbose` as needed. The default state
directory is `BotWAP/state` under the user's local application-data directory.
Keep that journal with the matching save. The Linux client requires permission
to access Cemu's `/proc/<pid>/mem`. It verifies seed/player identity before
writing the mailbox. Unsupported native grants are reported and retained.

A generated pack can also be checked by the C# contract reader without Cemu:

```sh
dotnet run --project src/client -- --self-test-pack /path/to/BotW_AP_P1.zip
```

That check reads the pack's actual ASM allocation and compares its IDs and
fingerprint with the manifest and AP slot data. Seed generation rejects enabled
items that have no delivery implementation.

## Starting after the Great Plateau tutorial

`skip_great_plateau` is enabled by default. Set it explicitly in the player YAML:

```yaml
Breath of the Wild:
  skip_great_plateau: true
```

Generate a new seed, apply it to your extracted game, enable the resulting AP
graphic pack, and choose **New Game**. Start with the Plateau tower/map enabled,
its main tutorial quests finished, and the Sheikah Slate in the pouch.
The Paraglider stays randomized, so Plateau containment is removed when that AP
item is received. The AP client is not needed to apply the other fresh-save
defaults.

This uses the reference randomizer's Bootup GameData initialization approach.
The patch adds the Sheikah Slate to the native `PorchItem` arrays, preserves
other entries, and updates the RSTB for the rebuilt resources. The four Plateau rune
terminals use an AP clone with the vanilla `DemoGetItem` action disabled, so
Magnesis, Remote Bombs, Stasis and Cryonis are granted through AP item receipts.
The clone is bound only to those four placements; other download terminals keep
their vanilla behavior. Shrine chests remain checks.

Slot data records the exact applied AP starting-item counts. The client accepts
only that many precollected receipts (AP location `-2`) as already applied; ordinary
rewards with the same ID still require delivery. The starting-state profile is
included in the seed fingerprint, so packs with different startup settings cannot
be interchanged.

Existing saves retain their saved flags/inventory and are not migrated by these
initial defaults. Set `skip_great_plateau: false` for the original tutorial and
keep the Paraglider in the randomized item pool. A fresh save and regenerated
pack are required when changing this option or applying the rune-terminal fix.
