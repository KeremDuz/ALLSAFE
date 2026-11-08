using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Allsafe.Agent.Tests;

public sealed class AgentApiClientTests
{
    private static readonly Uri Server = new("https://allsafe.example:8443/");
    private const string DeviceId = "cf8e9b4d-40b3-4eaf-af2c-a43803b99c36";
    private const string DeviceToken = "device-token-private-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string EnrollmentToken = "enrollment-private-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    private const string AgentVersion = "0.2.0";

    [Fact]
    public async Task EnrollmentMatchesApiContractAndReturnsDeviceSpecificCredentials()
    {
        using RecordingHandler handler = new(_ => JsonResponse(HttpStatusCode.Created,
            $$"""{"device_id":"{{DeviceId}}","agent_token":"{{DeviceToken}}"}"""));
        using HttpClient http = new(handler);
        AgentApiClient api = new(http);

        DeviceCredential credential = await api.EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion);

        CapturedRequest request = Assert.Single(handler.Requests);
        Assert.Equal(HttpMethod.Post, request.Method);
        Assert.Equal(new Uri(Server, "api/v1/agent/enroll"), request.Uri);
        Assert.Null(request.Authorization);
        Assert.Equal("application/json", request.ContentType);
        using JsonDocument document = JsonDocument.Parse(request.Body);
        JsonElement body = document.RootElement;
        AssertProperties(body, "enrollment_token", "hostname", "platform", "agent_version");
        Assert.Equal(EnrollmentToken, body.GetProperty("enrollment_token").GetString());
        Assert.Equal("LAB-WINDOWS", body.GetProperty("hostname").GetString());
        Assert.Equal("windows", body.GetProperty("platform").GetString());
        Assert.Equal(AgentVersion, body.GetProperty("agent_version").GetString());
        Assert.Equal(Server, credential.ServerUri);
        Assert.Equal(DeviceId, credential.DeviceId);
        Assert.Equal(DeviceToken, credential.AgentToken);
    }

    [Fact]
    public async Task HeartbeatUsesMatchingDeviceIdAndBearerWithoutEnrollmentSecret()
    {
        using RecordingHandler handler = new(HeartbeatResponse);
        using HttpClient http = new(handler);
        AgentApiClient api = new(http);
        DeviceCredential credential = new(Server, DeviceId, DeviceToken);

        await api.HeartbeatAsync(credential, AgentVersion, new InventorySnapshot("Windows 11", 8, 16_000_000_000));

        CapturedRequest request = Assert.Single(handler.Requests);
        Assert.Equal(HttpMethod.Post, request.Method);
        Assert.Equal(new Uri(Server, "api/v1/agent/heartbeat"), request.Uri);
        Assert.Equal(new AuthenticationHeaderValue("Bearer", DeviceToken), request.Authorization);
        using JsonDocument document = JsonDocument.Parse(request.Body);
        JsonElement body = document.RootElement;
        AssertProperties(body, "device_id", "agent_version", "inventory");
        Assert.Equal(DeviceId, body.GetProperty("device_id").GetString());
        Assert.Equal(AgentVersion, body.GetProperty("agent_version").GetString());
        JsonElement inventory = body.GetProperty("inventory");
        AssertProperties(inventory, "os_version", "cpu_count", "memory_total_bytes");
        Assert.Equal("Windows 11", inventory.GetProperty("os_version").GetString());
        Assert.Equal(8, inventory.GetProperty("cpu_count").GetInt32());
        Assert.Equal(16_000_000_000, inventory.GetProperty("memory_total_bytes").GetInt64());
        Assert.DoesNotContain(DeviceToken, request.Body, StringComparison.Ordinal);
        Assert.DoesNotContain("enrollment_token", request.Body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task HeartbeatsDoNotRetainAnotherDevicesBearer()
    {
        using RecordingHandler handler = new(HeartbeatResponse);
        using HttpClient http = new(handler);
        AgentApiClient api = new(http);
        string otherId = "3acbeaf6-0c1c-40db-9c0d-65b88204f7fb";
        string otherToken = "other-device-private-cccccccccccccccccccccccccccccccccccccccccccc";

        await api.HeartbeatAsync(new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null);
        await api.HeartbeatAsync(new DeviceCredential(Server, otherId, otherToken), AgentVersion, null);

        Assert.Equal(2, handler.Requests.Count);
        for (int index = 0; index < 2; index++)
        {
            CapturedRequest request = handler.Requests[index];
            using JsonDocument document = JsonDocument.Parse(request.Body);
            Assert.Equal(index == 0 ? DeviceId : otherId, document.RootElement.GetProperty("device_id").GetString());
            Assert.Equal(index == 0 ? DeviceToken : otherToken, request.Authorization?.Parameter);
        }
        Assert.Null(http.DefaultRequestHeaders.Authorization);
    }

    [Theory]
    [InlineData(400, false)]
    [InlineData(401, false)]
    [InlineData(403, false)]
    [InlineData(409, false)]
    [InlineData(422, false)]
    [InlineData(408, true)]
    [InlineData(429, true)]
    [InlineData(500, true)]
    [InlineData(503, true)]
    public async Task EnrollmentErrorsAreClassifiedWithoutRetryingOrDisclosingBodies(int statusCode, bool transient)
    {
        string sensitiveBody = $"server diagnostic containing {EnrollmentToken} and {DeviceToken}";
        using RecordingHandler handler = new(_ => JsonResponse((HttpStatusCode)statusCode, sensitiveBody));
        using HttpClient http = new(handler);
        AgentApiClient api = new(http);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(
            () => api.EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.Single(handler.Requests);
        Assert.Equal(statusCode, failure.StatusCode);
        Assert.Equal(transient, failure.IsTransient);
        AssertSanitized(failure, sensitiveBody, EnrollmentToken, DeviceToken);
    }

    [Theory]
    [InlineData(301)]
    [InlineData(302)]
    [InlineData(307)]
    [InlineData(308)]
    public async Task RedirectResponseFailsWithoutIssuingAnotherEnrollment(int statusCode)
    {
        using RecordingHandler handler = new(_ =>
        {
            HttpResponseMessage response = new((HttpStatusCode)statusCode);
            response.Headers.Location = new Uri("https://untrusted.example/collect");
            return response;
        });
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(
            () => new AgentApiClient(http).EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.Single(handler.Requests);
        Assert.Equal(statusCode, failure.StatusCode);
        Assert.False(failure.IsTransient);
    }

    [Fact]
    public async Task NetworkFailureDuringOneTimeEnrollmentIsNotRetriedOrDisclosed()
    {
        using RecordingHandler handler = new(_ => throw new HttpRequestException($"unsafe URI?token={EnrollmentToken}"));
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(
            () => new AgentApiClient(http).EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.Single(handler.Requests);
        Assert.Null(failure.StatusCode);
        Assert.True(failure.IsTransient);
        AssertSanitized(failure, EnrollmentToken, "unsafe URI");
    }

    [Theory]
    [InlineData(401)]
    [InlineData(403)]
    public async Task RevokedOrUnauthorizedDeviceHeartbeatIsPermanentAndSanitized(int statusCode)
    {
        using RecordingHandler handler = new(_ => JsonResponse((HttpStatusCode)statusCode, $"revoked {DeviceToken}"));
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http).HeartbeatAsync(
            new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null));

        Assert.Single(handler.Requests);
        Assert.Equal(statusCode, failure.StatusCode);
        Assert.False(failure.IsTransient);
        AssertSanitized(failure, DeviceToken, "revoked");
    }

    [Fact]
    public async Task NullInventoryAndUnknownInventoryFieldsAreOmitted()
    {
        using RecordingHandler handler = new(HeartbeatResponse);
        using HttpClient http = new(handler);
        AgentApiClient api = new(http);
        DeviceCredential credential = new(Server, DeviceId, DeviceToken);

        await api.HeartbeatAsync(credential, AgentVersion, null);
        await api.HeartbeatAsync(credential, AgentVersion, new InventorySnapshot("Windows 11", null, null));

        using JsonDocument first = JsonDocument.Parse(handler.Requests[0].Body);
        using JsonDocument second = JsonDocument.Parse(handler.Requests[1].Body);
        AssertProperties(first.RootElement, "device_id", "agent_version");
        AssertProperties(second.RootElement.GetProperty("inventory"), "os_version");
    }

    [Theory]
    [InlineData("not JSON")]
    [InlineData("{}")]
    [InlineData("{\"device_id\":\"cf8e9b4d-40b3-4eaf-af2c-a43803b99c36\"}")]
    [InlineData("{\"device_id\":\"cf8e9b4d-40b3-4eaf-af2c-a43803b99c36\",\"agent_token\":null}")]
    public async Task IncompleteOrInvalidEnrollmentResponseDoesNotYieldCredentials(string responseBody)
    {
        using RecordingHandler handler = new(_ => JsonResponse(HttpStatusCode.Created, responseBody));
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(
            () => new AgentApiClient(http).EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.False(failure.IsTransient);
        AssertSanitized(failure, responseBody);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task OversizedEnrollmentResponseIsRejectedEvenWithoutContentLength(bool contentLengthKnown)
    {
        string responseBody = $$"""{"device_id":"{{DeviceId}}","agent_token":"{{DeviceToken}}","padding":"{{new string('x', 40 * 1024)}}"}""";
        using RecordingHandler handler = new(_ =>
        {
            HttpContent content = contentLengthKnown
                ? new StringContent(responseBody, Encoding.UTF8, "application/json")
                : new UnknownLengthContent(Encoding.UTF8.GetBytes(responseBody));
            return new HttpResponseMessage(HttpStatusCode.Created) { Content = content };
        });
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(
            () => new AgentApiClient(http).EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.False(failure.IsTransient);
        AssertSanitized(failure, DeviceToken, EnrollmentToken);
    }

    [Fact]
    public async Task UnknownLengthResponseStopsReadingAtTheBound()
    {
        using UnknownLengthContent content = new(new byte[1024 * 1024]);
        using RecordingHandler handler = new(_ => new HttpResponseMessage(HttpStatusCode.Created) { Content = content });
        using HttpClient http = new(handler);

        await Assert.ThrowsAsync<AgentApiException>(
            () => new AgentApiClient(http).EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.InRange(content.BytesRead, 32 * 1024 + 1, 40 * 1024);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("{\"device_id\":\"3acbeaf6-0c1c-40db-9c0d-65b88204f7fb\"}")]
    [InlineData("null")]
    [InlineData("not JSON")]
    public async Task HeartbeatResponseMustAcknowledgeTheSameDevice(string responseBody)
    {
        using RecordingHandler handler = new(_ => JsonResponse(HttpStatusCode.OK, responseBody));
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http).HeartbeatAsync(
            new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null));

        Assert.False(failure.IsTransient);
        AssertSanitized(failure, DeviceToken);
    }

    [Fact]
    public void SharedDefaultCredentialsAreRejectedBeforeUse()
    {
        using HttpClient http = new();
        http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", DeviceToken);

        ArgumentException failure = Assert.Throws<ArgumentException>(() => new AgentApiClient(http));

        AssertSanitized(failure, DeviceToken);
    }

    [Fact]
    public async Task DefaultCredentialsAddedAfterConstructionAreRejectedBeforeSending()
    {
        using RecordingHandler handler = new(HeartbeatResponse);
        using HttpClient http = new(handler);
        AgentApiClient api = new(http);
        http.DefaultRequestHeaders.Add("Cookie", $"session={DeviceToken}");

        ArgumentException failure = await Assert.ThrowsAsync<ArgumentException>(
            () => api.EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.Empty(handler.Requests);
        AssertSanitized(failure, DeviceToken);
    }

    [Theory]
    [InlineData(429, 120, 120)]
    [InlineData(503, 120, 120)]
    [InlineData(503, 3600, 300)]
    [InlineData(500, 120, null)]
    [InlineData(403, 120, null)]
    public async Task ServerRetryDelayIsSanitizedBoundedAndLimitedToRateLimitsOrUnavailable(
        int status, int serverSeconds, int? expectedSeconds)
    {
        using RecordingHandler handler = new(_ =>
        {
            var response = JsonResponse((HttpStatusCode)status, $"private {DeviceToken}");
            response.Headers.RetryAfter = new RetryConditionHeaderValue(TimeSpan.FromSeconds(serverSeconds));
            return response;
        });
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http).HeartbeatAsync(
            new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null));

        Assert.Equal(expectedSeconds is { } seconds ? TimeSpan.FromSeconds(seconds) : null, failure.RetryAfter);
        Assert.Single(handler.Requests);
        AssertSanitized(failure, DeviceToken);
    }

    [Fact]
    public async Task RetryAfterDateIsSupported()
    {
        using RecordingHandler handler = new(_ =>
        {
            var response = JsonResponse(HttpStatusCode.TooManyRequests, "{}");
            response.Headers.RetryAfter = new RetryConditionHeaderValue(DateTimeOffset.UtcNow.AddSeconds(90));
            return response;
        });
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http).HeartbeatAsync(
            new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null));

        Assert.NotNull(failure.RetryAfter);
        Assert.InRange(failure.RetryAfter.Value.TotalSeconds, 1, 90);
    }

    [Fact]
    public async Task ExpiredRetryAfterDateDoesNotAddANegativeDelay()
    {
        using RecordingHandler handler = new(_ =>
        {
            var response = JsonResponse(HttpStatusCode.ServiceUnavailable, "{}");
            response.Headers.RetryAfter = new RetryConditionHeaderValue(DateTimeOffset.UtcNow.AddMinutes(-1));
            return response;
        });
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http).HeartbeatAsync(
            new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null));

        Assert.Equal(TimeSpan.Zero, failure.RetryAfter);
    }

    [Fact]
    public async Task MalformedRetryAfterIsIgnoredWithoutExposingHeaderValues()
    {
        using RecordingHandler handler = new(_ =>
        {
            var response = JsonResponse(HttpStatusCode.TooManyRequests, "{}");
            response.Headers.TryAddWithoutValidation("Retry-After", DeviceToken);
            return response;
        });
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http).HeartbeatAsync(
            new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null));

        Assert.True(failure.IsTransient);
        Assert.Null(failure.RetryAfter);
        AssertSanitized(failure, DeviceToken);
    }

    [Theory]
    [InlineData("device_id")]
    [InlineData("agent_token")]
    public async Task DuplicateEnrollmentIdentityPropertiesAreRejected(string property)
    {
        var value = property == "device_id" ? DeviceId : DeviceToken;
        string body = $$"""{"device_id":"{{DeviceId}}","agent_token":"{{DeviceToken}}","{{property}}":"{{value}}"}""";
        using RecordingHandler handler = new(_ => JsonResponse(HttpStatusCode.Created, body));
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http)
            .EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.False(failure.IsTransient);
        Assert.Single(handler.Requests);
        AssertSanitized(failure, DeviceToken, body);
    }

    [Fact]
    public async Task DuplicateHeartbeatAcknowledgementsAreRejectedEvenWhenOneMatches()
    {
        string body = $$"""{"device_id":"00000000-0000-0000-0000-000000000000","device_id":"{{DeviceId}}"}""";
        using RecordingHandler handler = new(_ => JsonResponse(HttpStatusCode.OK, body));
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http).HeartbeatAsync(
            new DeviceCredential(Server, DeviceId, DeviceToken), AgentVersion, null));

        Assert.False(failure.IsTransient);
        AssertSanitized(failure, DeviceToken);
    }

    [Theory]
    [InlineData("text/html")]
    [InlineData("text/plain")]
    [InlineData(null)]
    public async Task SuccessWithoutJsonMediaTypeDoesNotYieldCredentials(string? contentType)
    {
        using RecordingHandler handler = new(_ =>
        {
            var response = JsonResponse(HttpStatusCode.Created,
                $$"""{"device_id":"{{DeviceId}}","agent_token":"{{DeviceToken}}"}""");
            response.Content.Headers.ContentType = contentType is null ? null : new MediaTypeHeaderValue(contentType);
            return response;
        });
        using HttpClient http = new(handler);

        AgentApiException failure = await Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http)
            .EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));

        Assert.False(failure.IsTransient);
        AssertSanitized(failure, DeviceToken);
    }

    [Fact]
    public async Task DeadlineIncludesAStalledResponseBodyAfterHeadersHaveArrived()
    {
        using StallingContent content = new();
        using RecordingHandler handler = new(_ => new HttpResponseMessage(HttpStatusCode.Created) { Content = content });
        using HttpClient http = new(handler) { Timeout = TimeSpan.FromMilliseconds(100) };

        Task<AgentApiException> failure = Assert.ThrowsAsync<AgentApiException>(() => new AgentApiClient(http)
            .EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion));
        AgentApiException problem = await failure.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.True(problem.IsTransient);
        Assert.Null(problem.StatusCode);
        Assert.Single(handler.Requests);
        Assert.True(content.StreamDisposed);
    }

    [Fact]
    public async Task CallerCancellationDuringBodyReadIsPropagated()
    {
        using CancellationTokenSource cancellation = new();
        using StallingContent content = new(cancellation.Cancel);
        using RecordingHandler handler = new(_ => new HttpResponseMessage(HttpStatusCode.Created) { Content = content });
        using HttpClient http = new(handler);

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new AgentApiClient(http)
            .EnrollAsync(Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion, cancellation.Token));

        Assert.Single(handler.Requests);
        Assert.True(content.StreamDisposed);
    }

    [Fact]
    public async Task ExplicitCancellationIsPropagatedWithoutRetrying()
    {
        using CancellationTokenSource cancellation = new();
        using RecordingHandler handler = new((_, token) =>
        {
            cancellation.Cancel();
            token.ThrowIfCancellationRequested();
            return Task.FromResult(JsonResponse(HttpStatusCode.Created, "{}"));
        });
        using HttpClient http = new(handler);

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new AgentApiClient(http).EnrollAsync(
            Server, EnrollmentToken, "LAB-WINDOWS", AgentVersion, cancellation.Token));

        Assert.Single(handler.Requests);
    }

    private static HttpResponseMessage JsonResponse(HttpStatusCode statusCode, string body) =>
        new(statusCode) { Content = new StringContent(body, Encoding.UTF8, "application/json") };

    private static async Task<HttpResponseMessage> HeartbeatResponse(HttpRequestMessage request, CancellationToken token)
    {
        using JsonDocument document = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(token));
        string deviceId = document.RootElement.GetProperty("device_id").GetString()!;
        return JsonResponse(HttpStatusCode.OK, $$"""{"device_id":"{{deviceId}}"}""");
    }

    private static void AssertProperties(JsonElement element, params string[] names) =>
        Assert.Equal(names.Order(StringComparer.Ordinal), element.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal));

    private static void AssertSanitized(Exception exception, params string[] secrets)
    {
        foreach (string secret in secrets)
        {
            Assert.DoesNotContain(secret, exception.ToString(), StringComparison.Ordinal);
        }
    }

    private sealed record CapturedRequest(HttpMethod Method, Uri? Uri, AuthenticationHeaderValue? Authorization, string? ContentType, string Body);

    private sealed class RecordingHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> _respond;
        public List<CapturedRequest> Requests { get; } = [];

        public RecordingHandler(Func<HttpRequestMessage, HttpResponseMessage> respond)
            : this((request, _) => Task.FromResult(respond(request))) { }

        public RecordingHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> respond) => _respond = respond;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add(new CapturedRequest(request.Method, request.RequestUri, request.Headers.Authorization,
                request.Content?.Headers.ContentType?.MediaType, body));
            return await _respond(request, cancellationToken);
        }
    }

    private sealed class UnknownLengthContent : HttpContent
    {
        private readonly byte[] _bytes;
        private readonly TrackingStream _stream;

        public UnknownLengthContent(byte[] bytes)
        {
            _bytes = bytes;
            _stream = new(bytes);
            Headers.ContentType = new MediaTypeHeaderValue("application/json");
        }
        public int BytesRead => _stream.BytesRead;

        protected override bool TryComputeLength(out long length)
        {
            length = 0;
            return false;
        }

        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => stream.WriteAsync(_bytes).AsTask();

        protected override Task<Stream> CreateContentReadStreamAsync() => Task.FromResult<Stream>(_stream);
        protected override Task<Stream> CreateContentReadStreamAsync(CancellationToken cancellationToken) => Task.FromResult<Stream>(_stream);

        private sealed class TrackingStream(byte[] buffer) : MemoryStream(buffer)
        {
            public int BytesRead { get; private set; }

            public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
            {
                int read = await base.ReadAsync(buffer, cancellationToken);
                BytesRead += read;
                return read;
            }
        }
    }

    private sealed class StallingContent : HttpContent
    {
        private readonly StallingStream _stream;
        public bool StreamDisposed => _stream.Disposed;

        public StallingContent(Action? onRead = null)
        {
            _stream = new StallingStream(onRead);
            Headers.ContentType = new MediaTypeHeaderValue("application/json");
        }

        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => throw new NotSupportedException();
        protected override Task<Stream> CreateContentReadStreamAsync(CancellationToken cancellationToken) => Task.FromResult<Stream>(_stream);

        private sealed class StallingStream(Action? onRead) : Stream
        {
            public bool Disposed { get; private set; }
            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException();
            public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
            public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
            {
                onRead?.Invoke();
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
                return 0;
            }
            protected override void Dispose(bool disposing) { if (disposing) Disposed = true; base.Dispose(disposing); }
            public override void Flush() => throw new NotSupportedException();
            public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
            public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
            public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }
    }
}
