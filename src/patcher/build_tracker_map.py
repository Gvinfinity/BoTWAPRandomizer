"""Build the offline tracker background from an installed Wii U game dump.

Requires oead, Pillow, and the addrlib directory from AboodXD's BFRES-Tool.
Generated game images stay under ignored out/; no game artwork is redistributed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]


def raw(data):
    import oead
    return bytes(oead.yaz0.decompress(data)) if data[:4] == b'Yaz0' else data


def decode_tile(path, addrlib):
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
    info = addrlib.getSurfaceInfo(fmt, width, height, depth, dim, mode, aa, 0)
    pixels = addrlib.deswizzle(width, height, info.height, fmt, mode, swizzle, pitch, info.bpp, data[start:start + size])
    return Image.frombytes('RGBA', (width, height), pixels[:((width + 3) // 4) * ((height + 3) // 4) * 8], 'bcn', 1)


def choose_tile(paths):
    # The unsuffixed resource is the fully revealed tile. Suffixes select fog
    # and save-state variants; even the largest suffix can still contain fog.
    for path in paths:
        if len(path.stem.split('_')) == 2:
            return path
    raise ValueError(f'Missing fully revealed map tile: {paths[0].name}')



def build(roots, output, addrlib, lod=1):
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
    chosen = [choose_tile(groups[f'{col}-{row}']) for col in columns for row in range(10)]
    tile_size = decode_tile(chosen[0], addrlib).width
    image = Image.new('RGB', (tile_size * 12, tile_size * 10))
    for index, path in enumerate(chosen):
        tile = decode_tile(path, addrlib)
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
    for filename in ('worlds/botw/data/chests.json', 'worlds/botw/static/completions.json'):
        for entry in json.loads((ROOT / filename).read_text())['locations']:
            dungeon = entry.get('dungeon')
            match = re.search(r'/CDungeon/(Dungeon\d+)/', entry.get('logical_map', ''))
            if match:
                dungeon = match[1]
            anchor = dungeon or (f"Tower{entry['tower']:02}" if entry.get('kind') == 'tower' else None)
            if anchor in markers:
                positions[str(entry['id'])] = {'position': markers[anchor], 'source': 'entrance' if match else 'landmark'}
    output.mkdir(parents=True, exist_ok=True)
    image.save(output / 'map.webp', quality=95, method=6)
    (output / 'map.json').write_text(json.dumps({'version': 1, 'bounds': [-6000, -5000, 6000, 5000],
        'width': image.width, 'height': image.height, 'positions': positions}, indent=2) + '\n')
    print(f'Wrote {image.width}×{image.height} map and {len(positions)} shrine/tower positions to {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cemu-data', type=Path, default=Path.home() / '.local/share/Cemu')
    parser.add_argument('--base', type=Path)
    parser.add_argument('--update', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'out/tracker')
    parser.add_argument('--bfres-tool', type=Path, default=ROOT / 'out/tools/BFRES-Tool')
    parser.add_argument('--lod', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    sys.path.insert(0, str(args.bfres_tool.resolve()))
    try:
        import addrlib
    except ImportError:
        parser.error('Clone https://github.com/aboood40091/BFRES-Tool into out/tools/BFRES-Tool or pass --bfres-tool.')
    roots = [args.base] if args.base else sorted((args.cemu_data / 'mlc01/usr/title/00050000').glob('101c*/content'))
    if args.update:
        roots.append(args.update)
    elif not args.base:
        roots.extend(sorted((args.cemu_data / 'mlc01/usr/title/0005000e').glob('101c*/content')))
    roots = [root for root in roots if root and root.is_dir()]
    if not roots:
        parser.error('No installed BotW content found; pass --base and --update content directories.')
    build(roots, args.output, addrlib, args.lod)


if __name__ == '__main__':
    main()
