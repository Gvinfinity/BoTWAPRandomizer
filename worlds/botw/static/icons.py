"""Replace the v208 stock item texture pixels with the supplied AP logo."""
from importlib.resources import files
import struct
import zlib

from .resources import decompress, rewrap

ICON_ACTOR = 'AP_Item_00'  # Same byte length as Item_Ore_A in the BFRES dictionary.
ICON_TEMPLATE = 'content/UI/StockItem/Item_Ore_A.sbitemico'


def rgba8_address(x, y):
    """GX2 2D thin1, RGBA8, 96-pixel pitch, one slice, no pipe/bank swizzle."""
    pixel = (x & 3) | ((y & 1) << 2) | ((x & 4) << 1) | ((y & 6) << 3)
    pipe = ((x >> 3) ^ (y >> 3)) & 1
    bank = (((x >> 3) ^ (y >> 5)) & 1) | ((((x >> 4) ^ (y >> 4)) & 1) << 1)
    offset = ((y // 16) * 3 + x // 32) * 256 + pixel * 4
    return (offset & 255) | (pipe << 8) | (bank << 9) | ((offset & ~255) << 3)


def build_check_icon(dump):
    original = dump.read(ICON_TEMPLATE)
    raw = bytearray(decompress(original))
    if raw[:8] != b'FRES\x04\x05\x00\x03' or raw[8:10] != b'\xfe\xff':
        raise ValueError('Unsupported stock icon BFRES version')
    texture = raw.find(b'FTEX')
    if texture < 0 or raw.count(b'FTEX') != 1:
        raise ValueError('Expected one stock icon texture')
    def word(offset):
        return struct.unpack_from('>I', raw, texture + offset)[0]
    if (word(4), word(8), word(12), word(16), word(20), word(24), word(28),
            word(36), word(44), word(52), word(56), word(64)) != (
            1, 96, 96, 1, 1, 0x41A, 0, 96 * 96 * 4, 0, 4, 0xD0000, 96):
        raise ValueError('Unsupported stock icon surface layout')
    at = texture + 0xB0
    image = at + struct.unpack_from('>i', raw, at)[0]
    if image < texture + 0xC0 or image + 96 * 96 * 4 > len(raw):
        raise ValueError('Invalid stock icon image pointer')
    pixels = zlib.decompress(files(__package__).joinpath('assets/archipelago.rgba.zlib').read_bytes())
    if len(pixels) != 96 * 96 * 4:
        raise ValueError('Invalid bundled AP icon pixels')
    for y in range(96):
        for x in range(96):
            source = (y * 96 + x) * 4
            target = image + rgba8_address(x, y)
            raw[target:target + 4] = pixels[source:source + 4]
    # Preserve all offsets, surface settings, alignment, and dictionary shape.
    raw = bytes(raw).replace(b'Item_Ore_A', ICON_ACTOR.encode())
    return {f'content/UI/StockItem/{ICON_ACTOR}.sbitemico': rewrap(raw, original)}
