using Microsoft.Extensions.Hosting.WindowsServices;
using Microsoft.Extensions.Logging.EventLog;

namespace Allsafe.Agent;

public static class Program
{
    public const string AgentVersion = "0.1.0";
    public const string ServiceName = "ALLSAFEAgent";
    public static string DefaultStateDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "ALLSAFE", "Agent");

    public static async Task<int> Main(string[] args)
    {
        if (!OperatingSystem.IsWindows()) { Console.Error.WriteLine("ALLSAFE Agent requires Windows."); return 1; }
        CommandOptions? options = null;
        try
        {
            options = CommandOptions.Parse(args);
            if (options.Command == "help") { PrintHelp(); return 0; }
            if (WindowsServiceHelpers.IsWindowsService() && options.DevelopmentDirectory is not null)
                throw new ArgumentException("Development state is unavailable in service mode.");
            var store = new DeviceCredentialStore(options.DevelopmentDirectory ?? DefaultStateDirectory,
                development: options.DevelopmentDirectory is not null);
            using var http = CreateHttpClient();
            var api = new AgentApiClient(http);
            if (options.Command == "desktop")
            {
                RemoteDesktop.NativeDesktopSurface.RequireInteractiveUser(options.DevelopmentDirectory is not null);
                var identity = await store.LoadAsync() ?? throw new ArgumentException("No device identity exists. Enroll first.");
                _ = AgentServerUri.Parse(identity.ServerUri.ToString(), options.AllowLoopbackHttp);
                await using var desktop = await store.AcquireDesktopLeaseAsync();
                return await RemoteDesktop.DesktopApplication.RunAsync(identity, http);
            }
            if (options.Command == "status")
            {
                var identity = await store.LoadAsync() ?? throw new ArgumentException("No device identity exists. Enroll first.");
                _ = AgentServerUri.Parse(identity.ServerUri.ToString(), options.AllowLoopbackHttp);
                if (options.Server is not null && AgentServerUri.Parse(options.Server, options.AllowLoopbackHttp) != identity.ServerUri)
                    throw new ArgumentException("Stored identity belongs to another server. No server change was applied.");
                Console.WriteLine($"Device: {identity.DeviceId}. Protected identity can be loaded. This does not confirm server access.");
                Console.WriteLine($"Server: {identity.ServerUri}. Agent version: {AgentVersion}.");
                return 0;
            }
            // Validate enrollment configuration before creating a protected state directory.
            var enrollmentServer = options.Command == "enroll"
                ? AgentServerUri.Parse(options.RequiredServer(), options.AllowLoopbackHttp) : null;
            await using var operation = await store.AcquireOperationLeaseAsync(createIfMissing: true);
            if (options.Command == "enroll")
            {
                if (await store.LoadAsync() is not null)
                    throw new ArgumentException("A device identity already exists. Reuse it or stop the service before credential replacement.");
                var token = ReadSecret(options.TokenFromStdin);
                var credential = await api.EnrollAsync(enrollmentServer!, token, Environment.MachineName, AgentVersion, CancellationToken.None);
                await store.SaveAsync(credential);
                Console.WriteLine($"Device enrolled: {credential.DeviceId}. Credential saved with Windows protection.");
                return 0;
            }
            var saved = await store.LoadAsync() ?? throw new ArgumentException("No device identity exists. Enroll first.");
            _ = AgentServerUri.Parse(saved.ServerUri.ToString(), options.AllowLoopbackHttp);
            if (options.Command == "replace-credential")
            {
                var token = ReadSecret(options.TokenFromStdin);
                var replacement = new DeviceCredential(saved.ServerUri, saved.DeviceId, token);
                await api.HeartbeatAsync(replacement, AgentVersion, new WindowsInventoryProvider().Collect(), CancellationToken.None);
                await store.SaveAsync(replacement);
                Console.WriteLine("Replacement credential verified and saved. Restart the service.");
                return 0;
            }
            if (options.Command == "once")
            {
                await api.HeartbeatAsync(saved, AgentVersion, new WindowsInventoryProvider().Collect(), CancellationToken.None);
                Console.WriteLine($"Heartbeat accepted for device {saved.DeviceId}.");
                return 0;
            }
            var builder = Host.CreateApplicationBuilder(new HostApplicationBuilderSettings
            {
                Args = Array.Empty<string>(), ContentRootPath = AppContext.BaseDirectory
            });
            builder.Services.AddWindowsService(config => config.ServiceName = ServiceName);
            builder.Logging.ClearProviders();
            if (WindowsServiceHelpers.IsWindowsService())
            {
                builder.Logging.AddEventLog(config => { config.SourceName = ServiceName; config.LogName = "Application"; });
                builder.Logging.AddFilter<EventLogLoggerProvider>(null, LogLevel.Information);
            }
            else builder.Logging.AddSimpleConsole(config => { config.SingleLine = true; config.TimestampFormat = "yyyy-MM-dd HH:mm:ss "; config.UseUtcTimestamp = true; });
            var exitStatus = new AgentExitStatus();
            builder.Services.AddSingleton(saved);
            builder.Services.AddSingleton<IAgentHeartbeatClient>(api);
            builder.Services.AddSingleton<IInventoryProvider, WindowsInventoryProvider>();
            builder.Services.AddSingleton(TimeProvider.System);
            builder.Services.AddSingleton(exitStatus);
            builder.Services.AddHostedService<HeartbeatWorker>();
            using var host = builder.Build();
            await host.RunAsync();
            return exitStatus.ExitCode;
        }
        catch (AgentApiException problem)
        {
            Console.Error.WriteLine(problem.Message);
            if (options?.Command == "enroll")
                Console.Error.WriteLine("Enrollment is never retried automatically. If its response was lost, review the device list before obtaining a new invitation.");
            return 2;
        }
        catch (AgentCredentialException) { Console.Error.WriteLine("Protected state is busy, inaccessible or invalid. Stop the running agent before enrollment or credential replacement; check state permissions if the problem remains."); return 3; }
        catch (ArgumentException problem) { Console.Error.WriteLine(problem.Message); return 1; }
        catch (Exception) { Console.Error.WriteLine("Agent encountered a local startup or runtime failure. Identity preserved; check the service event log or console. No automatic enrollment was attempted."); return 3; }
    }

    public static HttpClient CreateHttpClient() => new(new HttpClientHandler
    {
        AllowAutoRedirect = false, UseCookies = false, UseProxy = false,
        UseDefaultCredentials = false, Credentials = null, MaxResponseHeadersLength = 16
    })
    { Timeout = TimeSpan.FromSeconds(20) };

    private static string ReadSecret(bool fromStdin)
    {
        if (fromStdin) return ReadBoundedSecret(Console.In);
        if (Console.IsInputRedirected) throw new ArgumentException("Use --token-stdin for an explicitly redirected secret.");
        Console.Write("Invitation or replacement token (hidden): ");
        var characters = new List<char>();
        while (true)
        {
            var key = Console.ReadKey(intercept: true);
            if (key.Key == ConsoleKey.Enter) break;
            if (key.Key == ConsoleKey.Backspace) { if (characters.Count > 0) characters.RemoveAt(characters.Count - 1); }
            else if (!char.IsControl(key.KeyChar) && characters.Count < 129) characters.Add(key.KeyChar);
        }
        Console.WriteLine();
        return ValidateSecret(new string(characters.ToArray()));
    }

    internal static string ReadBoundedSecret(TextReader input)
    {
        var characters = new List<char>(128);
        int value;
        while ((value = input.Read()) != -1 && value != '\n')
        {
            if (characters.Count == 129) throw new ArgumentException("A token must contain 32 to 128 visible ASCII characters.");
            characters.Add((char)value);
        }
        // Accept a single CRLF line without allowing other control characters.
        if (characters.Count > 0 && characters[^1] == '\r') characters.RemoveAt(characters.Count - 1);
        return ValidateSecret(new string(characters.ToArray()));
    }

    internal static string ValidateSecret(string value)
    {
        if (value.Length is < 32 or > 128 || value.Any(character => character is < '!' or > '~'))
            throw new ArgumentException("A token must contain 32 to 128 visible ASCII characters.");
        return value;
    }

    private static void PrintHelp() => Console.WriteLine("""
        ALLSAFE Windows Agent
        enroll --server https://allsafe.example [--token-stdin]
        run | once | status | replace-credential [--token-stdin]
        desktop (explicit interactive launch; every session requires local consent)
        Laboratory only: --allow-loopback-http --dev-state-dir <directory>
        Tokens are accepted through a hidden prompt or explicit stdin, never command arguments.
        Default identity directory: %ProgramData%\ALLSAFE\Agent
        """);
}

internal sealed record CommandOptions(string Command, string? Server, string? DevelopmentDirectory, bool AllowLoopbackHttp, bool TokenFromStdin)
{
    public string RequiredServer() => Server ?? throw new ArgumentException("Enrollment requires --server.");
    public static CommandOptions Parse(string[] args)
    {
        if (args.Length == 0 || args[0] is "help" or "--help") return new("help", null, null, false, false);
        if (args[0] is not ("enroll" or "run" or "once" or "status" or "replace-credential" or "desktop"))
            throw new ArgumentException("Unknown command. Use help.");
        string? server = null, directory = null;
        bool loopback = false, stdin = false;
        var seen = new HashSet<string>();
        for (var i = 1; i < args.Length; i++)
        {
            var key = args[i];
            if (!seen.Add(key)) throw new ArgumentException("Options must not be repeated.");
            switch (key)
            {
                case "--server":
                    if (++i >= args.Length || args[i].StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException("Missing server address.");
                    server = args[i]; break;
                case "--dev-state-dir":
                    if (++i >= args.Length || args[i].StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException("Missing development directory.");
                    directory = DeviceCredentialStore.NormalizeDirectory(args[i], development: true);
                    break;
                case "--allow-loopback-http": loopback = true; break;
                case "--token-stdin": stdin = true; break;
                default: throw new ArgumentException("Unknown option. Secrets must not be supplied as arguments.");
            }
        }
        if (server is not null && args[0] is not ("enroll" or "status")) throw new ArgumentException("Server address is stored during enrollment.");
        if (stdin && args[0] is not ("enroll" or "replace-credential")) throw new ArgumentException("This command does not accept a token.");
        return new(args[0], server, directory, loopback, stdin);
    }
}
