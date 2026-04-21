import time
import requests


BASE_URL = "https://musicbrainz.org/ws/2"
MIN_INTERVAL = 1.0  # MusicBrainz policy: <= 1 request per second


class MusicBrainzClient:
    """Thin client over the MusicBrainz web service.

    A descriptive User-Agent with a contact is required by MB policy.
    The client enforces a 1 req/sec global rate limit across all calls.
    """

    def __init__(self, contact: str, app_name: str = "AI-Wrapped", app_version: str = "0.1"):
        """Set up the session with the MB-required User-Agent header.

        contact must be an email or URL per MusicBrainz policy; without it
        requests may be blocked.
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"{app_name}/{app_version} ( {contact} )",
            "Accept": "application/json",
        })
        self._last_request_at: float = 0.0

    def _throttle(self) -> None:
        """Sleep if needed to enforce the 1 req/sec MusicBrainz rate limit."""
        elapsed = time.time() - self._last_request_at
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        self._last_request_at = time.time()

    def _get(self, path: str, **params) -> dict:
        """Throttle, then GET a MusicBrainz endpoint, returning parsed JSON."""
        self._throttle()
        params.setdefault("fmt", "json")
        resp = self.session.get(f"{BASE_URL}/{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def search_recording(self, artist: str, track: str) -> dict | None:
        """Find the best matching recording for (artist, track).

        Fetches the top 5 candidates and prefers the one with
        `first-release-date` set; falls back to the first result.
        Returns None if nothing matched.
        """
        query = f'recording:"{_escape(track)}" AND artist:"{_escape(artist)}"'
        try:
            data = self._get("recording", query=query, limit=5, inc="releases+tags")
        except requests.HTTPError:
            return None
        recordings = data.get("recordings") or []
        if not recordings:
            return None
        with_date = [r for r in recordings if r.get("first-release-date")]
        return with_date[0] if with_date else recordings[0]

    def search_recording_candidates(self, artist: str, track: str) -> list[dict]:
        """Return up to 5 raw recording candidates without picking one.

        Used by the metadata provider to probe AcousticBrainz for the
        best MBID when the primary MBID returns 404 in AB.
        """
        query = f'recording:"{_escape(track)}" AND artist:"{_escape(artist)}"'
        try:
            data = self._get("recording", query=query, limit=5, inc="releases+tags")
        except requests.HTTPError:
            return []
        return data.get("recordings") or []

    def get_recording(self, mbid: str) -> dict | None:
        """Fetch a recording by MBID, including releases and tags."""
        try:
            return self._get(f"recording/{mbid}", inc="releases+tags+artist-credits")
        except requests.HTTPError:
            return None


def extract_release_year(recording: dict) -> int | None:
    """Return the earliest release year for a recording dict, or None.

    Prefers `first-release-date`; falls back to the minimum year across
    any attached releases.
    """
    first = recording.get("first-release-date") or ""
    year = _year_from_date(first)
    if year is not None:
        return year

    years = []
    for rel in recording.get("releases", []) or []:
        y = _year_from_date(rel.get("date", ""))
        if y is not None:
            years.append(y)
    return min(years) if years else None


def extract_tags(recording: dict, top_n: int = 5) -> list[str]:
    """Return the most-voted tags from a recording dict."""
    tags = recording.get("tags") or []
    tags_sorted = sorted(tags, key=lambda t: int(t.get("count", 0)), reverse=True)
    return [t["name"].lower() for t in tags_sorted[:top_n]]


def _escape(s: str) -> str:
    """Escape double quotes in a Lucene query string."""
    return s.replace('"', '\\"')


def _year_from_date(date_str: str) -> int | None:
    """Parse a YYYY[-MM[-DD]] date string and return the year, or None."""
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None
