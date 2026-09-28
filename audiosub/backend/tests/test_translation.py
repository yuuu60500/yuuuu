from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.models import GlossaryTerm, Project, Segment
from app.services.translation import TranslationError, TranslationRequest
from app.services.translation.base import GlossaryEntry, TranslationItem, TranslationProvider
from app.services.translation.claude_provider import ClaudeTranslationProvider
from app.services.translation.prompt import build_user_prompt
from app.services.translator import translate_segments


class Recorder(TranslationProvider):
    def __init__(self, skip_first=None):
        self.requests = []
        self.skip_first = skip_first

    def translate_batch(self, request):
        self.requests.append(request)
        out = {i.id: f"T:{i.text}" for i in request.items}
        if self.skip_first and len(self.requests) == 1:
            out.pop(self.skip_first, None)
        return out


@pytest.fixture
def project(client):
    db = SessionLocal()
    p = Project(source_language="pt-PT", target_language="zh", domain="accounting_tax")
    db.add(p)
    db.flush()
    for i, text in enumerate(["Eu fui ao banco...", "...porque precisava", "tratar do pagamento.",
                              "Do IVA.", "Obrigado."]):
        db.add(Segment(project_id=p.id, segment_index=i, start_time=i, end_time=i + 0.9,
                       original_text=text))
    db.add(GlossaryTerm(term="IVA", translation="IVA", target_language="zh"))
    db.add(GlossaryTerm(term="IVA", translation="IVA-project", project_id=p.id))
    db.add(GlossaryTerm(term="fatura", translation="invoice", target_language="en"))
    db.commit()
    yield db, p
    db.close()


def test_batches_have_context_and_keep_ids(project):
    db, p = project
    rec = Recorder()
    n = translate_segments(db, p, "zh", provider=rec)
    assert n == 5
    assert [len(r.items) for r in rec.requests] == [2, 2, 1]  # batch size 2 in tests
    second = rec.requests[1]
    assert second.context_before == ["...porque precisava"]  # context size 1
    assert second.context_after == ["Obrigado."]
    segs = sorted(p.segments, key=lambda s: s.segment_index)
    assert segs[0].translated_text == "T:Eu fui ao banco..."
    assert all(s.translation_language == "zh" for s in segs)
    # Timings untouched
    assert [s.start_time for s in segs] == [0, 1, 2, 3, 4]


def test_glossary_project_overrides_global_and_filters_language(project):
    db, p = project
    rec = Recorder()
    translate_segments(db, p, "zh", provider=rec)
    glossary = {g.term: g.translation for g in rec.requests[0].glossary}
    assert glossary == {"IVA": "IVA-project"}


def test_missing_line_is_retried(project):
    db, p = project
    rec = Recorder(skip_first="2")
    translate_segments(db, p, "zh", provider=rec)
    assert len(rec.requests[1].items) == 1  # the retry
    assert all(s.translated_text for s in p.segments)


def test_selected_segments_only(project):
    db, p = project
    rec = Recorder()
    target = sorted(p.segments, key=lambda s: s.segment_index)[2]
    translate_segments(db, p, "zh", segment_ids=[target.id], provider=rec)
    assert len(rec.requests) == 1
    assert rec.requests[0].context_before == ["...porque precisava"]
    assert [s.translated_text for s in p.segments if s.translated_text] == ["T:tratar do pagamento."]


def test_same_language_copies(project):
    db, p = project
    rec = Recorder()
    translate_segments(db, p, "pt-PT", provider=rec)
    assert rec.requests == []
    assert all(s.translated_text == s.original_text for s in p.segments)


def test_prompt_contains_pt_pt_rules_domain_and_glossary():
    req = TranslationRequest(
        items=[TranslationItem("1", "早上好")], source_language="zh", target_language="pt-PT",
        domain="accounting_tax", glossary=[GlossaryEntry("增值税", "IVA")],
    )
    prompt = build_user_prompt(req)
    assert "European Portuguese" in prompt and "Never use Brazilian" in prompt
    assert "Accounting & Tax" in prompt and "Retenção na Fonte".lower() in prompt.lower()
    assert "增值税 => IVA" in prompt
    assert '"id": "1"' in prompt


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def fake_client(text, stop_reason="end_turn"):
    resp = SimpleNamespace(stop_reason=stop_reason,
                           content=[SimpleNamespace(type="text", text=text)])
    messages = FakeMessages(resp)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_claude_provider_request_and_parsing():
    client, messages = fake_client('{"translations": [{"id": "1", "text": " Olá "}, {"id": "9", "text": "x"}]}')
    provider = ClaudeTranslationProvider(client=client, model="claude-opus-5")
    req = TranslationRequest(items=[TranslationItem("1", "Hello")], source_language="en",
                             target_language="pt-PT")
    assert provider.translate_batch(req) == {"1": "Olá"}
    kw = messages.kwargs
    assert kw["model"] == "claude-opus-5"
    assert kw["fallbacks"] == "default"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["thinking"] == {"type": "adaptive"}


def test_claude_provider_refusal():
    client, _ = fake_client("", stop_reason="refusal")
    provider = ClaudeTranslationProvider(client=client, model="claude-opus-5")
    req = TranslationRequest(items=[TranslationItem("1", "Hello")], source_language="en",
                             target_language="zh")
    with pytest.raises(TranslationError):
        provider.translate_batch(req)


def test_claude_provider_reads_key_from_settings(monkeypatch):
    from app.config import get_settings

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    with pytest.raises(TranslationError, match="ANTHROPIC_API_KEY is not set"):
        ClaudeTranslationProvider()
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-ant-test")
    provider = ClaudeTranslationProvider()
    assert provider.client.api_key == "sk-ant-test"
