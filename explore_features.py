"""Compute narrative features from full Last.fm history + track metadata."""
import json
import os

from dotenv import load_dotenv

from src.lastfm.client import LastFMClient
from src.lastfm.cache import fetch_or_update
from src.lastfm.parser import parse_scrobbles
from src.musicbrainz.client import MusicBrainzClient
from src.acousticbrainz.client import AcousticBrainzClient
from src.metadata.provider import resolve_track_metadata_cached
from src.lastfm.parser import parse_top_tracks

from src.features.decade import decade_fingerprint
from src.features.binge import binge_weeks
from src.features.time_profile import time_signature
from src.features.artist_loyalty import artist_loyalty
from src.features.discovery import discovery_rate

load_dotenv()

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_USERNAME = os.getenv("LASTFM_USERNAME")
MUSICBRAINZ_CONTACT = os.getenv("MUSICBRAINZ_CONTACT")
GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
TOP_N = int(os.getenv("ENRICH_TOP_N", "50"))

if not all([LASTFM_API_KEY, LASTFM_USERNAME, MUSICBRAINZ_CONTACT]):
    raise SystemExit("Missing env vars — check .env")

lastfm = LastFMClient(LASTFM_API_KEY)
mb = MusicBrainzClient(contact=MUSICBRAINZ_CONTACT)
ab = AcousticBrainzClient()

genius_search_fn = None
if GENIUS_ACCESS_TOKEN:
    from src.genius.client import GeniusClient
    genius_search_fn = GeniusClient(GENIUS_ACCESS_TOKEN).search_song

# --- Full scrobble history (cached 24h) ---
print("Fetching full scrobble history (cached 24h)...")
raw_all = fetch_or_update(
    f"{LASTFM_USERNAME}_all_scrobbles",
    lambda: lastfm.get_recent_tracks(LASTFM_USERNAME),
    max_age_hours=24,
)
df_all = parse_scrobbles(raw_all)
print(f"  {len(df_all)} scrobbles, "
      f"{df_all['timestamp'].min().date()} → {df_all['timestamp'].max().date()}\n")

# --- Top-N track metadata (reuses explore_metadata cache) ---
print(f"Loading top-{TOP_N} track metadata...")
raw_top = fetch_or_update(
    f"{LASTFM_USERNAME}_top_tracks_3month_{TOP_N}",
    lambda: lastfm.get_top_tracks(LASTFM_USERNAME, period="3month", limit=TOP_N),
)
df_top = parse_top_tracks(raw_top)
track_metas = []
for _, row in df_top.iterrows():
    meta = resolve_track_metadata_cached(
        artist=row["artist"],
        track=row["track"],
        mb=mb,
        ab=ab,
        lastfm_tags_fn=lastfm.get_track_tags,
        known_mbid=row["mbid"] or None,
        genius_search_fn=genius_search_fn,
    )
    track_metas.append(meta)
print(f"  {len(track_metas)} tracks loaded from cache\n")

# --- Compute features ---
print("Computing features...")
features = {
    "decade_fingerprint": decade_fingerprint(track_metas),
    "binge_weeks":        binge_weeks(df_all),
    "time_signature":     time_signature(df_all),
    "artist_loyalty":     artist_loyalty(df_all),
    "discovery_rate":     discovery_rate(df_all),
}

# --- Print results ---
sep = "=" * 60
for name, result in features.items():
    print(f"\n{sep}")
    print(name.upper().replace("_", " "))
    print(json.dumps(result, ensure_ascii=False, indent=2))

total_size = len(json.dumps(features, ensure_ascii=False))
print(f"\n{sep}")
print(f"Total context size: {total_size} bytes ({total_size // 1024} KB)")
