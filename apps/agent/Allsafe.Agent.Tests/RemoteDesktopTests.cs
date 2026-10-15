using System.Drawing;
using System.Text;
using System.Threading.Channels;
using Allsafe.Agent.RemoteDesktop;

namespace Allsafe.Agent.Tests;

public sealed class RemoteDesktopTests
{
    private static DesktopSession Pending => new("a8d08b11-03b0-4455-8e09-585b700c0974", "cf8e9b4d-40b3-4eaf-af2c-a43803b99c36",
        "operator@example.test", "Destek isteği", "control", "pending", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(2), null);

    [Fact]
    public async Task LocalStopRevokesGrantBeforeLateQueuedInputCompletes()
    {
        var api = new FakeApi(); var surface = new FakeSurface(); var consent = Accepted();
        var queued = new TaskCompletionSource<DesktopInput?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var waiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int receives = 0;
        api.Connection.ReceiveOverride = _ =>
        {
            if (++receives == 1) return Task.FromResult<DesktopInput?>(new DesktopInput("ready"));
            waiting.TrySetResult(); return queued.Task;
        };
        var work = NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        await waiting.Task.WaitAsync(TimeSpan.FromSeconds(2));
        consent.Stop!();
        Assert.False(surface.Sharing);
        queued.SetResult(new DesktopInput("key", "down", Code: "ControlLeft"));
        await work.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Empty(surface.Inputs); Assert.False(surface.Sharing); Assert.True(api.Connection.Disposed);
    }

    [Fact]
    public async Task ResolutionChangeStopsInsteadOfSendingIncompatibleSecondDisplay()
    {
        var api = new FakeApi(); var surface = new FakeSurface { Width = call => call == 1 ? 1280 : 640 }; var consent = Accepted();
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("ready"));
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(3));
        Assert.Single(api.Connection.Displays); Assert.Equal(1, api.Connection.Frames); Assert.False(surface.Sharing);
    }

    [Fact]
    public async Task RefusingConsentNeverConnectsCapturesOrInjects()
    {
        var api = new FakeApi(); var surface = new FakeSurface(); var consent = new FakeConsent { Answer = Task.FromResult(false) };
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        Assert.False(Assert.Single(api.Decisions)); Assert.Equal(0, api.Connects);
        Assert.Equal(0, surface.Captures); Assert.Empty(surface.Inputs);
    }

    [Fact]
    public async Task WaitingForConsentCannotConnectCaptureOrInject()
    {
        using var cancellation = new CancellationTokenSource();
        var api = new FakeApi(); var surface = new FakeSurface(); var consent = new FakeConsent();
        var work = NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, cancellation.Token);
        await consent.Asked.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal(0, api.Connects); Assert.Equal(0, surface.Captures); Assert.Empty(api.Decisions);
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => work);
    }

    [Fact]
    public async Task SecureOrDisconnectedDesktopNeverAsksOrCaptures()
    {
        var api = new FakeApi(); var surface = new FakeSurface { Available = false }; var consent = new FakeConsent();
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        Assert.False(consent.Asked.Task.IsCompleted); Assert.Empty(api.Decisions); Assert.Equal(0, surface.Captures);
    }

    [Fact]
    public async Task ChangedModeAfterConsentCannotConnect()
    {
        var api = new FakeApi { Decision = pending => Approved(pending) with { Mode = "view" } };
        var surface = new FakeSurface(); var consent = Accepted();
        await Assert.ThrowsAsync<InvalidDataException>(() => NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None));
        Assert.Equal(0, api.Connects); Assert.Equal(0, surface.Captures);
    }

    [Fact]
    public async Task FramesWaitForBothVisibleStopControlAndRelayReadiness()
    {
        var api = new FakeApi(); var surface = new FakeSurface(); var consent = Accepted();
        var visible = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        consent.Activation = visible.Task;
        var work = NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        await consent.Activated.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal(0, api.Connects); Assert.Equal(0, surface.Captures);
        visible.SetResult();
        await api.Connected.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal(0, surface.Captures);
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("ready"));
        await api.Connection.FrameSent.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal((1280, 720), Assert.Single(api.Connection.Displays));
        consent.Stop!();
        await work.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.True(api.Connection.Disposed); Assert.True(surface.Releases > 0); Assert.Equal(0, surface.LastFrame!.Jpeg[0]);
    }

    [Fact]
    public async Task UnattendedAuthorizationStillWaitsForVisibleStopAndRelayReadiness()
    {
        var api = new FakeApi(); var surface = new FakeSurface();
        var visible = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var consent = new FakeConsent { Unattended = true, Activation = visible.Task };
        var work = NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        await consent.Activated.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.True(Assert.Single(api.Decisions)); Assert.False(consent.Asked.Task.IsCompleted);
        Assert.Equal(0, api.Connects); Assert.Equal(0, surface.Captures); Assert.False(surface.Sharing);
        visible.SetResult();
        await api.Connected.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.False(surface.Sharing); Assert.Equal(0, surface.Captures);
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("ready"));
        await api.Connection.FrameSent.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.True(surface.Sharing);
        consent.Stop!();
        Assert.False(surface.Sharing);
        await work.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.True(api.Connection.Disposed); Assert.True(surface.Releases > 0);
    }

    [Fact]
    public async Task UnattendedModeRejectsChangedServerAuthorization()
    {
        var api = new FakeApi { Decision = pending => Approved(pending) with { OperatorName = "other@example.test" } };
        var surface = new FakeSurface(); var consent = new FakeConsent { Unattended = true };
        await Assert.ThrowsAsync<InvalidDataException>(() => NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None));
        Assert.False(consent.Asked.Task.IsCompleted); Assert.Equal(0, api.Connects);
        Assert.Equal(0, surface.Captures); Assert.False(surface.Sharing);
    }

    [Fact]
    public async Task UnattendedModeCannotCaptureAnUnavailableWindowsDesktop()
    {
        var api = new FakeApi(); var surface = new FakeSurface { Available = false };
        var consent = new FakeConsent { Unattended = true };
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        Assert.Empty(api.Decisions); Assert.Equal(0, api.Connects);
        Assert.False(consent.Activated.Task.IsCompleted); Assert.Equal(0, surface.Captures); Assert.Empty(surface.Inputs);
    }

    [Fact]
    public async Task ViewOnlyRejectsControlAndAlwaysReleasesOnDisconnect()
    {
        var api = new FakeApi { Decision = pending => Approved(pending) with { Mode = "view" } }; var surface = new FakeSurface(); var consent = Accepted();
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("ready"));
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("key", "down", Code: "KeyA"));
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending with { Mode = "view" }, CancellationToken.None);
        Assert.Empty(surface.Inputs); Assert.True(surface.Releases > 0); Assert.True(api.Connection.Disposed);
    }

    [Fact]
    public async Task ControlInputAndBlurReleaseAreDeliveredAfterReady()
    {
        var api = new FakeApi(); var surface = new FakeSurface(); var consent = Accepted();
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("ready"));
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("key", "down", Code: "ControlLeft"));
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("release"));
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("stop"));
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        Assert.Equal("ControlLeft", Assert.Single(surface.Inputs).Code); Assert.True(surface.Releases >= 2);
    }

    [Fact]
    public async Task InputBeforeRelayReadyNeverReachesWindows()
    {
        var api = new FakeApi(); var surface = new FakeSurface(); var consent = Accepted();
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("key", "down", Code: "KeyA"));
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        Assert.Empty(surface.Inputs); Assert.Equal(0, surface.Captures); Assert.True(api.Connection.Disposed);
    }

    [Fact]
    public async Task LockingDesktopStopsInputAndFrames()
    {
        var api = new FakeApi(); var surface = new FakeSurface(); var consent = Accepted();
        var work = NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        await api.Connected.Task.WaitAsync(TimeSpan.FromSeconds(2));
        surface.Available = false;
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("ready"));
        await work.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Empty(surface.Inputs); Assert.Equal(0, surface.Captures); Assert.True(surface.Releases > 0);
    }

    [Fact]
    public async Task OversizedFramesNeverReachRelayAndMemoryIsCleared()
    {
        var api = new FakeApi(); var surface = new FakeSurface { FrameBytes = DesktopProtocol.MaximumFrameBytes + 1 }; var consent = Accepted();
        await api.Connection.Commands.Writer.WriteAsync(new DesktopInput("ready"));
        await NewCoordinator(api, surface, consent).HandleSessionAsync(Pending, CancellationToken.None);
        Assert.False(api.Connection.FrameSent.Task.IsCompleted); Assert.True(api.Connection.Disposed);
        Assert.All(surface.LastFrame!.Jpeg, value => Assert.Equal(0, value));
    }

    [Theory]
    [InlineData("{\"type\":\"pointer\",\"action\":\"down\",\"x\":-0.1,\"y\":0,\"button\":\"left\"}")]
    [InlineData("{\"type\":\"pointer\",\"action\":\"move\",\"x\":0,\"y\":1.1,\"button\":\"left\"}")]
    [InlineData("{\"type\":\"wheel\",\"delta\":1201}")]
    [InlineData("{\"type\":\"key\",\"action\":\"down\",\"code\":\"PrintScreen\"}")]
    [InlineData("{\"type\":\"key\",\"action\":\"press\",\"code\":\"KeyA\"}")]
    [InlineData("{\"type\":\"key\",\"action\":\"down\",\"code\":\"MetaLeft\"}")]
    [InlineData("{\"type\":\"shell\",\"command\":\"whoami\"}")]
    [InlineData("{\"type\":\"release\",\"clipboard\":\"private\"}")]
    [InlineData("{\"type\":\"stop\",\"type\":\"release\"}")]
    public void UntrustedInputIsRejectedLocally(string json)
        => Assert.Throws<InvalidDataException>(() => DesktopProtocol.ParseInput(Encoding.UTF8.GetBytes(json)));

    [Theory]
    [InlineData("{\"type\":\"pointer\",\"action\":\"move\",\"x\":0.2,\"y\":1,\"button\":\"left\"}", "pointer")]
    [InlineData("{\"type\":\"key\",\"action\":\"up\",\"code\":\"NumpadEnter\"}", "key")]
    [InlineData("{\"type\":\"wheel\",\"delta\":-1200}", "wheel")]
    [InlineData("{\"type\":\"ready\"}", "ready")]
    [InlineData("{\"type\":\"closed\",\"reason\":\"operator_closed\"}", "stop")]
    public void NarrowProtocolAcceptsSupportedMessages(string json, string type)
        => Assert.Equal(type, DesktopProtocol.ParseInput(Encoding.UTF8.GetBytes(json)).Type);

    [Fact]
    public void OversizedInputCannotBeParsed()
        => Assert.Throws<InvalidDataException>(() => DesktopProtocol.ParseInput(new byte[DesktopProtocol.MaximumMessageBytes + 1]));

    [Theory]
    [InlineData("https://allsafe.example", "wss")]
    [InlineData("http://127.0.0.1:8000", "ws")]
    public void StreamUrlsNeverContainCredentialsOrQuery(string server, string scheme)
    {
        var uri = RemoteDesktopApi.StreamUri(new Uri(server), Pending.Id);
        Assert.Equal(scheme, uri.Scheme); Assert.Empty(uri.Query); Assert.Empty(uri.UserInfo);
        Assert.EndsWith($"/{Pending.Id}/stream", uri.AbsolutePath, StringComparison.Ordinal);
        Assert.Throws<ArgumentException>(() => RemoteDesktopApi.StreamUri(new Uri(server), "../other?token=secret"));
    }

    [Fact]
    public void NativeInputLayoutMatches64BitWindowsAbiWithoutInjectingInput()
        => Assert.Equal(IntPtr.Size == 8 ? 40 : 28, NativeDesktopSurface.NativeInputSize);

    [Fact]
    public void CodecScalesOnlyGeneratedBitmapAndProducesBoundedJpeg()
    {
        using var bitmap = new Bitmap(2400, 1600);
        using (var graphics = Graphics.FromImage(bitmap)) graphics.Clear(Color.DarkSlateBlue);
        var frame = NativeDesktopSurface.EncodeFrame(bitmap);
        Assert.Equal(1080, frame.Width); Assert.Equal(720, frame.Height);
        Assert.InRange(frame.Jpeg.Length, 100, DesktopProtocol.MaximumFrameBytes);
        Assert.Equal(0xFF, frame.Jpeg[0]); Assert.Equal(0xD8, frame.Jpeg[1]);
        using var bytes = new MemoryStream(frame.Jpeg); using var decoded = Image.FromStream(bytes);
        Assert.Equal(frame.Width, decoded.Width); Assert.Equal(frame.Height, decoded.Height);
    }

    [Fact]
    public void DesktopCommandNeverAcceptsTokenOrServerOverrides()
    {
        Assert.Equal("desktop", CommandOptions.Parse(["desktop"]).Command);
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["desktop", "--token-stdin"]));
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["desktop", "--server", "https://other.example"]));
    }

    private static DesktopCoordinator NewCoordinator(FakeApi api, FakeSurface surface, FakeConsent consent)
        => new(api, surface, consent, TimeProvider.System);
    private static DesktopSession Approved(DesktopSession pending) => pending with { Status = "approved", ExpiresAt = DateTimeOffset.UtcNow.AddMinutes(10) };
    private static FakeConsent Accepted() => new() { Answer = Task.FromResult(true) };

    private sealed class FakeApi : IRemoteDesktopApi
    {
        public List<bool> Decisions { get; } = [];
        public int Connects { get; private set; }
        public FakeConnection Connection { get; } = new();
        public TaskCompletionSource Connected { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Func<DesktopSession, DesktopSession> Decision { get; init; } = Approved;
        public Task<IReadOnlyList<DesktopSession>> PendingAsync(CancellationToken cancellationToken) => Task.FromResult<IReadOnlyList<DesktopSession>>([]);
        public Task<DesktopSession> DecideAsync(string sessionId, bool approved, CancellationToken cancellationToken)
        {
            Decisions.Add(approved);
            return Task.FromResult(approved ? Decision(Pending) : Pending with { Status = "denied" });
        }
        public Task<IDesktopConnection> ConnectAsync(string sessionId, CancellationToken cancellationToken)
        { Connects++; Connected.TrySetResult(); return Task.FromResult<IDesktopConnection>(Connection); }
    }

    private sealed class FakeConnection : IDesktopConnection
    {
        public Channel<DesktopInput> Commands { get; } = Channel.CreateUnbounded<DesktopInput>();
        public List<(int Width, int Height)> Displays { get; } = [];
        public TaskCompletionSource FrameSent { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool Disposed { get; private set; }
        public int Frames { get; private set; }
        public Func<CancellationToken, Task<DesktopInput?>>? ReceiveOverride { get; set; }
        public Task SendDisplayAsync(int width, int height, CancellationToken cancellationToken)
        { Displays.Add((width, height)); return Task.CompletedTask; }
        public Task SendFrameAsync(byte[] jpeg, CancellationToken cancellationToken) { Frames++; FrameSent.TrySetResult(); return Task.CompletedTask; }
        public async Task<DesktopInput?> ReceiveAsync(CancellationToken cancellationToken)
            => ReceiveOverride is null ? await Commands.Reader.ReadAsync(cancellationToken) : await ReceiveOverride(cancellationToken);
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class FakeSurface : IDesktopSurface
    {
        public bool Available { get; set; } = true;
        public bool Sharing { get; private set; }
        public bool IsAvailable => Available;
        public int Captures { get; private set; }
        public int Releases { get; private set; }
        public List<DesktopInput> Inputs { get; } = [];
        public int FrameBytes { get; init; } = 100;
        public Func<int, int> Width { get; init; } = _ => 1280;
        public DesktopFrame? LastFrame { get; private set; }
        public void SetSharingEnabled(bool enabled) { Sharing = enabled; if (!enabled) ReleaseAll(); }
        public DesktopFrame Capture() { if (!Sharing) throw new InvalidDataException(); Captures++; return LastFrame = new DesktopFrame(Width(Captures), 720, Enumerable.Repeat((byte)42, FrameBytes).ToArray()); }
        public void Apply(DesktopInput input) { if (!Sharing) throw new InvalidDataException(); Inputs.Add(input); }
        public void ReleaseAll() => Releases++;
    }

    private sealed class FakeConsent : IDesktopConsent
    {
        public bool Unattended { get; init; }
        public Task<bool> Answer { get; init; } = new TaskCompletionSource<bool>().Task;
        public Task Activation { get; set; } = Task.CompletedTask;
        public TaskCompletionSource Asked { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Activated { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Action? Stop { get; private set; }
        public Task<bool> AskAsync(DesktopSession session, CancellationToken cancellationToken)
            => DesktopAccessPolicy.DecideAsync(Unattended, session, TimeProvider.System,
                token => { Asked.TrySetResult(); return Answer.WaitAsync(token); }, cancellationToken);
        public async Task ActiveAsync(DesktopSession session, Action stop, CancellationToken cancellationToken)
        { Stop = stop; Activated.TrySetResult(); await Activation.WaitAsync(cancellationToken); }
        public void Idle(string message) { }
    }
}
