"""Configuration-only provider endpoint validation. Redirects remain disabled by callers."""

from urllib.parse import urlsplit


def endpoint(value: str, *, allow_remote: bool = True) -> str:
    p = urlsplit(value)
    local = p.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        not p.hostname
        or p.username
        or p.password
        or p.query
        or p.fragment
        or (p.scheme != "https" and not (p.scheme == "http" and local))
        or (not local and not allow_remote)
    ):
        raise ValueError("Provider requires HTTPS (or loopback HTTP), without URL credentials/query")
    return value.rstrip("/")
