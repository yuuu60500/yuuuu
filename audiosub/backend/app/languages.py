"""Language registry.

Languages are data, not code paths: adding Spanish, French, etc. means adding
an entry here. `asr_code` is what the speech model expects (ASR works on the
spoken language, so pt-PT and pt-BR both map to "pt"); `code` is the locale we
store and translate into, which is where the PT-PT vs PT-BR distinction lives.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native_name: str
    asr_code: str
    can_be_source: bool = True
    can_be_target: bool = True
    # Extra instructions appended to the translation prompt for this target.
    translation_notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


LANGUAGES: dict[str, Language] = {
    lang.code: lang
    for lang in [
        Language(
            code="zh",
            name="Chinese",
            native_name="中文",
            asr_code="zh",
            translation_notes=(
                "Write in Simplified Chinese (简体中文) with Chinese punctuation. "
                "Keep it natural and concise, as a professional subtitler would."
            ),
            aliases=("zh-cn", "zh-hans", "chinese", "mandarin"),
        ),
        Language(
            code="en",
            name="English",
            native_name="English",
            asr_code="en",
            translation_notes="Write natural, idiomatic English.",
            aliases=("en-us", "en-gb", "english"),
        ),
        Language(
            code="pt-PT",
            name="Portuguese (Portugal)",
            native_name="Português de Portugal",
            asr_code="pt",
            translation_notes=(
                "Write in European Portuguese as spoken and written in Portugal "
                "(português de Portugal, pós-Acordo Ortográfico de 1990). Never use "
                "Brazilian Portuguese. In particular:\n"
                "- Use 'estar a + infinitivo' (\"estou a fazer\"), never the gerund "
                "progressive (\"estou fazendo\").\n"
                "- Use European vocabulary: equipa (not time), ecrã (not tela), "
                "telemóvel (not celular), autocarro (not ônibus), comboio (not trem), "
                "casa de banho (not banheiro), pequeno-almoço (not café da manhã), "
                "facto (not fato), receção, ação, direção.\n"
                "- Use European clitic placement (\"diga-me\", \"não me diga\") and "
                "polite forms typical of Portugal (\"o senhor\", \"a senhora\", "
                "\"consigo\"); avoid Brazilian \"você\" where it would sound unnatural.\n"
                "- Use European spelling and accents (e.g. \"económico\", "
                "\"género\", \"António\")."
            ),
            aliases=("pt", "pt-pt", "portuguese", "português"),
        ),
    ]
}

AUTO_DETECT = "auto"


def normalize_language(code: str | None) -> str | None:
    """Map an arbitrary code (e.g. ASR output "pt", "zh-CN") to a registry code."""
    if not code:
        return None
    if code == AUTO_DETECT:
        return AUTO_DETECT
    lowered = code.strip().lower()
    for lang in LANGUAGES.values():
        if lowered == lang.code.lower() or lowered in lang.aliases:
            return lang.code
    for lang in LANGUAGES.values():
        if lowered.split("-")[0] == lang.asr_code:
            return lang.code
    return None


def get_language(code: str | None) -> Language | None:
    normalized = normalize_language(code)
    return LANGUAGES.get(normalized) if normalized else None


def same_language(a: str | None, b: str | None) -> bool:
    la, lb = get_language(a), get_language(b)
    return la is not None and la == lb


def language_name(code: str | None) -> str:
    lang = get_language(code)
    return lang.name if lang else (code or "Unknown")
