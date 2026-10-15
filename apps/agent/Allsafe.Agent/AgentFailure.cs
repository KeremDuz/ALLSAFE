namespace Allsafe.Agent;

public sealed class AgentApiException : Exception
{
    public AgentApiException(int? statusCode, bool isTransient)
        : base(isTransient ? "ALLSAFE connection temporarily unavailable." : "ALLSAFE request rejected or response invalid.")
    {
        StatusCode = statusCode;
        IsTransient = isTransient;
    }

    public int? StatusCode { get; }
    public bool IsTransient { get; }
}

public sealed class AgentCredentialException : Exception
{
    public AgentCredentialException() : base("Device credential could not be securely stored or loaded.") { }
}
