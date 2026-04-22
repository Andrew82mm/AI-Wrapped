"""Shape feature dict into LLM-ready context + whitelist of allowed names.

The feature JSON from `wrapped.py` is already small (<10KB) and well-structured,
so we pass it through almost verbatim. The one thing we do extract is the set
of artist/track names the model is allowed to mention — downstream verification
rejects any name outside this whitelist.
"""
from __future__ import annotations

from typing import Any


def build_allowed_names(features: dict[str, Any]) -> dict[str, set[str]]:
    """Collect every artist/track name that appears in the feature dict.

    Returns {"artists": {...}, "tracks": {...}}. Anything the model writes
    outside these sets is treated as a hallucination.
    """
    artists: set[str] = set()
    tracks: set[str] = set()

    def add_artist(name: str | None) -> None:
        if name:
            artists.add(name.strip())

    def add_track(artist: str | None, track: str | None) -> None:
        if track:
            tracks.add(track.strip())
            add_artist(artist)

    for binge in features.get("binge_weeks", {}).get("binges", []) or []:
        add_artist(binge.get("top_artist"))

    loyalty = features.get("artist_loyalty", {}) or {}
    for section in ("veterans", "newcomers"):
        for item in loyalty.get(section, []) or []:
            add_artist(item.get("artist"))

    style = features.get("listening_style", {}) or {}
    obsession = style.get("obsession_track") or {}
    add_track(obsession.get("artist"), obsession.get("track"))

    for gp in features.get("guilty_pleasures", {}).get("guilty_pleasures", []) or []:
        add_artist(gp.get("artist"))

    arti = features.get("artifacts", {}) or {}
    longest = arti.get("longest_session") or {}
    for a in longest.get("top_artists", []) or []:
        add_artist(a)

    roommates = features.get("musical_roommates", {}) or {}
    for a in roommates.get("seeds", []) or []:
        add_artist(a)
    for rec in roommates.get("recommendations", []) or []:
        add_artist(rec.get("artist"))
        for s in rec.get("suggested_by", []) or []:
            add_artist(s)

    return {"artists": artists, "tracks": tracks}


def build_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the payload subset the LLM actually needs.

    We keep the feature block unchanged and strip only meta fields that would
    distract the model (exact timestamps, internal counters).
    """
    return {
        "user": payload.get("user"),
        "period": payload.get("period", "lifetime"),
        "features": payload.get("features", {}),
    }
