"""Enrich the user's top Last.fm tracks with MusicBrainz + AcousticBrainz metadata.

Replaces the old Spotify audio-features pipeline after Spotify closed
the `/audio-features` endpoint for new apps in late 2024.
"""
import os
from collections import Counter

from dotenv import load_dotenv

from src.lastfm.client import LastFMClient
from src.lastfm.cache import fetch_or_update
from src.lastfm.parser import parse_top_tracks
from src.musicbrainz.client import MusicBrainzClient
from src.acousticbrainz.client import AcousticBrainzClient
from src.genius.client import GeniusClient
from src.metadata.provider import resolve_track_metadata_cached

load_dotenv()

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_USERNAME = os.getenv("LASTFM_USERNAME")
MUSICBRAINZ_CONTACT = os.getenv("MUSICBRAINZ_CONTACT")
GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")

if not all([LASTFM_API_KEY, LASTFM_USERNAME, MUSICBRAINZ_CONTACT]):
    raise SystemExit(
        "Missing env vars — set LASTFM_API_KEY, LASTFM_USERNAME, "
        "MUSICBRAINZ_CONTACT in .env"
    )

TOP_N = int(os.getenv("ENRICH_TOP_N", "50"))

lastfm = LastFMClient(LASTFM_API_KEY)
mb = MusicBrainzClient(contact=MUSICBRAINZ_CONTACT)
ab = AcousticBrainzClient()
genius = GeniusClient(GENIUS_ACCESS_TOKEN) if GENIUS_ACCESS_TOKEN else None
genius_search_fn = genius.search_song if genius else None
if genius:
    print("Genius enabled — will use as year fallback")
else:
    print("Genius not configured (set GENIUS_ACCESS_TOKEN to enable)")

print(f"Fetching top {TOP_N} tracks from Last.fm...")
raw_tracks = fetch_or_update(
    f"{LASTFM_USERNAME}_top_tracks_3month_{TOP_N}",
    lambda: lastfm.get_top_tracks(LASTFM_USERNAME, period="3month", limit=TOP_N),
)
df_tracks = parse_top_tracks(raw_tracks)
print(f"Got {len(df_tracks)} tracks\n")

print("Resolving metadata (MusicBrainz + AcousticBrainz, cached)...")
results = []
for _, row in df_tracks.iterrows():
    meta = resolve_track_metadata_cached(
        artist=row["artist"],
        track=row["track"],
        mb=mb,
        ab=ab,
        lastfm_tags_fn=lastfm.get_track_tags,
        known_mbid=row["mbid"] or None,
        genius_search_fn=genius_search_fn,
    )
    results.append(meta)

covered = sum(1 for m in results if m.mbid)
with_mood = sum(1 for m in results if m.mood)
with_bpm = sum(1 for m in results if m.bpm)
with_year = sum(1 for m in results if m.year)

print("=" * 60)
print(f"COVERAGE (top {len(results)})")
print(f"  MBID resolved:    {covered}/{len(results)}")
print(f"  Release year:     {with_year}/{len(results)}")
print(f"  AB mood:          {with_mood}/{len(results)}")
print(f"  AB BPM:           {with_bpm}/{len(results)}")

print("\n" + "=" * 60)
print("PER TRACK")
for m in results:
    mood_str = "-"
    if m.mood:
        dominant = max(
            ((k, v) for k, v in m.mood.items() if v is not None),
            key=lambda kv: kv[1],
            default=(None, None),
        )
        if dominant[0]:
            mood_str = f"{dominant[0]}={dominant[1]:.2f}"
    bpm_str = f"{m.bpm:.0f}" if m.bpm else "-"
    year_str = str(m.year) if m.year else "-"
    genre_str = ", ".join(m.genres[:2]) if m.genres else "-"
    print(f"  {m.artist[:24]:24} | {m.track[:32]:32} | {year_str:>4} | {bpm_str:>4} | {mood_str:>18} | {genre_str}")

print("\n" + "=" * 60)
print("TOP GENRES (aggregated from MB/AB/Last.fm)")
genre_counter: Counter = Counter()
for m in results:
    for g in m.genres:
        genre_counter[g] += 1
for genre, count in genre_counter.most_common(15):
    print(f"  {count:3}  {genre}")

print("\n" + "=" * 60)
print("RELEASE YEAR DISTRIBUTION")
year_counter = Counter(m.year for m in results if m.year)
for year in sorted(year_counter):
    bar = "#" * year_counter[year]
    print(f"  {year}  {bar}")
