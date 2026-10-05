using System.Text.Json;
using System.Diagnostics;
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
    private readonly Action<string>? log;
    public SlotContract Contract { get; }
    public int Team { get; }
    public int Slot { get; }
    public bool Connected => session.Socket.Connected;
    public IReadOnlyList<ReceivedItem> ReceivedItems => session.Items.AllItemsReceived
        .Select(item => new ReceivedItem(item.ItemId, item.LocationId)).ToArray();
    public APSessionManager(string uri, string slotName, string? password, Mailbox mailbox, Action<string>? log = null)
    {
        this.log = log;
        session = OpenSession(uri, slotName, password, log, out var login);
        Team = login.Team; Slot = login.Slot;
        try
        {
            log?.Invoke("Validating slot data against Cemu.");
            using var data = JsonDocument.Parse(JsonConvert.SerializeObject(login.SlotData));
            Contract = new SlotContract(data.RootElement, mailbox, Slot, session.RoomState.Seed, session.Locations.AllLocations);
            log?.Invoke($"AP slot verified: fingerprint={Contract.Fingerprint}, locations={Contract.Locations.Count}, starting item types={Contract.StartingInventory.Count}");
        }
        catch { Dispose(); throw; }
    }

    // Uses the same SDK setup and login as normal play, without requiring Cemu
    // access or creating a delivery journal. No gameplay packets are submitted.
    public static void DiagnoseConnection(string uri, string slotName, string? password, Action<string>? log)
    {
        var connection = OpenSession(uri, slotName, password, log, out var login);
        try
        {
            Console.WriteLine($"AP connection test passed: team {login.Team}, slot {login.Slot}, seed {connection.RoomState.Seed}. Cemu/pack validation was not run.");
        }
        finally { Disconnect(connection, log); }
    }

    private static ArchipelagoSession OpenSession(string uri, string slotName, string? password,
        Action<string>? log, out LoginSuccessful login)
    {
        var elapsed = Stopwatch.StartNew();
        string stage = "opening WebSocket / waiting for RoomInfo";
        Exception? socketError = null;
        var connection = ArchipelagoSessionFactory.CreateSession(new Uri(uri));
        connection.Socket.SocketOpened += () => log?.Invoke($"AP WebSocket opened after {elapsed.Elapsed.TotalMilliseconds:F0} ms; waiting for RoomInfo.");
        connection.Socket.SocketClosed += reason => log?.Invoke($"AP WebSocket closed: {(string.IsNullOrEmpty(reason) ? "no close reason supplied by SDK" : reason)}; stage={stage}");
        connection.Socket.ErrorReceived += (exception, message) =>
        {
            socketError = exception;
            log?.Invoke($"AP socket error during {stage}: {message}\n{exception}");
        };
        connection.Socket.PacketReceived += packet =>
        {
            if (packet is RoomInfoPacket) stage = "RoomInfo received / logging in";
            if (packet is ConnectedPacket) stage = "Connected received";
            log?.Invoke($"AP <- {Summarize(packet)}");
        };
        connection.Socket.PacketsSent += packets =>
        {
            foreach (var packet in packets) log?.Invoke($"AP -> {Summarize(packet)}");
        };
        try
        {
            log?.Invoke($"AP connecting: {ServerEndpoint.Describe(new Uri(uri))}; SDK={typeof(ArchipelagoSession).Assembly.GetName().Version}; game=Breath of the Wild; slot={slotName}; items=AllItems");
            var result = connection.TryConnectAndLogin("Breath of the Wild", slotName, ItemsHandlingFlags.AllItems,
                version: new Version(0, 7, 0), password: password);
            if (result is not LoginSuccessful successful)
                throw new IOException($"Archipelago login failed at {uri} after {elapsed.Elapsed.TotalSeconds:F2}s during {stage}: " +
                    string.Join("; ", ((LoginFailure)result).Errors) +
                    (socketError is null ? "" : $" Socket error: {socketError.GetBaseException().Message}"), socketError);
            login = successful;
            stage = "login accepted";
            log?.Invoke($"AP login accepted: team={login.Team}, slot={login.Slot}, seed={connection.RoomState.Seed}; elapsed={elapsed.Elapsed.TotalMilliseconds:F0} ms");
            return connection;
        }
        catch { Disconnect(connection, log); throw; }
    }
    // Deliberately summarize packets: Connect carries the password, and slot/data
    // packages can be enormous. Never dump raw protocol payloads into the log.
    internal static string Summarize(ArchipelagoPacketBase packet) => packet switch
    {
        ConnectPacket connect => $"Connect game={connect.Game}, slot={connect.Name}, password={(string.IsNullOrEmpty(connect.Password) ? "not supplied" : "[redacted]")}, version={connect.Version}, items={connect.ItemsHandling}",
        RoomInfoPacket room => $"RoomInfo version={room.Version}, seed={room.SeedName}",
        ConnectedPacket connected => $"Connected team={connected.Team}, slot={connected.Slot}",
        ReceivedItemsPacket items => $"ReceivedItems index={items.Index}, count={items.Items.Length}",
        LocationChecksPacket checks => $"LocationChecks count={checks.Locations.Length}, ids=[{string.Join(", ", checks.Locations)}]",
        _ => packet.GetType().Name
    };
    public void SendChecks(long[] ids)
    {
        try
        {
            var timer = Stopwatch.StartNew();
            log?.Invoke($"Submitting {ids.Length} journaled location checks.");
            // Await the actual socket send. The SDK helper may return an outer
            // task before its nested async send completes, and marks checks locally.
            session.Socket.SendPacketAsync(new LocationChecksPacket { Locations = ids }).GetAwaiter().GetResult();
            log?.Invoke($"LocationChecks socket send completed in {timer.Elapsed.TotalMilliseconds:F1} ms.");
        }
        catch (Exception ex) when (ex is ArchipelagoSocketClosedException or System.Net.WebSockets.WebSocketException or System.Net.Sockets.SocketException or IOException)
        {
            Dispose();
            throw new IOException("AP check submission failed; journal retained for reconnect", ex);
        }
    }
    public void Dispose() => Disconnect(session, log);
    private static void Disconnect(ArchipelagoSession session, Action<string>? log)
    {
        if (!session.Socket.Connected) return;
        try { log?.Invoke("Closing AP WebSocket."); session.Socket.DisconnectAsync().WaitAsync(TimeSpan.FromSeconds(3)).GetAwaiter().GetResult(); }
        catch (Exception ex) when (ex is System.Net.WebSockets.WebSocketException or System.Net.Sockets.SocketException or IOException or TimeoutException) { log?.Invoke($"AP disconnect: {ex}"); }
    }
}
