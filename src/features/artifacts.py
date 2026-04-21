import pandas as pd


def year_artifacts(
    df: pd.DataFrame,
    sessions: list,
    dead_threshold_days: int = 7,
) -> dict:
    """Extract standout moments: longest session, longest daily streak,
    and notable listening gaps.

    The session path takes the full session list (not a resampled summary)
    because we need its raw tracks for the "longest session" hook. Streaks
    are computed on distinct-calendar-days, not on sessions — a streak
    should survive someone skipping an evening.

    Dead periods (gaps >= `dead_threshold_days`) are surfaced as narrative
    material — they're often where the interesting story is, even if we
    don't know why the user stopped listening.
    """
    if df.empty:
        return {}

    result: dict = {}

    # --- longest session ---
    if sessions:
        longest = max(sessions, key=lambda s: s.duration_minutes)
        result["longest_session"] = {
            "start": longest.start.isoformat(),
            "duration_min": longest.duration_minutes,
            "track_count": longest.track_count,
            "top_artists": longest.top_artists,
        }

    # --- longest daily-listening streak ---
    days = sorted(df["timestamp"].dt.date.unique())
    best_len = cur_len = 1
    best_end = cur_start = cur_end = days[0]
    best_start = days[0]
    for prev, today in zip(days, days[1:]):
        if (today - prev).days == 1:
            cur_len += 1
            cur_end = today
        else:
            if cur_len > best_len:
                best_len, best_start, best_end = cur_len, cur_start, cur_end
            cur_len, cur_start, cur_end = 1, today, today
    if cur_len > best_len:
        best_len, best_start, best_end = cur_len, cur_start, cur_end
    result["longest_streak"] = {
        "days": best_len,
        "start": best_start.isoformat(),
        "end": best_end.isoformat(),
    }

    # --- dead periods ---
    dead = []
    for prev, today in zip(days, days[1:]):
        gap = (today - prev).days
        if gap >= dead_threshold_days:
            dead.append({
                "after": prev.isoformat(),
                "before": today.isoformat(),
                "gap_days": gap,
            })
    dead.sort(key=lambda d: d["gap_days"], reverse=True)
    result["dead_periods"] = dead[:5]

    # --- peak day ---
    by_day = df.groupby(df["timestamp"].dt.date).size()
    peak_day = by_day.idxmax()
    result["peak_day"] = {
        "date": peak_day.isoformat(),
        "tracks": int(by_day.max()),
    }

    return result
