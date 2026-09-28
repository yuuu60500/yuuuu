from .base import TranslationProvider, TranslationRequest


class MockTranslationProvider(TranslationProvider):
    """Tags each line with the target language. For development and tests."""

    name = "mock"

    def translate_batch(self, request: TranslationRequest) -> dict[str, str]:
        glossary = {g.term: g.translation for g in request.glossary}
        out = {}
        for item in request.items:
            text = item.text
            for term, repl in glossary.items():
                text = text.replace(term, repl)
            out[item.id] = f"[{request.target_language}] {text}"
        return out
