namespace Allsafe.Agent.RemoteDesktop;

public static class DesktopApplication
{
    public static Task<int> RunAsync(DeviceCredential credential, HttpClient http, bool unattended = false)
    {
        // This public entry point must not bypass the unattended administrator requirement.
        if (unattended) DesktopAccessPolicy.RequireAdministrator(development: true, unattended: true, NativeDesktopSurface.IsElevated);
        var complete = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() =>
        {
            try
            {
                Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                using var surface = new DesktopSurfaceLifetime();
                using var form = new DesktopConsentForm(credential, surface.Value, NativeDesktopSurface.IsElevated, unattended);
                using var cancellation = new CancellationTokenSource();
                var coordinator = new DesktopCoordinator(new RemoteDesktopApi(http, credential), surface.Value, form, TimeProvider.System);
                Task worker = Task.CompletedTask;
                int result = 0;
                form.Shown += (_, _) => worker = Task.Run(async () =>
                {
                    try { await coordinator.RunAsync(cancellation.Token).ConfigureAwait(false); }
                    catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
                    catch (Exception)
                    {
                        result = 3;
                        form.Idle("Uzaktan destek durduruldu. Cihaz bağlantısını ve sunucu ayarlarını kontrol edip uygulamayı yeniden açın.");
                    }
                    finally { surface.Value.ReleaseAll(); }
                });
                form.FormClosing += (_, _) => { surface.Value.SetSharingEnabled(false); cancellation.Cancel(); surface.Value.ReleaseAll(); };
                Application.Run(form);
                cancellation.Cancel();
                worker.GetAwaiter().GetResult();
                complete.TrySetResult(result);
            }
            catch (Exception) { complete.TrySetResult(3); }
        }) { Name = "ALLSAFE visible remote support", IsBackground = false };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        return complete.Task;
    }

    private sealed class DesktopSurfaceLifetime : IDisposable
    {
        public NativeDesktopSurface Value { get; } = new();
        public void Dispose() { Value.SetSharingEnabled(false); Value.ReleaseAll(); }
    }
}

internal sealed class DesktopConsentForm : Form, IDesktopConsent
{
    private readonly Label _status = new() { AutoSize = false, Height = 70, Dock = DockStyle.Top, Padding = new Padding(16, 8, 16, 4) };
    private readonly Label _details = new() { AutoSize = false, Height = 60, Dock = DockStyle.Top, Padding = new Padding(16, 4, 16, 4), UseMnemonic = false };
    private readonly TextBox _operator = new() { ReadOnly = true, Dock = DockStyle.Top, Height = 32, TabStop = false };
    private readonly TextBox _reason = new() { ReadOnly = true, Multiline = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Top, Height = 78, TabStop = false };
    private readonly Button _allow = new() { Text = "Bu oturuma izin ver", Width = 165, Height = 38, Visible = false };
    private readonly Button _deny = new() { Text = "Reddet", Width = 100, Height = 38, Visible = false };
    private readonly Button _stop = new() { Text = "Oturumu durdur", Width = 165, Height = 38, Enabled = false };
    private readonly IDesktopSurface _surface;
    private readonly bool _unattended;
    private TaskCompletionSource<bool>? _pending;
    private Action? _stopAction;

    public DesktopConsentForm(DeviceCredential credential, IDesktopSurface surface, bool elevated, bool unattended = false)
    {
        DesktopAccessPolicy.RequireAdministrator(development: true, unattended, elevated);
        _surface = surface;
        _unattended = unattended;
        Text = "ALLSAFE | Uzaktan destek";
        ClientSize = new Size(620, 620);
        Font = new Font("Segoe UI", 10);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        StartPosition = FormStartPosition.CenterScreen;
        var title = new Label
        { Text = "ALLSAFE Uzaktan Destek", Dock = DockStyle.Top, Height = 58, Font = new Font(Font, FontStyle.Bold), Padding = new Padding(16, 18, 16, 8) };
        var warning = new Label
        {
            Text = unattended
                ? "Bu uygulama yönetici yetkileriyle çalışıyor. Yetkili panel operatörü, yerel onay beklemeden masaüstünüzde bu uygulamanın Windows yetkileriyle işlem yapabilir."
                : elevated
                    ? "Bu uygulama yönetici yetkileriyle çalışıyor. Kontrol izni verdiğinizde operatör masaüstünüzde bu uygulamanın Windows yetkileriyle işlem yapabilir."
                    : "Kontrol izni verdiğinizde operatör masaüstünüzde sizin Windows yetkilerinizle işlem yapabilir.",
            Dock = DockStyle.Top, Height = 80, Padding = new Padding(16, 8, 16, 8), ForeColor = Color.DarkRed
        };
        var mode = new Label
        {
            Text = unattended ? "Yönetilen erişim açık; yerel onay beklenmez." : "Her oturum için bu bilgisayardan ayrı izin gerekir.",
            Dock = DockStyle.Top, Height = 44, Padding = new Padding(16, 8, 16, 8),
            BackColor = unattended ? Color.LightGoldenrodYellow : SystemColors.Control,
            Font = new Font(Font, FontStyle.Bold)
        };
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 64, Padding = new Padding(12, 8, 12, 8) };
        buttons.Controls.AddRange([_allow, _deny, _stop]);
        Controls.Add(buttons); Controls.Add(_reason); Controls.Add(_operator); Controls.Add(_details); Controls.Add(_status); Controls.Add(mode); Controls.Add(warning); Controls.Add(title);
        _details.Text = $"Cihaz: {credential.DeviceId}\nSunucu: {credential.ServerUri.Host}";
        _status.Text = "Bağlantı isteği bekleniyor. Pencereyi kapatmak uzaktan desteği durdurur.";
        _allow.Click += (_, _) => ResolvePending(true);
        _deny.Click += (_, _) => ResolvePending(false);
        _stop.Click += (_, _) => StopSession();
        FormClosing += (_, _) => { _pending?.TrySetCanceled(); StopSession(); };
    }

    public Task<bool> AskAsync(DesktopSession session, CancellationToken cancellationToken)
        => DesktopAccessPolicy.DecideAsync(_unattended, session, TimeProvider.System,
            token => AskWithConsentAsync(session, token), cancellationToken);

    private async Task<bool> AskWithConsentAsync(DesktopSession session, CancellationToken cancellationToken)
    {
        var answer = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cancelled = cancellationToken.Register(() => answer.TrySetCanceled(cancellationToken));
        Post(() =>
        {
            if (answer.Task.IsCompleted) return;
            _pending = answer;
            _stopAction = null;
            _stop.Enabled = false;
            _allow.Visible = true; _deny.Visible = true;
            _status.Text = "Uzaktan destek isteği. İzin vermeden ekranınız paylaşılmaz ve giriş kabul edilmez.";
            _details.Text = SessionDetails(session);
            _operator.Text = "İsteyen: " + session.OperatorName;
            _reason.Text = "Amaç: " + session.Reason;
            Activate(); BringToFront();
        });
        try { return await answer.Task.ConfigureAwait(false); }
        finally { Post(() => { if (_pending == answer) { _pending = null; _allow.Visible = false; _deny.Visible = false; } }); }
    }

    public async Task ActiveAsync(DesktopSession session, Action stop, CancellationToken cancellationToken)
    {
        var visible = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cancelled = cancellationToken.Register(() => visible.TrySetCanceled(cancellationToken));
        Post(() =>
        {
            if (visible.Task.IsCompleted) return;
            _stopAction = stop;
            _stop.Enabled = true;
            _allow.Visible = false; _deny.Visible = false;
            _status.Text = session.Mode == "control" ? "Uzaktan kontrol açık. İstediğiniz anda oturumu durdurabilirsiniz." : "Ekran görüntüleme açık. Klavye ve fare kontrolü kapalı.";
            _details.Text = SessionDetails(session);
            _operator.Text = "İsteyen: " + session.OperatorName;
            _reason.Text = "Amaç: " + session.Reason;
            visible.TrySetResult();
        });
        await visible.Task.ConfigureAwait(false);
    }

    public void Idle(string message)
    {
        Post(() =>
        {
            _status.Text = message;
            _stopAction = null;
            _stop.Enabled = false;
            _allow.Visible = false; _deny.Visible = false;
        });
    }

    private void ResolvePending(bool accepted)
    {
        _pending?.TrySetResult(accepted);
        _allow.Visible = false; _deny.Visible = false;
        _status.Text = accepted ? "İzin verildi. Bağlantı kuruluyor." : "İstek reddedildi.";
    }

    private void StopSession()
    {
        _stopAction?.Invoke();
        _surface.ReleaseAll();
        _stop.Enabled = false;
        _status.Text = "Oturum durduruluyor.";
    }

    private void Post(Action action)
    {
        if (IsDisposed || Disposing || !IsHandleCreated) return;
        try { BeginInvoke((MethodInvoker)(() => { if (!IsDisposed && !Disposing) action(); })); }
        catch (InvalidOperationException) { }
    }

    private static string SessionDetails(DesktopSession session) =>
        $"Yetki: {(session.Mode == "control" ? "Ekran, klavye ve fare" : "Yalnızca ekran")}\nSon geçerlilik: {session.ExpiresAt.ToLocalTime():dd.MM.yyyy HH:mm:ss}";
}
