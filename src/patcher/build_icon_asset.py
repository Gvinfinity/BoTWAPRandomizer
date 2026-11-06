"""Maintenance helper: convert the supplied AP icon; requires Pillow."""
from pathlib import Path
import zlib


def main():
    from PIL import Image
    assets = Path(__file__).resolve().parents[2] / 'worlds/botw/static/assets'
    with Image.open(assets / 'archipelago.png') as image:
        pixels = image.convert('RGBA').resize((96, 96), Image.Resampling.LANCZOS).tobytes()
    (assets / 'archipelago.rgba.zlib').write_bytes(zlib.compress(pixels, 9))


if __name__ == '__main__':
    main()
