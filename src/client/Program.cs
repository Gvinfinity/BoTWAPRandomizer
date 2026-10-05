using BotWClient.Memory;
using BotWClient.Archipelago;

namespace BotWClient;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--self-test-pack") return TestHarness.ValidatePack(args[1]);
        if (args.Length == 2 && args[0] == "--self-test-tls") return TestHarness.Run(args[1]);
        if (args.Contains("--self-test") || args.Contains("--mock")) return TestHarness.Run();
        string? Option(string name) { int index = Array.IndexOf(args, name); return index >= 0 && index + 1 < args.Length ? args[index + 1] : null; }
        string? server = Option("--server"), slot = Option("--slot");
        if (server is null || slot is null)
        {
            Console.WriteLine("Usage: BotWClient --server host[:port]|ws://host[:port]|wss://host[:port] [--port number] --slot name [--password value] [--state-dir path] [--verbose]\n       Bare hosts negotiate WSS then WS, default port 38281. Explicit URLs use ports 80/443 unless specified.\n       BotWClient --self-test");
            return 1;
        }
        string directory = Option("--state-dir") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BotWAP", "state");
        using var cancellation = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancellation.Cancel(); };
        bool verbose = args.Contains("--verbose");
        var log = new ClientLog(verbose, Option("--password"));
        try
        {
            foreach (string option in new[] { "--server", "--port", "--slot", "--password", "--state-dir" })
                if (args.Contains(option) && (Option(option) is not { } value || value.StartsWith("--", StringComparison.Ordinal)))
                    throw new ArgumentException($"{option} requires a value.");
            var endpoint = ServerEndpoint.Parse(server, Option("--port"));
            log.Write($"BotWClient {typeof(Program).Assembly.GetName().Version}; .NET {Environment.Version}; {System.Runtime.InteropServices.RuntimeInformation.OSDescription}");
            log.Write($"AP endpoint: {ServerEndpoint.Describe(endpoint)}; slot={slot}; password={(Option("--password") is null ? "not supplied" : "supplied")}");
            log.Write($"Journal directory: {Path.GetFullPath(directory)}");
            if (args.Contains("--diagnose"))
            {
                APSessionManager.DiagnoseConnection(endpoint.AbsoluteUri, slot, Option("--password"), log.Write);
                return 0;
            }
            using var mailbox = new Mailbox(CemuMemoryReader.Attach(verbose, log.Write));
            log.Write($"Mailbox fingerprint={mailbox.Fingerprint}, incoming={mailbox.InHead}/{mailbox.InTail}, outgoing={mailbox.OutHead}/{mailbox.OutTail}, ack={mailbox.AckSequence}, delivery_error={mailbox.DeliveryError}");
            using var initial = new APSessionManager(endpoint.AbsoluteUri, slot, Option("--password"), mailbox, log.Write);
            using var bridge = new ClientBridge(mailbox, initial.Contract, directory, initial.Team, initial.Slot, log.Write);
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
                            log.Write("Starting AP reconnect attempt.");
                            var replacement = new APSessionManager(endpoint.AbsoluteUri, slot, Option("--password"), mailbox, log.Write);
                            if (replacement.Team != initial.Team || replacement.Slot != initial.Slot) { replacement.Dispose(); throw new InvalidDataException("AP login identity changed"); }
                            if (!ReferenceEquals(current, initial)) current.Dispose();
                            current = replacement; bridge.Reconnected();
                        }
                        catch (IOException ex) { log.Write(ex.ToString()); Console.WriteLine(ex.Message); continue; }
                    }
                    try { bridge.Pump(current); }
                    catch (IOException ex) when (!current.Connected) { log.Write(ex.ToString()); continue; }
                    if (bridge.BlockReason != lastReason)
                    {
                        lastReason = bridge.BlockReason;
                        if (lastReason is not null) Console.WriteLine(lastReason);
                        log.Write($"Delivery status: {lastReason ?? "ready"}");
                    }
                    cancellation.Token.WaitHandle.WaitOne(20);
                }
            }
            finally { if (!ReferenceEquals(current, initial)) current.Dispose(); }
            return 0;
        }
        catch (Exception ex) { if (verbose) log.Write(ex.ToString()); else Console.Error.WriteLine(ex.Message); return 1; }
    }
}
