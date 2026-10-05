# Static chest randomizer and APWorld

This is the first static chest implementation for the Wii U v208 game. It
generates Archipelago seeds and applies them to an extracted game as a Cemu
Graphic Pack. The generated pack includes the seed-bound acquisition/delivery hook, and the
client consumes APWorld slot data. Native flag/progressive-item grants and
in-game victory reporting remain unfinished; this is not yet a playable integration.

## Chest identity and hook contract

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
  chest_shuffle: true
  enable_the_master_trials_dlc: false
  enable_the_champions_ballad_dlc: false
```

## Catalog and first logic scope

The bundled base/update catalog contains 1,417 candidate chests, with 164 bound
checks: 32 Plateau overworld chests from BotwRandomizer's Paraglider chest list,
and 132 shrine chests bound to the Manual's names and requirements. Every
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
items into the remaining slots, and fills any spare slots with arrows. Insufficient
checks fail generation rather than discarding progression. The reference's default
starting tower, hearts, and pouch capacities are logical precollects.

The reference assumes progression items and flags have been synchronized into
the game. Slot data exposes delivery metadata; grants without an implemented
native mapping are explicitly `kind: unimplemented`. Tower unlocks, runes,
progressive equipment, capacities, event flags, and starting inventory still need
native delivery. Dark Beast Ganon is a logical goal event; the hook/client must
report its actual defeat. Shop patching is not integrated in this first pass.

## Validation performed

Solo and two-player worlds passed Archipelago restrictive fill and beatability
using the local AP installation. The applied 164-check zip was parsed back to
verify encoded drops, ActorLinks, GeneralParamLists, sorted ActorInfo hashes,
resource-size entries, and UI labels in all seven installed language packs.
The current 18 patcher/hook tests and 8 APWorld tests pass. The patcher and
APWorld tests cover the static pipeline; protocol tests additionally
exercise the actual hook instructions against simulated guest memory. C# self-tests
cover seed verification, native acknowledgements, queue limits, journal recovery,
and a real AP SDK exchange against a local WebSocket fixture.
Coverage includes chest identity, unmatched mappings, archive preservation,
initial access, rune rules, fill, hook backpressure, and partial native grants.
These checks do not establish Cemu runtime stability, check latency, UI behavior,
delivery accuracy, or Plateau fog bypass; the project acceptance metrics still
require emulator validation of the integrated hook.

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
fingerprint with the manifest and AP slot data. The current catalog has 5
native actor mappings and 176 explicitly unsupported grant mappings.
