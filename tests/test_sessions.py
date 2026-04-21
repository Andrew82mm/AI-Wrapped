import random
import pytest
import pandas as pd
from datetime import datetime, timedelta

from src.lastfm.sessions import (
    Session,
    detect_sessions,
    find_patterns,
    _slot,
    GAP_MINUTES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_df(timestamps: list[datetime], artist: str = "Artist") -> pd.DataFrame:
    return pd.DataFrame([
        {"timestamp": ts, "track": "Track", "artist": artist, "album": "Album", "mbid": ""}
        for ts in timestamps
    ])


def make_session_at(dt: datetime, duration_min: int = 30, artist: str = "Artist") -> Session:
    s = Session(start=dt, end=dt + timedelta(minutes=duration_min))
    s.tracks = [{"artist": artist}] * 5
    return s


def minutes(n: int) -> timedelta:
    return timedelta(minutes=n)


BASE = datetime(2026, 1, 5, 10, 0)  # Monday 10:00


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------

class TestSession:
    def test_duration_minutes(self):
        s = Session(start=BASE, end=BASE + minutes(45))
        assert s.duration_minutes == 45

    def test_track_count(self):
        s = Session(start=BASE, end=BASE + minutes(10))
        s.tracks = [{"artist": "A"}, {"artist": "B"}]
        assert s.track_count == 2

    def test_top_artists_order(self):
        s = Session(start=BASE, end=BASE + minutes(10))
        s.tracks = [
            {"artist": "A"}, {"artist": "A"}, {"artist": "A"},
            {"artist": "B"}, {"artist": "B"},
            {"artist": "C"},
        ]
        assert s.top_artists[0] == "A"
        assert s.top_artists[1] == "B"

    def test_top_artists_max_three(self):
        s = Session(start=BASE, end=BASE + minutes(10))
        s.tracks = [{"artist": str(i)} for i in range(10)]
        assert len(s.top_artists) <= 3

    def test_is_weekday_true(self):
        monday = datetime(2026, 1, 5)
        s = Session(start=monday, end=monday + minutes(10))
        assert s.is_weekday is True

    def test_is_weekday_false(self):
        saturday = datetime(2026, 1, 10)
        s = Session(start=saturday, end=saturday + minutes(10))
        assert s.is_weekday is False


# ---------------------------------------------------------------------------
# detect_sessions
# ---------------------------------------------------------------------------

class TestDetectSessions:
    def test_empty_df_returns_empty(self):
        assert detect_sessions(pd.DataFrame()) == []

    def test_single_track_is_one_session(self):
        sessions = detect_sessions(make_df([BASE]))
        assert len(sessions) == 1
        assert sessions[0].track_count == 1

    def test_consecutive_tracks_merge_into_one_session(self):
        timestamps = [BASE + minutes(i * 3) for i in range(5)]
        sessions = detect_sessions(make_df(timestamps))
        assert len(sessions) == 1
        assert sessions[0].track_count == 5

    def test_gap_splits_into_two_sessions(self):
        sessions = detect_sessions(make_df([BASE, BASE + minutes(GAP_MINUTES + 1)]))
        assert len(sessions) == 2

    def test_gap_exactly_at_boundary_does_not_split(self):
        sessions = detect_sessions(make_df([BASE, BASE + minutes(GAP_MINUTES)]))
        assert len(sessions) == 1

    def test_custom_gap(self):
        sessions = detect_sessions(make_df([BASE, BASE + minutes(10)]), gap_minutes=5)
        assert len(sessions) == 2

    def test_session_start_end_correct(self):
        timestamps = [BASE + minutes(i * 3) for i in range(4)]
        s = detect_sessions(make_df(timestamps))[0]
        assert s.start == timestamps[0]
        assert s.end == timestamps[-1]

    def test_unsorted_input_is_handled(self):
        timestamps = [BASE + minutes(9), BASE + minutes(3), BASE, BASE + minutes(6)]
        sessions = detect_sessions(make_df(timestamps))
        assert len(sessions) == 1
        assert sessions[0].track_count == 4


# ---------------------------------------------------------------------------
# _slot
# ---------------------------------------------------------------------------

class TestSlot:
    @pytest.mark.parametrize("hour,expected", [
        (0,  "night"),
        (3,  "night"),
        (6,  "morning"),
        (10, "morning"),
        (11, "afternoon"),
        (16, "afternoon"),
        (17, "evening"),
        (20, "evening"),
        (21, "late_night"),
        (23, "late_night"),
    ])
    def test_slot_mapping(self, hour, expected):
        assert _slot(hour) == expected


# ---------------------------------------------------------------------------
# find_patterns
# ---------------------------------------------------------------------------

class TestFindPatterns:
    def test_no_sessions_returns_empty(self):
        assert find_patterns([]) == []

    def test_below_min_occurrences_filtered_out(self):
        sessions = [make_session_at(BASE + timedelta(days=i)) for i in range(2)]
        assert find_patterns(sessions, min_occurrences=3) == []

    def test_pattern_detected_above_threshold(self):
        sessions = [make_session_at(BASE + timedelta(days=i)) for i in range(5)]
        assert len(find_patterns(sessions, min_occurrences=3)) >= 1

    def test_weekday_weekend_separated(self):
        monday = datetime(2026, 1, 5, 10, 0)
        saturday = datetime(2026, 1, 10, 10, 0)
        sessions = (
            [make_session_at(monday + timedelta(weeks=i)) for i in range(4)] +
            [make_session_at(saturday + timedelta(weeks=i)) for i in range(4)]
        )
        keys = {p["key"] for p in find_patterns(sessions, min_occurrences=3)}
        assert "weekday_morning" in keys
        assert "weekend_morning" in keys

    def test_sorted_by_occurrences_descending(self):
        monday = datetime(2026, 1, 5, 10, 0)
        saturday = datetime(2026, 1, 10, 10, 0)
        sessions = (
            [make_session_at(monday + timedelta(weeks=i)) for i in range(5)] +
            [make_session_at(saturday + timedelta(weeks=i)) for i in range(3)]
        )
        counts = [p["occurrences"] for p in find_patterns(sessions, min_occurrences=3)]
        assert counts == sorted(counts, reverse=True)

    def test_top_artists_in_pattern(self):
        sessions = [make_session_at(BASE + timedelta(days=i), artist="Radiohead") for i in range(4)]
        patterns = find_patterns(sessions, min_occurrences=3)
        assert "Radiohead" in patterns[0]["top_artists"]


# ---------------------------------------------------------------------------
# Synthetic integration test
# ---------------------------------------------------------------------------

class TestSyntheticPatterns:
    PATTERN_TRACKS = {
        "morning": [("Morning_Artist_1", "T1"), ("Morning_Artist_2", "T2"), ("Morning_Artist_3", "T3")],
        "work":    [("Work_Artist_1", "T1"),    ("Work_Artist_2", "T2"),    ("Work_Artist_3", "T3")],
        "night":   [("Night_Artist_1", "T1"),   ("Night_Artist_2", "T2"),   ("Night_Artist_3", "T3")],
    }

    @pytest.fixture
    def synthetic_df(self):
        random.seed(42)

        def make_session(start, duration_min, pattern):
            tracks = self.PATTERN_TRACKS[pattern]
            n = max(1, duration_min // 4)
            interval = (duration_min * 60) / n
            return [
                {
                    "timestamp": start + timedelta(seconds=i * interval),
                    "track": t, "artist": a, "album": "", "mbid": "",
                }
                for i, (a, t) in enumerate(random.choices(tracks, k=n))
            ]

        rows = []
        base = datetime(2026, 1, 5)
        for week in range(12):
            monday = base + timedelta(weeks=week)
            for day_offset in range(5):
                day = monday + timedelta(days=day_offset)
                rows.extend(make_session(day.replace(hour=7, minute=30), 30, "morning"))
                rows.extend(make_session(day.replace(hour=14), 120, "work"))
            for day_offset in [4, 5]:
                day = monday + timedelta(days=day_offset)
                rows.extend(make_session(day.replace(hour=23), 90, "night"))

        return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)

    def test_weekday_morning_found(self, synthetic_df):
        patterns = {p["key"]: p for p in find_patterns(detect_sessions(synthetic_df), min_occurrences=3)}
        assert "weekday_morning" in patterns
        assert any(a.startswith("Morning_Artist") for a in patterns["weekday_morning"]["top_artists"])

    def test_weekday_afternoon_found(self, synthetic_df):
        patterns = {p["key"]: p for p in find_patterns(detect_sessions(synthetic_df), min_occurrences=3)}
        assert "weekday_afternoon" in patterns
        assert any(a.startswith("Work_Artist") for a in patterns["weekday_afternoon"]["top_artists"])

    def test_night_pattern_found(self, synthetic_df):
        patterns = {p["key"]: p for p in find_patterns(detect_sessions(synthetic_df), min_occurrences=3)}
        night_key = next((k for k in patterns if "night" in k), None)
        assert night_key is not None
        assert any(a.startswith("Night_Artist") for a in patterns[night_key]["top_artists"])
