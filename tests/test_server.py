"""Tests for frontend/server.py API endpoints.

All tests are offline — the pipeline thread is never actually started.
We manipulate _jobs directly to simulate job lifecycle states.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from frontend.server import app, _jobs, _jobs_lock


client = TestClient(app)


def _inject_job(job_id: str, **kw):
    """Insert a job dict directly into the in-memory store."""
    defaults = {"status": "running", "step": 0, "step_label": "Starting…",
                "total": 5, "result": None, "error": None}
    with _jobs_lock:
        _jobs[job_id] = {**defaults, **kw}


def _remove_job(job_id: str):
    with _jobs_lock:
        _jobs.pop(job_id, None)


# --- POST /api/generate -----------------------------------------------------

class TestGenerate:
    def test_returns_job_id(self):
        with patch("frontend.server.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post("/api/generate", json={"username": "testuser"})
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert len(data["job_id"]) == 36  # UUID

    def test_empty_username_rejected(self):
        resp = client.post("/api/generate", json={"username": "   "})
        assert resp.status_code == 400

    def test_missing_username_field_rejected(self):
        resp = client.post("/api/generate", json={})
        assert resp.status_code == 422  # Pydantic validation

    def test_default_period_is_last_90(self):
        with patch("frontend.server.threading.Thread") as mock_thread:
            captured = {}
            def fake_start():
                pass
            inst = mock_thread.return_value
            inst.start = fake_start
            mock_thread.side_effect = lambda target, args, daemon: inst

            resp = client.post("/api/generate", json={"username": "u"})
        assert resp.status_code == 200

    def test_job_created_with_running_status(self):
        with patch("frontend.server.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post("/api/generate", json={"username": "u2"})
        job_id = resp.json()["job_id"]
        with _jobs_lock:
            job = _jobs.get(job_id)
        assert job is not None
        assert job["status"] == "running"
        _remove_job(job_id)

    def test_strips_username_whitespace(self):
        with patch("frontend.server.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post("/api/generate", json={"username": "  myuser  "})
        assert resp.status_code == 200
        _remove_job(resp.json()["job_id"])


# --- GET /api/status/{job_id} -----------------------------------------------

class TestStatus:
    def setup_method(self):
        self.job_id = str(uuid.uuid4())

    def teardown_method(self):
        _remove_job(self.job_id)

    def test_unknown_job_returns_404(self):
        resp = client.get(f"/api/status/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_running_job_returns_fields(self):
        _inject_job(self.job_id, status="running", step=2, step_label="Enriching…", total=5)
        resp = client.get(f"/api/status/{self.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["step"] == 2
        assert data["step_label"] == "Enriching…"
        assert data["total"] == 5
        assert data["error"] is None

    def test_done_job_returns_done_status(self):
        _inject_job(self.job_id, status="done", step=5, step_label="Done", result={"x": 1})
        resp = client.get(f"/api/status/{self.job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    def test_error_job_returns_error_message(self):
        _inject_job(self.job_id, status="error", error="API key missing")
        resp = client.get(f"/api/status/{self.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "API key missing" in data["error"]


# --- GET /api/result/{job_id} -----------------------------------------------

class TestResult:
    def setup_method(self):
        self.job_id = str(uuid.uuid4())

    def teardown_method(self):
        _remove_job(self.job_id)

    def test_unknown_job_returns_404(self):
        resp = client.get(f"/api/result/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_not_done_returns_400(self):
        _inject_job(self.job_id, status="running")
        resp = client.get(f"/api/result/{self.job_id}")
        assert resp.status_code == 400

    def test_error_status_returns_400(self):
        _inject_job(self.job_id, status="error", error="oops")
        resp = client.get(f"/api/result/{self.job_id}")
        assert resp.status_code == 400

    def test_done_returns_result_json(self):
        result_data = {"user": "alice", "scrobbles": 1234}
        _inject_job(self.job_id, status="done", result=result_data)
        resp = client.get(f"/api/result/{self.job_id}")
        assert resp.status_code == 200
        assert resp.json() == result_data

    def test_result_content_type_is_json(self):
        _inject_job(self.job_id, status="done", result={"ok": True})
        resp = client.get(f"/api/result/{self.job_id}")
        assert "application/json" in resp.headers["content-type"]


# --- GET / ------------------------------------------------------------------

class TestIndex:
    def test_index_serves_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert b"<!DOCTYPE html>" in resp.content or b"<html" in resp.content


# --- lifecycle integration --------------------------------------------------

class TestJobLifecycle:
    """Simulate the full generate → status → result flow without running the pipeline."""

    def test_full_flow(self):
        result_payload = {"user": "alice", "scrobbles": 99}

        def fake_pipeline(job_id, username, period, backend):
            _inject_job(job_id, status="done", step=5, step_label="Done",
                        result=result_payload)

        with patch("frontend.server._run_pipeline", side_effect=fake_pipeline):
            with patch("frontend.server.threading.Thread") as mock_thread:
                def fake_thread(target, args, daemon):
                    class T:
                        def start(self):
                            target(*args)
                    return T()
                mock_thread.side_effect = fake_thread
                gen_resp = client.post("/api/generate",
                                       json={"username": "alice", "period": "last:90"})

        assert gen_resp.status_code == 200
        job_id = gen_resp.json()["job_id"]

        status_resp = client.get(f"/api/status/{job_id}")
        assert status_resp.json()["status"] == "done"

        result_resp = client.get(f"/api/result/{job_id}")
        assert result_resp.status_code == 200
        assert result_resp.json()["user"] == "alice"

        _remove_job(job_id)
