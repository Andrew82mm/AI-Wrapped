"""Shared HTTP client base for the metadata provider clients.

MusicBrainz, AcousticBrainz and Genius each wrapped a `requests.Session` and a
near-identical GET-then-parse-JSON helper. This centralises the session setup,
the request timeout (previously missing everywhere), and the 404→None handling
so those concerns live in one place. Provider-specific behaviour (MusicBrainz's
rate-limit throttle, Genius's `.response` unwrapping, etc.) stays in the
subclasses.
"""
from __future__ import annotations

import requests

# (connect, read) seconds. A missing timeout lets a stalled socket hang the
# whole pipeline indefinitely.
DEFAULT_TIMEOUT = (10, 30)


class BaseHTTPClient:
    """A thin `requests.Session` wrapper with a timeout and JSON GET helper."""

    def __init__(
        self,
        headers: dict | None = None,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    ):
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)
        self.timeout = timeout

    def _get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        allow_404: bool = False,
    ) -> dict | None:
        """GET `url` and return parsed JSON.

        With `allow_404=True`, a 404 returns None instead of raising (common for
        AcousticBrainz/Genius lookups that legitimately miss). Any other non-2xx
        raises `requests.HTTPError`.
        """
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if allow_404 and resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
