import pandas as pd


_LATE_HOURS = set(range(22, 24)) | set(range(0, 5))


def guilty_pleasures(
    df: pd.DataFrame,
    min_plays: int = 5,
    late_fraction_threshold: float = 0.5,
    top_n: int = 5,
) -> dict:
    """Surface artists listened to almost exclusively late at night.

    An artist qualifies when:
      - they have at least `min_plays` scrobbles (noise floor), and
      - at least `late_fraction_threshold` of those fall in 22:00-05:00.

    The phrase "guilty pleasure" is a narrative framing, not a moral
    judgement — the signal is "listened to alone, off-hours".

    Returns per-artist late_fraction + total plays, ranked by late_fraction
    then by play count.
    """
    if df.empty:
        return {}

    df = df.copy()
    df["hour"] = df["timestamp"].dt.hour
    df["is_late"] = df["hour"].isin(_LATE_HOURS)

    by_artist = df.groupby("artist").agg(
        plays=("track", "size"),
        late_plays=("is_late", "sum"),
    )
    by_artist = by_artist[by_artist["plays"] >= min_plays]
    if by_artist.empty:
        return {}

    by_artist["late_fraction"] = by_artist["late_plays"] / by_artist["plays"]
    qualifying = by_artist[by_artist["late_fraction"] >= late_fraction_threshold]
    if qualifying.empty:
        return {"candidates": 0, "guilty_pleasures": []}

    ranked = qualifying.sort_values(
        ["late_fraction", "plays"], ascending=[False, False]
    ).head(top_n)

    return {
        "candidates": int(len(qualifying)),
        "threshold": late_fraction_threshold,
        "guilty_pleasures": [
            {
                "artist": artist,
                "plays": int(row["plays"]),
                "late_fraction": round(float(row["late_fraction"]), 2),
            }
            for artist, row in ranked.iterrows()
        ],
    }
