"""Bind discovered map instances to the Manual's named shrine checks."""
from __future__ import annotations

import json
from pathlib import Path
import re

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

    # The Trial of the Sword's final arena is represented by two mutually
    # exclusive map variants in FinalTrial.pack. They contain the same seven
    # physical chest HashIds. Give each physical chest one AP location and
    # patch that same check into both map variants. These are deliberately
    # named by HashId: the Manual lists floor checks, but does not identify
    # which actor HashId belongs to each floor.
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
            name=f"Trial of the Sword (Final Trials) - Chest {hash_id:08X}",
            region="Trial of the Sword (Final Trials)",
            requires="",
            category=["The Master Trials DLC"],
            binding="master-trials-finaltrial-hash",
        )
        if alternate is not None:
            canonical["resource_variants"] = [{
                "resource": alternate["resource"],
                "map_sha256": alternate["map_sha256"],
            }]
            discovery["locations"].remove(alternate)

    discovery["binding_warnings"] = warnings
    return discovery
