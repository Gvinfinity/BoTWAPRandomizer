# BotW Archipelago Multiworld

This repository contains the Breath of the Wild Archipelago world, the static game patcher, and the Cemu client and hook components. The supported game is the Wii U release updated to v1.5.0 (v208).

## Development setup

You will need Python 3.10 or newer for the world and patcher, and the .NET SDK required by `src/client/BotWClient.csproj` (currently .NET 10). To develop against the Archipelago framework, install this world into an Archipelago checkout or bundle it as an `.apworld`.

```sh
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e '.[test]'   # run from src/patcher
```

Build the world bundle from the repository root:

```sh
python -m src.patcher bundle-world --output dist/botw.apworld
```

Build the client from the repository root:

```sh
dotnet build src/client/BotWClient.csproj
```

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
All five Sanity options default to `true`. ChestSanity adds overworld chests;
mapped shrine chests remain enabled. ShrineSanity adds shrine completion rewards,
TowerSanity adds tower activations, and MinibossSanity/BossSanity add defeats.
Currently, keep `chest_sanity: true` with the default starting inventory: disabling
it removes all initially reachable checks and can prevent seed generation.
For older YAMLs, rename `chest_shuffle` to `chest_sanity`, and replace the
`_checks` suffix with `_sanity` on `shrine`, `tower`, `miniboss`, and `boss`.
The goal controls generation logic and the client's Victory report; it does not
prevent an early Ganon fight. Use the updated client and generate a new seed and
Graphic Pack after changing this option.

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
4. In Cemu, open **Options → General settings → General** and note the configured Graphic Packs directory. Extract the generated ZIP into that directory, preserving its `rules.txt` and directory structure.
5. Open **Options → Graphic Packs**, refresh the list if needed, and enable the generated BotW Archipelago pack under the Breath of the Wild category. Do not enable the standalone AP hook pack alongside it.
6. Start the game, then launch the built `BotWClient` and connect it to the same Archipelago room using the generated player credentials.

For platform-specific folder locations and more detail, see the [Cemu installation guide](docs/cemu_installation_guide.md). The hook is version-specific; do not enable it with another game update version. Disable other packs that alter the same chests, shops, inventory, or Great Plateau behavior if they conflict.
