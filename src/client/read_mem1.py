import os, sys
def get_cemu_pid():
    pids = os.popen("pidof Cemu").read().strip().split()
    return int(pids[0]) if pids else None

pid = get_cemu_pid()
if not pid: sys.exit(1)

# MEM1 is usually ~32MB or 64MB and contains the executable code.
# Alternatively, look for executable mappings.
with open(f"/proc/{pid}/maps", "r") as f:
    for line in f:
        # Cemu maps Wii U memory. MEM1 is mapped somewhere.
        # But wait, we can just search for the specific byte pattern of a known function?
        # Let's just print all rw-p or rwxp mappings between 30MB and 70MB.
        parts = line.split()
        if len(parts) < 1: continue
        start, end = [int(x, 16) for x in parts[0].split("-")]
        size = end - start
        if 30 * 1024 * 1024 <= size <= 80 * 1024 * 1024:
            print(f"Potential MEM1: {hex(start)} - {hex(end)} ({size/1024/1024} MB) {parts[1]}")
