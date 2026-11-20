"""Regressions for game-map tile selection and texture validation."""
from pathlib import Path
import pytest
from src.patcher.build_tracker_map import choose_tile, decode_tile


def test_full_tile_is_not_largest_fog_variant():
    paths = [Path(f'MapTex1_A-4{suffix}.sbmaptex') for suffix in ('_0', '_16388', '', '_16386', '_6')]
    assert choose_tile(paths).name == 'MapTex1_A-4.sbmaptex'


def test_missing_full_tile_is_reported():
    with pytest.raises(ValueError, match='Missing fully revealed'):
        choose_tile([Path('MapTex1_A-4_0.sbmaptex')])


def test_invalid_texture_is_rejected(tmp_path):
    tile = tmp_path / 'MapTex1_A-4.sbmaptex'
    tile.write_bytes(b'not a game texture')
    with pytest.raises(ValueError, match='Not a Wii U BFRES'):
        decode_tile(tile)
