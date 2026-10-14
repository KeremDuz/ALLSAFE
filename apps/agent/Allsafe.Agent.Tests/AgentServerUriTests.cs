namespace Allsafe.Agent.Tests;

public sealed class AgentServerUriTests
{
    [Theory]
    [InlineData("https://allsafe.example")]
    [InlineData("https://allsafe.example/")]
    [InlineData("https://allsafe.example:8443/")]
    [InlineData("https://127.0.0.1/")]
    public void HttpsRootIsAccepted(string input)
    {
        Uri server = AgentServerUri.Parse(input, allowLoopbackHttp: false);

        Assert.Equal(Uri.UriSchemeHttps, server.Scheme);
        Assert.Equal("/", server.AbsolutePath);
        Assert.Equal(string.Empty, server.UserInfo);
    }

    [Theory]
    [InlineData("http://localhost:8000")]
    [InlineData("http://127.0.0.1:8000/")]
    [InlineData("http://[::1]:8000/")]
    public void LoopbackHttpRequiresExplicitDevelopmentOptIn(string input)
    {
        Assert.Throws<ArgumentException>(() => AgentServerUri.Parse(input, false));
        Assert.True(AgentServerUri.Parse(input, true).IsLoopback);
    }

    [Theory]
    [InlineData("http://allsafe.example/", true)]
    [InlineData("http://192.168.1.42:8000/", true)]
    [InlineData("ftp://allsafe.example/", true)]
    [InlineData("file:///C:/agent.json", true)]
    [InlineData("https://user:password@allsafe.example/", false)]
    [InlineData("https://allsafe.example/api/", false)]
    [InlineData("https://allsafe.example/?token=secret", false)]
    [InlineData("https://allsafe.example/#secret", false)]
    [InlineData("https://allsafe.example/%2Fapi", false)]
    [InlineData("/api/v1/", false)]
    [InlineData("", false)]
    public void UnsafeOrAmbiguousServerAddressIsRejected(string input, bool allowHttp)
    {
        Assert.Throws<ArgumentException>(() => AgentServerUri.Parse(input, allowHttp));
    }

    [Fact]
    public void CredentialDiagnosticTextDoesNotRevealDeviceToken()
    {
        const string token = "private-device-token-7b60acf130ee";
        DeviceCredential credential = new(new Uri("https://allsafe.example/"), Guid.NewGuid().ToString(), token);

        Assert.DoesNotContain(token, credential.ToString(), StringComparison.Ordinal);
    }
}
