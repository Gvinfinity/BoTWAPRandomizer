"""Regressions for independent resource-heap and DLC map startup crashes."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # Registers the standalone botw_static package.
from botw_static.resource_sizes import rstb_name, update_resource_sizes

oead = pytest.importorskip("oead")
rstb = pytest.importorskip("rstb")


def archive(files):
    writer = oead.SarcWriter(oead.Endianness.Big)
    for name, data in files.items():
        writer.files[name] = data
    return bytes(writer.write()[1])


def table(entries):
    result = rstb.ResourceSizeTable(b"RSTB" + b"\0" * 8, be=True)
    for name, size in entries.items():
        result.set_size(name, size)
    return result


class Dump:
    def __init__(self, files):
        self.files = files

    def read(self, path):
        return self.files[path]


@pytest.mark.parametrize("path, expected", [
    ("content/Pack/MainField.pack!Map/MainField/D-6/D-6_Static.smubin",
     "Map/MainField/D-6/D-6_Static.mubin"),
    ("aoc/0010/Pack/AocMainField.pack!Map/MainField/D-6/D-6_Static.smubin",
     "Aoc/0010/Map/MainField/D-6/D-6_Static.mubin"),
    ("aoc/0010/Map/MainField/D-6/D-6_Static.smubin",
     "Aoc/0010/Map/MainField/D-6/D-6_Static.mubin"),
    ("content/Pack/Bootup.pack!GameData/gamedata.ssarc!/bool_data_0.bgdata",
     "bool_data_0.bgdata"),
])
def test_resource_mount_survives_archive_lookup(path, expected):
    assert rstb_name(path) == expected


def test_dlc_growth_updates_dlc_budget_and_does_not_allocate_outer_pack():
    outer = "aoc/0010/Pack/AocMainField.pack"
    member = "Map/MainField/D-6/D-6_Static.smubin"
    base = member.replace(".smubin", ".mubin")
    dlc = "Aoc/0010/" + base
    original = archive({member: b"x" * 245648})
    patched = archive({member: b"x" * 245760})
    sizes = table({base: 205920, dlc: 245952})
    update_resource_sizes(sizes, Dump({outer: original}), {outer: patched})
    assert sizes.get_size(base) == 205920
    assert sizes.get_size(dlc) == 246144
    assert not sizes.is_in_table("Pack/AocMainField.pack")
    assert not sizes.is_in_table("Aoc/0010/Pack/AocMainField.pack")


def test_preserves_parse_allowance_zero_entries_and_unmodified_members():
    outer = "content/Pack/Test.pack"
    original = archive({"changed.byml": b"a" * 100, "zero.byml": b"b", "keep.byml": b"c"})
    patched = archive({"changed.byml": b"a" * 150, "zero.byml": b"b" * 100, "keep.byml": b"c"})
    sizes = table({"changed.byml": 4096, "zero.byml": 0, "keep.byml": 512})
    update_resource_sizes(sizes, Dump({outer: original}), {outer: patched})
    assert sizes.get_size("changed.byml") == 4160
    assert sizes.get_size("zero.byml") == 0
    assert sizes.get_size("keep.byml") == 512
    assert len(sizes.crc32_map) == 3


def test_renamed_actor_inherits_template_and_shared_growth_is_not_compounded():
    template = "content/Actor/Pack/Item_Ore_A.sbactorpack"
    member = "Actor/ActorLink/Item_Ore_A.bxml"
    original = archive({member: b"a" * 100, "shared.byml": b"b" * 100})
    files = {}
    for code in (1, 2):
        name = f"AP_Check_{code:08X}"
        files[template.replace("Item_Ore_A", name)] = archive({
            member.replace("Item_Ore_A", name): b"a" * 150,
            "shared.byml": b"b" * 150,
        })
    sizes = table({"Actor/Pack/Item_Ore_A.bactorpack": 12768,
                   member: 2300, "shared.byml": 1024})
    update_resource_sizes(sizes, Dump({template: original}), files)
    assert sizes.get_size("shared.byml") == 1088
    assert sizes.get_size("Actor/ActorLink/AP_Check_00000001.bxml") == 2364
    assert sizes.get_size("Actor/Pack/AP_Check_00000001.bactorpack") >= 12768
    assert sizes.get_size(member) == 2300
    stream = io.BytesIO()
    sizes.write(stream, be=True)
    assert rstb.ResourceSizeTable(stream.getvalue(), be=True).crc32_map == sizes.crc32_map
