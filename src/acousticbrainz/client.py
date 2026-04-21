import requests


BASE_URL = "https://acousticbrainz.org"


class AcousticBrainzClient:
    """Client for the AcousticBrainz public API.

    AcousticBrainz was frozen in 2022: no new submissions are accepted,
    so tracks released after ~2022 are unlikely to be covered. 404 is a
    common, expected outcome — callers get None rather than an exception.
    """

    def __init__(self):
        self.session = requests.Session()

    def _get(self, path: str) -> dict | None:
        resp = self.session.get(f"{BASE_URL}/{path}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_high_level(self, mbid: str) -> dict | None:
        """High-level features: mood, danceability, genre_* classifiers."""
        try:
            return self._get(f"{mbid}/high-level")
        except requests.HTTPError:
            return None

    def get_low_level(self, mbid: str) -> dict | None:
        """Low-level features: bpm, key, loudness, spectral stats."""
        try:
            return self._get(f"{mbid}/low-level")
        except requests.HTTPError:
            return None


def extract_mood(high_level: dict) -> dict | None:
    """Reduce AB high-level output to a compact mood dict.

    Returns probabilities in [0, 1] for happy/sad/aggressive/relaxed/party,
    plus danceability. None if the high-level payload is missing the
    expected structure.
    """
    if not high_level:
        return None
    hl = high_level.get("highlevel") or {}
    if not hl:
        return None

    def prob(section: str, positive_label: str) -> float | None:
        node = hl.get(section)
        if not node:
            return None
        probs = node.get("all") or {}
        val = probs.get(positive_label)
        return round(float(val), 3) if val is not None else None

    return {
        "happy": prob("mood_happy", "happy"),
        "sad": prob("mood_sad", "sad"),
        "aggressive": prob("mood_aggressive", "aggressive"),
        "relaxed": prob("mood_relaxed", "relaxed"),
        "party": prob("mood_party", "party"),
        "danceability": prob("danceability", "danceable"),
    }


def extract_genre(high_level: dict) -> str | None:
    """Pick the top genre label from the Dortmund classifier, if present."""
    if not high_level:
        return None
    hl = high_level.get("highlevel") or {}
    node = hl.get("genre_dortmund")
    if not node:
        return None
    return node.get("value")


def extract_bpm(low_level: dict) -> float | None:
    """Return BPM from the low-level rhythm section."""
    if not low_level:
        return None
    rhythm = low_level.get("rhythm") or {}
    bpm = rhythm.get("bpm")
    return round(float(bpm), 1) if bpm is not None else None
