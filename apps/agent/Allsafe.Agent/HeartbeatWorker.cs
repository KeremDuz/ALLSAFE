namespace Allsafe.Agent;

public sealed class HeartbeatWorker(AgentApiClient api, DeviceCredential credential,
    ILogger<HeartbeatWorker> logger, IHostApplicationLifetime lifetime) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var failures = 0;
        while (!stoppingToken.IsCancellationRequested)
        {
            TimeSpan delay;
            try
            {
                await api.HeartbeatAsync(credential, Program.AgentVersion, new WindowsInventoryProvider().Collect(), stoppingToken);
                failures = 0;
                logger.LogInformation("Device heartbeat accepted.");
                delay = TimeSpan.FromSeconds(30);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (AgentApiException problem) when (problem.IsTransient)
            {
                failures = Math.Min(failures + 1, 5);
                delay = RetryDelay(failures, Random.Shared.NextDouble());
                logger.LogWarning("Connection temporarily unavailable. Retrying in {Seconds:F0} seconds.", delay.TotalSeconds);
            }
            catch (AgentApiException)
            {
                logger.LogError("Server rejected the device credential or protocol. Local identity preserved; administrator action required.");
                Environment.ExitCode = 2;
                lifetime.StopApplication();
                return;
            }
            catch (Exception)
            {
                logger.LogError("Local inventory collection failed. No new device was created.");
                delay = TimeSpan.FromSeconds(30);
            }
            try { await Task.Delay(delay, stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
        }
    }

    public static TimeSpan RetryDelay(int failures, double jitter) =>
        TimeSpan.FromSeconds(Math.Min(60, 5 * Math.Pow(2, Math.Clamp(failures - 1, 0, 4)) + Math.Clamp(jitter, 0, 1)));
}
