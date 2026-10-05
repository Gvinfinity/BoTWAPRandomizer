using System;
using System.Diagnostics;
using System.IO;
using System.Buffers.Binary;

class Program {
    static void Main() {
        var processes = Process.GetProcessesByName("Cemu");
        if (processes.Length == 0) return;
        var cemu = processes[0];
        string mapsFile = $"/proc/{cemu.Id}/maps";
        ulong memBase = 0;
        foreach (var line in File.ReadAllLines(mapsFile)) {
            if (!line.Contains("rw-p")) continue;
            var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            ulong start = Convert.ToUInt64(parts[0].Split('-')[0], 16);
            ulong end = Convert.ToUInt64(parts[0].Split('-')[1], 16);
            if (end - start >= 512UL * 1024 * 1024 && end - start <= 2000UL * 1024 * 1024) {
                // verify mailbox magic
                try {
                    using var fs = new FileStream($"/proc/{cemu.Id}/mem", FileMode.Open, FileAccess.Read);
                    fs.Position = (long)(start + 0x11000000);
                    byte[] chunk = new byte[8];
                    fs.Read(chunk, 0, 8);
                    if (chunk[0]==0x41 && chunk[1]==0x50) {
                        memBase = start;
                        break;
                    }
                } catch {}
            }
        }
        if (memBase == 0) return;
        using var mem = new FileStream($"/proc/{cemu.Id}/mem", FileMode.Open, FileAccess.Read);
        
        ulong[] targets = { 0x02EB5AB8, 0x02EB3DF0, 0x03741B20 };
        foreach (var target in targets) {
            mem.Position = (long)(memBase + target);
            byte[] inst = new byte[4];
            mem.Read(inst, 0, 4);
            uint val = BinaryPrimitives.ReverseEndianness(BitConverter.ToUInt32(inst));
            Console.WriteLine($"0x{target:X8}: {val:X8}");
        }
    }
}
