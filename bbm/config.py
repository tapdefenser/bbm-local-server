from urllib.parse import urlsplit


def validate_origin(value):
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Server URL must be an http(s) origin without credentials")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("Server URL must not include a path, query or fragment")
    if not value.isascii() or any(c.isspace() for c in value):
        raise ValueError("Server URL must be ASCII without whitespace")
    if parts.hostname in ("0.0.0.0", "::"):
        raise ValueError("Use a reachable address, not a wildcard bind address")
    # Accessing port validates its numeric syntax/range.
    if parts.port == 0:
        raise ValueError("Port must be nonzero")
    return value.rstrip("/")
