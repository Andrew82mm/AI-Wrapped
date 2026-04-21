from statistics import mean


def _session_fingerprint(session, meta_lookup) -> dict:
    """Aggregate a session's tracks into mood/bpm/genre vectors.

    meta_lookup: callable (artist, track) -> TrackMetadata | None.
    Missing metadata degrades gracefully — the fields just stay None.
    """
    moods: dict[str, list[float]] = {}
    bpms: list[float] = []
    genres: set[str] = set()
    artists = [t["artist"] for t in session.tracks]

    for t in session.tracks:
        meta = meta_lookup(t["artist"], t["track"])
        if not meta:
            continue
        if meta.mood:
            for dim, val in meta.mood.items():
                if val is not None:
                    moods.setdefault(dim, []).append(float(val))
        if meta.bpm:
            bpms.append(float(meta.bpm))
        if meta.genres:
            genres.update(meta.genres[:3])

    return {
        "mood": {dim: round(mean(v), 3) for dim, v in moods.items()},
        "bpm": round(mean(bpms), 1) if bpms else None,
        "genres": genres,
        "top_artist": max(set(artists), key=artists.count) if artists else None,
    }


def _sharpness(a: dict, b: dict) -> float:
    """Composite distance between two session fingerprints in [0, 1].

    Combines mood L1 distance, BPM delta (normalised by 60), and genre
    Jaccard distance. Missing sub-signals are dropped, not imputed — a
    session with only BPM will still score, just on fewer axes.
    """
    signals: list[float] = []

    shared = set(a["mood"]) & set(b["mood"])
    if shared:
        dist = sum(abs(a["mood"][d] - b["mood"][d]) for d in shared) / len(shared)
        signals.append(min(dist, 1.0))

    if a["bpm"] and b["bpm"]:
        signals.append(min(abs(a["bpm"] - b["bpm"]) / 60.0, 1.0))

    if a["genres"] or b["genres"]:
        union = a["genres"] | b["genres"]
        intersect = a["genres"] & b["genres"]
        if union:
            signals.append(1.0 - len(intersect) / len(union))

    return round(mean(signals), 3) if signals else 0.0


def context_switches(
    sessions,
    meta_lookup,
    top_n: int = 5,
    min_signals: int = 2,
) -> dict:
    """Find session-to-session transitions with the sharpest change.

    A transition is scored only when at least `min_signals` of the three
    axes (mood, bpm, genre) are defined for both sides — otherwise we'd
    rank sessions by missing-metadata luck.

    Returns median sharpness + top-N sharpest transitions with context.
    """
    if len(sessions) < 2:
        return {}

    fingerprints = [_session_fingerprint(s, meta_lookup) for s in sessions]

    transitions = []
    for i in range(1, len(sessions)):
        a, b = fingerprints[i - 1], fingerprints[i]
        defined = sum([
            bool(set(a["mood"]) & set(b["mood"])),
            bool(a["bpm"] and b["bpm"]),
            bool(a["genres"] or b["genres"]),
        ])
        if defined < min_signals:
            continue
        score = _sharpness(a, b)
        gap_hours = round(
            (sessions[i].start - sessions[i - 1].end).total_seconds() / 3600, 1
        )
        transitions.append({
            "from_session": sessions[i - 1].start.isoformat(),
            "to_session": sessions[i].start.isoformat(),
            "gap_hours": gap_hours,
            "sharpness": score,
            "from_artist": a["top_artist"],
            "to_artist": b["top_artist"],
            "from_genres": sorted(a["genres"])[:3],
            "to_genres": sorted(b["genres"])[:3],
        })

    if not transitions:
        return {}

    scores = [t["sharpness"] for t in transitions]
    median = sorted(scores)[len(scores) // 2]
    transitions.sort(key=lambda t: t["sharpness"], reverse=True)

    return {
        "median_sharpness": round(median, 3),
        "scored_transitions": len(transitions),
        "top_switches": transitions[:top_n],
    }
