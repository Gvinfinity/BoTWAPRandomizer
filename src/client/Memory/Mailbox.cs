using System.Buffers.Binary;
using System.Text;
using System.Text.Json;

namespace BotWClient.Memory;

public static class GameOffsets
{
    public const uint SafeStringVtable = 0x10263910;
    public const uint PauseMenuDataMgrPtr = 0x10469978;
    public const uint GdtManagerPtr = 0x1046D5B0;
    public const uint PlayerInfoPtr = 0x10463F38;

    public const uint MaxHeartValueHandle = 0x10466AD4;
    public const uint WeaponPorchStockHandle = 0x10467B04;
    public const uint BowPorchStockHandle = 0x10464480;
    public const uint ShieldPorchStockHandle = 0x104678CC;

    public const uint PauseMenuCritSectionOffset = 0x10;
    public const uint PauseMenuItemListOffset = 0x4C;
    public const uint PauseMenuItemListHeadOffset = 0x50;
    public const uint PauseMenuItemListNodeOffset = 0x58;
    public const uint PouchItemValueOffset = 0x10;
    public const uint PouchItemNameOffset = 0x18;
    public const uint PlayerInfoActorOffset = 0x30;

    public const uint LockCritSection = 0x030BB668;
    public const uint UnlockCritSection = 0x030BB69C;
    public const uint GetPouchItemType = 0x02EAE914;
    public const uint GetWeaponMaxValue = 0x0308812C;
    public const uint PauseMenuAddItem = 0x02EB3DF0;
    public const uint PauseMenuPostAddFood = 0x02EB58A8;
    public const uint PauseMenuSaveToGameData = 0x02EB3764;
    public const uint GdtGetS32 = 0x02E146A4;
    public const uint GdtSetS32 = 0x02E14848;
    public const uint GdtGetFlagStaminaMax = 0x02E1AC6C;
    public const uint PlayerInfoSetMaxHeartValue = 0x02D4992C;
    public const uint PlayerInfoSetStaminaMax = 0x02D49DFC;
    public const uint PlayerInfoSetActorStaminaMax = 0x02D49E88;
}

public static class Protocol
{
    private static readonly JsonDocument Schema = JsonDocument.Parse(typeof(Protocol).Assembly.GetManifestResourceStream("BotWClient.protocol.json")!);
    public static int Get(string name) => Schema.RootElement.GetProperty(name).GetInt32();
    public static uint Read(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadUInt32BigEndian(bytes);
    public static void Write(Span<byte> bytes, uint value) => BinaryPrimitives.WriteUInt32BigEndian(bytes, value);
    public static float ReadFloat(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadSingleBigEndian(bytes);
    public static void WriteFloat(Span<byte> bytes, float value) => BinaryPrimitives.WriteSingleBigEndian(bytes, value);
    public static uint Capability(string name) => Schema.RootElement.GetProperty("capabilities").GetProperty(name).GetUInt32();

    public static void ValidateActorName(string actorName, uint quantity)
    {
        if (quantity == 0 || quantity > int.MaxValue)
            throw new ArgumentException("Invalid item quantity");
        if (string.IsNullOrEmpty(actorName) || actorName.Length >= Get("actor_name_size") ||
            actorName.Any(c => c == 0 || c > 127) || actorName.StartsWith("AP_Check_", StringComparison.Ordinal))
            throw new ArgumentException("Actor must be a native ASCII item name with a terminating NUL");
        if (quantity != 1 && actorName.StartsWith("Weapon_", StringComparison.Ordinal))
            throw new ArgumentException("Weapon grants must grant exactly one actor");
    }

    public static byte[] Encode(RpcCall call)
    {
        if (call.SeqId == 0 || call.Address == 0)
            throw new ArgumentException("Invalid RPC sequence or function address");
        var bytes = new byte[Get("incoming_size")];
        Write(bytes.AsSpan(0), call.SeqId);
        Write(bytes.AsSpan(4), call.Address);
        Write(bytes.AsSpan(8), call.R3);
        Write(bytes.AsSpan(12), call.R4);
        Write(bytes.AsSpan(16), call.R5);
        Write(bytes.AsSpan(20), call.R6);
        Write(bytes.AsSpan(24), call.R7);
        Write(bytes.AsSpan(28), call.R8);
        Write(bytes.AsSpan(32), call.R9);
        Write(bytes.AsSpan(36), call.R10);
        WriteFloat(bytes.AsSpan(40), call.F1);
        WriteFloat(bytes.AsSpan(44), call.F2);
        WriteFloat(bytes.AsSpan(48), call.F3);
        WriteFloat(bytes.AsSpan(52), call.F4);
        return bytes;
    }
}

public readonly record struct RpcCall(
    uint SeqId,
    uint Address,
    uint R3 = 0, uint R4 = 0, uint R5 = 0, uint R6 = 0,
    uint R7 = 0, uint R8 = 0, uint R9 = 0, uint R10 = 0,
    float F1 = 0f, float F2 = 0f, float F3 = 0f, float F4 = 0f);

public readonly record struct RpcResult(uint SeqId, uint R3, float F1);
public record struct OutgoingCheck(uint SeqId, ulong ApLocationId, uint IsShop);

public interface IMemory : IDisposable
{
    byte[] Read(int offset, int length);
    byte[] ReadGuest(uint guestAddress, uint mailboxGuestAddress, int length);
    void Write(int offset, byte[] bytes);
}

public sealed class Mailbox(IMemory memory) : IDisposable
{
    public uint Word(int offset) => Protocol.Read(memory.Read(offset, 4));
    public void SetWord(int offset, uint value) { var bytes = new byte[4]; Protocol.Write(bytes, value); memory.Write(offset, bytes); }
    public uint Status => Word(8);
    public uint InHead => Word(12);
    public uint InTail => Word(16);
    public uint OutHead => Word(20);
    public uint OutTail => Word(24);
    public uint GuestAddress => Word(Protocol.Get("mailbox_address_offset"));
    public uint AckSequence => Word(Protocol.Get("ack_sequence_offset"));
    public string Fingerprint => Convert.ToHexString(memory.Read(Protocol.Get("seed_fingerprint_offset"), 16)).ToLowerInvariant();

    public HashSet<long> Validate()
    {
        if (Encoding.ASCII.GetString(memory.Read(0, 8)) != "APMBBOTW" ||
            Encoding.ASCII.GetString(memory.Read(Protocol.Get("extension_offset"), 4)) != "APV2" ||
            Word(Protocol.Get("version_offset")) != Protocol.Get("version") ||
            Word(Protocol.Get("configured_offset")) != 1 ||
            (Word(Protocol.Get("capabilities_offset")) & Protocol.Capability("rpc")) == 0)
            throw new InvalidDataException("An RPC-capable protocol v2 seed hook is required");
        _ = memory.Read(Protocol.Get("scratch_offset"), Protocol.Get("scratch_size"));
        uint count = Word(Protocol.Get("location_count_offset"));
        if (count == 0 || count > Protocol.Get("max_locations")) throw new InvalidDataException("Invalid hook location table");
        var ids = new HashSet<long>();
        for (int i = 0; i < count; i++)
        {
            uint id = Word(Protocol.Get("location_table_offset") + i * Protocol.Get("location_entry_size"));
            if (id == 0 || !ids.Add(id)) throw new InvalidDataException("Invalid or duplicate hook location ID");
        }
        ValidateRing(InHead, InTail); ValidateRing(OutHead, OutTail);
        return ids;
    }

    private static void ValidateRing(uint head, uint tail)
    {
        if (unchecked(head - tail) > Protocol.Get("ring_capacity")) throw new InvalidDataException("Corrupt mailbox ring counters");
    }

    public bool EnqueueBatch(ReadOnlySpan<RpcCall> calls, uint expectedHead)
    {
        if (calls.IsEmpty) throw new ArgumentException("RPC batch cannot be empty");
        int capacity = Protocol.Get("ring_capacity"), stride = Protocol.Get("incoming_size"), baseOffset = Protocol.Get("incoming_offset");
        if (calls.Length > capacity) throw new ArgumentException("RPC batch exceeds ring capacity");
        uint head = InHead, tail = InTail; ValidateRing(head, tail);
        if (head != expectedHead || unchecked(head - tail) + (uint)calls.Length > (uint)capacity) return false;
        for (int i = 0; i < calls.Length; i++)
        {
            byte[] bytes = Protocol.Encode(calls[i]);
            uint slot = unchecked(head + (uint)i);
            memory.Write(baseOffset + (int)(slot % (uint)capacity) * stride, bytes);
        }
        SetWord(12, unchecked(head + (uint)calls.Length));
        return true;
    }

    public bool Enqueue(RpcCall call, uint expectedHead) => EnqueueBatch([call], expectedHead);

    public RpcResult ReadResult(uint slotHead)
    {
        int capacity = Protocol.Get("ring_capacity"), stride = Protocol.Get("incoming_size"), baseOffset = Protocol.Get("incoming_offset");
        byte[] bytes = memory.Read(baseOffset + (int)(slotHead % (uint)capacity) * stride, stride);
        return new RpcResult(Protocol.Read(bytes), Protocol.Read(bytes.AsSpan(56)), Protocol.ReadFloat(bytes.AsSpan(60)));
    }

    public uint WriteSafeString(string actorName)
    {
        Protocol.ValidateActorName(actorName, 1);
        uint baseAddr = GuestAddress;
        if (baseAddr == 0) throw new InvalidDataException("Guest mailbox address is not initialized");
        int scratchOffset = Protocol.Get("scratch_offset");
        var buffer = new byte[64];
        Protocol.Write(buffer.AsSpan(0), unchecked(baseAddr + (uint)scratchOffset + 8));
        Protocol.Write(buffer.AsSpan(4), GameOffsets.SafeStringVtable);
        Encoding.ASCII.GetBytes(actorName).CopyTo(buffer, 8);
        memory.Write(scratchOffset, buffer);
        return unchecked(baseAddr + (uint)scratchOffset);
    }

    public uint ReadGuestWord(uint guestAddress) => Protocol.Read(memory.ReadGuest(guestAddress, GuestAddress, 4));

    public (uint Sum, uint Count) MeasureNamedPouch(uint mgr, string actorName)
    {
        byte[] expected = Encoding.ASCII.GetBytes(actorName + '\0');
        uint baseAddr = GuestAddress;
        uint listHead = unchecked(mgr + GameOffsets.PauseMenuItemListOffset);
        uint node = Protocol.Read(memory.ReadGuest(unchecked(mgr + GameOffsets.PauseMenuItemListHeadOffset), baseAddr, 4));
        uint nodeOffset = Protocol.Read(memory.ReadGuest(unchecked(mgr + GameOffsets.PauseMenuItemListNodeOffset), baseAddr, 4));
        uint sum = 0, count = 0;
        for (int step = 0; step < 420 && node != listHead && node != 0; step++)
        {
            uint itemPtr = unchecked(node - nodeOffset);
            uint namePtr = Protocol.Read(memory.ReadGuest(unchecked(itemPtr + GameOffsets.PouchItemNameOffset), baseAddr, 4));
            if (namePtr != 0 && memory.ReadGuest(namePtr, baseAddr, expected.Length).AsSpan().SequenceEqual(expected))
            {
                int value = unchecked((int)Protocol.Read(memory.ReadGuest(unchecked(itemPtr + GameOffsets.PouchItemValueOffset), baseAddr, 4)));
                if (value > 0) { sum = unchecked(sum + (uint)value); count++; }
            }
            node = Protocol.Read(memory.ReadGuest(unchecked(node + 4), baseAddr, 4));
        }
        return (sum, count);
    }

    public (uint Sum, uint Count) MeasureStablePouch(uint mgr, string actorName)
    {
        var previous = MeasureNamedPouch(mgr, actorName);
        for (int attempt = 0; attempt < 3; attempt++)
        {
            var current = MeasureNamedPouch(mgr, actorName);
            if (current == previous) return current;
            previous = current;
        }
        return previous;
    }

    public OutgoingCheck? PeekCheck()
    {
        uint head = OutHead, tail = OutTail; ValidateRing(head, tail);
        if (head == tail) return null;
        var bytes = memory.Read(Protocol.Get("outgoing_offset") + (int)(tail % Protocol.Get("ring_capacity")) * Protocol.Get("outgoing_size"), Protocol.Get("outgoing_size"));
        var check = new OutgoingCheck(Protocol.Read(bytes), BinaryPrimitives.ReadUInt64BigEndian(bytes.AsSpan(4)), Protocol.Read(bytes.AsSpan(12)));
        if (check.SeqId != tail) throw new InvalidDataException("Outgoing sequence does not match its ring position");
        return check;
    }

    public void AcknowledgeCheck(uint sequence)
    {
        if (OutTail != sequence) throw new InvalidDataException("Outgoing consumer changed unexpectedly");
        SetWord(24, unchecked(sequence + 1));
    }

    public void Dispose() => memory.Dispose();
}
