namespace Allsafe.Agent.Tests;

public sealed class HeartbeatRetryTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    [InlineData(100)]
    public void RetryDelayStaysWithinFiveToSixtySeconds(int failures)
    {
        Assert.InRange(HeartbeatWorker.RetryDelay(failures, 0).TotalSeconds, 5, 60);
        Assert.InRange(HeartbeatWorker.RetryDelay(failures, 1).TotalSeconds, 5, 60);
    }

    [Fact]
    public void ContinuedFailureIncreasesDelayUntilItReachesTheCap()
    {
        double previous = 0;
        for (int failures = 1; failures <= 5; failures++)
        {
            double delay = HeartbeatWorker.RetryDelay(failures, 0.5).TotalSeconds;
            Assert.True(delay > previous);
            previous = delay;
        }
        Assert.Equal(TimeSpan.FromSeconds(60), HeartbeatWorker.RetryDelay(5, 0.5));
        Assert.Equal(TimeSpan.FromSeconds(60), HeartbeatWorker.RetryDelay(int.MaxValue, 1));
    }

    [Fact]
    public void JitterChangesAnUncappedDelayAndIsClampedAtItsBounds()
    {
        TimeSpan minimum = HeartbeatWorker.RetryDelay(2, 0);
        TimeSpan maximum = HeartbeatWorker.RetryDelay(2, 1);

        Assert.True(maximum > minimum);
        Assert.Equal(minimum, HeartbeatWorker.RetryDelay(2, -1));
        Assert.Equal(maximum, HeartbeatWorker.RetryDelay(2, 2));
    }
}
