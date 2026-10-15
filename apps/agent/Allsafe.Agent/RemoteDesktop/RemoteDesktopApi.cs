using System.Net.Http.Headers;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text.Json;

namespace Allsafe.Agent.RemoteDesktop;

public sealed class RemoteDesktopApi(HttpClient http, DeviceCredential credential) : IRemoteDesktopApi
{
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };

    public async Task<IReadOnlyList<DesktopSession>> PendingAsync(CancellationToken cancellationToken)
    {
        using var response = await RequestAsync(HttpMethod.Get,
            "api/v1/agent/remote-desktop/pending?device_id=" + credential.DeviceId, null, cancellationToken).ConfigureAwait(false);
        var root = response.RootElement;
        if (!root.TryGetProperty("sessions", out var sessions) || sessions.ValueKind != JsonValueKind.Array || sessions.GetArrayLength() > 10)
            throw new InvalidDataException("Invalid remote desktop session response.");
        return sessions.EnumerateArray().Select(ParseSession).ToArray();
    }

    public async Task<DesktopSession> DecideAsync(string sessionId, bool approved, CancellationToken cancellationToken)
    {
        ValidateId(sessionId);
        using var response = await RequestAsync(HttpMethod.Post,
            $"api/v1/agent/remote-desktop/sessions/{sessionId}/decision", new { device_id = credential.DeviceId, approved }, cancellationToken).ConfigureAwait(false);
        return ParseSession(response.RootElement);
    }

    public async Task<IDesktopConnection> ConnectAsync(string sessionId, CancellationToken cancellationToken)
    {
        var socket = new ClientWebSocket();
        var invoker = new HttpMessageInvoker(new SocketsHttpHandler
        {
            AllowAutoRedirect = false, UseProxy = false, UseCookies = false,
            Credentials = null, MaxResponseHeadersLength = 16
        });
        socket.Options.Proxy = null;
        socket.Options.UseDefaultCredentials = false;
        socket.Options.Credentials = null;
        socket.Options.KeepAliveInterval = TimeSpan.FromSeconds(10);
        socket.Options.KeepAliveTimeout = TimeSpan.FromSeconds(10);
        socket.Options.SetRequestHeader("Authorization", "Bearer " + credential.AgentToken);
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(15));
            await socket.ConnectAsync(StreamUri(credential.ServerUri, sessionId), invoker, timeout.Token).ConfigureAwait(false);
            var connection = new DesktopConnection(socket, invoker);
            await connection.SendJsonAsync(new { type = "hello", device_id = credential.DeviceId }, cancellationToken).ConfigureAwait(false);
            return connection;
        }
        catch { socket.Dispose(); invoker.Dispose(); throw; }
    }

    internal static Uri StreamUri(Uri origin, string sessionId)
    {
        ValidateId(sessionId);
        var server = AgentServerUri.Parse(origin.AbsoluteUri, allowLoopbackHttp: true);
        return new UriBuilder(new Uri(server, $"api/v1/agent/remote-desktop/sessions/{sessionId}/stream"))
        { Scheme = server.Scheme == Uri.UriSchemeHttps ? "wss" : "ws" }.Uri;
    }

    private DesktopSession ParseSession(JsonElement body)
    {
        try
        {
            var result = body.Deserialize<DesktopSession>(JsonOptions) ?? throw new InvalidDataException();
            ValidateId(result.Id);
            if (result.DeviceId != credential.DeviceId || string.IsNullOrWhiteSpace(result.OperatorName) ||
                result.OperatorName.Length > 255 || result.OperatorName.Any(char.IsControl) || string.IsNullOrWhiteSpace(result.Reason) ||
                result.Reason.Length > 500 || result.Reason.Any(character => char.IsControl(character) && character is not '\n' and not '\r') ||
                result.Mode is not ("view" or "control") ||
                result.Status is not ("pending" or "approved" or "active" or "denied" or "closed" or "expired") ||
                result.CreatedAt == default || result.ExpiresAt <= result.CreatedAt)
                throw new InvalidDataException();
            return result;
        }
        catch (Exception problem) when (problem is JsonException or ArgumentException or InvalidDataException)
        { throw new InvalidDataException("Invalid remote desktop session response."); }
    }

    private async Task<JsonDocument> RequestAsync(HttpMethod method, string path, object? body, CancellationToken cancellationToken)
    {
        if (http.DefaultRequestHeaders.Authorization is not null || http.DefaultRequestHeaders.Contains("Cookie"))
            throw new InvalidDataException("Desktop client must not contain default credentials.");
        using var request = new HttpRequestMessage(method, new Uri(credential.ServerUri, path));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential.AgentToken);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (body is not null) request.Content = new StringContent(JsonSerializer.Serialize(body), System.Text.Encoding.UTF8, "application/json");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(20));
        try
        {
            using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                int status = (int)response.StatusCode;
                throw new AgentApiException(status, status is 408 or 429 || status >= 500);
            }
            if (response.Content.Headers.ContentLength > 32 * 1024 || response.Content.Headers.ContentType?.MediaType != "application/json")
                throw new InvalidDataException("Invalid remote desktop session response.");
            await using var stream = await response.Content.ReadAsStreamAsync(deadline.Token).ConfigureAwait(false);
            using var bytes = new MemoryStream();
            var buffer = new byte[4096];
            try
            {
                int read;
                while ((read = await stream.ReadAsync(buffer, deadline.Token).ConfigureAwait(false)) > 0)
                {
                    if (bytes.Length + read > 32 * 1024) throw new InvalidDataException("Remote desktop response is too large.");
                    bytes.Write(buffer, 0, read);
                }
                using var document = JsonDocument.Parse(bytes.GetBuffer().AsMemory(0, (int)bytes.Length), new JsonDocumentOptions { MaxDepth = 8 });
                RejectDuplicateProperties(document.RootElement);
                return JsonDocument.Parse(document.RootElement.GetRawText());
            }
            finally { CryptographicOperations.ZeroMemory(buffer); CryptographicOperations.ZeroMemory(bytes.GetBuffer()); }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested) { throw new AgentApiException(null, true); }
        catch (HttpRequestException) { throw new AgentApiException(null, true); }
    }

    private static void RejectDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new InvalidDataException("Ambiguous remote desktop response.");
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var item in element.EnumerateArray()) RejectDuplicateProperties(item);
    }

    private static void ValidateId(string id)
    {
        if (!Guid.TryParseExact(id, "D", out _)) throw new ArgumentException("A canonical session UUID is required.");
    }
}

internal sealed class DesktopConnection(ClientWebSocket socket, HttpMessageInvoker invoker) : IDesktopConnection
{
    public Task SendDisplayAsync(int width, int height, CancellationToken cancellationToken)
        => SendJsonAsync(new { type = "display", width, height }, cancellationToken);

    internal Task SendJsonAsync(object body, CancellationToken cancellationToken)
        => SendAsync(JsonSerializer.SerializeToUtf8Bytes(body), WebSocketMessageType.Text, cancellationToken);

    public Task SendFrameAsync(byte[] jpeg, CancellationToken cancellationToken)
    {
        if (jpeg.Length is 0 or > DesktopProtocol.MaximumFrameBytes) throw new InvalidDataException("Desktop frame exceeds the limit.");
        return SendAsync(jpeg, WebSocketMessageType.Binary, cancellationToken);
    }

    private async Task SendAsync(byte[] bytes, WebSocketMessageType type, CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(5));
        await socket.SendAsync(bytes.AsMemory(), type, true, timeout.Token).ConfigureAwait(false);
    }

    public async Task<DesktopInput?> ReceiveAsync(CancellationToken cancellationToken)
    {
        var bytes = new byte[DesktopProtocol.MaximumMessageBytes];
        int length = 0;
        try
        {
            while (true)
            {
                var received = await socket.ReceiveAsync(bytes.AsMemory(length), cancellationToken).ConfigureAwait(false);
                if (received.MessageType == WebSocketMessageType.Close) return null;
                if (received.MessageType != WebSocketMessageType.Text) throw new InvalidDataException("Unsupported desktop message.");
                length += received.Count;
                if (received.EndOfMessage) return DesktopProtocol.ParseInput(bytes.AsMemory(0, length));
                if (length >= bytes.Length) throw new InvalidDataException("Desktop message exceeds the limit.");
            }
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (socket.State == WebSocketState.Open)
            {
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(1));
                await SendJsonAsync(new { type = "stop" }, deadline.Token).ConfigureAwait(false);
                await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "Local session ended", deadline.Token).ConfigureAwait(false);
            }
        }
        catch (Exception problem) when (problem is WebSocketException or OperationCanceledException or ObjectDisposedException) { }
        finally { socket.Abort(); socket.Dispose(); invoker.Dispose(); }
    }
}
