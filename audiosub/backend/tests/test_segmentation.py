from app.services.segmentation import SegmentationConfig, is_cjk, segment_transcript, wrap_lines


def words(text, start, step=0.3):
    out = []
    for i, w in enumerate(text.split()):
        out.append({"word": " " + w, "start": start + i * step,
                    "end": start + (i + 1) * step - 0.02, "probability": 0.9})
    return out


def test_breaks_after_sentence_end():
    text = "Bom dia. Gostaria de falar consigo sobre o assunto de ontem."
    cues = segment_transcript([{"start": 0, "end": 5, "text": text, "words": words(text, 0)}])
    assert cues[0].text == "Bom dia."
    assert cues[1].text.replace("\n", " ") == "Gostaria de falar consigo sobre o assunto de ontem."
    assert cues[0].end <= cues[1].start


def test_long_run_is_split_and_wrapped():
    text = ("Bom dia eu gostaria de falar com você relativamente ao assunto que falámos "
            "ontem porque precisamos de tratar do pagamento do IVA, e também das faturas "
            "que ficaram pendentes na semana passada com a Autoridade Tributária")
    cues = segment_transcript([{"start": 0, "end": 20, "text": text, "words": words(text, 0, 0.25)}])
    assert len(cues) > 1
    cfg = SegmentationConfig()
    for cue in cues:
        lines = cue.text.split("\n")
        assert len(lines) <= 2
        assert all(len(line) <= cfg.max_line_chars + 10 for line in lines)
        assert cue.end - cue.start <= cfg.max_duration + 0.5
    # Nothing lost or duplicated
    rebuilt = " ".join(c.text.replace("\n", " ") for c in cues)
    assert rebuilt == text


def test_pause_creates_break():
    w = words("olá tudo bem", 0) + words("sim obrigado", 5)
    cues = segment_transcript([{"start": 0, "end": 6, "text": "", "words": w}])
    assert [c.text for c in cues] == ["olá tudo bem", "sim obrigado"]


def test_without_word_timestamps_interpolates():
    cues = segment_transcript([{"start": 10, "end": 14, "text": "Bom dia. Tudo bem?", "confidence": 0.8}])
    assert [c.text for c in cues] == ["Bom dia.", "Tudo bem?"]
    assert cues[0].start == 10 and cues[-1].end <= 14.0001
    assert cues[0].confidence == 0.8


def test_cjk():
    assert is_cjk("早上好，你好吗？")
    cues = segment_transcript([{"start": 0, "end": 4, "text": "早上好，你好吗？我想和你谈谈增值税。"}])
    assert [c.text for c in cues] == ["早上好，你好吗？", "我想和你谈谈增值税。"]


def test_wrap_lines_balanced():
    wrapped = wrap_lines("Gostaria de falar consigo sobre o assunto de ontem, se possível.")
    a, b = wrapped.split("\n")
    assert abs(len(a) - len(b)) < 25
    assert wrap_lines("Bom dia.") == "Bom dia."
