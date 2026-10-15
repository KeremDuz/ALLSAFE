using System.Runtime.InteropServices;

namespace Allsafe.Agent;

public sealed class WindowsInventoryProvider : IInventoryProvider
{
    public InventorySnapshot Collect()
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("ALLSAFE Agent requires Windows.");
        var os = RuntimeInformation.OSDescription;
        if (os.Length > 255) os = os[..255];
        var processors = GetActiveProcessorCount(0xffff);
        int? cpuCount = processors is >= 1 and <= 4096 ? (int)processors : null;
        var memory = new MemoryStatus { Length = (uint)Marshal.SizeOf<MemoryStatus>() };
        long? memoryBytes = GlobalMemoryStatusEx(ref memory) && memory.TotalPhysical is > 0 and <= long.MaxValue
            ? (long)memory.TotalPhysical : null;
        return new InventorySnapshot(os, cpuCount, memoryBytes);
    }

    [DllImport("kernel32.dll")]
    private static extern uint GetActiveProcessorCount(ushort groupNumber);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GlobalMemoryStatusEx(ref MemoryStatus status);

    [StructLayout(LayoutKind.Sequential)]
    private struct MemoryStatus
    {
        public uint Length;
        public uint MemoryLoad;
        public ulong TotalPhysical;
        public ulong AvailablePhysical;
        public ulong TotalPageFile;
        public ulong AvailablePageFile;
        public ulong TotalVirtual;
        public ulong AvailableVirtual;
        public ulong AvailableExtendedVirtual;
    }
}
