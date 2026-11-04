using System.Diagnostics;
using System.Text.Json;
using BotWClient.Archipelago;
using BotWClient.Memory;

namespace BotWClient;

internal static class CemuIntegrationTest
{
    public static int Run(string scenarioPath)
    {
        string? resultPath = null, progressPath = null;
        var timer = Stopwatch.StartNew();
        var results = new List<object>();
        string stage = "startup";
        bool chestChecked = false;
        int planned = 0;
        JsonElement? currentCase = null;
        string? blockReason = null;
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(scenarioPath));
            var config = document.RootElement;
            resultPath = config.GetProperty("result_path").GetString()!;
            progressPath = config.TryGetProperty("progress_path", out var pp) ? pp.GetString() : null;
            var limit = TimeSpan.FromSeconds(config.GetProperty("timeout_seconds").GetInt32());
            if (limit <= TimeSpan.Zero || limit > TimeSpan.FromMinutes(30)) throw new ArgumentException("Invalid total timeout");
            var itemLimit = TimeSpan.FromSeconds(config.TryGetProperty("item_timeout_seconds", out var it) ? it.GetInt32() : 15);
            if (itemLimit <= TimeSpan.Zero || itemLimit > TimeSpan.FromMinutes(2)) throw new ArgumentException("Invalid item timeout");
            TimeSpan deadline = limit;
            string stateDirectory = config.GetProperty("state_directory").GetString()!;
            if (Directory.Exists(stateDirectory)) throw new IOException("Test requires a new journal directory");
            uint location = config.GetProperty("location").GetUInt32();
            var data = config.GetProperty("slot_data");
            var cases = config.TryGetProperty("cases", out var list) ? list.EnumerateArray().Select(x => x.Clone()).ToArray() :
                new[] { JsonSerializer.SerializeToElement(new { item = config.GetProperty("item").GetUInt32(), name = "Legacy actor", category = "actor" }) };
            if (cases.Length == 0) throw new InvalidDataException("Scenario has no receipts");
            planned = cases.Length;
            int? pid = config.TryGetProperty("cemu_pid", out var pv) ? pv.GetInt32() : null;
            void CheckDeadline()
            {
                if (timer.Elapsed >= deadline) throw new TimeoutException($"Timed out during {stage}; {blockReason}");
                if (pid.HasValue && Process.GetProcessById(pid.Value).HasExited) throw new IOException("Cemu exited");
            }
            void Wait(Func<bool> ready, string waiting)
            {
                stage = waiting; Progress();
                while (true)
                {
                    CheckDeadline();
                    if (ready()) return;
                    Thread.Sleep(10);
                }
            }
            Progress();
            CemuMemoryReader? memory = null;
            while (memory is null)
            {
                CheckDeadline();
                try { memory = CemuMemoryReader.Attach(false, null, pid); }
                catch (IOException) { Thread.Sleep(250); }
            }
            using var mailbox = new Mailbox(memory);
            mailbox.Validate();
            uint tick = mailbox.Word(28);
            bool Active() => mailbox.Status == 2 && mailbox.GuestAddress != 0 && mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr) != 0;
            Wait(() => mailbox.Word(28) != tick && Active(), "gameplay readiness");
            using var server = new ProtocolServerFixture(data, location, cases[0].GetProperty("item").GetUInt32(), limit, manualItems: true);
            using var session = new APSessionManager(server.Uri, "Test", null, mailbox, Console.WriteLine);
            using var bridge = new ClientBridge(mailbox, session.Contract, stateDirectory, session.Team, session.Slot, Console.WriteLine);
            Wait(() => { bridge.Pump(session); return server.Checks.Task.IsCompleted; }, "chest acquisition and AP LocationChecks");
            if (!server.Checks.Task.GetAwaiter().GetResult().Contains(location)) throw new InvalidDataException("Wrong location check");
            chestChecked = true; Progress();

            // The fixture gates receipts. Observation and test cleanup RPCs run only while
            // the production bridge has no grant in flight and the ring is empty.
            uint observationSequence = 0xF0000000;
            RpcResult Call(uint target, uint r3 = 0, uint r4 = 0, uint r5 = 0, uint r6 = 0, uint r7 = 0)
            {
                Wait(Active, "active gameplay for observation");
                if (mailbox.InHead != mailbox.InTail) throw new InvalidDataException("Observation raced a production RPC");
                uint head = mailbox.InHead, seq = ++observationSequence;
                if (!mailbox.Enqueue(new RpcCall(seq, target, r3, r4, r5, r6, r7), head)) throw new IOException("Observation enqueue failed");
                Wait(() => mailbox.InTail == unchecked(head + 1), "native observation RPC");
                if (mailbox.AckSequence != seq) throw new InvalidDataException("Observation acknowledgement mismatch");
                return mailbox.ReadResult(head);
            }
            double ReadFlag(string name, string type)
            {
                if (name == "StaminaMax") return Call(GameOffsets.GdtGetFlagStaminaMax).F1;
                uint manager = mailbox.ReadGuestWord(GameOffsets.GdtManagerPtr);
                if (manager == 0) throw new IOException("GameData manager unavailable");
                uint core = mailbox.GameDataCore(manager, 0x700);
                if (core == 0) throw new IOException("GameData core unavailable");
                uint text = mailbox.WriteSafeString(name);
                mailbox.SetWord(Protocol.Get("scratch_offset") + 64, 0);
                var read = Call(type == "bool" ? GameOffsets.GdtGetBoolByName : GameOffsets.GdtGetS32ByName,
                    core, mailbox.ScratchResultAddress, text, mailbox.ReadGuestWord(manager + 0x704) >> 24, 1);
                if (read.R3 == 0) throw new InvalidDataException("Native observation cannot read " + name);
                uint raw = mailbox.ReadGuestWord(mailbox.ScratchResultAddress);
                return type == "bool" ? (raw == 0 ? 0 : 1) : unchecked((int)raw);
            }
            (uint Sum, uint Count) Pouch(string actor) => mailbox.MeasureStablePouch(mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr), actor);
            void Require(bool condition, string error) { if (!condition) throw new InvalidDataException(error); }
            foreach (var test in cases)
            {
                currentCase = test;
                int index = results.Count;
                string name = test.GetProperty("name").GetString()!;
                uint item = test.GetProperty("item").GetUInt32();
                string category = test.GetProperty("category").GetString()!;
                var mapping = data.GetProperty("items").GetProperty(item.ToString());
                string kind = mapping.GetProperty("kind").GetString()!;
                deadline = new[] { limit, timer.Elapsed + itemLimit }.Min();
                var receiptTimer = Stopwatch.StartNew();
                var before = new Dictionary<string, double>();
                var after = new Dictionary<string, double>();
                string? actor = null, removeActor = null;
                uint actorType = 0, expectedActorValue = 1;
                (uint Sum, uint Count) beforePouch = default;
                var expectedFlags = new Dictionary<string, (string Type, double Value)>();
                bool capped = false;
                stage = $"preparing receipt {index + 1}/{planned}: {name}"; Progress();
                if (kind == "native")
                {
                    var profile = NativeGrants.Profiles[name];
                    int selected = profile.Tiers.Length;
                    for (int i = 0; i < profile.Tiers.Length; i++)
                    {
                        var marker = profile.Tiers[i].Writes[^1];
                        double value = ReadFlag(marker.Name, marker.Type);
                        before[marker.Name] = value;
                        if (value < marker.Value) { selected = i; break; }
                    }
                    capped = selected == profile.Tiers.Length;
                    var tier = profile.Tiers[Math.Min(selected, profile.Tiers.Length - 1)];
                    foreach (var flag in tier.Writes)
                        expectedFlags[flag.Name] = (flag.Type, flag.Value);
                    actor = tier.Actor; removeActor = tier.RemoveActor;
                }
                else if (kind == "progression")
                {
                    var (flag, type, delta, cap) = name switch
                    {
                        "Heart Container" => ("MaxHartValue", "s32", 4d, 120d),
                        "Stamina Vessel" => ("StaminaMax", "f32", 200d, 3000d),
                        "Weapon Slot" => ("WeaponPorchStockNum", "s32", 1d, 20d),
                        "Bow Slot" => ("BowPorchStockNum", "s32", 1d, 14d),
                        "Shield Slot" => ("ShieldPorchStockNum", "s32", 1d, 20d),
                        _ => throw new InvalidDataException("Unknown progression item " + name)
                    };
                    double value = ReadFlag(flag, type); before[flag] = value;
                    expectedFlags[flag] = (type, Math.Min(value + delta, cap)); capped = value >= cap;
                }
                else if (kind == "rupees")
                {
                    double value = ReadFlag("CurrentRupee", "s32"); before["CurrentRupee"] = value;
                    expectedFlags["CurrentRupee"] = ("s32", Math.Min(value + mapping.GetProperty("quantity").GetUInt32(), 999999));
                }
                else if (kind == "actor") actor = mapping.GetProperty("actor").GetString();
                else throw new InvalidDataException("Unsupported live test delivery " + kind);
                if (actor is not null)
                {
                    beforePouch = Pouch(actor);
                    actorType = Call(GameOffsets.GetPouchItemType, mailbox.WriteSafeString(actor)).R3;
                    Require(actorType <= 9, "Invalid native pouch type for " + actor);
                    expectedActorValue = actorType is 0 or 1 or 3
                        ? Call(GameOffsets.GetWeaponMaxValue, mailbox.WriteSafeString(actor)).R3
                        : kind == "actor" && mapping.TryGetProperty("quantity", out var amount) ? amount.GetUInt32() : 1;
                    before[actor + ":sum"] = beforePouch.Sum; before[actor + ":count"] = beforePouch.Count;
                }
                if (removeActor is not null) before[removeActor + ":count"] = Pouch(removeActor).Count;
                server.PublishItem(item).GetAwaiter().GetResult();
                Wait(() => { bridge.Pump(session); blockReason = bridge.BlockReason; return bridge.NextItem == index + 1; },
                    $"delivery {index + 1}/{planned}: {name}");
                Wait(Active, "gameplay for receipt verification");
                foreach (var (flag, expected) in expectedFlags)
                {
                    double observed = ReadFlag(flag, expected.Type); after[flag] = observed;
                    Require(Math.Abs(observed - expected.Value) < .01, $"{name}: {flag} expected {expected.Value}, observed {observed}");
                }
                if (actor is not null)
                {
                    var pouch = Pouch(actor); after[actor + ":sum"] = pouch.Sum; after[actor + ":count"] = pouch.Count;
                    if (kind == "native") Require(pouch.Count > 0, name + ": native key item missing from pouch");
                    else if (actorType == 9 && beforePouch.Count > 0) Require(pouch.Count == beforePouch.Count, name + ": duplicate key item");
                    else Require(pouch.Sum == beforePouch.Sum + expectedActorValue, name + ": incorrect pouch value increase");
                }
                if (removeActor is not null)
                {
                    after[removeActor + ":count"] = Pouch(removeActor).Count;
                    Require(after[removeActor + ":count"] == 0, name + ": base champion item remains");
                }
                bool cleanedUp = false;
                if (kind == "actor" && actorType is 4 or 5 or 6 && actor is not null)
                {
                    // Full coverage exceeds the game's armor capacity. Remove each
                    // verified test piece using the native API, keeping the same save
                    // and emulator session rather than restarting between batches.
                    uint text = mailbox.WriteSafeString(actor);
                    mailbox.SetWord(Protocol.Get("scratch_offset") + 68, 0x01000000);
                    Call(GameOffsets.PauseMenuChangeItem, mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr),
                        text, uint.MaxValue, mailbox.ScratchResultAddress + 4);
                    Wait(() => Pouch(actor).Count == 0, "verified armor cleanup: " + name);
                    cleanedUp = true;
                }
                results.Add(new { item, name, category, passed = true, capped, cleaned_up = cleanedUp,
                    elapsed_seconds = receiptTimer.Elapsed.TotalSeconds, before, after });
                stage = $"verified {results.Count}/{planned}: {name}"; Progress();
                WriteResult(new { passed = false, running = true, elapsed_seconds = timer.Elapsed.TotalSeconds, stage, planned, completed = results.Count, items = results });
                Console.WriteLine($"LIVE PASS {results.Count}/{planned}: {name} ({receiptTimer.Elapsed.TotalSeconds:F2}s)");
            }
            WriteResult(new { passed = true, elapsed_seconds = timer.Elapsed.TotalSeconds, location, fingerprint = mailbox.Fingerprint,
                planned, completed = results.Count, items = results });
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            WriteResult(new { passed = false, elapsed_seconds = timer.Elapsed.TotalSeconds, stage, planned,
                completed = results.Count, failed_case = currentCase, block_reason = blockReason, items = results, error = error.ToString() });
            return 1;
        }
        void Progress()
        {
            if (progressPath is not null) AtomicWrite(progressPath, new { stage, chest_checked = chestChecked, planned, completed = results.Count });
        }
        void WriteResult(object result) { if (resultPath is not null) AtomicWrite(resultPath, result); }
    }

    private static void AtomicWrite(string path, object result)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path + ".tmp", JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        File.Move(path + ".tmp", path, overwrite: true);
    }
}
