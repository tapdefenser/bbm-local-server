"""Bounded IL2CPP 24.1 string-literal reads/patches for the supplied BBM build."""
import hashlib
import struct
from dataclasses import dataclass

METADATA_ENTRY = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
METADATA_SHA256 = "77282de5193ffa9c4b3648bc5704b01d1fb7194edb9c60fd9e60a7a6d49f8cf6"
APK_SHA256 = "4218e0dcccfe2fb86617588a41557edc5269ea0fae5780e03a3e31e6c3f7501e"
BOOTSTRAP_URLS = (
    "https://version.bigbadmonsters.net:9100",
    "https://qa-version.bigbadmonsters.net:9100",
    "https://qa-2-version.bigbadmonsters.net:9100",
)


@dataclass(frozen=True)
class Literal:
    index: int
    table_offset: int
    offset: int
    size: int
    value: bytes


def literals(blob):
    if len(blob) < 32:
        raise ValueError("Truncated IL2CPP metadata")
    magic, version, table, size, data, data_size = struct.unpack_from("<6I", blob)
    if magic != 0xFAB11BAF or version != 24 or size % 8:
        raise ValueError("Expected IL2CPP metadata version 24")
    if table + size > len(blob) or data + data_size > len(blob):
        raise ValueError("Metadata table outside file")
    result = []
    for index, pos in enumerate(range(table, table + size, 8)):
        length, offset = struct.unpack_from("<II", blob, pos)
        if offset + length > data_size:
            raise ValueError(f"Literal {index} outside data region")
        result.append(Literal(index, pos, data + offset, length, bytes(blob[data+offset:data+offset+length])))
    return result


def require_original(blob):
    if hashlib.sha256(blob).hexdigest() != METADATA_SHA256:
        raise ValueError("Metadata is not the supported, unmodified 1.4.1 build")


def protocol_keys(blob):
    require_original(blob)
    table = literals(blob)
    # Identified from WebManager..cctor and Start in the ARM64 client.
    # Material is read from the user's local package; it is not embedded here.
    jwt_key, crypto_key = table[1320].value, table[1345].value
    if len(jwt_key) != 40 or len(crypto_key) != 39:
        raise ValueError("Unexpected protocol literal lengths")
    return jwt_key, crypto_key[:16]


def patch_bootstrap(blob, server_url):
    require_original(blob)
    replacement = server_url.encode("ascii")
    table = literals(blob)
    selected = [x for x in table if x.value.decode("utf-8") in BOOTSTRAP_URLS]
    if len(selected) != len(BOOTSTRAP_URLS):
        raise ValueError("Expected exactly three production/QA bootstrap literals")
    out = bytearray(blob)
    report = []
    for item in selected:
        if len(replacement) > item.size:
            raise ValueError(f"URL is too long ({len(replacement)} bytes); maximum is {min(x.size for x in selected)}")
        for other in table:
            if other.index != item.index and max(item.offset, other.offset) < min(item.offset+item.size, other.offset+other.size):
                raise ValueError("Overlapping string literals: refusing in-place patch")
        out[item.offset:item.offset+item.size] = replacement + bytes(item.size-len(replacement))
        struct.pack_into("<I", out, item.table_offset, len(replacement))
        report.append({"literal_index": item.index, "offset": item.offset,
                       "old": item.value.decode(), "new": server_url})
    patched = literals(out)
    affected = {x.index for x in selected}
    for before, after in zip(table, patched):
        if after.value != (replacement if before.index in affected else before.value):
            raise ValueError("Unrelated metadata string changed")
    return bytes(out), report
