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
import re
import sys
import threading
import time
import uuid
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from frontend.render import build_wrapped_data

app = FastAPI(title="AI-Wrapped")

# ── configuration (env-driven, safe defaults) ────────────────────────────────
# CORS is opt-in: the app is served same-origin from GET /, so no cross-origin
# access is needed by default. Set ALLOWED_ORIGINS to a comma-separated list to
# enable it (e.g. when the frontend is hosted separately). Previously this was
# a wildcard "*", which let any site drive the pipeline on the server's keys.
_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware, allow_origins=_ALLOWED_ORIGINS,
        allow_methods=["*"], allow_headers=["*"],
    )

# Optional shared-secret auth. If API_TOKEN is set, every /api/* call must send
# a matching X-API-Token header. Unset (default) → no auth, for local use.
_API_TOKEN = os.getenv("API_TOKEN")
# Cap concurrent pipelines so a burst of requests can't spawn unbounded threads
# that each do heavy network + LLM work.
_MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_JOBS", "4"))
_pipeline_sem = threading.Semaphore(_MAX_CONCURRENT)
# Cap retained jobs so the in-memory store can't grow without bound.
_MAX_JOBS = int(os.getenv("MAX_JOBS", "200"))
# Last.fm usernames are alphanumeric plus _ and -; anything else is rejected so
# it can never be used as a path component to escape data/.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _require_auth(x_api_token: str | None = Header(default=None)) -> None:
    """Enforce the shared-secret token when API_TOKEN is configured."""
    if _API_TOKEN and x_api_token != _API_TOKEN:
        raise HTTPException(401, "invalid or missing API token")


# ── in-memory job store ──────────────────────────────────────────────────────
# job: { status: pending|running|done|error, step: int, step_label: str,
#        total: int, result: dict|None, error: str|None, created_at: float }
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _prune_jobs() -> None:
    """Evict oldest finished jobs when the store exceeds _MAX_JOBS."""
    with _jobs_lock:
        overflow = len(_jobs) - _MAX_JOBS
        if overflow <= 0:
            return
        finished = sorted(
            (jid for jid, j in _jobs.items() if j["status"] in ("done", "error")),
            key=lambda jid: _jobs[jid].get("created_at", 0.0),
        )
        for jid in finished[:overflow]:
            _jobs.pop(jid, None)


def _set(job_id: str, **kw):
    with _jobs_lock:
        _jobs[job_id].update(kw)


# ── pipeline runner ──────────────────────────────────────────────────────────

def _run_pipeline(job_id: str, username: str, period_str: str):
    with _pipeline_sem:
        try:
            _pipeline(job_id, username, period_str)
        except Exception as exc:
            _set(job_id, status="error", error=str(exc))


def _step(job_id, n, label):
    _set(job_id, step=n, step_label=label)


def _pipeline(job_id: str, username: str, period_str: str):
    import re
    from datetime import datetime

    from src.lastfm.client import LastFMClient
    from src.lastfm.cache import fetch_or_update, fetch_scrobbles_incremental
    from src.lastfm.parser import (
        parse_scrobbles, parse_top_artists, parse_top_tracks,
    )
    from src.lastfm.sessions import detect_sessions
    from src.musicbrainz.client import MusicBrainzClient
    from src.acousticbrainz.client import AcousticBrainzClient
    from src.metadata.provider import resolve_track_metadata_cached
    from src.features import compute_features
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
    _step(job_id, 1, "Fetching scrobble history… (first run may take a few minutes)")

    # Fetching user info also validates that the username exists (raises early
    # on an unknown user) before we do the expensive scrobble pull.
    fetch_or_update("info", lambda: lastfm.get_user_info(username),
                    max_age_hours=24, cache_dir=user_cache)
    raw_tracks = fetch_or_update("top_tracks_3month",
                                 lambda: lastfm.get_top_tracks(username, period="3month", limit=50),
                                 cache_dir=user_cache)
    raw_all = fetch_scrobbles_incremental(
        "all_scrobbles",
        lambda from_ts=None: lastfm.get_recent_tracks(username, from_ts=from_ts),
        cache_dir=user_cache,
    )

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

    features = compute_features(
        df_all, sessions, metas, top_artists_names, all_artists,
        lastfm.get_similar_artists,
    )

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
        narr = generate_narrative(payload, voice="a", lang="ru")
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


@app.post("/api/generate", dependencies=[Depends(_require_auth)])
def generate(req: GenerateRequest):
    username = req.username.strip()
    if not username:
        raise HTTPException(400, "username required")
    if not _USERNAME_RE.match(username):
        raise HTTPException(400, "invalid username")

    _prune_jobs()
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running", "step": 0, "step_label": "Starting…",
            "total": 5, "result": None, "error": None,
            "created_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id, username, req.period),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}", dependencies=[Depends(_require_auth)])
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


@app.get("/api/result/{job_id}", dependencies=[Depends(_require_auth)])
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
    # Bind loopback by default; override with HOST=0.0.0.0 only behind an
    # authenticated reverse proxy (set API_TOKEN too).
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("frontend.server:app", host=host, port=port, reload=False)
