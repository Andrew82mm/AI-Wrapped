"""Tests for features added in the 2026-04 roadmap expansion."""
import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.metadata.provider import TrackMetadata
from src.features.period import Period, filter_df, year_period, last_n_days
from src.features.mood_trajectory import mood_trajectory
from src.features.context_switch import context_switches
from src.features.neighbours import musical_roommates
from src.features.guilty_pleasures import guilty_pleasures
from src.features.listening_style import listening_style
from src.features.artifacts import year_artifacts
from src.lastfm.sessions import detect_sessions


def _scrobbles_df(rows):
    return pd.DataFrame(
        rows, columns=["timestamp", "artist", "track", "album", "mbid"]
    )


def _meta(artist, track, mood=None, bpm=None, genres=None, year=None):
    return TrackMetadata(
        artist=artist, track=track, mood=mood, bpm=bpm,
        genres=genres or [], year=year,
    )


# --- period -------------------------------------------------------------

class TestPeriod:
    def test_filter_df_none_is_noop(self):
        df = _scrobbles_df([
            {"timestamp": datetime(2025, 5, 1), "artist": "A", "track": "T",
             "album": "", "mbid": ""},
        ])
        assert len(filter_df(df, None)) == 1

    def test_filter_df_inclusive(self):
        rows = [
            {"timestamp": datetime(2025, m, 1), "artist": "A", "track": "T",
             "album": "", "mbid": ""}
            for m in (3, 6, 9)
        ]
        df = _scrobbles_df(rows)
        p = Period("summer", datetime(2025, 6, 1), datetime(2025, 8, 31))
        assert len(filter_df(df, p)) == 1

    def test_year_period(self):
        p = year_period(2024)
        assert p.contains(datetime(2024, 7, 1))
        assert not p.contains(datetime(2025, 1, 1))

    def test_last_n_days_empty(self):
        assert last_n_days(pd.DataFrame(columns=["timestamp"]), 30) is None


# --- mood_trajectory -----------------------------------------------------

class TestMoodTrajectory:
    def test_empty_df(self):
        assert mood_trajectory(pd.DataFrame(), []) == {}

    def test_no_mood_data(self):
        df = _scrobbles_df([
            {"timestamp": datetime(2025, 1, 1), "artist": "A", "track": "T",
             "album": "", "mbid": ""}
        ])
        assert mood_trajectory(df, [_meta("A", "T")]) == {}

    def test_weekly_aggregation(self):
        metas = [
            _meta("A", "T1", mood={"happy": 0.8, "sad": 0.2, "aggressive": None,
                                   "relaxed": None, "party": None}),
            _meta("B", "T2", mood={"happy": 0.2, "sad": 0.8, "aggressive": None,
                                   "relaxed": None, "party": None}),
        ]
        rows = []
        base = datetime(2025, 1, 6)  # Monday
        for w in range(10):
            for _ in range(5):
                rows.append({
                    "timestamp": base + timedelta(weeks=w),
                    "artist": "A" if w % 2 == 0 else "B",
                    "track": "T1" if w % 2 == 0 else "T2",
                    "album": "", "mbid": "",
                })
        df = _scrobbles_df(rows)
        r = mood_trajectory(df, metas)
        assert r["weeks_covered"] == 10
        assert 0 <= r["baseline"]["happy"] <= 1
        assert "happy" in r["extremes"]

    def test_min_weeks_gate(self):
        metas = [_meta("A", "T", mood={"happy": 0.5, "sad": 0.5})]
        rows = [
            {"timestamp": datetime(2025, 1, 1) + timedelta(weeks=w),
             "artist": "A", "track": "T", "album": "", "mbid": ""}
            for w in range(3)
        ]
        assert mood_trajectory(_scrobbles_df(rows), metas) == {}


# --- context_switch ------------------------------------------------------

class TestContextSwitches:
    def _build_sessions(self):
        rows = []
        # Session 1: 3 tracks by A, tight window
        for m in range(0, 15, 5):
            rows.append({"timestamp": datetime(2025, 1, 1, 10, m),
                         "artist": "A", "track": "T1",
                         "album": "", "mbid": ""})
        # Gap > 30 min → new session
        for m in range(0, 15, 5):
            rows.append({"timestamp": datetime(2025, 1, 1, 14, m),
                         "artist": "B", "track": "T2",
                         "album": "", "mbid": ""})
        return detect_sessions(_scrobbles_df(rows))

    def test_few_sessions(self):
        assert context_switches([], lambda a, t: None) == {}

    def test_sharp_transition(self):
        sessions = self._build_sessions()
        metas = {
            ("A", "T1"): _meta("A", "T1", mood={"happy": 0.1, "sad": 0.9},
                               bpm=60, genres=["ambient"]),
            ("B", "T2"): _meta("B", "T2", mood={"happy": 0.9, "sad": 0.1},
                               bpm=170, genres=["metal"]),
        }
        r = context_switches(sessions, lambda a, t: metas.get((a, t)))
        assert r["scored_transitions"] == 1
        assert r["top_switches"][0]["sharpness"] > 0.5
        assert r["top_switches"][0]["from_artist"] == "A"
        assert r["top_switches"][0]["to_artist"] == "B"

    def test_min_signals_filter(self):
        sessions = self._build_sessions()
        # Only top_artist known — no mood/bpm/genres → skip
        r = context_switches(sessions, lambda a, t: None)
        assert r == {}


# --- neighbours ----------------------------------------------------------

class TestMusicalRoommates:
    def test_no_top_artists(self):
        assert musical_roommates([], set(), lambda a: []) == {}

    def test_aggregates_across_seeds(self):
        def similar(artist):
            return {
                "A": [{"name": "X", "match": 0.9}, {"name": "Y", "match": 0.5}],
                "B": [{"name": "X", "match": 0.7}, {"name": "Z", "match": 0.4}],
            }.get(artist, [])

        r = musical_roommates(["A", "B"], {"A", "B"}, similar, top_n=3)
        names = [rec["artist"] for rec in r["recommendations"]]
        assert names[0] == "X"  # highest aggregated score
        assert "A" not in names and "B" not in names

    def test_filters_known_artists(self):
        def similar(a):
            return [{"name": "Known", "match": 0.9},
                    {"name": "Fresh", "match": 0.5}]
        r = musical_roommates(["Seed"], {"Known"}, similar)
        names = [rec["artist"] for rec in r["recommendations"]]
        assert "Known" not in names
        assert "Fresh" in names


# --- guilty_pleasures ----------------------------------------------------

class TestGuiltyPleasures:
    def test_empty(self):
        assert guilty_pleasures(pd.DataFrame()) == {}

    def test_below_min_plays(self):
        rows = [{"timestamp": datetime(2025, 1, 1, 23, 0),
                 "artist": "Obscure", "track": "T",
                 "album": "", "mbid": ""}]
        r = guilty_pleasures(_scrobbles_df(rows), min_plays=5)
        assert r == {}

    def test_late_night_artist_detected(self):
        rows = [
            {"timestamp": datetime(2025, 1, d, 23, 0),
             "artist": "Secret", "track": "T", "album": "", "mbid": ""}
            for d in range(1, 11)
        ]
        # One normal-hour artist as noise
        rows.extend([
            {"timestamp": datetime(2025, 1, d, 14, 0),
             "artist": "Normal", "track": "T", "album": "", "mbid": ""}
            for d in range(1, 11)
        ])
        r = guilty_pleasures(_scrobbles_df(rows), min_plays=5)
        names = [g["artist"] for g in r["guilty_pleasures"]]
        assert "Secret" in names
        assert "Normal" not in names


# --- listening_style -----------------------------------------------------

class TestListeningStyle:
    def test_empty(self):
        assert listening_style(pd.DataFrame()) == {}

    def test_obsessive(self):
        # 100 plays of single track, 5 unique
        rows = []
        for _ in range(100):
            rows.append({"timestamp": datetime(2025, 1, 1),
                         "artist": "A", "track": "T",
                         "album": "", "mbid": ""})
        for i in range(4):
            rows.append({"timestamp": datetime(2025, 1, 1),
                         "artist": "A", "track": f"Other{i}",
                         "album": "", "mbid": ""})
        r = listening_style(_scrobbles_df(rows))
        assert r["label"] == "obsessive"
        assert r["obsession_track"]["track"] == "T"

    def test_collector(self):
        rows = [{"timestamp": datetime(2025, 1, 1),
                 "artist": f"A{i}", "track": f"T{i}",
                 "album": "", "mbid": ""} for i in range(100)]
        r = listening_style(_scrobbles_df(rows))
        assert r["label"] == "collector"
        assert r["unique_ratio"] == 1.0


# --- artifacts -----------------------------------------------------------

class TestArtifacts:
    def test_empty(self):
        assert year_artifacts(pd.DataFrame(), []) == {}

    def test_streak_and_gap(self):
        rows = []
        # 5-day streak
        for d in range(1, 6):
            rows.append({"timestamp": datetime(2025, 1, d, 12, 0),
                         "artist": "A", "track": "T",
                         "album": "", "mbid": ""})
        # 10-day gap
        rows.append({"timestamp": datetime(2025, 1, 16, 12, 0),
                     "artist": "A", "track": "T",
                     "album": "", "mbid": ""})
        df = _scrobbles_df(rows)
        sessions = detect_sessions(df)
        r = year_artifacts(df, sessions, dead_threshold_days=7)
        assert r["longest_streak"]["days"] == 5
        assert r["dead_periods"][0]["gap_days"] == 11

    def test_peak_day(self):
        rows = []
        for _ in range(50):
            rows.append({"timestamp": datetime(2025, 1, 15, 20, 0),
                         "artist": "A", "track": "T",
                         "album": "", "mbid": ""})
        rows.append({"timestamp": datetime(2025, 1, 16, 20, 0),
                     "artist": "A", "track": "T",
                     "album": "", "mbid": ""})
        df = _scrobbles_df(rows)
        r = year_artifacts(df, detect_sessions(df))
        assert r["peak_day"]["date"] == "2025-01-15"
        assert r["peak_day"]["tracks"] == 50
