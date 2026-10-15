namespace Allsafe.Agent.RemoteDesktop;

internal static class DesktopAccessPolicy
{
    internal static void RequireAdministrator(bool development, bool unattended, bool elevated)
    {
        if (unattended && !elevated)
            throw new ArgumentException("Unattended desktop access requires an explicitly launched local administrator, including laboratory mode.");
        if (!development && !elevated)
            throw new ArgumentException("Launch remote desktop explicitly as a local administrator to read the protected device identity. Device permissions must not be weakened.");
    }

    internal static Task<bool> DecideAsync(bool unattended, DesktopSession pending, TimeProvider clock,
        Func<CancellationToken, Task<bool>> ask, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!unattended) return ask(cancellationToken);
        // This local mode changes only the approval gesture. The coordinator still
        // matches the server decision, activates visible Stop, and waits for relay readiness.
        return Task.FromResult(pending.Status == "pending" && pending.Mode is "view" or "control" &&
            pending.ExpiresAt > clock.GetUtcNow());
    }
}
