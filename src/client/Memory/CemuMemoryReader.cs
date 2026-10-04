using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Buffers.Binary;

namespace BotWClient.Memory
{
    public struct IncomingItem
    {
        public uint SeqId;
        public uint ApItemId;
        public string ActorName;
        public uint Quantity;
        public uint Flags;
    }

    public struct OutgoingCheck
    {
        public uint SeqId;
        public ulong ApLocationId;
        public uint IsShop;
    }

    public class CemuMemoryReader
    {
        private const int OFF_MAGIC      = 0x00;
        private const int OFF_STATUS     = 0x08;
        private const int OFF_IN_HEAD    = 0x0C;
        private const int OFF_IN_TAIL    = 0x10;
        private const int OFF_OUT_HEAD   = 0x14;
        private const int OFF_OUT_TAIL   = 0x18;
        private const int OFF_TICK_COUNT = 0x1C;
        
        private const int OFF_INCOMING_QUEUE = 0x20;
        // Incoming Queue is now 256 * 64 = 16384 (0x4000) bytes!
        private const int OFF_OUTGOING_QUEUE = 0x4020;

        private Process? _cemuProcess;
        private ulong _hostMailboxAddress = 0;
        private string _memFile = "";
        private bool _verbose;

        public int GetCemuPid() => _cemuProcess != null ? _cemuProcess.Id : 0;
        public bool IsConnected => _hostMailboxAddress != 0;

        public CemuMemoryReader(bool verbose = false)
        {
            _verbose = verbose;
            AttachToCemu();
        }

        private void Log(string msg)
        {
            if (_verbose) Console.WriteLine($"  [DBG] {msg}");
        }

        private void AttachToCemu()
        {
            var processes = Process.GetProcessesByName("Cemu");
            if (processes.Length == 0) return;

            _cemuProcess = processes[0];
            _memFile = $"/proc/{_cemuProcess.Id}/mem";

            string mapsFile = $"/proc/{_cemuProcess.Id}/maps";
            if (!File.Exists(mapsFile)) return;

            var lines = File.ReadAllLines(mapsFile);
            byte[] targetBE = { 0x41, 0x50, 0x4D, 0x42, 0x42, 0x4F, 0x54, 0x57 }; 

            using var fs = new FileStream(_memFile, FileMode.Open, FileAccess.Read);

            foreach (var line in lines)
            {
                if (!line.Contains("rw-p") && !line.Contains("rwxp")) continue;

                var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                var addrRange = parts[0].Split('-');
                ulong start = Convert.ToUInt64(addrRange[0], 16);
                ulong end = Convert.ToUInt64(addrRange[1], 16);
                ulong size = end - start;

                if (size > 2000UL * 1024 * 1024) continue;

                try {
                    fs.Position = (long)start;
                    byte[] chunk = new byte[size];
                    int read = fs.Read(chunk, 0, (int)size);
                    
                    for (int i = 0; i < read - 8; i += 4)
                    {
                        bool matchBE = true;
                        for (int j = 0; j < 8; j++) {
                            if (chunk[i+j] != targetBE[j]) { matchBE = false; break; }
                        }
                        if (matchBE)
                        {
                            _hostMailboxAddress = start + (ulong)i;
                            Log($"Mailbox found at host 0x{_hostMailboxAddress:X}!");
                            return;
                        }
                    }
                } catch { }
            }
        }

        public void PrintHookStatus()
        {
            if (!IsConnected) {
                Console.WriteLine("  Hook Status: Not Ready (Magic signature not found in RAM)");
                return;
            }
            try
            {
                using var fs = new FileStream(_memFile, FileMode.Open, FileAccess.Read);
                using var br = new BinaryReader(fs);

                fs.Position = (long)_hostMailboxAddress;
                byte[] header = br.ReadBytes(0x20);
                
                uint status = BinaryPrimitives.ReverseEndianness(BitConverter.ToUInt32(header, OFF_STATUS));
                uint ticks = BinaryPrimitives.ReverseEndianness(BitConverter.ToUInt32(header, OFF_TICK_COUNT));
                
                uint inHead = BinaryPrimitives.ReverseEndianness(BitConverter.ToUInt32(header, OFF_IN_HEAD));
                uint inTail = BinaryPrimitives.ReverseEndianness(BitConverter.ToUInt32(header, OFF_IN_TAIL));
                uint outHead = BinaryPrimitives.ReverseEndianness(BitConverter.ToUInt32(header, OFF_OUT_HEAD));
                uint outTail = BinaryPrimitives.ReverseEndianness(BitConverter.ToUInt32(header, OFF_OUT_TAIL));

                Console.WriteLine($"  Host Mailbox = 0x{_hostMailboxAddress:X}");
                Console.WriteLine($"  Hook Status: {(status == 2 ? "In Game" : "Not Ready")}  |  Tick Count: {ticks}");
                Console.WriteLine($"  Q_IN: H={inHead} T={inTail}  |  Q_OUT: H={outHead} T={outTail}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error reading status: {ex.Message}");
            }
        }

        public bool WriteIncomingItem(IncomingItem item)
        {
            if (!IsConnected) return false;
            try
            {
                using var fs = new FileStream(_memFile, FileMode.Open, FileAccess.ReadWrite);
                using var br = new BinaryReader(fs);
                using var bw = new BinaryWriter(fs);

                fs.Position = (long)_hostMailboxAddress + OFF_IN_HEAD;
                uint inHead = BinaryPrimitives.ReverseEndianness(br.ReadUInt32());
                fs.Position = (long)_hostMailboxAddress + OFF_IN_TAIL;
                uint inTail = BinaryPrimitives.ReverseEndianness(br.ReadUInt32());

                if (inHead - inTail >= 256) return false;

                // Incoming item is now 64 bytes!
                ulong itemOffset = _hostMailboxAddress + OFF_INCOMING_QUEUE + ((inHead % 256) * 64);
                fs.Position = (long)itemOffset;

                bw.Write(BinaryPrimitives.ReverseEndianness(item.SeqId));
                bw.Write(BinaryPrimitives.ReverseEndianness(item.ApItemId));

                // Name is now 48 bytes maximum.
                byte[] nameBytes = new byte[48];
                if (!string.IsNullOrEmpty(item.ActorName))
                {
                    Encoding.ASCII.GetBytes(item.ActorName, 0, Math.Min(item.ActorName.Length, 47), nameBytes, 0);
                }
                bw.Write(nameBytes);
                bw.Write(BinaryPrimitives.ReverseEndianness(item.Quantity));
                bw.Write(BinaryPrimitives.ReverseEndianness(item.Flags));

                fs.Position = (long)_hostMailboxAddress + OFF_IN_HEAD;
                bw.Write(BinaryPrimitives.ReverseEndianness(inHead + 1));
                return true;
            }
            catch
            {
                return false;
            }
        }

        public OutgoingCheck? ReadOutgoingCheck()
        {
            if (!IsConnected) return null;
            try
            {
                using var fs = new FileStream(_memFile, FileMode.Open, FileAccess.ReadWrite);
                using var br = new BinaryReader(fs);
                using var bw = new BinaryWriter(fs);

                fs.Position = (long)_hostMailboxAddress + OFF_OUT_HEAD;
                uint outHead = BinaryPrimitives.ReverseEndianness(br.ReadUInt32());
                fs.Position = (long)_hostMailboxAddress + OFF_OUT_TAIL;
                uint outTail = BinaryPrimitives.ReverseEndianness(br.ReadUInt32());

                if (outTail == outHead) return null;

                ulong checkOffset = _hostMailboxAddress + OFF_OUTGOING_QUEUE + ((outTail % 256) * 16);
                fs.Position = (long)checkOffset;

                OutgoingCheck check = new OutgoingCheck
                {
                    SeqId = BinaryPrimitives.ReverseEndianness(br.ReadUInt32()),
                    ApLocationId = BinaryPrimitives.ReverseEndianness(br.ReadUInt64()),
                    IsShop = BinaryPrimitives.ReverseEndianness(br.ReadUInt32())
                };

                fs.Position = (long)_hostMailboxAddress + OFF_OUT_TAIL;
                bw.Write(BinaryPrimitives.ReverseEndianness(outTail + 1));
                return check;
            }
            catch
            {
                return null;
            }
        }
    }
}
