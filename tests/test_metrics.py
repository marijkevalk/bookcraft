"""Tests for the verifiable manuscript metrics (pure, no I/O)."""

from bookcraft.metrics import ChapterMetrics, Metrics, compute_metrics


def test_word_sentence_and_dialogue_counts():
    paras = [
        "She just really felt the cold.",  # 6 words, crutch just/really, filter felt
        '"Stop," he said.',  # 3 words, dialogue
    ]
    m = compute_metrics(paras)
    assert m.word_count == 9
    assert m.paragraph_count == 2
    assert m.sentence_count == 2
    assert m.avg_sentence_length == 4.5
    assert m.dialogue_ratio == 0.5  # only the second paragraph has quotes
    assert m.reading_ease > 0


def test_crutch_and_filter_words_detected():
    m = compute_metrics(["She just really felt it, just because."])
    assert set(m.crutch_counts) == {"just", "really"}
    assert set(m.filter_counts) == {"felt"}


def test_empty_input_is_safe():
    m = compute_metrics([])
    assert m == Metrics(
        word_count=0,
        paragraph_count=0,
        sentence_count=0,
        avg_sentence_length=0.0,
        sentence_length_stdev=0.0,
        dialogue_ratio=0.0,
        reading_ease=0.0,
        crutch_counts={},
        filter_counts={},
        chapters=(),
    )


def test_blank_paragraphs_ignored():
    m = compute_metrics(["", "   ", "One two three."])
    assert m.paragraph_count == 1
    assert m.word_count == 3


def test_chapters_passthrough():
    chapters = [ChapterMetrics("Chapter 1", 1200), ChapterMetrics("Chapter 2", 980)]
    m = compute_metrics(["Some text here."], chapters=chapters)
    assert m.chapters == tuple(chapters)
    assert m.chapters[0].word_count == 1200
