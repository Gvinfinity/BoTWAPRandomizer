using System;
using System.Diagnostics;
using System.IO;

namespace BotWClient.Memory
{
    public class Scanner
    {
        public static void Run()
        {
            var processes = Process.GetProcessesByName("Cemu");
            if (processes.Length == 0) return;
            var proc = processes[0];
            var mapsFile = $"/proc/{proc.Id}/maps";
            var lines = File.ReadAllLines(mapsFile);
            
            using var fs = new FileStream($"/proc/{proc.Id}/mem", FileMode.Open, FileAccess.Read);
            
            foreach (var line in lines)
            {
                if (line.Contains("r-xp") || line.Contains("rwxp"))
                {
                    var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                    var addrRange = parts[0].Split('-');
                    ulong start = Convert.ToUInt64(addrRange[0], 16);
                    ulong end = Convert.ToUInt64(addrRange[1], 16);
                    ulong size = end - start;
                    
                    if (size > 100 * 1024 * 1024) continue;
                    
                    try {
                        fs.Position = (long)start;
                        byte[] chunk = new byte[8];
                        fs.Read(chunk, 0, 8);
                        
                        // We are looking for Application::calc -> 0x0303E4C0
                        // Since we don't know the host address of the .text segment, we can't easily find it.
                        // BUT wait, Cemu translates PPC to x86! 
                        // The PPC executable is STILL loaded in memory somewhere for reference/data!
                        
                    } catch {}
                }
            }
        }
    }
}
