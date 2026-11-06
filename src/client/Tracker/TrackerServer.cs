using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Reflection;

namespace BotWClient.Tracker;

// This server only exposes immutable snapshots. HTTP handlers never touch Cemu,
// the delivery journal, or the Archipelago connection.
public sealed class TrackerServer : IDisposable
{
    private readonly HttpListener listener = new();
    private byte[] state = Encoding.UTF8.GetBytes("{}");
    private readonly byte[] catalog;
    private readonly byte[]? mapImage;
    private readonly byte[] mapInfo;
    public string Url { get; }
    private static byte[] Resource(string name)
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("BotWClient.tracker." + name)
            ?? throw new InvalidDataException($"Missing tracker resource {name}");
        using var buffer = new MemoryStream(); stream.CopyTo(buffer); return buffer.ToArray();
    }
    public TrackerServer(int port, IEnumerable<long>? active = null, string? mapDirectory = null)
    {
        if (port is < 1024 or > 65535) throw new ArgumentOutOfRangeException(nameof(port), "Tracker port must be 1024–65535.");
        mapDirectory ??= FindMapDirectory();
        JsonNode? map = null;
        if (mapDirectory is not null)
        {
            map = JsonNode.Parse(File.ReadAllText(Path.Combine(mapDirectory, "map.json")))!;
            if (map["version"]?.GetValue<int>() != 1 || map["bounds"]?.ToJsonString() != "[-6000,-5000,6000,5000]")
                throw new InvalidDataException("Unsupported tracker map; rebuild it using src.patcher.build_tracker_map.");
            mapImage = File.ReadAllBytes(Path.Combine(mapDirectory, "map.webp"));
        }
        mapInfo = JsonSerializer.SerializeToUtf8Bytes(new { available = mapImage is not null, bounds = new[] { -6000, -5000, 6000, 5000 } });
        var ids = active?.ToHashSet();
        var locations = new JsonArray();
        foreach (string file in new[] { "chests.json", "completions.json", "combat.json" })
        {
            var root = JsonNode.Parse(Resource(file))!;
            foreach (var entry in root["locations"]!.AsArray())
            {
                if (entry?["region"] is null || (ids is not null && !ids.Contains(entry["id"]!.GetValue<long>()))) continue;
                // Interior coordinates are local to their dungeon, never Hyrule coordinates.
                bool overworld = entry["logical_map"]?.GetValue<string>().Contains("Map/MainField/", StringComparison.Ordinal) == true;
                var anchor = map?["positions"]?[entry["id"]!.ToString()];
                locations.Add(new JsonObject {
                    ["id"] = entry["id"]!.DeepClone(), ["name"] = entry["name"]!.DeepClone(),
                    ["region"] = entry["region"]!.DeepClone(), ["kind"] = entry["kind"]?.DeepClone() ?? JsonValue.Create("chest"),
                    ["position"] = overworld ? entry["position"]?.DeepClone() : anchor?["position"]?.DeepClone(),
                    ["positionSource"] = overworld ? JsonValue.Create("world") : anchor?["source"]?.DeepClone(),
                    ["requires"] = entry["requires"]?.DeepClone(),
                    ["ballad"] = entry["category"]?.AsArray().Any(category => category?.GetValue<string>() == "The Champions' Ballad DLC") ?? false
                });
            }
        }
        const long trial = 0xC2100000;
        if (ids is null || ids.Contains(trial)) locations.Add(new JsonObject {
            ["id"] = trial, ["name"] = "Trial of the Sword - Completed", ["region"] = "Trial of the Sword (Final Trials)", ["kind"] = "objective"
        });
        catalog = JsonSerializer.SerializeToUtf8Bytes(locations);
        Url = $"http://127.0.0.1:{port}/";
        listener.Prefixes.Add(Url); listener.Start();
        _ = Task.Run(Serve);
    }
    private static string? FindMapDirectory()
    {
        foreach (string start in new[] { Environment.CurrentDirectory, AppContext.BaseDirectory })
            for (DirectoryInfo? directory = new(start); directory is not null; directory = directory.Parent)
            {
                string path = Path.Combine(directory.FullName, "out", "tracker");
                if (File.Exists(Path.Combine(path, "map.json")) && File.Exists(Path.Combine(path, "map.webp"))) return path;
            }
        string installed = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BotWAP", "tracker");
        return File.Exists(Path.Combine(installed, "map.json")) ? installed : null;
    }
    public void Publish(string identity, string player, bool connected, IEnumerable<long> checks, int received, string? delivery,
        IReadOnlyDictionary<string, int>? inventory = null, int delivered = 0)
    {
        var snapshot = JsonSerializer.SerializeToUtf8Bytes(new { identity, player, connected, checks = checks.Distinct().ToArray(), received, delivered, inventory, delivery, updated = DateTimeOffset.UtcNow });
        Volatile.Write(ref state, snapshot);
    }
    private async Task Serve()
    {
        while (listener.IsListening)
        {
            HttpListenerContext context;
            try { context = await listener.GetContextAsync(); }
            catch (Exception ex) when (ex is HttpListenerException or ObjectDisposedException) { break; }
            _ = Respond(context);
        }
    }
    private async Task Respond(HttpListenerContext context)
    {
        try
        {
            var response = context.Response;
            response.Headers["Cache-Control"] = "no-store";
            response.Headers["X-Content-Type-Options"] = "nosniff";
            response.Headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'";
            if (context.Request.HttpMethod != "GET") { response.StatusCode = 405; return; }
            // No CORS or wildcard binding: seed data stays on the loopback origin.
            string? host = context.Request.Headers["Host"];
            if (host != new Uri(Url).Authority) { response.StatusCode = 403; return; }
            string path = context.Request.Url!.AbsolutePath;
            byte[] body;
            switch (path)
            {
                case "/api/state": body = Volatile.Read(ref state); response.ContentType = "application/json"; break;
                case "/api/locations": body = catalog; response.ContentType = "application/json"; break;
                case "/api/items": body = Resource("items.json"); response.ContentType = "application/json"; break;
                case "/api/map": body = mapInfo; response.ContentType = "application/json"; break;
                case "/map.webp":
                    if (mapImage is null) { response.StatusCode = 404; return; }
                    body = mapImage; response.ContentType = "image/webp"; break;
                case "/": body = Resource("index.html"); response.ContentType = "text/html; charset=utf-8"; break;
                case "/app.js": body = Resource("app.js"); response.ContentType = "text/javascript; charset=utf-8"; break;
                case "/logic.js": body = Resource("logic.js"); response.ContentType = "text/javascript; charset=utf-8"; break;
                case "/style.css": body = Resource("style.css"); response.ContentType = "text/css; charset=utf-8"; break;
                default: response.StatusCode = 404; return;
            }
            response.ContentLength64 = body.Length;
            await response.OutputStream.WriteAsync(body);
        }
        catch (Exception ex) when (ex is HttpListenerException or IOException or ObjectDisposedException) { }
        finally { context.Response.Close(); }
    }
    public void Dispose() { listener.Close(); }
}
