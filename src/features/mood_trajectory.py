from collections import defaultdict
import pandas as pd


MOOD_DIMS = ("happy", "sad", "aggressive", "relaxed", "party")


def _artist_mood_table(track_metas: list) -> dict[str, dict[str, float]]:
    """Average each artist's per-track moods from available metadata.

    AB covers ~60% of tracks, so we fall back to artist-level averages
    when a scrobbled track has no direct mood. Artists with zero mood
    coverage are simply absent from the returned dict.
    """
    buckets: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {dim: [] for dim in MOOD_DIMS}
    )
    for m in track_metas:
        if not m.mood:
            continue
        for dim in MOOD_DIMS:
            val = m.mood.get(dim)
            if val is not None:
                buckets[m.artist][dim].append(float(val))

    result: dict[str, dict[str, float]] = {}
    for artist, dims in buckets.items():
        avg = {d: (sum(v) / len(v)) for d, v in dims.items() if v}
        if avg:
            result[artist] = avg
    return result


def mood_trajectory(
    df: pd.DataFrame,
    track_metas: list,
    min_weeks: int = 8,
) -> dict:
    """Reconstruct week-by-week mood curve weighted by play counts.

    We project each scrobble onto the artist-level mood vector (averaged
    from the top-N enriched tracks) and aggregate by ISO week. This trades
    per-track precision for coverage — a worthwhile tradeoff given AB's
    2022 freeze.

    Returns weekly series plus baseline, deviations, and the single week
    with the largest |delta| on each mood dimension. Baselines are rounded
    to 3 decimals; keep raw precision internally if you build on this.
    """
    if df.empty or not track_metas:
        return {}

    artist_mood = _artist_mood_table(track_metas)
    if not artist_mood:
        return {}

    df = df.copy()
    df["week"] = df["timestamp"].dt.strftime("%G-W%V")
    total_scrobbles = len(df)
    df = df[df["artist"].isin(artist_mood)]
    if df.empty:
        return {}

    weekly: dict[str, dict[str, float]] = {}
    for week, group in df.groupby("week"):
        dim_totals = {d: 0.0 for d in MOOD_DIMS}
        weight_per_dim = {d: 0.0 for d in MOOD_DIMS}
        for artist, n in group["artist"].value_counts().items():
            mood = artist_mood.get(artist, {})
            for dim, val in mood.items():
                dim_totals[dim] += val * n
                weight_per_dim[dim] += n
        weekly[week] = {
            d: round(dim_totals[d] / weight_per_dim[d], 3)
            for d in MOOD_DIMS
            if weight_per_dim[d] > 0
        }

    if len(weekly) < min_weeks:
        return {}

    baseline: dict[str, float] = {}
    for dim in MOOD_DIMS:
        vals = [w[dim] for w in weekly.values() if dim in w]
        if vals:
            baseline[dim] = round(sum(vals) / len(vals), 3)

    extremes: dict[str, dict] = {}
    for dim in MOOD_DIMS:
        if dim not in baseline:
            continue
        best = max(
            ((wk, w[dim] - baseline[dim]) for wk, w in weekly.items() if dim in w),
            key=lambda p: abs(p[1]),
            default=None,
        )
        if best:
            extremes[dim] = {"week": best[0], "delta": round(best[1], 3)}

    return {
        "baseline": baseline,
        "weekly": dict(sorted(weekly.items())),
        "extremes": extremes,
        "artists_covered": df["artist"].nunique(),
        "weeks_covered": len(weekly),
        "scored_fraction": round(len(df) / max(1, total_scrobbles), 2),
    }
