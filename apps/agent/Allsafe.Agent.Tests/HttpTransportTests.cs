using System.Net;
using System.Net.Sockets;
using System.Text;

namespace Allsafe.Agent.Tests;

[CollectionDefinition("HTTP transport", DisableParallelization = true)]
public sealed class HttpTransportCollection { }

[Collection("HTTP transport")]
public sealed class HttpTransportTests
{
    [Fact]
    public async Task ConfiguredHttpClientDoesNotUseTheMachineProxy()
    {
        using TcpListener origin = new(IPAddress.Loopback, 0);
        origin.Start();
        int originPort = ((IPEndPoint)origin.LocalEndpoint).Port;
        using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(10));
        IWebProxy originalProxy = HttpClient.DefaultProxy;
        try
        {
            // A proxy that throws even for loopback proves that no proxy decision is consulted.
            HttpClient.DefaultProxy = new RejectingProxy();
            using HttpClient client = Program.CreateHttpClient();
            Task serve = ServeResponseAsync(origin, "HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", deadline.Token);

            using HttpResponseMessage response = await client.GetAsync($"http://127.0.0.1:{originPort}/", deadline.Token);
            await serve;

            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        }
        finally
        {
            HttpClient.DefaultProxy = originalProxy;
        }
    }

    [Fact]
    public async Task ConfiguredHttpClientDoesNotFollowRedirectToAnotherOrigin()
    {
        using TcpListener origin = new(IPAddress.Loopback, 0);
        using TcpListener destination = new(IPAddress.Loopback, 0);
        origin.Start();
        destination.Start();
        int originPort = ((IPEndPoint)origin.LocalEndpoint).Port;
        int destinationPort = ((IPEndPoint)destination.LocalEndpoint).Port;
        using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(10));
        Task serve = ServeRedirectAsync(origin, destinationPort, deadline.Token);
        using HttpClient client = Program.CreateHttpClient();

        using HttpResponseMessage response = await client.GetAsync($"http://127.0.0.1:{originPort}/", deadline.Token);
        await serve;

        Assert.Equal(HttpStatusCode.Found, response.StatusCode);
        Assert.False(destination.Pending());
    }

    private static async Task ServeRedirectAsync(TcpListener listener, int destinationPort, CancellationToken token)
        => await ServeResponseAsync(listener,
            $"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{destinationPort}/collect\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", token);

    private static async Task ServeResponseAsync(TcpListener listener, string rawResponse, CancellationToken token)
    {
        using TcpClient connection = await listener.AcceptTcpClientAsync(token);
        await using NetworkStream stream = connection.GetStream();
        using StreamReader reader = new(stream, Encoding.ASCII, leaveOpen: true);
        while (await reader.ReadLineAsync(token) is { Length: > 0 }) { }
        byte[] response = Encoding.ASCII.GetBytes(rawResponse);
        await stream.WriteAsync(response, token);
        await stream.FlushAsync(token);
    }

    private sealed class RejectingProxy : IWebProxy
    {
        public ICredentials? Credentials { get; set; }
        public Uri? GetProxy(Uri destination) => throw new InvalidOperationException("Agent consulted the machine proxy.");
        public bool IsBypassed(Uri host) => throw new InvalidOperationException("Agent consulted the machine proxy.");
    }
}
