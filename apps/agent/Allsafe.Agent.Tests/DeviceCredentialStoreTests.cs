using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace Allsafe.Agent.Tests;

public sealed class DeviceCredentialStoreTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "Allsafe.Agent.Tests", Guid.NewGuid().ToString("N"));
    private const string DeviceId = "cf8e9b4d-40b3-4eaf-af2c-a43803b99c36";
    private const string DeviceToken = "private-device-store-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    [Fact]
    public async Task MissingCredentialReturnsNull()
    {
        Assert.Null(await new DeviceCredentialStore(_directory, development: true).LoadAsync());
    }

    [Fact]
    public async Task PersistedCredentialRoundTripsWithoutPlaintext()
    {
        DeviceCredential credential = NewCredential();
        DeviceCredentialStore store = new(_directory, development: true);

        await store.SaveAsync(credential);
        DeviceCredential? loaded = await new DeviceCredentialStore(_directory, development: true).LoadAsync();

        Assert.NotNull(loaded);
        Assert.Equal(credential.ServerUri, loaded.ServerUri);
        Assert.Equal(credential.DeviceId, loaded.DeviceId);
        Assert.Equal(credential.AgentToken, loaded.AgentToken);
        byte[] protectedBytes = await File.ReadAllBytesAsync(Path.Combine(_directory, "credential.bin"));
        string possiblePlaintext = Encoding.UTF8.GetString(protectedBytes);
        Assert.DoesNotContain(DeviceToken, possiblePlaintext, StringComparison.Ordinal);
        Assert.DoesNotContain(DeviceId, possiblePlaintext, StringComparison.Ordinal);
        Assert.DoesNotContain(credential.ServerUri.AbsoluteUri, possiblePlaintext, StringComparison.Ordinal);
    }

    [Fact]
    public async Task TamperedProtectedCredentialFailsWithoutExposingSecrets()
    {
        DeviceCredentialStore store = new(_directory, development: true);
        await store.SaveAsync(NewCredential());
        string file = Path.Combine(_directory, "credential.bin");
        byte[] protectedBytes = await File.ReadAllBytesAsync(file);
        protectedBytes[protectedBytes.Length / 2] ^= 0x80;
        await File.WriteAllBytesAsync(file, protectedBytes);

        AgentCredentialException failure = await Assert.ThrowsAsync<AgentCredentialException>(() => store.LoadAsync());

        Assert.DoesNotContain(DeviceToken, failure.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task ReplacementPersistsNewCredentialAndLeavesNoTemporaryPlaintextFiles()
    {
        DeviceCredentialStore store = new(_directory, development: true);
        await store.SaveAsync(NewCredential());
        DeviceCredential replacement = new(new Uri("https://allsafe.example/"), DeviceId,
            "replacement-private-device-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");

        await store.SaveAsync(replacement);
        DeviceCredential? loaded = await store.LoadAsync();

        Assert.NotNull(loaded);
        Assert.Equal(replacement.AgentToken, loaded.AgentToken);
        Assert.Empty(Directory.GetFiles(_directory, "*.tmp"));
        foreach (string file in Directory.GetFiles(_directory))
        {
            string possiblePlaintext = Encoding.UTF8.GetString(await File.ReadAllBytesAsync(file));
            Assert.DoesNotContain(replacement.AgentToken, possiblePlaintext, StringComparison.Ordinal);
            Assert.DoesNotContain(DeviceToken, possiblePlaintext, StringComparison.Ordinal);
        }
    }

    [Fact]
    public async Task DevelopmentCredentialAclDoesNotGrantOtherUsersAccess()
    {
        await new DeviceCredentialStore(_directory, development: true).SaveAsync(NewCredential());

        DirectorySecurity directorySecurity = new DirectoryInfo(_directory).GetAccessControl();
        FileSecurity fileSecurity = new FileInfo(Path.Combine(_directory, "credential.bin")).GetAccessControl();
        HashSet<string> allowed =
        [
            WindowsIdentity.GetCurrent().User!.Value,
            new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null).Value,
            new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null).Value
        ];

        try
        {
            allowed.Add(new NTAccount("NT SERVICE", "ALLSAFEAgent").Translate(typeof(SecurityIdentifier)).Value);
        }
        catch (IdentityNotMappedException) { }

        Assert.True(directorySecurity.AreAccessRulesProtected);
        Assert.True(fileSecurity.AreAccessRulesProtected);
        Assert.Equal(WindowsIdentity.GetCurrent().User, directorySecurity.GetOwner(typeof(SecurityIdentifier)));
        Assert.Equal(WindowsIdentity.GetCurrent().User, fileSecurity.GetOwner(typeof(SecurityIdentifier)));
        AssertAllowedAcl(directorySecurity, allowed);
        AssertAllowedAcl(fileSecurity, allowed);
    }

    [Theory]
    [InlineData("https://other-allsafe.example/", DeviceId)]
    [InlineData("https://allsafe.example/", "3acbeaf6-0c1c-40db-9c0d-65b88204f7fb")]
    public async Task ExistingIdentityCannotBeSilentlyReassigned(string server, string deviceId)
    {
        DeviceCredentialStore store = new(_directory, development: true);
        await store.SaveAsync(NewCredential());

        await Assert.ThrowsAsync<AgentCredentialException>(() => store.SaveAsync(
            new DeviceCredential(new Uri(server), deviceId, DeviceToken)));

        DeviceCredential? preserved = await store.LoadAsync();
        Assert.NotNull(preserved);
        Assert.Equal(DeviceId, preserved.DeviceId);
        Assert.Equal(new Uri("https://allsafe.example/"), preserved.ServerUri);
    }

    [Fact]
    public async Task BroadReadAccessToCredentialCausesLoadToFail()
    {
        DeviceCredentialStore store = new(_directory, development: true);
        await store.SaveAsync(NewCredential());
        FileInfo file = new(Path.Combine(_directory, "credential.bin"));
        FileSecurity security = file.GetAccessControl();
        security.AddAccessRule(new FileSystemAccessRule(
            new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null), FileSystemRights.Read, AccessControlType.Allow));
        file.SetAccessControl(security);

        await Assert.ThrowsAsync<AgentCredentialException>(() => store.LoadAsync());
    }

    [Fact]
    public async Task CancelledReplacementPreservesExistingCredentialAndCleansTemporaryFiles()
    {
        DeviceCredentialStore store = new(_directory, development: true);
        await store.SaveAsync(NewCredential());
        using CancellationTokenSource cancellation = new();
        cancellation.Cancel();
        DeviceCredential replacement = new(new Uri("https://allsafe.example/"), DeviceId,
            "cancelled-replacement-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => store.SaveAsync(replacement, cancellation.Token));

        DeviceCredential? preserved = await store.LoadAsync();
        Assert.NotNull(preserved);
        Assert.Equal(DeviceToken, preserved.AgentToken);
        Assert.Empty(Directory.GetFiles(_directory, "*.tmp"));
    }

    private static void AssertAllowedAcl(FileSystemSecurity security, HashSet<string> allowed)
    {
        AuthorizationRuleCollection rules = security.GetAccessRules(true, true, typeof(SecurityIdentifier));
        Assert.NotEmpty(rules.Cast<FileSystemAccessRule>());
        foreach (FileSystemAccessRule rule in rules)
        {
            if (rule.AccessControlType == AccessControlType.Allow)
            {
                Assert.Contains(rule.IdentityReference.Value, allowed);
            }
        }
    }

    private static DeviceCredential NewCredential() => new(new Uri("https://allsafe.example/"), DeviceId, DeviceToken);

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }
}
