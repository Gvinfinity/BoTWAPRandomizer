using System.Net;
using System.Net.Sockets;
using System.Buffers.Binary;
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
    private sealed record MapAssets(byte[] Catalog, byte[]? Image, byte[] Info);

    private readonly HashSet<long>? activeIds;
    private readonly string? explicitMapDirectory;
    private readonly object mapLock = new();
    private (string? Directory, DateTime Metadata, DateTime Image)? mapVersion;
    private MapAssets? mapAssets;
    public string Url { get; }
    private static byte[] Resource(string name)
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("BotWClient.tracker." + name)
            ?? throw new InvalidDataException($"Missing tracker resource {name}");
        using var buffer = new MemoryStream(); stream.CopyTo(buffer); return buffer.ToArray();
    }
    public TrackerServer(int port, IEnumerable<long>? active = null, string? mapDirectory = null)
    {
        if (port != 0 && (port is < 1024 or > 65535))
            throw new ArgumentOutOfRangeException(nameof(port), "Use 0 for an available port or specify a port from 1024–65535.");
        if (port == 0)
        {
            // Ask the OS for a free loopback port before registering the HTTP prefix.
            using var probe = new TcpListener(IPAddress.Loopback, 0);
            probe.Start();
            port = ((IPEndPoint)probe.LocalEndpoint).Port;
        }
        activeIds = active?.ToHashSet();
        explicitMapDirectory = mapDirectory;
        Url = $"http://127.0.0.1:{port}/";
        listener.Prefixes.Add(Url); listener.Start();
        _ = Task.Run(Serve);
    }

    private MapAssets GetMapAssets()
    {
        lock (mapLock)
        {
            string? directory = explicitMapDirectory ?? FindMapDirectory();
            var version = (directory,
                directory is null ? default : File.GetLastWriteTimeUtc(Path.Combine(directory, "map.json")),
                directory is null ? default : File.GetLastWriteTimeUtc(Path.Combine(directory, "map.webp")));
            if (mapAssets is null || mapVersion != version)
            {
                mapAssets = LoadMapAssets(directory);
                mapVersion = version;
            }
            return mapAssets;
        }
    }

    private MapAssets LoadMapAssets(string? mapDirectory)
    {
        byte[]? mapImage = null;
        JsonNode? map = null;
        string? mapError = null;
        if (mapDirectory is not null)
        {
            try
            {
                var metadata = JsonNode.Parse(File.ReadAllText(Path.Combine(mapDirectory, "map.json")));
                if (metadata is not JsonObject || metadata["version"] is not JsonValue version ||
                    !version.TryGetValue<int>(out int value) || value != 1 ||
                    metadata["bounds"]?.ToJsonString() != "[-6000,-5000,6000,5000]" ||
                    metadata["positions"] is not JsonObject)
                    throw new InvalidDataException("Unsupported map metadata");
                var image = File.ReadAllBytes(Path.Combine(mapDirectory, "map.webp"));
                if (image.Length < 20 || !image.AsSpan(0, 4).SequenceEqual("RIFF"u8) ||
                    !image.AsSpan(8, 4).SequenceEqual("WEBP"u8) ||
                    BinaryPrimitives.ReadUInt32LittleEndian(image.AsSpan(4, 4)) != image.Length - 8)
                    throw new InvalidDataException("Invalid or incomplete WebP map");
                mapImage = image;
                map = metadata;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or JsonException)
            {
                mapError = $"{ex.Message}. Rebuild the tracker map.";
            }
        }
        byte[] mapInfo = JsonSerializer.SerializeToUtf8Bytes(new { available = mapImage is not null, error = mapError, bounds = new[] { -6000, -5000, 6000, 5000 } });
        var locations = new JsonArray();
        foreach (string file in new[] { "chests.json", "completions.json", "combat.json" })
        {
            var root = JsonNode.Parse(Resource(file))!;
            foreach (var entry in root["locations"]!.AsArray())
            {
                if (entry?["region"] is null || (activeIds is not null && !activeIds.Contains(entry["id"]!.GetValue<long>()))) continue;
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
        if (activeIds is null || activeIds.Contains(trial)) locations.Add(new JsonObject {
            ["id"] = trial, ["name"] = "Trial of the Sword - Completed", ["region"] = "Trial of the Sword (Final Trials)", ["kind"] = "objective"
        });
        return new MapAssets(JsonSerializer.SerializeToUtf8Bytes(locations), mapImage, mapInfo);
    }
    private static string? FindMapDirectory()
    {
        static bool HasMap(string path) =>
            File.Exists(Path.Combine(path, "map.json")) && File.Exists(Path.Combine(path, "map.webp"));
        string installed = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BotWAP", "tracker");
        if (HasMap(installed)) return installed;
        foreach (string start in new[] { Environment.CurrentDirectory, AppContext.BaseDirectory })
            for (DirectoryInfo? directory = new(start); directory is not null; directory = directory.Parent)
            {
                string path = Path.Combine(directory.FullName, "out", "tracker");
                if (HasMap(path)) return path;
            }
        return null;
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
                case "/api/locations": body = GetMapAssets().Catalog; response.ContentType = "application/json"; break;
                case "/api/items": body = Resource("items.json"); response.ContentType = "application/json"; break;
                case "/api/map": body = GetMapAssets().Info; response.ContentType = "application/json"; break;
                case "/map.webp":
                    if (GetMapAssets().Image is not { } image) { response.StatusCode = 404; return; }
                    body = image; response.ContentType = "image/webp"; break;
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
