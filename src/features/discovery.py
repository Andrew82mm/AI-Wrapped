import pandas as pd


def discovery_rate(df: pd.DataFrame) -> dict:
    """Compute how many new tracks the user discovers each month.

    A track is 'new' in the month it first appears in the scrobble history.
    Requires at least 3 months of data for a meaningful trend.

    Returns monthly new track counts, average, trend direction, and an
    explorer score (ratio of unique tracks to total scrobbles).
    """
    if df.empty:
        return {}

    df = df.copy()
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    df["track_key"] = df["artist"] + "|||" + df["track"]

    first_seen = df.groupby("track_key")["month"].min().rename("first_month")
    new_counts = first_seen.value_counts()

    all_months = df["month"].sort_values().unique()
    if len(all_months) < 3:
        return {}

    # Reindex to all calendar months so zeros are explicit, not missing
    monthly_new = new_counts.reindex(all_months, fill_value=0).sort_index()

    monthly_dict = {str(m): int(c) for m, c in monthly_new.items()}
    avg = round(monthly_new.mean(), 1)

    # Trend: compare last 3 months vs previous 3 months
    months = list(monthly_new.index)
    if len(months) >= 6:
        recent = monthly_new.iloc[-3:].mean()
        prior = monthly_new.iloc[-6:-3].mean()
        if recent > prior * 1.15:
            trend = "growing"
        elif recent < prior * 0.85:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    explorer_score = round(df["track_key"].nunique() / len(df), 3)

    return {
        "avg_new_tracks_per_month": avg,
        "trend": trend,
        "explorer_score": explorer_score,
        "monthly_new_tracks": monthly_dict,
    }
