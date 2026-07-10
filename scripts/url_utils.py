"""Safe urllib wrapper that enforces https/http scheme validation."""

import urllib.request
from urllib.parse import urlparse

USER_AGENT = "knowledge-acquisition-skill/1.0"


def safe_urlopen(url_or_request: urllib.request.Request | str, *, timeout: int = 30):  # nosemgrep: dynamic-urllib-use-detected
    """Open a URL after validating the scheme is https or http.

    Prevents file:// and other dangerous scheme attacks flagged by
    semgrep rule dynamic-urllib-use-detected.
    """
    url = url_or_request.full_url if isinstance(url_or_request, urllib.request.Request) else url_or_request
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"URL scheme not allowed: {parsed.scheme!r}")
    return urllib.request.urlopen(url_or_request, timeout=timeout)  # nosec B310  # nosemgrep
