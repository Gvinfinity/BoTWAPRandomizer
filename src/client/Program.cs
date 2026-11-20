using System.Collections.Concurrent;
using System.Text.Json;
using BotWClient.Memory;
using BotWClient.Archipelago;
using BotWClient.Tracker;
using Microsoft.Win32.SafeHandles;

namespace BotWClient;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Contains("--self-test-tracker")) return TrackerTests.Run();
        if (args.Length == 2 && args[0] == "--cemu-test") return CemuIntegrationTest.Run(args[1]);
        if (args.Length == 2 && args[0] == "--self-test-pack") return TestHarness.ValidatePack(args[1]);
        if (args.Length == 2 && args[0] == "--self-test-tls") return TestHarness.Run(args[1]);
        if (args.Contains("--self-test") || args.Contains("--mock")) return TestHarness.Run();
        string? Option(string name) { int index = Array.IndexOf(args, name); return index >= 0 && index + 1 < args.Length ? args[index + 1] : null; }
        if (args.Contains("--tracker-only"))
        {
            try
            {
                using var preview = new TrackerServer(int.Parse(Option("--tracker-port") ?? "38282"), mapDirectory: Option("--tracker-map-dir"));
                preview.Publish("catalog-preview", "Catalog preview · no live game", false, [], 0, null);
                Console.WriteLine($"Tracker: {preview.Url} (catalog preview; Ctrl+C to exit)");
                using var stop = new ManualResetEventSlim();
                Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop.Set(); };
                stop.Wait(); return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex.Message); return 1; }
        }
        string? server = Option("--server"), slot = Option("--slot");
        bool launchedFromGui = args.Contains("--launcher");
        string? password = Option("--password");
        if (launchedFromGui && password is null)
        {
            password = Environment.GetEnvironmentVariable("BOTWAP_ROOM_PASSWORD");
            Environment.SetEnvironmentVariable("BOTWAP_ROOM_PASSWORD", null);
            if (password == "") password = null;
        }
        if (args.Contains("--interactive") && !Console.IsInputRedirected)
        {
            if (server is null) { Console.Write("Archipelago server (host:port): "); server = Console.ReadLine()?.Trim(); }
            if (slot is null) { Console.Write("Player name: "); slot = Console.ReadLine()?.Trim(); }
            if (password is null && !args.Contains("--password") &&
                !string.IsNullOrWhiteSpace(server) && !string.IsNullOrWhiteSpace(slot))
            {
                Console.Write("Room password (Enter if none): ");
                var input = new System.Text.StringBuilder();
                for (var key = Console.ReadKey(intercept: true); key.Key != ConsoleKey.Enter;
                     key = Console.ReadKey(intercept: true))
                {
                    if (key.Key == ConsoleKey.Backspace && input.Length > 0) input.Length--;
                    else if (!char.IsControl(key.KeyChar)) input.Append(key.KeyChar);
                }
                Console.WriteLine();
                if (input.Length > 0) password = input.ToString();
            }
        }
        if (string.IsNullOrWhiteSpace(server) || string.IsNullOrWhiteSpace(slot))
        {
            Console.WriteLine("Tracker: add --tracker [--tracker-port 38282] for a local browser map. Use --tracker-only to preview without Cemu or AP.\n       Tests: --self-test-tracker\n");
            Console.WriteLine("Usage: BotWClient --server host[:port]|ws://host[:port]|wss://host[:port] [--port number] --slot name [--password value] [--state-dir path] [--verbose]\n       Bare hosts negotiate WSS then WS, default port 38281. Explicit URLs use ports 80/443 unless specified.\n       BotWClient --interactive | --self-test");
            return 1;
        }
        string directory = Option("--state-dir") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BotWAP", "state");
        using var cancellation = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancellation.Cancel(); };
        var commands = new ConcurrentQueue<string>();
        if (launchedFromGui)
        {
            _ = Task.Run(() =>
            {
                string? line;
                while ((line = Console.ReadLine()) is not null) commands.Enqueue(line);
                cancellation.Cancel();
            });
        }
        void Emit(object message)
        {
            Console.WriteLine("@BOTWAP@" + JsonSerializer.Serialize(message));
        }
        Action<object>? events = launchedFromGui ? Emit : null;
        bool verbose = args.Contains("--verbose");
        var log = new ClientLog(verbose, password);
        try
        {
            foreach (string option in new[] { "--server", "--port", "--slot", "--password", "--state-dir", "--cemu-pid", "--cemu-mem-fd" })
                if (args.Contains(option) && (Option(option) is not { } value || value.StartsWith("--", StringComparison.Ordinal)))
                    throw new ArgumentException($"{option} requires a value.");
            var endpoint = ServerEndpoint.Parse(server, Option("--port"));
            log.Write($"BotWClient {typeof(Program).Assembly.GetName().Version}; .NET {Environment.Version}; {System.Runtime.InteropServices.RuntimeInformation.OSDescription}");
            log.Write($"AP endpoint: {ServerEndpoint.Describe(endpoint)}; slot={slot}; password={(password is null ? "not supplied" : "supplied")}");
            log.Write($"Journal directory: {Path.GetFullPath(directory)}");
            if (args.Contains("--diagnose"))
            {
                APSessionManager.DiagnoseConnection(endpoint.AbsoluteUri, slot, password, log.Write);
                return 0;
            }
            int? cemuPid = Option("--cemu-pid") is { } pid ? int.Parse(pid) : null;
            int? memoryFd = Option("--cemu-mem-fd") is { } fd ? int.Parse(fd) : null;
            if (cemuPid is <= 0 || (memoryFd.HasValue &&
                (!launchedFromGui || !OperatingSystem.IsLinux() || cemuPid is null || memoryFd < 3)))
                throw new ArgumentException("Invalid Cemu process or inherited memory descriptor.");
            using var memoryHandle = memoryFd is { } descriptor
                ? new SafeFileHandle((nint)descriptor, ownsHandle: true) : null;
            using var mailbox = new Mailbox(CemuMemoryReader.Attach(verbose, log.Write, cemuPid, memoryHandle));
            log.Write($"Mailbox fingerprint={mailbox.Fingerprint}, guest_addr=0x{mailbox.GuestAddress:X8}, incoming={mailbox.InHead}/{mailbox.InTail}, outgoing={mailbox.OutHead}/{mailbox.OutTail}, ack={mailbox.AckSequence}");
            using var initial = new APSessionManager(endpoint.AbsoluteUri, slot, password, mailbox, log.Write, events);
            using var bridge = new ClientBridge(mailbox, initial.Contract, directory, initial.Team, initial.Slot, log.Write);
            APSessionManager current = initial;
            using var tracker = args.Contains("--tracker")
                ? new TrackerServer(int.Parse(Option("--tracker-port") ?? "38282"), initial.Contract.Locations, Option("--tracker-map-dir")) : null;
            if (tracker is not null) Console.WriteLine($"Tracker: {tracker.Url}");
            long trackerUpdate = 0;
            string? lastReason = null;
            Console.WriteLine($"Connected to AP, team {initial.Team}, slot {initial.Slot}. Seed pack verified. Ctrl+C to exit.");
            try
            {
                while (!cancellation.IsCancellationRequested)
                {
                    if (tracker is not null && Environment.TickCount64 >= trackerUpdate)
                    {
                        tracker.Publish($"{initial.Contract.Fingerprint}-T{initial.Team}-P{initial.Slot}", slot,
                            current.Connected, bridge.TrackerChecks.Concat(current.CheckedLocations),
                            current.ReceivedItems.Count, bridge.BlockReason, current.TrackerInventory(), bridge.NextItem);
                        trackerUpdate = Environment.TickCount64 + 1000;
                    }
                    if (!current.Connected)
                    {
                        bridge.Pump(current); // Persist checks even while the connection is down.
                        Console.WriteLine("AP disconnected. Reconnecting in 5 seconds...");
                        if (cancellation.Token.WaitHandle.WaitOne(5000)) break;
                        try
                        {
                            log.Write("Starting AP reconnect attempt.");
                            var replacement = new APSessionManager(endpoint.AbsoluteUri, slot, password, mailbox, log.Write, events);
                            if (replacement.Team != initial.Team || replacement.Slot != initial.Slot) { replacement.Dispose(); throw new InvalidDataException("AP login identity changed"); }
                            if (!ReferenceEquals(current, initial)) current.Dispose();
                            current = replacement; bridge.Reconnected();
                        }
                        catch (IOException ex) { log.Write(ex.ToString()); Console.WriteLine(ex.Message); continue; }
                    }
                    while (commands.TryDequeue(out string? command))
                    {
                        if (command == "/help")
                            Console.WriteLine("Enter chat or server commands such as !help, !hint, and !remaining. Use /help for this message.");
                        else if (command.StartsWith('/'))
                            Console.WriteLine($"Unknown client command: {command}");
                        else if (current.Connected)
                        {
                            try { current.SendMessage(command); }
                            catch (Exception ex) { Console.WriteLine($"Unable to send message: {ex.Message}"); }
                        }
                        else Console.WriteLine("Message not sent. The server is disconnected.");
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
