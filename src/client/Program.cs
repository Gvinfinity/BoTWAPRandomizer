using System;
using System.Threading;
using BotWClient.Memory;
using BotWClient.Archipelago;

namespace BotWClient
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.WriteLine("BotW Archipelago Multiworld Client");
            
            var memoryReader = new CemuMemoryReader();
            
            // In a real run, parse from args or interactive prompt
            string uri = "localhost:38281";
            string slotName = "Player1";

            var apSession = new APSessionManager(uri, slotName, memoryReader);

            Console.WriteLine("Polling memory for outgoing checks...");
            while (true)
            {
                var check = memoryReader.ReadOutgoingCheck();
                if (check.HasValue)
                {
                    apSession.DispatchLocationCheck(check.Value);
                }
                Thread.Sleep(10); // Check latency < 150ms requirement
            }
        }
    }
}
