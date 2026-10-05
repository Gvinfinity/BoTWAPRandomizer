namespace BotWClient.Archipelago;

internal static class ServerEndpoint
{
    public static Uri Parse(string server, string? port = null)
    {
        bool explicitScheme = server.Contains("://", StringComparison.Ordinal);
        if (!Uri.TryCreate(explicitScheme ? server : "unspecified://" + server, UriKind.Absolute, out var uri) ||
            string.IsNullOrWhiteSpace(uri.Host) ||
            (explicitScheme && uri.Scheme is not ("ws" or "wss")) ||
            uri.UserInfo.Length != 0 || uri.Fragment.Length != 0)
            throw new ArgumentException("--server must be a host[:port], ws:// URL, or wss:// URL without credentials or a fragment.");

        // Use an unknown scheme to detect explicitly written default ports (80/443).
        var authority = new Uri(explicitScheme ? "unspecified" + server[server.IndexOf(":", StringComparison.Ordinal)..] : "unspecified://" + server);
        int embeddedPort = authority.Port;
        int selectedPort = embeddedPort;
        if (port is not null)
        {
            if (!int.TryParse(port, out selectedPort) || selectedPort is < 1 or > 65535)
                throw new ArgumentException("--port must be a number between 1 and 65535.");
            if (embeddedPort != -1 && embeddedPort != selectedPort)
                throw new ArgumentException("--port conflicts with the port in --server; supply one port or matching values.");
        }
        if (selectedPort == 0) throw new ArgumentException("Server port must be between 1 and 65535.");
        if (selectedPort == -1) selectedPort = explicitScheme ? uri.Port : 38281;
        return new UriBuilder(uri) { Port = selectedPort }.Uri;
    }

    public static string Describe(Uri uri) => uri.Scheme == "unspecified"
        ? $"{new UriBuilder(uri) { Scheme = "wss" }.Uri} (automatic: SDK tries WSS, then WS)"
        : $"{uri} ({(uri.Scheme == "wss" ? "TLS; certificate validation enabled" : "plain WebSocket")})";
}
