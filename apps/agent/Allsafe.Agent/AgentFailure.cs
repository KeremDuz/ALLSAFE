namespace Allsafe.Agent;

public sealed class AgentApiException : Exception
{
    public AgentApiException(int? statusCode, bool isTransient, TimeSpan? retryAfter = null)
        : base(isTransient ? "ALLSAFE connection temporarily unavailable." : "ALLSAFE request rejected or response invalid.")
    {
        StatusCode = statusCode;
        IsTransient = isTransient;
        RetryAfter = isTransient && retryAfter is { } delay
            ? TimeSpan.FromSeconds(Math.Clamp(delay.TotalSeconds, 0, 300)) : null;
    }

    public int? StatusCode { get; }
    public bool IsTransient { get; }
    public TimeSpan? RetryAfter { get; }
}

public sealed class AgentCredentialException : Exception
{
    public AgentCredentialException() : base("Device credential could not be securely stored or loaded.") { }
}
