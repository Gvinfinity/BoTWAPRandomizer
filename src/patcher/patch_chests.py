"""Compatibility entry point for the per-instance BYML chest patcher."""
try:
    from . import core
except ImportError:
    import core

from botw_static.chests import patch_chest_byml


def process_map_file(filepath: str, location_map: dict[int, int]):
    from pathlib import Path
    from botw_static.resources import decode_byml, encode_byml
    path = Path(filepath)
    original = path.read_bytes()
    data = decode_byml(original)
    if patch_chest_byml(data, location_map):
        path.write_bytes(encode_byml(data, original))
