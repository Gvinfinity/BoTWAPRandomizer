using BotWClient.Memory;
using BotWClient.Archipelago;

namespace BotWClient;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--self-test-pack") return TestHarness.ValidatePack(args[1]);
        if (args.Contains("--self-test") || args.Contains("--mock")) return TestHarness.Run();
        string? Option(string name) { int index = Array.IndexOf(args, name); return index >= 0 && index + 1 < args.Length ? args[index + 1] : null; }
        string? server = Option("--server"), slot = Option("--slot");
        if (server is null || slot is null)
        {
            Console.WriteLine("Usage: BotWClient --server host:port --slot name [--password value] [--state-dir path] [--verbose]\n       BotWClient --self-test");
            return 1;
        }
        string directory = Option("--state-dir") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BotWAP", "state");
        using var cancellation = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancellation.Cancel(); };
        try
        {
            using var mailbox = new Mailbox(CemuMemoryReader.Attach(args.Contains("--verbose")));
            using var initial = new APSessionManager(server, slot, Option("--password"), mailbox);
            using var bridge = new ClientBridge(mailbox, initial.Contract, directory, initial.Team, initial.Slot);
            APSessionManager current = initial;
            string? lastReason = null;
            Console.WriteLine($"Connected to AP, team {initial.Team}, slot {initial.Slot}. Seed pack verified. Ctrl+C to exit.");
            try
            {
                while (!cancellation.IsCancellationRequested)
                {
                    if (!current.Connected)
                    {
                        bridge.Pump(current); // Persist checks even while the connection is down.
                        Console.WriteLine("AP disconnected. Reconnecting in 5 seconds...");
                        if (cancellation.Token.WaitHandle.WaitOne(5000)) break;
                        try
                        {
                            var replacement = new APSessionManager(server, slot, Option("--password"), mailbox);
                            if (replacement.Team != initial.Team || replacement.Slot != initial.Slot) { replacement.Dispose(); throw new InvalidDataException("AP login identity changed"); }
                            if (!ReferenceEquals(current, initial)) current.Dispose();
                            current = replacement; bridge.Reconnected();
                        }
                        catch (IOException ex) { Console.WriteLine(ex.Message); continue; }
                    }
                    try { bridge.Pump(current); }
                    catch (IOException) when (!current.Connected) { continue; }
                    if (bridge.BlockReason != lastReason)
                    {
                        lastReason = bridge.BlockReason;
                        if (lastReason is not null) Console.WriteLine(lastReason);
                    }
                    cancellation.Token.WaitHandle.WaitOne(20);
                }
            }
            finally { if (!ReferenceEquals(current, initial)) current.Dispose(); }
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex.Message); return 1; }
    }
}
