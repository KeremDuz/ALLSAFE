using System.Security.Cryptography;

namespace Allsafe.Agent.RemoteDesktop;

public sealed class DesktopCoordinator(IRemoteDesktopApi api, IDesktopSurface surface,
    IDesktopConsent consent, TimeProvider clock)
{
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                surface.ReleaseAll();
                var pending = await api.PendingAsync(cancellationToken).ConfigureAwait(false);
                foreach (var session in pending)
                {
                    if (session.Status != "pending" || session.ExpiresAt <= clock.GetUtcNow()) continue;
                    await HandleSessionAsync(session, cancellationToken).ConfigureAwait(false);
                }
                consent.Idle("Bağlantı isteği bekleniyor. Pencereyi kapatmak uzaktan desteği durdurur.");
            }
            catch (AgentApiException problem) when (problem.IsTransient)
            { consent.Idle("Sunucuya ulaşılamıyor. Yeniden bağlantı bekleniyor."); }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { break; }
            await Task.Delay(TimeSpan.FromSeconds(3), clock, cancellationToken).ConfigureAwait(false);
        }
    }

    internal async Task HandleSessionAsync(DesktopSession pending, CancellationToken cancellationToken)
    {
        if (pending.Status != "pending" || pending.Mode is not ("view" or "control") ||
            pending.ExpiresAt <= clock.GetUtcNow() || !surface.IsAvailable) return;
        using var approvalDeadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        approvalDeadline.CancelAfter(Min(pending.ExpiresAt - clock.GetUtcNow(), TimeSpan.FromMinutes(2)));
        bool accepted;
        try { accepted = await consent.AskAsync(pending, approvalDeadline.Token).ConfigureAwait(false); }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        { consent.Idle("İsteğin süresi doldu."); return; }
        if (accepted && !surface.IsAvailable) accepted = false;
        var decision = await api.DecideAsync(pending.Id, accepted, cancellationToken).ConfigureAwait(false);
        if (!accepted) { consent.Idle("İstek reddedildi."); return; }
        // Approval is tied to the exact request shown locally, never to a later mode/operator change.
        if (decision.Id != pending.Id || decision.DeviceId != pending.DeviceId || decision.Mode != pending.Mode ||
            decision.OperatorName != pending.OperatorName || decision.Reason != pending.Reason || decision.Status != "approved" ||
            decision.ExpiresAt <= clock.GetUtcNow() || decision.ExpiresAt > clock.GetUtcNow().AddMinutes(10).AddSeconds(2) ||
            !surface.IsAvailable)
            throw new InvalidDataException("Remote desktop approval does not match local consent.");
        using var session = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var grantGate = new object();
        using var revokeGrant = session.Token.Register(() => { lock (grantGate) surface.SetSharingEnabled(false); });
        session.CancelAfter(Min(decision.ExpiresAt - clock.GetUtcNow(), TimeSpan.FromMinutes(10)));
        try
        {
            await consent.ActiveAsync(decision, () =>
            {
                lock (grantGate)
                {
                    surface.SetSharingEnabled(false);
                    try { session.Cancel(); }
                    catch (ObjectDisposedException) { }
                }
            }, session.Token).ConfigureAwait(false);
            await using var connection = await api.ConnectAsync(decision.Id, session.Token).ConfigureAwait(false);
            var ready = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            Task sender = SendFramesAfterReadyAsync(connection, ready.Task, session.Token),
                receiver = ReceiveInputAsync(connection, decision.Mode, ready, grantGate, session.Token);
            try { await await Task.WhenAny(sender, receiver).ConfigureAwait(false); }
            finally
            {
                session.Cancel();
                surface.ReleaseAll();
                try { await Task.WhenAll(sender, receiver).ConfigureAwait(false); }
                catch (OperationCanceledException) when (session.IsCancellationRequested) { }
            }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested) { }
        catch (Exception problem) when (problem is IOException or System.Net.WebSockets.WebSocketException or InvalidDataException or TimeoutException)
        { consent.Idle("Uzaktan destek bağlantısı sona erdi. Yeniden bağlantı için yeni onay gerekir."); }
        finally
        {
            session.Cancel();
            surface.SetSharingEnabled(false);
            surface.ReleaseAll();
            consent.Idle("Uzaktan destek sona erdi. Yeni bir oturum için yeniden izin istenir.");
        }
    }

    private async Task SendFramesAfterReadyAsync(IDesktopConnection connection, Task ready, CancellationToken cancellationToken)
    {
        await ready.WaitAsync(TimeSpan.FromSeconds(15), cancellationToken).ConfigureAwait(false);
        await SendFramesAsync(connection, cancellationToken).ConfigureAwait(false);
    }

    private async Task SendFramesAsync(IDesktopConnection connection, CancellationToken cancellationToken)
    {
        int lastWidth = 0, lastHeight = 0;
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!surface.IsAvailable) throw new InvalidDataException("Interactive desktop is unavailable.");
            var frame = surface.Capture();
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (frame.Width is < 1 or > DesktopProtocol.MaximumWidth || frame.Height is < 1 or > DesktopProtocol.MaximumHeight ||
                    frame.Jpeg.Length is 0 or > DesktopProtocol.MaximumFrameBytes)
                    throw new InvalidDataException("Desktop frame exceeds the limit.");
                if (lastWidth != frame.Width || lastHeight != frame.Height)
                {
                    if (lastWidth != 0) throw new InvalidDataException("Display resolution changed; new local consent is required.");
                    await connection.SendDisplayAsync(frame.Width, frame.Height, cancellationToken).ConfigureAwait(false);
                    lastWidth = frame.Width; lastHeight = frame.Height;
                }
                cancellationToken.ThrowIfCancellationRequested();
                if (!surface.IsAvailable) throw new InvalidDataException("Interactive desktop is unavailable.");
                await connection.SendFrameAsync(frame.Jpeg, cancellationToken).ConfigureAwait(false);
            }
            finally { CryptographicOperations.ZeroMemory(frame.Jpeg); }
            await Task.Delay(TimeSpan.FromMilliseconds(500), clock, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task ReceiveInputAsync(IDesktopConnection connection, string mode, TaskCompletionSource ready, object grantGate, CancellationToken cancellationToken)
    {
        while (true)
        {
            var input = await connection.ReceiveAsync(cancellationToken).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            if (input is null || input.Type == "stop") return;
            if (input.Type == "ready")
            {
                lock (grantGate)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    surface.SetSharingEnabled(true);
                    if (!ready.TrySetResult()) throw new InvalidDataException("Duplicate desktop readiness message.");
                }
                continue;
            }
            if (!ready.Task.IsCompletedSuccessfully) throw new InvalidDataException("Input arrived before the operator joined.");
            if (!surface.IsAvailable) throw new InvalidDataException("Interactive desktop is unavailable.");
            if (input.Type == "release") { surface.ReleaseAll(); continue; }
            if (mode != "control") throw new InvalidDataException("Input is unavailable in view mode.");
            cancellationToken.ThrowIfCancellationRequested();
            surface.Apply(input);
        }
    }

    private static TimeSpan Min(TimeSpan first, TimeSpan second) => first < second ? first : second;
}
