"""Render the tracker map locally from a player's Wii U content."""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import struct
import sys
from tempfile import TemporaryDirectory


def installed_map_directory():
    if sys.platform == 'win32':
        local_data = os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local'
    else:
        local_data = os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share'
    return Path(local_data) / 'BotWAP/tracker'


def raw(data):
    import oead
    return bytes(oead.yaz0.decompress(data)) if data[:4] == b'Yaz0' else data


def decode_tile(path):
    from PIL import Image
    data = raw(path.read_bytes())
    if data[:4] != b'FRES':
        raise ValueError(f'Not a Wii U BFRES texture: {path}')
    # Follow the texture resource dictionary rather than searching image bytes.
    group = 0x24 + struct.unpack_from('>i', data, 0x24)[0]
    if struct.unpack_from('>I', data, group + 4)[0] != 1:
        raise ValueError(f'Expected exactly one map texture: {path}')
    pointer = group + 8 + 16 + 12
    ftex = pointer + struct.unpack_from('>i', data, pointer)[0]
    if data[ftex:ftex + 4] != b'FTEX':
        raise ValueError(f'Missing FTEX: {path}')
    dim, width, height, depth, _, fmt, aa, _, size, _, _, _, mode, swizzle, _, pitch = struct.unpack_from('>16I', data, ftex + 4)
    if fmt not in (0x31, 0x431) or aa or depth != 1:
        raise ValueError(f'Unsupported map texture format: {path}')
    pointer = ftex + 0xb0
    start = pointer + struct.unpack_from('>i', data, pointer)[0]
    if start < 0 or start + size > len(data):
        raise ValueError(f'Truncated map texture: {path}')
    if mode != 4 or pitch % 32 or pitch < (width + 3) // 4:
        raise ValueError(f'Unsupported Wii U map tiling: {path}')
    pixels = untile_bc1(data[start:start + size], width, height, pitch, swizzle)
    return Image.frombytes('RGBA', (width, height), pixels, 'bcn', 1)


@lru_cache(maxsize=8)
def bc1_offsets(width, height, pitch, swizzle):
    """Byte addresses of BC1 blocks in a GX2 2D thin, single-sample surface."""
    offsets = []
    pipe_bank_xor = (swizzle >> 8) & 7
    for y in range((height + 3) // 4):
        for x in range((width + 3) // 4):
            # A macro tile covers 32×16 blocks, divided into 8×8 micro tiles.
            macro_tile = (y // 16) * (pitch // 32) + x // 32
            block = (x & 1) | ((y & 1) << 1) | ((x & 6) << 1) | ((y & 6) << 3)
            pipe = ((x >> 3) ^ (y >> 3)) & 1
            bank_low = ((x >> 3) ^ (y >> 5)) & 1
            bank_high = ((x >> 4) ^ (y >> 4)) & 1
            channel = (pipe | (bank_low << 1) | (bank_high << 2)) ^ pipe_bank_xor
            byte = macro_tile * 512 + block * 8
            offsets.append(((byte & ~255) << 3) | (channel << 8) | (byte & 255))
    return offsets


def untile_bc1(data, width, height, pitch, swizzle):
    offsets = bc1_offsets(width, height, pitch, swizzle)
    if max(offsets) + 8 > len(data):
        raise ValueError('Incomplete Wii U map texture')
    return b''.join(data[offset:offset + 8] for offset in offsets)


def choose_tile(paths):
    # The unsuffixed resource is the fully revealed tile. Suffixes select fog
    # and save-state variants; even the largest suffix can still contain fog.
    for path in paths:
        if len(path.stem.split('_')) == 2:
            return path
    name = paths[0].name if paths else 'map tiles missing from the selected content'
    raise ValueError(f'Missing fully revealed map tile: {name}')



def build(roots, output, locations, lod=1):
    import oead
    from PIL import Image
    tiles = {}
    for root in roots:
        for path in (root / 'UI/MapTex/MainField').glob(f'MapTex{lod}_*.sbmaptex'):
            tiles[path.name] = path
    groups = {}
    for path in tiles.values():
        groups.setdefault(path.stem.split('_')[1], []).append(path)
    columns = 'ZABCDEFGHIJK'  # Z is the western border, not the final column.
    chosen = [choose_tile(groups.get(f'{col}-{row}', ())) for col in columns for row in range(10)]
    tile_size = decode_tile(chosen[0]).width
    image = Image.new('RGB', (tile_size * 12, tile_size * 10))
    for index, path in enumerate(chosen):
        tile = decode_tile(path)
        if tile.size != (tile_size, tile_size):
            raise ValueError(f'Inconsistent tile size: {path}')
        image.paste(tile.convert('RGB'), ((index // 10) * tile_size, (index % 10) * tile_size))
        if index % 10 == 9:
            print(f'Decoded map column {columns[index // 10]}', flush=True)
    markers = {}
    for root in roots:
        bootup = root / 'Pack/Bootup.pack'
        if not bootup.is_file():
            continue
        member = oead.Sarc(bootup.read_bytes()).get_file('Map/MainField/Static.smubin')
        if member is None:
            continue
        data = oead.byml.from_binary(raw(bytes(member.data)))
        for marker in data.get('LocationMarker', []):
            if marker.get('MessageID') and marker.get('Translate'):
                markers[marker['MessageID']] = [float(marker['Translate'][axis]) for axis in 'XYZ']
    positions = {}
    for entry in locations:
        dungeon = entry.get('dungeon')
        match = re.search(r'/CDungeon/(Dungeon\d+)/', entry.get('logical_map', ''))
        if match:
            dungeon = match[1]
        anchor = dungeon or (f"Tower{entry['tower']:02}" if entry.get('kind') == 'tower' else None)
        if anchor in markers:
            positions[str(entry['id'])] = {'position': markers[anchor], 'source': 'entrance' if match else 'landmark'}
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as directory:
        temporary = Path(directory)
        image.save(temporary / 'map.webp', quality=95, method=4)
        (temporary / 'map.json').write_text(json.dumps({'version': 1, 'bounds': [-6000, -5000, 6000, 5000],
            'width': image.width, 'height': image.height, 'positions': positions}, indent=2) + '\n', encoding='utf-8')
        (temporary / 'map.webp').replace(output / 'map.webp')
        (temporary / 'map.json').replace(output / 'map.json')
    print(f'Wrote {image.width}×{image.height} map and {len(positions)} shrine/tower positions to {output}')

