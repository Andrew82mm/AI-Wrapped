"""Unit tests for the narrative module — all offline (no OpenRouter calls)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.narrative.context import build_allowed_names, build_context
from src.narrative.prompt import system_prompt, user_prompt, VOICES, LANGS
from src.narrative.verify import verify_names
from src.narrative.generate import (
    Narrative,
    NarrativeError,
    _extract_json,
    generate_narrative,
)


SAMPLE_FEATURES = {
    "binge_weeks": {
        "binges": [
            {"week": "2025-W25", "top_artist": "Kanye West", "tracks": 1230},
            {"week": "2025-W22", "top_artist": "Radiohead", "tracks": 851},
        ]
    },
    "artist_loyalty": {
        "veterans": [{"artist": "Aphex Twin", "active_weeks": 65}],
        "newcomers": [{"artist": "Laufey", "active_weeks": 1}],
    },
    "listening_style": {
        "obsession_track": {"artist": "Crystal Castles", "track": "Crimewave"}
    },
    "guilty_pleasures": {
        "guilty_pleasures": [{"artist": "Mitski", "plays": 7}]
    },
    "artifacts": {
        "longest_session": {"top_artists": ["1000 Eyes"]}
    },
    "musical_roommates": {
        "seeds": ["Mac DeMarco"],
        "recommendations": [
            {"artist": "Thom Yorke", "suggested_by": ["Radiohead"]}
        ],
    },
}


# --- context -----------------------------------------------------------------

def test_build_allowed_names_collects_all_sources():
    allowed = build_allowed_names(SAMPLE_FEATURES)
    for name in [
        "Kanye West", "Radiohead", "Aphex Twin", "Laufey",
        "Crystal Castles", "Mitski", "1000 Eyes", "Mac DeMarco", "Thom Yorke",
    ]:
        assert name in allowed["artists"], f"missing artist {name!r}"
    assert "Crimewave" in allowed["tracks"]


def test_build_allowed_names_handles_empty_features():
    assert build_allowed_names({}) == {"artists": set(), "tracks": set()}


def test_build_context_strips_metadata_timestamp():
    payload = {"user": "u", "period": "2025", "features": {"x": 1}, "generated_at": "..."}
    ctx = build_context(payload)
    assert ctx == {"user": "u", "period": "2025", "features": {"x": 1}}


# --- prompt ------------------------------------------------------------------

@pytest.mark.parametrize("voice", VOICES)
@pytest.mark.parametrize("lang", LANGS)
def test_system_prompt_covers_all_voice_lang_combos(voice, lang):
    p = system_prompt(voice, lang)
    assert "sections" in p  # output contract always mentioned
    assert "artists_mentioned" in p


def test_system_prompt_rejects_unknown_voice():
    with pytest.raises(ValueError):
        system_prompt("z", "ru")


def test_system_prompt_rejects_unknown_lang():
    with pytest.raises(ValueError):
        system_prompt("a", "fr")


def test_user_prompt_embeds_context_as_json():
    ctx = {"user": "u", "features": {"k": "v"}}
    out = user_prompt(ctx, "ru")
    assert "\"user\": \"u\"" in out
    assert "\"k\": \"v\"" in out


# --- verify ------------------------------------------------------------------

def test_verify_ok_when_all_names_whitelisted():
    allowed = {"artists": {"Radiohead", "Aphex Twin"}, "tracks": set()}
    r = verify_names(["Radiohead", "Aphex Twin"], allowed)
    assert r.ok and r.offenders == []


def test_verify_case_insensitive():
    allowed = {"artists": {"Radiohead"}, "tracks": set()}
    r = verify_names(["radiohead", "  RADIOHEAD  "], allowed)
    assert r.ok


def test_verify_flags_unknown_artist():
    allowed = {"artists": {"Radiohead"}, "tracks": set()}
    r = verify_names(["Radiohead", "The Beatles"], allowed)
    assert not r.ok
    assert r.offenders == ["The Beatles"]


def test_verify_accepts_track_names_in_mentioned_list():
    allowed = {"artists": {"Crystal Castles"}, "tracks": {"Crimewave"}}
    r = verify_names(["Crimewave"], allowed)
    assert r.ok


def test_verify_empty_mentioned_is_ok():
    allowed = {"artists": set(), "tracks": set()}
    assert verify_names([], allowed).ok


def test_error_hint_lists_offenders():
    allowed = {"artists": set(), "tracks": set()}
    hint = verify_names(["Ghost", "Phantom"], allowed).error_hint()
    assert "'Ghost'" in hint and "'Phantom'" in hint


# --- generate: json extraction ----------------------------------------------

def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_fenced_no_lang():
    assert _extract_json('```\n{"a": 1}\n```') == {"a": 1}


# --- generate: end-to-end with mocked HTTP ----------------------------------

def _mk_response(payload_dict: dict, status: int = 200):
    class R:
        status_code = status
        text = json.dumps(payload_dict)
        def json(self):  # noqa: D401
            return payload_dict
    return R()


def _valid_model_output() -> str:
    return json.dumps({
        "sections": [
            {"title": "Год Radiohead", "body": "..."},
        ],
        "artists_mentioned": ["Radiohead", "Aphex Twin"],
    })


def test_generate_narrative_happy_path():
    api_resp = _mk_response({
        "choices": [{"message": {"content": _valid_model_output()}}]
    })
    payload = {"user": "u", "features": SAMPLE_FEATURES}
    with patch("src.narrative.generate.requests.post", return_value=api_resp) as post:
        narr = generate_narrative(payload, api_key="k")
    assert narr.verify.ok
    assert len(narr.sections) == 1
    assert "Radiohead" in narr.artists_mentioned
    post.assert_called_once()


def test_generate_narrative_retries_once_on_hallucination():
    bad = json.dumps({
        "sections": [{"title": "t", "body": "b"}],
        "artists_mentioned": ["Made Up Band"],
    })
    good = _valid_model_output()
    responses = [
        _mk_response({"choices": [{"message": {"content": bad}}]}),
        _mk_response({"choices": [{"message": {"content": good}}]}),
    ]
    payload = {"user": "u", "features": SAMPLE_FEATURES}
    with patch("src.narrative.generate.requests.post", side_effect=responses) as post:
        narr = generate_narrative(payload, api_key="k")
    assert post.call_count == 2
    assert narr.verify.ok


def test_generate_narrative_returns_unverified_after_max_retries():
    bad = json.dumps({
        "sections": [{"title": "t", "body": "b"}],
        "artists_mentioned": ["Made Up Band"],
    })
    responses = [
        _mk_response({"choices": [{"message": {"content": bad}}]}),
        _mk_response({"choices": [{"message": {"content": bad}}]}),
    ]
    payload = {"user": "u", "features": SAMPLE_FEATURES}
    with patch("src.narrative.generate.requests.post", side_effect=responses):
        narr = generate_narrative(payload, api_key="k")
    assert not narr.verify.ok
    assert narr.verify.offenders == ["Made Up Band"]


def test_generate_narrative_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(NarrativeError, match="OPENROUTER_API_KEY"):
        generate_narrative({"features": {}})


def test_generate_narrative_raises_on_http_error():
    api_resp = _mk_response({"error": "bad"}, status=500)
    with patch("src.narrative.generate.requests.post", return_value=api_resp):
        with pytest.raises(NarrativeError, match="500"):
            generate_narrative({"features": SAMPLE_FEATURES}, api_key="k")


def test_narrative_as_text_renders_sections_as_markdown():
    n = Narrative(
        sections=[{"title": "T1", "body": "B1"}, {"title": "T2", "body": "B2"}],
        artists_mentioned=[],
        verify=verify_names([], {"artists": set(), "tracks": set()}),
        raw="",
    )
    text = n.as_text()
    assert "## T1" in text and "B1" in text
    assert "## T2" in text and "B2" in text
