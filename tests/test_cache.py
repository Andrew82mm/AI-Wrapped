import json
import threading
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, mock_open

import src.lastfm.cache as cache_module


FRESH_PAYLOAD = json.dumps({
    "fetched_at": datetime.now().isoformat(),
    "data": {"key": "value"},
})

STALE_PAYLOAD = json.dumps({
    "fetched_at": (datetime.now() - timedelta(hours=10)).isoformat(),
    "data": {"key": "old"},
})


class TestCacheLoad:
    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        assert cache_module.load("nonexistent") is None

    def test_returns_data_when_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        (tmp_path / "test.json").write_text(FRESH_PAYLOAD)
        result = cache_module.load("test", max_age_hours=6)
        assert result == {"key": "value"}

    def test_returns_none_when_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        (tmp_path / "test.json").write_text(STALE_PAYLOAD)
        assert cache_module.load("test", max_age_hours=6) is None


class TestCacheSave:
    def test_saves_file_with_fetched_at(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        cache_module.save("test", [1, 2, 3])
        payload = json.loads((tmp_path / "test.json").read_text())
        assert "fetched_at" in payload
        assert payload["data"] == [1, 2, 3]

    def test_save_leaves_no_tmp_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        cache_module.save("test", {"x": 1})
        assert not (tmp_path / "test.json.tmp").exists()

    def test_save_is_atomic_original_survives_exception(self, tmp_path, monkeypatch):
        """If json.dump raises mid-write, the original cache file must not be corrupted."""
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        cache_module.save("test", {"original": True})

        original_text = (tmp_path / "test.json").read_text()

        with patch("src.lastfm.cache.json.dump", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                cache_module.save("test", {"corrupted": True})

        # Original file must be intact — tmp was never renamed over it.
        assert (tmp_path / "test.json").read_text() == original_text

    def test_concurrent_writes_produce_valid_json(self, tmp_path, monkeypatch):
        """Two threads writing the same cache key simultaneously must not corrupt the file."""
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        errors = []

        def writer(value):
            try:
                cache_module.save("shared", {"v": value, "padding": "x" * 4096})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # Final file must be valid JSON.
        payload = json.loads((tmp_path / "shared.json").read_text())
        assert "data" in payload


class TestFetchOrUpdate:
    def test_calls_fetch_fn_when_no_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        fetch_fn = lambda: {"fresh": True}
        result = cache_module.fetch_or_update("test", fetch_fn)
        assert result == {"fresh": True}

    def test_does_not_call_fetch_fn_when_cache_is_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        (tmp_path / "test.json").write_text(FRESH_PAYLOAD)
        called = []
        cache_module.fetch_or_update("test", lambda: called.append(1) or {})
        assert called == []

    def test_calls_fetch_fn_when_cache_is_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        (tmp_path / "test.json").write_text(STALE_PAYLOAD)
        result = cache_module.fetch_or_update("test", lambda: {"refreshed": True}, max_age_hours=6)
        assert result == {"refreshed": True}

    def test_saves_result_after_fetch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
        cache_module.fetch_or_update("test", lambda: {"saved": True})
        payload = json.loads((tmp_path / "test.json").read_text())
        assert payload["data"] == {"saved": True}


# --- cache_dir parameter (per-user isolation) --------------------------------

class TestCacheDirParam:
    """Ensure that passing cache_dir routes files to that directory, not CACHE_DIR."""

    def test_load_reads_from_cache_dir(self, tmp_path):
        user_dir = tmp_path / "alice"
        user_dir.mkdir()
        (user_dir / "scrobbles.json").write_text(FRESH_PAYLOAD)
        result = cache_module.load("scrobbles", cache_dir=str(user_dir))
        assert result == {"key": "value"}

    def test_load_does_not_read_from_global_cache_dir(self, tmp_path, monkeypatch):
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        user_dir = tmp_path / "alice"
        user_dir.mkdir()
        # File exists in global, not in user dir
        (global_dir / "scrobbles.json").write_text(FRESH_PAYLOAD)
        monkeypatch.setattr(cache_module, "CACHE_DIR", str(global_dir))
        result = cache_module.load("scrobbles", cache_dir=str(user_dir))
        assert result is None

    def test_save_writes_to_cache_dir(self, tmp_path):
        user_dir = tmp_path / "bob"
        user_dir.mkdir()
        cache_module.save("tracks", [1, 2, 3], cache_dir=str(user_dir))
        assert (user_dir / "tracks.json").exists()
        payload = json.loads((user_dir / "tracks.json").read_text())
        assert payload["data"] == [1, 2, 3]

    def test_save_creates_cache_dir_if_missing(self, tmp_path):
        user_dir = tmp_path / "charlie" / "nested"
        cache_module.save("info", {"ok": True}, cache_dir=str(user_dir))
        assert (user_dir / "info.json").exists()

    def test_fetch_or_update_uses_cache_dir(self, tmp_path):
        user_dir = tmp_path / "dave"
        user_dir.mkdir()
        (user_dir / "top.json").write_text(FRESH_PAYLOAD)
        called = []
        cache_module.fetch_or_update("top", lambda: called.append(1) or {},
                                     cache_dir=str(user_dir))
        assert called == [], "Should have hit cache, not called fetch_fn"

    def test_two_users_isolated(self, tmp_path):
        dir_a = tmp_path / "userA"
        dir_b = tmp_path / "userB"
        dir_a.mkdir(); dir_b.mkdir()
        cache_module.save("info", {"user": "A"}, cache_dir=str(dir_a))
        cache_module.save("info", {"user": "B"}, cache_dir=str(dir_b))
        assert cache_module.load("info", cache_dir=str(dir_a)) == {"user": "A"}
        assert cache_module.load("info", cache_dir=str(dir_b)) == {"user": "B"}
