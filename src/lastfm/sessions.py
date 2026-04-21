from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd


GAP_MINUTES = 30  # пауза больше этого = новая сессия


@dataclass
class Session:
    start: datetime
    end: datetime
    tracks: list[dict] = field(default_factory=list)

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def top_artists(self) -> list[str]:
        counts = {}
        for t in self.tracks:
            counts[t["artist"]] = counts.get(t["artist"], 0) + 1
        return sorted(counts, key=counts.get, reverse=True)[:3]

    @property
    def hour(self) -> int:
        return self.start.hour

    @property
    def weekday(self) -> str:
        return self.start.strftime("%A")

    @property
    def is_weekday(self) -> bool:
        return self.start.weekday() < 5


def detect_sessions(df: pd.DataFrame, gap_minutes: int = GAP_MINUTES) -> list[Session]:
    """Split scrobbles into sessions by time gap."""
    if df.empty:
        return []

    df = df.sort_values("timestamp").reset_index(drop=True)
    sessions = []
    current = None

    for _, row in df.iterrows():
        track = row.to_dict()

        if current is None:
            current = Session(start=row["timestamp"], end=row["timestamp"])
        else:
            gap = (row["timestamp"] - current.end).total_seconds() / 60
            if gap > gap_minutes:
                sessions.append(current)
                current = Session(start=row["timestamp"], end=row["timestamp"])
            else:
                current.end = row["timestamp"]

        current.tracks.append(track)

    if current:
        sessions.append(current)

    return sessions


def sessions_to_df(sessions: list[Session]) -> pd.DataFrame:
    rows = []
    for s in sessions:
        rows.append({
            "start": s.start,
            "end": s.end,
            "duration_min": s.duration_minutes,
            "track_count": s.track_count,
            "top_artists": ", ".join(s.top_artists),
            "hour": s.hour,
            "weekday": s.weekday,
            "is_weekday": s.is_weekday,
            "date": s.start.date(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

TIME_SLOTS = {
    "night":    (0, 6),
    "morning":  (6, 11),
    "afternoon": (11, 17),
    "evening":  (17, 21),
    "late_night": (21, 24),
}


def _slot(hour: int) -> str:
    for name, (lo, hi) in TIME_SLOTS.items():
        if lo <= hour < hi:
            return name
    return "unknown"


def find_patterns(sessions: list[Session], min_occurrences: int = 3) -> list[dict]:
    """
    Find recurring session patterns.
    A pattern = same time slot + same weekday type (weekday/weekend),
    repeated at least min_occurrences times.
    """
    from collections import defaultdict

    buckets: dict[str, list[Session]] = defaultdict(list)

    for s in sessions:
        day_type = "weekday" if s.is_weekday else "weekend"
        key = f"{day_type}_{_slot(s.hour)}"
        buckets[key].append(s)

    patterns = []
    for key, group in buckets.items():
        if len(group) < min_occurrences:
            continue

        day_type, slot = key.split("_", 1)
        hours = [s.hour for s in group]
        durations = [s.duration_minutes for s in group]
        all_artists: dict[str, int] = {}
        for s in group:
            for a in s.top_artists:
                all_artists[a] = all_artists.get(a, 0) + 1

        patterns.append({
            "key": key,
            "day_type": day_type,
            "time_slot": slot,
            "occurrences": len(group),
            "avg_hour": round(sum(hours) / len(hours), 1),
            "avg_duration_min": round(sum(durations) / len(durations)),
            "top_artists": sorted(all_artists, key=all_artists.get, reverse=True)[:3],
        })

    return sorted(patterns, key=lambda p: p["occurrences"], reverse=True)
