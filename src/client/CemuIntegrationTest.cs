using System.Diagnostics;
using System.Text.Json;
using BotWClient.Archipelago;
using BotWClient.Memory;

namespace BotWClient;

internal static class CemuIntegrationTest
{
    public static int Run(string scenarioPath)
    {
        string? resultPath = null;
        var timer = Stopwatch.StartNew();
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(scenarioPath));
            var config = document.RootElement;
            resultPath = config.GetProperty("result_path").GetString()!;
            var limit = TimeSpan.FromSeconds(config.GetProperty("timeout_seconds").GetInt32());
            if (limit <= TimeSpan.Zero || limit > TimeSpan.FromMinutes(30))
                throw new ArgumentException("Timeout must be between 1 and 1800 seconds");
            string stateDirectory = config.GetProperty("state_directory").GetString()!;
            if (Directory.Exists(stateDirectory)) throw new IOException("Test requires a new journal directory");
            uint location = config.GetProperty("location").GetUInt32();
            uint item = config.GetProperty("item").GetUInt32();
            string actor = config.GetProperty("actor").GetString()!;
            Protocol.ValidateActorName(actor, 1);
            var data = config.GetProperty("slot_data");
            var mapping = data.GetProperty("items").GetProperty(item.ToString());
            if (mapping.GetProperty("kind").GetString() != "actor" || mapping.GetProperty("actor").GetString() != actor)
                throw new InvalidDataException("Scenario actor must match the received item's grant");
            int? pid = config.TryGetProperty("cemu_pid", out var pidValue) ? pidValue.GetInt32() : null;
            CemuMemoryReader? memory = null;
            while (memory is null)
            {
                try { memory = CemuMemoryReader.Attach(true, Console.WriteLine, pid); }
                catch (IOException) when (timer.Elapsed < limit) { Thread.Sleep(1000); }
            }
            using var mailbox = new Mailbox(memory);
            mailbox.Validate();
            uint tick = mailbox.Word(28);
            void Wait(Func<bool> ready, string stage)
            {
                while (!ready())
                {
                    if (timer.Elapsed >= limit) throw new TimeoutException($"Timed out during {stage}");
                    Thread.Sleep(20);
                }
            }
            Wait(() => mailbox.Word(28) != tick && mailbox.GuestAddress != 0 &&
                mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr) != 0, "gameplay readiness");
            var before = mailbox.MeasureStablePouch(mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr), actor);
            using var server = new ProtocolServerFixture(data, location, item, limit);
            using var session = new APSessionManager(server.Uri, "Test", null, mailbox, Console.WriteLine);
            using var bridge = new ClientBridge(mailbox, session.Contract, stateDirectory, session.Team, session.Slot, Console.WriteLine);
            Wait(() => { bridge.Pump(session); return bridge.NextItem == 1; }, "item delivery");
            var after = mailbox.MeasureStablePouch(mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr), actor);
            uint quantity = mapping.TryGetProperty("quantity", out var amount) ? amount.GetUInt32() : 1;
            if (after.Sum != before.Sum + quantity)
                throw new InvalidDataException("Client acknowledged delivery without the expected pouch value increase");
            Wait(() => { bridge.Pump(session); return server.Checks.Task.IsCompleted; }, "chest acquisition and AP LocationChecks");
            if (!server.Checks.Task.GetAwaiter().GetResult().Contains(location))
                throw new InvalidDataException("Server received the wrong location");
            var final = mailbox.MeasureStablePouch(mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr), actor);
            if (final.Sum != after.Sum) throw new InvalidDataException("Received item did not remain in the loaded pouch");
            Write(new { passed = true, elapsed_seconds = timer.Elapsed.TotalSeconds, location, item, actor,
                fingerprint = mailbox.Fingerprint, before_sum = before.Sum, before_count = before.Count,
                after_sum = after.Sum, after_count = after.Count });
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            Write(new { passed = false, elapsed_seconds = timer.Elapsed.TotalSeconds, error = error.ToString() });
            return 1;
        }
        void Write(object result)
        {
            if (resultPath is null) return;
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(resultPath))!);
            File.WriteAllText(resultPath, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        }
    }
}
