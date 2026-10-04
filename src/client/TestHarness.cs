using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using BotWClient.Memory;

namespace BotWClient
{
    // MOCK FOR LINUX Cemu Native (Reading memory map)
    // Normally you would use /proc/PID/mem and /proc/PID/maps
    public class TestHarness
    {
        // For testing on a local machine without a real Cemu process, 
        // we can allocate a local byte array to simulate Cemu memory.
        private byte[] _simulatedCemuRam = new byte[1024 * 1024]; // 1MB mock
        private int _mailboxOffset = 0x0; 

        public void RunInteractiveTest()
        {
            Console.WriteLine("--- BotW AP Hook Interactive Test ---");
            Console.WriteLine("1. Start test loop (Mocking AP Server)");
            Console.WriteLine("2. Simulate Cemu receiving 'Weapon_Sword_001' from AP");
            Console.WriteLine("3. Simulate Cemu opening a chest (sending check to AP)");
            
            // Initialize Mock Mailbox Magic
            using (var ms = new MemoryStream(_simulatedCemuRam))
            using (var bw = new BinaryWriter(ms))
            {
                bw.Write(0x424F5457); // Magic
                bw.Write(0x00000001); // Version
            }

            // Test loop thread
            var apThread = new Thread(() => {
                uint lastProcessedOut = 0;
                while (true)
                {
                    using (var ms = new MemoryStream(_simulatedCemuRam))
                    using (var br = new BinaryReader(ms))
                    {
                        ms.Position = 0x14; // Out_Head
                        uint outHead = br.ReadUInt32();
                        
                        if (outHead > lastProcessedOut)
                        {
                            ms.Position = 0x2020 + (lastProcessedOut % 256) * 16; // Outgoing Queue Offset
                            uint seq = br.ReadUInt32();
                            ulong locId = br.ReadUInt64();
                            Console.WriteLine($"[AP Client] Received check! Location ID: {locId:X}");
                            lastProcessedOut++;
                        }
                    }
                    Thread.Sleep(100);
                }
            });
            apThread.IsBackground = true;
            apThread.Start();

            while (true)
            {
                Console.Write("> ");
                string? input = Console.ReadLine();
                if (input == "2")
                {
                    SimulateReceiveItem();
                }
                else if (input == "3")
                {
                    SimulateSendCheck();
                }
            }
        }

        private void SimulateReceiveItem()
        {
            using (var ms = new MemoryStream(_simulatedCemuRam))
            using (var bw = new BinaryWriter(ms))
            using (var br = new BinaryReader(ms))
            {
                ms.Position = 0x0C; // In_Head
                uint inHead = br.ReadUInt32();

                ms.Position = 0x20 + (inHead % 256) * 32; // Incoming Queue Offset
                bw.Write(inHead); // seqId
                bw.Write(0x4001); // Item ID
                
                var nameBytes = System.Text.Encoding.ASCII.GetBytes("Weapon_Sword_001");
                var padded = new byte[16];
                Array.Copy(nameBytes, padded, Math.Min(nameBytes.Length, 16));
                bw.Write(padded);
                
                bw.Write(1u); // quantity
                bw.Write(0u); // flags

                ms.Position = 0x0C; // Update In_Head
                bw.Write(inHead + 1);
            }
            Console.WriteLine("[Client] Inserted Weapon_Sword_001 into Mailbox. Hook will grant it on next tick.");
        }

        private void SimulateSendCheck()
        {
            using (var ms = new MemoryStream(_simulatedCemuRam))
            using (var bw = new BinaryWriter(ms))
            using (var br = new BinaryReader(ms))
            {
                ms.Position = 0x14; // Out_Head
                uint outHead = br.ReadUInt32();

                ms.Position = 0x2020 + (outHead % 256) * 16;
                bw.Write(outHead); // seq
                bw.Write(0x5000UL); // Loc ID
                bw.Write(0u); // IsShop

                ms.Position = 0x14;
                bw.Write(outHead + 1);
            }
            Console.WriteLine("[Hook] Wrote chest check to Mailbox.");
        }
    }
}
