"""Verifiable, no-opinion manuscript metrics — the credibility anchor.

Every number here is computed deterministically from the manuscript text, so the
reader can check it (the same trust the formatter's word-count integrity check
already earns). AI opinions come later and always sit *on top of* these facts.

Pure functions: no I/O, no network, fully unit-testable.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ']+")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+(?:\s|$)")
_VOWEL_GROUP_RE = re.compile(r"[aeiouyàáâäéèêëíïîóôöúùûü]+", re.IGNORECASE)
_DIALOGUE_RE = re.compile(r"[\"“”‘’']")  # noqa: RUF001 (smart quotes intentional)

# Crutch / filler words commonly over-used in fast-written romance.
CRUTCH_WORDS = (
    "just",
    "really",
    "very",
    "suddenly",
    "quite",
    "actually",
    "literally",
    "somehow",
    "slightly",
    "almost",
    "simply",
    "completely",
    "totally",
)
# Filter words that put distance between reader and character (weaken immediacy).
FILTER_WORDS = (
    "felt",
    "saw",
    "heard",
    "noticed",
    "realized",
    "watched",
    "seemed",
    "knew",
    "thought",
    "wondered",
    "looked",
)


@dataclass(frozen=True)
class ChapterMetrics:
    title: str
    word_count: int


@dataclass(frozen=True)
class Metrics:
    word_count: int
    paragraph_count: int
    sentence_count: int
    avg_sentence_length: float
    sentence_length_stdev: float
    dialogue_ratio: float  # fraction of (non-empty) paragraphs containing dialogue
    reading_ease: float  # Flesch reading ease (higher = easier)
    crutch_counts: dict[str, int]  # per 10k words, only words that occur
    filter_counts: dict[str, int]  # per 10k words, only words that occur
    chapters: tuple[ChapterMetrics, ...] = ()


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _count_syllables(word: str) -> int:
    groups = _VOWEL_GROUP_RE.findall(word)
    count = len(groups)
    if word.lower().endswith("e") and count > 1:
        count -= 1  # silent trailing 'e'
    return max(count, 1)


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [p for p in (s.strip() for s in parts) if p]


def _per_10k(counts: Counter[str], total_words: int) -> dict[str, int]:
    if total_words == 0:
        return {}
    scale = 10_000 / total_words
    return {w: round(c * scale) for w, c in counts.items() if c}


def compute_metrics(
    paragraphs: list[str],
    chapters: list[ChapterMetrics] | None = None,
) -> Metrics:
    """Compute verifiable metrics from a manuscript's paragraph texts."""
    non_empty = [p for p in paragraphs if p.strip()]
    full_text = "\n".join(non_empty)
    words = _words(full_text)
    word_count = len(words)

    sentences = _sentences(full_text)
    sent_lengths = [len(_words(s)) for s in sentences]
    sentence_count = len(sentences)
    avg_len = (sum(sent_lengths) / sentence_count) if sentence_count else 0.0
    stdev = (
        math.sqrt(sum((n - avg_len) ** 2 for n in sent_lengths) / sentence_count)
        if sentence_count
        else 0.0
    )

    dialogue_paras = sum(1 for p in non_empty if _DIALOGUE_RE.search(p))
    dialogue_ratio = (dialogue_paras / len(non_empty)) if non_empty else 0.0

    syllables = sum(_count_syllables(w) for w in words)
    if word_count and sentence_count:
        reading_ease = (
            206.835
            - 1.015 * (word_count / sentence_count)
            - 84.6 * (syllables / word_count)
        )
    else:
        reading_ease = 0.0

    lower = [w.lower() for w in words]
    freq = Counter(lower)
    crutch = Counter({w: freq[w] for w in CRUTCH_WORDS if freq[w]})
    filt = Counter({w: freq[w] for w in FILTER_WORDS if freq[w]})

    return Metrics(
        word_count=word_count,
        paragraph_count=len(non_empty),
        sentence_count=sentence_count,
        avg_sentence_length=round(avg_len, 1),
        sentence_length_stdev=round(stdev, 1),
        dialogue_ratio=round(dialogue_ratio, 3),
        reading_ease=round(reading_ease, 1),
        crutch_counts=_per_10k(crutch, word_count),
        filter_counts=_per_10k(filt, word_count),
        chapters=tuple(chapters or ()),
    )
