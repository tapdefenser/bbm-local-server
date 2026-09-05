"""Patch the metadata string table, rebuild a copy, then align/sign/verify it.

Neither executable code nor AndroidManifest.xml needs modifying for this
milestone: WebManager already attaches its AllPassCertHandler for HTTPS.
"""
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from bbm.config import validate_origin
from bbm.metadata import APK_SHA256, METADATA_ENTRY, patch_bootstrap

ROOT = Path(__file__).resolve().parents[1]
SIGNER_HASH = "e1299fd6fcf4da527dd53735b56127e8ea922a321128123b9c32d619bba1d835"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def is_signature(name):
    return name.upper().startswith("META-INF/") and (name.upper().endswith((".SF", ".RSA", ".DSA", ".EC")) or name.upper() == "META-INF/MANIFEST.MF")


def build(source, origin, output, sign=True):
    origin = validate_origin(origin)
    if urlsplit(origin).scheme != "https":
        raise ValueError("This patch preserves the Android manifest; use an HTTPS endpoint")
    source, output = Path(source).resolve(), Path(output).resolve()
    if sha256(source) != APK_SHA256:
        raise ValueError("Expected the unmodified net.commseed.bbm 1.4.1 APK")
    output.mkdir(parents=True, exist_ok=True)
    unsigned = output / "bbm-local-unsigned.apk"
    if unsigned.exists() or (output / "patch-report.json").exists():
        raise ValueError("Output already contains a build; choose a new output directory")
    signer = ROOT / ".tools/uber-apk-signer-1.3.0.jar"
    if sign and (not signer.is_file() or sha256(signer) != SIGNER_HASH):
        raise ValueError("Verified uber-apk-signer 1.3.0 required; run tools/setup.ps1")
    with zipfile.ZipFile(source) as src:
        patched, changes = patch_bootstrap(src.read(METADATA_ENTRY), origin)
        with zipfile.ZipFile(unsigned, "x") as dest:
            for entry in src.infolist():
                if is_signature(entry.filename):
                    continue
                payload = patched if entry.filename == METADATA_ENTRY else src.read(entry)
                dest.writestr(copy.copy(entry), payload)
    report = {"source": str(source), "source_sha256": APK_SHA256, "server": origin,
              "changes": changes, "unsigned_sha256": sha256(unsigned),
              "runtime_verified": False, "manifest_changed": False, "native_code_changed": False}
    if sign:
        keystore = ROOT / ".local/bbm-debug.keystore"
        keystore.parent.mkdir(exist_ok=True)
        if not keystore.exists():
            keytool = shutil.which("keytool")
            if not keytool:
                raise ValueError("JDK keytool not found")
            subprocess.run([keytool, "-genkeypair", "-noprompt", "-keystore", str(keystore),
                            "-storepass", "android", "-keypass", "android", "-alias", "androiddebugkey",
                            "-dname", "CN=BBM Local Development", "-keyalg", "RSA", "-keysize", "2048",
                            "-validity", "3650", "-storetype", "JKS"], check=True)
        subprocess.run(["java", "-jar", str(signer), "--apks", str(unsigned), "--out", str(output / "signed"),
                        "--ksDebug", str(keystore)], check=True)
        signed = list((output / "signed").glob("*.apk"))
        if len(signed) != 1:
            raise ValueError("Expected one signed APK")
        signed = signed[0]
        # Verify unchanged content of every original entry outside the literal patch/signatures.
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(signed) as dest:
            expected = {x.filename for x in src.infolist() if not is_signature(x.filename)}
            actual = {x.filename for x in dest.infolist() if not is_signature(x.filename)}
            if expected != actual:
                raise ValueError("Unexpected APK entry changes after signing")
            for name in expected:
                if dest.read(name) != (patched if name == METADATA_ENTRY else src.read(name)):
                    raise ValueError(f"Unexpected content change: {name}")
        report.update({"signed_apk": str(signed), "signed_sha256": sha256(signed), "content_verified": True})
    (output / "patch-report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(ROOT / "analysis/xapk_1.4.1/net.commseed.bbm.apk"))
    parser.add_argument("--server", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--unsigned-only", action="store_true")
    args = parser.parse_args()
    build(args.source, args.server, args.output, not args.unsigned_only)
