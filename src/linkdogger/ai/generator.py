"""AI draft generation — outreach subject/body via an OpenAI-compatible API.

The default endpoint is NVIDIA NIM (build.nvidia.com) with the DeepSeek
V4 Flash model (``deepseek-ai/deepseek-v4-flash``). A single call
produces one professional email template with ``{name}``, ``{company}``,
``{position}`` and ``{from_name}`` placeholders, which the sender layer
personalizes per recipient — one API call per batch, not per email.
Transient failures (rate limits, 5xx) are retried with backoff. Any
persistent failure raises ``AIError`` so the CLI can abort cleanly.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from linkdogger.config.settings import Settings
from linkdogger.errors import AIError

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0)
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 529)

SYSTEM_PROMPT = (
    "You are a professional cold-outreach email writer for a B2B "
    "networking tool. Write one concise, professional email template. "
    "Rules: warm and respectful; no buzzwords, links or claims you cannot "
    "verify; use only the allowed placeholders; end with a clear, "
    "low-pressure ask. Format the body like a real email: a greeting, "
    "one sentence about why you are reaching out, one or two sentences "
    "of value, a closing line, and a sign-off. Separate paragraphs with "
    "a blank line (use \\n\\n). Respond with valid JSON only, shaped "
    'exactly {"subject": "...", "body": "..."}.'
)

USER_PROMPT = (
    "Write the outreach email to a professional contact. Use these "
    "placeholders where natural so the email personalizes per recipient: "
    "{name}, {company}, {position} and {from_name} (the sender's name). "
    "Subject: short, under 9 words, no placeholder overuse. Body: open "
    "with 'Dear {name},', mention how you found the person, state the "
    "value and the ask, then close with 'Best regards,' followed by "
    "{from_name} on the next line. A recipient may have no company or "
    "position: phrase sentences so they still read naturally when a "
    "placeholder is missing (e.g. 'your work at {company}' instead of "
    "'your role as {position} at {company}')."
)


@dataclass(frozen=True)
class EmailDraft:
    """AI-generated subject and body template (with placeholders)."""

    subject: str
    body: str


class DraftGenerator:
    """Generates a personalized email template via a chat completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._client = httpx.Client(
            base_url=self._settings.ai_base_url,
            timeout=self._settings.ai_timeout_seconds,
            headers={"Authorization": f"Bearer {self._settings.ai_api_key or ''}"},
        )

    def generate_template(self) -> EmailDraft:
        """Generate one template used for every recipient in the batch."""
        if not self._settings.ai_api_key:
            raise AIError("LINKDOGGER_AI_API_KEY is not set")
        payload = {
            "model": self._settings.ai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ],
            "temperature": 0.7,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }
        return _parse_draft(self._post_with_retries(payload))

    def check(self) -> str:
        """Verify the endpoint is reachable and the API key works."""
        if not self._settings.ai_api_key:
            raise AIError("LINKDOGGER_AI_API_KEY is not set")
        try:
            with httpx.Client(
                base_url=self._settings.ai_base_url,
                timeout=10.0,
                headers={"Authorization": f"Bearer {self._settings.ai_api_key}"},
            ) as client:
                response = client.get("/models")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise AIError(f"endpoint returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AIError(f"endpoint request failed: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            return "ok"
        model_ids = [
            str(item.get("id", ""))
            for item in data["data"]
            if isinstance(item, dict) and item.get("id")
        ]
        if self._settings.ai_model not in model_ids:
            return (
                f"ok ({len(model_ids)} models) — configured model "
                f"'{self._settings.ai_model}' is not listed"
            )
        return f"ok ({len(model_ids)} models)"

    def _post_with_retries(self, payload: dict[str, object]) -> Any:
        last_exc: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in RETRYABLE_STATUS_CODES:
                    raise AIError(
                        f"AI API returned HTTP {exc.response.status_code}"
                    ) from exc
                last_exc = exc
            except httpx.HTTPError as exc:
                last_exc = exc
            if attempt < MAX_ATTEMPTS - 1:
                logger.warning(
                    "AI API attempt %d failed (%s); retrying in %.0fs",
                    attempt + 1,
                    last_exc,
                    RETRY_BACKOFF_SECONDS[attempt],
                )
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
        assert last_exc is not None
        raise AIError(
            f"AI API failed after {MAX_ATTEMPTS} attempts: {last_exc}"
        ) from last_exc


def _parse_draft(data: Any) -> EmailDraft:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("AI API returned an unexpected response shape") from exc
    parsed = _parse_content(content)
    if not isinstance(parsed, dict):
        raise AIError("AI response did not contain a valid subject/body JSON object")
    subject = parsed.get("subject")
    body = parsed.get("body")
    if not isinstance(subject, str) or not isinstance(body, str):
        raise AIError("AI response is missing 'subject' or 'body'")
    return EmailDraft(subject.strip(), body.strip())


def _parse_content(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from model output (raw, fenced, or in prose)."""
    candidates = [text, *re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)]
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
        except ValueError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None
