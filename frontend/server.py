"""FastAPI server for AI-Wrapped.

Runs the full pipeline in a background thread per request and exposes
three endpoints the browser polls:

  POST /api/generate          { username, period }  → { job_id }
  GET  /api/status/{job_id}   → { status, step, step_label, total }
  GET  /api/result/{job_id}   → WRAPPED_DATA JSON (when status == "done")
  GET  /                      → serves frontend/index.html

Start with:
  python frontend/server.py
  # or
  uvicorn frontend.server:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from frontend.render import build_wrapped_data

app = FastAPI(title="AI-Wrapped")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── in-memory job store ──────────────────────────────────────────────────────
# job: { status: pending|running|done|error, step: int, step_label: str,
#        total: int, result: dict|None, error: str|None }
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _set(job_id: str, **kw):
    with _jobs_lock:
        _jobs[job_id].update(kw)


# ── pipeline runner ──────────────────────────────────────────────────────────

def _run_pipeline(job_id: str, username: str, period_str: str, backend: str):
    try:
        _pipeline(job_id, username, period_str, backend)
    except Exception as exc:
        _set(job_id, status="error", error=str(exc))


def _step(job_id, n, label):
    _set(job_id, step=n, step_label=label)


def _pipeline(job_id: str, username: str, period_str: str, backend: str):
    import re
    from datetime import datetime

    from src.lastfm.client import LastFMClient
    from src.lastfm.cache import fetch_or_update
    from src.lastfm.parser import (
        parse_scrobbles, parse_top_artists, parse_top_tracks, parse_top_albums,
    )
    from src.lastfm.sessions import detect_sessions
    from src.musicbrainz.client import MusicBrainzClient
    from src.acousticbrainz.client import AcousticBrainzClient
    from src.metadata.provider import resolve_track_metadata_cached
    from src.features.decade import decade_fingerprint
    from src.features.binge import binge_weeks
    from src.features.time_profile import time_signature
    from src.features.artist_loyalty import artist_loyalty
    from src.features.discovery import discovery_rate
    from src.features.neighbours import musical_roommates
    from src.features.guilty_pleasures import guilty_pleasures
    from src.features.listening_style import listening_style
    from src.features.artifacts import year_artifacts
    from src.features.period import filter_df, last_n_days, year_period, Period
    from src.narrative.generate import generate_narrative, NarrativeError

    api_key    = os.getenv("LASTFM_API_KEY")
    mb_contact = os.getenv("MUSICBRAINZ_CONTACT")
    genius_token = os.getenv("GENIUS_ACCESS_TOKEN")
    top_n = int(os.getenv("ENRICH_TOP_N", "50"))

    if not api_key or not mb_contact:
        raise RuntimeError("Missing LASTFM_API_KEY or MUSICBRAINZ_CONTACT in .env")

    user_cache = str(ROOT / "data" / username)
    os.makedirs(user_cache, exist_ok=True)

    lastfm = LastFMClient(api_key)

    # ── 1: profile ────────────────────────────────────────────────────────────
    _step(job_id, 1, "Fetching scrobble history…")

    info = fetch_or_update("info", lambda: lastfm.get_user_info(username),
                           max_age_hours=24, cache_dir=user_cache)
    fetch_or_update("top_artists_3month",
                    lambda: lastfm.get_top_artists(username, period="3month", limit=50),
                    cache_dir=user_cache)
    raw_tracks = fetch_or_update("top_tracks_3month",
                                 lambda: lastfm.get_top_tracks(username, period="3month", limit=50),
                                 cache_dir=user_cache)
    fetch_or_update("top_albums_3month",
                    lambda: lastfm.get_top_albums(username, period="3month", limit=50),
                    cache_dir=user_cache)
    raw_all = fetch_or_update("all_scrobbles",
                              lambda: lastfm.get_recent_tracks(username),
                              max_age_hours=24, cache_dir=user_cache)

    raw_artists = fetch_or_update("top_artists_3month",
                                  lambda: lastfm.get_top_artists(username, period="3month", limit=50),
                                  cache_dir=user_cache)

    df_all_full  = parse_scrobbles(raw_all)
    df_top_tracks = parse_top_tracks(raw_tracks)
    df_top_artists = parse_top_artists(raw_artists)

    # period filter
    period: Period | None = None
    if period_str and period_str != "lifetime":
        m = re.match(r"last:(\d+)", period_str)
        if m:
            period = last_n_days(df_all_full, int(m.group(1)))
        elif re.match(r"\d{4}$", period_str):
            period = year_period(int(period_str))

    df_all   = filter_df(df_all_full, period)
    sessions = detect_sessions(df_all)

    # ── 2: metadata ───────────────────────────────────────────────────────────
    _step(job_id, 2, "Enriching track metadata…")

    mb = MusicBrainzClient(contact=mb_contact)
    ab = AcousticBrainzClient()
    genius_fn = None
    if genius_token:
        from src.genius.client import GeniusClient
        genius_fn = GeniusClient(genius_token).search_song

    metas = []
    for _, row in df_top_tracks.head(top_n).iterrows():
        meta = resolve_track_metadata_cached(
            artist=row["artist"], track=row["track"],
            mb=mb, ab=ab, lastfm_tags_fn=lastfm.get_track_tags,
            known_mbid=row["mbid"] or None, genius_search_fn=genius_fn,
        )
        metas.append(meta)

    # ── 3: features ───────────────────────────────────────────────────────────
    _step(job_id, 3, "Analysing listening patterns…")

    top_artists_names = df_top_artists["artist"].tolist()
    all_artists = set(df_all["artist"].unique().tolist()) if not df_all.empty else set()

    features = {
        "decade_fingerprint": decade_fingerprint(metas),
        "binge_weeks":        binge_weeks(df_all),
        "time_signature":     time_signature(df_all),
        "artist_loyalty":     artist_loyalty(df_all),
        "discovery_rate":     discovery_rate(df_all),
        "listening_style":    listening_style(df_all),
        "guilty_pleasures":   guilty_pleasures(df_all),
        "artifacts":          year_artifacts(df_all, sessions),
        "musical_roommates":  musical_roommates(
            top_artists_names, all_artists, lastfm.get_similar_artists,
        ),
    }

    # ── 4: narrative ──────────────────────────────────────────────────────────
    _step(job_id, 4, "Writing your story… (up to 5 min)")

    payload = {
        "user":            username,
        "period":          period.name if period else "lifetime",
        "scrobbles_total": len(df_all),
        "features":        features,
    }

    narrative_sections = []
    try:
        narr = generate_narrative(payload, voice="a", lang="ru", backend=backend)
        narrative_sections = narr.sections
    except Exception as exc:
        # narrative failure is non-fatal — report without text
        print(f"[narrative] {exc}", file=sys.stderr)

    # ── 5: build result ───────────────────────────────────────────────────────
    _step(job_id, 5, "Building report…")

    result = build_wrapped_data(payload, narrative_sections)
    _set(job_id, status="done", result=result)


# ── endpoints ────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    username: str
    period: str = "last:90"
    backend: str = "cli"


@app.post("/api/generate")
def generate(req: GenerateRequest):
    if not req.username.strip():
        raise HTTPException(400, "username required")

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running", "step": 0, "step_label": "Starting…",
            "total": 5, "result": None, "error": None,
        }

    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id, req.username.strip(), req.period, req.backend),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return {
        "status":     job["status"],
        "step":       job["step"],
        "step_label": job["step_label"],
        "total":      job["total"],
        "error":      job["error"],
    }


@app.get("/api/result/{job_id}")
def result(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"job status is '{job['status']}'")
    return JSONResponse(job["result"])


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "index.html")


# ── dev entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("frontend.server:app", host="0.0.0.0", port=8000, reload=False)
