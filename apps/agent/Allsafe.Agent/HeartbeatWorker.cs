namespace Allsafe.Agent;

public sealed class AgentExitStatus
{
    public int ExitCode { get; private set; }
    internal void Fail(int code) => ExitCode = code;
}

public sealed class HeartbeatWorker(IAgentHeartbeatClient api, DeviceCredential credential,
    IInventoryProvider inventory, ILogger<HeartbeatWorker> logger,
    IHostApplicationLifetime lifetime, TimeProvider clock, AgentExitStatus exitStatus) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var failures = 0;
        var connected = false;
        var inventoryUnavailable = false;
        while (!stoppingToken.IsCancellationRequested)
        {
            InventorySnapshot? snapshot = null;
            try
            {
                snapshot = inventory.Collect();
                if (inventoryUnavailable) logger.LogInformation("Inventory collection recovered.");
                inventoryUnavailable = false;
            }
            catch (Exception)
            {
                if (!inventoryUnavailable)
                    logger.LogWarning("Inventory unavailable. Heartbeat will continue without an inventory update.");
                inventoryUnavailable = true;
            }

            TimeSpan delay;
            try
            {
                await api.HeartbeatAsync(credential, Program.AgentVersion, snapshot, stoppingToken);
                if (!connected || failures > 0)
                    logger.LogInformation("ALLSAFE connection established.");
                else logger.LogDebug("Device heartbeat accepted.");
                connected = true;
                failures = 0;
                delay = TimeSpan.FromSeconds(30 + Random.Shared.NextDouble() * 3);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (AgentApiException problem) when (problem.IsTransient)
            {
                failures = Math.Min(failures + 1, 5);
                delay = RetryDelay(failures, Random.Shared.NextDouble());
                if (problem.RetryAfter is { } requested && requested > delay) delay = requested;
                if (failures == 1)
                    logger.LogWarning("Connection unavailable (HTTP {Status}). Retrying in {Seconds:F0} seconds.",
                        problem.StatusCode?.ToString() ?? "unavailable", delay.TotalSeconds);
                else logger.LogDebug("Connection retry in {Seconds:F0} seconds.", delay.TotalSeconds);
            }
            catch (AgentApiException problem)
            {
                logger.LogError("Server rejected the device credential or protocol (HTTP {Status}). Identity preserved; administrator action required.",
                    problem.StatusCode?.ToString() ?? "unavailable");
                exitStatus.Fail(2);
                lifetime.StopApplication();
                return;
            }
            catch (Exception)
            {
                logger.LogError("Local agent failure. Identity preserved; administrator action required.");
                exitStatus.Fail(3);
                lifetime.StopApplication();
                return;
            }
            try { await Task.Delay(delay, clock, stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
        }
    }

    public static TimeSpan RetryDelay(int failures, double jitter) =>
        TimeSpan.FromSeconds(Math.Min(60, 5 * Math.Pow(2, Math.Clamp(failures - 1, 0, 4)) + Math.Clamp(jitter, 0, 1)));
}
