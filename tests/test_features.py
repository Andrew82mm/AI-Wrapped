import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.features.decade import decade_fingerprint
from src.features.binge import binge_weeks
from src.features.time_profile import time_signature
from src.features.artist_loyalty import artist_loyalty
from src.features.discovery import discovery_rate
from src.metadata.provider import TrackMetadata


def _meta(year):
    return TrackMetadata(artist="A", track="T", year=year)


def _df(rows):
    return pd.DataFrame(rows, columns=["timestamp", "artist", "track", "album", "mbid"])


def _scrobbles(n_weeks=12, tracks_per_week=10):
    rows = []
    base = datetime(2024, 1, 1, 20, 0)
    for w in range(n_weeks):
        for d in range(tracks_per_week):
            rows.append({
                "timestamp": base + timedelta(weeks=w, hours=d),
                "artist": f"Artist{(w * d) % 5}",
                "track": f"Track{(w * d) % 20}",
                "album": "",
                "mbid": "",
            })
    return pd.DataFrame(rows)


# --- decade_fingerprint ---

class TestDecadeFingerprint:
    def test_empty(self):
        assert decade_fingerprint([]) == {}

    def test_no_years(self):
        assert decade_fingerprint([TrackMetadata("A", "T")]) == {}

    def test_single_decade(self):
        metas = [_meta(1995), _meta(1997), _meta(1999)]
        r = decade_fingerprint(metas)
        assert r["dominant_decade"] == "1990s"
        assert r["covered_decades"] == 1
        assert r["era_label"] == "catalog_digger"

    def test_eclectic_span(self):
        metas = [_meta(1972), _meta(1985), _meta(2000), _meta(2015), _meta(2024)]
        r = decade_fingerprint(metas)
        assert r["era_label"] == "eclectic"
        assert r["covered_decades"] == 5

    def test_contemporary(self):
        metas = [_meta(2022), _meta(2023), _meta(2024), _meta(2025)]
        r = decade_fingerprint(metas)
        assert r["dominant_decade"] == "2020s"
        assert r["era_label"] == "contemporary"

    def test_distribution_sums_to_one(self):
        metas = [_meta(1990), _meta(2000), _meta(2010)]
        r = decade_fingerprint(metas)
        assert abs(sum(r["distribution"].values()) - 1.0) < 0.02


# --- binge_weeks ---

class TestBingeWeeks:
    def test_empty(self):
        assert binge_weeks(pd.DataFrame()) == {}

    def test_too_few_weeks(self):
        df = _scrobbles(n_weeks=4)
        assert binge_weeks(df) == {}

    def test_detects_binge(self):
        rows = []
        base = datetime(2024, 1, 1, 20, 0)
        for w in range(10):
            count = 100 if w == 5 else 10
            for i in range(count):
                rows.append({"timestamp": base + timedelta(weeks=w, hours=i),
                              "artist": "A", "track": "T", "album": "", "mbid": ""})
        df = pd.DataFrame(rows)
        r = binge_weeks(df)
        assert r["binge_count"] >= 1
        assert r["binges"][0]["vs_median"] > 2.0

    def test_no_binge_when_flat(self):
        df = _scrobbles(n_weeks=10, tracks_per_week=10)
        r = binge_weeks(df)
        assert r.get("binge_count", 0) == 0


# --- time_signature ---

class TestTimeSignature:
    def test_empty(self):
        assert time_signature(pd.DataFrame()) == {}

    def test_night_owl(self):
        rows = [{"timestamp": datetime(2024, 1, i % 28 + 1, 23, 0),
                 "artist": "A", "track": "T", "album": "", "mbid": ""}
                for i in range(50)]
        df = pd.DataFrame(rows)
        r = time_signature(df)
        assert r["dominant_slot"] == "late_night"
        assert r["label"] == "night owl"

    def test_distribution_sums_to_one(self):
        df = _scrobbles(n_weeks=4)
        r = time_signature(df)
        assert abs(sum(r["slot_distribution"].values()) - 1.0) < 0.01


# --- artist_loyalty ---

class TestArtistLoyalty:
    def test_empty(self):
        assert artist_loyalty(pd.DataFrame()) == {}

    def test_veteran_detected(self):
        rows = []
        base = datetime(2023, 1, 1)
        for w in range(20):
            rows.append({"timestamp": base + timedelta(weeks=w),
                         "artist": "Radiohead", "track": "Creep", "album": "", "mbid": ""})
        df = pd.DataFrame(rows)
        r = artist_loyalty(df)
        veterans = [v["artist"] for v in r["veterans"]]
        assert "Radiohead" in veterans

    def test_newcomer_detected(self):
        rows = []
        base = datetime(2024, 1, 1)
        for w in range(10):
            rows.append({"timestamp": base + timedelta(weeks=w),
                         "artist": "OldBand", "track": "T", "album": "", "mbid": ""})
        # Newcomer only in last 2 weeks
        for w in range(9, 11):
            rows.append({"timestamp": base + timedelta(weeks=w),
                         "artist": "NewBand", "track": "T", "album": "", "mbid": ""})
        df = pd.DataFrame(rows)
        r = artist_loyalty(df)
        newcomers = [n["artist"] for n in r["newcomers"]]
        assert "NewBand" in newcomers


# --- discovery_rate ---

class TestDiscoveryRate:
    def test_empty(self):
        assert discovery_rate(pd.DataFrame()) == {}

    def test_too_few_months(self):
        rows = [{"timestamp": datetime(2024, 1, i + 1),
                 "artist": "A", "track": f"T{i}", "album": "", "mbid": ""}
                for i in range(10)]
        assert discovery_rate(pd.DataFrame(rows)) == {}

    def test_explorer_score_range(self):
        df = _scrobbles(n_weeks=16)
        r = discovery_rate(df)
        assert 0 <= r["explorer_score"] <= 1

    def test_trend_field_present(self):
        df = _scrobbles(n_weeks=24)
        r = discovery_rate(df)
        assert r["trend"] in ("growing", "declining", "stable")
