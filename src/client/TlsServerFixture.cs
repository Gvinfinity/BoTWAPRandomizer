using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Cryptography.X509Certificates;

namespace BotWClient;

// TLS termination for the local protocol fixture. The test subprocess trusts
// only the temporary certificate via SSL_CERT_FILE; production validation stays on.
internal sealed class TlsServerFixture : IDisposable
{
    private readonly TcpListener listener = new(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource stop = new(TimeSpan.FromSeconds(20));
    private readonly X509Certificate2 certificate;
    private readonly Task worker;
    public string Uri { get; }

    public TlsServerFixture(string backend, string certificatePath)
    {
        certificate = X509CertificateLoader.LoadPkcs12FromFile(certificatePath, null);
        listener.Start();
        Uri = $"wss://127.0.0.1:{((IPEndPoint)listener.LocalEndpoint).Port}";
        worker = Run(new Uri(backend).Port);
    }

    private async Task Run(int backendPort)
    {
        try
        {
            using var client = await listener.AcceptTcpClientAsync(stop.Token);
            using var tls = new SslStream(client.GetStream());
            await tls.AuthenticateAsServerAsync(new SslServerAuthenticationOptions { ServerCertificate = certificate }, stop.Token);
            using var backend = new TcpClient();
            await backend.ConnectAsync(IPAddress.Loopback, backendPort, stop.Token);
            using var stream = backend.GetStream();
            var toBackend = tls.CopyToAsync(stream, stop.Token);
            var toClient = stream.CopyToAsync(tls, stop.Token);
            await Task.WhenAny(toBackend, toClient);
            stop.Cancel();
            await Task.WhenAll(toBackend, toClient);
        }
        catch (Exception) when (stop.IsCancellationRequested) { }
    }

    public void Dispose()
    {
        stop.Cancel(); listener.Stop();
        try { worker.GetAwaiter().GetResult(); }
        finally { certificate.Dispose(); stop.Dispose(); }
    }
}
