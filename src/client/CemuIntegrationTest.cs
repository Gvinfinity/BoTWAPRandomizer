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
        bool chestChecked = false, inputAllowed = true;
        int planned = 0;
        uint? physicalOrbs = null;
        double? completionFlag = null;
        double[]? playerPosition = null;
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
            if (Directory.Exists(stateDirectory) && !(config.TryGetProperty("resume_journal", out var resume) && resume.GetBoolean())) throw new IOException("Test requires a new journal directory");
            uint location = config.GetProperty("location").GetUInt32();
            var data = config.GetProperty("slot_data");
            bool physical = config.TryGetProperty("physical_check", out var physicalCheck);
            bool runeTerminalTest = config.TryGetProperty("rune_terminal_test", out var runeTerminal);
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
            if (physical)
            {
                inputAllowed = false; Progress();
                Wait(() => {
                    uint player = mailbox.ReadGuestWord(GameOffsets.PlayerInfoPtr);
                    return player != 0 && mailbox.ReadGuestWord(player + GameOffsets.PlayerInfoActorOffset) != 0;
                }, "live player for physical completion fixture");
            }
            using var server = new ProtocolServerFixture(data, location, cases[0].GetProperty("item").GetUInt32(), limit, manualItems: true);
            using var session = new APSessionManager(server.Uri, "Test", null, mailbox, Console.WriteLine);
            using var bridge = new ClientBridge(mailbox, session.Contract, stateDirectory, session.Team, session.Slot, Console.WriteLine);
            if (!physical)
            {
                Wait(() => { bridge.Pump(session); return server.Checks.Task.IsCompleted; }, "chest acquisition and AP LocationChecks");
                if (!server.Checks.Task.GetAwaiter().GetResult().Contains(location)) throw new InvalidDataException("Wrong location check");
                chestChecked = true; Progress();
            }
            else
            {
                if (config.TryGetProperty("resume_journal", out var continuation) && continuation.GetBoolean())
                {
                    // A reloaded save can re-emit earlier physical completions.
                    // Only previously journaled checks may precede this visit.
                    var prior = bridge.TrackerChecks.ToHashSet();
                    while (mailbox.PeekCheck() is { } previous)
                    {
                        Require(prior.Contains((long)previous.ApLocationId),
                            "Unjournaled physical check fired before interaction");
                        mailbox.AcknowledgeCheck(previous.SeqId);
                    }
                }
                else if (mailbox.OutHead != 0 || server.HasCheck(location))
                    throw new InvalidDataException("Physical check fired before the fixture enabled interaction");
            }
            uint checkHeadBeforeGrant = mailbox.OutHead;

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
                uint text = mailbox.WriteSafeGameDataName(name);
                mailbox.SetWord(Protocol.Get("scratch_offset") + 64, 0);
                var read = Call(type == "bool" ? GameOffsets.GdtGetBoolByName : GameOffsets.GdtGetS32ByName,
                    core, mailbox.ScratchResultAddress, text, mailbox.ReadGuestWord(manager + 0x704) >> 24, 1);
                if (read.R3 == 0) throw new InvalidDataException("Native observation cannot read " + name);
                uint raw = mailbox.ReadGuestWord(mailbox.ScratchResultAddress);
                return type == "bool" ? (raw == 0 ? 0 : 1) : unchecked((int)raw);
            }
            (uint Sum, uint Count) Pouch(string actor) => mailbox.MeasureStablePouch(mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr), actor);
            void Require(bool condition, string error) { if (!condition) throw new InvalidDataException(error); }
            bool deliveryAfterCheck = config.TryGetProperty("delivery_after_check", out var afterCheck) && afterCheck.GetBoolean();
            void CollectPhysical()
            {
                deadline = limit;
                for (int frame = 0; frame < 3; frame++)
                {
                    uint previous = mailbox.Word(28);
                    Wait(() => { bridge.Pump(session); return mailbox.Word(28) != previous; }, "checking grant/check isolation");
                }
                Require(mailbox.OutHead == checkHeadBeforeGrant,
                    "Incoming item grant incorrectly emitted the physical location check");
                uint orbsBefore = Pouch("Obj_DungeonClearSeal").Sum;
                if (config.TryGetProperty("expected_position", out var expectedPosition))
                {
                    var arrivalDeadline = timer.Elapsed + TimeSpan.FromSeconds(20);
                    Wait(() => {
                        uint info = mailbox.ReadGuestWord(GameOffsets.PlayerInfoPtr);
                        uint player = info == 0 ? 0 : mailbox.ReadGuestWord(info + GameOffsets.PlayerInfoActorOffset);
                        if (player == 0) return false;
                        playerPosition = Enumerable.Range(0, 3).Select(i => (double)BitConverter.UInt32BitsToSingle(
                            mailbox.ReadGuestWord(player + 0x2D4u + (uint)i * 4))).ToArray();
                        double distance = Math.Sqrt(playerPosition.Zip(expectedPosition.EnumerateArray(),
                            (actual, expected) => Math.Pow(actual - expected.GetDouble(), 2)).Sum());
                        Require(timer.Elapsed < arrivalDeadline || (double.IsFinite(distance) && distance < 6),
                            "Player did not reach the fixture location: distance " + distance + "; actual " + string.Join(",", playerPosition));
                        return double.IsFinite(distance) && distance < 6;
                    }, "player arrival at the physical fixture");
                }
                Action? assistTick = null;
                double nextAssist = 0;
                if (config.TryGetProperty("assisted_combat", out var assistance) && assistance.GetBoolean()
                    && physicalCheck.GetProperty("kind").GetString() is "miniboss" or "boss")
                {
                    uint exports = mailbox.GuestAddress + (uint)Protocol.Get("mailbox_size");
                    Require(mailbox.ReadGuestWord(exports) == 0x41505445, "Test native exports are unavailable");
                    uint finder = mailbox.ReadGuestWord(exports + 4), zeroLife = mailbox.ReadGuestWord(exports + 8);
                    uint enemy = 0;
                    string targetName = physicalCheck.GetProperty("actor").GetString()!;
                    // Some Beast arenas need an A interaction to start their
                    // encounter before the boss actor exists. Do not suppress
                    // runner input while waiting for that actor to spawn.
                    inputAllowed = true;
                    Progress();
                    void SpawnPrerequisite(string flag)
                    {
                        Require(flag is "LastBossIncompleteGanonGenerateFlag" or "FinalTrial_InBossBattleArea"
                            or "Appear_PGanonWind" or "Appear_PGanonFire" or "Appear_PGanonWater" or "Appear_PGanonElectric",
                            "Not a permitted transient spawn prerequisite");
                        uint manager = mailbox.ReadGuestWord(GameOffsets.GdtManagerPtr);
                        uint core = mailbox.GameDataCore(manager, 0x70C);
                        Require(core != 0, "Writable GameData core unavailable for fixture spawn");
                        Call(GameOffsets.GdtSetBoolTyped, core, 1, mailbox.WriteSafeString(flag), 0, 1);
                        if (((mailbox.ReadGuestWord(manager + 0x714) >> 16) & 0xFF) != 0)
                            Call(GameOffsets.GdtSetBoolTyped, mailbox.GameDataCore(manager, 0x710), 1,
                                mailbox.WriteSafeString(flag), 0, 1);
                        Require(ReadFlag(flag, "bool") == 1, "Cannot enable fixture spawn prerequisite " + flag);
                        Console.WriteLine("TEST ASSIST: enabled transient spawn prerequisite " + flag);
                    }
                    if (targetName.StartsWith("Enemy_SiteBoss_", StringComparison.Ordinal))
                        SpawnPrerequisite("Appear_PGanon" + physicalCheck.GetProperty("scene").GetString()!.Replace("Remains", ""));
                    if (targetName == "Enemy_Ganon") SpawnPrerequisite("LastBossIncompleteGanonGenerateFlag");
                    if (targetName == "Priest_Boss_Normal") SpawnPrerequisite("FinalTrial_InBossBattleArea");
                    int positionOffset = Protocol.Get("scratch_offset") + 80;
                    for (int axis = 0; axis < 3; axis++)
                        mailbox.SetWord(positionOffset + axis * 4, BitConverter.SingleToUInt32Bits((float)playerPosition![axis]));
                    Wait(() => { enemy = Call(finder, mailbox.WriteSafeString(targetName), mailbox.GuestAddress + (uint)positionOffset).R3; return enemy != 0; },
                        "native encounter actor: " + targetName);
                    uint id = mailbox.ReadGuestWord(enemy + 0x50);
                    var enemyPosition = Enumerable.Range(0, 3).Select(i => (double)BitConverter.UInt32BitsToSingle(
                        mailbox.ReadGuestWord(enemy + 0x2D4u + (uint)i * 4))).ToArray();
                    double separation = Math.Sqrt(enemyPosition.Zip(playerPosition!, (a,b) => Math.Pow(a-b,2)).Sum());
                    Require(double.IsFinite(separation) && separation < 50, "Encounter actor is outside the visited location");
                    Require(Call(zeroLife, enemy, id).R3 == 1, "Encounter actor expired before the native defeat aid");
                    Console.WriteLine("TEST ASSIST: native zero-life request for " + targetName + "; waiting for its actual death flag");
                    string[] phaseActors = targetName switch {
                        "Enemy_Giant_Bone" => [targetName, "Enemy_Giant_Bone_Eye"],
                        "Priest_Boss_Normal" => [targetName, "Priest_Boss_Giant"],
                        "Enemy_GanonBeast" => [targetName, "Enemy_GanonBeast_WeakPoint"],
                        _ => [targetName]
                    };
                    assistTick = () => {
                        foreach (string phaseActor in phaseActors)
                        {
                            uint activeEnemy = Call(finder, mailbox.WriteSafeString(phaseActor), mailbox.GuestAddress + (uint)positionOffset).R3;
                            if (activeEnemy == 0) continue;
                            uint actorId = mailbox.ReadGuestWord(activeEnemy + 0x50);
                            uint vtable = mailbox.ReadGuestWord(activeEnemy + 0xE8);
                            uint getter = vtable == 0 ? 0 : mailbox.ReadGuestWord(vtable + 0x2BC);
                            if (getter == 0) continue;
                            uint life = Call(getter, activeEnemy).R3;
                            if (life == 0 || unchecked((int)mailbox.ReadGuestWord(life)) <= 0) continue;
                            if (Call(zeroLife, activeEnemy, actorId).R3 == 1)
                                Console.WriteLine("TEST ASSIST: native zero-life request for active phase " + phaseActor);
                        }
                    };
                }
                inputAllowed = true;
                double nextPositionSample = 0;
                Wait(() => {
                    bridge.Pump(session);
                    if (server.HasCheck(location) && mailbox.OutHead != checkHeadBeforeGrant) return true;
                    if (assistTick is not null && timer.Elapsed.TotalSeconds >= nextAssist)
                    {
                        assistTick(); nextAssist = timer.Elapsed.TotalSeconds + 2;
                    }
                    if (timer.Elapsed.TotalSeconds >= nextPositionSample)
                    {
                        uint info = mailbox.ReadGuestWord(GameOffsets.PlayerInfoPtr);
                        uint player = info == 0 ? 0 : mailbox.ReadGuestWord(info + GameOffsets.PlayerInfoActorOffset);
                        if (player != 0)
                            playerPosition = Enumerable.Range(0, 3).Select(i => (double)BitConverter.UInt32BitsToSingle(
                                mailbox.ReadGuestWord(player + 0x2D4u + (uint)i * 4))).ToArray();
                        physicalOrbs = Pouch("Obj_DungeonClearSeal").Sum;
                        if (physicalCheck.TryGetProperty("watch_flag", out var watched))
                            completionFlag = ReadFlag(watched.GetString()!, physicalCheck.GetProperty("watch_type").GetString()!);
                        nextPositionSample = timer.Elapsed.TotalSeconds + .5; Progress();
                    }
                    return server.HasCheck(location) && mailbox.OutHead != checkHeadBeforeGrant;
                },
                    "physical completion: " + physicalCheck.GetProperty("name").GetString());
                inputAllowed = false; chestChecked = true;
                if (physicalCheck.TryGetProperty("watch_flag", out var completedFlag))
                {
                    completionFlag = ReadFlag(completedFlag.GetString()!, physicalCheck.GetProperty("watch_type").GetString()!);
                    Require(completionFlag >= physicalCheck.GetProperty("watch_threshold").GetDouble(),
                        "Physical encounter completion flag did not reach its threshold");
                }
                Progress();
                Require(physicalCheck.GetProperty("kind").GetString() != "shrine" || Pouch("Obj_DungeonClearSeal").Sum == orbsBefore, "Tracked shrine granted a vanilla Spirit Orb");
            }
            if (runeTerminalTest)
            {
                string flag = runeTerminal.GetProperty("flag").GetString()!;
                string activationFlag = runeTerminal.GetProperty("activation_flag").GetString()!;
                Require(ReadFlag(flag, "bool") == 0, "Rune fixture started with the AP rune already owned");
                Require(ReadFlag(activationFlag, "bool") == 0, "Rune terminal fixture started activated");
                if (config.TryGetProperty("expected_position", out var runePosition))
                {
                    var arrivalDeadline = timer.Elapsed + TimeSpan.FromSeconds(20);
                    Wait(() => {
                        uint info = mailbox.ReadGuestWord(GameOffsets.PlayerInfoPtr);
                        uint player = info == 0 ? 0 : mailbox.ReadGuestWord(info + GameOffsets.PlayerInfoActorOffset);
                        if (player == 0) return false;
                        playerPosition = Enumerable.Range(0, 3).Select(i => (double)BitConverter.UInt32BitsToSingle(
                            mailbox.ReadGuestWord(player + 0x2D4u + (uint)i * 4))).ToArray();
                        double distance = Math.Sqrt(playerPosition.Zip(runePosition.EnumerateArray(),
                            (actual, expected) => Math.Pow(actual - expected.GetDouble(), 2)).Sum());
                        Require(timer.Elapsed < arrivalDeadline || (double.IsFinite(distance) && distance < 6),
                            "Player did not reach the rune terminal: " + string.Join(",", playerPosition));
                        return double.IsFinite(distance) && distance < 6;
                    }, "player arrival at the rune terminal");
                }
                inputAllowed = true; Progress();
                var terminalDeadline = timer.Elapsed + TimeSpan.FromSeconds(10);
                while (timer.Elapsed < terminalDeadline)
                {
                    bridge.Pump(session);
                    Require(ReadFlag(flag, "bool") == 0, "Vanilla rune terminal granted " + flag);
                    Require(!server.HasCheck(location), "Rune terminal emitted an unexpected location check");
                    if (config.TryGetProperty("expected_position", out var terminalPosition))
                    {
                        uint info = mailbox.ReadGuestWord(GameOffsets.PlayerInfoPtr);
                        uint player = info == 0 ? 0 : mailbox.ReadGuestWord(info + GameOffsets.PlayerInfoActorOffset);
                        if (player != 0)
                        {
                            playerPosition = Enumerable.Range(0, 3).Select(i => (double)BitConverter.UInt32BitsToSingle(
                                mailbox.ReadGuestWord(player + 0x2D4u + (uint)i * 4))).ToArray();
                            double distance = Math.Sqrt(playerPosition.Zip(terminalPosition.EnumerateArray(),
                                (actual, expected) => Math.Pow(actual - expected.GetDouble(), 2)).Sum());
                            Require(double.IsFinite(distance) && distance < 1.5,
                                "Link moved away from the rune terminal: " + string.Join(",", playerPosition));
                        }
                    }
                    Thread.Sleep(400);
                    Progress();
                }
                string interactionPath = config.GetProperty("rune_interaction_path").GetString()!;
                Require(File.Exists(interactionPath), "The live fixture did not send its single terminal interaction");
                Require(ReadFlag(activationFlag, "bool") == 0, "Rune terminal unexpectedly completed its vanilla acquisition flow");
                inputAllowed = false; Progress();
            }
            if (physical && deliveryAfterCheck && !runeTerminalTest) CollectPhysical();
            foreach (var test in config.TryGetProperty("checks_only", out var checksOnly) && checksOnly.GetBoolean() ? Array.Empty<JsonElement>() : cases)
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
            if (physical && !deliveryAfterCheck) CollectPhysical();
            if (config.TryGetProperty("watch_combat", out var watchCombat) && watchCombat.GetBoolean())
            {
                Require(mailbox.OutHead == 1, "An incoming grant incorrectly generated an encounter death check");
                foreach (string id in data.GetProperty("locations").EnumerateObject().Select(e => e.Name))
                    if (uint.Parse(id) != location) Require(!server.HasCheck(long.Parse(id)), "Unexpected encounter check " + id);
            }
            string? goalTest = config.TryGetProperty("goal_test", out var gt) ? gt.GetString() : null;
            if (goalTest is not null)
            {
                Require(server.HasCheck(location), "Goal fixture check never reached AP");
                if (goalTest == "complete")
                {
                    Wait(() => { bridge.Pump(session); return server.GoalStatus.Task.IsCompleted; }, "AP goal status");
                    Require(server.GoalStatus.Task.GetAwaiter().GetResult() == 30, "Expected CLIENT_GOAL");
                }
                else if (goalTest == "locked")
                {
                    var observation = Stopwatch.StartNew();
                    while (observation.Elapsed < TimeSpan.FromSeconds(10))
                    {
                        CheckDeadline();
                        bridge.Pump(session);
                        Require(!server.GoalStatus.Task.IsCompleted, "Missing prerequisite allowed Victory");
                        Require(data.GetProperty("goal_required_location_ids").EnumerateArray().Any(required => !server.HasCheck(required.GetInt64())), "Lock fixture has no missing prerequisite");
                        Thread.Sleep(10);
                    }
                }
                else throw new InvalidDataException("Unknown goal test");
            }
            WriteResult(new { passed = true, goal_test = goalTest, elapsed_seconds = timer.Elapsed.TotalSeconds, location, fingerprint = mailbox.Fingerprint,
                physical_check_passed = physical && !runeTerminalTest, rune_terminal_passed = runeTerminalTest,
                completion_flag = completionFlag, assisted_fast_events = config.TryGetProperty("fast_fixtures", out var fast) && fast.GetBoolean(), assisted_native_defeat = config.TryGetProperty("assisted_combat", out var aid) && aid.GetBoolean(), player_position = playerPosition, delivery_after_check = deliveryAfterCheck, planned, completed = results.Count, items = results });
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
            if (progressPath is not null) AtomicWrite(progressPath, new { stage, chest_checked = chestChecked, input_allowed = inputAllowed, spirit_orbs = physicalOrbs, completion_flag = completionFlag, player_position = playerPosition, planned, completed = results.Count });
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
