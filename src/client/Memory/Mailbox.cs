using System.Buffers.Binary;
using System.Text;
using System.Text.Json;

namespace BotWClient.Memory;

public static class Protocol
{
    private static readonly JsonDocument Schema = JsonDocument.Parse(typeof(Protocol).Assembly.GetManifestResourceStream("BotWClient.protocol.json")!);
    public static int Get(string name) => Schema.RootElement.GetProperty(name).GetInt32();
    public static uint Read(ReadOnlySpan<byte> bytes) => BinaryPrimitives.ReadUInt32BigEndian(bytes);
    public static void Write(Span<byte> bytes, uint value) => BinaryPrimitives.WriteUInt32BigEndian(bytes, value);
    public static byte[] Encode(IncomingItem item)
    {
        if (item.SeqId == 0 || item.Quantity == 0 || item.Quantity > int.MaxValue || item.Flags != 0)
            throw new ArgumentException("Invalid item sequence, quantity, or command flags");
        if (string.IsNullOrEmpty(item.ActorName) || item.ActorName.Length >= Get("actor_name_size") ||
            item.ActorName.Any(c => c == 0 || c > 127) || item.ActorName.StartsWith("AP_Check_", StringComparison.Ordinal))
            throw new ArgumentException("Actor must be a native ASCII item name with a terminating NUL");
        if (item.Quantity != 1 && item.ActorName.StartsWith("Weapon_", StringComparison.Ordinal))
            throw new ArgumentException("Weapon commands must grant exactly one actor");
        var bytes = new byte[Get("incoming_size")];
        Write(bytes, item.SeqId); Write(bytes.AsSpan(4), item.ApItemId);
        Encoding.ASCII.GetBytes(item.ActorName).CopyTo(bytes, 8);
        Write(bytes.AsSpan(56), item.Quantity); Write(bytes.AsSpan(60), item.Flags);
        return bytes;
    }
}

public record struct IncomingItem(uint SeqId, uint ApItemId, string ActorName, uint Quantity, uint Flags = 0);
public record struct OutgoingCheck(uint SeqId, ulong ApLocationId, uint IsShop);
public interface IMemory : IDisposable
{
    byte[] Read(int offset, int length);
    void Write(int offset, byte[] bytes);
}

public sealed class Mailbox(IMemory memory) : IDisposable
{
    public uint Word(int offset) => Protocol.Read(memory.Read(offset, 4));
    public void SetWord(int offset, uint value) { var bytes = new byte[4]; Protocol.Write(bytes, value); memory.Write(offset, bytes); }
    public uint InHead => Word(12);
    public uint InTail => Word(16);
    public uint OutHead => Word(20);
    public uint OutTail => Word(24);
    public uint AckSequence => Word(Protocol.Get("ack_sequence_offset"));
    public uint DeliveryError => Word(Protocol.Get("delivery_error_offset"));
    public string Fingerprint => Convert.ToHexString(memory.Read(Protocol.Get("seed_fingerprint_offset"), 16)).ToLowerInvariant();
    public HashSet<long> Validate()
    {
        if (Encoding.ASCII.GetString(memory.Read(0, 8)) != "APMBBOTW" ||
            Encoding.ASCII.GetString(memory.Read(Protocol.Get("extension_offset"), 4)) != "APV2" ||
            Word(Protocol.Get("version_offset")) != Protocol.Get("version") ||
            Word(Protocol.Get("configured_offset")) != 1 ||
            (Word(Protocol.Get("capabilities_offset")) & 1) != 1)
            throw new InvalidDataException("A configured protocol v2 seed hook is required");
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
    public bool Enqueue(IncomingItem item, uint expectedHead)
    {
        byte[] bytes = Protocol.Encode(item);
        uint head = InHead, tail = InTail; ValidateRing(head, tail);
        if (head != expectedHead || unchecked(head - tail) >= Protocol.Get("ring_capacity")) return false;
        memory.Write(Protocol.Get("incoming_offset") + (int)(head % Protocol.Get("ring_capacity")) * Protocol.Get("incoming_size"), bytes);
        // Payload is completely written before the native consumer can see the head.
        SetWord(12, unchecked(head + 1)); return true;
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
