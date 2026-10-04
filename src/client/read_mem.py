import os
import sys
import struct
import subprocess

def get_cemu_pid():
    try:
        pids = subprocess.check_output(["pidof", "Cemu"]).decode().strip().split()
        return int(pids[0])
    except:
        return None

def find_mem2(pid):
    with open(f"/proc/{pid}/maps", "r") as f:
        for line in f:
            if "rw-p" in line:
                parts = line.split()
                addr_range = parts[0].split("-")
                start = int(addr_range[0], 16)
                end = int(addr_range[1], 16)
                size = end - start
                if 1024 * 1024 * 1024 <= size <= 1500 * 1024 * 1024: # ~1.2GB
                    return start - 0x10000000
    return None

def read_mem(pid, addr, size):
    with open(f"/proc/{pid}/mem", "rb") as f:
        f.seek(addr)
        return f.read(size)

pid = get_cemu_pid()
if not pid:
    print("Cemu not running")
    sys.exit(1)

mem_base = find_mem2(pid)
if not mem_base:
    print("MEM2 not found")
    sys.exit(1)

print(f"memory_base: {hex(mem_base)}")

addrs_to_check = [
    0x0303E4C0, # Application::calc
    0x03780D7C, # ActorSystem::calc (Example)
    0x03741B20, # ksys::act::ActorSystem Item Pickup
    0x0313B840, # SpawnActors hook
]

for addr in addrs_to_check:
    try:
        data = read_mem(pid, mem_base + addr, 16)
        hex_data = " ".join([f"{b:02X}" for b in data])
        print(f"Address {hex(addr)}: {hex_data}")
    except Exception as e:
        print(f"Failed to read {hex(addr)}: {e}")
