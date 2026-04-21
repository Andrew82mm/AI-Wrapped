"""
Synthetic data test for session detector.
Tracks are named to make it obvious which pattern they belong to.
"""
from datetime import datetime, timedelta
import random
import pandas as pd

from src.lastfm.sessions import detect_sessions, sessions_to_df, find_patterns

random.seed(42)

# Each pattern has its own distinct artists and tracks
PATTERN_TRACKS = {
    "morning": [
        ("Morning_Artist_1", "Morning_Track_1"),
        ("Morning_Artist_1", "Morning_Track_2"),
        ("Morning_Artist_2", "Morning_Track_1"),
        ("Morning_Artist_2", "Morning_Track_2"),
        ("Morning_Artist_3", "Morning_Track_1"),
    ],
    "work": [
        ("Work_Artist_1", "Work_Track_1"),
        ("Work_Artist_1", "Work_Track_2"),
        ("Work_Artist_1", "Work_Track_3"),
        ("Work_Artist_2", "Work_Track_1"),
        ("Work_Artist_2", "Work_Track_2"),
        ("Work_Artist_3", "Work_Track_1"),
    ],
    "night": [
        ("Night_Artist_1", "Night_Track_1"),
        ("Night_Artist_1", "Night_Track_2"),
        ("Night_Artist_2", "Night_Track_1"),
        ("Night_Artist_2", "Night_Track_2"),
        ("Night_Artist_3", "Night_Track_1"),
    ],
}


def make_session(start: datetime, duration_min: int, pattern: str) -> list[dict]:
    tracks = PATTERN_TRACKS[pattern]
    n_tracks = max(1, duration_min // 4)
    interval = (duration_min * 60) / n_tracks
    rows = []
    for i in range(n_tracks):
        artist, track = random.choice(tracks)
        rows.append({
            "timestamp": start + timedelta(seconds=i * interval),
            "track": track,
            "artist": artist,
            "album": f"{pattern.capitalize()} Album",
            "mbid": "",
        })
    return rows


# ---------------------------------------------------------------------------
# Build synthetic scrobbles with 3 planted patterns over 12 weeks
#
# Pattern A — weekday morning   07:30 ±5 min  ~30 min    Mon–Fri
# Pattern B — weekday afternoon 14:00 ±10 min ~120 min   Mon–Fri
# Pattern C — weekend late night 23:00 ±15 min ~90 min   Fri + Sat
# ---------------------------------------------------------------------------

rows = []
base = datetime(2026, 1, 5)  # Monday

for week in range(12):
    monday = base + timedelta(weeks=week)

    for day_offset in range(5):  # Mon–Fri
        day = monday + timedelta(days=day_offset)

        # Pattern A: morning commute
        start_a = day.replace(hour=7, minute=30) + timedelta(minutes=random.randint(-5, 5))
        rows.extend(make_session(start_a, duration_min=random.randint(25, 35), pattern="morning"))

        # Pattern B: afternoon work session
        start_b = day.replace(hour=14, minute=0) + timedelta(minutes=random.randint(-10, 10))
        rows.extend(make_session(start_b, duration_min=random.randint(100, 140), pattern="work"))

    for day_offset in [4, 5]:  # Fri + Sat night
        day = monday + timedelta(days=day_offset)
        start_c = day.replace(hour=23, minute=0) + timedelta(minutes=random.randint(-15, 15))
        rows.extend(make_session(start_c, duration_min=random.randint(75, 105), pattern="night"))


df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
print(f"Synthetic scrobbles: {len(df)}")
print(f"Date range: {df['timestamp'].min().date()} → {df['timestamp'].max().date()}\n")

# ---------------------------------------------------------------------------
# Run detector
# ---------------------------------------------------------------------------

sessions = detect_sessions(df)
df_sessions = sessions_to_df(sessions)

print(f"Sessions detected: {len(sessions)}")
print(f"Avg duration: {df_sessions['duration_min'].mean():.0f} min\n")

patterns = find_patterns(sessions, min_occurrences=3)

print("=" * 65)
print(f"{'PATTERN':<30} {'TIME':>6}  {'AVG DUR':>8}  {'TIMES':>6}  TOP ARTISTS")
print("=" * 65)
for p in patterns:
    artists = ", ".join(p["top_artists"])
    print(
        f"  {p['day_type']} {p['time_slot']:<20}"
        f"  ~{p['avg_hour']:04.1f}"
        f"  {p['avg_duration_min']:>5} min"
        f"  x{p['occurrences']:>3}"
        f"  | {artists}"
    )

# ---------------------------------------------------------------------------
# Assertions — check planted patterns were found and mapped to correct artists
# ---------------------------------------------------------------------------

print("\n" + "=" * 65)
print("ASSERTIONS")
print("=" * 65)

keys = {p["key"]: p for p in patterns}

def assert_pattern(key: str, expected_artist_prefix: str):
    assert key in keys, f"FAIL: '{key}' not found in patterns"
    artists = keys[key]["top_artists"]
    match = any(a.startswith(expected_artist_prefix) for a in artists)
    assert match, f"FAIL: '{key}' found but top artists are {artists}, expected {expected_artist_prefix}*"
    print(f"  OK  {key} → {artists}")

assert_pattern("weekday_morning",   "Morning_Artist")
assert_pattern("weekday_afternoon", "Work_Artist")
assert any(
    k in keys for k in ("weekend_late_night", "weekend_evening")
), f"FAIL: no weekend night pattern found. Keys: {list(keys)}"
night_key = "weekend_late_night" if "weekend_late_night" in keys else "weekend_evening"
night_artists = keys[night_key]["top_artists"]
assert any(a.startswith("Night_Artist") for a in night_artists), \
    f"FAIL: weekend night artists are {night_artists}"
print(f"  OK  {night_key} → {night_artists}")

print("\nAll assertions passed.")
