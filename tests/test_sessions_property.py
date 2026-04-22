"""Property-based tests for detect_sessions using Hypothesis.

Invariants that must hold for any input:
  1. Track count is conserved — no track is lost or duplicated.
  2. Every session contains at least one track.
  3. Sessions are returned in chronological order (start times ascending).
  4. Each session's start timestamp <= its end timestamp.
  5. Consecutive sessions do not overlap.
"""
import pandas as pd
from datetime import datetime, timedelta

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.lastfm.sessions import detect_sessions, GAP_MINUTES


_BASE = datetime(2020, 1, 1)


def _make_df(minute_offsets: list[int]) -> pd.DataFrame:
    timestamps = [_BASE + timedelta(minutes=m) for m in minute_offsets]
    return pd.DataFrame([
        {"timestamp": ts, "track": "T", "artist": "A", "album": "", "mbid": ""}
        for ts in timestamps
    ])


@given(st.lists(st.integers(min_value=0, max_value=100_000), min_size=1, max_size=200))
@settings(max_examples=500)
def test_track_count_is_conserved(offsets):
    df = _make_df(offsets)
    sessions = detect_sessions(df)
    assert sum(s.track_count for s in sessions) == len(df)


@given(st.lists(st.integers(min_value=0, max_value=100_000), min_size=1, max_size=200))
@settings(max_examples=300)
def test_all_sessions_are_nonempty(offsets):
    sessions = detect_sessions(_make_df(offsets))
    assert all(s.track_count > 0 for s in sessions)


@given(st.lists(st.integers(min_value=0, max_value=100_000), min_size=2, max_size=200))
@settings(max_examples=300)
def test_sessions_are_chronologically_ordered(offsets):
    sessions = detect_sessions(_make_df(offsets))
    starts = [s.start for s in sessions]
    assert starts == sorted(starts)


@given(st.lists(st.integers(min_value=0, max_value=100_000), min_size=1, max_size=200))
@settings(max_examples=300)
def test_session_start_lte_end(offsets):
    sessions = detect_sessions(_make_df(offsets))
    assert all(s.start <= s.end for s in sessions)


@given(st.lists(st.integers(min_value=0, max_value=100_000), min_size=2, max_size=200))
@settings(max_examples=300)
def test_consecutive_sessions_do_not_overlap(offsets):
    sessions = detect_sessions(_make_df(offsets))
    for a, b in zip(sessions, sessions[1:]):
        assert a.end <= b.start


@given(
    st.lists(st.integers(min_value=0, max_value=100_000), min_size=1, max_size=200),
    st.integers(min_value=1, max_value=120),
)
@settings(max_examples=200)
def test_custom_gap_still_conserves_tracks(offsets, gap):
    df = _make_df(offsets)
    sessions = detect_sessions(df, gap_minutes=gap)
    assert sum(s.track_count for s in sessions) == len(df)


@given(st.lists(st.integers(min_value=0, max_value=100_000), min_size=2, max_size=200))
@settings(max_examples=200)
def test_larger_gap_never_produces_more_sessions(offsets):
    """A wider gap threshold can only merge sessions, never split them."""
    df = _make_df(offsets)
    sessions_narrow = detect_sessions(df, gap_minutes=GAP_MINUTES)
    sessions_wide = detect_sessions(df, gap_minutes=GAP_MINUTES * 10)
    assert len(sessions_wide) <= len(sessions_narrow)
