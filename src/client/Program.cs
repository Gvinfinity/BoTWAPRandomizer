using System;
using System.Threading;
using BotWClient.Memory;
using System.IO;

namespace BotWClient
{
    class Program
    {
        static void Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--mock")
            {
                new TestHarness().RunInteractiveTest();
                return;
            }

            bool verbose = Array.Exists(args, a => a == "--verbose" || a == "-v");

            Console.WriteLine("--- BotW AP Live Client (Linux) ---");
            Console.WriteLine("Attempting to connect to Cemu...");
            
            var reader = new CemuMemoryReader(verbose: true);
            if (!reader.IsConnected)
            {
                Console.WriteLine("Make sure Cemu is running, the game is loaded, and you have sudo permissions if required.");
                return;
            }
            
            // --- DEBUG DUMP ---
            try {
                ulong mem1_start = 0;
                string[] maps = File.ReadAllLines($"/proc/{reader.GetCemuPid()}/maps");
                foreach(var line in maps) {
                    if (line.Contains("rwxp")) {
                        var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                        var addrRange = parts[0].Split('-');
                        ulong start = Convert.ToUInt64(addrRange[0], 16);
                        ulong end = Convert.ToUInt64(addrRange[1], 16);
                        ulong size = end - start;
                        if (size == 32 * 1024 * 1024) { // Exactly 32MB
                            mem1_start = start;
                            break;
                        }
                    }
                }

                if (mem1_start != 0) {
                    ulong[] addrs = { 0x0303E4C0, 0x03780D7C, 0x03741B20, 0x0313B840, 0x037B6040, 0x0321F534 };
                    using var fs = new FileStream($"/proc/{reader.GetCemuPid()}/mem", FileMode.Open, FileAccess.Read);
                    var br = new BinaryReader(fs);
                    Console.WriteLine($"\n--- MEMORY DIAGNOSTICS (MEM1: {mem1_start:X}) ---");
                    foreach (var guestAddr in addrs) {
                        ulong hostAddr = mem1_start + (guestAddr - 0x02000000);
                        fs.Position = (long)hostAddr;
                        byte[] data = br.ReadBytes(16);
                        Console.Write($"Guest 0x{guestAddr:X8}: ");
                        foreach(var b in data) Console.Write($"{b:X2} ");
                        Console.WriteLine();
                    }
                    Console.WriteLine("--------------------------\n");
                }
            } catch (Exception ex) {
                Console.WriteLine("Diagnostics failed: " + ex.Message);
            }
            // ------------------

            Console.WriteLine("\n[Connected!] Live Memory Link established.");
            Console.WriteLine("In-game, pick up any vanilla item/weapon to send a location check.");
            Console.WriteLine("Press 2 and enter to add a full-durability Weapon_Sword_001 to the pouch.");
            Console.WriteLine("Press s and enter to print hook status.");
            
            // Poll for outgoing checks (Chest opens)
            var pollThread = new Thread(() => {
                while (true)
                {
                    var check = reader.ReadOutgoingCheck();
                    if (check.HasValue)
                    {
                        Console.WriteLine($"\n[Cemu -> Client] Location Check complete! ID: 0x{check.Value.ApLocationId:X}");
                        Console.Write("> ");
                    }
                    Thread.Sleep(100);
                }
            });
            pollThread.IsBackground = true;
            pollThread.Start();

            // Interactive input
            while (true)
            {
                Console.Write("> ");
                string? input = Console.ReadLine();
                if (input == "2")
                {
                    bool success = reader.WriteIncomingItem(new IncomingItem 
                    {
                        ApItemId = 0x4001,
                        ActorName = "Weapon_Sword_001",
                        Quantity = 1,
                        Flags = 0
                    });
                    
                    if (success) 
                        Console.WriteLine("[Client -> Cemu] Sent Weapon_Sword_001 to Link!");
                    else
                        Console.WriteLine("Failed to write to Cemu memory.");
                }
                else if (input == "s" || input == "status")
                {
                    reader.PrintHookStatus();
                }
            }
        }
    }
}
