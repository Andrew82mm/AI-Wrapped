import pytest
import pandas as pd
from src.lastfm.parser import parse_scrobbles, parse_top_artists, parse_top_tracks, parse_top_albums


def make_raw_track(name="Creep", artist="Radiohead", album="Pablo Honey", uts="1700000000", mbid="abc"):
    return {
        "name": name,
        "artist": {"#text": artist},
        "album": {"#text": album},
        "date": {"uts": uts},
        "mbid": mbid,
    }


def make_raw_artist(rank, name, playcount, mbid=""):
    return {"@attr": {"rank": str(rank)}, "name": name, "playcount": str(playcount), "mbid": mbid}


def make_raw_track_top(rank, name, artist, playcount, duration=240, mbid=""):
    return {
        "@attr": {"rank": str(rank)},
        "name": name,
        "artist": {"name": artist},
        "playcount": str(playcount),
        "duration": str(duration),
        "mbid": mbid,
    }


def make_raw_album(rank, name, artist, playcount, mbid=""):
    return {
        "@attr": {"rank": str(rank)},
        "name": name,
        "artist": {"name": artist},
        "playcount": str(playcount),
        "mbid": mbid,
    }


class TestParseScrobbles:
    def test_basic_fields(self):
        raw = [make_raw_track()]
        df = parse_scrobbles(raw)
        assert list(df.columns) == ["timestamp", "track", "artist", "album", "mbid"]
        assert df.iloc[0]["track"] == "Creep"
        assert df.iloc[0]["artist"] == "Radiohead"

    def test_sorted_by_timestamp(self):
        raw = [
            make_raw_track(uts="1700000100"),
            make_raw_track(uts="1700000000"),
            make_raw_track(uts="1700000200"),
        ]
        df = parse_scrobbles(raw)
        timestamps = df["timestamp"].tolist()
        assert timestamps == sorted(timestamps)

    def test_missing_mbid_defaults_to_empty_string(self):
        raw = [{"name": "X", "artist": {"#text": "Y"}, "album": {"#text": "Z"}, "date": {"uts": "1700000000"}}]
        df = parse_scrobbles(raw)
        assert df.iloc[0]["mbid"] == ""

    def test_empty_input(self):
        df = parse_scrobbles([])
        assert df.empty


class TestParseTopArtists:
    def test_fields_and_types(self):
        raw = [make_raw_artist(1, "Radiohead", 100, "mbid-1")]
        df = parse_top_artists(raw)
        assert df.iloc[0]["rank"] == 1
        assert df.iloc[0]["artist"] == "Radiohead"
        assert df.iloc[0]["playcount"] == 100

    def test_multiple_artists_order_preserved(self):
        raw = [make_raw_artist(1, "A", 100), make_raw_artist(2, "B", 50)]
        df = parse_top_artists(raw)
        assert list(df["artist"]) == ["A", "B"]


class TestParseTopTracks:
    def test_fields_and_types(self):
        raw = [make_raw_track_top(1, "Creep", "Radiohead", 42, duration=200)]
        df = parse_top_tracks(raw)
        assert df.iloc[0]["track"] == "Creep"
        assert df.iloc[0]["duration_sec"] == 200
        assert df.iloc[0]["playcount"] == 42

    def test_missing_duration_defaults_to_zero(self):
        item = make_raw_track_top(1, "T", "A", 10)
        del item["duration"]
        df = parse_top_tracks([item])
        assert df.iloc[0]["duration_sec"] == 0


class TestParseTopAlbums:
    def test_fields_and_types(self):
        raw = [make_raw_album(1, "OK Computer", "Radiohead", 38)]
        df = parse_top_albums(raw)
        assert df.iloc[0]["album"] == "OK Computer"
        assert df.iloc[0]["artist"] == "Radiohead"
        assert df.iloc[0]["playcount"] == 38
