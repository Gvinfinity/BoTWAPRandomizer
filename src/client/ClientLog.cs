using System.Diagnostics;

namespace BotWClient;

internal sealed class ClientLog(bool enabled, string? password = null, TextWriter? output = null)
{
    private readonly Stopwatch elapsed = Stopwatch.StartNew();
    private readonly object gate = new();
    public void Write(string message)
    {
        if (!enabled) return;
        if (!string.IsNullOrEmpty(password)) message = message.Replace(password, "[redacted]", StringComparison.Ordinal);
        lock (gate)
            (output ?? Console.Error).WriteLine($"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss.fff zzz} +{elapsed.Elapsed.TotalSeconds:F3}s] {message}");
    }
}
