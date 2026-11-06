import struct
import zlib
from importlib.resources import files

from src.patcher.core import ROOT
from botw_static.icons import ICON_ACTOR, ICON_TEMPLATE, build_check_icon, rgba8_address
from botw_static.resource_sizes import allocation_template
from botw_static.ui import reward_messages


def test_reward_labels_use_the_placed_item_and_recipient():
    placements = {
        1: dict(name='Magnesis', player=1, player_name='Link'),
        2: dict(name='Sharp Knife', player=2, player_name='Chef'),
        3: dict(name='Final countdown', player=3),
    }
    labels = reward_messages([1, 2, 3], placements, 1, 'Link')
    assert labels['AP_Check_00000001_Name'] == 'Magnesis'
    assert labels['AP_Check_00000002_Name'] == 'Sharp Knife (Chef)'
    assert labels['AP_Check_00000003_Name'] == 'Final countdown (Player 3)'
    assert 'Sent to Link' in labels['AP_Check_00000001_Desc']


def test_player_and_foreign_item_names_cannot_inject_msbt_commands():
    labels = reward_messages([1], {1: dict(name='Épée\x0e\x00', player=2, player_name='Zelda\n\x0f')}, 1)
    assert labels['AP_Check_00000001_Name'] == 'Épée (Zelda)'


def test_icon_tile_layout_covers_the_entire_surface_once():
    addresses = {rgba8_address(x, y) for y in range(96) for x in range(96)}
    assert addresses == set(range(0, 96 * 96 * 4, 4))
    assert [rgba8_address(x, y) for x, y in ((0, 0), (8, 0), (16, 0), (32, 0), (0, 16))] == [0, 768, 1024, 2048, 7168]


def test_icon_replaces_pixels_preserving_the_supported_bfres_layout():
    raw = bytearray(0x800 + 96 * 96 * 4)
    raw[:10] = b'FRES\x04\x05\x00\x03\xfe\xff'
    texture = 0x94
    raw[texture:texture + 4] = b'FTEX'
    for offset, value in {4: 1, 8: 96, 12: 96, 16: 1, 20: 1, 24: 0x41A,
                          36: 96 * 96 * 4, 52: 4, 56: 0xD0000, 64: 96,
                          0xB0: 0x800 - (texture + 0xB0)}.items():
        struct.pack_into('>I', raw, texture + offset, value)
    raw[0x300:0x30A] = b'Item_Ore_A'

    class Dump:
        def read(self, path):
            assert path == ICON_TEMPLATE
            return bytes(raw)

    path, output = next(iter(build_check_icon(Dump()).items()))
    assert allocation_template(path) == ICON_TEMPLATE
    assert len(output) == len(raw)
    assert output[:0x800] == bytes(raw[:0x800]).replace(b'Item_Ore_A', ICON_ACTOR.encode())
    pixels = zlib.decompress(files('botw_static').joinpath('assets/archipelago.rgba.zlib').read_bytes())
    for y in range(96):
        for x in range(96):
            source = (y * 96 + x) * 4
            target = 0x800 + rgba8_address(x, y)
            assert output[target:target + 4] == pixels[source:source + 4]
