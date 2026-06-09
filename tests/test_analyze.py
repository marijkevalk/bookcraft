"""Tests for the AI analysis core — parsing, quote-verification, orchestration.

No Claude calls: the runner is a fake returning canned JSON.
"""

from bookcraft.analyze import (
    Analysis,
    ChapterAnalysis,
    Finding,
    Synthesis,
    analyze_chapter,
    analyze_manuscript,
    synthesize,
)
from bookcraft.metrics import compute_metrics

CHAPTER_TEXT = "She just really felt the cold wind bite at her bare skin."


class FakeRunner:
    """Returns synth JSON for the synthesis prompt, chapter JSON otherwise."""

    def __init__(self, chapter_json: str, synth_json: str = "{}") -> None:
        self.chapter_json = chapter_json
        self.synth_json = synth_json
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.synth_json if "editor-in-chief" in prompt else self.chapter_json


def test_verifiable_quote_kept_fabricated_dropped():
    runner = FakeRunner(
        '{"findings": ['
        '{"dimension": "2", "severity": "high", "issue": "filter words",'
        ' "quote": "She just really felt", "fix": "cut the filter"},'
        '{"dimension": "1", "severity": "low", "issue": "made up",'
        ' "quote": "this sentence is nowhere in the chapter", "fix": "x"}'
        "]}"
    )
    ch = analyze_chapter(1, "Opening", CHAPTER_TEXT, rubric="(rubric)", runner=runner)
    assert len(ch.findings) == 1  # the fabricated-quote finding is dropped
    assert ch.findings[0].severity == "high"
    assert ch.findings[0].location == "ch.1 — Opening"


def test_quote_match_is_case_and_whitespace_insensitive():
    runner = FakeRunner(
        '{"findings": [{"dimension": "2", "severity": "medium", "issue": "x",'
        ' "quote": "SHE   JUST  really felt", "fix": "y"}]}'
    )
    ch = analyze_chapter(1, "C", CHAPTER_TEXT, rubric="(r)", runner=runner)
    assert len(ch.findings) == 1


def test_malformed_json_yields_no_findings():
    ch = analyze_chapter(1, "C", CHAPTER_TEXT, rubric="(r)", runner=FakeRunner("not json"))
    assert ch.findings == ()


def test_synthesis_parses_and_clamps_score():
    runner = FakeRunner(
        "{}",
        synth_json='{"verdict": "REVISE", "score": 150, "summary": "s",'
        ' "opening_assessment": "o"}',
    )
    s = synthesize((), compute_metrics([CHAPTER_TEXT]), runner)
    assert s.verdict == "revise"
    assert s.score == 100  # clamped to 0-100
    assert s.opening_assessment == "o"


def test_synthesis_bad_json_falls_back():
    s = synthesize((), compute_metrics([CHAPTER_TEXT]), FakeRunner("{}", "garbage"))
    assert s.verdict == "revise"
    assert s.score == 0


def test_top_issues_sorted_by_severity():
    findings = (
        Finding("1", "low", "lo", "q", "f"),
        Finding("2", "high", "hi", "q", "f"),
        Finding("3", "medium", "me", "q", "f"),
    )
    analysis = Analysis(
        synthesis=Synthesis("revise", 70, "", ""),
        chapters=(ChapterAnalysis(1, "C", findings),),
        metrics=compute_metrics([CHAPTER_TEXT]),
    )
    assert [f.severity for f in analysis.top_issues(3)] == ["high", "medium", "low"]


def test_analyze_manuscript_orchestrates_chapters_and_synthesis():
    runner = FakeRunner(
        '{"findings": [{"dimension": "2", "severity": "high", "issue": "x",'
        ' "quote": "cold wind", "fix": "y"}]}',
        synth_json='{"verdict": "revise", "score": 60, "summary": "s",'
        ' "opening_assessment": "o"}',
    )
    metrics = compute_metrics([CHAPTER_TEXT])
    result = analyze_manuscript(
        [("Ch1", CHAPTER_TEXT), ("Ch2", CHAPTER_TEXT)],
        metrics,
        runner,
        rubric="(rubric)",
    )
    assert len(result.chapters) == 2
    assert result.synthesis.score == 60
    assert len(result.all_findings) == 2  # one per chapter
    # 2 chapter calls + 1 synthesis call
    assert len(runner.calls) == 3


def test_split_chapters_by_heading_and_marker():
    from bookcraft.analyze import split_chapters

    paras = [
        ("Heading 1", "Chapter 1: Aria"),
        ("Normal", "She woke cold."),
        ("Normal", "The room was dark."),
        ("Normal", "PROLOGUE"),  # matched by marker even without a heading style
        ("Normal", "Long ago."),
        ("Heading 1", "Chapter 2"),
        ("Normal", "He left."),
    ]
    chapters = split_chapters(paras)
    assert [t for t, _ in chapters] == ["Chapter 1: Aria", "PROLOGUE", "Chapter 2"]
    assert chapters[0][1] == "She woke cold.\nThe room was dark."
    assert chapters[2][1] == "He left."


def test_split_chapters_front_matter_before_first_heading():
    from bookcraft.analyze import split_chapters

    paras = [
        ("Normal", "Copyright 2026."),
        ("Heading 1", "Chapter 1"),
        ("Normal", "Begin."),
    ]
    chapters = split_chapters(paras)
    assert chapters[0][0] == "(front matter)"
    assert chapters[0][1] == "Copyright 2026."


def test_quote_verification_tolerates_smart_quotes():
    # Manuscript uses a straight apostrophe; the model returns a smart one.
    text = "My dragon hasn't stopped moving since the fire."
    runner = FakeRunner(
        '{"findings": [{"dimension": "2", "severity": "low", "issue": "x",'
        ' "quote": "My dragon hasn’t stopped moving", "fix": "y"}]}'
    )
    ch = analyze_chapter(1, "C", text, rubric="(r)", runner=runner)
    assert len(ch.findings) == 1  # matched despite the apostrophe style difference
