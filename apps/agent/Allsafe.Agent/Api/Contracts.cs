namespace Allsafe.Agent;

public sealed class DeviceCredential
{
    public DeviceCredential(Uri serverUri, string deviceId, string agentToken)
    {
        ArgumentNullException.ThrowIfNull(serverUri);
        ServerUri = AgentServerUri.Parse(serverUri.AbsoluteUri, allowLoopbackHttp: true);
        if (!Guid.TryParseExact(deviceId, "D", out var id))
            throw new ArgumentException("A canonical device UUID is required.", nameof(deviceId));
        if (string.IsNullOrWhiteSpace(agentToken) || agentToken.Length < 32 || agentToken.Length > 128 || agentToken.Any(char.IsWhiteSpace))
            throw new ArgumentException("A valid device credential is required.", nameof(agentToken));
        DeviceId = id.ToString("D");
        AgentToken = agentToken;
    }

    public Uri ServerUri { get; }
    public string DeviceId { get; }
    public string AgentToken { get; }
    public override string ToString() => $"DeviceCredential {{ DeviceId = {DeviceId}, AgentToken = [REDACTED] }}";
}

public sealed record InventorySnapshot(string? OsVersion, int? CpuCount, long? MemoryTotalBytes);
