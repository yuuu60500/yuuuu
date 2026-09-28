import json
import logging

import anthropic

from ...config import get_settings
from .base import TranslationError, TranslationProvider, TranslationRequest
from .prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT, build_user_prompt

log = logging.getLogger(__name__)


class ClaudeTranslationProvider(TranslationProvider):
    name = "claude"

    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None):
        settings = get_settings()
        if client is None:
            if not settings.anthropic_api_key:
                raise TranslationError(
                    "ANTHROPIC_API_KEY is not set. Add it to backend/.env and restart the backend."
                )
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.client = client
        self.model = model or settings.translation_model

    def translate_batch(self, request: TranslationRequest) -> dict[str, str]:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
                },
                # If a safety classifier declines, re-run on Anthropic's recommended
                # fallback model instead of failing the batch.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                # The system prompt is identical for every batch; cache it.
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": build_user_prompt(request)}],
            )
        except anthropic.RateLimitError as exc:
            raise TranslationError("Translation service rate limit reached; retry shortly.") from exc
        except anthropic.AuthenticationError as exc:
            raise TranslationError("Translation service rejected the API key.") from exc
        except anthropic.APIStatusError as exc:
            raise TranslationError(f"Translation service error ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise TranslationError("Could not reach the translation service.") from exc

        if response.stop_reason == "refusal":
            raise TranslationError("The translation model declined this batch.")
        if response.stop_reason == "max_tokens":
            raise TranslationError("Translation output was truncated.")

        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TranslationError("Translation model returned invalid JSON.") from exc

        wanted = {item.id for item in request.items}
        return {
            str(t["id"]): t["text"].strip()
            for t in data.get("translations", [])
            if str(t.get("id")) in wanted
        }
