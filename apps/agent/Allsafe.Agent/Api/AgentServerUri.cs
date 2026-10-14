using System.Net;

namespace Allsafe.Agent;

public static class AgentServerUri
{
    public static Uri Parse(string value, bool allowLoopbackHttp)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) ||
            string.IsNullOrWhiteSpace(uri.Host) || uri.UserInfo.Length != 0 ||
            uri.Query.Length != 0 || uri.Fragment.Length != 0 || uri.AbsolutePath != "/" ||
            value.Contains('@') || value.Contains('?') || value.Contains('#'))
            throw new ArgumentException("ALLSAFE server must be an absolute origin without credentials or a path.", nameof(value));

        var loopback = uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
            (IPAddress.TryParse(uri.Host.Trim('[', ']'), out var address) && IPAddress.IsLoopback(address));
        if (uri.Scheme != Uri.UriSchemeHttps &&
            !(allowLoopbackHttp && uri.Scheme == Uri.UriSchemeHttp && loopback))
            throw new ArgumentException("HTTPS is required; HTTP is allowed only for an explicitly enabled loopback lab.", nameof(value));

        return new Uri(uri.GetLeftPart(UriPartial.Authority) + "/", UriKind.Absolute);
    }
}
