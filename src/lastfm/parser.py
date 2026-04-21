from datetime import datetime
import pandas as pd


def parse_scrobbles(raw_tracks: list[dict]) -> pd.DataFrame:
    """Parse raw scrobbles from user.getRecentTracks into a DataFrame.

    Columns: timestamp, track, artist, album, mbid.
    Result is sorted by timestamp ascending.
    Currently playing track (no date field) must be filtered out before calling.
    """
    rows = []
    for t in raw_tracks:
        rows.append({
            "timestamp": datetime.fromtimestamp(int(t["date"]["uts"])),
            "track": t["name"],
            "artist": t["artist"]["#text"],
            "album": t["album"]["#text"],
            "mbid": t.get("mbid", ""),
        })

    if not rows:
        return pd.DataFrame(columns=["timestamp", "track", "artist", "album", "mbid"])
    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def parse_top_artists(raw: list[dict]) -> pd.DataFrame:
    """Parse raw response from user.getTopArtists into a DataFrame.

    Columns: rank, artist, playcount, mbid.
    """
    rows = []
    for item in raw:
        rows.append({
            "rank": int(item["@attr"]["rank"]),
            "artist": item["name"],
            "playcount": int(item["playcount"]),
            "mbid": item.get("mbid", ""),
        })
    return pd.DataFrame(rows)


def parse_top_tracks(raw: list[dict]) -> pd.DataFrame:
    """Parse raw response from user.getTopTracks into a DataFrame.

    Columns: rank, track, artist, playcount, duration_sec, mbid.
    """
    rows = []
    for item in raw:
        rows.append({
            "rank": int(item["@attr"]["rank"]),
            "track": item["name"],
            "artist": item["artist"]["name"],
            "playcount": int(item["playcount"]),
            "duration_sec": int(item.get("duration", 0)),
            "mbid": item.get("mbid", ""),
        })
    return pd.DataFrame(rows)


def parse_top_albums(raw: list[dict]) -> pd.DataFrame:
    """Parse raw response from user.getTopAlbums into a DataFrame.

    Columns: rank, album, artist, playcount, mbid.
    """
    rows = []
    for item in raw:
        rows.append({
            "rank": int(item["@attr"]["rank"]),
            "album": item["name"],
            "artist": item["artist"]["name"],
            "playcount": int(item["playcount"]),
            "mbid": item.get("mbid", ""),
        })
    return pd.DataFrame(rows)
