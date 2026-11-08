using System.ComponentModel;
using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using Microsoft.Extensions.Hosting.WindowsServices;

namespace Allsafe.Agent.RemoteDesktop;

public sealed class NativeDesktopSurface : IDesktopSurface
{
    private readonly object _gate = new();
    private readonly HashSet<string> _pressedKeys = new(StringComparer.Ordinal);
    private readonly HashSet<string> _pressedButtons = new(StringComparer.Ordinal);
    private bool _sharingEnabled;

    public static void RequireInteractiveUser(bool development, bool unattended = false)
    {
        if (!OperatingSystem.IsWindows() || WindowsServiceHelpers.IsWindowsService() ||
            !Environment.UserInteractive || Process.GetCurrentProcess().SessionId == 0)
            throw new ArgumentException("Remote desktop requires an explicitly launched interactive Windows session; it cannot run as a service.");
        DesktopAccessPolicy.RequireAdministrator(development, unattended, IsElevated);
        if (!DesktopAvailable()) throw new ArgumentException("An active, unlocked Default desktop is required.");
    }

    public static bool IsElevated
    {
        get
        {
            using var identity = WindowsIdentity.GetCurrent();
            return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
        }
    }

    public bool IsAvailable => DesktopAvailable();

    public void SetSharingEnabled(bool enabled)
    {
        lock (_gate)
        {
            if (enabled) EnsureAvailable();
            _sharingEnabled = enabled;
            if (!enabled) ReleaseAll();
        }
    }

    public DesktopFrame Capture()
    {
        lock (_gate)
        {
            if (!_sharingEnabled) throw new InvalidDataException("Local sharing permission is inactive.");
            EnsureAvailable();
            int width = GetSystemMetrics(0), height = GetSystemMetrics(1);
            if (width is < 1 or > 32768 || height is < 1 or > 32768 || (long)width * height > 64_000_000)
                throw new InvalidDataException("Primary display dimensions are unsupported.");
            using var original = new Bitmap(width, height, PixelFormat.Format24bppRgb);
            using (var graphics = Graphics.FromImage(original))
                graphics.CopyFromScreen(0, 0, 0, 0, original.Size, CopyPixelOperation.SourceCopy);
            EnsureAvailable();
            return EncodeFrame(original);
        }
    }

    // Takes an already acquired bitmap; tests can verify the codec without capturing a real desktop.
    internal static DesktopFrame EncodeFrame(Bitmap original)
    {
        var size = ScaledSize(original.Width, original.Height);
        using var scaled = new Bitmap(size.Width, size.Height, PixelFormat.Format24bppRgb);
        using (var graphics = Graphics.FromImage(scaled))
        {
            graphics.InterpolationMode = InterpolationMode.HighQualityBilinear;
            graphics.DrawImage(original, new Rectangle(Point.Empty, size));
        }
        var encoder = ImageCodecInfo.GetImageEncoders().Single(item => item.FormatID == ImageFormat.Jpeg.Guid);
        foreach (long quality in new long[] { 60, 40, 20 })
        {
            using var bytes = new MemoryStream();
            using var parameters = new EncoderParameters(1);
            parameters.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, quality);
            try
            {
                scaled.Save(bytes, encoder, parameters);
                if (bytes.Length <= DesktopProtocol.MaximumFrameBytes)
                    return new DesktopFrame(size.Width, size.Height, bytes.ToArray());
            }
            finally { CryptographicOperations.ZeroMemory(bytes.GetBuffer()); }
        }
        throw new InvalidDataException("Compressed desktop frame exceeds the limit.");
    }

    internal static Size ScaledSize(int width, int height)
    {
        if (width <= 0 || height <= 0) throw new ArgumentException("Display size must be positive.");
        double scale = Math.Min(1, Math.Min(1280.0 / width, 720.0 / height));
        return new Size(Math.Max(1, (int)Math.Round(width * scale)), Math.Max(1, (int)Math.Round(height * scale)));
    }

    public void Apply(DesktopInput input)
    {
        lock (_gate)
        {
            if (!_sharingEnabled) throw new InvalidDataException("Local sharing permission is inactive.");
            EnsureAvailable();
            if (input.Type == "release") { ReleaseAll(); return; }
            if (input.Type == "pointer")
            {
                if (!double.IsFinite(input.X) || !double.IsFinite(input.Y) || input.X is < 0 or > 1 || input.Y is < 0 or > 1 ||
                    input.Action is not ("move" or "down" or "up") || input.Button is not ("left" or "right" or "middle"))
                    throw new InvalidDataException("Unsupported pointer input.");
                var move = MouseInput(0x8001, (int)Math.Round(input.X * 65535), (int)Math.Round(input.Y * 65535));
                // Without VIRTUALDESK, normalized coordinates address the primary monitor only.
                Inject(move);
                if (input.Action == "down")
                {
                    _pressedButtons.Add(input.Button);
                    Inject(MouseInput(ButtonFlag(input.Button, up: false)));
                }
                else if (input.Action == "up")
                {
                    Inject(MouseInput(ButtonFlag(input.Button, up: true)));
                    _pressedButtons.Remove(input.Button);
                }
            }
            else if (input.Type == "wheel")
            {
                if (input.Delta is < -1200 or > 1200) throw new InvalidDataException("Unsupported wheel input.");
                Inject(MouseInput(0x0800, data: unchecked((uint)input.Delta)));
            }
            else if (input.Type == "key" && input.Code is not null && DesktopProtocol.IsAllowedKey(input.Code) && input.Action is "down" or "up")
            {
                bool up = input.Action == "up";
                if (!up) _pressedKeys.Add(input.Code);
                Inject(KeyInput(input.Code, up));
                if (up) _pressedKeys.Remove(input.Code);
            }
            else throw new InvalidDataException("Unsupported desktop input.");
        }
    }

    public void ReleaseAll()
    {
        lock (_gate)
        {
            // Secure desktops reject SendInput. Keep pending releases until the Default
            // desktop returns; the coordinator retries while this visible app stays open.
            if (!DesktopAvailable()) return;
            foreach (var code in _pressedKeys.OrderBy(IsModifier).ToArray())
                if (TryInject(KeyInput(code, up: true))) _pressedKeys.Remove(code);
            foreach (var button in _pressedButtons.ToArray())
                if (TryInject(MouseInput(ButtonFlag(button, up: true)))) _pressedButtons.Remove(button);
        }
    }

    private static bool IsModifier(string code) => code.StartsWith("Shift", StringComparison.Ordinal) ||
        code.StartsWith("Control", StringComparison.Ordinal) || code.StartsWith("Alt", StringComparison.Ordinal) || code.StartsWith("Meta", StringComparison.Ordinal);

    private static void EnsureAvailable()
    {
        if (!DesktopAvailable()) throw new InvalidDataException("Interactive desktop is locked, disconnected or unavailable.");
    }

    private static bool DesktopAvailable()
    {
        if (!OperatingSystem.IsWindows() || !Environment.UserInteractive || Process.GetCurrentProcess().SessionId == 0) return false;
        IntPtr state = IntPtr.Zero, desktop = IntPtr.Zero;
        try
        {
            if (!WTSQuerySessionInformationW(IntPtr.Zero, Process.GetCurrentProcess().SessionId, 8, out state, out int bytes) ||
                bytes < sizeof(int) || Marshal.ReadInt32(state) != 0) return false;
            var threadDesktop = GetThreadDesktop(GetCurrentThreadId());
            int receivesInput = 0;
            if (threadDesktop == IntPtr.Zero || !GetUserObjectInformationW(threadDesktop, 6, ref receivesInput, sizeof(int), out _) || receivesInput == 0)
                return false;
            desktop = OpenInputDesktop(0, false, 0x0001);
            if (desktop == IntPtr.Zero) return false;
            var name = new StringBuilder(256);
            return GetUserObjectInformationName(desktop, 2, name, name.Capacity * sizeof(char), out _) &&
                name.ToString().Equals("Default", StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            if (state != IntPtr.Zero) WTSFreeMemory(state);
            if (desktop != IntPtr.Zero) CloseDesktop(desktop);
        }
    }

    private static uint ButtonFlag(string button, bool up) => (button, up) switch
    { ("left", false) => 0x0002, ("left", true) => 0x0004, ("right", false) => 0x0008, ("right", true) => 0x0010,
      ("middle", false) => 0x0020, ("middle", true) => 0x0040, _ => throw new InvalidDataException("Unsupported pointer button.") };

    private static Input MouseInput(uint flags, int x = 0, int y = 0, uint data = 0) => new()
    { Type = 0, Data = new InputUnion { Mouse = new Mouse { X = x, Y = y, MouseData = data, Flags = flags } } };

    private static Input KeyInput(string code, bool up)
    {
        ushort key = VirtualKey(code);
        uint scan = MapVirtualKeyW(key, 0);
        if (scan == 0) throw new InvalidDataException("Unsupported keyboard key.");
        bool extended = code is "ControlRight" or "AltRight" or "MetaLeft" or "MetaRight" or "Delete" or "Insert" or
            "Home" or "End" or "PageUp" or "PageDown" or "ArrowLeft" or "ArrowRight" or "ArrowUp" or "ArrowDown" or "NumpadDivide" or "NumpadEnter" or "NumLock";
        return new Input
        {
            Type = 1,
            Data = new InputUnion { Keyboard = new Keyboard { Scan = (ushort)scan, Flags = 0x0008u | (up ? 0x0002u : 0) | (extended ? 1u : 0) } }
        };
    }

    private static ushort VirtualKey(string code)
    {
        if (code.StartsWith("Key", StringComparison.Ordinal) && code.Length == 4) return code[3];
        if (code.StartsWith("Digit", StringComparison.Ordinal) && code.Length == 6) return code[5];
        if (code.StartsWith("Numpad", StringComparison.Ordinal) && code.Length == 7 && char.IsAsciiDigit(code[6])) return (ushort)(0x60 + code[6] - '0');
        if (code.StartsWith('F') && int.TryParse(code.AsSpan(1), out int number) && number is >= 1 and <= 12) return (ushort)(0x6F + number);
        return code switch
        {
            "Backspace" => 0x08, "Tab" => 0x09, "Enter" => 0x0D, "Escape" => 0x1B, "Space" => 0x20,
            "Delete" => 0x2E, "Insert" => 0x2D, "Home" => 0x24, "End" => 0x23, "PageUp" => 0x21, "PageDown" => 0x22,
            "ArrowLeft" => 0x25, "ArrowRight" => 0x27, "ArrowUp" => 0x26, "ArrowDown" => 0x28,
            "ShiftLeft" => 0xA0, "ShiftRight" => 0xA1, "ControlLeft" => 0xA2, "ControlRight" => 0xA3,
            "AltLeft" => 0xA4, "AltRight" => 0xA5, "CapsLock" => 0x14, "NumLock" => 0x90,
            "NumpadAdd" => 0x6B, "NumpadSubtract" => 0x6D, "NumpadMultiply" => 0x6A,
            "NumpadDivide" => 0x6F, "NumpadDecimal" => 0x6E, "NumpadEnter" => 0x0D,
            "Minus" => 0xBD, "Equal" => 0xBB, "BracketLeft" => 0xDB, "BracketRight" => 0xDD,
            "Backslash" => 0xDC, "Semicolon" => 0xBA, "Quote" => 0xDE, "Backquote" => 0xC0,
            "Comma" => 0xBC, "Period" => 0xBE, "Slash" => 0xBF,
            _ => throw new InvalidDataException("Unsupported keyboard key.")
        };
    }

    private static void Inject(Input value)
    {
        if (!TryInject(value)) throw new Win32Exception("Windows rejected remote input; the session must stop.");
    }
    private static bool TryInject(Input value) => SendInput(1, [value], Marshal.SizeOf<Input>()) == 1;

    internal static int NativeInputSize => Marshal.SizeOf<Input>();
    [StructLayout(LayoutKind.Sequential)] private struct Input { public uint Type; public InputUnion Data; }
    [StructLayout(LayoutKind.Explicit)] private struct InputUnion
    { [FieldOffset(0)] public Mouse Mouse; [FieldOffset(0)] public Keyboard Keyboard; [FieldOffset(0)] public Hardware Hardware; }
    [StructLayout(LayoutKind.Sequential)] private struct Mouse
    { public int X, Y; public uint MouseData, Flags, Time; public UIntPtr Extra; }
    [StructLayout(LayoutKind.Sequential)] private struct Keyboard
    { public ushort VirtualKey, Scan; public uint Flags, Time; public UIntPtr Extra; }
    [StructLayout(LayoutKind.Sequential)] private struct Hardware { public uint Message; public ushort Low, High; }

    [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, Input[] inputs, int size);
    [DllImport("user32.dll")] private static extern uint MapVirtualKeyW(uint code, uint type);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] private static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr OpenInputDesktop(uint flags, [MarshalAs(UnmanagedType.Bool)] bool inherit, uint access);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetUserObjectInformationW(IntPtr handle, int index, ref int information, int length, out int needed);
    [DllImport("user32.dll", EntryPoint = "GetUserObjectInformationW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetUserObjectInformationName(IntPtr handle, int index, StringBuilder information, int length, out int needed);
    [DllImport("wtsapi32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSQuerySessionInformationW(IntPtr server, int sessionId, int infoClass, out IntPtr information, out int length);
    [DllImport("wtsapi32.dll")] private static extern void WTSFreeMemory(IntPtr memory);
}
