namespace Allsafe.Agent.Tests;

public sealed class CommandOptionsTests
{
    [Theory]
    [InlineData("--token", "private-secret")]
    [InlineData("--token-stdin", "--token-stdin")]
    [InlineData("--server", "--token-stdin")]
    public void AmbiguousOrSecretCommandArgumentsAreRejected(string first, string second)
    {
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["enroll", first, second]));
    }

    [Theory]
    [InlineData("run")]
    [InlineData("once")]
    [InlineData("replace-credential")]
    public void StoredDeviceServerCannotBeOverridden(string command)
    {
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse([command, "--server", "https://other.example"]));
    }

    [Theory]
    [InlineData("")]
    [InlineData("child")]
    [InlineData("..")]
    public void DevelopmentStateCannotOverlapProtectedAllsafeState(string relative)
    {
        var directory = Path.GetFullPath(Path.Combine(Program.DefaultStateDirectory, relative));
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["run", "--dev-state-dir", directory]));
    }

    [Fact]
    public void IndependentLabStateIsAccepted()
    {
        var directory = Path.GetFullPath(Path.Combine(".local", "agent-command-tests"));
        var options = CommandOptions.Parse(["run", "--allow-loopback-http", "--dev-state-dir", directory]);
        Assert.Equal(directory, options.DevelopmentDirectory);
        Assert.True(options.AllowLoopbackHttp);
    }

    [Theory]
    [InlineData("C:\\ProgramData\\ALLSAFE ")]
    [InlineData("C:\\ProgramData \\ALLSAFE\\Agent")]
    [InlineData("C:\\PROGRA~3\\ALLSAFE\\Agent")]
    public void AmbiguousStatePathsCannotBypassProtectedStateCheck(string directory)
    {
        Assert.Throws<ArgumentException>(() => CommandOptions.Parse(["run", "--dev-state-dir", directory]));
        Assert.Throws<ArgumentException>(() => new DeviceCredentialStore(directory, development: true));
    }

    [Fact]
    public void CredentialStoreItselfRejectsDevelopmentAccessToProtectedState()
    {
        Assert.Throws<ArgumentException>(() => new DeviceCredentialStore(Program.DefaultStateDirectory, development: true));
    }

    [Theory]
    [InlineData(32, "\n")]
    [InlineData(128, "\r\n")]
    [InlineData(128, "")]
    public void BoundedSecretReaderAcceptsOneCanonicalLine(int length, string ending)
    {
        string secret = new('a', length);
        using StringReader input = new(secret + ending);
        Assert.Equal(secret, Program.ReadBoundedSecret(input));
    }

    [Fact]
    public void SecretReaderDoesNotConsumeAnUnboundedInput()
    {
        using CountingReader input = new(new string('a', 100_000));
        var problem = Assert.Throws<ArgumentException>(() => Program.ReadBoundedSecret(input));
        Assert.InRange(input.Reads, 129, 130);
        Assert.DoesNotContain(new string('a', 32), problem.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData('\0')]
    [InlineData('\t')]
    [InlineData('\u007f')]
    [InlineData('\u00e9')]
    public void ControlAndNonAsciiSecretsAreRejectedWithoutEcho(char character)
    {
        string token = new string('a', 32) + character;
        Assert.Throws<ArgumentException>(() => Program.ValidateSecret(token));
        Assert.Throws<ArgumentException>(() => new DeviceCredential(new Uri("https://allsafe.example"), Guid.NewGuid().ToString(), token));
    }

    private sealed class CountingReader(string value) : StringReader(value)
    {
        public int Reads { get; private set; }
        public override int Read() { Reads++; return base.Read(); }
    }
}
