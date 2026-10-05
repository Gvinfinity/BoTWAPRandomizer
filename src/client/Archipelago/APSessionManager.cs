using System.Text.Json;
using Archipelago.MultiClient.Net;
using Archipelago.MultiClient.Net.Enums;
using Archipelago.MultiClient.Net.Packets;
using Archipelago.MultiClient.Net.Exceptions;
using BotWClient.Memory;
using Newtonsoft.Json;

namespace BotWClient.Archipelago;

public sealed class APSessionManager : IServerLink, IDisposable
{
    private readonly ArchipelagoSession session;
    public SlotContract Contract { get; }
    public int Team { get; }
    public int Slot { get; }
    public bool Connected => session.Socket.Connected;
    public IReadOnlyList<ReceivedItem> ReceivedItems => session.Items.AllItemsReceived
        .Select(item => new ReceivedItem(item.ItemId, item.LocationId)).ToArray();
    public APSessionManager(string uri, string slotName, string? password, Mailbox mailbox)
    {
        session = ArchipelagoSessionFactory.CreateSession(uri);
        var result = session.TryConnectAndLogin("Breath of the Wild", slotName, ItemsHandlingFlags.AllItems, password: password);
        if (result is not LoginSuccessful login)
        {
            Dispose();
            throw new IOException("Archipelago login failed: " + string.Join("; ", ((LoginFailure)result).Errors));
        }
        Team = login.Team; Slot = login.Slot;
        try
        {
            using var data = JsonDocument.Parse(JsonConvert.SerializeObject(login.SlotData));
            Contract = new SlotContract(data.RootElement, mailbox, Slot, session.RoomState.Seed, session.Locations.AllLocations);
        }
        catch { Dispose(); throw; }
    }
    public void SendChecks(long[] ids)
    {
        try
        {
            // Await the actual socket send. The SDK helper may return an outer
            // task before its nested async send completes, and marks checks locally.
            session.Socket.SendPacketAsync(new LocationChecksPacket { Locations = ids }).GetAwaiter().GetResult();
        }
        catch (Exception ex) when (ex is ArchipelagoSocketClosedException or System.Net.WebSockets.WebSocketException or System.Net.Sockets.SocketException or IOException)
        {
            Dispose();
            throw new IOException("AP check submission failed; journal retained for reconnect", ex);
        }
    }
    public void Dispose()
    {
        if (!session.Socket.Connected) return;
        try { session.Socket.DisconnectAsync().GetAwaiter().GetResult(); }
        catch (Exception ex) when (ex is System.Net.WebSockets.WebSocketException or System.Net.Sockets.SocketException or IOException) { }
    }
}
