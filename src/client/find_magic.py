import sys
import os
import struct

def find_magic():
    pids = os.popen("pidof Cemu").read().strip().split()
    if not pids:
        print("Cemu not running")
        return
    pid = int(pids[0])
    
    magic = struct.pack("<I", 0x424F5457) # BOTW
    version = struct.pack("<I", 1)
    target = magic + version
    
    # Also try big-endian just in case
    magic_be = struct.pack(">I", 0x424F5457)
    version_be = struct.pack(">I", 1)
    target_be = magic_be + version_be

    with open(f"/proc/{pid}/maps", "r") as maps, open(f"/proc/{pid}/mem", "rb") as mem:
        for line in maps:
            if "rw" not in line: continue
            parts = line.split()
            start, end = [int(x, 16) for x in parts[0].split("-")]
            
            # Skip huge non-memory regions to avoid slow scans, but keep typical mem ranges
            if end - start > 2 * 1024 * 1024 * 1024: continue
            
            try:
                mem.seek(start)
                chunk = mem.read(end - start)
                idx = chunk.find(target)
                if idx != -1:
                    print(f"Found LE magic at host {hex(start + idx)}")
                idx_be = chunk.find(target_be)
                if idx_be != -1:
                    print(f"Found BE magic at host {hex(start + idx_be)}")
            except Exception as e:
                pass

find_magic()
