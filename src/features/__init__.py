"""Feature computation registry.

`compute_features` is the single source of truth for the narrative feature set.
Both entry points — the CLI (`wrapped.py`) and the web backend
(`frontend/server.py`) — call it so the two cannot drift out of sync (previously
the same dict was hand-maintained in two places).
"""
from __future__ import annotations

from .artifacts import year_artifacts
from .artist_loyalty import artist_loyalty
from .binge import binge_weeks
from .decade import decade_fingerprint
from .discovery import discovery_rate
from .guilty_pleasures import guilty_pleasures
from .listening_style import listening_style
from .neighbours import musical_roommates
from .time_profile import time_signature


def compute_features(
    df_all,
    sessions,
    track_metas,
    top_artists_names,
    all_artists,
    similar_fn,
) -> dict:
    """Compute the full narrative feature set from prepared inputs.

    `similar_fn(artist) -> list[dict]` is injected (Last.fm's
    get_similar_artists) so this module stays free of client coupling.
    """
    return {
        "decade_fingerprint": decade_fingerprint(track_metas),
        "binge_weeks":        binge_weeks(df_all),
        "time_signature":     time_signature(df_all),
        "artist_loyalty":     artist_loyalty(df_all),
        "discovery_rate":     discovery_rate(df_all),
        "listening_style":    listening_style(df_all),
        "guilty_pleasures":   guilty_pleasures(df_all),
        "artifacts":          year_artifacts(df_all, sessions),
        "musical_roommates":  musical_roommates(top_artists_names, all_artists, similar_fn),
    }
