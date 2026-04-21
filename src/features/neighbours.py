from collections import defaultdict


def musical_roommates(
    user_top_artists: list[str],
    user_all_artists: set[str],
    similar_fn,
    top_n: int = 5,
    seed_limit: int = 5,
    per_seed_limit: int = 20,
) -> dict:
    """Aggregate recommended artists from similar-artist neighbourhoods.

    similar_fn: callable (artist) -> list[{"name", "match"}]. Passed in
    rather than hardcoded to keep this module free of Last.fm coupling
    and trivially testable.

    Scoring is sum-of-match across seeds — an artist suggested by three
    of your favourites outranks one with a single high-match edge.
    Artists already in `user_all_artists` are filtered out (case-insensitive).

    Returns seeds used, raw candidate count, and the ranked top-N.
    """
    if not user_top_artists:
        return {}

    known = {a.lower() for a in user_all_artists}
    scores: dict[str, float] = defaultdict(float)
    supporters: dict[str, list[str]] = defaultdict(list)

    seeds = user_top_artists[:seed_limit]
    for seed in seeds:
        similar = similar_fn(seed) or []
        for item in similar[:per_seed_limit]:
            name = item.get("name")
            match = float(item.get("match", 0.0))
            if not name or name.lower() in known:
                continue
            scores[name] += match
            supporters[name].append(seed)

    if not scores:
        return {"seeds": seeds, "candidates": 0, "recommendations": []}

    ranked = sorted(scores.items(), key=lambda p: p[1], reverse=True)[:top_n]

    return {
        "seeds": seeds,
        "candidates": len(scores),
        "recommendations": [
            {
                "artist": name,
                "score": round(score, 3),
                "suggested_by": supporters[name],
            }
            for name, score in ranked
        ],
    }
