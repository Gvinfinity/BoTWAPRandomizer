"""Build a seed's complete static Graphic Pack from a copyright-free plan."""
from . import core
from botw_static.apply import apply_plan
from botw_static.plan import read_plan
from botw_static.resources import GameDump


def create_graphic_pack(output_zip: str, patch_file: str, base: str, update: str, dlc: str | None = None):
    return apply_plan(read_plan(patch_file), GameDump(base, update, dlc), output_zip)
