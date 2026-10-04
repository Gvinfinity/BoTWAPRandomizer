using System;
using System.Threading;

namespace BotWClient
{
    class Program
    {
        static void Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--test")
            {
                new TestHarness().RunInteractiveTest();
                return;
            }

            Console.WriteLine("BotW Archipelago Multiworld Client");
            Console.WriteLine("Run with '--test' to simulate the mailbox hook.");
        }
    }
}
