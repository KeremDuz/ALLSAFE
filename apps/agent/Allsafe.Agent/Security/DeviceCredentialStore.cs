using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.Json;

namespace Allsafe.Agent;

public sealed class DeviceCredentialStore
{
    public const string ServiceName = "ALLSAFEAgent";
    private const string CredentialFileName = "credential.bin";
    private const int MaximumCredentialBytes = 32 * 1024;
    private static readonly byte[] Entropy = "ALLSAFE.Agent.DeviceCredential.v1"u8.ToArray();
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    private readonly string _directory;
    private readonly bool _development;

    public DeviceCredentialStore(string directory, bool development = false)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("ALLSAFE device credentials require Windows.");
        _directory = NormalizeDirectory(directory, development);
        _development = development;
    }

    internal static string NormalizeDirectory(string directory, bool development)
    {
        var full = Path.GetFullPath(directory);
        if (full.StartsWith("\\\\", StringComparison.Ordinal) || new DirectoryInfo(full).Parent is null)
            throw new ArgumentException("Device credentials require a local directory.", nameof(directory));
        // Win32 can resolve trailing spaces and DOS short names to a different
        // spelling of the protected directory. Require an unambiguous long path
        // before any directory creation or ACL change; use the long name instead
        // of accepting '~' even when it is part of a literal directory name.
        if (full.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            .Any(component => component.EndsWith(' ') || component.EndsWith('.') || component.Contains('~')))
            throw new ArgumentException("Device state requires a long path without ambiguous directory names.", nameof(directory));
        if (development)
        {
            var protectedRoot = Path.GetDirectoryName(Program.DefaultStateDirectory)!;
            if (string.Equals(Path.TrimEndingDirectorySeparator(full), protectedRoot, StringComparison.OrdinalIgnoreCase) ||
                full.StartsWith(protectedRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Development state must use a separate directory.", nameof(directory));
        }
        return full;
    }

    public Task<FileStream> AcquireOperationLeaseAsync(bool createIfMissing, CancellationToken cancellationToken = default)
    {
        FileStream? lease = null;
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            RejectReparseDirectories();
            var lockPath = Path.Combine(_directory, "operation.lock");
            RejectReparsePoint(lockPath);
            // Existing locks can be held by the read-only virtual service account.
            lease = OpenCredential(lockPath, FileShare.None);
            if (lease is null)
            {
                if (!createIfMissing) throw new AgentCredentialException();
                SecureDirectory();
                lease = new FileStream(lockPath, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None);
                SecureFile(lockPath);
            }
            ValidateAccess(lease);
            cancellationToken.ThrowIfCancellationRequested();
            var acquired = lease;
            lease = null;
            return Task.FromResult(acquired);
        }
        catch (Exception error) when (IsStoreFailure(error))
        {
            throw new AgentCredentialException();
        }
        finally
        {
            lease?.Dispose();
        }
    }

    public async Task SaveAsync(DeviceCredential credential, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(credential);
        string? temporaryPath = null;
        byte[]? plaintext = null;
        byte[]? encrypted = null;
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            SecureDirectory();
            // The lock also prevents two enrollment processes from replacing each other's identity.
            var lockPath = Path.Combine(_directory, "credential.lock");
            RejectReparsePoint(lockPath);
            await using var gate = new FileStream(lockPath,
                FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            var previous = await LoadAsync(cancellationToken).ConfigureAwait(false);
            if (previous is not null && (previous.DeviceId != credential.DeviceId || previous.ServerUri != credential.ServerUri))
                throw new AgentCredentialException();
            plaintext = JsonSerializer.SerializeToUtf8Bytes(
                new CredentialEnvelope(1, credential.ServerUri.AbsoluteUri, credential.DeviceId, credential.AgentToken), JsonOptions);
            encrypted = ProtectedData.Protect(plaintext, Entropy, DataProtectionScope.LocalMachine);
            if (encrypted.Length > MaximumCredentialBytes) throw new AgentCredentialException();
            temporaryPath = Path.Combine(_directory, $"credential-{Guid.NewGuid():N}.tmp");
            await using (var output = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write,
                FileShare.None, 4096, FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await output.WriteAsync(encrypted, cancellationToken).ConfigureAwait(false);
                await output.FlushAsync(cancellationToken).ConfigureAwait(false);
                output.Flush(flushToDisk: true);
            }
            cancellationToken.ThrowIfCancellationRequested();
            SecureFile(temporaryPath);
            var destination = Path.Combine(_directory, CredentialFileName);
            RejectReparsePoint(destination);
            File.Move(temporaryPath, destination, overwrite: true);
            temporaryPath = null;
        }
        catch (Exception error) when (IsStoreFailure(error))
        {
            throw new AgentCredentialException();
        }
        finally
        {
            if (plaintext is not null) CryptographicOperations.ZeroMemory(plaintext);
            if (encrypted is not null) CryptographicOperations.ZeroMemory(encrypted);
            if (temporaryPath is not null)
            {
                try { File.Delete(temporaryPath); }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
            }
        }
    }

    public async Task<DeviceCredential?> LoadAsync(CancellationToken cancellationToken = default)
    {
        byte[]? encrypted = null;
        byte[]? plaintext = null;
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            RejectReparseDirectories();
            var filename = Path.Combine(_directory, CredentialFileName);
            RejectReparsePoint(filename);
            // Exists() hides access errors and wrong-kind paths. Only a genuinely missing
            // file may be treated as an unregistered device.
            await using var input = OpenCredential(filename);
            if (input is null) return null;
            ValidateAccess(input);
            if (input.Length is <= 0 or > MaximumCredentialBytes) throw new AgentCredentialException();
            encrypted = new byte[(int)input.Length];
            await input.ReadExactlyAsync(encrypted, cancellationToken).ConfigureAwait(false);
            plaintext = ProtectedData.Unprotect(encrypted, Entropy, DataProtectionScope.LocalMachine);
            var envelope = JsonSerializer.Deserialize<CredentialEnvelope>(plaintext, JsonOptions);
            if (envelope is null || envelope.SchemaVersion != 1 || envelope.ServerUri is null ||
                envelope.DeviceId is null || envelope.AgentToken is null)
                throw new AgentCredentialException();
            return new DeviceCredential(AgentServerUri.Parse(envelope.ServerUri, allowLoopbackHttp: true),
                envelope.DeviceId, envelope.AgentToken);
        }
        catch (Exception error) when (IsStoreFailure(error))
        {
            throw new AgentCredentialException();
        }
        finally
        {
            if (encrypted is not null) CryptographicOperations.ZeroMemory(encrypted);
            if (plaintext is not null) CryptographicOperations.ZeroMemory(plaintext);
        }
    }

    private void SecureDirectory()
    {
        RejectReparseDirectories();
        Directory.CreateDirectory(_directory);
        RejectReparseDirectories();
        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        var administrator = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);
        var system = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        var currentUser = WindowsIdentity.GetCurrent().User ?? throw new AgentCredentialException();
        security.SetOwner(_development ? currentUser : administrator);
        AddDirectoryRule(security, administrator, FileSystemRights.FullControl);
        AddDirectoryRule(security, system, FileSystemRights.FullControl);
        var service = ServiceIdentifier();
        if (service is not null) AddDirectoryRule(security, service, FileSystemRights.ReadAndExecute);
        if (_development) AddDirectoryRule(security, currentUser, FileSystemRights.FullControl);
        new DirectoryInfo(_directory).SetAccessControl(security);
    }

    private static FileStream? OpenCredential(string filename, FileShare share = FileShare.Read)
    {
        try
        {
            return new FileStream(filename, FileMode.Open, FileAccess.Read,
                share, 4096, FileOptions.Asynchronous);
        }
        catch (FileNotFoundException) { return null; }
        catch (DirectoryNotFoundException) { return null; }
    }

    private void ValidateAccess(FileStream input)
    {
        var allowed = new HashSet<string>
        {
            new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null).Value,
            new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null).Value
        };
        var allowedOwners = new HashSet<string>(allowed);
        var service = ServiceIdentifier();
        if (service is not null) allowed.Add(service.Value);
        if (_development)
        {
            var currentUser = WindowsIdentity.GetCurrent().User?.Value ?? throw new AgentCredentialException();
            allowed.Add(currentUser);
            allowedOwners.Add(currentUser);
        }
        var directorySecurity = new DirectoryInfo(_directory).GetAccessControl();
        if (!directorySecurity.AreAccessRulesProtected) throw new AgentCredentialException();
        EnsureAllowed(directorySecurity, allowed, allowedOwners, FileSystemRights.ReadAndExecute);
        // Validate the exact opened object, rather than re-resolving its pathname.
        var fileSecurity = input.GetAccessControl();
        if (!fileSecurity.AreAccessRulesProtected) throw new AgentCredentialException();
        EnsureAllowed(fileSecurity, allowed, allowedOwners, FileSystemRights.Read);
    }

    private void SecureFile(string filename)
    {
        var security = new FileSecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        var administrator = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);
        var system = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        var currentUser = WindowsIdentity.GetCurrent().User ?? throw new AgentCredentialException();
        security.SetOwner(_development ? currentUser : administrator);
        security.AddAccessRule(new FileSystemAccessRule(administrator, FileSystemRights.FullControl, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(system, FileSystemRights.FullControl, AccessControlType.Allow));
        var service = ServiceIdentifier();
        if (service is not null)
            security.AddAccessRule(new FileSystemAccessRule(service, FileSystemRights.Read, AccessControlType.Allow));
        if (_development)
            security.AddAccessRule(new FileSystemAccessRule(currentUser, FileSystemRights.FullControl, AccessControlType.Allow));
        new FileInfo(filename).SetAccessControl(security);
    }

    private SecurityIdentifier? ServiceIdentifier()
    {
        try { return (SecurityIdentifier)new NTAccount("NT SERVICE", ServiceName).Translate(typeof(SecurityIdentifier)); }
        catch (IdentityNotMappedException) when (_development) { return null; }
    }

    private static void EnsureAllowed(FileSystemSecurity security, HashSet<string> allowed, HashSet<string> allowedOwners,
        FileSystemRights readOnlyRights)
    {
        var owner = security.GetOwner(typeof(SecurityIdentifier))?.Value;
        if (owner is null || !allowedOwners.Contains(owner)) throw new AgentCredentialException();
        foreach (FileSystemAccessRule rule in security.GetAccessRules(true, true, typeof(SecurityIdentifier)))
        {
            if (rule.AccessControlType != AccessControlType.Allow) continue;
            var identity = rule.IdentityReference.Value;
            if (!allowed.Contains(identity) || (!allowedOwners.Contains(identity) &&
                (rule.FileSystemRights & ~(readOnlyRights | FileSystemRights.Synchronize)) != 0))
                throw new AgentCredentialException();
        }
    }

    private static void AddDirectoryRule(DirectorySecurity security, SecurityIdentifier identity, FileSystemRights rights)
        => security.AddAccessRule(new FileSystemAccessRule(identity, rights,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));

    private static void RejectReparsePoint(string path, bool requireDirectory = false)
    {
        try
        {
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0 ||
                (requireDirectory && (attributes & FileAttributes.Directory) == 0))
                throw new AgentCredentialException();
        }
        catch (FileNotFoundException) { }
        catch (DirectoryNotFoundException) { }
    }

    private void RejectReparseDirectories()
    {
        for (var directory = new DirectoryInfo(_directory); directory is not null; directory = directory.Parent)
            RejectReparsePoint(directory.FullName, requireDirectory: true);
    }

    private static bool IsStoreFailure(Exception error) => error is IOException or UnauthorizedAccessException or
        CryptographicException or JsonException or ArgumentException or IdentityNotMappedException or System.Security.SecurityException;

    private sealed record CredentialEnvelope(int SchemaVersion, string? ServerUri, string? DeviceId, string? AgentToken);
}
