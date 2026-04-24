import datetime

import pandas as pd


def _week_label(iso_week: str) -> str:
    """Convert '2026-W05' to 'Feb 2' (Monday of that week)."""
    year, w = iso_week.split("-W")
    monday = datetime.datetime.strptime(f"{year}-W{w}-1", "%G-W%V-%u")
    return monday.strftime("%b %-d")


def binge_weeks(df: pd.DataFrame, threshold_multiplier: float = 2.0) -> dict:
    """Detect weeks where listening spiked above normal.

    A week is a binge if its track count exceeds threshold_multiplier × median.
    Requires a DataFrame with at least 8 weeks of history for a meaningful
    baseline — returns an empty dict otherwise.

    Returns a compact dict for LLM prompt context.
    """
    if df.empty:
        return {}

    df = df.copy()
    df["week"] = df["timestamp"].dt.strftime("%G-W%V")

    weekly = df.groupby("week").size().rename("tracks")
    if len(weekly) < 8:
        return {}

    median = weekly.median()
    threshold = median * threshold_multiplier

    binge_mask = weekly > threshold
    binge_data = []
    for week, count in weekly[binge_mask].items():
        top_artist = (
            df[df["week"] == week]["artist"]
            .value_counts()
            .idxmax()
        )
        binge_data.append({
            "week": week,
            "tracks": int(count),
            "vs_median": round(count / median, 1),
            "top_artist": top_artist,
        })

    binge_data.sort(key=lambda x: x["tracks"], reverse=True)
    binge_weeks_set = {b["week"] for b in binge_data}

    top_by_week = {
        week: df[df["week"] == week]["artist"].value_counts().idxmax()
        for week in weekly.index
    }
    weekly_data = [
        {
            "week": week,
            "label": _week_label(week),
            "tracks": int(count),
            "is_binge": week in binge_weeks_set,
            "top_artist": top_by_week.get(week) if week in binge_weeks_set else None,
        }
        for week, count in weekly.items()
    ]

    return {
        "median_weekly_tracks": int(median),
        "binge_count": len(binge_data),
        "binges": binge_data[:5],
        "weekly_data": weekly_data,
    }
