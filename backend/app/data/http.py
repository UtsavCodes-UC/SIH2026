"""HTTPS for the outbound calls the backend makes (TomTom traffic, place-name suggestions)."""

from __future__ import annotations

import functools
import ssl
import urllib.request


@functools.lru_cache(maxsize=1)
def tls_context() -> ssl.SSLContext:
    """The OS trust store plus the Mozilla roots that ship with certifi.

    Python on Windows reads only the roots already installed in the OS store, and Windows installs some
    lazily, so a fresh machine can fail with "self signed certificate in certificate chain" against a
    perfectly valid site (seen once against api.tomtom.com; the next call worked). Adding certifi's bundle
    makes the call independent of that. Verification stays on.
    """
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError):
        pass
    return context


def open_url(request: str | urllib.request.Request, timeout: float | None = None):
    """`urllib.request.urlopen` with certificate checking on and the context above."""
    return urllib.request.urlopen(request, timeout=timeout, context=tls_context())
