from fastapi import APIRouter

from ..config import get_settings
from ..domains import DOMAINS
from ..languages import LANGUAGES
from ..services.media import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta")
def meta():
    """Options for the UI, so languages/domains are never hard-coded in the frontend."""
    return {
        "source_languages": [{"code": "auto", "name": "Auto Detect"}]
        + [{"code": l.code, "name": l.name, "native_name": l.native_name}
           for l in LANGUAGES.values() if l.can_be_source],
        "target_languages": [
            {"code": l.code, "name": l.name, "native_name": l.native_name}
            for l in LANGUAGES.values() if l.can_be_target
        ],
        "domains": [{"code": d.code, "name": d.name} for d in DOMAINS.values()],
        "subtitle_modes": [
            {"code": "original", "name": "Original Only"},
            {"code": "translation", "name": "Translation Only"},
            {"code": "bilingual", "name": "Bilingual"},
        ],
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "max_upload_mb": get_settings().max_upload_mb,
    }


@router.get("/health")
def health():
    s = get_settings()
    return {"status": "ok", "asr_provider": s.asr_provider, "translation_provider": s.translation_provider}
