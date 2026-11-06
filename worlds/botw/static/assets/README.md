# Archipelago icon

`archipelago.png` is copied without artwork changes from `data/icon.png` in
the local Archipelago checkout (https://github.com/ArchipelagoMW/Archipelago).
The upstream MIT license is included as `Archipelago-LICENSE.txt`.

`archipelago.rgba.zlib` contains zlib-compressed, row-major RGBA8 pixels resized
to the game's 96 × 96 item icon size with Pillow's Lanczos filter. It contains
only the supplied artwork; no game texture data is distributed here. Regenerate
it with `python src/patcher/build_icon_asset.py` in an environment with Pillow.
Runtime patch application needs only the Python standard library and the normal
patcher dependencies.

The patcher replaces the pixels in the player's own `Item_Ore_A.sbitemico` and
preserves its FTEX surface settings. The fixed RGBA8 tile address formula follows
the Wii U layout described by the
[Cemu address library](https://github.com/cemu-project/Cemu/blob/main/src/Cafe/HW/Latte/LatteAddrLib/LatteAddrLib.cpp).
