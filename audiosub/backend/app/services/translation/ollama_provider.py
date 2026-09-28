"""Offline translation with a local model served by Ollama.

Runs entirely on the user's machine: no API key, no per-use cost. Uses the
same prompt as the Claude provider (PT-PT rules, domain, glossary), but small
local models follow it less reliably, so quality is lower.
"""

import json

import httpx

from ...config import get_settings
from .base import TranslationError, TranslationProvider, TranslationRequest
from .prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT, build_user_prompt


class OllamaTranslationProvider(TranslationProvider):
    name = "ollama"

    def __init__(self, client: httpx.Client | None = None, model: str | None = None):
        settings = get_settings()
        self.base_url = settings.ollama_url.rstrip("/")
        self.model = model or settings.ollama_model
        self.client = client or httpx.Client(timeout=settings.ollama_timeout)

    def translate_batch(self, request: TranslationRequest) -> dict[str, str]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": OUTPUT_SCHEMA,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }
        try:
            resp = self.client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.ConnectError as exc:
            raise TranslationError(
                f"Cannot reach Ollama at {self.base_url}. Is Ollama installed and running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise TranslationError(
                "The local model took too long. Try a smaller model or a lower "
                "TRANSLATION_BATCH_SIZE."
            ) from exc
        if resp.status_code == 404:
            raise TranslationError(
                f"Model '{self.model}' is not installed. Run: ollama pull {self.model}"
            )
        if resp.status_code != 200:
            raise TranslationError(f"Ollama error ({resp.status_code}): {resp.text[:300]}")

        content = (resp.json().get("message") or {}).get("content", "")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise TranslationError("The local model returned invalid JSON.") from exc

        wanted = {item.id for item in request.items}
        out = {}
        for t in data.get("translations", []) if isinstance(data, dict) else []:
            key = str(t.get("id", "")).strip()
            text = t.get("text")
            if key in wanted and isinstance(text, str) and text.strip():
                out[key] = text.strip()
        return out
