import pytest

from app.services.asr.mock_provider import MockASRProvider
from app.services.translation.mock_provider import MockTranslationProvider


def create(client, **kw):
    body = {"source_language": "auto", "target_language": "zh", "domain": "accounting_tax",
            "subtitle_mode": "bilingual", **kw}
    r = client.post("/api/projects", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, pid, path, name=None):
    with open(path, "rb") as f:
        return client.post(f"/api/projects/{pid}/upload",
                           files={"file": (name or path.rsplit("/", 1)[-1], f)})


@pytest.fixture
def asr_calls(monkeypatch):
    calls = []
    orig = MockASRProvider.transcribe

    def spy(self, path, language=None):
        calls.append(language)
        return orig(self, path, language)

    monkeypatch.setattr(MockASRProvider, "transcribe", spy)
    return calls


def test_meta(client):
    m = client.get("/api/meta").json()
    assert [l["code"] for l in m["source_languages"]] == ["auto", "zh", "en", "pt-PT"]
    assert "accounting_tax" in [d["code"] for d in m["domains"]]
    assert m["supported_extensions"] == ["m4a", "mp3", "mp4", "wav"]


def test_full_mvp_flow(client, mp4_file, asr_calls):
    p = create(client)
    assert p["status"] == "CREATED"

    r = upload(client, p["id"], mp4_file)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["status"] == "UPLOADED" and p["file_type"] == "mp4" and p["media_kind"] == "video"
    assert 11.5 < p["duration"] < 12.5
    assert p["steps"]["upload"]["status"] == "completed"

    p = client.post(f"/api/projects/{p['id']}/process").json()
    p = client.get(f"/api/projects/{p['id']}").json()
    assert p["status"] == "READY", p
    assert p["detected_language"] == "pt-PT"
    assert p["progress"] == 100
    assert all(p["steps"][s]["status"] == "completed" for s in
               ["audio", "transcription", "segmentation", "translation", "finalize"])
    assert asr_calls == [None]  # auto-detect
    assert p["segment_count"] >= 4

    segs = client.get(f"/api/projects/{p['id']}/segments").json()
    assert segs[0]["original_text"] == "Bom dia, tudo bem?"
    assert segs[0]["translated_text"].startswith("[zh]")
    assert segs[0]["confidence"] == pytest.approx(0.95)

    # Media is streamable (with range support)
    r = client.get(f"/api/projects/{p['id']}/media", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100

    # Edit original, translation and times
    s0 = segs[0]
    r = client.patch(f"/api/segments/{s0['id']}", json={
        "original_text": "Bom dia!", "translated_text": "早上好！", "start_time": 0.5, "end_time": 2.0})
    assert r.status_code == 200 and r.json()["original_text"] == "Bom dia!"
    assert client.patch(f"/api/segments/{s0['id']}", json={"end_time": 0.1}).status_code == 422

    # Split
    s1 = segs[1]
    r = client.post(f"/api/segments/{s1['id']}/split", json={})
    assert r.status_code == 200
    a, b = r.json()
    assert a["end_time"] == b["start_time"]
    joined = (a["original_text"] + " " + b["original_text"]).replace("\n", " ")
    assert joined == s1["original_text"].replace("\n", " ")
    segs = client.get(f"/api/projects/{p['id']}/segments").json()
    assert [s["segment_index"] for s in segs] == list(range(len(segs)))

    # Merge back
    r = client.post(f"/api/projects/{p['id']}/segments/merge", json={"segment_ids": [a["id"], b["id"]]})
    assert r.status_code == 200
    assert r.json()["original_text"] == s1["original_text"]  # re-wrapped the same way
    n_before = len(client.get(f"/api/projects/{p['id']}/segments").json())

    # Add and delete
    r = client.post(f"/api/projects/{p['id']}/segments",
                    json={"start_time": 11.0, "end_time": 11.9, "original_text": "Adeus."})
    assert r.status_code == 201
    new_id = r.json()["id"]
    assert client.delete(f"/api/segments/{new_id}").status_code == 204
    assert len(client.get(f"/api/projects/{p['id']}/segments").json()) == n_before

    # Retranslate selected into English without calling ASR again
    segs = client.get(f"/api/projects/{p['id']}/segments").json()
    r = client.post(f"/api/projects/{p['id']}/translate",
                    json={"target_language": "en", "segment_ids": [segs[2]["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["segments"][0]["translated_text"].startswith("[en]")

    # Retranslate all with another language/domain: ASR is not re-run
    r = client.post(f"/api/projects/{p['id']}/translate",
                    json={"target_language": "zh", "domain": "legal"})
    assert r.status_code == 200
    assert r.json()["project"]["status"] == "READY"
    assert asr_calls == [None]
    segs = client.get(f"/api/projects/{p['id']}/segments").json()
    assert all(s["translated_text"].startswith("[zh]") for s in segs)

    # Exports
    srt = client.get(f"/api/projects/{p['id']}/export?format=srt&content=original")
    assert srt.status_code == 200
    assert srt.text.startswith("1\n00:00:00,500 --> 00:00:02,000\nBom dia!\n")
    assert "portuguese_meeting.pt-PT.srt" in srt.headers["content-disposition"]
    zh = client.post(f"/api/projects/{p['id']}/export", json={"format": "srt", "content": "translation"})
    assert "[zh]" in zh.text and "portuguese_meeting.zh.srt" in zh.headers["content-disposition"]
    bi = client.post(f"/api/projects/{p['id']}/export",
                     json={"format": "srt", "content": "bilingual", "order": "translation_first"})
    first_block = bi.text.split("\n\n")[0].split("\n")
    assert first_block[2].startswith("[zh]") and first_block[3] == "Bom dia!"
    vtt = client.post(f"/api/projects/{p['id']}/export", json={"format": "vtt", "content": "original"})
    assert vtt.text.startswith("WEBVTT\n\n1\n00:00:00.500 --> ")
    txt = client.post(f"/api/projects/{p['id']}/export", json={"format": "txt", "content": "original"})
    assert txt.text.startswith("Bom dia!\n")

    # Project history
    listed = client.get("/api/projects").json()
    assert p["id"] in [x["id"] for x in listed]


def test_translation_failure_can_be_retried_without_asr(client, mp3_file, asr_calls, monkeypatch):
    p = create(client, source_language="pt-PT", target_language="en")
    upload(client, p["id"], mp3_file)

    def boom(self, request):
        raise RuntimeError("translation service down")

    monkeypatch.setattr(MockTranslationProvider, "translate_batch", boom)
    client.post(f"/api/projects/{p['id']}/process")
    p = client.get(f"/api/projects/{p['id']}").json()
    assert p["status"] == "FAILED"
    assert p["steps"]["transcription"]["status"] == "completed"
    assert p["steps"]["translation"]["status"] == "failed"
    assert "translation service down" in p["steps"]["translation"]["error"]
    assert asr_calls == ["pt"]  # explicit source language passed to ASR
    # Subtitles survive the failure
    assert p["segment_count"] > 0

    monkeypatch.undo()
    p = client.post(f"/api/projects/{p['id']}/retry").json()
    p = client.get(f"/api/projects/{p['id']}").json()
    assert p["status"] == "READY"
    assert p["steps"]["translation"]["status"] == "completed"
    assert len(asr_calls) == 1


def test_original_only_mode_skips_translation(client, mp3_file):
    p = create(client, target_language=None, subtitle_mode="original")
    upload(client, p["id"], mp3_file)
    client.post(f"/api/projects/{p['id']}/process")
    p = client.get(f"/api/projects/{p['id']}").json()
    assert p["status"] == "READY"
    assert p["steps"]["translation"]["status"] == "skipped"
    r = client.post(f"/api/projects/{p['id']}/export", json={"format": "srt", "content": "bilingual"})
    assert r.status_code == 400


def test_rejects_bad_uploads(client, tmp_path):
    p = create(client)
    bad = tmp_path / "notes.pdf"
    bad.write_bytes(b"%PDF")
    assert upload(client, p["id"], str(bad)).status_code == 400
    fake = tmp_path / "fake.mp3"
    fake.write_bytes(b"this is not audio" * 10)
    r = upload(client, p["id"], str(fake))
    assert r.status_code == 400
    assert client.post(f"/api/projects/{p['id']}/process").status_code == 400


def test_validation(client):
    assert client.post("/api/projects", json={"target_language": "klingon"}).status_code == 422
    assert client.post("/api/projects", json={"domain": "astrology"}).status_code == 422
    p = client.post("/api/projects", json={"target_language": "pt"}).json()
    assert p["target_language"] == "pt-PT"  # Portuguese always means PT-PT


def test_glossary_crud(client):
    r = client.post("/api/glossary", json={"term": "OCC", "translation": "Ordem dos Contabilistas Certificados"})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert any(t["term"] == "OCC" for t in client.get("/api/glossary").json())
    r = client.put(f"/api/glossary/{tid}", json={"term": "OCC", "translation": "OCC", "target_language": "zh"})
    assert r.json()["target_language"] == "zh"
    assert client.delete(f"/api/glossary/{tid}").status_code == 204


def test_standalone_services(client, mp3_file):
    p = create(client, source_language="en", target_language="pt-PT")
    upload(client, p["id"], mp3_file)
    r = client.post("/api/transcribe", json={"file_id": p["id"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["language"] == "en" and data["segments"][0]["text"].startswith("Good morning")
    client.post(f"/api/projects/{p['id']}/resegment")
    r = client.post("/api/translate", json={
        "project_id": p["id"], "glossary": [{"term": "VAT", "translation": "IVA"}]})
    assert r.status_code == 200, r.text
    assert any("IVA" in s["translated_text"] for s in r.json())


def test_delete_project(client, mp3_file):
    p = create(client)
    upload(client, p["id"], mp3_file)
    assert client.delete(f"/api/projects/{p['id']}").status_code == 204
    assert client.get(f"/api/projects/{p['id']}").status_code == 404
