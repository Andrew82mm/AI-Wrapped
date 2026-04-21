import pandas as pd
from collections import Counter


_SLOTS = {
    "night": range(0, 5),
    "morning": range(5, 12),
    "afternoon": range(12, 17),
    "evening": range(17, 21),
    "late_night": range(21, 24),
}


def _slot(hour: int) -> str:
    for name, hours in _SLOTS.items():
        if hour in hours:
            return name
    return "unknown"


def time_signature(df: pd.DataFrame) -> dict:
    """Compute a listening time-of-day profile.

    Returns peak hour, dominant slot, slot distribution (fractions),
    and a human-readable label for LLM context.
    """
    if df.empty:
        return {}

    hours = df["timestamp"].dt.hour
    hour_counts = Counter(hours.tolist())
    peak_hour = max(hour_counts, key=hour_counts.get)

    slot_counts: Counter = Counter(_slot(h) for h in hours)
    total = sum(slot_counts.values())
    slot_dist = {s: round(slot_counts.get(s, 0) / total, 2) for s in _SLOTS}

    dominant_slot = max(slot_counts, key=slot_counts.get)

    label_map = {
        "night": "insomniac",
        "morning": "early bird",
        "afternoon": "daytime listener",
        "evening": "evening listener",
        "late_night": "night owl",
    }

    return {
        "peak_hour": peak_hour,
        "dominant_slot": dominant_slot,
        "label": label_map.get(dominant_slot, dominant_slot),
        "slot_distribution": slot_dist,
    }
