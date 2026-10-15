using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Allsafe.Agent;

public sealed class AgentApiClient : IAgentHeartbeatClient
{
    private const int MaximumResponseBytes = 32 * 1024;
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };
    private readonly HttpClient _client;

    public AgentApiClient(HttpClient client)
    {
        ArgumentNullException.ThrowIfNull(client);
        RejectDefaultCredentials(client);
        _client = client;
    }

    public async Task<DeviceCredential> EnrollAsync(Uri serverUri, string enrollmentToken, string hostname,
        string agentVersion, CancellationToken cancellationToken = default)
    {
        var server = AgentServerUri.Parse(serverUri.AbsoluteUri, allowLoopbackHttp: true);
        ValidateText(enrollmentToken, 32, 128);
        ValidateText(hostname, 1, 255);
        ValidateText(agentVersion, 1, 64);
        using var request = CreateRequest(server, "api/v1/agent/enroll",
            new EnrollmentRequest(enrollmentToken, hostname, "windows", agentVersion));
        using var response = await SendAsync(request, 201, cancellationToken).ConfigureAwait(false);
        try
        {
            using var payload = ParseResponse(response.Bytes);
            var body = payload.RootElement;
            if (body.ValueKind != JsonValueKind.Object ||
                !body.TryGetProperty("device_id", out var deviceId) || deviceId.ValueKind != JsonValueKind.String ||
                !body.TryGetProperty("agent_token", out var agentToken) || agentToken.ValueKind != JsonValueKind.String)
                throw new AgentApiException(201, false);
            return new DeviceCredential(server, deviceId.GetString()!, agentToken.GetString()!);
        }
        catch (Exception error) when (error is JsonException or ArgumentException)
        {
            throw new AgentApiException(201, false);
        }
    }

    public async Task HeartbeatAsync(DeviceCredential credential, string agentVersion,
        InventorySnapshot? inventory, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(credential);
        ValidateText(agentVersion, 1, 64);
        if (inventory is not null && (inventory.OsVersion?.Length > 255 || inventory.CpuCount is < 1 or > 4096 ||
            inventory.MemoryTotalBytes is < 0))
            throw new ArgumentException("Inventory is outside the API contract.", nameof(inventory));
        using var request = CreateRequest(credential.ServerUri, "api/v1/agent/heartbeat",
            new HeartbeatRequest(credential.DeviceId, agentVersion, inventory));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential.AgentToken);
        using var response = await SendAsync(request, 200, cancellationToken).ConfigureAwait(false);
        try
        {
            using var payload = ParseResponse(response.Bytes);
            if (payload.RootElement.ValueKind != JsonValueKind.Object ||
                !payload.RootElement.TryGetProperty("device_id", out var deviceId) ||
                deviceId.ValueKind != JsonValueKind.String || deviceId.GetString() != credential.DeviceId)
                throw new AgentApiException(200, false);
        }
        catch (JsonException)
        {
            throw new AgentApiException(200, false);
        }
    }

    private static HttpRequestMessage CreateRequest<T>(Uri server, string path, T payload)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, new Uri(server, path));
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Content = new ProtectedJsonContent(JsonSerializer.SerializeToUtf8Bytes(payload, JsonOptions));
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
        return request;
    }

    private async Task<BoundedResponse> SendAsync(HttpRequestMessage request, int expectedStatus,
        CancellationToken cancellationToken)
    {
        RejectDefaultCredentials(_client);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var timeout = _client.Timeout;
        deadline.CancelAfter(timeout == Timeout.InfiniteTimeSpan || timeout > TimeSpan.FromSeconds(30)
            ? TimeSpan.FromSeconds(30) : timeout);
        try
        {
            using var response = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead,
                deadline.Token).ConfigureAwait(false);
            var statusCode = (int)response.StatusCode;
            if (statusCode != expectedStatus)
                throw new AgentApiException(statusCode, statusCode is 408 or 429 || statusCode >= 500,
                    statusCode is 429 or 503 ? ReadRetryAfter(response) : null);
            var mediaType = response.Content.Headers.ContentType?.MediaType;
            if (mediaType is null || !(mediaType.Equals("application/json", StringComparison.OrdinalIgnoreCase) ||
                (mediaType.StartsWith("application/", StringComparison.OrdinalIgnoreCase) &&
                 mediaType.EndsWith("+json", StringComparison.OrdinalIgnoreCase))))
                throw new AgentApiException(statusCode, false);
            if (response.Content.Headers.ContentLength > MaximumResponseBytes)
                throw new AgentApiException(statusCode, false);
            await using var stream = await response.Content.ReadAsStreamAsync(deadline.Token).ConfigureAwait(false);
            using var bytes = new MemoryStream();
            var buffer = new byte[4096];
            try
            {
                int read;
                while ((read = await stream.ReadAsync(buffer, deadline.Token).ConfigureAwait(false)) != 0)
                {
                    if (bytes.Length + read > MaximumResponseBytes)
                        throw new AgentApiException(statusCode, false);
                    await bytes.WriteAsync(buffer.AsMemory(0, read), deadline.Token).ConfigureAwait(false);
                }
                return new BoundedResponse(bytes.ToArray());
            }
            finally
            {
                CryptographicOperations.ZeroMemory(buffer);
                CryptographicOperations.ZeroMemory(bytes.GetBuffer());
            }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new AgentApiException(null, true);
        }
        catch (Exception error) when (error is HttpRequestException or IOException)
        {
            throw new AgentApiException(null, true);
        }
    }

    private static void RejectDefaultCredentials(HttpClient client)
    {
        if (client.DefaultRequestHeaders.Authorization is not null || client.DefaultRequestHeaders.Contains("Cookie"))
            throw new ArgumentException("Agent client must not contain default credentials.", nameof(client));
    }

    private static TimeSpan? ReadRetryAfter(HttpResponseMessage response)
    {
        var retryAfter = response.Headers.RetryAfter;
        return retryAfter?.Delta ?? (retryAfter?.Date is { } date ? date - DateTimeOffset.UtcNow : null);
    }

    private static JsonDocument ParseResponse(byte[] bytes)
    {
        var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
        try
        {
            RejectDuplicateProperties(document.RootElement);
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    private static void RejectDuplicateProperties(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new JsonException("Ambiguous API response.");
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray()) RejectDuplicateProperties(item);
        }
    }

    private static void ValidateText(string value, int minimum, int maximum)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length < minimum || value.Length > maximum)
            throw new ArgumentException("A supplied agent field is outside the API contract.");
    }

    private sealed record EnrollmentRequest(string EnrollmentToken, string Hostname, string Platform, string AgentVersion);
    private sealed record HeartbeatRequest(string DeviceId, string AgentVersion, InventorySnapshot? Inventory);
    private sealed class ProtectedJsonContent : ByteArrayContent
    {
        private readonly byte[] _bytes;
        public ProtectedJsonContent(byte[] bytes) : base(bytes) => _bytes = bytes;

        protected override void Dispose(bool disposing)
        {
            if (disposing) CryptographicOperations.ZeroMemory(_bytes);
            base.Dispose(disposing);
        }
    }
    private sealed class BoundedResponse(byte[] bytes) : IDisposable
    {
        public byte[] Bytes { get; } = bytes;
        public void Dispose() => CryptographicOperations.ZeroMemory(Bytes);
    }
}
