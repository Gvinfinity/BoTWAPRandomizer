using System.Text;
using System.Text.Json;
using System.IO.Compression;
using System.Text.RegularExpressions;
using System.Text.Json.Nodes;
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
            using var ram = new ArrayMemory();
            for (int i = 0; i < words.Length; i++) Protocol.Write(ram.Bytes.AsSpan(i*4), words[i]);
            using var mailbox = new Mailbox(ram);
            long[] ids = plan.GetProperty("locations").EnumerateArray().Select(entry => entry.GetProperty("id").GetInt64()).ToArray();
            var contract = new SlotContract(plan.GetProperty("slot_data"), mailbox, plan.GetProperty("player").GetInt32(), plan.GetProperty("seed").GetString()!, ids);
            int native = 0, unsupported = 0;
            foreach (var item in plan.GetProperty("slot_data").GetProperty("items").EnumerateObject())
            {
                if (contract.Delivery(long.Parse(item.Name), 1, out _) is not null) native++;
                else unsupported++;
            }
            Console.WriteLine($"PASS: generated pack accepted by C#; {ids.Length} checks, {native} native actor mappings, {unsupported} explicitly unsupported grants, fingerprint {contract.Fingerprint}");
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }
    private sealed class ArrayMemory : IMemory
    {
        public readonly byte[] Bytes = new byte[Protocol.Get("mailbox_size")];
        public byte[] Read(int offset, int length) => Bytes.AsSpan(offset, length).ToArray();
        public void Write(int offset, byte[] bytes) => bytes.CopyTo(Bytes, offset);
        public void Dispose() { }
    }
    private sealed class Server : IServerLink
    {
        public bool Connected { get; set; } = true;
        public IReadOnlyList<ReceivedItem> ReceivedItems { get; set; } = [];
        public List<long> Sent { get; } = [];
        public bool FailSend { get; set; }
        public void SendChecks(long[] ids) { if (FailSend) throw new IOException("Simulated network failure"); Sent.AddRange(ids); }
    }
    private static void Require(bool value, string message) { if (!value) throw new Exception(message); }
    private static void Reject(Action action)
    {
        try { action(); } catch (Exception ex) when (ex is ArgumentException or InvalidDataException) { return; }
        throw new Exception("Expected validation failure");
    }
    public static int Run()
    {
        string directory = Path.Combine(Path.GetTempPath(), "botw-ap-client-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var ram = new ArrayMemory(); using var mailbox = new Mailbox(ram);
            "APMBBOTW"u8.CopyTo(ram.Bytes); "APV2"u8.CopyTo(ram.Bytes.AsSpan(Protocol.Get("extension_offset")));
            mailbox.SetWord(Protocol.Get("version_offset"), 2); mailbox.SetWord(Protocol.Get("capabilities_offset"), 1);
            mailbox.SetWord(Protocol.Get("configured_offset"), 1); mailbox.SetWord(Protocol.Get("location_count_offset"), 1);
            const uint location = 0xB0123456, item = 0xB0100001, unsupported = 0xB0100002;
            mailbox.SetWord(Protocol.Get("location_table_offset"), location); mailbox.SetWord(8, 2);
            using var data = JsonDocument.Parse($$$$"""
            {"protocol_version":2,"player":1,"seed":"test","seed_fingerprint":"00000000000000000000000000000000",
             "check_actor_prefix":"AP_Check_","locations":{"{{{{location}}}}":"AP_Check_B0123456"},
             "items":{"{{{{item}}}}":{"kind":"actor","actor":"Weapon_Sword_070","quantity":1},
                      "{{{{unsupported}}}}":{"kind":"unimplemented","name":"Tower"}}}
            """);
            var contract = new SlotContract(data.RootElement, mailbox, 1, "test", [location]);
            Reject(() => new SlotContract(data.RootElement, mailbox, 2, "test", [location]));
            Reject(() => new SlotContract(data.RootElement, mailbox, 1, "other", [location]));
            Reject(() => Protocol.Encode(new IncomingItem(1, item, new string('x', 48), 1)));
            Reject(() => Protocol.Encode(new IncomingItem(1, item, "AP_Check_B0123456", 1)));
            Reject(() => Protocol.Encode(new IncomingItem(1, item, "nonascii_é", 1)));
            Reject(() => Protocol.Encode(new IncomingItem(1, item, "Item", 0)));
            Reject(() => Protocol.Encode(new IncomingItem(1, item, "Weapon_Sword_070", 2)));
            var encoded = Protocol.Encode(new IncomingItem(1, item, "Weapon_Sword_070", 1));
            Require(Protocol.Read(encoded.AsSpan(4)) == item && encoded[55] == 0 && Protocol.Read(encoded.AsSpan(56)) == 1, "Incorrect big endian wire encoding");
            var server = new Server { ReceivedItems = [item, unsupported] };
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                bridge.Pump(server);
                Require(mailbox.InHead == 1 && bridge.NextItem == 0, "Item was consumed before hook acknowledgement");
                mailbox.SetWord(Protocol.Get("delivery_error_offset"), 4); bridge.Pump(server);
                Require(bridge.BlockReason is not null && mailbox.InHead == 1, "Full pouch must hold its item");
                Require(Encoding.ASCII.GetString(ram.Read(Protocol.Get("incoming_offset") + 8, 16)).TrimEnd('\0') == "Weapon_Sword_070", "Actor mapping was ignored");
            }
            // Crash/reconnect while queued must not inject another copy.
            uint lifetime = mailbox.Word(Protocol.Get("reserved_offset"));
            mailbox.SetWord(Protocol.Get("reserved_offset"), 0);
            Reject(() => { using var reset = new ClientBridge(mailbox, contract, directory, 0, 1); });
            mailbox.SetWord(Protocol.Get("reserved_offset"), lifetime);
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                server.ReceivedItems = []; bridge.Pump(server);
                Require(bridge.BlockReason is not null && mailbox.InHead == 1, "Reconnect did not wait for item history replay");
                server.ReceivedItems = [item, unsupported];
                bridge.Pump(server); Require(mailbox.InHead == 1, "Queued item duplicated after reconnect");
                mailbox.SetWord(Protocol.Get("ack_sequence_offset"), 1); mailbox.SetWord(16, 1);
                mailbox.SetWord(Protocol.Get("delivery_error_offset"), 0); bridge.Pump(server);
                Require(bridge.NextItem == 1 && mailbox.InHead == 1 && bridge.BlockReason is not null, "Unsupported item was discarded or fabricated");
                int offset = Protocol.Get("outgoing_offset");
                mailbox.SetWord(offset, 0); mailbox.SetWord(offset + 4, 0); mailbox.SetWord(offset + 8, location); mailbox.SetWord(offset + 12, 0); mailbox.SetWord(20, 1);
                server.FailSend = true;
                try { bridge.Pump(server); } catch (IOException) { }
                Require(mailbox.OutTail == 1 && server.Sent.Count == 0, "Check ownership was not journaled before network failure");
            }
            server.FailSend = false;
            using (var bridge = new ClientBridge(mailbox, contract, directory, 0, 1))
            {
                bridge.Pump(server); Require(server.Sent.Contains(location) && bridge.NextItem == 1, "Reconnect lost a check or replayed an acknowledged item");
            }
            mailbox.SetWord(12, 0); mailbox.SetWord(16, 0); mailbox.SetWord(20, 0); mailbox.SetWord(24, 0);
            mailbox.SetWord(Protocol.Get("ack_sequence_offset"), 0); mailbox.SetWord(Protocol.Get("reserved_offset"), 0);
            using (var fixture = new ProtocolServerFixture(data.RootElement, location, item))
            using (var session = new APSessionManager(fixture.Uri, "Test", null, mailbox))
            using (var bridge = new ClientBridge(mailbox, session.Contract, Path.Combine(directory, "network"), session.Team, session.Slot))
            {
                Require(SpinWait.SpinUntil(() => session.ReceivedItems.Count == 1, 5000), "AP SDK did not receive item history");
                int offset = Protocol.Get("outgoing_offset");
                mailbox.SetWord(offset, 0); mailbox.SetWord(offset + 4, 0); mailbox.SetWord(offset + 8, location); mailbox.SetWord(offset + 12, 0); mailbox.SetWord(20, 1);
                bridge.Pump(session);
                Require(mailbox.InHead == 1 && Protocol.Read(ram.Read(Protocol.Get("incoming_offset") + 4, 4)) == item, "AP network item did not reach the mailbox");
                Require(fixture.Checks.Task.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult().Contains(location), "Mailbox check did not reach the AP socket");
            }
            // Precollected flags already applied to a fresh save must not block
            // the live item history or discard later rewards with the same ID.
            mailbox.SetWord(12, 0); mailbox.SetWord(16, 0); mailbox.SetWord(20, 0); mailbox.SetWord(24, 0);
            mailbox.SetWord(Protocol.Get("ack_sequence_offset"), 0); mailbox.SetWord(Protocol.Get("reserved_offset"), 0);
            var startNode = JsonNode.Parse(data.RootElement.GetRawText())!;
            startNode["starting_state"] = JsonSerializer.SerializeToNode(new { version = 1, logical_inventory = new Dictionary<string, int> { ["Tower"] = 1 } });
            startNode["starting_inventory"] = JsonSerializer.SerializeToNode(new Dictionary<string, int> { [unsupported.ToString()] = 1 });
            using var startData = JsonDocument.Parse(startNode.ToJsonString());
            var startContract = new SlotContract(startData.RootElement, mailbox, 1, "test", [location]);
            server.ReceivedItems = [new ReceivedItem(unsupported, -2), item, new ReceivedItem(unsupported, -2)];
            string startDirectory = Path.Combine(directory, "starting");
            using (var bridge = new ClientBridge(mailbox, startContract, startDirectory, 0, 1))
            {
                bridge.Pump(server);
                Require(bridge.NextItem == 1 && mailbox.InHead == 1 && Protocol.Read(ram.Read(Protocol.Get("incoming_offset"), 4)) == 2,
                    "Applied starting item blocked delivery or changed the received-item sequence");
                mailbox.SetWord(Protocol.Get("ack_sequence_offset"), 2); mailbox.SetWord(16, 1);
                bridge.Pump(server);
                Require(bridge.NextItem == 2 && bridge.BlockReason is not null, "Starting count limit discarded an additional precollected item");
            }
            using (var bridge = new ClientBridge(mailbox, startContract, startDirectory, 0, 1))
            {
                server.ReceivedItems = [new ReceivedItem(unsupported, -2), item, new ReceivedItem(unsupported, location)];
                bridge.Pump(server);
                Require(bridge.NextItem == 2 && mailbox.InHead == 1 && bridge.BlockReason is not null,
                    "Reconnect replayed defaults or discarded a chest reward with a starting item ID");
            }
            // Ring counters wrap unsigned; a full ring never overwrites its consumer.
            mailbox.SetWord(12, uint.MaxValue); mailbox.SetWord(16, uint.MaxValue);
            Require(mailbox.Enqueue(new IncomingItem(2, item, "Item_Ore_A", 1), uint.MaxValue) && mailbox.InHead == 0, "Counter wrap failed");
            mailbox.SetWord(12, 256); mailbox.SetWord(16, 0);
            Require(!mailbox.Enqueue(new IncomingItem(3, item, "Item_Ore_A", 1), 256), "Full ring overwritten");
            mailbox.SetWord(Protocol.Get("version_offset"), 1); Reject(() => mailbox.Validate());
            Console.WriteLine("PASS: shared wire format, identity checks, applied starting inventory, native acknowledgements, journal recovery, network failure, unsupported grants, queue capacity, counter wrap and real AP SDK WebSocket exchange");
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        finally { if (Directory.Exists(directory)) Directory.Delete(directory, recursive: true); }
    }
}
