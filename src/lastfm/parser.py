from datetime import datetime
import pandas as pd


def parse_scrobbles(raw_tracks: list[dict]) -> pd.DataFrame:
    """Convert raw Last.fm track list to a clean DataFrame."""
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
