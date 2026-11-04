using System.Text.Json;
using BotWClient.Memory;

namespace BotWClient.Archipelago;

public enum GrantKind { Actor, HeartContainer, StaminaVessel, WeaponSlot, BowSlot, ShieldSlot }
public readonly record struct ItemGrant(GrantKind Kind, string Name, uint Quantity);

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

    public static GrantKind? ProgressionGrant(string name) => name switch
    {
        "Heart Container" => GrantKind.HeartContainer,
        "Stamina Vessel" => GrantKind.StaminaVessel,
        "Weapon Slot" => GrantKind.WeaponSlot,
        "Bow Slot" => GrantKind.BowSlot,
        "Shield Slot" => GrantKind.ShieldSlot,
        _ => null,
    };

    public ItemGrant? ResolveGrant(long id, out string? reason)
    {
        reason = null;
        if (!items.TryGetValue(id, out var delivery)) throw new InvalidDataException($"No delivery mapping for AP item {id}");
        string kind = delivery.GetProperty("kind").GetString()!;
        if (kind is "progression" or "unimplemented" && delivery.TryGetProperty("name", out var nameElement))
        {
            string logicalName = nameElement.GetString()!;
            if (ProgressionGrant(logicalName) is { } progressionKind)
            {
                if (delivery.TryGetProperty("quantity", out var progQty) && progQty.GetUInt32() != 1)
                    throw new ArgumentException("Invalid progression quantity");
                if ((mailbox.Word(Protocol.Get("capabilities_offset")) & Protocol.Capability("progression")) == 0)
                {
                    reason = $"{logicalName} requires the updated progression hook; restart Cemu with the updated graphic pack";
                    return null;
                }
                return new ItemGrant(progressionKind, logicalName, 1);
            }
        }
        if (kind != "actor")
        {
            reason = $"AP item {id} ({delivery.GetProperty("name").GetString()}) requires an unimplemented native grant; delivery remains pending";
            return null;
        }
        string actor = delivery.GetProperty("actor").GetString()!;
        uint quantity = delivery.TryGetProperty("quantity", out var quantityElement) ? quantityElement.GetUInt32() : 1;
        Protocol.ValidateActorName(actor, quantity);
        return new ItemGrant(GrantKind.Actor, actor, quantity);
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
    public uint LastRpcSeq { get; set; }
    public int NextItem { get; set; }
    public Flight? InFlight { get; set; }
    public HashSet<long> Checks { get; set; } = [];
    public Dictionary<long, int> StartingAcknowledged { get; set; } = [];
}

public sealed class Flight
{
    public int Index { get; set; }
    public long ItemId { get; set; }
    public string Stage { get; set; } = "Init";
    public uint PendingHead { get; set; }
    public RpcCall[]? PendingCalls { get; set; }
    public int PouchType { get; set; } = -1;
    public uint WeaponValue { get; set; }
    public uint RemainingQuantity { get; set; }
    public uint BeforeSum { get; set; }
    public uint BeforeCount { get; set; }
    public bool AlreadyOwnedKeyItem { get; set; }
    public bool SetterCalled { get; set; }
    public int TargetInt { get; set; }
    public float TargetFloat { get; set; }
    public string? LastError { get; set; }
}

public sealed class ClientBridge : IDisposable
{
    private readonly Mailbox mailbox;
    private readonly SlotContract contract;
    private readonly string path;
    private readonly FileStream lease;
    private readonly Action<string>? log;
    private readonly JournalState state;
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
            log?.Invoke($"Journal ready: {path}; epoch={epoch}, next_item={state.NextItem}, checks={state.Checks.Count}, in_flight={state.InFlight?.Stage ?? "none"}");
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

    private static (uint HandleAddr, int Delta, int Cap) ProgressionSpec(GrantKind kind) => kind switch
    {
        GrantKind.HeartContainer => (GameOffsets.MaxHeartValueHandle, 4, 120),
        GrantKind.WeaponSlot => (GameOffsets.WeaponPorchStockHandle, 1, 20),
        GrantKind.BowSlot => (GameOffsets.BowPorchStockHandle, 1, 14),
        GrantKind.ShieldSlot => (GameOffsets.ShieldPorchStockHandle, 1, 20),
        _ => throw new ArgumentOutOfRangeException(nameof(kind)),
    };

    private RpcCall NextCall(uint address, uint r3 = 0, uint r4 = 0, uint r5 = 0, uint r6 = 0,
        uint r7 = 0, uint r8 = 0, uint r9 = 0, uint r10 = 0, float f1 = 0f)
    {
        uint seq = unchecked(state.LastRpcSeq + 1);
        if (seq == 0) seq = 1;
        state.LastRpcSeq = seq;
        return new RpcCall(seq, address, r3, r4, r5, r6, r7, r8, r9, r10, f1);
    }

    private void QueueRpc(Flight flight, string stage, RpcCall[] calls)
    {
        if (mailbox.InHead != mailbox.InTail) throw new InvalidDataException("Incoming mailbox contains an item from another producer");
        flight.Stage = stage;
        flight.PendingHead = mailbox.InHead;
        flight.PendingCalls = calls;
        Save();
        if (!mailbox.EnqueueBatch(calls, flight.PendingHead)) throw new InvalidDataException("Incoming producer head changed");
    }

    private void CompleteFlight(Flight flight)
    {
        state.NextItem++;
        state.InFlight = null;
        Save();
        log?.Invoke($"Native item acknowledged: item={flight.ItemId}, next_item={state.NextItem}");
    }

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
            checksDirty = false;
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
            if (flight.Index != state.NextItem || received[flight.Index].ItemId != flight.ItemId)
                throw new InvalidDataException("Received item history disagrees with the pending journal entry");
            var grantOpt = contract.ResolveGrant(flight.ItemId, out var flightReason);
            if (grantOpt is null) { BlockReason = flightReason; return; }
            if (!AdvanceFlight(flight, grantOpt.Value)) return;
        }
        if (state.NextItem >= received.Count) return;
        if (mailbox.InHead != mailbox.InTail) throw new InvalidDataException("Incoming mailbox contains an item from another producer");
        if (mailbox.Status != 2 || mailbox.GuestAddress == 0) { BlockReason = "Waiting for active gameplay"; return; }
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
        long id = received[state.NextItem].ItemId;
        var next = contract.ResolveGrant(id, out var blocked);
        if (next is null) { BlockReason = blocked; return; }
        var started = new Flight { Index = state.NextItem, ItemId = id, RemainingQuantity = next.Value.Quantity };
        state.InFlight = started;
        Save();
        log?.Invoke($"Starting RPC grant: item={id}, kind={next.Value.Kind}, name={next.Value.Name}, quantity={next.Value.Quantity}");
        AdvanceFlight(started, next.Value);
    }

    private bool AdvanceFlight(Flight flight, ItemGrant grant)
    {
        if (flight.PendingCalls is { Length: > 0 } pending)
        {
            uint expectedEnd = unchecked(flight.PendingHead + (uint)pending.Length);
            if (mailbox.InHead == flight.PendingHead && mailbox.InTail == flight.PendingHead)
            {
                if (grant.Kind == GrantKind.Actor) mailbox.WriteSafeString(grant.Name);
                if (!mailbox.EnqueueBatch(pending, flight.PendingHead)) throw new InvalidDataException("Incoming producer head changed");
                log?.Invoke($"Republished journaled RPC batch: item={flight.ItemId}, stage={flight.Stage}");
                BlockReason = flight.SetterCalled ? "Waiting for saved progression" : flight.LastError;
                return false;
            }
            if (mailbox.InHead != expectedEnd || unchecked(expectedEnd - mailbox.InTail) > (uint)pending.Length)
                throw new InvalidDataException("Mailbox reset or changed during an outstanding grant; manual recovery is required to avoid duplicate delivery");
            if (mailbox.InTail != expectedEnd)
            {
                BlockReason = flight.SetterCalled ? "Waiting for saved progression" : flight.LastError;
                return false;
            }
            if (mailbox.AckSequence != pending[^1].SeqId)
                throw new InvalidDataException("RPC acknowledgement sequence mismatch");
            uint completedHead = flight.PendingHead;
            flight.PendingCalls = null;
            switch (flight.Stage)
            {
                case "Classify":
                    int pouchType = unchecked((int)mailbox.ReadResult(completedHead).R3);
                    if (pouchType < 0)
                    {
                        flight.Stage = "Init";
                        flight.LastError = $"Native grant blocked: invalid actor {grant.Name}";
                        Save();
                        BlockReason = flight.LastError;
                        return false;
                    }
                    flight.PouchType = pouchType;
                    flight.Stage = pouchType is 0 or 1 or 3 ? "Durability" : "QueueAdd";
                    break;
                case "Durability":
                    flight.WeaponValue = mailbox.ReadResult(completedHead).R3;
                    flight.Stage = "QueueAdd";
                    break;
                case "VerifyAdd":
                    if (flight.AlreadyOwnedKeyItem) { CompleteFlight(flight); return true; }
                    if (mailbox.Status != 2 || mailbox.GuestAddress == 0)
                    {
                        flight.Stage = "QueueAdd"; Save();
                        BlockReason = "Waiting for active gameplay";
                        return false;
                    }
                    uint mgrAfter = mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr);
                    if (mgrAfter == 0)
                    {
                        flight.Stage = "QueueAdd"; Save();
                        BlockReason = "Waiting for PauseMenuDataMgr";
                        return false;
                    }
                    var (afterSum, afterCount) = mailbox.MeasureStablePouch(mgrAfter, grant.Name);
                    if (afterCount <= flight.BeforeCount && afterSum <= flight.BeforeSum)
                    {
                        flight.Stage = "QueueAdd";
                        flight.LastError = $"Native grant pending: pouch unchanged or full for {grant.Name}";
                        Save();
                        BlockReason = flight.LastError;
                        return false;
                    }
                    flight.LastError = null;
                    if (flight.PouchType is 2 or 7 or 8)
                    {
                        uint added = unchecked(afterSum - flight.BeforeSum);
                        if (added < flight.RemainingQuantity)
                        {
                            flight.RemainingQuantity -= added;
                            flight.Stage = "QueueAdd";
                            break;
                        }
                    }
                    CompleteFlight(flight);
                    return true;
                case "ReadInitial":
                    if (grant.Kind == GrantKind.StaminaVessel)
                    {
                        float current = mailbox.ReadResult(completedHead).F1;
                        if (current < 1000f)
                        {
                            flight.Stage = "Init"; Save();
                            BlockReason = "Waiting for GameData defaults";
                            return false;
                        }
                        if (current >= 3000f) { CompleteFlight(flight); return true; }
                        flight.TargetFloat = Math.Min(current + 200f, 3000f);
                        flight.Stage = "SendSetter";
                    }
                    else
                    {
                        int current = unchecked((int)mailbox.ReadResult(completedHead).R3);
                        if (current < 1)
                        {
                            flight.Stage = "Init"; Save();
                            BlockReason = "Waiting for GameData defaults";
                            return false;
                        }
                        var (_, delta, cap) = ProgressionSpec(grant.Kind);
                        if (current >= cap) { CompleteFlight(flight); return true; }
                        flight.TargetInt = Math.Min(current + delta, cap);
                        flight.Stage = "SendSetter";
                    }
                    break;
                case "WaitSetter":
                    flight.Stage = "PollTarget";
                    break;
                case "VerifyTarget":
                    bool reached = grant.Kind == GrantKind.StaminaVessel
                        ? mailbox.ReadResult(completedHead).F1 >= flight.TargetFloat
                        : unchecked((int)mailbox.ReadResult(completedHead).R3) >= flight.TargetInt;
                    if (reached) { CompleteFlight(flight); return true; }
                    flight.Stage = "PollTarget";
                    break;
                default:
                    throw new InvalidDataException($"Unknown journal RPC stage {flight.Stage}");
            }
        }

        if (mailbox.Status != 2 || mailbox.GuestAddress == 0)
        {
            if (!flight.SetterCalled && flight.Stage == "SendSetter") flight.Stage = "Init";
            Save();
            BlockReason = "Waiting for active gameplay";
            return false;
        }

        if (grant.Kind == GrantKind.Actor)
        {
            uint mgr = mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr);
            if (mgr == 0) { Save(); BlockReason = "Waiting for PauseMenuDataMgr"; return false; }
            switch (flight.Stage)
            {
                case "Init":
                {
                    uint safeStr = mailbox.WriteSafeString(grant.Name);
                    QueueRpc(flight, "Classify", [NextCall(GameOffsets.GetPouchItemType, r3: safeStr, r4: 0)]);
                    BlockReason = flight.LastError;
                    return false;
                }
                case "Durability":
                {
                    uint safeStr = mailbox.WriteSafeString(grant.Name);
                    QueueRpc(flight, "Durability", [NextCall(GameOffsets.GetWeaponMaxValue, r3: safeStr)]);
                    BlockReason = flight.LastError;
                    return false;
                }
                case "QueueAdd":
                {
                    var (beforeSum, beforeCount) = mailbox.MeasureStablePouch(mgr, grant.Name);
                    flight.BeforeSum = beforeSum;
                    flight.BeforeCount = beforeCount;
                    if (flight.PouchType == 9 && beforeCount != 0)
                    {
                        flight.AlreadyOwnedKeyItem = true;
                        QueueRpc(flight, "VerifyAdd", [
                            NextCall(GameOffsets.LockCritSection, r3: unchecked(mgr + GameOffsets.PauseMenuCritSectionOffset)),
                            NextCall(GameOffsets.PauseMenuSaveToGameData, r3: mgr, r4: unchecked(mgr + GameOffsets.PauseMenuItemListOffset)),
                            NextCall(GameOffsets.UnlockCritSection, r3: unchecked(mgr + GameOffsets.PauseMenuCritSectionOffset)),
                        ]);
                        BlockReason = flight.LastError;
                        return false;
                    }
                    flight.AlreadyOwnedKeyItem = false;
                    uint safeStr = mailbox.WriteSafeString(grant.Name);
                    uint value = flight.PouchType is 0 or 1 or 3 ? flight.WeaponValue : flight.RemainingQuantity;
                    var calls = new List<RpcCall>(5)
                    {
                        NextCall(GameOffsets.LockCritSection, r3: unchecked(mgr + GameOffsets.PauseMenuCritSectionOffset)),
                        NextCall(GameOffsets.PauseMenuAddItem, r3: mgr, r4: safeStr, r5: (uint)flight.PouchType,
                            r6: unchecked(mgr + GameOffsets.PauseMenuItemListOffset), r7: value),
                    };
                    if (flight.PouchType == 8) calls.Add(NextCall(GameOffsets.PauseMenuPostAddFood, r3: mgr, r4: safeStr));
                    calls.Add(NextCall(GameOffsets.PauseMenuSaveToGameData, r3: mgr, r4: unchecked(mgr + GameOffsets.PauseMenuItemListOffset)));
                    calls.Add(NextCall(GameOffsets.UnlockCritSection, r3: unchecked(mgr + GameOffsets.PauseMenuCritSectionOffset)));
                    QueueRpc(flight, "VerifyAdd", calls.ToArray());
                    BlockReason = flight.LastError;
                    return false;
                }
                default:
                    throw new InvalidDataException($"Unexpected actor grant stage {flight.Stage}");
            }
        }
        else
        {
            uint gdtMgr = mailbox.ReadGuestWord(GameOffsets.GdtManagerPtr);
            if (gdtMgr == 0)
            {
                if (!flight.SetterCalled) flight.Stage = "Init";
                Save();
                BlockReason = "Waiting for GameData manager";
                return false;
            }
            uint playerInfo = 0;
            if (grant.Kind is GrantKind.HeartContainer or GrantKind.StaminaVessel)
            {
                playerInfo = mailbox.ReadGuestWord(GameOffsets.PlayerInfoPtr);
                if (playerInfo == 0 || mailbox.ReadGuestWord(unchecked(playerInfo + GameOffsets.PlayerInfoActorOffset)) == 0)
                {
                    if (!flight.SetterCalled) flight.Stage = "Init";
                    Save();
                    BlockReason = "Waiting for live player";
                    return false;
                }
            }
            int handle = 0;
            if (grant.Kind != GrantKind.StaminaVessel)
            {
                var (handleAddr, _, _) = ProgressionSpec(grant.Kind);
                handle = unchecked((int)mailbox.ReadGuestWord(handleAddr));
                if (handle == -1)
                {
                    if (!flight.SetterCalled) flight.Stage = "Init";
                    Save();
                    BlockReason = "Waiting for GameData flag handles";
                    return false;
                }
            }
            switch (flight.Stage)
            {
                case "Init":
                    QueueRpc(flight, "ReadInitial", [
                        grant.Kind == GrantKind.StaminaVessel
                            ? NextCall(GameOffsets.GdtGetFlagStaminaMax, r3: 0)
                            : NextCall(GameOffsets.GdtGetS32, r3: (uint)handle, r4: 0)
                    ]);
                    return false;
                case "SendSetter":
                    flight.SetterCalled = true;
                    RpcCall[] setters = grant.Kind switch
                    {
                        GrantKind.StaminaVessel => [
                            NextCall(GameOffsets.PlayerInfoSetStaminaMax, r3: playerInfo, f1: flight.TargetFloat),
                            NextCall(GameOffsets.PlayerInfoSetActorStaminaMax, r3: playerInfo, f1: flight.TargetFloat),
                        ],
                        GrantKind.HeartContainer => [
                            NextCall(GameOffsets.PlayerInfoSetMaxHeartValue, r3: playerInfo, r4: (uint)flight.TargetInt),
                        ],
                        _ => [
                            NextCall(GameOffsets.GdtSetS32, r3: (uint)flight.TargetInt, r4: (uint)handle, r5: 0),
                        ],
                    };
                    QueueRpc(flight, "WaitSetter", setters);
                    BlockReason = "Waiting for saved progression";
                    return false;
                case "PollTarget":
                    QueueRpc(flight, "VerifyTarget", [
                        grant.Kind == GrantKind.StaminaVessel
                            ? NextCall(GameOffsets.GdtGetFlagStaminaMax, r3: 0)
                            : NextCall(GameOffsets.GdtGetS32, r3: (uint)handle, r4: 0)
                    ]);
                    BlockReason = "Waiting for saved progression";
                    return false;
                default:
                    throw new InvalidDataException($"Unexpected progression grant stage {flight.Stage}");
            }
        }
    }

    public void Dispose() => lease.Dispose();
}
