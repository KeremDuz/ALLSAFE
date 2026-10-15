using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Allsafe.Agent.Tests;

public sealed class HeartbeatWorkerTests
{
    private static readonly DeviceCredential Credential = new(new Uri("https://allsafe.example/"),
        "cf8e9b4d-40b3-4eaf-af2c-a43803b99c36", "private-worker-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    private static readonly InventorySnapshot Snapshot = new("Windows test", 4, 8_000_000_000);

    [Fact]
    public async Task TransientFailureHonorsRetryAfterAndLogsRecovery()
    {
        using CancellationTokenSource shutdown = new();
        var client = new ScriptedClient((call, _, _) =>
        {
            if (call == 2) return Task.FromException(new AgentApiException(503, true, TimeSpan.FromSeconds(120)));
            if (call == 4) shutdown.Cancel();
            return Task.CompletedTask;
        });
        var clock = new RecordingTimeProvider();
        var logger = new RecordingLogger();
        var lifetime = new TestLifetime();
        var exit = new AgentExitStatus();
        using var worker = NewWorker(client, clock, logger, lifetime, exit);

        await worker.StartAsync(shutdown.Token);
        await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.Equal(4, client.Calls.Count);
        Assert.Equal(TimeSpan.FromSeconds(120), clock.Delays.ToArray()[1]);
        Assert.Equal(2, logger.Entries.Count(entry => entry.Level == LogLevel.Information &&
            entry.Message == "ALLSAFE connection established."));
        Assert.Single(logger.Entries, entry => entry.Level == LogLevel.Warning);
        Assert.Equal(0, lifetime.StopCalls);
        Assert.Equal(0, exit.ExitCode);
    }

    [Fact]
    public async Task RepeatedSuccessesUseDebugInsteadOfRepeatingInformationLogs()
    {
        using CancellationTokenSource shutdown = new();
        var client = new ScriptedClient((call, _, _) =>
        {
            if (call == 3) shutdown.Cancel();
            return Task.CompletedTask;
        });
        var clock = new RecordingTimeProvider();
        var logger = new RecordingLogger();
        using var worker = NewWorker(client, clock, logger);

        await worker.StartAsync(shutdown.Token);
        await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.Equal(3, client.Calls.Count);
        Assert.Single(logger.Entries, entry => entry.Level == LogLevel.Information);
        Assert.Equal(2, logger.Entries.Count(entry => entry.Level == LogLevel.Debug &&
            entry.Message == "Device heartbeat accepted."));
        Assert.DoesNotContain(logger.Entries, entry => entry.Level >= LogLevel.Warning);
        Assert.All(clock.Delays, delay => Assert.InRange(delay.TotalSeconds, 30, 33));
        Assert.All(client.Calls, call =>
        {
            Assert.Same(Credential, call.Credential);
            Assert.Equal(Program.AgentVersion, call.Version);
        });
    }

    [Fact]
    public async Task RepeatedTransientFailuresDoNotRepeatWarningLogs()
    {
        using CancellationTokenSource shutdown = new();
        var client = new ScriptedClient((call, _, _) =>
        {
            if (call <= 2) return Task.FromException(new AgentApiException(503, true));
            shutdown.Cancel();
            return Task.CompletedTask;
        });
        var clock = new RecordingTimeProvider();
        var logger = new RecordingLogger();
        using var worker = NewWorker(client, clock, logger);

        await worker.StartAsync(shutdown.Token);
        await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.Single(logger.Entries, entry => entry.Level == LogLevel.Warning);
        Assert.Single(logger.Entries, entry => entry.Level == LogLevel.Debug &&
            entry.Message.StartsWith("Connection retry", StringComparison.Ordinal));
        Assert.InRange(clock.Delays.ToArray()[0].TotalSeconds, 5, 6);
        Assert.InRange(clock.Delays.ToArray()[1].TotalSeconds, 10, 11);
        Assert.Single(logger.Entries, entry => entry.Message == "ALLSAFE connection established.");
    }

    [Fact]
    public async Task InventoryFailureStillSendsHeartbeatAndReportsRecoveryOnce()
    {
        using CancellationTokenSource shutdown = new();
        var client = new ScriptedClient((call, _, _) =>
        {
            if (call == 3) shutdown.Cancel();
            return Task.CompletedTask;
        });
        var inventory = new ScriptedInventory(call => call <= 2
            ? throw new InvalidOperationException("Untrusted local inventory details.") : Snapshot);
        var logger = new RecordingLogger();
        using var worker = NewWorker(client, new RecordingTimeProvider(), logger, inventory: inventory);

        await worker.StartAsync(shutdown.Token);
        await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.Collection(client.Calls,
            call => Assert.Null(call.Inventory),
            call => Assert.Null(call.Inventory),
            call => Assert.Same(Snapshot, call.Inventory));
        Assert.Single(logger.Entries, entry => entry.Level == LogLevel.Warning);
        Assert.Single(logger.Entries, entry => entry.Message == "Inventory collection recovered.");
        Assert.DoesNotContain(logger.Entries, entry =>
            entry.Message.Contains("Untrusted local inventory details", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(401)]
    [InlineData(403)]
    public async Task PermanentCredentialFailureStopsWithoutRetry(int statusCode)
    {
        var client = new ScriptedClient((_, _, _) => Task.FromException(new AgentApiException(statusCode, false)));
        var clock = new RecordingTimeProvider();
        var logger = new RecordingLogger();
        var lifetime = new TestLifetime();
        var exit = new AgentExitStatus();
        using var worker = NewWorker(client, clock, logger, lifetime, exit);

        await worker.StartAsync(CancellationToken.None);
        await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.Single(client.Calls);
        Assert.Empty(clock.Delays);
        Assert.Equal(1, lifetime.StopCalls);
        Assert.Equal(2, exit.ExitCode);
        Assert.Single(logger.Entries, entry => entry.Level == LogLevel.Error);
        Assert.DoesNotContain(logger.Entries, entry => entry.Message.Contains(Credential.AgentToken, StringComparison.Ordinal));
    }

    [Fact]
    public async Task UnexpectedClientFailureStopsWithDistinctExitCodeWithoutLeakingDetails()
    {
        var client = new ScriptedClient((_, _, _) => Task.FromException(
            new InvalidOperationException("private-client-failure-" + Credential.AgentToken)));
        var clock = new RecordingTimeProvider();
        var logger = new RecordingLogger();
        var lifetime = new TestLifetime();
        var exit = new AgentExitStatus();
        using var worker = NewWorker(client, clock, logger, lifetime, exit);

        await worker.StartAsync(CancellationToken.None);
        await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(5));

        Assert.Single(client.Calls);
        Assert.Empty(clock.Delays);
        Assert.Equal(1, lifetime.StopCalls);
        Assert.Equal(3, exit.ExitCode);
        Assert.Single(logger.Entries, entry => entry.Level == LogLevel.Error);
        Assert.DoesNotContain(logger.Entries, entry => entry.Message.Contains(Credential.AgentToken, StringComparison.Ordinal));
        Assert.DoesNotContain(logger.Entries, entry => entry.Message.Contains("private-client-failure", StringComparison.Ordinal));
    }

    [Fact]
    public async Task StopDuringNetworkRequestCancelsWithoutFailureOrAnotherHeartbeat()
    {
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = new ScriptedClient((_, _, cancellation) =>
        {
            entered.TrySetResult();
            return Task.Delay(Timeout.InfiniteTimeSpan, cancellation);
        });
        var clock = new RecordingTimeProvider();
        var logger = new RecordingLogger();
        var lifetime = new TestLifetime();
        var exit = new AgentExitStatus();
        using var worker = NewWorker(client, clock, logger, lifetime, exit);

        await worker.StartAsync(CancellationToken.None);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await worker.StopAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(5));

        Assert.True(worker.ExecuteTask!.IsCompletedSuccessfully);
        Assert.Single(client.Calls);
        Assert.Empty(clock.Delays);
        Assert.Equal(0, lifetime.StopCalls);
        Assert.Equal(0, exit.ExitCode);
        Assert.DoesNotContain(logger.Entries, entry => entry.Level >= LogLevel.Warning);
    }

    [Fact]
    public async Task StopDuringHeartbeatDelayCancelsWithoutWaitingForNextInterval()
    {
        var client = new ScriptedClient((_, _, _) => Task.CompletedTask);
        var clock = new RecordingTimeProvider(frozen: true);
        var logger = new RecordingLogger();
        var lifetime = new TestLifetime();
        var exit = new AgentExitStatus();
        using var worker = NewWorker(client, clock, logger, lifetime, exit);

        await worker.StartAsync(CancellationToken.None);
        await clock.TimerCreated.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await worker.StopAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(5));

        Assert.True(worker.ExecuteTask!.IsCompletedSuccessfully);
        Assert.Single(client.Calls);
        Assert.InRange(Assert.Single(clock.Delays).TotalSeconds, 30, 33);
        Assert.Equal(0, lifetime.StopCalls);
        Assert.Equal(0, exit.ExitCode);
        Assert.DoesNotContain(logger.Entries, entry => entry.Level >= LogLevel.Warning);
    }

    private static HeartbeatWorker NewWorker(ScriptedClient client, RecordingTimeProvider clock,
        RecordingLogger logger, TestLifetime? lifetime = null, AgentExitStatus? exit = null,
        IInventoryProvider? inventory = null) => new(client, Credential,
            inventory ?? new ScriptedInventory(_ => Snapshot), logger, lifetime ?? new TestLifetime(),
            clock, exit ?? new AgentExitStatus());

    private sealed record HeartbeatCall(DeviceCredential Credential, string Version, InventorySnapshot? Inventory);

    private sealed class ScriptedClient(Func<int, InventorySnapshot?, CancellationToken, Task> action) : IAgentHeartbeatClient
    {
        private int _calls;
        public ConcurrentQueue<HeartbeatCall> Calls { get; } = new();

        public Task HeartbeatAsync(DeviceCredential credential, string agentVersion, InventorySnapshot? inventory,
            CancellationToken cancellationToken = default)
        {
            Calls.Enqueue(new HeartbeatCall(credential, agentVersion, inventory));
            return action(Interlocked.Increment(ref _calls), inventory, cancellationToken);
        }
    }

    private sealed class ScriptedInventory(Func<int, InventorySnapshot> action) : IInventoryProvider
    {
        private int _calls;
        public InventorySnapshot Collect() => action(Interlocked.Increment(ref _calls));
    }

    private sealed class RecordingTimeProvider(bool frozen = false) : TimeProvider
    {
        public ConcurrentQueue<TimeSpan> Delays { get; } = new();
        public TaskCompletionSource TimerCreated { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
        {
            Delays.Enqueue(dueTime);
            ITimer timer = TimeProvider.System.CreateTimer(callback, state,
                frozen ? Timeout.InfiniteTimeSpan : TimeSpan.FromMilliseconds(1), Timeout.InfiniteTimeSpan);
            TimerCreated.TrySetResult();
            return timer;
        }
    }

    private sealed record LogEntry(LogLevel Level, string Message);

    private sealed class RecordingLogger : ILogger<HeartbeatWorker>
    {
        public ConcurrentQueue<LogEntry> Entries { get; } = new();
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => true;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter) => Entries.Enqueue(new LogEntry(logLevel, formatter(state, exception)));
    }

    private sealed class TestLifetime : IHostApplicationLifetime
    {
        private int _stopCalls;
        public int StopCalls => Volatile.Read(ref _stopCalls);
        public CancellationToken ApplicationStarted => CancellationToken.None;
        public CancellationToken ApplicationStopping => CancellationToken.None;
        public CancellationToken ApplicationStopped => CancellationToken.None;
        public void StopApplication() => Interlocked.Increment(ref _stopCalls);
    }
}
