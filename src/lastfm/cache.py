import json
import logging
import os
import tempfile
from datetime import datetime, timedelta


CACHE_DIR = os.path.join(os.path.dirname(__file__), "../../data")

_log = logging.getLogger(__name__)


def _cache_path(name: str, cache_dir: str | None = None) -> str:
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

    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    fetched_at = datetime.fromisoformat(payload["fetched_at"])
    if datetime.now() - fetched_at > timedelta(hours=max_age_hours):
        return None

    return payload["data"]


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
