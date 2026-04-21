import time
import requests


BASE_URL = "https://ws.audioscrobbler.com/2.0/"


class LastFMClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, method: str, **params) -> dict:
        """Send a GET request to the Last.fm API and return the parsed JSON.

        Raises ValueError on API-level errors (e.g. invalid user, bad method).
        """
        response = self.session.get(BASE_URL, params={
            "method": method,
            "api_key": self.api_key,
            "format": "json",
            **params,
        })
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise ValueError(f"Last.fm API error {data['error']}: {data['message']}")
        return data

    def get_recent_tracks(self, username: str, from_ts: int = None, to_ts: int = None, limit: int = 200) -> list[dict]:
        """Fetch all scrobbles for a user, handling pagination automatically.

        Args:
            from_ts: Unix timestamp — fetch scrobbles after this point.
            to_ts:   Unix timestamp — fetch scrobbles before this point.
            limit:   Page size (max 200 per Last.fm API).

        Returns a flat list of raw track dicts with the currently-playing
        track (no date field) already filtered out.
        """
        tracks = []
        page = 1

        while True:
            params = {"user": username, "limit": limit, "page": page}
            if from_ts:
                params["from"] = from_ts
            if to_ts:
                params["to"] = to_ts

            data = self._get("user.getRecentTracks", **params)
            page_tracks = data["recenttracks"]["track"]

            # Skip currently playing track (has no timestamp)
            page_tracks = [t for t in page_tracks if "date" in t]
            tracks.extend(page_tracks)

            attr = data["recenttracks"]["@attr"]
            if int(attr["page"]) >= int(attr["totalPages"]):
                break

            page += 1
            time.sleep(0.25)  # respect rate limit

        return tracks

    def get_top_artists(self, username: str, period: str = "overall", limit: int = 50) -> list[dict]:
        """Fetch top artists for a user over a given period.

        period: overall | 7day | 1month | 3month | 6month | 12month
        """
        data = self._get("user.getTopArtists", user=username, period=period, limit=limit)
        return data["topartists"]["artist"]

    def get_top_tracks(self, username: str, period: str = "overall", limit: int = 50) -> list[dict]:
        """Fetch top tracks for a user over a given period.

        period: overall | 7day | 1month | 3month | 6month | 12month
        """
        data = self._get("user.getTopTracks", user=username, period=period, limit=limit)
        return data["toptracks"]["track"]

    def get_top_albums(self, username: str, period: str = "overall", limit: int = 50) -> list[dict]:
        """Fetch top albums for a user over a given period.

        period: overall | 7day | 1month | 3month | 6month | 12month
        """
        data = self._get("user.getTopAlbums", user=username, period=period, limit=limit)
        return data["topalbums"]["album"]

    def get_user_info(self, username: str) -> dict:
        data = self._get("user.getInfo", user=username)
        return data["user"]

    def get_weekly_chart_list(self, username: str) -> list[dict]:
        """Return all available weekly chart periods for a user.

        Useful for fetching historical data week by week.
        """
        data = self._get("user.getWeeklyChartList", user=username)
        return data["weeklychartlist"]["chart"]

    def get_track_tags(self, artist: str, track: str, limit: int = 5) -> list[str]:
        """Return top tags for a specific track, filtered by the same
        quality rule as get_artist_tags (count >= mean). Returns [] on error.
        """
        try:
            data = self._get("track.getTopTags", artist=artist, track=track)
            tags = data["toptags"]["tag"]
            if isinstance(tags, dict):
                tags = [tags]
            counts = [int(t["count"]) for t in tags]
            if not counts:
                return []
            mean_count = sum(counts) / len(counts)
            filtered = [t["name"].lower() for t in tags if int(t["count"]) >= mean_count]
            return filtered[:limit]
        except Exception:
            return []

    def get_artist_tags(self, artist: str, limit: int = 5) -> list[str]:
        """Return top genre tags for an artist, filtered by quality.

        Only tags with count >= mean count of all returned tags are kept,
        which removes personal/obscure tags added by few users.
        Returns at most `limit` tags. Returns [] on any API error.
        """
        try:
            data = self._get("artist.getTopTags", artist=artist)
            tags = data["toptags"]["tag"]
            counts = [int(t["count"]) for t in tags]
            if not counts:
                return []
            mean_count = sum(counts) / len(counts)
            filtered = [t["name"].lower() for t in tags if int(t["count"]) >= mean_count]
            return filtered[:limit]
        except Exception:
            return []
