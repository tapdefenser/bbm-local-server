"""Wire format inferred from WebManager.<WWWPost>d__26.MoveNext.

Version service: form jsonPacket=<JSON>.
Game service: form bbmPacket=Base64(AES-128-ECB-PKCS7(UTF8(HS256 JWT))).
JWT payload: {jsonPacket: <JSON string>, exp?: <unix seconds>}.
Responses are plain JSON objects, with result=1 denoting success.
"""
import base64
import hashlib
import hmac
import json
import math
import time
from urllib.parse import parse_qs, urlencode

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class ProtocolError(ValueError):
    pass


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


class Codec:
    def __init__(self, jwt_key, aes_key):
        self.jwt_key, self.aes_key = jwt_key, aes_key

    def encode(self, packet, expires=None):
        claims = {"jsonPacket": json_bytes(packet).decode()}
        if expires is not None:
            claims["exp"] = expires
        message = b64url(json_bytes({"typ": "JWT", "alg": "HS256"})) + b"." + b64url(json_bytes(claims))
        token = message + b"." + b64url(hmac.digest(self.jwt_key, message, "sha256"))
        pad = padding.PKCS7(128).padder()
        padded = pad.update(token) + pad.finalize()
        encryptor = Cipher(algorithms.AES(self.aes_key), modes.ECB()).encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()
        return urlencode({"bbmPacket": base64.b64encode(encrypted).decode()}).encode()

    def decode(self, body, content_type):
        try:
            if content_type.split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
                raise ProtocolError("Expected form-urlencoded body")
            form = parse_qs(body.decode("ascii"), keep_blank_values=True, max_num_fields=8)
            if set(form) == {"jsonPacket"} and len(form["jsonPacket"]) == 1:
                packet = json.loads(form["jsonPacket"][0])
                wire = "jsonPacket"
            elif set(form) == {"bbmPacket"} and len(form["bbmPacket"]) == 1:
                ciphertext = base64.b64decode(form["bbmPacket"][0], validate=True)
                if not ciphertext or len(ciphertext) % 16:
                    raise ProtocolError("Invalid encrypted packet size")
                decryptor = Cipher(algorithms.AES(self.aes_key), modes.ECB()).decryptor()
                padded = decryptor.update(ciphertext) + decryptor.finalize()
                unpad = padding.PKCS7(128).unpadder()
                token = unpad.update(padded) + unpad.finalize()
                head, payload, signature = token.split(b".")
                decode64 = lambda value: base64.b64decode(value + b"=" * (-len(value) % 4), altchars=b"-_", validate=True)
                header = json.loads(decode64(head))
                if not isinstance(header, dict) or header.get("alg") != "HS256":
                    raise ProtocolError("Unexpected JWT algorithm")
                expected = hmac.digest(self.jwt_key, head + b"." + payload, "sha256")
                if not hmac.compare_digest(decode64(signature), expected):
                    raise ProtocolError("Invalid packet signature")
                claims = json.loads(decode64(payload))
                if not isinstance(claims, dict):
                    raise ProtocolError("Invalid JWT claims")
                expiry = claims.get("exp")
                if expiry is not None and (type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry < time.time() - 30):
                    raise ProtocolError("Expired or invalid packet timestamp")
                packet = json.loads(claims["jsonPacket"])
                wire = "bbmPacket"
            else:
                raise ProtocolError("Expected exactly one jsonPacket or bbmPacket field")
            if not isinstance(packet, dict):
                raise ProtocolError("Packet must be an object")
            return packet, wire
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            if isinstance(exc, ProtocolError):
                raise
            raise ProtocolError("Malformed packet") from exc


def redact(value):
    private = {"accesstoken", "sessionid", "udid", "dui", "password", "token", "nickname"}
    if isinstance(value, dict):
        return {k: "<redacted>" if k.lower() in private else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
