using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace BotWClient;

// Local protocol fixture: exercises the real Archipelago SDK over a WebSocket.
internal sealed class ProtocolServerFixture : IDisposable
{
    private readonly HttpListener listener = new();
    private readonly CancellationTokenSource stop = new(TimeSpan.FromSeconds(15));
    private readonly Task worker;
    private readonly JsonElement slotData;
    private readonly uint location, item;
    public string Uri { get; }
    public TaskCompletionSource<long[]> Checks { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public ProtocolServerFixture(JsonElement slotData, uint location, uint item)
    {
        this.slotData = slotData.Clone(); this.location = location; this.item = item;
        var probe = new TcpListener(IPAddress.Loopback, 0); probe.Start();
        int port = ((IPEndPoint)probe.LocalEndpoint).Port; probe.Stop();
        Uri = $"ws://127.0.0.1:{port}";
        listener.Prefixes.Add($"http://127.0.0.1:{port}/"); listener.Start();
        worker = Run();
    }
    private async Task Run()
    {
        try
        {
            var context = await listener.GetContextAsync().WaitAsync(stop.Token);
            using var socket = (await context.AcceptWebSocketAsync(null)).WebSocket;
            async Task Send(params object[] packets)
            {
                byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(packets);
                await socket.SendAsync(bytes, WebSocketMessageType.Text, true, stop.Token);
            }
            var package = new Dictionary<string, object> { ["Breath of the Wild"] = new {
                item_name_to_id = new Dictionary<string, long> { ["Master Sword"] = item },
                location_name_to_id = new Dictionary<string, long> { ["Test Chest"] = location },
                checksum = "botw-local-protocol-fixture-v2"
            }};
            await Send(new { cmd = "RoomInfo", password = false, games = new[] { "Breath of the Wild" }, tags = new[] { "AP" },
                version = new { major = 0, minor = 6, build = 0, @class = "Version" }, seed_name = "test",
                permissions = new { release = 1, collect = 1, remaining = 1 }, hint_cost = 10, location_check_points = 1,
                datapackage_checksums = new Dictionary<string, string> { ["Breath of the Wild"] = "botw-local-protocol-fixture-v2" }, time = 0.0 });
            byte[] buffer = new byte[65536];
            while (!stop.IsCancellationRequested)
            {
                using var message = new MemoryStream();
                WebSocketReceiveResult result;
                do
                {
                    result = await socket.ReceiveAsync(buffer, stop.Token);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", stop.Token);
                        return;
                    }
                    message.Write(buffer, 0, result.Count);
                } while (!result.EndOfMessage);
                using var packets = JsonDocument.Parse(message.ToArray());
                foreach (var packet in packets.RootElement.EnumerateArray())
                {
                    switch (packet.GetProperty("cmd").GetString())
                    {
                        case "GetDataPackage": await Send(new { cmd = "DataPackage", data = new { games = package } }); break;
                        case "Connect":
                            await Send(new { cmd = "Connected", team = 0, slot = 1,
                                players = new[] { new { team = 0, slot = 1, alias = "Test", name = "Test", @class = "NetworkPlayer" } },
                                missing_locations = new[] { location }, checked_locations = Array.Empty<long>(),
                                slot_info = new Dictionary<string, object> { ["1"] = new { name = "Test", game = "Breath of the Wild", type = 1, group_members = Array.Empty<int>() } },
                                hint_points = 0, slot_data = slotData });
                            // Replay arrives separately from login: the bridge must wait for it.
                            await Send(new { cmd = "ReceivedItems", index = 0,
                                items = new[] { new { item, location, player = 1, flags = 1, @class = "NetworkItem" } } });
                            break;
                        case "LocationChecks":
                            Checks.TrySetResult(packet.GetProperty("locations").EnumerateArray().Select(x => x.GetInt64()).ToArray());
                            break;
                    }
                }
            }
        }
        catch (Exception) when (stop.IsCancellationRequested) { Checks.TrySetCanceled(); }
        catch (Exception ex) { Checks.TrySetException(ex); throw; }
    }
    public void Dispose()
    {
        stop.Cancel(); listener.Stop(); listener.Close();
        try { worker.GetAwaiter().GetResult(); } catch (OperationCanceledException) { }
        stop.Dispose();
    }
}
