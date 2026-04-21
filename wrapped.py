"""Single entry point for the AI-Wrapped pipeline.

Replaces the three ad-hoc `explore_*.py` scripts. Runs the full chain:
profile & sessions  →  top-N metadata enrichment  →  feature computation,
with granular stage selection so you don't pay for what you don't need.

Usage
-----
  python wrapped.py                     # full pipeline
  python wrapped.py --stages profile    # just profile + sessions
  python wrapped.py --stages features   # features only (needs cached data)
  python wrapped.py --period 2025       # scope to calendar year 2025
  python wrapped.py --period last:90    # scope to last 90 days
  python wrapped.py --json out.json     # dump LLM context to file
  python wrapped.py --top-n 100         # override ENRICH_TOP_N

Stages can be combined: --stages profile,metadata or just --stages all.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta

from dotenv import load_dotenv

from src.lastfm.client import LastFMClient
from src.lastfm.cache import fetch_or_update
from src.lastfm.parser import (
    parse_scrobbles, parse_top_artists, parse_top_tracks, parse_top_albums,
)
from src.lastfm.sessions import detect_sessions, sessions_to_df, find_patterns
from src.musicbrainz.client import MusicBrainzClient
from src.acousticbrainz.client import AcousticBrainzClient
from src.metadata.provider import resolve_track_metadata_cached

from src.features.decade import decade_fingerprint
from src.features.binge import binge_weeks
from src.features.time_profile import time_signature
from src.features.artist_loyalty import artist_loyalty
from src.features.discovery import discovery_rate
from src.features.mood_trajectory import mood_trajectory
from src.features.context_switch import context_switches
from src.features.neighbours import musical_roommates
from src.features.guilty_pleasures import guilty_pleasures
from src.features.listening_style import listening_style
from src.features.artifacts import year_artifacts
from src.features.period import Period, filter_df, year_period, last_n_days


STAGE_ALIASES = {
    "all":      ("profile", "metadata", "features"),
    "profile":  ("profile",),
    "metadata": ("metadata",),
    "features": ("profile", "metadata", "features"),  # features depend on both
}


# --- plumbing ---------------------------------------------------------------

def _parse_stages(raw: str) -> set[str]:
    stages: set[str] = set()
    for chunk in raw.split(","):
        key = chunk.strip().lower()
        if key not in STAGE_ALIASES:
            raise SystemExit(f"Unknown stage: {key!r}. "
                             f"Valid: {', '.join(STAGE_ALIASES)}")
        stages.update(STAGE_ALIASES[key])
    return stages


def _parse_period(raw: str | None, df=None) -> Period | None:
    """Translate --period CLI value into a Period (or None)."""
    if not raw:
        return None
    if raw.startswith("last:"):
        days = int(raw.split(":", 1)[1])
        if df is None or df.empty:
            return None
        return last_n_days(df, days)
    if raw.isdigit() and len(raw) == 4:
        return year_period(int(raw))
    # ISO range "YYYY-MM-DD:YYYY-MM-DD"
    if ":" in raw:
        lo, hi = raw.split(":", 1)
        return Period(
            name=raw,
            start=datetime.fromisoformat(lo),
            end=datetime.fromisoformat(hi),
        )
    raise SystemExit(f"Unrecognised --period value: {raw!r}")


def _header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)


# --- stages -----------------------------------------------------------------

def run_profile(lastfm: LastFMClient, username: str, *, verbose: bool) -> dict:
    """Pull user info + top artists/tracks/albums + full scrobble history.

    Returns a dict with parsed DataFrames and session list — everything
    later stages need, shared via one in-memory context rather than
    re-read from disk.
    """
    if verbose:
        _header("PROFILE")

    info = fetch_or_update(
        f"{username}_info",
        lambda: lastfm.get_user_info(username),
        max_age_hours=24,
    )
    registered = datetime.fromtimestamp(int(info["registered"]["unixtime"]))

    raw_artists = fetch_or_update(
        f"{username}_top_artists_3month",
        lambda: lastfm.get_top_artists(username, period="3month", limit=50),
    )
    raw_tracks_top = fetch_or_update(
        f"{username}_top_tracks_3month",
        lambda: lastfm.get_top_tracks(username, period="3month", limit=50),
    )
    raw_albums = fetch_or_update(
        f"{username}_top_albums_3month",
        lambda: lastfm.get_top_albums(username, period="3month", limit=50),
    )
    raw_all = fetch_or_update(
        f"{username}_all_scrobbles",
        lambda: lastfm.get_recent_tracks(username),
        max_age_hours=24,
    )

    df_artists = parse_top_artists(raw_artists)
    df_top_tracks = parse_top_tracks(raw_tracks_top)
    df_albums = parse_top_albums(raw_albums)
    df_all = parse_scrobbles(raw_all)
    sessions = detect_sessions(df_all)

    if verbose:
        print(f"User: {info['name']} ({info.get('country') or '—'})")
        print(f"Lifetime scrobbles: {int(info['playcount']):,}")
        print(f"Registered: {registered.strftime('%Y-%m-%d')}")
        if not df_all.empty:
            print(f"History range: {df_all['timestamp'].min().date()} "
                  f"→ {df_all['timestamp'].max().date()} "
                  f"({len(df_all)} scrobbles)")
        print(f"Sessions: {len(sessions)}")

    return {
        "info": info,
        "registered": registered,
        "df_top_artists": df_artists,
        "df_top_tracks": df_top_tracks,
        "df_top_albums": df_albums,
        "df_all": df_all,
        "sessions": sessions,
    }


def run_metadata(
    lastfm: LastFMClient,
    mb: MusicBrainzClient,
    ab: AcousticBrainzClient,
    df_top_tracks,
    genius_search_fn,
    *,
    verbose: bool,
) -> list:
    """Enrich top tracks with MB + AB + LFM fallback. Cached by (artist, track)."""
    if verbose:
        _header("METADATA ENRICHMENT")

    metas = []
    for _, row in df_top_tracks.iterrows():
        meta = resolve_track_metadata_cached(
            artist=row["artist"],
            track=row["track"],
            mb=mb,
            ab=ab,
            lastfm_tags_fn=lastfm.get_track_tags,
            known_mbid=row["mbid"] or None,
            genius_search_fn=genius_search_fn,
        )
        metas.append(meta)

    if verbose:
        with_mbid = sum(1 for m in metas if m.mbid)
        with_mood = sum(1 for m in metas if m.mood)
        with_bpm = sum(1 for m in metas if m.bpm)
        with_year = sum(1 for m in metas if m.year)
        n = len(metas)
        print(f"Tracks:      {n}")
        print(f"MBID:        {with_mbid}/{n}")
        print(f"Release year:{with_year}/{n}")
        print(f"AB mood:     {with_mood}/{n}")
        print(f"AB BPM:      {with_bpm}/{n}")

    return metas


def run_features(
    df_all, sessions, track_metas, df_top_artists,
    lastfm: LastFMClient, *, verbose: bool,
) -> dict:
    """Compute the full narrative feature set."""
    if verbose:
        _header("FEATURES")

    meta_index = {(m.artist, m.track): m for m in track_metas}
    meta_lookup = lambda a, t: meta_index.get((a, t))

    top_artists_names = df_top_artists["artist"].tolist()
    all_artists = set(df_all["artist"].unique().tolist()) if not df_all.empty else set()

    features = {
        "decade_fingerprint": decade_fingerprint(track_metas),
        "binge_weeks":        binge_weeks(df_all),
        "time_signature":     time_signature(df_all),
        "artist_loyalty":     artist_loyalty(df_all),
        "discovery_rate":     discovery_rate(df_all),
        "mood_trajectory":    mood_trajectory(df_all, track_metas),
        "context_switches":   context_switches(sessions, meta_lookup),
        "listening_style":    listening_style(df_all),
        "guilty_pleasures":   guilty_pleasures(df_all),
        "artifacts":          year_artifacts(df_all, sessions),
        "musical_roommates":  musical_roommates(
            top_artists_names, all_artists, lastfm.get_similar_artists,
        ),
    }

    if verbose:
        for name, result in features.items():
            print(f"\n--- {name} ---")
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    return features


# --- main -------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stages", default="all",
        help="comma-separated: all | profile | metadata | features (default: all)",
    )
    parser.add_argument(
        "--period", default=None,
        help="YYYY | YYYY-MM-DD:YYYY-MM-DD | last:N (days). Default: full history.",
    )
    parser.add_argument(
        "--top-n", type=int, default=None,
        help="override ENRICH_TOP_N for metadata enrichment",
    )
    parser.add_argument(
        "--json", default=None,
        help="write LLM-ready feature JSON to this path",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="suppress per-stage stdout (still writes --json)",
    )
    args = parser.parse_args(argv)

    stages = _parse_stages(args.stages)
    verbose = not args.quiet

    load_dotenv()
    api_key = os.getenv("LASTFM_API_KEY")
    username = os.getenv("LASTFM_USERNAME")
    mb_contact = os.getenv("MUSICBRAINZ_CONTACT")
    genius_token = os.getenv("GENIUS_ACCESS_TOKEN")
    top_n = args.top_n or int(os.getenv("ENRICH_TOP_N", "50"))

    if not all([api_key, username, mb_contact]):
        print("Missing env vars — set LASTFM_API_KEY, LASTFM_USERNAME, "
              "MUSICBRAINZ_CONTACT in .env", file=sys.stderr)
        return 2

    lastfm = LastFMClient(api_key)

    # --- profile (always needed if downstream stages are requested) ---
    ctx = run_profile(lastfm, username, verbose=verbose)
    df_all_full = ctx["df_all"]

    # Scope to period. `df_top_tracks` comes from LFM's own "3month" window
    # and is not user-filterable, so period only scopes the full history.
    period = _parse_period(args.period, df_all_full)
    df_all = filter_df(df_all_full, period)
    sessions = detect_sessions(df_all) if period else ctx["sessions"]

    if verbose and period:
        print(f"\n[period] {period.name}: "
              f"{period.start.date()} → {period.end.date()} "
              f"({len(df_all)} scrobbles)")

    # --- metadata ---
    track_metas: list = []
    if "metadata" in stages or "features" in stages:
        mb = MusicBrainzClient(contact=mb_contact)
        ab = AcousticBrainzClient()
        genius_search_fn = None
        if genius_token:
            from src.genius.client import GeniusClient
            genius_search_fn = GeniusClient(genius_token).search_song

        df_top_for_meta = ctx["df_top_tracks"].head(top_n)
        track_metas = run_metadata(
            lastfm, mb, ab, df_top_for_meta, genius_search_fn, verbose=verbose,
        )

    # --- features ---
    features: dict = {}
    if "features" in stages:
        features = run_features(
            df_all, sessions, track_metas, ctx["df_top_artists"], lastfm,
            verbose=verbose,
        )

    # --- JSON dump ---
    if args.json and features:
        payload = {
            "user": username,
            "period": period.name if period else "lifetime",
            "generated_at": datetime.now().isoformat(),
            "features": features,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        if verbose:
            size = os.path.getsize(args.json)
            print(f"\n[json] wrote {args.json} ({size} bytes, "
                  f"{size // 1024} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
