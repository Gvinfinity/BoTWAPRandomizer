"""Bind discovered map instances to the Manual's named shrine checks."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .check_logic import apply_check_logic
from .messages import read_msbt
from .resources import binary_modules, decompress


def bind_reference(discovery: dict, dump, reference_dir: Path, randomizer_dir: Path) -> dict:
    oead, _ = binary_modules()
    locations = json.loads((reference_dir / "locations.json").read_text())["data"]
    # Use an English message pack for exact reference names. Never guess shrine
    # numbers: Dungeon000 is Tah Muhl, for example, not Oman Au.
    for language in ("EUen", "USen"):
        try:
            boot = oead.Sarc(decompress(dump.read(f"content/Pack/Bootup_{language}.pack")))
            message = next(entry for entry in boot.get_files() if entry.name.endswith(".ssarc"))
            messages = oead.Sarc(decompress(bytes(message.data)))
            names = read_msbt(bytes(messages.get_file("StaticMsg/Dungeon.msbt").data))
            break
        except FileNotFoundError:
            continue
    else:
        raise ValueError("An English Bootup message pack is required for reference binding")
    source = (randomizer_dir / "BotwRandoLib/LibHelpers.cs").read_text(encoding="utf-8-sig")
    plateau_section = source.split("GetParagliderChests()", 1)[1].split("return chests;", 1)[0]
    plateau_hashes = {int(value) for value in re.findall(r"chests.Add\((\d+)\)", plateau_section)}
    groups = {}
    for location in discovery["locations"]:
        dungeon = re.search(r"(?:^|/)CDungeon/(Dungeon\d+)/", location["logical_map"])
        if dungeon:
            groups.setdefault(dungeon[1], []).append(location)
        elif location["hash_id"] in plateau_hashes and "/MainField/" in location["logical_map"]:
            location.update(region="Great Plateau", category=["Overworld Chests"], binding="randomizer-plateau-hash")
    warnings = []
    for dungeon, chests in sorted(groups.items()):
        shrine = names.get(dungeon)
        refs = [location for location in locations
                if shrine and location["name"].startswith(shrine + " - Chest")]
        if len(refs) != len(chests):
            warnings.append(f"{dungeon}: {len(chests)} discovered chests, {len(refs)} named reference checks")
            continue
        # Multiple numbered chests are safe to bind automatically only when
        # their access rules agree. Differing rules require physical annotation.
        if len({entry.get("requires", "") for entry in refs}) > 1:
            warnings.append(f"{dungeon}: numbered chest rules differ; needs explicit HashId binding")
            continue
        for chest, ref in zip(sorted(chests, key=lambda entry: entry["hash_id"]), refs):
            chest.update(name=ref["name"], region=ref["region"], requires=ref.get("requires", ""),
                         category=ref.get("category", []), binding="manual-shrine-equal-rule")

    # FinalTrial.pack is the Champions' Ballad's fifth Divine Beast, not Trial
    # of the Sword. Both variants contain the same seven physical chest IDs.
    # Preserve one check and patch it into both variants.
    trial_maps = {
        "Map/MainFieldDungeon/FinalTrial/FinalTrial_Static.smubin",
        "Map/MainFieldDungeon/FinalTrial/FinalTrial_Static_NoGrudgeMerge.smubin",
    }
    variants = {}
    for chest in discovery["locations"]:
        if chest["logical_map"] in trial_maps and chest["resource"].startswith("aoc/0010/Pack/FinalTrial.pack!"):
            variants.setdefault(chest["hash_id"], []).append(chest)
    for hash_id, chests in variants.items():
        canonical = next((entry for entry in chests if entry["logical_map"].endswith("FinalTrial_Static.smubin")), None)
        alternate = next((entry for entry in chests if entry["logical_map"].endswith("FinalTrial_Static_NoGrudgeMerge.smubin")), None)
        if canonical is None:
            continue
        canonical.update(
            name=f"Final Trial - Chest {hash_id:08X}",
            region="Final Trial",
            requires="",
            category=["The Champions' Ballad DLC"],
            binding="champions-ballad-finaltrial-hash",
        )
        if alternate is not None:
            canonical["resource_variants"] = [{
                "resource": alternate["resource"],
                "map_sha256": alternate["map_sha256"],
            }]
            discovery["locations"].remove(alternate)

    discovery["locations"] = [apply_check_logic(entry) if entry.get("region") else entry
                              for entry in discovery["locations"]]
    discovery["binding_warnings"] = warnings
    return discovery
