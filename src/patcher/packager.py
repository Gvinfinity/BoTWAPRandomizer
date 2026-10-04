import zipfile
import os
import shutil

def create_graphic_pack(output_path: str, patch_dir: str):
    """
    Zips up rules.txt, patches.txt, and the modified root/ maps.
    """
    print(f"Creating graphic pack at {output_path}")
    # ...
