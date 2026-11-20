using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace BotWClient.Memory;

// ---------------------------------------------------------------------------
// Platform-agnostic process-memory back-end.
// Linux  → /proc/<pid>/mem  (RandomAccess on a SafeFileHandle)
// Windows → OpenProcess + ReadProcessMemory / WriteProcessMemory
// ---------------------------------------------------------------------------

/// <summary>
/// Abstracts raw cross-process memory I/O so the mailbox scanner is
/// independent of the host operating system.
/// </summary>
internal interface IProcessMemoryBackend : IDisposable
{
    /// <summary>Reads <paramref name="length"/> bytes from <paramref name="address"/> in the target process.</summary>
    int Read(long address, Span<byte> buffer);

    /// <summary>Writes <paramref name="bytes"/> to <paramref name="address"/> in the target process.</summary>
    void Write(long address, ReadOnlySpan<byte> bytes);

    /// <summary>
    /// Enumerates writable, committed memory regions as (start, end) pairs.
    /// Only regions that are readable+writable are yielded.
    /// </summary>
    IEnumerable<(long Start, long End)> WritableRegions();
}

// ---------------------------------------------------------------------------
// Linux back-end: /proc/<pid>/mem
// ---------------------------------------------------------------------------
internal sealed class LinuxProcessMemory : IProcessMemoryBackend
{
    private readonly SafeFileHandle _handle;

    public LinuxProcessMemory(int pid)
    {
        _handle = File.OpenHandle(
            $"/proc/{pid}/mem",
            FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite);
    }

    public int Read(long address, Span<byte> buffer)
    {
        try { return RandomAccess.Read(_handle, buffer, address); }
        catch (IOException) { return 0; }
    }

    public void Write(long address, ReadOnlySpan<byte> bytes) =>
        RandomAccess.Write(_handle, bytes, address);

    public IEnumerable<(long Start, long End)> WritableRegions()
    {
        // /proc/<pid>/maps is available because we opened /proc/<pid>/mem,
        // so we know the PID. We recover it from the handle path via /proc/self.
        // However the PID is passed separately — we keep a copy.
        // This method is only called by the scanner which has the PID, so
        // we expose the maps path instead.
        throw new NotSupportedException("Use LinuxProcessMemory(pid, mapsPath)");
    }

    public void Dispose() => _handle.Dispose();
}

// Full Linux back-end that also owns the maps enumeration.
internal sealed class LinuxProcessMemoryFull : IProcessMemoryBackend
{
    private readonly SafeFileHandle _handle;
    private readonly string _mapsPath;

    public LinuxProcessMemoryFull(int pid, SafeFileHandle? inheritedHandle = null)
    {
        _handle   = inheritedHandle ?? File.OpenHandle($"/proc/{pid}/mem", FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite);
        _mapsPath = $"/proc/{pid}/maps";
    }

    public int Read(long address, Span<byte> buffer)
    {
        try { return RandomAccess.Read(_handle, buffer, address); }
        catch (IOException) { return 0; }
    }

    public void Write(long address, ReadOnlySpan<byte> bytes) =>
        RandomAccess.Write(_handle, bytes, address);

    public IEnumerable<(long Start, long End)> WritableRegions()
    {
        foreach (string line in File.ReadLines(_mapsPath))
        {
            var fields = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length < 2 || !fields[1].StartsWith("rw", StringComparison.Ordinal))
                continue;
            var range = fields[0].Split('-');
            if (range.Length != 2) continue;
            long start = long.Parse(range[0], NumberStyles.HexNumber);
            long end   = long.Parse(range[1], NumberStyles.HexNumber);
            yield return (start, end);
        }
    }

    public void Dispose() => _handle.Dispose();
}

// ---------------------------------------------------------------------------
// Windows back-end: OpenProcess + ReadProcessMemory / WriteProcessMemory
// ---------------------------------------------------------------------------
internal sealed class WindowsProcessMemory : IProcessMemoryBackend
{
    // Process access rights
    private const uint PROCESS_VM_READ      = 0x0010;
    private const uint PROCESS_VM_WRITE     = 0x0020;
    private const uint PROCESS_VM_OPERATION = 0x0008;
    private const uint PROCESS_QUERY_INFORMATION = 0x0400;

    // VirtualQueryEx MEM_COMMIT / PAGE protection masks
    private const uint MEM_COMMIT  = 0x1000;
    private const uint PAGE_GUARD  = 0x100;
    private const uint PAGE_NOACCESS = 0x01;

    // Pages that are both readable and writable
    private static readonly uint[] WritablePages =
    [
        0x04, // PAGE_READWRITE
        0x08, // PAGE_WRITECOPY
        0x40, // PAGE_EXECUTE_READWRITE
        0x80, // PAGE_EXECUTE_WRITECOPY
    ];

    [StructLayout(LayoutKind.Sequential)]
    private struct MEMORY_BASIC_INFORMATION
    {
        public nint  BaseAddress;
        public nint  AllocationBase;
        public uint  AllocationProtect;
        public nint  RegionSize;        // SIZE_T — pointer-sized
        public uint  State;
        public uint  Protect;
        public uint  Type;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern nint OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(nint hObject);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool ReadProcessMemory(
        nint  hProcess,
        nint  lpBaseAddress,
        byte[] lpBuffer,
        nint  nSize,
        out nint lpNumberOfBytesRead);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool WriteProcessMemory(
        nint  hProcess,
        nint  lpBaseAddress,
        byte[] lpBuffer,
        nint  nSize,
        out nint lpNumberOfBytesWritten);

    [DllImport("kernel32.dll")]
    private static extern nint VirtualQueryEx(
        nint  hProcess,
        nint  lpAddress,
        out MEMORY_BASIC_INFORMATION lpBuffer,
        nuint dwLength);

    private readonly nint _hProcess;

    public WindowsProcessMemory(int pid)
    {
        _hProcess = OpenProcess(
            PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION,
            false, pid);
        if (_hProcess == nint.Zero)
            throw new IOException($"OpenProcess({pid}) failed: Win32 error {Marshal.GetLastWin32Error()}");
    }

    public int Read(long address, Span<byte> buffer)
    {
        // ReadProcessMemory requires a managed byte[] overload — copy via temp array.
        var tmp = new byte[buffer.Length];
        if (!ReadProcessMemory(_hProcess, (nint)address, tmp, (nint)tmp.Length, out nint bytesRead))
            return 0;
        tmp.AsSpan(0, (int)bytesRead).CopyTo(buffer);
        return (int)bytesRead;
    }

    public void Write(long address, ReadOnlySpan<byte> bytes)
    {
        var tmp = bytes.ToArray();
        if (!WriteProcessMemory(_hProcess, (nint)address, tmp, (nint)tmp.Length, out _))
            throw new IOException($"WriteProcessMemory failed: Win32 error {Marshal.GetLastWin32Error()}");
    }

    public IEnumerable<(long Start, long End)> WritableRegions()
    {
        nuint mbiSize = (nuint)Marshal.SizeOf<MEMORY_BASIC_INFORMATION>();
        nint  current = nint.Zero;

        while (VirtualQueryEx(_hProcess, current, out var mbi, mbiSize) != nint.Zero)
        {
            long start  = (long)mbi.BaseAddress;
            long size   = (long)mbi.RegionSize;
            long end    = start + size;

            // Advance cursor before any early-continue so we never loop forever.
            current = (nint)end;

            if (mbi.State != MEM_COMMIT) continue;
            if ((mbi.Protect & PAGE_GUARD) != 0) continue;
            if ((mbi.Protect & PAGE_NOACCESS) != 0) continue;
            if (!WritablePages.Contains(mbi.Protect & 0xFF)) continue;

            yield return (start, end);
        }
    }

    public void Dispose() { if (_hProcess != nint.Zero) CloseHandle(_hProcess); }
}

// ---------------------------------------------------------------------------
// CemuMemoryReader — the public IMemory implementation used by Mailbox.
// Works on both Linux and Windows.
// ---------------------------------------------------------------------------
public sealed class CemuMemoryReader : IMemory
{
    private readonly IProcessMemoryBackend _backend;
    private readonly long _address;
    private FileStream? _producerLease;

    public int ProcessId { get; }

    private CemuMemoryReader(IProcessMemoryBackend backend, long address, int pid)
    {
        _backend  = backend;
        _address  = address;
        ProcessId = pid;
    }

    internal static FileStream AcquireProducerLease(string path) => new(path,
        FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None, 4096, FileOptions.DeleteOnClose);

    public static CemuMemoryReader Attach(bool verbose = false, Action<string>? log = null, int? processId = null)
        => Attach(verbose, log, processId, null);

    internal static CemuMemoryReader Attach(bool verbose, Action<string>? log, int? processId, SafeFileHandle? inheritedHandle)
    {
        if (verbose && log is null) log = new ClientLog(true).Write;
        log?.Invoke("Searching for Cemu processes and a configured AP v2 mailbox.");

        bool isWindows = OperatingSystem.IsWindows();
        bool isLinux   = OperatingSystem.IsLinux();
        if (!isWindows && !isLinux)
            throw new PlatformNotSupportedException("Cemu attachment requires Linux or Windows.");

        foreach (var process in Process.GetProcesses()
            .Where(p => processId.HasValue
                ? p.Id == processId.Value
                : p.ProcessName.Equals("Cemu", StringComparison.OrdinalIgnoreCase)))
        {
            var timer  = Stopwatch.StartNew();
            long scanned = 0;

            log?.Invoke($"Scanning Cemu PID {process.Id}.");
            var producerLease = AcquireProducerLease(
                Path.Combine(Path.GetTempPath(), $"BotWAP-Cemu-{process.Id}.lock"));

            IProcessMemoryBackend? backend = null;
            bool selected = false;
            try
            {
                backend = isLinux
                    ? new LinuxProcessMemoryFull(process.Id, inheritedHandle)
                    : new WindowsProcessMemory(process.Id);

                byte[] buffer = new byte[1024 * 1024];

                foreach (var (start, end) in backend.WritableRegions())
                {
                    for (long position = start; position < end; position += buffer.Length - 7)
                    {
                        int toRead = (int)Math.Min(buffer.Length, end - position);
                        int read   = backend.Read(position, buffer.AsSpan(0, toRead));
                        if (read < 8) break;
                        scanned += read;

                        for (int i = 0; i <= read - 8; i++)
                        {
                            if (!buffer.AsSpan(i, 8).SequenceEqual("APMBBOTW"u8)) continue;

                            var candidate = new CemuMemoryReader(backend, position + i, process.Id);
                            try
                            {
                                using var identity = new MemoryStream(candidate.Read(Protocol.Get("extension_offset"), 16));
                                if (!identity.ToArray().AsSpan(0, 4).SequenceEqual("APV2"u8) ||
                                    candidate.ReadWord(Protocol.Get("configured_offset")) != 1) continue;
                                new Mailbox(candidate).Validate();
                                log?.Invoke(
                                    $"Cemu PID {process.Id}, mailbox 0x{position + i:X}; " +
                                    $"scanned {scanned / 1048576.0:F1} MiB in {timer.Elapsed.TotalSeconds:F2}s.");
                                candidate._producerLease = producerLease;
                                selected = true;
                                return candidate;
                            }
                            catch (Exception ex) when (ex is IOException or InvalidDataException)
                            {
                                log?.Invoke($"Rejected mailbox candidate 0x{position + i:X}: {ex.Message}");
                            }
                        }
                    }
                }
            }
            finally
            {
                if (!selected)
                {
                    try { backend?.Dispose(); }
                    finally { producerLease.Dispose(); }
                }
            }
        }

        throw new IOException("No configured AP v2 mailbox found. Load the seed's graphic pack in Cemu first.");
    }

    private uint ReadWord(int offset) => Protocol.Read(Read(offset, 4));

    private byte[] ReadAt(long hostAddress, int length)
    {
        if (hostAddress < 0) throw new InvalidDataException("Invalid guest memory address");
        byte[] bytes = new byte[length];
        int total = 0;
        while (total < length)
        {
            int count = _backend.Read(hostAddress + total, bytes.AsSpan(total));
            if (count == 0) throw new EndOfStreamException("Cemu memory is unavailable");
            total += count;
        }
        return bytes;
    }

    public byte[] Read(int offset, int length) => ReadAt(_address + offset, length);

    public byte[] ReadGuest(uint guestAddress, uint mailboxGuestAddress, int length)
    {
        if (mailboxGuestAddress == 0) throw new InvalidDataException("Guest mailbox address is not initialized");
        return ReadAt(_address + ((long)guestAddress - (long)mailboxGuestAddress), length);
    }

    public void Write(int offset, byte[] bytes) =>
        _backend.Write(_address + offset, bytes);

    public void Dispose()
    {
        try { _backend.Dispose(); }
        finally { _producerLease?.Dispose(); }
    }
}
