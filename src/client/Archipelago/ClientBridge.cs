using System.Text.Json;
using BotWClient.Memory;

namespace BotWClient.Archipelago;

public sealed class SlotContract
{
    public string Fingerprint { get; }
    public HashSet<long> Locations { get; } = [];
    public Dictionary<long, int> StartingInventory { get; } = [];
    private readonly Dictionary<long, JsonElement> items = [];
    private readonly Mailbox mailbox;
    public SlotContract(JsonElement data, Mailbox mailbox, int slot, string seed, IEnumerable<long> serverLocations)
    {
        this.mailbox = mailbox;
        if (data.GetProperty("protocol_version").GetInt32() != Protocol.Get("version") ||
            data.GetProperty("check_actor_prefix").GetString() != "AP_Check_" ||
            data.GetProperty("player").GetInt32() != slot || data.GetProperty("seed").GetString() != seed)
            throw new InvalidDataException("AP slot data does not match the client protocol or logged-in player/seed");
        Fingerprint = data.GetProperty("seed_fingerprint").GetString()!;
        if (Fingerprint.Length != 32 || Fingerprint != mailbox.Fingerprint)
            throw new InvalidDataException("The Cemu graphic pack belongs to a different seed/player");
        foreach (var location in data.GetProperty("locations").EnumerateObject())
        {
            uint id = uint.Parse(location.Name);
            if (id == 0 || location.Value.GetString() != $"AP_Check_{id:X8}") throw new InvalidDataException("Invalid check actor mapping");
            Locations.Add(id);
        }
        if (!Locations.SetEquals(mailbox.Validate()) || !Locations.SetEquals(serverLocations))
            throw new InvalidDataException("Server, slot data, and hook location tables disagree");
        foreach (var item in data.GetProperty("items").EnumerateObject()) items.Add(long.Parse(item.Name), item.Value.Clone());
        if (data.TryGetProperty("starting_state", out var start))
        {
            if (start.GetProperty("version").GetInt32() != 1)
                throw new InvalidDataException("Unsupported starting-state profile");
            var logical = start.GetProperty("logical_inventory");
            var appliedNames = new HashSet<string>();
            foreach (var item in data.GetProperty("starting_inventory").EnumerateObject())
            {
                long id = long.Parse(item.Name); int count = item.Value.GetInt32();
                if (!items.ContainsKey(id) || count < 1 || count > 32)
                    throw new InvalidDataException("Invalid applied starting inventory");
                var mapping = items[id];
                string? name = mapping.GetProperty("kind").GetString() == "actor"
                    ? mapping.GetProperty("actor").GetString() == "PlayerStole2" ? "Paraglider" : null
                    : mapping.GetProperty("name").GetString();
                if (name is null || !logical.TryGetProperty(name, out var expected) || expected.GetInt32() != count || !appliedNames.Add(name))
                    throw new InvalidDataException("Applied starting inventory disagrees with the starting-state profile");
                StartingInventory.Add(id, count);
            }
            if (!appliedNames.SetEquals(logical.EnumerateObject().Select(item => item.Name)))
                throw new InvalidDataException("Starting inventory is missing an applied default");
        }
    }
    public IncomingItem? Delivery(long id, uint sequence, out string? reason)
    {
        reason = null;
        if (!items.TryGetValue(id, out var delivery)) throw new InvalidDataException($"No delivery mapping for AP item {id}");
        string kind = delivery.GetProperty("kind").GetString()!;
        // Existing servers advertise these five items as unimplemented. Upgrade
        // their exact logical names only when the running hook supports them.
        if (kind is "progression" or "unimplemented" && delivery.TryGetProperty("name", out var name))
        {
            uint command = Protocol.ProgressionCommand(name.GetString()!);
            if (command != 0)
            {
                if ((mailbox.Word(Protocol.Get("capabilities_offset")) & Protocol.Capability("progression")) == 0)
                {
                    reason = $"{name.GetString()} requires the updated progression hook; restart Cemu with the updated graphic pack";
                    return null;
                }
                var grant = new IncomingItem(sequence, checked((uint)id), name.GetString()!, 1, command);
                Protocol.Encode(grant); return grant;
            }
        }
        if (kind != "actor")
        {
            reason = $"AP item {id} ({delivery.GetProperty("name").GetString()}) requires an unimplemented native grant; delivery remains pending";
            return null;
        }
        var item = new IncomingItem(sequence, checked((uint)id), delivery.GetProperty("actor").GetString()!,
            delivery.TryGetProperty("quantity", out var quantity) ? quantity.GetUInt32() : 1);
        Protocol.Encode(item); return item;
    }
}

public interface IServerLink
{
    bool Connected { get; }
    IReadOnlyList<ReceivedItem> ReceivedItems { get; }
    void SendChecks(long[] ids);
}
public readonly record struct ReceivedItem(long ItemId, long LocationId)
{
    public static implicit operator ReceivedItem(long id) => new(id, 0);
}

public sealed class JournalState
{
    public uint MailboxEpoch { get; set; }
    public int NextItem { get; set; }
    public Flight? InFlight { get; set; }
    public HashSet<long> Checks { get; set; } = [];
    public Dictionary<long, int> StartingAcknowledged { get; set; } = [];
}
public sealed record Flight(int Index, long ItemId, uint Head, uint Sequence);

// A durable journal takes ownership of checks before freeing the hook's outgoing ring.
// One item is in flight at a time; only the native acknowledgement advances the AP history index.
public sealed class ClientBridge : IDisposable
{
    private readonly Mailbox mailbox;
    private readonly SlotContract contract;
    private readonly string path;
    private readonly FileStream lease;
    private readonly Action<string>? log;
    private JournalState state;
    private bool checksDirty = true;
    public string? BlockReason { get; private set; }
    public int NextItem => state.NextItem;
    public ClientBridge(Mailbox mailbox, SlotContract contract, string directory, int team, int slot, Action<string>? log = null)
    {
        this.log = log;
        this.mailbox = mailbox; this.contract = contract;
        Directory.CreateDirectory(directory);
        path = Path.Combine(directory, $"{contract.Fingerprint}-T{team}-P{slot}.json");
        lease = new FileStream(path + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        try
        {
            state = File.Exists(path) ? JsonSerializer.Deserialize<JournalState>(File.ReadAllText(path))! : new JournalState();
            if (state.NextItem < 0 || !state.Checks.IsSubsetOf(contract.Locations)) throw new InvalidDataException("Invalid client journal");
            if (state.StartingAcknowledged.Any(pair => pair.Value < 0 ||
                    pair.Value > contract.StartingInventory.GetValueOrDefault(pair.Key)))
                throw new InvalidDataException("Client journal exceeds the statically applied starting inventory");
            if (!File.Exists(path) && (mailbox.InHead != 0 || mailbox.InTail != 0 || mailbox.AckSequence != 0))
                throw new InvalidDataException("This running mailbox already delivered items, but its client journal is missing");
            uint epoch = mailbox.Word(Protocol.Get("reserved_offset"));
            if (state.InFlight is not null && (epoch == 0 || state.MailboxEpoch != epoch))
                throw new InvalidDataException("Cemu restarted during an outstanding grant; reconcile the save and journal before resuming");
            if (epoch == 0)
            {
                epoch = (uint)System.Security.Cryptography.RandomNumberGenerator.GetInt32(1, int.MaxValue);
                mailbox.SetWord(Protocol.Get("reserved_offset"), epoch);
            }
            state.MailboxEpoch = epoch; Save();
            log?.Invoke($"Journal ready: {path}; epoch={epoch}, next_item={state.NextItem}, checks={state.Checks.Count}, in_flight={state.InFlight?.ToString() ?? "none"}");
        }
        catch { lease.Dispose(); throw; }
    }
    private void Save()
    {
        string temporary = path + ".tmp";
        using (var stream = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            JsonSerializer.Serialize(stream, state); stream.Flush(flushToDisk: true);
        }
        File.Move(temporary, path, overwrite: true);
    }
    public void Reconnected() { checksDirty = true; log?.Invoke($"AP reconnected; replaying {state.Checks.Count} journaled checks, next_item={state.NextItem}."); }
    public void Pump(IServerLink server)
    {
        if (mailbox.Word(Protocol.Get("reserved_offset")) != state.MailboxEpoch)
            throw new InvalidDataException("The running mailbox was reset; reconnect after loading the correct save");
        BlockReason = null;
        while (mailbox.PeekCheck() is { } check)
        {
            if (check.IsShop != 0 || check.ApLocationId > uint.MaxValue || !contract.Locations.Contains((long)check.ApLocationId))
                throw new InvalidDataException("Hook reported a check absent from this seed's chest table");
            state.Checks.Add((long)check.ApLocationId); Save(); checksDirty = true;
            mailbox.AcknowledgeCheck(check.SeqId);
            log?.Invoke($"Hook check journaled and acknowledged: location={check.ApLocationId}, sequence={check.SeqId}, server_connected={server.Connected}");
        }
        if (server.Connected && checksDirty)
        {
            if (state.Checks.Count != 0) server.SendChecks(state.Checks.Order().ToArray());
            checksDirty = false; // Journal retains every check and resends them after each login.
        }
        if (!server.Connected) return;
        var received = server.ReceivedItems;
        if (state.InFlight is { } flight)
        {
            if (flight.Index >= received.Count)
            {
                BlockReason = "Waiting for AP to replay the received-item history";
                return;
            }
            if (flight.Index != state.NextItem || flight.Sequence != checked((uint)flight.Index + 1) ||
                received[flight.Index].ItemId != flight.ItemId)
                throw new InvalidDataException("Received item history disagrees with the pending journal entry");
            uint after = unchecked(flight.Head + 1);
            if (mailbox.InTail == after && mailbox.AckSequence == flight.Sequence)
            {
                state.NextItem++; state.InFlight = null; Save();
                log?.Invoke($"Native item acknowledged: item={flight.ItemId}, sequence={flight.Sequence}, next_item={state.NextItem}");
            }
            else if (mailbox.InHead == flight.Head && mailbox.InTail == flight.Head)
            {
                // Intent was saved, but the producer head was never published.
                var item = contract.Delivery(flight.ItemId, flight.Sequence, out var reason);
                if (item is null) { BlockReason = reason; return; }
                mailbox.Enqueue(item.Value, flight.Head); log?.Invoke($"Republished journaled item={flight.ItemId}, sequence={flight.Sequence}"); return;
            }
            else if (mailbox.InHead == after && mailbox.InTail == flight.Head)
            {
                uint error = mailbox.DeliveryError;
                if (error != 0) BlockReason = $"Native grant pending (hook error {error}: 1 invalid actor, 2 unsupported command, 3 not ready, 4 pouch unchanged/full, 5 waiting for saved progression)";
                return;
            }
            else throw new InvalidDataException("Mailbox reset or changed during an outstanding grant; manual recovery is required to avoid duplicate delivery");
        }
        if (state.NextItem >= received.Count) return;
        if (mailbox.InHead != mailbox.InTail) throw new InvalidDataException("Incoming mailbox contains an item from another producer");
        if (mailbox.Word(8) != 2) { BlockReason = "Waiting for active gameplay"; return; }
        // AP reserves location -2 for precollected inventory. Only acknowledge
        // the exact counts already initialized by this seed's static pack.
        // An ordinary reward with the same item ID must still use native delivery.
        while (state.NextItem < received.Count)
        {
            var receipt = received[state.NextItem];
            int applied = state.StartingAcknowledged.GetValueOrDefault(receipt.ItemId);
            if (receipt.LocationId != -2 || applied >= contract.StartingInventory.GetValueOrDefault(receipt.ItemId)) break;
            state.StartingAcknowledged[receipt.ItemId] = applied + 1;
            state.NextItem++; Save();
            log?.Invoke($"Acknowledged statically applied starting item={receipt.ItemId}, count={applied + 1}, next_item={state.NextItem}");
        }
        if (state.NextItem >= received.Count) return;
        uint sequence = checked((uint)state.NextItem + 1);
        long id = received[state.NextItem].ItemId;
        var next = contract.Delivery(id, sequence, out var blocked);
        if (next is null) { BlockReason = blocked; return; }
        state.InFlight = new Flight(state.NextItem, id, mailbox.InHead, sequence); Save();
        if (!mailbox.Enqueue(next.Value, state.InFlight.Head)) throw new InvalidDataException("Incoming producer head changed");
        log?.Invoke($"Queued native delivery: item={id}, sequence={sequence}, command={next.Value.Flags}, item_name={next.Value.ActorName}; awaiting hook acknowledgement.");
    }
    public void Dispose() => lease.Dispose();
}
