using System.Text.Json;
using BotWClient.Memory;

namespace BotWClient.Archipelago;

public sealed record NativeFlag(string Name, string Type, int Value, bool EventOnly = false);
public sealed record NativeTier(NativeFlag[] Writes, string? Actor, string? RemoveActor = null);
public sealed record NativeProfile(NativeTier[] Tiers, string? Refresh = null);

public static class NativeGrants
{
    public static readonly IReadOnlyDictionary<string, NativeProfile> Profiles =
        JsonSerializer.Deserialize<Dictionary<string, NativeProfile>>(
            typeof(NativeGrants).Assembly.GetManifestResourceStream("BotWClient.native_grants.json")!)!;
}

public sealed partial class ClientBridge
{
    private bool AdvanceNative(Flight flight, ItemGrant grant)
    {
        var profile = NativeGrants.Profiles[grant.Name];
        if (flight.NativeActorPending)
        {
            AdvanceFlight(flight, new ItemGrant(GrantKind.Actor, profile.Tiers[flight.NativeTier].Actor!, 1));
            return false;
        }
        if (flight.PendingCalls is { Length: > 0 } pending)
        {
            uint end = unchecked(flight.PendingHead + (uint)pending.Length);
            if (mailbox.InHead == flight.PendingHead && mailbox.InTail == flight.PendingHead)
            {
                if (flight.Stage == "NativeRemove") PrepareRemovalString(RemovalActor(flight, profile)!);
                else if (flight.Stage != "NativeRefresh") PrepareNativeString(flight, profile);
                if (!mailbox.EnqueueBatch(pending, flight.PendingHead)) throw new InvalidDataException("Incoming producer head changed");
                return false;
            }
            if (mailbox.InTail != end) return false;
            if (mailbox.AckSequence != pending[^1].SeqId) throw new InvalidDataException("Native grant acknowledgement mismatch");
            uint slot = flight.PendingHead;
            flight.PendingCalls = null;
            if (flight.Stage is "NativeScan" or "NativeVerify")
            {
                if (mailbox.ReadResult(slot).R3 == 0)
                {
                    flight.Stage = flight.Stage == "NativeScan" ? "NativeReadTier" : "NativeReadBack";
                    Save(); BlockReason = "Waiting for native flag " + CurrentNativeFlag(flight, profile).Name;
                    return false;
                }
                var flag = CurrentNativeFlag(flight, profile);
                uint value = mailbox.ReadGuestWord(mailbox.ScratchResultAddress);
                bool owned = flag.Type == "bool" ? value != 0 : unchecked((int)value) >= flag.Value;
                if (flight.Stage == "NativeScan")
                {
                    if (owned)
                    {
                        flight.NativeTier++;
                        flight.Stage = "NativeReadTier";
                    }
                    else
                    {
                        // Persist the selected tier before any mutations. A partial tier must
                        // resume here rather than selecting the next upgrade after reconnect.
                        flight.NativeTierSelected = true;
                        flight.NativeWrite = 0;
                        flight.Stage = "NativeActor";
                    }
                }
                else if (owned)
                {
                    flight.NativeWrite++;
                    flight.Stage = "NativeWrite";
                }
                else flight.Stage = "NativeWrite";
            }
            else if (flight.Stage == "NativeSet")
            {
                if (CurrentNativeFlag(flight, profile) is { Type: "bool", EventOnly: false } && mailbox.ReadResult(slot).R3 == 0)
                {
                    flight.Stage = "NativeWrite";
                    Save(); BlockReason = "Native flag setter refused " + CurrentNativeFlag(flight, profile).Name;
                    return false;
                }
                flight.Stage = "NativeReadBack";
            }
            else if (flight.Stage == "NativeRemove")
            {
                // The native function returns void. Verify the actual pouch on
                // the next active tick instead of interpreting a return register.
                flight.Stage = "NativeRemoveVerify";
            }
            else if (flight.Stage == "NativeRefresh")
            {
                CompleteFlight(flight);
                return true;
            }
            else throw new InvalidDataException("Unknown native grant stage " + flight.Stage);
            Save();
        }
        if (mailbox.Status != 2 || mailbox.GuestAddress == 0)
        {
            BlockReason = "Waiting for active gameplay";
            return false;
        }
        if (flight.Stage == "NativeRemoveVerify") return FinishNative(flight, profile);
        if (flight.Stage == "Init") { flight.Stage = "NativeReadTier"; Save(); }
        if (flight.Stage == "NativeReadTier" && flight.NativeTier == profile.Tiers.Length)
        {
            return FinishNative(flight, profile);
        }
        var tier = profile.Tiers[flight.NativeTier];
        if (flight.Stage == "NativeActor")
        {
            if (tier.Actor is { } actor)
            {
                flight.NativeActorPending = true;
                flight.RemainingQuantity = 1;
                flight.PouchType = -1;
                flight.Stage = "Init";
                Save();
                AdvanceFlight(flight, new ItemGrant(GrantKind.Actor, actor, 1));
                return false;
            }
            flight.Stage = "NativeWrite";
        }
        if (flight.Stage == "NativeActorDone") flight.Stage = "NativeWrite";
        if (flight.Stage == "NativeWrite" && flight.NativeWrite == tier.Writes.Length)
        {
            return FinishNative(flight, profile);
        }
        uint manager = mailbox.ReadGuestWord(GameOffsets.GdtManagerPtr);
        if (manager == 0) { Save(); BlockReason = "Waiting for GameData manager"; return false; }
        var current = CurrentNativeFlag(flight, profile);
        uint name = PrepareNativeString(flight, profile);
        if (flight.Stage is "NativeReadTier" or "NativeReadBack")
        {
            uint core = mailbox.GameDataCore(manager, 0x700);
            if (core == 0) { Save(); BlockReason = "Waiting for GameData core"; return false; }
            uint flags = mailbox.ReadGuestWord(manager + 0x704) >> 24;
            QueueRpc(flight, flight.Stage == "NativeReadTier" ? "NativeScan" : "NativeVerify", [
                NextCall(current.Type == "bool" ? GameOffsets.GdtGetBoolByName : GameOffsets.GdtGetS32ByName,
                    r3: core, r4: mailbox.ScratchResultAddress, r5: name, r6: flags, r7: 1)]);
        }
        else if (flight.Stage == "NativeWrite")
        {
            if (current.EventOnly)
            {
                uint core = mailbox.GameDataCore(manager, 0x70C);
                if (core == 0) { Save(); BlockReason = "Waiting for writable GameData core"; return false; }
                // Event-only tower flags require the native event permission path.
                // flags=0 bypasses program-write restrictions; force=0 preserves latches.
                uint target = current.Type == "bool" ? GameOffsets.GdtSetBoolTyped : GameOffsets.GdtSetS32Typed;
                var writes = new List<RpcCall> {
                    NextCall(target, r3: core, r4: unchecked((uint)current.Value), r5: name, r6: 0, r7: 1, r8: 0)
                };
                // Match the manager setter's mirrored-core write when enabled.
                bool mirror = ((mailbox.ReadGuestWord(manager + 0x714) >> 16) & 0xFF) != 0;
                if (mirror)
                {
                    uint second = mailbox.GameDataCore(manager, 0x710);
                    if (second == 0) { Save(); BlockReason = "Waiting for mirrored GameData core"; return false; }
                    writes.Add(NextCall(target, r3: second, r4: unchecked((uint)current.Value), r5: name, r6: 0, r7: 1, r8: 0));
                }
                QueueRpc(flight, "NativeSet", writes.ToArray());
                return false;
            }
            QueueRpc(flight, "NativeSet", [NextCall(
                current.Type == "bool" ? GameOffsets.GdtSetBoolByName : GameOffsets.GdtSetS32ByName,
                r3: manager, r4: unchecked((uint)current.Value), r5: name)]);
        }
        else throw new InvalidDataException("Unexpected native grant stage " + flight.Stage);
        return false;
    }

    private bool FinishNative(Flight flight, NativeProfile profile)
    {
        if (RemovalActor(flight, profile) is { } remove)
        {
            uint mgr = mailbox.ReadGuestWord(GameOffsets.PauseMenuDataMgrPtr);
            if (mgr == 0) { Save(); BlockReason = "Waiting for PauseMenuDataMgr"; return false; }
            if (mailbox.MeasureStablePouch(mgr, remove).Count != 0)
            {
                uint name = PrepareRemovalString(remove);
                // Copied from the native delete-item caller at 0x02152650:
                // mgr, SafeString*, negative count, bool* allowEquipped, null.
                // The callee takes its own lock, saves and rebuilds the pouch.
                QueueRpc(flight, "NativeRemove", [NextCall(GameOffsets.PauseMenuChangeItem,
                    r3: mgr, r4: name, r5: uint.MaxValue,
                    r6: mailbox.ScratchResultAddress + 4, r7: 0)]);
                BlockReason = "Waiting for base champion item removal";
                return false;
            }
        }
        if (profile.Refresh == "map")
        {
            uint map = mailbox.ReadGuestWord(GameOffsets.MapManagerPtr);
            if (map == 0) { Save(); BlockReason = "Waiting for map manager"; return false; }
            QueueRpc(flight, "NativeRefresh", [
                NextCall(GameOffsets.MapLoadTowerCentres, r3: map),
                NextCall(GameOffsets.MapLoadTowerScaleLevels, r3: map),
                NextCall(GameOffsets.MapInitTowerRecords, r3: map)]);
            return false;
        }
        CompleteFlight(flight);
        return true;
    }

    private static string? RemovalActor(Flight flight, NativeProfile profile) =>
        profile.Tiers[Math.Min(flight.NativeTier, profile.Tiers.Length - 1)].RemoveActor;

    private uint PrepareRemovalString(string actor)
    {
        uint name = mailbox.WriteSafeString(actor);
        // allowEquipped is a native bool in the first byte of a big-endian word.
        mailbox.SetWord(Protocol.Get("scratch_offset") + 68, 0x01000000);
        return name;
    }

    private static NativeFlag CurrentNativeFlag(Flight flight, NativeProfile profile) =>
        flight.NativeTierSelected ? profile.Tiers[flight.NativeTier].Writes[flight.NativeWrite]
            : profile.Tiers[flight.NativeTier].Writes[^1];

    private uint PrepareNativeString(Flight flight, NativeProfile profile)
    {
        uint name = mailbox.WriteSafeString(CurrentNativeFlag(flight, profile).Name);
        mailbox.SetWord(Protocol.Get("scratch_offset") + 64, 0);
        return name;
    }
}
