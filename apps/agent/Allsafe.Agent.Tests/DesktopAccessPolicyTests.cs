using Allsafe.Agent.RemoteDesktop;

namespace Allsafe.Agent.Tests;

public sealed class DesktopAccessPolicyTests
{
    private static DesktopSession Pending => new(Guid.NewGuid().ToString(), Guid.NewGuid().ToString(),
        "administrator@example.test", "Yönetilen cihaz desteği", "control", "pending",
        DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(2), null);

    [Fact]
    public void DesktopUsesConsentUnlessUnattendedIsExplicit()
    {
        Assert.False(CommandOptions.Parse(["desktop"]).Unattended);
        Assert.True(CommandOptions.Parse(["desktop", "--unattended"]).Unattended);
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["desktop", "--unattended", "--unattended"]));
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["desktop", "--unattended", "--token-stdin"]));
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["desktop", "--unattended", "--server", "https://other.example"]));
    }

    [Theory]
    [InlineData("enroll")]
    [InlineData("run")]
    [InlineData("once")]
    [InlineData("status")]
    [InlineData("replace-credential")]
    [InlineData("help")]
    [InlineData("--help")]
    public void UnattendedOptionCannotChangeOtherCommands(string command)
        => Assert.Throws<ArgumentException>(() => CommandOptions.Parse([command, "--unattended"]));

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void UnattendedRequiresAdministratorEvenWithLaboratoryIdentity(bool development)
    {
        Assert.Throws<ArgumentException>(() => DesktopAccessPolicy.RequireAdministrator(development, unattended: true, elevated: false));
        DesktopAccessPolicy.RequireAdministrator(development, unattended: true, elevated: true);
    }

    [Fact]
    public void ConsentedLaboratoryModeDoesNotRequireElevation()
    {
        DesktopAccessPolicy.RequireAdministrator(development: true, unattended: false, elevated: false);
        Assert.Throws<ArgumentException>(() => DesktopAccessPolicy.RequireAdministrator(development: false, unattended: false, elevated: false));
    }

    [Fact]
    public async Task DefaultPolicyStillWaitsForTheLocalGesture()
    {
        var answer = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        int prompts = 0;
        var decision = DesktopAccessPolicy.DecideAsync(false, Pending, TimeProvider.System,
            _ => { prompts++; return answer.Task; }, CancellationToken.None);
        Assert.Equal(1, prompts);
        Assert.False(decision.IsCompleted);
        answer.SetResult(false);
        Assert.False(await decision);
    }

    [Fact]
    public async Task ExplicitUnattendedModeAuthorizesAValidRequestWithoutPrompting()
    {
        bool prompt = false;
        bool accepted = await DesktopAccessPolicy.DecideAsync(true, Pending, TimeProvider.System,
            _ => { prompt = true; return Task.FromResult(false); }, CancellationToken.None);
        Assert.True(accepted);
        Assert.False(prompt);
    }

    [Theory]
    [InlineData("pending", "shell", false)]
    [InlineData("approved", "control", false)]
    [InlineData("closed", "view", false)]
    [InlineData("pending", "control", true)]
    public async Task UnattendedModeCannotAuthorizeInvalidOrExpiredRequests(string status, string mode, bool expired)
    {
        var pending = Pending with { Status = status, Mode = mode };
        if (expired) pending = pending with { ExpiresAt = DateTimeOffset.UtcNow.AddSeconds(-1) };
        bool accepted = await DesktopAccessPolicy.DecideAsync(true, pending, TimeProvider.System,
            _ => throw new InvalidOperationException("Unexpected local prompt"), CancellationToken.None);
        Assert.False(accepted);
    }

    [Fact]
    public async Task CancelledUnattendedRequestCannotBeAuthorized()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => DesktopAccessPolicy.DecideAsync(true, Pending,
            TimeProvider.System, _ => Task.FromResult(true), cancellation.Token));
    }
}
