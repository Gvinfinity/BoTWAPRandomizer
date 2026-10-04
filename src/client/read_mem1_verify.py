import sys
pid = int(sys.argv[1])
mem1_start = 0x7f169f600000
with open(f"/proc/{pid}/mem", "rb") as f:
    for addr in [0x0303E4C0, 0x03780D7C, 0x03741B20, 0x0313B840]:
        offset = addr - 0x02000000
        f.seek(mem1_start + offset)
        data = f.read(16)
        print(f"Guest {hex(addr)}: " + " ".join([f"{b:02X}" for b in data]))
