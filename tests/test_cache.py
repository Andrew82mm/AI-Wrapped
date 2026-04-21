import json
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
