"""AI draft generation — outreach subject/body via an OpenAI-compatible API.

The default endpoint is NVIDIA NIM (build.nvidia.com) with the DeepSeek
V4 Flash model (``deepseek-ai/deepseek-v4-flash``). One call per contact;
the model returns a JSON object with ``subject`` and ``body``. Any API,
network or parsing failure raises ``AIError`` so the CLI can abort cleanly.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from linkdogger.config.settings import Settings
from linkdogger.errors import AIError
from linkdogger.mail.contacts import Contact

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a cold-outreach email writer for a professional networking "
    "tool. Write a short, warm, professional email. Rules: 2-4 short "
    "sentences in the body; a clear, low-pressure ask; no buzzwords; no "
    "placeholders, links or claims you cannot verify; the sender signs "
    "with their own name. Respond with valid JSON only, shaped exactly "
    '{"subject": "...", "body": "..."}.'
)


@dataclass(frozen=True)
class EmailDraft:
    """AI-generated subject and body for one recipient."""

    subject: str
    body: str


class DraftGenerator:
    """Generates personalized email drafts through a chat completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._client = httpx.Client(
            base_url=self._settings.ai_base_url,
            timeout=self._settings.ai_timeout_seconds,
            headers={"Authorization": f"Bearer {self._settings.ai_api_key or ''}"},
        )

    def generate(self, contact: Contact) -> EmailDraft:
        """Generate one personalized draft for ``contact``."""
        if not self._settings.ai_api_key:
            raise AIError("LINKDOGGER_AI_API_KEY is not set")
        payload = {
            "model": self._settings.ai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(contact, self._settings)},
            ],
            "temperature": 0.7,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            return _parse_draft(response.json())
        except httpx.HTTPStatusError as exc:
            raise AIError(f"AI API returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise AIError(f"AI API request failed: {exc}") from exc


def generate_drafts(
    contacts: list[Contact],
    generator: DraftGenerator | None = None,
) -> list[EmailDraft]:
    """Generate one draft per contact with a shared generator."""
    gen = generator or DraftGenerator()
    return [gen.generate(contact) for contact in contacts]


def _user_prompt(contact: Contact, settings: Settings) -> str:
    bits = [f"Recipient name: {contact.name or 'unknown'}"]
    if contact.company:
        bits.append(f"Recipient company: {contact.company}")
    if contact.position:
        bits.append(f"Recipient position: {contact.position}")
    bits.append(f"Sender name: {settings.smtp_from_name or 'the sender'}")
    bits.append("Write the subject line and body of the email to this recipient.")
    return "\n".join(bits)


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
