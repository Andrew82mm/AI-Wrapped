from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field

from src.lastfm.cache import fetch_or_update
from src.musicbrainz.client import MusicBrainzClient, extract_release_year, extract_tags
from src.acousticbrainz.client import (
    AcousticBrainzClient,
    extract_mood,
    extract_genre,
    extract_bpm,
)
from src.genius.client import extract_release_year as genius_extract_year


@dataclass
class TrackMetadata:
    """Unified per-track metadata assembled from MB + AB + Last.fm.

    Any field may be None when the upstream source did not cover the
    track — callers should treat missing values as expected, not errors.
    """
    artist: str
    track: str
    mbid: str | None = None
    year: int | None = None
    genres: list[str] = field(default_factory=list)
    mood: dict | None = None
    bpm: float | None = None
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_track_metadata(
    artist: str,
    track: str,
    mb: MusicBrainzClient,
    ab: AcousticBrainzClient,
    lastfm_tags_fn=None,
    known_mbid: str | None = None,
    genius_search_fn=None,
) -> TrackMetadata:
    """Compose TrackMetadata for a single track across providers.

    Resolution order:
      1. MBID — use `known_mbid` if given, else search MusicBrainz.
      2. Release year + MB tags from the recording lookup.
      3. AcousticBrainz high/low level for mood, genre, BPM.
      4. Last.fm track tags as a genre fallback when MB/AB gave nothing.
      5. Genius release year as a fallback when MB had no date.

    `lastfm_tags_fn`  — optional callable `(artist, track) -> list[str]`.
    `genius_search_fn` — optional callable `(artist, track) -> song_dict`.
    Both are injected to keep this module free of provider coupling.
    """
    meta = TrackMetadata(artist=artist, track=track)

    mbid = known_mbid or None
    if not mbid:
        recording = mb.search_recording(artist, track)
        if recording:
            mbid = recording.get("id")
            meta.year = extract_release_year(recording)
            meta.genres = extract_tags(recording)
            meta.sources.append("musicbrainz")
    else:
        recording = mb.get_recording(mbid)
        if recording:
            meta.year = extract_release_year(recording)
            meta.genres = extract_tags(recording)
            meta.sources.append("musicbrainz")

    meta.mbid = mbid

    # All remaining calls are independent of each other — run in parallel.
    futures = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        if mbid:
            futures["ab_high"] = pool.submit(ab.get_high_level, mbid)
            futures["ab_low"] = pool.submit(ab.get_low_level, mbid)
        if not meta.genres and lastfm_tags_fn:
            futures["lfm_tags"] = pool.submit(lastfm_tags_fn, artist, track)
        if not meta.year and genius_search_fn:
            futures["genius"] = pool.submit(genius_search_fn, artist, track)

        results = {name: f.result() for name, f in futures.items()}

    # If AB returned nothing for our MBID, try other MB candidates —
    # Last.fm MBIDs often point to a different recording than AB indexed.
    if mbid and not results.get("ab_high"):
        ab_mbid = _find_ab_mbid(artist, track, mbid, mb, ab)
        if ab_mbid and ab_mbid != mbid:
            results["ab_high"] = ab.get_high_level(ab_mbid)
            results["ab_low"] = ab.get_low_level(ab_mbid)

    high = results.get("ab_high")
    if high:
        meta.mood = extract_mood(high)
        ab_genre = extract_genre(high)
        if ab_genre and ab_genre not in meta.genres:
            meta.genres = [ab_genre] + meta.genres
        meta.sources.append("acousticbrainz")

    low = results.get("ab_low")
    if low:
        meta.bpm = extract_bpm(low)

    tags = results.get("lfm_tags")
    if tags:
        meta.genres = tags
        meta.sources.append("lastfm")

    genius_song = results.get("genius")
    year = genius_extract_year(genius_song)
    if year:
        meta.year = year
        meta.sources.append("genius")

    return meta


def resolve_track_metadata_cached(
    artist: str,
    track: str,
    mb: MusicBrainzClient,
    ab: AcousticBrainzClient,
    lastfm_tags_fn=None,
    known_mbid: str | None = None,
    genius_search_fn=None,
    max_age_hours: int = 24 * 30,
) -> TrackMetadata:
    """Cached wrapper around resolve_track_metadata.

    Cache TTL defaults to 30 days since track metadata is effectively
    static — release year and MBID do not change.
    """
    key = f"meta_{_safe(artist)}___{_safe(track)}"
    payload = fetch_or_update(
        key,
        lambda: resolve_track_metadata(
            artist, track, mb, ab, lastfm_tags_fn, known_mbid, genius_search_fn
        ).to_dict(),
        max_age_hours=max_age_hours,
    )
    return TrackMetadata(**payload)


def _find_ab_mbid(
    artist: str,
    track: str,
    skip_mbid: str,
    mb: MusicBrainzClient,
    ab: AcousticBrainzClient,
) -> str | None:
    """Search MB for up to 5 recording candidates and return the first
    MBID that AcousticBrainz actually has data for.

    Skips `skip_mbid` since the caller already knows it returns 404.
    AB probes run in parallel — no rate limit on AB side.
    """
    candidates = mb.search_recording_candidates(artist, track)
    mbids = [r["id"] for r in candidates if r.get("id") and r["id"] != skip_mbid]
    if not mbids:
        return None

    with ThreadPoolExecutor(max_workers=len(mbids)) as pool:
        probe = {pool.submit(ab.get_high_level, m): m for m in mbids}
        for future in as_completed(probe):
            if future.result() is not None:
                return probe[future]
    return None


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)[:80]
