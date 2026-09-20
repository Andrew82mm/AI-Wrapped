"""Narrative generator for any OpenAI-compatible chat-completions API.

We POST to a `/chat/completions` endpoint directly via `requests` — no SDK.
Works with any OpenAI-compatible provider (OpenRouter, OpenAI, Together,
Groq, a local Ollama/llama.cpp/vLLM server, …) by pointing `LLM_BASE_URL`
at it. Configuration (all overridable via the function parameters):

  LLM_BASE_URL   base URL, e.g. https://openrouter.ai/api/v1 (default),
                 https://api.openai.com/v1, http://localhost:11434/v1
  LLM_API_KEY    bearer token (falls back to OPENROUTER_API_KEY / OPENAI_API_KEY)
  LLM_MODEL      model id (falls back to OPENROUTER_MODEL, then DEFAULT_MODEL)

Flow: build system + user prompt, POST, parse JSON body, validate names.
On validation failure we retry once, appending a hint to the system prompt.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import requests

from .context import build_allowed_names, build_context
from .prompt import system_prompt, user_prompt
from .verify import VerifyResult, verify_names


DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _resolve_api_key(explicit: str | None) -> str | None:
    """API key from the explicit arg, then common env vars (in priority order)."""
    return (
        explicit
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _chat_completions_url(base_url: str) -> str:
    """Build the /chat/completions endpoint from a base URL."""
    return base_url.rstrip("/") + "/chat/completions"


@dataclass
class Narrative:
    sections: list[dict]  # [{title, body}, ...]
    artists_mentioned: list[str]
    verify: VerifyResult
    raw: str  # the full model response string, for debugging

    def as_text(self) -> str:
        """Render sections as plain markdown for CLI display."""
        parts: list[str] = []
        for s in self.sections:
            parts.append(f"## {s.get('title', '').strip()}")
            parts.append(s.get("body", "").strip())
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"


class NarrativeError(RuntimeError):
    """Raised when the model response cannot be parsed or fails validation twice."""


def _extract_json(raw: str) -> dict:
    """Model sometimes wraps JSON in ```json fences even when told not to."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    return json.loads(s)


def _call_chat_completions(
    system: str,
    user: str,
    *,
    url: str,
    api_key: str,
    model: str,
    temperature: float,
    timeout: int,
    rate_limit_retries: int = 4,
    rate_limit_backoff: float = 15.0,
) -> str:
    """POST to an OpenAI-compatible /chat/completions endpoint and return the
    assistant message content.

    Retries up to `rate_limit_retries` times on 429 with exponential backoff,
    since free-tier models are often temporarily rate-limited upstream.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    for attempt in range(rate_limit_retries + 1):
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 429 and attempt < rate_limit_retries:
            wait = rate_limit_backoff * (2 ** attempt)
            print(f"[narrative] rate-limited (429), retrying in {wait:.0f}s "
                  f"(attempt {attempt + 1}/{rate_limit_retries})...")
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            raise NarrativeError(
                f"LLM API {resp.status_code}: {resp.text[:500]}"
            )
        break
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise NarrativeError(f"Malformed LLM API response: {data!r}") from e


def generate_narrative(
    payload: dict,
    *,
    voice: str = "a",
    lang: str = "ru",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.8,
    timeout: int = 300,
    max_retries: int = 1,
) -> Narrative:
    """Generate a Wrapped narrative via any OpenAI-compatible chat API.

    Config precedence: explicit arg → env var → default. See the module
    docstring for the env vars (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL).

    `max_retries=1` means: one initial attempt, plus up to one retry if the
    first output mentions artists outside the whitelist. After the retry the
    result is returned regardless — with `verify.ok=False` if still invalid.
    """
    api_key = _resolve_api_key(api_key)
    if not api_key:
        raise NarrativeError(
            "No LLM API key set — set LLM_API_KEY (or OPENROUTER_API_KEY) in "
            ".env, or pass api_key=."
        )
    base_url = base_url or os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL
    model = model or os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
    url = _chat_completions_url(base_url)

    context = build_context(payload)
    allowed = build_allowed_names(context.get("features", {}))

    system = system_prompt(voice, lang)
    user = user_prompt(context, lang)

    last_raw = ""
    last_result: VerifyResult | None = None
    last_parsed: dict = {}

    for attempt in range(max_retries + 1):
        retry_system = system
        if attempt > 0 and last_result is not None:
            retry_system = system + "\n\nRETRY NOTE: " + last_result.error_hint()

        last_raw = _call_chat_completions(
            retry_system, user,
            url=url, api_key=api_key, model=model,
            temperature=temperature, timeout=timeout,
        )
        try:
            last_parsed = _extract_json(last_raw)
        except json.JSONDecodeError as e:
            if attempt >= max_retries:
                raise NarrativeError(
                    f"Model returned non-JSON on final attempt: {e}. "
                    f"Raw: {last_raw[:500]}"
                ) from e
            continue

        mentioned = last_parsed.get("artists_mentioned", []) or []
        last_result = verify_names(mentioned, allowed)
        if last_result.ok:
            break

    return Narrative(
        sections=last_parsed.get("sections", []) or [],
        artists_mentioned=last_parsed.get("artists_mentioned", []) or [],
        verify=last_result or VerifyResult(ok=True, offenders=[]),
        raw=last_raw,
    )
