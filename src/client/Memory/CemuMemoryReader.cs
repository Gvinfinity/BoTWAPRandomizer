using System.Diagnostics;
using System.Globalization;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace BotWClient.Memory;

// Linux /proc access. Scan bounded chunks rather than allocating an entire guest mapping.
public sealed class CemuMemoryReader : IMemory
{
    private readonly SafeFileHandle handle;
    private readonly long address;
    private FileStream? producerLease;
    public int ProcessId { get; }
    private CemuMemoryReader(SafeFileHandle handle, long address, int pid) { this.handle = handle; this.address = address; ProcessId = pid; }
    public static CemuMemoryReader Attach(bool verbose = false, Action<string>? log = null)
    {
        if (verbose && log is null) log = new ClientLog(true).Write;
        log?.Invoke("Searching for Cemu processes and a configured AP v2 mailbox.");
        if (!OperatingSystem.IsLinux()) throw new PlatformNotSupportedException("Cemu attachment currently uses Linux /proc");
        foreach (var process in Process.GetProcesses().Where(p => p.ProcessName.Equals("Cemu", StringComparison.OrdinalIgnoreCase)))
        {
            var timer = Stopwatch.StartNew();
            long scanned = 0;
            log?.Invoke($"Scanning Cemu PID {process.Id}; opening /proc/{process.Id}/mem.");
            var producerLease = new FileStream(Path.Combine(Path.GetTempPath(), $"BotWAP-Cemu-{process.Id}.lock"),
                FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            SafeFileHandle handle;
            try { handle = File.OpenHandle($"/proc/{process.Id}/mem", FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite); }
            catch { producerLease.Dispose(); throw; }
            bool selected = false;
            try
            {
                foreach (string line in File.ReadLines($"/proc/{process.Id}/maps"))
                {
                    var fields = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                    if (!fields[1].StartsWith("rw", StringComparison.Ordinal)) continue;
                    var range = fields[0].Split('-');
                    long start = long.Parse(range[0], NumberStyles.HexNumber), end = long.Parse(range[1], NumberStyles.HexNumber);
                    byte[] buffer = new byte[1024 * 1024];
                    for (long position = start; position < end; position += buffer.Length - 7)
                    {
                        int read;
                        try { read = RandomAccess.Read(handle, buffer.AsSpan(0, (int)Math.Min(buffer.Length, end - position)), position); }
                        catch (IOException) { break; }
                        if (read < 8) break;
                        scanned += read;
                        for (int i = 0; i <= read - 8; i++)
                        {
                            if (!buffer.AsSpan(i, 8).SequenceEqual("APMBBOTW"u8)) continue;
                            var candidate = new CemuMemoryReader(handle, position + i, process.Id);
                            try
                            {
                                using var identity = new MemoryStream(candidate.Read(Protocol.Get("extension_offset"), 16));
                                if (!identity.ToArray().AsSpan(0, 4).SequenceEqual("APV2"u8) || candidate.ReadWord(Protocol.Get("configured_offset")) != 1) continue;
                                new Mailbox(candidate).Validate(); selected = true;
                                candidate.producerLease = producerLease;
                                log?.Invoke($"Cemu PID {process.Id}, mailbox 0x{position + i:X}; scanned {scanned / 1048576.0:F1} MiB in {timer.Elapsed.TotalSeconds:F2}s.");
                                return candidate;
                            }
                            catch (IOException ex) { log?.Invoke($"Rejected mailbox candidate 0x{position + i:X}: {ex.Message}"); }
                        }
                    }
                }
            }
            finally { if (!selected) { handle.Dispose(); producerLease.Dispose(); } }
        }
        throw new IOException("No configured AP v2 mailbox found. Load the seed's graphic pack in Cemu first.");
    }
    private uint ReadWord(int offset) => Protocol.Read(Read(offset, 4));
    public byte[] Read(int offset, int length)
    {
        byte[] bytes = new byte[length]; int total = 0;
        while (total < length)
        {
            int count = RandomAccess.Read(handle, bytes.AsSpan(total), address + offset + total);
            if (count == 0) throw new EndOfStreamException("Cemu memory is unavailable"); total += count;
        }
        return bytes;
    }
    public void Write(int offset, byte[] bytes) => RandomAccess.Write(handle, bytes, address + offset);
    public void Dispose() { handle.Dispose(); producerLease?.Dispose(); }
}
