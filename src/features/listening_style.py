import pandas as pd


def listening_style(df: pd.DataFrame) -> dict:
    """Split the coarse explorer_score into breadth and repeat-intensity.

    `explorer_score` (unique/total) conflates two distinct personas:
    the collector who samples 1000 tracks once, and the obsessive who
    plays 20 tracks 50 times each. Both can land at the same ratio.

    Metrics returned:
      - catalog_breadth:   unique tracks (absolute count)
      - unique_ratio:      unique / total (the legacy explorer_score)
      - repeat_intensity:  max plays of any single track / median plays
      - obsession_track:   the single most-repeated track, for narrative hooks
      - top_repeat_ratio:  top-track plays / total, a concentration proxy

    The label synthesises all three into one of: collector, obsessive,
    balanced. Thresholds are coarse — the feature exists to give the
    LLM a frame, not to bin users precisely.
    """
    if df.empty:
        return {}

    df = df.copy()
    df["key"] = df["artist"] + "|||" + df["track"]

    total = len(df)
    counts = df["key"].value_counts()
    unique = len(counts)
    median_plays = float(counts.median())
    top_plays = int(counts.iloc[0])
    top_key = counts.index[0]
    top_artist, top_track = top_key.split("|||", 1)

    unique_ratio = round(unique / total, 3)
    repeat_intensity = round(top_plays / max(median_plays, 1.0), 2)
    top_repeat_ratio = round(top_plays / total, 3)

    if unique_ratio >= 0.6 and repeat_intensity < 15:
        label = "collector"
    elif repeat_intensity >= 25 and unique_ratio < 0.4:
        label = "obsessive"
    else:
        label = "balanced"

    return {
        "catalog_breadth": unique,
        "unique_ratio": unique_ratio,
        "repeat_intensity": repeat_intensity,
        "top_repeat_ratio": top_repeat_ratio,
        "obsession_track": {
            "artist": top_artist,
            "track": top_track,
            "plays": top_plays,
        },
        "label": label,
    }
