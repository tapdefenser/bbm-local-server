"""Create endpoint configuration and a local TLS certificate."""
import argparse
import hashlib
import ipaddress
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from bbm.config import validate_origin

ROOT = Path(__file__).resolve().parents[1]


def prepare(origin, bind="0.0.0.0", config_path=None):
    origin = validate_origin(origin)
    parsed = urlsplit(origin)
    if parsed.scheme != "https":
        raise ValueError("Use HTTPS for the original Android network configuration")
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    suffix = hashlib.sha256(parsed.hostname.encode()).hexdigest()[:12]
    cert_path, key_path = local / f"tls-{suffix}.crt", local / f"tls-{suffix}.key"
    if not cert_path.exists() and not key_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BBM local development")])
        alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
        try:
            alt.append(x509.IPAddress(ipaddress.ip_address(parsed.hostname)))
        except ValueError:
            alt.append(x509.DNSName(parsed.hostname))
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365))
                .add_extension(x509.SubjectAlternativeName(alt), critical=False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .sign(key, hashes.SHA256()))
        with key_path.open("xb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        with cert_path.open("xb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
    elif not cert_path.exists() or not key_path.exists():
        raise ValueError("Incomplete existing TLS files; refusing to replace them")
    config = {
        "public_url": origin, "listen_host": bind, "listen_port": parsed.port or 443,
        "source_apk": "analysis/xapk_1.4.1/net.commseed.bbm.apk",
        "asset_root": "analysis/xapk_1.4.1/obb/assets/AssetBundle",
        "gameplay_config": "config/gameplay.json",
        "bundle_version": 240,
        "database": "runtime/bbm.sqlite3", "request_log": "runtime/requests.jsonl",
        "tls_cert": cert_path.relative_to(ROOT).as_posix(), "tls_key": key_path.relative_to(ROOT).as_posix(),
        "allow_dev_login": True,
    }
    target = Path(config_path) if config_path else local / "server.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2)+"\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, help="Phone-reachable HTTPS origin, e.g. https://192.168.0.243:9100")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--config")
    args = parser.parse_args()
    print(prepare(args.server, args.bind, args.config))
