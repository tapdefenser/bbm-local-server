// Independent .NET wire fixture using synthetic keys, not game credentials.
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

static string B64Url(byte[] data) => Convert.ToBase64String(data).TrimEnd('=').Replace('+', '-').Replace('/', '_');
var jwtKey = Encoding.UTF8.GetBytes("test-signing-key");
var aesKey = Encoding.UTF8.GetBytes("0123456789abcdef");
var header = "{\"typ\":\"JWT\",\"alg\":\"HS256\"}";
var payload = "{\"jsonPacket\":\"{\\\"userId\\\":7,\\\"sessionId\\\":11,\\\"txId\\\":3}\"}";
var input = B64Url(Encoding.UTF8.GetBytes(header)) + "." + B64Url(Encoding.UTF8.GetBytes(payload));
var token = input + "." + B64Url(HMACSHA256.HashData(jwtKey, Encoding.UTF8.GetBytes(input)));
using var aes = Aes.Create();
aes.Key = aesKey;
aes.Mode = CipherMode.ECB;
aes.Padding = PaddingMode.PKCS7;
using var transform = aes.CreateEncryptor();
var bytes = Encoding.UTF8.GetBytes(token);
var encrypted = transform.TransformFinalBlock(bytes, 0, bytes.Length);
Console.WriteLine("bbmPacket=" + Uri.EscapeDataString(Convert.ToBase64String(encrypted)));
