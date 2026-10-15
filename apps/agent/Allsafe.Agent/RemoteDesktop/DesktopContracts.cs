using System.Text.Json;

namespace Allsafe.Agent.RemoteDesktop;

public sealed record DesktopSession(string Id, string DeviceId, string OperatorName, string Reason,
    string Mode, string Status, DateTimeOffset CreatedAt, DateTimeOffset ExpiresAt, string? ClosedReason);

public sealed record DesktopFrame(int Width, int Height, byte[] Jpeg);

public sealed record DesktopInput(string Type, string? Action = null, double X = 0, double Y = 0,
    string? Button = null, int Delta = 0, string? Code = null);

public interface IRemoteDesktopApi
{
    Task<IReadOnlyList<DesktopSession>> PendingAsync(CancellationToken cancellationToken);
    Task<DesktopSession> DecideAsync(string sessionId, bool approved, CancellationToken cancellationToken);
    Task<IDesktopConnection> ConnectAsync(string sessionId, CancellationToken cancellationToken);
}

public interface IDesktopConnection : IAsyncDisposable
{
    Task SendDisplayAsync(int width, int height, CancellationToken cancellationToken);
    Task SendFrameAsync(byte[] jpeg, CancellationToken cancellationToken);
    Task<DesktopInput?> ReceiveAsync(CancellationToken cancellationToken);
}

public interface IDesktopSurface
{
    bool IsAvailable { get; }
    void SetSharingEnabled(bool enabled);
    DesktopFrame Capture();
    void Apply(DesktopInput input);
    void ReleaseAll();
}

public interface IDesktopConsent
{
    Task<bool> AskAsync(DesktopSession session, CancellationToken cancellationToken);
    Task ActiveAsync(DesktopSession session, Action stop, CancellationToken cancellationToken);
    void Idle(string message);
}

public static class DesktopProtocol
{
    public const int MaximumMessageBytes = 4096;
    public const int MaximumFrameBytes = 768 * 1024;
    public const int MaximumWidth = 1920;
    public const int MaximumHeight = 1080;
    private static readonly HashSet<string> Keys = BuildKeys();

    public static bool IsAllowedKey(string code) => Keys.Contains(code);

    public static DesktopInput ParseInput(ReadOnlyMemory<byte> bytes)
    {
        if (bytes.Length is 0 or > MaximumMessageBytes) throw new InvalidDataException("Invalid desktop input.");
        try
        {
            using var json = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 2 });
            var root = json.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Invalid desktop input.");
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in root.EnumerateObject())
                if (!names.Add(property.Name)) throw new InvalidDataException("Ambiguous desktop input.");
            string type = root.GetProperty("type").GetString() ?? "";
            switch (type)
            {
                case "stop":
                case "release":
                case "ready":
                    ExactProperties(names, "type");
                    return new DesktopInput(type);
                case "closed":
                    ExactProperties(names, "type", "reason");
                    string? reason = root.GetProperty("reason").GetString();
                    if (reason is null || reason.Length > 128 || reason.Any(char.IsControl)) throw new InvalidDataException("Invalid desktop closure.");
                    return new DesktopInput("stop");
                case "pointer":
                    ExactProperties(names, "type", "action", "x", "y", "button");
                    var action = root.GetProperty("action").GetString();
                    var button = root.GetProperty("button").GetString();
                    double x = root.GetProperty("x").GetDouble(), y = root.GetProperty("y").GetDouble();
                    if (action is not ("move" or "down" or "up") || button is not ("left" or "right" or "middle") ||
                        !double.IsFinite(x) || !double.IsFinite(y) || x is < 0 or > 1 || y is < 0 or > 1)
                        throw new InvalidDataException("Invalid desktop input.");
                    return new DesktopInput(type, action, x, y, button);
                case "wheel":
                    ExactProperties(names, "type", "delta");
                    int delta = root.GetProperty("delta").GetInt32();
                    if (delta is < -1200 or > 1200) throw new InvalidDataException("Invalid desktop input.");
                    return new DesktopInput(type, Delta: delta);
                case "key":
                    ExactProperties(names, "type", "action", "code");
                    string? keyAction = root.GetProperty("action").GetString(), code = root.GetProperty("code").GetString();
                    if (keyAction is not ("down" or "up") || code is null || !Keys.Contains(code))
                        throw new InvalidDataException("Invalid desktop input.");
                    return new DesktopInput(type, keyAction, Code: code);
                default: throw new InvalidDataException("Unsupported desktop input.");
            }
        }
        catch (Exception problem) when (problem is JsonException or InvalidOperationException or KeyNotFoundException or FormatException or OverflowException)
        { throw new InvalidDataException("Invalid desktop input."); }
    }

    private static void ExactProperties(HashSet<string> actual, params string[] expected)
    {
        if (!actual.SetEquals(expected)) throw new InvalidDataException("Unsupported desktop input fields.");
    }

    private static HashSet<string> BuildKeys()
    {
        var keys = new HashSet<string>(StringComparer.Ordinal)
        {
            "Backspace", "Tab", "Enter", "Escape", "Space", "Delete", "Insert", "Home", "End",
            "PageUp", "PageDown", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
            "ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight",
            "CapsLock", "NumLock", "NumpadAdd", "NumpadSubtract", "NumpadMultiply", "NumpadDivide", "NumpadDecimal", "NumpadEnter",
            "Minus", "Equal", "BracketLeft", "BracketRight",
            "Backslash", "Semicolon", "Quote", "Backquote", "Comma", "Period", "Slash"
        };
        for (char letter = 'A'; letter <= 'Z'; letter++) keys.Add("Key" + letter);
        for (int digit = 0; digit <= 9; digit++) keys.Add("Digit" + digit);
        for (int digit = 0; digit <= 9; digit++) keys.Add("Numpad" + digit);
        for (int number = 1; number <= 12; number++) keys.Add("F" + number);
        return keys;
    }
}
