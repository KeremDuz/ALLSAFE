using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Allsafe.Agent.RemoteDesktop;

namespace Allsafe.Agent.Tests;

public sealed class RemoteDesktopTransportTests
{
    private const string DeviceId = "cf8e9b4d-40b3-4eaf-af2c-a43803b99c36";
    private const string SessionId = "a8d08b11-03b0-4455-8e09-585b700c0974";
    private const string Token = "desktop-test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private static readonly DeviceCredential Credential = new(new Uri("https://allsafe.example"), DeviceId, Token);

    [Fact]
    public async Task PendingAndDecisionBindIdentityAndBearerToSameOrigin()
    {
        List<Uri> requested = [];
        using var http = new HttpClient(new Handler(async request =>
        {
            requested.Add(request.RequestUri!);
            Assert.Equal("allsafe.example", request.RequestUri!.Host);
            Assert.Equal(new AuthenticationHeaderValue("Bearer", Token), request.Headers.Authorization);
            Assert.DoesNotContain(Token, request.RequestUri.AbsoluteUri, StringComparison.Ordinal);
            if (request.Method == HttpMethod.Get)
            {
                Assert.Equal("?device_id=" + DeviceId, request.RequestUri.Query);
                return Json(new { sessions = new[] { Session("pending") } });
            }
            using var document = JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
            Assert.Equal(DeviceId, document.RootElement.GetProperty("device_id").GetString());
            Assert.True(document.RootElement.GetProperty("approved").GetBoolean());
            return Json(Session("approved"));
        }));
        var api = new RemoteDesktopApi(http, Credential);
        Assert.Equal("operator@test.example", Assert.Single(await api.PendingAsync(CancellationToken.None)).OperatorName);
        Assert.Equal("approved", (await api.DecideAsync(SessionId, true, CancellationToken.None)).Status);
        Assert.Equal(2, requested.Count);
    }

    [Fact]
    public async Task AnotherDeviceResponseIsRejected()
    {
        using var http = new HttpClient(new Handler(_ => Task.FromResult(Json(new
        { sessions = new[] { Session("pending", Guid.NewGuid().ToString()) } }))));
        await Assert.ThrowsAsync<InvalidDataException>(() => new RemoteDesktopApi(http, Credential).PendingAsync(CancellationToken.None));
    }

    [Fact]
    public async Task OversizedAndAmbiguousResponsesFailClosed()
    {
        foreach (var body in new[] { new string(' ', 32 * 1024 + 1), "{\"sessions\":[],\"sessions\":[]}" })
        {
            using var http = new HttpClient(new Handler(_ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            { Content = new StringContent(body, Encoding.UTF8, "application/json") })));
            await Assert.ThrowsAsync<InvalidDataException>(() => new RemoteDesktopApi(http, Credential).PendingAsync(CancellationToken.None));
        }
    }

    [Fact]
    public async Task DefaultCookiesAndCredentialsCannotLeakIntoDesktopRequests()
    {
        using var http = new HttpClient(new Handler(_ => throw new InvalidOperationException("No request should be sent.")));
        http.DefaultRequestHeaders.Add("Cookie", "unrelated=session");
        await Assert.ThrowsAsync<InvalidDataException>(() => new RemoteDesktopApi(http, Credential).PendingAsync(CancellationToken.None));
    }

    [Theory]
    [InlineData(401, false)]
    [InlineData(403, false)]
    [InlineData(503, true)]
    public async Task RevocationIsPermanentAndServerFailureIsTransient(int status, bool transient)
    {
        using var http = new HttpClient(new Handler(_ => Task.FromResult(new HttpResponseMessage((HttpStatusCode)status))));
        var problem = await Assert.ThrowsAsync<AgentApiException>(() => new RemoteDesktopApi(http, Credential).PendingAsync(CancellationToken.None));
        Assert.Equal(transient, problem.IsTransient); Assert.DoesNotContain(Token, problem.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task WebSocketRedirectIsNeverFollowed()
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        using var redirect = new TcpListener(IPAddress.Loopback, 0);
        using var target = new TcpListener(IPAddress.Loopback, 0);
        redirect.Start(); target.Start();
        int originPort = ((IPEndPoint)redirect.LocalEndpoint).Port, targetPort = ((IPEndPoint)target.LocalEndpoint).Port;
        var serve = Task.Run(async () =>
        {
            using var client = await redirect.AcceptTcpClientAsync(timeout.Token);
            await using var stream = client.GetStream();
            byte[] buffer = new byte[4096];
            int length = 0;
            while (length < buffer.Length)
            {
                length += await stream.ReadAsync(buffer.AsMemory(length), timeout.Token);
                if (Encoding.ASCII.GetString(buffer, 0, length).Contains("\r\n\r\n", StringComparison.Ordinal)) break;
            }
            var response = Encoding.ASCII.GetBytes($"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{targetPort}/unexpected\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            await stream.WriteAsync(response, timeout.Token);
        }, timeout.Token);
        using var http = Program.CreateHttpClient();
        var credential = new DeviceCredential(new Uri($"http://127.0.0.1:{originPort}"), DeviceId, Token);
        await Assert.ThrowsAsync<WebSocketException>(() => new RemoteDesktopApi(http, credential).ConnectAsync(SessionId, timeout.Token));
        await serve;
        Assert.False(target.Pending());
    }

    private static object Session(string status, string device = DeviceId) => new
    {
        id = SessionId, device_id = device, operator_name = "operator@test.example", reason = "Test support",
        mode = "control", status, created_at = DateTimeOffset.UtcNow, expires_at = DateTimeOffset.UtcNow.AddMinutes(2), closed_reason = (string?)null
    };
    private static HttpResponseMessage Json(object body) => new(HttpStatusCode.OK)
    { Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json") };
    private sealed class Handler(Func<HttpRequestMessage, Task<HttpResponseMessage>> response) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => response(request);
    }
}
