from unittest.mock import MagicMock

from src.metadata.provider import resolve_track_metadata
from src.musicbrainz.client import extract_release_year, extract_tags
from src.acousticbrainz.client import extract_mood, extract_genre, extract_bpm


def make_recording(mbid="mb-1", first_release="2001-05-01", tags=None):
    return {
        "id": mbid,
        "first-release-date": first_release,
        "tags": tags or [{"name": "Post-Rock", "count": 10}, {"name": "Ambient", "count": 3}],
    }


def make_high_level(genre="rock", happy=0.8, danceable=0.4):
    return {
        "highlevel": {
            "genre_dortmund": {"value": genre, "probability": 0.7},
            "mood_happy": {"all": {"happy": happy, "not_happy": 1 - happy}},
            "mood_sad": {"all": {"sad": 0.1, "not_sad": 0.9}},
            "mood_aggressive": {"all": {"aggressive": 0.2, "not_aggressive": 0.8}},
            "mood_relaxed": {"all": {"relaxed": 0.6, "not_relaxed": 0.4}},
            "mood_party": {"all": {"party": 0.3, "not_party": 0.7}},
            "danceability": {"all": {"danceable": danceable, "not_danceable": 1 - danceable}},
        }
    }


def make_low_level(bpm=128.5):
    return {"rhythm": {"bpm": bpm}}


def test_extract_release_year_prefers_first_release_date():
    rec = make_recording(first_release="1999-03-10")
    assert extract_release_year(rec) == 1999


def test_extract_release_year_falls_back_to_releases():
    rec = {"first-release-date": "", "releases": [{"date": "2010-01-01"}, {"date": "2005-06-06"}]}
    assert extract_release_year(rec) == 2005


def test_extract_release_year_handles_missing():
    assert extract_release_year({}) is None


def test_extract_tags_sorted_by_count():
    rec = {"tags": [{"name": "B", "count": 1}, {"name": "A", "count": 10}]}
    assert extract_tags(rec, top_n=2) == ["a", "b"]


def test_extract_mood_returns_probabilities():
    mood = extract_mood(make_high_level(happy=0.75, danceable=0.2))
    assert mood["happy"] == 0.75
    assert mood["danceability"] == 0.2


def test_extract_mood_none_on_empty():
    assert extract_mood({}) is None
    assert extract_mood({"highlevel": {}}) is None


def test_extract_genre_from_dortmund():
    assert extract_genre(make_high_level(genre="jazz")) == "jazz"


def test_extract_bpm():
    assert extract_bpm(make_low_level(128.4)) == 128.4
    assert extract_bpm(None) is None
    assert extract_bpm({}) is None


def test_resolve_uses_mb_then_ab():
    mb = MagicMock()
    mb.search_recording.return_value = make_recording(mbid="mb-123")
    ab = MagicMock()
    ab.get_high_level.return_value = make_high_level(genre="rock")
    ab.get_low_level.return_value = make_low_level(bpm=140.0)

    meta = resolve_track_metadata("Radiohead", "Creep", mb, ab)

    assert meta.mbid == "mb-123"
    assert meta.year == 2001
    assert meta.bpm == 140.0
    assert meta.mood["happy"] == 0.8
    assert "rock" in meta.genres
    assert "musicbrainz" in meta.sources
    assert "acousticbrainz" in meta.sources


def test_resolve_falls_back_to_lastfm_tags_when_no_genres():
    mb = MagicMock()
    mb.search_recording.return_value = {"id": "mb-x", "first-release-date": "", "tags": []}
    ab = MagicMock()
    ab.get_high_level.return_value = None
    ab.get_low_level.return_value = None
    lastfm_fn = MagicMock(return_value=["shoegaze", "dreampop"])

    meta = resolve_track_metadata("Slowdive", "Alison", mb, ab, lastfm_tags_fn=lastfm_fn)

    assert meta.genres == ["shoegaze", "dreampop"]
    assert "lastfm" in meta.sources
    lastfm_fn.assert_called_once_with("Slowdive", "Alison")


def test_resolve_skips_mb_search_when_known_mbid():
    mb = MagicMock()
    mb.get_recording.return_value = make_recording(mbid="known-mb")
    ab = MagicMock()
    ab.get_high_level.return_value = None
    ab.get_low_level.return_value = None

    meta = resolve_track_metadata("X", "Y", mb, ab, known_mbid="known-mb")

    mb.search_recording.assert_not_called()
    mb.get_recording.assert_called_once_with("known-mb")
    assert meta.mbid == "known-mb"


def test_resolve_returns_empty_when_mb_fails():
    mb = MagicMock()
    mb.search_recording.return_value = None
    ab = MagicMock()

    meta = resolve_track_metadata("Unknown", "Nothing", mb, ab)

    assert meta.mbid is None
    assert meta.year is None
    assert meta.genres == []
    assert meta.mood is None
    ab.get_high_level.assert_not_called()
