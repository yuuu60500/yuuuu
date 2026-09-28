from app.services.export import Cue, render, srt_time, vtt_time

CUES = [
    Cue(1.2, 4.8, "Bom dia, tudo bem?", "早上好，你好吗？"),
    Cue(4.9, 8.3, "Gostaria de falar sobre o IVA.", "我想谈谈IVA。"),
]


def test_timestamps():
    assert srt_time(1.2) == "00:00:01,200"
    assert vtt_time(3723.456) == "01:02:03.456"


def test_srt_original():
    out = render(CUES, "srt", "original")
    assert out.startswith("1\n00:00:01,200 --> 00:00:04,800\nBom dia, tudo bem?\n\n2\n")


def test_vtt_translation():
    out = render(CUES, "vtt", "translation")
    assert out.startswith("WEBVTT\n\n1\n00:00:01.200 --> 00:00:04.800\n早上好，你好吗？")


def test_bilingual_orders():
    a = render(CUES, "srt", "bilingual", "original_first")
    assert "Bom dia, tudo bem?\n早上好，你好吗？" in a
    b = render(CUES, "srt", "bilingual", "translation_first")
    assert "早上好，你好吗？\nBom dia, tudo bem?" in b


def test_txt():
    out = render(CUES, "txt", "original")
    assert out == "Bom dia, tudo bem?\nGostaria de falar sobre o IVA.\n"


def test_skips_empty_and_renumbers():
    out = render([Cue(0, 1, "a", None), Cue(1, 2, "b", "B")], "srt", "translation")
    assert out.startswith("1\n00:00:01,000")
