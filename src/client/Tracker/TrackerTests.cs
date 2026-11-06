using System.Net;
using System.Text.Json;

namespace BotWClient.Tracker;

internal static class TrackerTests
{
    public static int Run()
    {
        try { Check().GetAwaiter().GetResult(); Console.WriteLine("PASS: tracker HTTP assets, seed isolation, overworld coordinates, immutable snapshots, read-only routes, private loopback origin, game map bounds, and entrance anchors"); return 0; }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }
    private static async Task Check()
    {
        // Choose an available local port without relying on a fixed user port.
        var socket = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
        socket.Start(); int port = ((IPEndPoint)socket.LocalEndpoint).Port; socket.Stop();
        long id;
        using var http = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}/"), Timeout = TimeSpan.FromSeconds(5) };
        using (var catalog = new TrackerServer(port))
        {
            using var all = JsonDocument.Parse(await http.GetStringAsync("api/locations"));
            var entries = all.RootElement.EnumerateArray().ToArray();
            Require(entries.Length > 100 && entries.Select(e => e.GetProperty("id").GetInt64()).Distinct().Count() == entries.Length, "Catalog identity");
            id = entries.First(e => e.GetProperty("position").ValueKind == JsonValueKind.Array).GetProperty("id").GetInt64();
            foreach (var entry in entries.Where(e => e.GetProperty("name").GetString()!.Contains("Shrine - Chest")))
                Require(entry.GetProperty("position").ValueKind == JsonValueKind.Null || entry.GetProperty("positionSource").GetString() == "entrance", "Interiors use entrance anchors, never local dungeon coordinates");
        }
        using var tracker = new TrackerServer(port, [id]);
        long[] checks = [id];
        tracker.Publish("test-seed-T0-P1", "Link", true, checks, 2, "Waiting for active gameplay", new Dictionary<string, int> { ["Paraglider"] = 1 }, 1);
        checks[0] = 123; // Publishing must copy state before handlers observe it.
        using var locations = JsonDocument.Parse(await http.GetStringAsync("api/locations"));
        Require(locations.RootElement.GetArrayLength() == 1 && locations.RootElement[0].GetProperty("id").GetInt64() == id, "Only active seed locations");
        Require(!locations.RootElement[0].TryGetProperty("original_actor", out _) && !locations.RootElement[0].TryGetProperty("placed_item", out _), "No loot spoilers");
        using var state = JsonDocument.Parse(await http.GetStringAsync("api/state"));
        Require(state.RootElement.GetProperty("checks")[0].GetInt64() == id && state.RootElement.GetProperty("inventory").GetProperty("Paraglider").GetInt32() == 1, "Snapshot isolation and inventory");
        foreach (string path in new[] { "", "app.js", "logic.js", "style.css", "api/items", "api/map" })
        {
            using var response = await http.GetAsync(path);
            Require(response.IsSuccessStatusCode && (await response.Content.ReadAsByteArrayAsync()).Length > 20, $"Embedded resource: {path}");
            Require(response.Headers.Contains("Content-Security-Policy") && !response.Headers.Contains("Access-Control-Allow-Origin"), "Origin restrictions");
        }
        using var mapInfo = JsonDocument.Parse(await http.GetStringAsync("api/map"));
        Require(mapInfo.RootElement.GetProperty("bounds").EnumerateArray().Select(value => value.GetInt32()).SequenceEqual(new[] { -6000, -5000, 6000, 5000 }), "Game map calibration");
        if (mapInfo.RootElement.GetProperty("available").GetBoolean())
        {
            using var background = await http.GetAsync("map.webp");
            Require(background.IsSuccessStatusCode && background.Content.Headers.ContentType?.MediaType == "image/webp", "Game background is served locally");
        }
        using var missing = await http.GetAsync("not-a-file"); Require(missing.StatusCode == HttpStatusCode.NotFound, "Unknown route");
        using var post = await http.PostAsync("api/state", new StringContent("{}")); Require(post.StatusCode == HttpStatusCode.MethodNotAllowed, "No game mutation endpoint");
    }
    private static void Require(bool condition, string message) { if (!condition) throw new InvalidDataException(message); }
}
