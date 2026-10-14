using System.Net;
using System.Net.Sockets;
using System.Text;

namespace Allsafe.Agent.Tests;

public sealed class HttpTransportTests
{
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
    {
        using TcpClient connection = await listener.AcceptTcpClientAsync(token);
        await using NetworkStream stream = connection.GetStream();
        using StreamReader reader = new(stream, Encoding.ASCII, leaveOpen: true);
        while (await reader.ReadLineAsync(token) is { Length: > 0 }) { }
        byte[] response = Encoding.ASCII.GetBytes(
            $"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{destinationPort}/collect\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        await stream.WriteAsync(response, token);
        await stream.FlushAsync(token);
    }
}
