using System.Buffers.Binary;
using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Archipelago.MultiClient.Net.Enums;
using BotWClient.Archipelago;
using BotWClient.Memory;

namespace BotWClient;

internal static class TestHarness
{
    public static int ValidatePack(string path)
    {
        try
        {
            using var archive = ZipFile.OpenRead(path);
            var manifest = archive.Entries.Single(entry => entry.FullName.EndsWith("/botw_patch.json", StringComparison.Ordinal));
            using var data = JsonDocument.Parse(manifest.Open());
            var plan = data.RootElement;
            var hook = archive.Entries.Single(entry => entry.FullName.EndsWith("/patch_Archipelago.asm", StringComparison.Ordinal));
            using var text = new StreamReader(hook.Open());
            string block = text.ReadToEnd().Split("_AP_Mailbox_Base:\n")[1].Split("_AP_Is_Injecting:")[0];
            uint[] words = Regex.Matches(block, @"0x[0-9A-F]{8}").Select(match => Convert.ToUInt32(match.Value[2..], 16)).ToArray();
            Require(words.Length * 4 == Protocol.Get("mailbox_size"), "Generated ASM mailbox allocation disagrees with the C# schema");
            using var ram = new GuestSimulator();
            for (int i = 0; i < words.Length; i++) Protocol.Write(ram.MailboxBytes.AsSpan(i * 4), words[i]);
            using var mailbox = new Mailbox(ram);
            long[] ids = plan.GetProperty("locations").EnumerateArray().Select(entry => entry.GetProperty("id").GetInt64()).ToArray();
            var contract = new SlotContract(plan.GetProperty("slot_data"), mailbox, plan.GetProperty("player").GetInt32(), plan.GetProperty("seed").GetString()!, ids);
            int native = 0, unsupported = 0;
            foreach (var item in plan.GetProperty("slot_data").GetProperty("items").EnumerateObject())
            {
                if (contract.ResolveGrant(long.Parse(item.Name), out _) is not null) native++;
                else unsupported++;
            }
            Console.WriteLine($"PASS: generated pack accepted by C#; {ids.Length} checks, {native} native delivery mappings, {unsupported} explicitly unsupported grants, fingerprint {contract.Fingerprint}");
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }

    private sealed class GuestSimulator : IMemory
    {
        public const uint MailboxBase = 0x0E000000;
        public const uint PauseMgrAddr = 0x30000000;
        public const uint GdtMgrAddr = 0x31000000;
        public const uint PlayerInfoAddr = 0x32000000;
        public const uint PlayerActorAddr = 0x33000000;
        private const uint PouchArenaBase = 0x34000000;
        private const uint NodeOffset = 0x30;

        public readonly byte[] MailboxBytes = new byte[Protocol.Get("mailbox_size")];
        private readonly Dictionary<uint, byte[]> pages = [];
        private readonly List<(string Name, int Value)> pouch = [];

        public bool Locked { get; private set; }
        public bool PouchFull { get; set; }
        public bool HoldChampionRemoval;
        public List<string> RemovedChampionItems = [];
        public uint? PerCallStackCap { get; set; }
        public List<uint> Calls { get; } = [];
        public Dictionary<uint, int> SavedS32 { get; } = new()
        {
            [101] = 12,
            [103] = 8,
            [104] = 5,
            [105] = 4,
        };
        public Dictionary<uint, int> PendingS32 { get; } = [];
        public float SavedStamina { get; set; } = 1000f;
        public float? PendingStamina { get; set; }
        public int ActorStaminaRefreshes { get; set; }

        public GuestSimulator()
        {
            WriteGuestWord(GameOffsets.PauseMenuDataMgrPtr, PauseMgrAddr);
            WriteGuestWord(GameOffsets.GdtManagerPtr, GdtMgrAddr);
            WriteGuestWord(GdtMgrAddr + 0x700, 0x22003000);
            WriteGuestWord(0x22003000, 0x22000000);
            WriteGuestWord(GdtMgrAddr + 0x70C, 0x22003004);
            WriteGuestWord(0x22003004, 0x22001000);
            WriteGuestWord(GameOffsets.MapManagerPtr, 0x22002000);
            WriteGuestWord(GdtMgrAddr + 0x704, 0x01000000);
            WriteGuestWord(GameOffsets.PlayerInfoPtr, PlayerInfoAddr);
            WriteGuestWord(PlayerInfoAddr + GameOffsets.PlayerInfoActorOffset, PlayerActorAddr);
            WriteGuestWord(GameOffsets.MaxHeartValueHandle, 101);
            WriteGuestWord(GameOffsets.WeaponPorchStockHandle, 103);
            WriteGuestWord(GameOffsets.BowPorchStockHandle, 104);
            WriteGuestWord(GameOffsets.ShieldPorchStockHandle, 105);
            RebuildPouchMemory();
        }

        public byte[] Read(int offset, int length) => MailboxBytes.AsSpan(offset, length).ToArray();
        public void Write(int offset, byte[] bytes) => bytes.CopyTo(MailboxBytes, offset);

        public byte[] ReadGuest(uint guestAddress, uint mailboxGuestAddress, int length)
        {
            Require(mailboxGuestAddress == MailboxBase, "Unexpected mailbox guest base");
            if (guestAddress >= MailboxBase && (ulong)guestAddress + (uint)length <= MailboxBase + (uint)MailboxBytes.Length)
                return MailboxBytes.AsSpan((int)(guestAddress - MailboxBase), length).ToArray();
            var result = new byte[length];
            for (int i = 0; i < length; i++)
            {
                uint addr = unchecked(guestAddress + (uint)i);
                uint page = addr & ~0xFFFu;
                result[i] = pages.TryGetValue(page, out var data) ? data[addr & 0xFFFu] : (byte)0;
            }
            return result;
        }

        public void WriteGuestBytes(uint guestAddress, ReadOnlySpan<byte> bytes)
        {
            if (guestAddress >= MailboxBase && (ulong)guestAddress + (uint)bytes.Length <= MailboxBase + (uint)MailboxBytes.Length)
            {
                bytes.CopyTo(MailboxBytes.AsSpan((int)(guestAddress - MailboxBase), bytes.Length));
                return;
            }
            for (int i = 0; i < bytes.Length; i++)
            {
                uint addr = unchecked(guestAddress + (uint)i);
                uint page = addr & ~0xFFFu;
                if (!pages.TryGetValue(page, out var data))
                {
                    data = new byte[4096];
                    pages[page] = data;
                }
                data[addr & 0xFFFu] = bytes[i];
            }
        }

        public void WriteGuestWord(uint guestAddress, uint value)
        {
            Span<byte> buf = stackalloc byte[4];
            BinaryPrimitives.WriteUInt32BigEndian(buf, value);
            WriteGuestBytes(guestAddress, buf);
        }

        public uint ReadGuestWordDirect(uint guestAddress) => Protocol.Read(ReadGuest(guestAddress, MailboxBase, 4));

        public string ReadSafeString(uint safeStringAddr)
        {
            uint textPtr = ReadGuestWordDirect(safeStringAddr);
            uint vtable = ReadGuestWordDirect(safeStringAddr + 4);
            Require(vtable == GameOffsets.SafeStringVtable, "Invalid SafeString vtable");
            var bytes = new List<byte>();
            for (uint i = 0; i < 64; i++)
            {
                byte b = ReadGuest(textPtr + i, MailboxBase, 1)[0];
                if (b == 0) break;
                bytes.Add(b);
            }
            return Encoding.ASCII.GetString(bytes.ToArray());
        }

        public void ClearPouch()
        {
            pouch.Clear();
            RebuildPouchMemory();
        }

        public void SetPouchItem(string name, int value)
        {
            pouch.Add((name, value));
            RebuildPouchMemory();
        }

        public int TotalPouchValue(string name) => pouch.Where(p => p.Name == name && p.Value > 0).Sum(p => p.Value);

        private void RebuildPouchMemory()
        {
            uint listHead = PauseMgrAddr + GameOffsets.PauseMenuItemListOffset;
            WriteGuestWord(PauseMgrAddr + GameOffsets.PauseMenuItemListNodeOffset, NodeOffset);
            if (pouch.Count == 0)
            {
                WriteGuestWord(PauseMgrAddr + GameOffsets.PauseMenuItemListHeadOffset, listHead);
                return;
            }
            WriteGuestWord(PauseMgrAddr + GameOffsets.PauseMenuItemListHeadOffset, PouchArenaBase + NodeOffset);
            for (int i = 0; i < pouch.Count; i++)
            {
                uint entryAddr = PouchArenaBase + (uint)i * 0x100u;
                uint nameAddr = entryAddr + 0x80u;
                byte[] encoded = Encoding.ASCII.GetBytes(pouch[i].Name + '\0');
                WriteGuestBytes(nameAddr, encoded);
                uint type = pouch[i].Name.StartsWith("Armor_", StringComparison.Ordinal)
                    ? pouch[i].Name.EndsWith("_Head", StringComparison.Ordinal) ? 4u
                        : pouch[i].Name.EndsWith("_Upper", StringComparison.Ordinal) ? 5u : 6u : 0u;
                WriteGuestWord(entryAddr + GameOffsets.PouchItemTypeOffset, type);
                WriteGuestBytes(entryAddr + GameOffsets.PouchItemActiveOffset, [1]);
                WriteGuestWord(entryAddr + GameOffsets.PouchItemValueOffset, unchecked((uint)pouch[i].Value));
                WriteGuestWord(entryAddr + GameOffsets.PouchItemNameOffset, nameAddr);
                uint nextNode = i + 1 < pouch.Count ? PouchArenaBase + (uint)(i + 1) * 0x100u + NodeOffset : listHead;
                WriteGuestWord(entryAddr + NodeOffset + 4, nextNode);
            }
        }

        public Dictionary<string, uint> NativeValues = [];
        public Dictionary<string, uint> PendingNativeValues = [];
        public bool CommitNativeImmediately = true;
        public uint Wallet = 123;
        public uint? PendingWallet;

        public void CommitProgression()
        {
            foreach (var pair in PendingS32) SavedS32[pair.Key] = pair.Value;
            PendingS32.Clear();
            foreach (var pair in PendingNativeValues) NativeValues[pair.Key] = pair.Value;
            PendingNativeValues.Clear();
            if (PendingWallet is { } wallet) { Wallet = wallet; PendingWallet = null; }
            if (PendingStamina is { } stamina) { SavedStamina = stamina; PendingStamina = null; }
        }

        public void Tick()
        {
            Protocol.Write(MailboxBytes.AsSpan(Protocol.Get("mailbox_address_offset")), MailboxBase);
            Protocol.Write(MailboxBytes.AsSpan(8), 2);
            uint heartbeat = Protocol.Read(MailboxBytes.AsSpan(28));
            Protocol.Write(MailboxBytes.AsSpan(28), unchecked(heartbeat + 1));

            uint head = Protocol.Read(MailboxBytes.AsSpan(12));
            uint tail = Protocol.Read(MailboxBytes.AsSpan(16));
            if (unchecked(head - tail) > (uint)Protocol.Get("ring_capacity")) return;

            int capacity = Protocol.Get("ring_capacity"), stride = Protocol.Get("incoming_size"), baseOffset = Protocol.Get("incoming_offset");
            while (tail != head)
            {
                int slotOffset = baseOffset + (int)(tail % (uint)capacity) * stride;
                var span = MailboxBytes.AsSpan(slotOffset, stride);
                uint seq = Protocol.Read(span);
                uint target = Protocol.Read(span.Slice(4));
                uint r3 = Protocol.Read(span.Slice(8)), r4 = Protocol.Read(span.Slice(12)),
                     r5 = Protocol.Read(span.Slice(16)), r6 = Protocol.Read(span.Slice(20)),
                     r7 = Protocol.Read(span.Slice(24));
                float f1 = Protocol.ReadFloat(span.Slice(40));

                uint retR3 = 0;
                float retF1 = 0f;
                if (target != 0)
                {
                    Calls.Add(target);
                    switch (target)
                    {
                        case GameOffsets.LockCritSection:
                            Require(!Locked && r3 == PauseMgrAddr + GameOffsets.PauseMenuCritSectionOffset, "Invalid lock call");
                            Locked = true;
                            break;
                        case GameOffsets.UnlockCritSection:
                            Require(Locked && r3 == PauseMgrAddr + GameOffsets.PauseMenuCritSectionOffset, "Invalid unlock call");
                            Locked = false;
                            break;
                        case GameOffsets.GetPouchItemType:
                            Require(r4 == 0, "Invalid getPouchItemType debug flag");
                            string classifyName = ReadSafeString(r3);
                            retR3 = classifyName switch
                            {
                                _ when classifyName.StartsWith("Weapon_Sword_", StringComparison.Ordinal) => 0u,
                                _ when classifyName.StartsWith("Weapon_Bow_", StringComparison.Ordinal) => 1u,
                                "NormalArrow" => 2u,
                                _ when classifyName.StartsWith("Weapon_Shield_", StringComparison.Ordinal) => 3u,
                                _ when classifyName.StartsWith("Armor_", StringComparison.Ordinal) =>
                                    classifyName.EndsWith("_Head", StringComparison.Ordinal) ? 4u :
                                    classifyName.EndsWith("_Upper", StringComparison.Ordinal) ? 5u : 6u,
                                _ when classifyName.StartsWith("Item_Ore_", StringComparison.Ordinal) => 7u,
                                _ when classifyName.StartsWith("Item_Cook_", StringComparison.Ordinal) => 8u,
                                "PlayerStole2" => 9u,
                                _ when classifyName.StartsWith("Obj_", StringComparison.Ordinal) => 9u,
                                _ => 0xFFFFFFFFu,
                            };
                            break;
                        case GameOffsets.GetWeaponMaxValue:
                            _ = ReadSafeString(r3);
                            retR3 = 40u;
                            break;
                        case GameOffsets.PauseMenuChangeItem:
                            Require(!Locked && r3 == PauseMgrAddr && r5 == uint.MaxValue && r7 == 0,
                                "Invalid native pouch removal ABI");
                            Require(ReadGuest(r6, MailboxBase, 1)[0] == 1,
                                "Removal must pass a pointer to allowEquipped=true");
                            string removeName = ReadSafeString(r4);
                            Require(removeName.StartsWith("Obj_HeroSoul_", StringComparison.Ordinal),
                                "Removal targeted an upgraded or unrelated item");
                            if (!HoldChampionRemoval)
                            {
                                int removeIndex = pouch.FindIndex(p => p.Name == removeName && p.Value > 0);
                                if (removeIndex >= 0) pouch.RemoveAt(removeIndex);
                                RemovedChampionItems.Add(removeName);
                                RebuildPouchMemory();
                            }
                            // Deliberately return garbage: the real native method is void.
                            retR3 = 0xDEADBEEF;
                            break;
                        case GameOffsets.PauseMenuAddItem:
                            Require(Locked && r3 == PauseMgrAddr && r6 == PauseMgrAddr + GameOffsets.PauseMenuItemListOffset, "Invalid addItem call");
                            string addName = ReadSafeString(r4);
                            if (!PouchFull)
                            {
                                uint amount = r5 is 2 or 7 or 8 && PerCallStackCap is { } cap ? Math.Min(r7, cap) : r7;
                                int existing = pouch.FindIndex(p => p.Name == addName);
                                if (r5 is 2 or 7 && existing >= 0)
                                    pouch[existing] = (addName, pouch[existing].Value + (int)amount);
                                else
                                    pouch.Add((addName, r5 is 4 or 5 or 6 ? -1 : (int)amount));
                                RebuildPouchMemory();
                            }
                            retR3 = 0xDEADBEEFu;
                            break;
                        case GameOffsets.PauseMenuPostAddFood:
                            Require(Locked && r3 == PauseMgrAddr, "Invalid postAddFood call");
                            _ = ReadSafeString(r4);
                            break;
                        case GameOffsets.PauseMenuSaveToGameData:
                            Require(Locked && r3 == PauseMgrAddr && r4 == PauseMgrAddr + GameOffsets.PauseMenuItemListOffset, "Invalid saveToGameData call");
                            break;
                        case GameOffsets.MapLoadTowerCentres:
                        case GameOffsets.MapLoadTowerScaleLevels:
                        case GameOffsets.MapInitTowerRecords:
                            Require(r3 == 0x22002000, "Invalid map manager pointer");
                            break;
                        case GameOffsets.GdtSetBoolTyped:
                        case GameOffsets.GdtSetS32Typed:
                            Require(r3 == 0x22001000 && r6 == 0 && r7 == 1 && Protocol.Read(span.Slice(28)) == 0,
                                "Event-only flag setter must use native permission path without forcing latches");
                            goto case GameOffsets.GdtSetBoolByName;
                        case GameOffsets.GdtSetBoolByName:
                        case GameOffsets.GdtSetS32ByName:
                            if (target is GameOffsets.GdtSetBoolByName or GameOffsets.GdtSetS32ByName)
                                Require(r3 == GdtMgrAddr, "Invalid native setter manager");
                            string flagName = ReadSafeString(r5);
                            if (CommitNativeImmediately) NativeValues[flagName] = r4;
                            else PendingNativeValues[flagName] = r4;
                            retR3 = 1;
                            break;
                        case GameOffsets.GdtGetBoolByName:
                        case GameOffsets.GdtGetS32ByName when ReadSafeString(r5) != "CurrentRupee":
                            Require(r3 == 0x22000000 && r6 == 1 && r7 == 1, "Invalid native flag read ABI");
                            uint flagValue = NativeValues.GetValueOrDefault(ReadSafeString(r5));
                            // Bool output is one byte at the big-endian out address.
                            if (target == GameOffsets.GdtGetBoolByName)
                                WriteGuestBytes(r4, [(byte)flagValue]);
                            else WriteGuestWord(r4, flagValue);
                            retR3 = 1;
                            break;
                        case GameOffsets.GdtGetS32ByName:
                            Require(r3 == 0x22000000 && ReadSafeString(r5) == "CurrentRupee" && r6 == 1 && r7 == 1,
                                "Invalid wallet read ABI");
                            WriteGuestWord(r4, Wallet);
                            retR3 = 1;
                            break;
                        case GameOffsets.IncreaseCurrentRupee:
                            Require(r4 == 0, "Invalid rupee delta tag");
                            PendingWallet = Math.Min(Wallet + r3, 999999);
                            break;
                        case GameOffsets.GdtGetS32:
                            Require(r4 == 0, "Invalid getS32 debug flag");
                            retR3 = unchecked((uint)SavedS32[r3]);
                            break;
                        case GameOffsets.GdtSetS32:
                            PendingS32[r4] = unchecked((int)r3);
                            break;
                        case GameOffsets.PlayerInfoSetMaxHeartValue:
                            Require(r3 == PlayerInfoAddr, "Invalid PlayerInfo pointer");
                            PendingS32[101] = unchecked((int)r4);
                            break;
                        case GameOffsets.GdtGetFlagStaminaMax:
                            Require(r3 == 0, "Invalid stamina debug flag");
                            retF1 = SavedStamina;
                            break;
                        case GameOffsets.PlayerInfoSetStaminaMax:
                            Require(r3 == PlayerInfoAddr, "Invalid PlayerInfo pointer");
                            PendingStamina = f1;
                            break;
                        case GameOffsets.PlayerInfoSetActorStaminaMax:
                            Require(r3 == PlayerInfoAddr && PendingStamina == f1, "Invalid actor stamina setter call");
                            ActorStaminaRefreshes++;
                            break;
                        default:
                            throw new Exception($"Unexpected RPC target 0x{target:X8}");
                    }
                }
                Protocol.Write(span.Slice(56), retR3);
                Protocol.WriteFloat(span.Slice(60), retF1);
                Protocol.Write(MailboxBytes.AsSpan(Protocol.Get("ack_sequence_offset")), seq);
                tail = unchecked(tail + 1);
                Protocol.Write(MailboxBytes.AsSpan(16), tail);
            }
            Require(!Locked, "PauseMenuDataMgr critical section remained locked after tick");
        }

        public void Dispose() { }
    }

    private sealed class Server : IServerLink
    {
        public bool Connected { get; set; } = true;
        public IReadOnlyList<ReceivedItem> ReceivedItems { get; set; } = [];
        public List<long> Sent { get; } = [];
        public int GoalReports { get; private set; }
        public bool FailSend { get; set; }
        public void SendChecks(long[] ids) { if (FailSend) throw new IOException("Simulated network failure"); Sent.AddRange(ids); }
        public void SendGoal() { if (FailSend) throw new IOException("Simulated network failure"); GoalReports++; }
    }

    private static void Require(bool value, string message) { if (!value) throw new Exception(message); }

    private static void Reject(Action action)
    {
        try { action(); } catch (Exception ex) when (ex is ArgumentException or InvalidDataException) { return; }
        throw new Exception("Expected validation failure");
    }

    private static void ConfigureMailbox(GuestSimulator sim, Mailbox mailbox, uint location, uint capabilities = 7)
    {
        Array.Clear(sim.MailboxBytes);
        sim.ClearPouch();
        "APMBBOTW"u8.CopyTo(sim.MailboxBytes);
        "APV2"u8.CopyTo(sim.MailboxBytes.AsSpan(Protocol.Get("extension_offset")));
        mailbox.SetWord(Protocol.Get("version_offset"), 2);
        mailbox.SetWord(Protocol.Get("capabilities_offset"), capabilities);
        mailbox.SetWord(Protocol.Get("configured_offset"), 1);
        mailbox.SetWord(Protocol.Get("location_count_offset"), 1);
        mailbox.SetWord(Protocol.Get("location_table_offset"), location);
        sim.Tick();
    }

    private static void DriveUntilIdle(ClientBridge bridge, IServerLink server, GuestSimulator sim, int maxSteps = 10)
    {
        for (int i = 0; i < maxSteps; i++)
        {
            bridge.Pump(server);
            sim.Tick();
        }
        bridge.Pump(server);
    }

    private static void TestProducerLease()
    {
        string path = Path.Combine(Path.GetTempPath(), "botw-ap-lease-test-" + Guid.NewGuid().ToString("N") + ".lock");
        try
        {
            using (var lease = CemuMemoryReader.AcquireProducerLease(path))
            {
                Require(File.Exists(path), "Producer lock missing while held");
                try
                {
                    using var competing = CemuMemoryReader.AcquireProducerLease(path);
                    throw new Exception("Concurrent producer acquired the Cemu lock");
                }
                catch (IOException) { }
                Require(File.Exists(path), "Rejected producer removed the active lock");
            }
            Require(!File.Exists(path), "Normal shutdown left the Cemu lock behind");
            try
            {
                using var lease = CemuMemoryReader.AcquireProducerLease(path);
                // Reproduce a /proc/PID/mem permission failure after lock acquisition.
                throw new UnauthorizedAccessException("Memory access denied");
            }
            catch (UnauthorizedAccessException) { }
            Require(!File.Exists(path), "Failed attachment left the Cemu lock behind");
            File.WriteAllText(path, "stale lock");
            using (var lease = CemuMemoryReader.AcquireProducerLease(path)) { }
            Require(!File.Exists(path), "Stale lock was not reclaimed and removed");
            using (var lease = CemuMemoryReader.AcquireProducerLease(path)) { }
            Require(!File.Exists(path), "Retry left the Cemu lock behind");
            Console.WriteLine("PASS: producer lock exclusion, failure cleanup, stale lock recovery and retry");
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    private static void TestEndpoints()
    {
        var automatic = ServerEndpoint.Parse("archipelago.reprgb.gay", "63456");
        Require(automatic.Scheme == "unspecified" && automatic.Port == 63456, "Separate --port was ignored");
        Require(ServerEndpoint.Parse("localhost").Port == 38281, "Bare-host default port changed");
        Require(ServerEndpoint.Parse("localhost:12345").Port == 12345, "Embedded port lost");
        Require(ServerEndpoint.Parse("wss://example.org").Port == 443, "WSS default port incorrect");
        Require(ServerEndpoint.Parse("ws://example.org").Port == 80, "WS default port incorrect");
        Require(ServerEndpoint.Parse("wss://example.org:443", "443").Port == 443, "Matching explicit default port rejected");
        var secure = ServerEndpoint.Parse("wss://example.org/ap/socket?room=1", "63456");
        Require(secure.Scheme == "wss" && secure.Port == 63456 && secure.PathAndQuery == "/ap/socket?room=1", "WSS URL components lost");
        Require(ServerEndpoint.Parse("[::1]", "12345").HostNameType == UriHostNameType.IPv6, "IPv6 host rejected");
        Require(ServerEndpoint.Parse("ws://[::1]:12345").Port == 12345, "IPv6 port lost");
        foreach (string bad in new[] { "", "0", "65536", "-1", "abc" }) Reject(() => ServerEndpoint.Parse("localhost", bad));
        foreach (string bad in new[] { "", "https://example.org", "ftp://example.org", "wss://user:secret@example.org", "ws://localhost/#fragment", "localhost:0", "localhost:99999" })
            Reject(() => ServerEndpoint.Parse(bad));
        Reject(() => ServerEndpoint.Parse("localhost:12345", "23456"));
        Reject(() => ServerEndpoint.Parse("wss://example.org:443", "12345"));
        using var output = new StringWriter();
        new ClientLog(false, output: output).Write("hidden");
        Require(output.ToString().Length == 0, "Verbose logging enabled by default");
        new ClientLog(true, "test-secret", output).Write("failure: test-secret");
        Require(output.ToString().Contains("[redacted]") && !output.ToString().Contains("test-secret"), "Diagnostic password leaked");
        Require(!APSessionManager.Summarize(new global::Archipelago.MultiClient.Net.Packets.ConnectPacket { Password = "test-secret" }).Contains("test-secret"), "Connect packet password leaked");
    }

    private static void TestTlsSubprocess(string directory)
    {
        using var key = RSA.Create(2048);
        var request = new CertificateRequest("CN=localhost", key, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        var names = new SubjectAlternativeNameBuilder(); names.AddIpAddress(IPAddress.Loopback); names.AddDnsName("localhost");
        request.CertificateExtensions.Add(names.Build());
        request.CertificateExtensions.Add(new X509BasicConstraintsExtension(true, false, 0, true));
        using var certificate = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddHours(1));
        string pfx = Path.Combine(directory, "test-tls.pfx"), pem = Path.Combine(directory, "test-ca.pem");
        File.WriteAllBytes(pfx, certificate.Export(X509ContentType.Pfx));
        File.WriteAllText(pem, certificate.ExportCertificatePem());
        var start = new ProcessStartInfo(Environment.ProcessPath!) { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        if (Path.GetFileNameWithoutExtension(Environment.ProcessPath) == "dotnet") start.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory, "BotWClient.dll"));
        start.ArgumentList.Add("--self-test-tls"); start.ArgumentList.Add(pfx);
        start.Environment["SSL_CERT_FILE"] = pem;
        using var process = Process.Start(start)!;
        var stdout = process.StandardOutput.ReadToEndAsync(); var stderr = process.StandardError.ReadToEndAsync();
        if (!process.WaitForExit(30000)) { process.Kill(entireProcessTree: true); throw new Exception("WSS integration test timed out"); }
        Require(process.ExitCode == 0, $"WSS integration failed: {stdout.GetAwaiter().GetResult()} {stderr.GetAwaiter().GetResult()}");
        Console.WriteLine("PASS: real AP SDK login, item delivery and checks over WSS with certificate validation");
    }

    private static void TestGoalPrerequisites()
    {
        const uint goal = 0xC2000000, prerequisite = goal + 1;
        using var sim = new GuestSimulator();
        using var mailbox = new Mailbox(sim);
        ConfigureMailbox(sim, mailbox, goal);
        mailbox.SetWord(Protocol.Get("location_count_offset"), 2);
        mailbox.SetWord(Protocol.Get("location_table_offset") + 8, prerequisite);
        var data = JsonSerializer.SerializeToElement(new {
            protocol_version = 2, player = 1, seed = "test",
            seed_fingerprint = new string('0', 32), check_actor_prefix = "AP_Check_",
            goal_location_id = goal, goal_required_location_ids = new[] { prerequisite },
            locations = new Dictionary<string, string> {
                [goal.ToString()] = $"AP_Check_{goal:X8}",
                [prerequisite.ToString()] = $"AP_Check_{prerequisite:X8}"
            }, items = new { }
        });
        var contract = new SlotContract(data, mailbox, 1, "test", [goal, prerequisite]);
        var server = new Server();
        string directory = Path.Combine(Path.GetTempPath(), "botw-goal-test-" + Guid.NewGuid().ToString("N"));
        void Emit(uint index, uint location)
        {
            int offset = Protocol.Get("outgoing_offset") + (int)index * 16;
            mailbox.SetWord(offset, index);
            mailbox.SetWord(offset + 4, 0);
            mailbox.SetWord(offset + 8, location);
            mailbox.SetWord(offset + 12, 0);
            mailbox.SetWord(20, index + 1);
        }
        try
        {
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                Emit(0, goal); bridge.Pump(server);
                Require(server.Sent.Contains(goal) && server.GoalReports == 0,
                        "Early Dark Beast check incorrectly reported Victory");
            }
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                bridge.Pump(server);
                Require(server.GoalReports == 0, "Reconnect bypassed missing goal prerequisites");
                Emit(1, prerequisite); bridge.Pump(server);
                Require(server.Sent.Contains(prerequisite) && server.GoalReports == 1,
                        "Completing the last prerequisite did not report Victory");
            }
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                bridge.Pump(server);
                Require(server.GoalReports == 2, "Completed goal was not replayed after reconnect");
            }
        }
        finally { if (Directory.Exists(directory)) Directory.Delete(directory, true); }
    }

    public static int Run(string? tlsCertificate = null)
    {
        string directory = Path.Combine(Path.GetTempPath(), "botw-ap-client-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            TestEndpoints();
            TestProducerLease();
            TestGoalPrerequisites();
            const uint location = 0xB0123456, swordItem = 0xB0100001, unsupported = 0xB0100002,
                       arrowItem = 0xB0100003, foodItem = 0xB0100004, keyItem = 0xB0100005, badActorItem = 0xB0100006;

            using var sim = new GuestSimulator();
            using var mailbox = new Mailbox(sim);
            ConfigureMailbox(sim, mailbox, location, capabilities: 5);

            using var data = JsonDocument.Parse($$$$"""
            {"protocol_version":2,"player":1,"seed":"test","seed_fingerprint":"00000000000000000000000000000000",
             "check_actor_prefix":"AP_Check_","goal_location_id":{{{{location}}}},"locations":{"{{{{location}}}}":"AP_Check_B0123456"},
             "items":{"{{{{swordItem}}}}":{"kind":"actor","actor":"Weapon_Sword_070","quantity":1},
                      "{{{{arrowItem}}}}":{"kind":"actor","actor":"NormalArrow","quantity":10},
                      "{{{{foodItem}}}}":{"kind":"actor","actor":"Item_Cook_A","quantity":1},
                      "{{{{keyItem}}}}":{"kind":"actor","actor":"PlayerStole2","quantity":1},
                      "{{{{badActorItem}}}}":{"kind":"actor","actor":"Invalid_Actor_Name","quantity":1},
                      "{{{{unsupported}}}}":{"kind":"unimplemented","name":"Tower"}}}
            """);

            var contract = new SlotContract(data.RootElement, mailbox, 1, "test", [location]);
            Reject(() => new SlotContract(data.RootElement, mailbox, 2, "test", [location]));
            Reject(() => new SlotContract(data.RootElement, mailbox, 1, "other", [location]));
            Reject(() => Protocol.ValidateActorName(new string('x', 48), 1));
            Reject(() => Protocol.ValidateActorName("AP_Check_B0123456", 1));
            Reject(() => Protocol.ValidateActorName("nonascii_é", 1));
            Reject(() => Protocol.ValidateActorName("Item", 0));
            Reject(() => Protocol.ValidateActorName("Weapon_Sword_070", 2));
            Reject(() => Protocol.Encode(new RpcCall(0, GameOffsets.GetPouchItemType)));
            Reject(() => Protocol.Encode(new RpcCall(1, 0)));

            var encodedCall = Protocol.Encode(new RpcCall(7, GameOffsets.PauseMenuAddItem, 1, 2, 3, 4, 5, 6, 7, 8, 200f));
            Require(Protocol.Read(encodedCall.AsSpan(0)) == 7 &&
                    Protocol.Read(encodedCall.AsSpan(4)) == GameOffsets.PauseMenuAddItem &&
                    Protocol.Read(encodedCall.AsSpan(8)) == 1 &&
                    Protocol.Read(encodedCall.AsSpan(36)) == 8 &&
                    Protocol.ReadFloat(encodedCall.AsSpan(40)) == 200f, "Incorrect big-endian RPC wire encoding");

            using var progressionData = JsonDocument.Parse($$$$"""
            {"protocol_version":2,"player":1,"seed":"test","seed_fingerprint":"00000000000000000000000000000000",
             "check_actor_prefix":"AP_Check_","locations":{"{{{{location}}}}":"AP_Check_B0123456"},
             "items":{"2953838612":{"kind":"unimplemented","name":"Heart Container"},
                      "2953838613":{"kind":"progression","name":"Stamina Vessel","command":"stamina_vessel","quantity":1},
                      "2953838629":{"kind":"unimplemented","name":"Weapon Slot"},
                      "2953838630":{"kind":"unimplemented","name":"Bow Slot"},
                      "2953838631":{"kind":"unimplemented","name":"Shield Slot"}}}
            """);
            var progressionContract = new SlotContract(progressionData.RootElement, mailbox, 1, "test", [location]);
            Require(progressionContract.ResolveGrant(2953838612, out var oldHookReason) is null &&
                    oldHookReason!.Contains("updated progression hook"), "Hook without progression capability must block progression grants");

            mailbox.SetWord(Protocol.Get("capabilities_offset"), 7);
            uint[] upgradeIds = [2953838612, 2953838613, 2953838629, 2953838630, 2953838631];
            var upgrades = new Server { ReceivedItems = upgradeIds.Select(id => new ReceivedItem(id, 100)).ToList() };
            using (var bridge = new ClientBridge(mailbox, progressionContract, Path.Combine(directory, "upgrades"), 0, 1))
            {
                for (int upgrade = 0; upgrade < upgradeIds.Length; upgrade++)
                {
                    int setterCountBefore = sim.Calls.Count(c => c is GameOffsets.PlayerInfoSetMaxHeartValue or GameOffsets.PlayerInfoSetStaminaMax or GameOffsets.GdtSetS32);
                    bridge.Pump(upgrades); sim.Tick();
                    bridge.Pump(upgrades); sim.Tick();
                    int setterCountAfter = sim.Calls.Count(c => c is GameOffsets.PlayerInfoSetMaxHeartValue or GameOffsets.PlayerInfoSetStaminaMax or GameOffsets.GdtSetS32);
                    Require(setterCountAfter == setterCountBefore + 1, "Progression must invoke native setter once");
                    for (int poll = 0; poll < 3; poll++)
                    {
                        bridge.Pump(upgrades); sim.Tick();
                        Require(bridge.NextItem == upgrade && bridge.BlockReason is not null, "Pending save-backed progression must wait");
                        Require(sim.Calls.Count(c => c is GameOffsets.PlayerInfoSetMaxHeartValue or GameOffsets.PlayerInfoSetStaminaMax or GameOffsets.GdtSetS32) == setterCountAfter,
                            "Asynchronous progression setter must never be repeated for the same receipt");
                    }
                    sim.CommitProgression();
                    bridge.Pump(upgrades); sim.Tick();
                }
                bridge.Pump(upgrades);
                Require(bridge.NextItem == 5 && sim.SavedS32[101] == 16 && sim.SavedStamina == 1200f &&
                        sim.ActorStaminaRefreshes == 1 && sim.SavedS32[103] == 9 && sim.SavedS32[104] == 6 && sim.SavedS32[105] == 5,
                        "All five progression upgrades must advance saved values and history");
            }

            ConfigureMailbox(sim, mailbox, location);
            using (var walletData = JsonDocument.Parse("""
                {"protocol_version":2,"check_actor_prefix":"AP_Check_","player":1,"seed":"test",
                 "seed_fingerprint":"00000000000000000000000000000000",
                 "locations":{"2953983062":"AP_Check_B0123456"},
                 "items":{"700":{"kind":"rupees","name":"100 Rupees","quantity":100}}}
                """))
            {
                var walletContract = new SlotContract(walletData.RootElement, mailbox, 1, "test", [location]);
                var walletServer = new Server { ReceivedItems = [700] };
                using var walletBridge = new ClientBridge(mailbox, walletContract, Path.Combine(directory, "wallet"), 0, 1);
                for (int i = 0; i < 12; i++) { walletBridge.Pump(walletServer); sim.Tick(); }
                Require(walletBridge.NextItem == 0 && sim.PendingWallet == 223 && sim.Wallet == 123,
                    "Wallet must wait for asynchronous delta to commit");
                Require(sim.Calls.Count(c => c == GameOffsets.IncreaseCurrentRupee) == 1,
                    "Wallet delta must be issued exactly once");
                sim.CommitProgression();
                DriveUntilIdle(walletBridge, walletServer, sim);
                Require(walletBridge.NextItem == 1 && sim.Wallet == 223, "Wallet receipt not acknowledged after commit");
            }

            ConfigureMailbox(sim, mailbox, location);
            sim.NativeValues.Clear();
            sim.CommitNativeImmediately = false;
            using (var recoveryData = JsonDocument.Parse(JsonSerializer.Serialize(new {
                protocol_version = 2, player = 1, seed = "test", seed_fingerprint = new string('0', 32),
                check_actor_prefix = "AP_Check_", locations = new Dictionary<string,string> { [location.ToString()] = "AP_Check_B0123456" },
                items = new Dictionary<string,object> { ["800"] = new { kind = "native", name = "Progressive Stasis", quantity = 1 } } })))
            {
                var recoveryContract = new SlotContract(recoveryData.RootElement, mailbox, 1, "test", [location]);
                var recoveryServer = new Server { ReceivedItems = [800] };
                string recoveryDirectory = Path.Combine(directory, "native-recovery");
                using (var first = new ClientBridge(mailbox, recoveryContract, recoveryDirectory, 0, 1))
                {
                    DriveUntilIdle(first, recoveryServer, sim, maxSteps: 6);
                    Require(first.NextItem == 0 && sim.PendingNativeValues.GetValueOrDefault("IsGet_Obj_StopTimer") == 1,
                        "Native grant acknowledged before saved flag commit");
                }
                sim.CommitProgression();
                using (var resumed = new ClientBridge(mailbox, recoveryContract, recoveryDirectory, 0, 1))
                {
                    DriveUntilIdle(resumed, recoveryServer, sim, maxSteps: 15);
                    Require(resumed.NextItem == 1 && sim.NativeValues["IsGet_Obj_StopTimer"] == 1 &&
                        sim.NativeValues.GetValueOrDefault("IsGet_Obj_StopTimerLv2") == 0,
                        "Reconnect advanced a partly applied receipt to the next progressive tier");
                }
            }
            sim.CommitNativeImmediately = true;
            sim.NativeValues.Clear();
            ConfigureMailbox(sim, mailbox, location);
            var nativeItems = new Dictionary<string, object>();
            var nativeReceipts = new List<ReceivedItem>();
            long nativeId = 1000;
            foreach (var pair in NativeGrants.Profiles)
            {
                nativeItems[(nativeId).ToString()] = new { kind = "native", name = pair.Key, quantity = 1 };
                for (int i = 0; i < pair.Value.Tiers.Length + 1; i++) nativeReceipts.Add(nativeId);
                nativeId++;
            }
            using (var nativeData = JsonDocument.Parse(JsonSerializer.Serialize(new {
                protocol_version = 2, player = 1, seed = "test", seed_fingerprint = new string('0', 32),
                check_actor_prefix = "AP_Check_", locations = new Dictionary<string,string> { [location.ToString()] = "AP_Check_B0123456" },
                items = nativeItems })))
            {
                var nativeContract = new SlotContract(nativeData.RootElement, mailbox, 1, "test", [location]);
                var nativeServer = new Server { ReceivedItems = nativeReceipts };
                using var nativeBridge = new ClientBridge(mailbox, nativeContract, Path.Combine(directory, "native"), 0, 1);
                DriveUntilIdle(nativeBridge, nativeServer, sim, maxSteps: 2500);
                Require(nativeBridge.NextItem == nativeReceipts.Count, "Native receipts failed to drain");
                Require(sim.NativeValues["IsGet_Obj_RemoteBombLv2"] == 1 && sim.NativeValues["IsGet_Obj_RemoteBombCube2"] == 1 &&
                    sim.NativeValues["GreatFairy_ArmorRank"] == 4 && sim.NativeValues["MasterSword_Add_Power"] == 30 &&
                    sim.NativeValues["Open_MasterSword_FullPower"] == 1 && sim.NativeValues["MapTower_07"] == 1 &&
                    sim.NativeValues["IsGet_App_FinalTrial"] == 1, "Native tiers or caps incorrect");
                foreach (string race in new[] { "Rito", "Goron", "Zora", "Gerudo" })
                {
                    Require(sim.TotalPouchValue("Obj_HeroSoul_" + race) == 0 &&
                        sim.TotalPouchValue("Obj_DLC_HeroSoul_" + race) == 1,
                        "Champion upgrade must replace the base key item for " + race);
                }
                Require(sim.Calls.Contains(GameOffsets.MapInitTowerRecords), "Tower grant omitted native map refresh");
            }

            // Stop after an upgrade has queued removal, reconnect with the batch
            // journaled but unpublished, then reconnect again after native execution.
            ConfigureMailbox(sim, mailbox, location);
            sim.ClearPouch();
            sim.SetPouchItem("Obj_HeroSoul_Rito", 1);
            sim.SetPouchItem("PlayerStole2", 1);
            sim.NativeValues.Clear();
            sim.NativeValues["IsGet_Obj_HeroSoul_Rito"] = 1;
            using (var championData = JsonDocument.Parse(JsonSerializer.Serialize(new {
                protocol_version = 2, player = 1, seed = "test", seed_fingerprint = new string('0', 32),
                check_actor_prefix = "AP_Check_", locations = new Dictionary<string,string> { [location.ToString()] = "AP_Check_B0123456" },
                items = new Dictionary<string,object> { ["900"] = new { kind = "native", name = "Progressive Revali's Gale", quantity = 1 } } })))
            {
                var championContract = new SlotContract(championData.RootElement, mailbox, 1, "test", [location]);
                var championServer = new Server { ReceivedItems = [900] };
                string championDirectory = Path.Combine(directory, "champion-removal");
                bool queuedRemoval = false;
                using (var first = new ClientBridge(mailbox, championContract, championDirectory, 0, 1))
                {
                    for (int i = 0; i < 50; i++)
                    {
                        first.Pump(championServer);
                        using var journal = JsonDocument.Parse(File.ReadAllText(Directory.GetFiles(championDirectory, "*.json").Single()));
                        queuedRemoval = journal.RootElement.GetProperty("InFlight").GetProperty("Stage").GetString() == "NativeRemove";
                        if (queuedRemoval) break;
                        sim.Tick();
                    }
                    Require(queuedRemoval && first.NextItem == 0 && sim.TotalPouchValue("Obj_DLC_HeroSoul_Rito") == 1 &&
                        sim.NativeValues["IsGet_Obj_DLC_HeroSoul_Rito"] == 1, "Base removed before upgraded grant was confirmed");
                }
                // Recreate the crash window between journal save and ring publication.
                mailbox.SetWord(12, mailbox.InTail);
                mailbox.WriteSafeString("UnrelatedScratchContents");
                sim.HoldChampionRemoval = true;
                using (var second = new ClientBridge(mailbox, championContract, championDirectory, 0, 1))
                {
                    DriveUntilIdle(second, championServer, sim, maxSteps: 8);
                    Require(second.NextItem == 0 && sim.TotalPouchValue("Obj_HeroSoul_Rito") == 1,
                        "Receipt acknowledged while base removal was pending");
                    sim.HoldChampionRemoval = false;
                    // Execute removal without consuming its acknowledgement.
                    second.Pump(championServer);
                    sim.Tick();
                }
                int removalsBeforeResume = sim.RemovedChampionItems.Count;
                using (var third = new ClientBridge(mailbox, championContract, championDirectory, 0, 1))
                {
                    DriveUntilIdle(third, championServer, sim, maxSteps: 10);
                    Require(third.NextItem == 1 && sim.TotalPouchValue("Obj_HeroSoul_Rito") == 0 &&
                        sim.TotalPouchValue("Obj_DLC_HeroSoul_Rito") == 1 && sim.TotalPouchValue("PlayerStole2") == 1,
                        "Removal recovery failed or changed unrelated pouch entries");
                    Require(sim.RemovedChampionItems.Count == removalsBeforeResume,
                        "Already executed champion removal was repeated after reconnect");
                }
            }

            ConfigureMailbox(sim, mailbox, location);
            using (var armorData = JsonDocument.Parse(JsonSerializer.Serialize(new {
                protocol_version = 2, player = 1, seed = "test", seed_fingerprint = new string('0', 32),
                check_actor_prefix = "AP_Check_", locations = new Dictionary<string,string> { [location.ToString()] = "AP_Check_B0123456" },
                items = new Dictionary<string,object> { ["901"] = new { kind = "actor", actor = "Armor_029_Head", quantity = 1 } } })))
            {
                var armorContract = new SlotContract(armorData.RootElement, mailbox, 1, "test", [location]);
                var armorServer = new Server { ReceivedItems = [901] };
                using var armorBridge = new ClientBridge(mailbox, armorContract, Path.Combine(directory, "armor-sentinel"), 0, 1);
                DriveUntilIdle(armorBridge, armorServer, sim);
                var measured = mailbox.MeasureStablePouch(GuestSimulator.PauseMgrAddr, "Armor_029_Head");
                Require(armorBridge.NextItem == 1 && measured.Count == 1 && measured.Sum == 1,
                    "Armor sentinel values must not cause duplicate grants or a blocked queue");
            }

            ConfigureMailbox(sim, mailbox, location);
            sim.PerCallStackCap = 3;
            sim.SetPouchItem("PlayerStole2", 1);
            var batchServer = new Server { ReceivedItems = [arrowItem, foodItem, keyItem, badActorItem] };
            using (var bridge = new ClientBridge(mailbox, contract, Path.Combine(directory, "pouch"), 0, 1))
            {
                DriveUntilIdle(bridge, batchServer, sim, maxSteps: 20);
                Require(bridge.NextItem == 3 && sim.TotalPouchValue("NormalArrow") == 10 && sim.TotalPouchValue("Item_Cook_A") == 1 &&
                        sim.Calls.Contains(GameOffsets.PauseMenuPostAddFood) && bridge.BlockReason is not null,
                        "Stackable partial loop, food post-add, owned key item, and invalid actor handling failed");
            }
            sim.PerCallStackCap = null;

            ConfigureMailbox(sim, mailbox, location);
            sim.PouchFull = true;
            var server = new Server { ReceivedItems = [swordItem, unsupported] };
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                DriveUntilIdle(bridge, server, sim, maxSteps: 4);
                Require(bridge.NextItem == 0 && bridge.BlockReason is not null && sim.TotalPouchValue("Weapon_Sword_070") == 0,
                        "Full pouch must retain its weapon item");
                sim.PouchFull = false;
                bridge.Pump(server);
                Require(mailbox.InHead > mailbox.InTail && bridge.NextItem == 0, "Add batch must wait for hook execution");
            }

            uint lifetime = mailbox.Word(Protocol.Get("reserved_offset"));
            mailbox.SetWord(Protocol.Get("reserved_offset"), 0);
            Reject(() => { using var reset = new ClientBridge(mailbox, contract, directory, 0, 1); });
            mailbox.SetWord(Protocol.Get("reserved_offset"), lifetime);

            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                uint pendingHead = mailbox.InHead;
                server.ReceivedItems = []; bridge.Pump(server);
                Require(bridge.BlockReason is not null && mailbox.InHead == pendingHead, "Reconnect did not wait for item history replay");
                server.ReceivedItems = [swordItem, unsupported];
                bridge.Pump(server);
                Require(mailbox.InHead == pendingHead, "In-flight RPC batch duplicated after reconnect");
                sim.Tick();
                bridge.Pump(server);
                Require(bridge.NextItem == 1 && sim.TotalPouchValue("Weapon_Sword_070") == 40 && bridge.BlockReason is not null,
                        "Weapon durability or unsupported item block failed after reconnect");

                int offset = Protocol.Get("outgoing_offset");
                mailbox.SetWord(offset, 0); mailbox.SetWord(offset + 4, 0); mailbox.SetWord(offset + 8, location); mailbox.SetWord(offset + 12, 0); mailbox.SetWord(20, 1);
                server.FailSend = true;
                try { bridge.Pump(server); } catch (IOException) { }
                Require(mailbox.OutTail == 1 && server.Sent.Count == 0, "Check ownership was not journaled before network failure");
            }
            server.FailSend = false;
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                bridge.Pump(server);
                Require(server.Sent.Contains(location) && server.GoalReports == 1 && bridge.NextItem == 1 && sim.TotalPouchValue("Weapon_Sword_070") == 40,
                        "Reconnect lost a check, failed to report CLIENT_GOAL, or replayed an acknowledged item");
            }

            ConfigureMailbox(sim, mailbox, location);
            using (var fixture = new ProtocolServerFixture(data.RootElement, location, swordItem))
            using (var tls = tlsCertificate is null ? null : new TlsServerFixture(fixture.Uri, tlsCertificate))
            using (var output = new StringWriter())
            using (var session = new APSessionManager(tls?.Uri ?? fixture.Uri, "Test", "test-secret", mailbox, new ClientLog(true, "test-secret", output).Write))
            using (var bridge = new ClientBridge(mailbox, session.Contract, Path.Combine(directory, "network"), session.Team, session.Slot))
            {
                Require(SpinWait.SpinUntil(() => session.ReceivedItems.Count == 1, 5000), "AP SDK did not receive item history");
                int offset = Protocol.Get("outgoing_offset");
                mailbox.SetWord(offset, 0); mailbox.SetWord(offset + 4, 0); mailbox.SetWord(offset + 8, location); mailbox.SetWord(offset + 12, 0); mailbox.SetWord(20, 1);
                DriveUntilIdle(bridge, session, sim, maxSteps: 5);
                Require(bridge.NextItem == 1 && sim.TotalPouchValue("Weapon_Sword_070") == 40, "AP network item was not granted via RPC");
                Require(fixture.Checks.Task.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult().Contains(location), "Mailbox check did not reach the AP socket");
                Require(fixture.GoalStatus.Task.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult() == (int)ArchipelagoClientState.ClientGoal,
                        "Goal check did not send CLIENT_GOAL over the real AP SDK socket");
                string diagnostics = output.ToString();
                Require(diagnostics.Contains("RoomInfo") && diagnostics.Contains("Connected") && diagnostics.Contains("AP slot verified") && diagnostics.Contains("ReceivedItems"), "Verbose connection stages missing");
                Require(!diagnostics.Contains("test-secret"), "Password leaked during real login");
            }

            ConfigureMailbox(sim, mailbox, location);
            var startNode = JsonNode.Parse(data.RootElement.GetRawText())!;
            startNode["starting_state"] = JsonSerializer.SerializeToNode(new { version = 1, logical_inventory = new Dictionary<string, int> { ["Tower"] = 1 } });
            startNode["starting_inventory"] = JsonSerializer.SerializeToNode(new Dictionary<string, int> { [unsupported.ToString()] = 1 });
            using var startData = JsonDocument.Parse(startNode.ToJsonString());
            var startContract = new SlotContract(startData.RootElement, mailbox, 1, "test", [location]);
            server.ReceivedItems = [new ReceivedItem(unsupported, -2), swordItem, new ReceivedItem(unsupported, -2)];
            string startDirectory = Path.Combine(directory, "starting");
            using (var bridge = new ClientBridge(mailbox, startContract, startDirectory, 0, 1))
            {
                DriveUntilIdle(bridge, server, sim, maxSteps: 5);
                Require(bridge.NextItem == 2 && bridge.BlockReason is not null,
                        "Applied starting item blocked delivery or failed to hold extra precollected item");
            }
            using (var bridge = new ClientBridge(mailbox, startContract, startDirectory, 0, 1))
            {
                server.ReceivedItems = [new ReceivedItem(unsupported, -2), swordItem, new ReceivedItem(unsupported, location)];
                bridge.Pump(server);
                Require(bridge.NextItem == 2 && bridge.BlockReason is not null,
                        "Reconnect replayed defaults or discarded a chest reward with a starting item ID");
            }

            mailbox.SetWord(12, uint.MaxValue); mailbox.SetWord(16, uint.MaxValue);
            Require(mailbox.Enqueue(new RpcCall(2, GameOffsets.GetPouchItemType, 1, 0), uint.MaxValue) && mailbox.InHead == 0, "Counter wrap failed");
            mailbox.SetWord(12, 256); mailbox.SetWord(16, 0);
            Require(!mailbox.Enqueue(new RpcCall(3, GameOffsets.GetPouchItemType, 1, 0), 256), "Full ring overwritten");
            mailbox.SetWord(Protocol.Get("capabilities_offset"), 3); Reject(() => mailbox.Validate());
            mailbox.SetWord(Protocol.Get("capabilities_offset"), 7);
            mailbox.SetWord(Protocol.Get("version_offset"), 1); Reject(() => mailbox.Validate());

            Console.WriteLine("PASS: RPC wire format, Wii U v208 offsets, item/native/progression grants, champion replacement and removal recovery, reconnect/journal/network failure, starting inventory, queue capacity, counter wrap, real AP SDK check-before-goal status, and WebSocket exchange");
            if (tlsCertificate is null && OperatingSystem.IsLinux()) TestTlsSubprocess(directory);
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        finally { if (Directory.Exists(directory)) Directory.Delete(directory, recursive: true); }
    }
}
