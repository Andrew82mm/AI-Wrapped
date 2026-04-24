"""Tests for frontend/render.py — build_wrapped_data and helpers."""
from __future__ import annotations

import pytest

from frontend.render import (
    _period_meta,
    _format_duration,
    _format_date,
    build_wrapped_data,
)


# --- _period_meta -----------------------------------------------------------

class TestPeriodMeta:
    def test_lifetime(self):
        r = _period_meta("lifetime")
        assert r["label"] == "All time"
        assert r["days"] is None

    def test_last_90(self):
        r = _period_meta("last:90")
        assert r["label"] == "90 days"
        assert r["days"] == 90

    def test_last_7(self):
        r = _period_meta("last:7")
        assert r["label"] == "7 days"
        assert r["days"] == 7

    def test_last_180(self):
        assert _period_meta("last:180")["label"] == "6 months"

    def test_last_365(self):
        assert _period_meta("last:365")["label"] == "1 year"

    def test_last_unknown_days(self):
        r = _period_meta("last:45")
        assert r["label"] == "45 days"
        assert r["days"] == 45

    def test_year(self):
        r = _period_meta("2025")
        assert r["label"] == "2025"
        assert r["days"] == 365

    def test_unknown_falls_back(self):
        r = _period_meta("custom_range")
        assert r["label"] == "custom_range"
        assert r["days"] is None


# --- _format_duration -------------------------------------------------------

class TestFormatDuration:
    def test_under_one_hour(self):
        assert _format_duration(45) == "45m"

    def test_exactly_one_hour(self):
        assert _format_duration(60) == "1h 00m"

    def test_mixed(self):
        assert _format_duration(95) == "1h 35m"

    def test_zero(self):
        assert _format_duration(0) == "0m"


# --- _format_date -----------------------------------------------------------

class TestFormatDate:
    def test_valid_iso(self):
        result = _format_date("2025-06-15T20:00:00")
        assert "Jun" in result
        assert "15" in result

    def test_invalid_fallback(self):
        assert _format_date("not-a-date") == "not-a-date"


# --- build_wrapped_data -----------------------------------------------------

FULL_FEATURES = {
    "time_signature": {
        "peak_hour": 23,
        "dominant_slot": "late_night",
        "label": "night owl",
        "slot_distribution": {"night": 0.1, "morning": 0.05, "afternoon": 0.1,
                              "evening": 0.2, "late_night": 0.55},
        "hour_distribution": list(range(24)),
    },
    "decade_fingerprint": {
        "distribution": {"2020s": 0.6, "2010s": 0.3, "1990s": 0.1},
        "dominant_decade": "2020s",
        "earliest_year": 1991,
        "latest_year": 2025,
    },
    "binge_weeks": {
        "median_weekly_tracks": 50,
        "binge_count": 2,
        "weekly_data": [
            {"label": "Jan 1", "tracks": 100, "is_binge": True,  "top_artist": "Radiohead"},
            {"label": "Jan 8", "tracks": 40,  "is_binge": False, "top_artist": None},
        ] * 8,
    },
    "artist_loyalty": {
        "veterans": [{"artist": "Radiohead", "active_weeks": 52}],
        "newcomers": [{"artist": "Laufey",   "first_week": "2025-W10"}],
    },
    "guilty_pleasures": {
        "guilty_pleasures": [
            {"artist": "Calvin Harris", "plays": 12, "late_fraction": 0.9},
            {"artist": "Pitbull",       "plays":  8, "late_fraction": 0.8},
        ],
    },
    "musical_roommates": {
        "recommendations": [
            {"artist": "Thom Yorke", "suggested_by": ["Radiohead"]},
        ],
    },
    "artifacts": {
        "longest_session": {
            "duration_min": 150,
            "start": "2025-03-10T20:00:00",
            "top_artists": ["Radiohead"],
        },
        "longest_streak": {
            "days": 14,
            "start": "2025-01-01T00:00:00",
            "end": "2025-01-14T00:00:00",
        },
        "peak_day": {"date": "2025-03-10T00:00:00", "tracks": 80},
        "dead_periods": [{"gap_days": 10, "after": "2025-02-01", "before": "2025-02-11"}],
    },
}


def _build(features=None, period="last:90", scrobbles=900, narrative=None):
    payload = {
        "user": "testuser",
        "period": period,
        "scrobbles_total": scrobbles,
        "features": features or FULL_FEATURES,
    }
    return build_wrapped_data(payload, narrative)


class TestBuildWrappedDataBasic:
    def test_user_and_period_pass_through(self):
        d = _build()
        assert d["user"] == "testuser"
        assert d["period"]["days"] == 90

    def test_scrobbles_and_per_day(self):
        d = _build(scrobbles=900)
        assert d["scrobbles"] == 900
        assert d["per_day"] == 10  # 900 / 90

    def test_per_day_zero_for_lifetime(self):
        d = _build(period="lifetime", scrobbles=1000)
        assert d["per_day"] == 0

    def test_empty_features_no_crash(self):
        d = build_wrapped_data({"user": "u", "period": "lifetime", "scrobbles_total": 0, "features": {}})
        assert d["user"] == "u"
        assert d["guilty_pleasures"] == []
        assert d["artifacts"] == []


class TestTimeSignatureTransform:
    def test_peak_label_pm(self):
        d = _build()
        assert d["time_signature"]["peak_label"] == "11:00 PM"

    def test_peak_label_am(self):
        features = {**FULL_FEATURES, "time_signature": {**FULL_FEATURES["time_signature"], "peak_hour": 9}}
        d = _build(features=features)
        assert d["time_signature"]["peak_label"] == "9:00 AM"

    def test_peak_label_noon(self):
        features = {**FULL_FEATURES, "time_signature": {**FULL_FEATURES["time_signature"], "peak_hour": 12}}
        d = _build(features=features)
        assert d["time_signature"]["peak_label"] == "12:00 PM"

    def test_peak_label_midnight(self):
        features = {**FULL_FEATURES, "time_signature": {**FULL_FEATURES["time_signature"], "peak_hour": 0}}
        d = _build(features=features)
        assert d["time_signature"]["peak_label"] == "12:00 AM"

    def test_label_mapped(self):
        d = _build()
        assert d["time_signature"]["label"] == "Night Owl"

    def test_slot_pill_late_night(self):
        d = _build()
        assert "10 PM" in d["time_signature"]["pill"]

    def test_slot_pill_morning(self):
        features = {**FULL_FEATURES, "time_signature": {**FULL_FEATURES["time_signature"], "dominant_slot": "morning"}}
        d = _build(features=features)
        assert "Morning" in d["time_signature"]["pill"]

    def test_hour_distribution_passes_through(self):
        d = _build()
        assert len(d["time_signature"]["hour_distribution"]) == 24


class TestDecadeFingerprintTransform:
    def test_sorted_by_pct_descending(self):
        d = _build()
        pcts = [dec["pct"] for dec in d["decade_fingerprint"]["decades"]]
        assert pcts == sorted(pcts, reverse=True)

    def test_pct_scaled_to_100(self):
        d = _build()
        dec_map = {dec["label"]: dec["pct"] for dec in d["decade_fingerprint"]["decades"]}
        assert dec_map["2020s"] == 60

    def test_dominant_passed_through(self):
        d = _build()
        assert d["decade_fingerprint"]["dominant"] == "2020s"

    def test_known_decade_gets_color(self):
        d = _build()
        colors = {dec["label"]: dec["color"] for dec in d["decade_fingerprint"]["decades"]}
        assert colors["2020s"] == "#e60023"

    def test_unknown_decade_gets_fallback_color(self):
        features = {**FULL_FEATURES, "decade_fingerprint": {"distribution": {"1800s": 1.0}, "dominant_decade": "1800s"}}
        d = _build(features=features)
        assert d["decade_fingerprint"]["decades"][0]["color"] == "#6845ab"


class TestBingeWeeksTransform:
    def test_capped_at_16_weeks(self):
        d = _build()
        assert len(d["binge_weeks"]["weeks"]) <= 16

    def test_spike_flag_set(self):
        d = _build()
        spikes = [w for w in d["binge_weeks"]["weeks"] if w["spike"]]
        assert all(w["artist"] is not None for w in spikes)

    def test_non_binge_artist_is_none(self):
        d = _build()
        non_spikes = [w for w in d["binge_weeks"]["weeks"] if not w["spike"]]
        assert all(w["artist"] is None for w in non_spikes)

    def test_median_and_count_passed_through(self):
        d = _build()
        assert d["binge_weeks"]["median"] == 50
        assert d["binge_weeks"]["binge_count"] == 2


class TestArtistLoyaltyTransform:
    def test_veteran_present(self):
        d = _build()
        assert d["artist_loyalty"]["veterans"][0]["name"] == "Radiohead"
        assert "52 weeks" in d["artist_loyalty"]["veterans"][0]["badge"]

    def test_newcomer_badge_has_date(self):
        d = _build()
        badge = d["artist_loyalty"]["newcomers"][0]["badge"]
        assert badge.startswith("first heard")

    def test_capped_at_five(self):
        features = {**FULL_FEATURES, "artist_loyalty": {
            "veterans":  [{"artist": f"V{i}", "active_weeks": i} for i in range(10)],
            "newcomers": [{"artist": f"N{i}", "first_week": "2025-W01"} for i in range(10)],
        }}
        d = _build(features=features)
        assert len(d["artist_loyalty"]["veterans"])  <= 5
        assert len(d["artist_loyalty"]["newcomers"]) <= 5


class TestGuiltyPleasuresTransform:
    def test_artist_name_and_tag(self):
        d = _build()
        gp = d["guilty_pleasures"]
        assert gp[0]["name"] == "Calvin Harris"
        assert "90%" in gp[0]["tag"]

    def test_palette_assigned(self):
        d = _build()
        for item in d["guilty_pleasures"]:
            assert "bg" in item and "color" in item

    def test_letter_is_first_char_uppercase(self):
        d = _build()
        assert d["guilty_pleasures"][0]["letter"] == "C"

    def test_capped_at_three(self):
        features = {**FULL_FEATURES, "guilty_pleasures": {
            "guilty_pleasures": [{"artist": f"GP{i}", "plays": 5, "late_fraction": 0.9} for i in range(10)]
        }}
        d = _build(features=features)
        assert len(d["guilty_pleasures"]) <= 3

    def test_empty_guilty_returns_empty_list(self):
        features = {**FULL_FEATURES, "guilty_pleasures": {"guilty_pleasures": []}}
        d = _build(features=features)
        assert d["guilty_pleasures"] == []


class TestRecommendationsTransform:
    def test_name_and_via(self):
        d = _build()
        rec = d["recommendations"][0]
        assert rec["name"] == "Thom Yorke"
        assert rec["via"] == ["Radiohead"]

    def test_via_capped_at_three(self):
        features = {**FULL_FEATURES, "musical_roommates": {
            "recommendations": [{"artist": "X", "suggested_by": ["A", "B", "C", "D", "E"]}]
        }}
        d = _build(features=features)
        assert len(d["recommendations"][0]["via"]) <= 3

    def test_capped_at_three_recs(self):
        features = {**FULL_FEATURES, "musical_roommates": {
            "recommendations": [{"artist": f"R{i}", "suggested_by": []} for i in range(10)]
        }}
        d = _build(features=features)
        assert len(d["recommendations"]) <= 3


class TestArtifactsTransform:
    def test_longest_session_card(self):
        d = _build()
        session_cards = [c for c in d["artifacts"] if "session" in c["label"].lower()]
        assert session_cards
        assert "2h 30m" in session_cards[0]["value"]

    def test_streak_card(self):
        d = _build()
        streak_cards = [c for c in d["artifacts"] if "streak" in c["label"].lower()]
        assert streak_cards
        assert "14 days" in streak_cards[0]["value"]

    def test_peak_day_card(self):
        d = _build()
        peak_cards = [c for c in d["artifacts"] if "scrobbles" in c["label"].lower()]
        assert peak_cards
        assert peak_cards[0]["value"] == "80"

    def test_dead_period_card(self):
        d = _build()
        dead_cards = [c for c in d["artifacts"] if "silence" in c["value"] or "break" in c["label"].lower()]
        assert dead_cards

    def test_no_crash_when_artifacts_empty(self):
        features = {**FULL_FEATURES, "artifacts": {}}
        d = _build(features=features)
        assert d["artifacts"] == []


class TestNarrativeSections:
    def test_sections_passed_through(self):
        secs = [{"title": "T", "body": "B"}]
        d = _build(narrative=secs)
        assert d["narrative"]["sections"] == secs

    def test_no_sections_defaults_to_empty_list(self):
        d = _build(narrative=None)
        assert d["narrative"]["sections"] == []
