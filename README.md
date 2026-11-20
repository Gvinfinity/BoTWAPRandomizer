# BotW Archipelago Multiworld

This repository contains the Breath of the Wild Archipelago world, the static game patcher, and the Cemu client and hook components. The supported game is the Wii U release updated to v1.5.0 (v208).

## Play through the Archipelago Launcher

1. Install Breath of the Wild Wii U **v1.5.0 (v208)** in Cemu. Install the BotW
   `.apworld` with the Archipelago Launcher, then restart the Launcher.
2. Get your player's `.apbotw` seed file. In the Launcher, choose **Open Patch**
   or **Install BotW Seed Pack** and select the file.
3. Select your extracted base and update `content` folders, the DLC folder
   containing `0010` if you play with DLC, and Cemu's Graphic Packs folder.
   The installer creates the pack there and remembers your folder choices as
   defaults. If you're replacing a seed for the same player number, move the
   existing pack out of the Graphic Packs folder first.
4. Refresh **Options → Graphic Packs** in Cemu and enable the seed pack. Close
   Cemu, then choose **BotW Client** in the Archipelago Launcher. Select the
   Cemu executable if prompted. The client starts Breath of the Wild by title
   ID from Cemu's game list. Load your save in
   that Cemu window, enter the room address, and choose **Connect**. Enter your
   player name and the room password if required. The Launcher client can access
   the Cemu process it starts on Linux without sudo.
   Room messages appear in the Archipelago tab, and the Hints tab shows your
   saved hints. Enter chat or server commands such as `!hint <item>` in the
   command field. In the **Tracker** tab, choose **Generate map** once and enable
   the tracker before connecting to see your live checks.

The Windows x64 and Linux x64 player bundles include the patcher and client.
Players only need Archipelago, Cemu, and their own game files. If you built
a world archive without a patcher, use the
[standalone player setup](#standalone-player-setup).

## Development setup

You will need Python 3.10 or newer for the world and patcher, and the .NET SDK required by `src/client/BotWClient.csproj` (currently .NET 10). To develop against the Archipelago framework, install this world into an Archipelago checkout or bundle it as an `.apworld`.

```sh
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e '.[test]'   # run from src/patcher
```

Build the world bundle from the repository root:

```sh
python -m src.patcher bundle-world
```

This creates `out/botw-0.5.8.apworld`,
with the version defined in `worlds/botw/static/version.py` and recorded in the
archive manifest. Install only one BotW APWorld version in Archipelago.

Version 0.5.3 separates Beast boarding from internal controls, adds Gerudo Town
disguise and Lakna Rokee Camera requirements, and models local DLC quest stages.
See [boarding and quest logic](docs/boarding_logic.md) for requirements and native
supply assumptions. Generate a new seed and Graphic Pack to use these rules.

Build the client from the repository root:

```sh
dotnet build src/client/BotWClient.csproj
```

To ship the client inside the APWorld, publish a self-contained single-file
executable and pass it into the bundler. For example, on Linux x64:

```sh
dotnet publish src/client -c Release -r linux-x64 --self-contained true \
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true \
  -o out/client/linux-x64
python -m src.patcher bundle-world \
  --client linux-x64=out/client/linux-x64/BotWClient
```

Repeat `--client RID=PATH` to ship multiple platforms in one APWorld. Supported
RIDs are `linux-x64`, `linux-arm64`, `win-x64`, and `win-arm64`. Use
`BotWClient.exe` for Windows publish outputs. A bundle without these options can
be used for generation and patching.

For a player release, also build and include the self-contained patcher.
From a Python 3.12 environment:

```sh
python -m pip install PyInstaller -r src/patcher/requirements-tracker.txt
python -m src.patcher.build_player linux-x64 out/patcher-linux-x64.zip
python -m src.patcher.build_player win-x64 out/patcher-win-x64.zip \
  --windows-python /path/to/python-3.12-embed-amd64.zip
```

The Windows build uses the official CPython 3.12 Windows x64 embeddable ZIP
and installs Windows wheels into it at build time. The Linux build runs on
Linux x64. Pass `--patcher linux-x64=out/patcher-linux-x64.zip` or
`--patcher win-x64=out/patcher-win-x64.zip` to `bundle-world` alongside the
matching `--client` argument. The default filenames for single-platform player
bundles are `out/botw-0.5.8-linux-x64.apworld` and
`out/botw-0.5.8-win-x64.apworld`. Repeat both options for a multi-platform bundle.

Add `--tracker` to the client command for an offline map tracker at
`http://127.0.0.1:38282/`. Checks overlay the actual BotW map extracted from your
installed game, with shrine entrance groups, automatic completion, item progression,
and search/filter controls. Preview without Cemu using
`dotnet run --project src/client -- --tracker-only`. See [the tracker guide](docs/tracker.md)
for one-time map preparation and logic limits.

The patcher uses extracted game content as input; it does not include game files. See [the patcher CLI](src/patcher/__main__.py) for `discover` and `apply` commands and their required paths. The repository also includes detailed [Cemu integration test notes](docs/cemu_integration_tests.md).

## Install and play on Cemu

Set the goal in your Archipelago player YAML:

```yaml
name: Player
game: Breath of the Wild
Breath of the Wild:
  goal: all_divine_beasts_and_trials
  chest_sanity: true
  shrine_sanity: true
  tower_sanity: true
  miniboss_sanity: true
  boss_sanity: true
  enable_the_master_trials_dlc: true
  trial_of_the_sword: false
```

| `goal` value | Required checks for Victory |
| --- | --- |
| `dark_beast_ganon` | Dark Beast Ganon only |
| `all_divine_beasts` | All four Blight defeats and Dark Beast Ganon |
| `all_divine_beasts_and_trials` (default) | All four Blight defeats, Trial of the Sword completion if both the trial and its DLC are enabled, and Dark Beast Ganon |
| `all_checks` | Every enabled check, including Dark Beast Ganon |

Beast goals keep the four Blight checks enabled even with `boss_sanity: false`.
Set `trial_of_the_sword: false` to exclude all trial chests and its completion
check, including its Victory requirement. Other Master Trials DLC content remains
enabled. The option defaults to `true` and only takes effect with
`enable_the_master_trials_dlc: true`; it does not block entering the trial in-game.
All five Sanity options default to `true`. ChestSanity adds all mapped chests.
ShrineSanity adds mapped shrine chests and shrine completion rewards.
TowerSanity adds tower activations, and MinibossSanity/BossSanity add defeats.
Keep at least one of `chest_sanity` and `shrine_sanity` enabled with the
default starting inventory so there are enough checks for progression items.
For older YAMLs, rename `chest_shuffle` to `chest_sanity`, and replace the
`_checks` suffix with `_sanity` on `shrine`, `tower`, `miniboss`, and `boss`.
The goal controls generation logic and the client's Victory report; it does not
prevent an early Ganon fight. Use the updated client and generate a new seed and
Graphic Pack after changing this option.

## Standalone player setup

1. Install Breath of the Wild for Wii U in Cemu and apply the update to **v1.5.0 (v208)**. Keep your own legally obtained game, update, and DLC files.
2. Generate an Archipelago seed using the BotW world and download that player's `.apbotw` file.
3. Extract the Wii U game's base and v208 update content from your own copy. Install the patcher dependencies once (Python 3.12 is recommended):

   ```sh
   python3.12 -m venv .venv-patcher
   .venv-patcher/bin/pip install -r src/patcher/requirements.txt
   ```

   On Windows, use the equivalent `.venv-patcher\\Scripts\\python.exe` executable in place of `.venv-patcher/bin/python` below. From the repository root, apply the player patch. Replace the example paths and output filename as needed; include `--dlc /path/to/dlc/content` when playing with DLC:

   ```sh
   .venv-patcher/bin/python -m src.patcher apply AP_seed_P1_Player.apbotw \\
     --base /path/to/base/content \\
     --update /path/to/update/content \\
     --output out/BotW_AP_P1.zip
   ```

   This creates a seed-specific Graphic Pack ZIP by applying the patch plan to your game content. The base/update/DLC combination should match the content you use in Cemu.
   Tracked pickups display the Archipelago icon and the placed reward's item
   name, including its recipient when sent to another player. Regenerate the
   seed to include recipient names; older patches can show `Player N` instead.
4. In Cemu, open **Options → General settings → General** and note the configured Graphic Packs directory. Extract the generated ZIP into that directory, preserving its `rules.txt` and directory structure.
5. Open **Options → Graphic Packs**, refresh the list if needed, and enable the generated BotW Archipelago pack under the Breath of the Wild category. Do not enable the standalone AP hook pack alongside it.
6. Start the game, then launch the built `BotWClient` and connect it to the same Archipelago room using the generated player credentials.

For platform-specific folder locations and more detail, see the [Cemu installation guide](docs/cemu_installation_guide.md). The hook is version-specific; do not enable it with another game update version. Disable other packs that alter the same chests, shops, inventory, or Great Plateau behavior if they conflict.
