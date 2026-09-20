import json
import logging
import os
import tempfile
from datetime import datetime, timedelta


CACHE_DIR = os.path.join(os.path.dirname(__file__), "../../data")

_log = logging.getLogger(__name__)


def _cache_path(name: str, cache_dir: str | None = None) -> str:
    # `name` must be a single filename component. Reject anything containing a
    # path separator or `..` so a crafted key (e.g. an artist literally named
    # "../../etc/x", or an unsanitised username used as a key prefix) cannot
    # escape the cache directory. This is the central choke point for every
    # caller, not just those that remember to call _safe().
    if name != os.path.basename(name) or name in ("", ".", "..") or os.sep in name \
            or (os.altsep and os.altsep in name):
        raise ValueError(f"unsafe cache name: {name!r}")
    dir_ = os.path.abspath(cache_dir or CACHE_DIR)
    os.makedirs(dir_, exist_ok=True)
    return os.path.join(dir_, f"{name}.json")


def save(name: str, data, cache_dir: str | None = None) -> None:
    """Serialize data to <cache_dir>/<name>.json with a fetched_at timestamp.

    Write is atomic: each call creates its own unique temp file via
    tempfile.mkstemp, then os.replace renames it into place.  Concurrent
    writers are safe — last writer wins, and readers always see a complete
    file (os.replace is atomic at the POSIX filesystem level).
    """
    payload = {
        "fetched_at": datetime.now().isoformat(),
        "data": data,
    }
    path = _cache_path(name, cache_dir)
    dir_path = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        os.unlink(tmp_path)
        raise
    os.replace(tmp_path, path)


def load(name: str, max_age_hours: int = 6, cache_dir: str | None = None):
    """Load cached data from <cache_dir>/<name>.json.

    Returns the data payload if the file exists and is younger than
    max_age_hours, otherwise returns None.
    """
    path = _cache_path(name, cache_dir)
    if not os.path.exists(path):
        return None

    # A corrupt/partial/hand-edited cache file must degrade to a cache miss,
    # not crash the whole pipeline (mirrors fetch_scrobbles_incremental's guard).
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        data = payload["data"]
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
        _log.warning("%s: ignoring unreadable cache file (%s)", name, exc)
        return None

    if datetime.now() - fetched_at > timedelta(hours=max_age_hours):
        return None

    return data


def fetch_scrobbles_incremental(
    name: str,
    fetch_fn,          # fetch_fn(from_ts=None) -> list[dict]
    cache_dir: str | None = None,
) -> list[dict]:
    """Fetch only new scrobbles and prepend them to the existing cache.

    On the very first call (no cache) fetches everything via fetch_fn().
    On subsequent calls loads the existing cache, finds the latest unix
    timestamp already stored, and fetches only tracks newer than that,
    then merges and saves. This keeps step-1 fast for returning users.

    There is no max-age check: an incremental fetch is always cheap (it only
    pulls tracks newer than what we have), so freshness is handled implicitly.
    """
    path = _cache_path(name, cache_dir)
    existing: list[dict] = []
    from_ts: int | None = None

    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            existing = payload.get("data", [])
            # find the most recent timestamp already cached
            timestamps = [int(t["date"]["uts"]) for t in existing if "date" in t]
            if timestamps:
                from_ts = max(timestamps) + 1
        except Exception:
            existing = []

    new_tracks = fetch_fn(from_ts=from_ts)

    if new_tracks or not existing:
        merged = new_tracks + existing
        save(name, merged, cache_dir)
        return merged

    # nothing new — touch the cache timestamp so we don't keep re-checking
    save(name, existing, cache_dir)
    return existing


def fetch_or_update(name: str, fetch_fn, max_age_hours: int = 6, cache_dir: str | None = None):
    """Return cached data if fresh, otherwise fetch, save, and return.

    If cache is missing or older than max_age_hours, calls fetch_fn(),
    saves the result to disk, and returns it.

    Pass cache_dir to store data in a user-specific subdirectory instead
    of the default shared data/ folder.
    """
    cached = load(name, max_age_hours, cache_dir)
    if cached is not None:
        _log.debug("%s: using cached data", name)
        return cached

    _log.debug("%s: fetching from API...", name)
    data = fetch_fn()
    save(name, data, cache_dir)
    return data
