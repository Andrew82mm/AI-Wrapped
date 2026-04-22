"""Integration tests for the metadata resolution pipeline.

Unlike unit tests that use MagicMock (which returns MagicMock for any attribute
access and does not exercise parsing logic), these tests pass *realistic API
response shapes* through the full provider chain.  This catches silent breakage
when MB/AB change their JSON schema.

Each fixture replicates the exact JSON structure returned by the real API.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.metadata.provider import resolve_track_metadata, TrackMetadata
from src.musicbrainz.client import extract_release_year, extract_tags
from src.acousticbrainz.client import extract_mood, extract_genre, extract_bpm
from src.genius.client import extract_release_year as genius_extract_year


# ---------------------------------------------------------------------------
# Realistic API response fixtures
# ---------------------------------------------------------------------------

MB_RECORDING = {
    "id": "8f3b8f56-9166-41d3-8e8f-9a30e72b7dc6",
    "title": "Creep",
    "first-release-date": "1992-09-21",
    "tags": [
        {"name": "alternative rock", "count": 15},
        {"name": "rock", "count": 9},
        {"name": "90s", "count": 4},
    ],
    "releases": [
        {"date": "1992-09-21", "title": "Creep (single)"},
        {"date": "1993-02-22", "title": "Pablo Honey"},
    ],
}

MB_RECORDING_NO_DATE = {
    "id": "aaaa-1111",
    "title": "Track Without Date",
    "first-release-date": "",
    "tags": [],
    "releases": [],
}

AB_HIGH_LEVEL = {
    "highlevel": {
        "genre_dortmund": {"value": "alternative", "probability": 0.82},
        "mood_happy": {"all": {"happy": 0.35, "not_happy": 0.65}},
        "mood_sad": {"all": {"sad": 0.61, "not_sad": 0.39}},
        "mood_aggressive": {"all": {"aggressive": 0.22, "not_aggressive": 0.78}},
        "mood_relaxed": {"all": {"relaxed": 0.55, "not_relaxed": 0.45}},
        "mood_party": {"all": {"party": 0.18, "not_party": 0.82}},
        "danceability": {"all": {"danceable": 0.38, "not_danceable": 0.62}},
    }
}

AB_LOW_LEVEL = {
    "rhythm": {"bpm": 92.4},
    "lowlevel": {"average_loudness": 0.72},
}

GENIUS_SONG = {
    "title": "Creep",
    "url": "https://genius.com/Radiohead-creep-lyrics",
    "release_date_for_display": "September 21, 1992",
    "release_date_components": {"year": 1992, "month": 9, "day": 21},
    "primary_artist": {"name": "Radiohead"},
}


# ---------------------------------------------------------------------------
# Parser unit tests with real JSON shapes
# ---------------------------------------------------------------------------

class TestMBParsersWithRealShapes:
    def test_extract_release_year_from_first_release_date(self):
        assert extract_release_year(MB_RECORDING) == 1992

    def test_extract_release_year_empty_field_falls_back_to_releases(self):
        rec = {
            "first-release-date": "",
            "releases": [{"date": "2010-05-01"}, {"date": "2005-11-30"}],
        }
        assert extract_release_year(rec) == 2005

    def test_extract_release_year_returns_none_when_no_dates(self):
        assert extract_release_year(MB_RECORDING_NO_DATE) is None

    def test_extract_tags_sorted_descending(self):
        tags = extract_tags(MB_RECORDING, top_n=3)
        assert tags[0] == "alternative rock"
        assert tags[1] == "rock"
        assert "90s" in tags

    def test_extract_tags_respects_top_n(self):
        assert len(extract_tags(MB_RECORDING, top_n=2)) == 2

    def test_extract_tags_empty_recording(self):
        assert extract_tags({}) == []


class TestABParsersWithRealShapes:
    def test_extract_mood_happy_probability(self):
        mood = extract_mood(AB_HIGH_LEVEL)
        assert mood is not None
        assert mood["happy"] == pytest.approx(0.35, abs=1e-3)
        assert mood["sad"] == pytest.approx(0.61, abs=1e-3)

    def test_extract_mood_danceability(self):
        mood = extract_mood(AB_HIGH_LEVEL)
        assert mood["danceability"] == pytest.approx(0.38, abs=1e-3)

    def test_extract_mood_returns_none_for_empty_payload(self):
        assert extract_mood({}) is None
        assert extract_mood({"highlevel": {}}) is None

    def test_extract_genre_dortmund_value(self):
        assert extract_genre(AB_HIGH_LEVEL) == "alternative"

    def test_extract_genre_returns_none_when_missing(self):
        assert extract_genre({}) is None
        assert extract_genre({"highlevel": {}}) is None

    def test_extract_bpm_rounded(self):
        assert extract_bpm(AB_LOW_LEVEL) == pytest.approx(92.4, abs=0.05)

    def test_extract_bpm_returns_none_for_empty(self):
        assert extract_bpm({}) is None
        assert extract_bpm(None) is None


class TestGeniusParsersWithRealShapes:
    def test_extract_release_year_from_components(self):
        assert genius_extract_year(GENIUS_SONG) == 1992

    def test_extract_release_year_returns_none_when_no_components(self):
        assert genius_extract_year({}) is None
        assert genius_extract_year({"release_date_components": {}}) is None

    def test_extract_release_year_returns_none_for_none_input(self):
        assert genius_extract_year(None) is None


# ---------------------------------------------------------------------------
# End-to-end pipeline with real JSON shapes
# ---------------------------------------------------------------------------

class TestResolveTrackMetadataE2E:
    def _make_mb(self, recording=MB_RECORDING):
        mb = MagicMock()
        mb.search_recording.return_value = recording
        mb.get_recording.return_value = recording
        return mb

    def _make_ab(self, high=AB_HIGH_LEVEL, low=AB_LOW_LEVEL):
        ab = MagicMock()
        ab.get_high_level.return_value = high
        ab.get_low_level.return_value = low
        return ab

    def test_full_pipeline_happy_path(self):
        meta = resolve_track_metadata(
            "Radiohead", "Creep", self._make_mb(), self._make_ab()
        )
        assert isinstance(meta, TrackMetadata)
        assert meta.mbid == "8f3b8f56-9166-41d3-8e8f-9a30e72b7dc6"
        assert meta.year == 1992
        assert "alternative" in meta.genres
        assert meta.mood is not None
        assert meta.mood["happy"] == pytest.approx(0.35, abs=1e-3)
        assert meta.bpm == pytest.approx(92.4, abs=0.05)
        assert "musicbrainz" in meta.sources
        assert "acousticbrainz" in meta.sources

    def test_pipeline_with_known_mbid_skips_search(self):
        mb = self._make_mb()
        meta = resolve_track_metadata(
            "Radiohead", "Creep", mb, self._make_ab(),
            known_mbid="8f3b8f56-9166-41d3-8e8f-9a30e72b7dc6",
        )
        mb.search_recording.assert_not_called()
        assert meta.mbid == "8f3b8f56-9166-41d3-8e8f-9a30e72b7dc6"

    def test_pipeline_genius_year_fills_missing_mb_date(self):
        mb = self._make_mb(recording=MB_RECORDING_NO_DATE)
        ab = self._make_ab(high=None, low=None)

        def genius_fn(artist, track):
            return GENIUS_SONG

        meta = resolve_track_metadata(
            "X", "Y", mb, ab, genius_search_fn=genius_fn
        )
        assert meta.year == 1992
        assert "genius" in meta.sources

    def test_pipeline_ab_genre_prepended_to_mb_tags(self):
        """AB genre should appear first in genres list."""
        meta = resolve_track_metadata(
            "Radiohead", "Creep", self._make_mb(), self._make_ab()
        )
        assert meta.genres[0] == "alternative"

    def test_pipeline_lastfm_tags_used_when_no_mb_genres(self):
        recording_no_tags = {**MB_RECORDING, "tags": []}
        mb = self._make_mb(recording=recording_no_tags)
        ab = self._make_ab(high=None, low=None)
        lastfm_fn = MagicMock(return_value=["shoegaze", "dreampop"])

        meta = resolve_track_metadata(
            "Slowdive", "Alison", mb, ab, lastfm_tags_fn=lastfm_fn
        )
        assert meta.genres == ["shoegaze", "dreampop"]
        assert "lastfm" in meta.sources

    def test_pipeline_graceful_when_mb_returns_none(self):
        mb = MagicMock()
        mb.search_recording.return_value = None
        ab = MagicMock()

        meta = resolve_track_metadata("Ghost", "Phantom", mb, ab)

        assert meta.mbid is None
        assert meta.year is None
        assert meta.genres == []
        assert meta.mood is None
        ab.get_high_level.assert_not_called()

    def test_pipeline_ab_fallback_uses_cached_high_level(self):
        """_find_ab_mbid must not trigger a second get_high_level for the winning MBID."""
        mb = self._make_mb()
        ab = MagicMock()
        # Primary MBID returns 404 (None), candidate mbid-alt has data.
        ab.get_high_level.side_effect = lambda mbid: (
            None if mbid == MB_RECORDING["id"] else AB_HIGH_LEVEL
        )
        ab.get_low_level.return_value = AB_LOW_LEVEL
        mb.search_recording_candidates.return_value = [
            {"id": MB_RECORDING["id"]},
            {"id": "mbid-alt"},
        ]

        meta = resolve_track_metadata("Radiohead", "Creep", mb, ab)

        # get_high_level for "mbid-alt" should be called exactly once (probe reused).
        calls = [c.args[0] for c in ab.get_high_level.call_args_list]
        assert calls.count("mbid-alt") == 1
        assert meta.mood is not None
