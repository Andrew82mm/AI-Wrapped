import pandas as pd


def artist_loyalty(df: pd.DataFrame, top_n: int = 10) -> dict:
    """Compute how long the user has been listening to each artist.

    'Weeks with artist' = number of distinct ISO weeks where the artist
    appeared at least once. This is more meaningful than total span
    (which inflates for artists heard once a year ago).

    Returns veterans (longest-running) and newcomers (heard only recently),
    plus the median weeks across all artists with 2+ active weeks.
    """
    if df.empty:
        return {}

    df = df.copy()
    df["week"] = df["timestamp"].dt.strftime("%G-W%V")

    artist_weeks = (
        df.groupby("artist")["week"]
        .nunique()
        .rename("active_weeks")
        .sort_values(ascending=False)
    )

    first_seen = df.groupby("artist")["week"].min().rename("first_week")
    stats = pd.concat([artist_weeks, first_seen], axis=1)

    all_weeks_sorted = sorted(df["week"].unique())
    recent_cutoff = all_weeks_sorted[-4] if len(all_weeks_sorted) >= 4 else all_weeks_sorted[0]

    veterans = (
        stats[stats["active_weeks"] >= 4]
        .sort_values("active_weeks", ascending=False)
        .head(top_n)
    )
    newcomers = (
        stats[
            (stats["first_week"] >= recent_cutoff) &
            (stats["active_weeks"] <= 3)
        ]
        .sort_values("active_weeks", ascending=False)
        .head(5)
    )

    recurring = stats[stats["active_weeks"] >= 2]
    median_weeks = int(recurring["active_weeks"].median()) if not recurring.empty else 0

    return {
        "median_active_weeks": median_weeks,
        "veterans": [
            {"artist": a, "active_weeks": int(r["active_weeks"]), "first_week": r["first_week"]}
            for a, r in veterans.iterrows()
        ],
        "newcomers": [
            {"artist": a, "active_weeks": int(r["active_weeks"]), "first_week": r["first_week"]}
            for a, r in newcomers.iterrows()
        ],
    }
