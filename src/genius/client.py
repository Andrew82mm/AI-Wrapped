import requests


BASE_URL = "https://api.genius.com"


class GeniusClient:
    """Minimal Genius API client.

    Genius is used not for audio features (it has none) but as a source
    of free-text context about songs and artists for the LLM narrative
    stage: song URL, release date, short description/annotations.
    If no token is configured, callers should skip Genius entirely.
    """

    def __init__(self, access_token: str):
        """Initialise the session with the Genius Bearer token."""
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        })

    def _get(self, path: str, **params) -> dict | None:
        """GET a Genius endpoint, returning the inner response dict or None on 404."""
        resp = self.session.get(f"{BASE_URL}/{path}", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("response")

    def search_song(self, artist: str, track: str) -> dict | None:
        """Search Genius and return the top hit for (artist, track), or None.

        Matches by case-insensitive artist substring on the primary artist.
        """
        query = f"{artist} {track}"
        data = self._get("search", q=query)
        if not data:
            return None
        hits = data.get("hits") or []
        artist_lc = artist.lower()
        for hit in hits:
            song = (hit.get("result") or {})
            primary = (song.get("primary_artist") or {}).get("name", "").lower()
            if artist_lc in primary or primary in artist_lc:
                return song
        return hits[0]["result"] if hits else None


def extract_release_year(song: dict) -> int | None:
    """Return release year from Genius `release_date_components`, or None."""
    if not song:
        return None
    components = song.get("release_date_components") or {}
    year = components.get("year")
    return int(year) if year else None


def extract_song_summary(song: dict) -> dict | None:
    """Reduce a Genius song payload to a small dict for prompt context.

    Returns title, url, release_date, primary_artist. Full description
    annotations are intentionally deferred — they require a second API
    call per song and are overkill for the current narrative scope.
    """
    if not song:
        return None
    return {
        "title": song.get("title"),
        "url": song.get("url"),
        "release_date": song.get("release_date_for_display"),
        "primary_artist": (song.get("primary_artist") or {}).get("name"),
    }
