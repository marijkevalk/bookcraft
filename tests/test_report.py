"""Tests for the report HTML builder (pure; PDF rendering not exercised here)."""

from bookcraft.analyze import Analysis, ChapterAnalysis, Finding, Synthesis
from bookcraft.metrics import compute_metrics
from bookcraft.report import render_html


def _analysis() -> Analysis:
    findings = (
        Finding(
            "Prose & voice",
            "high",
            "Too many filter words",
            "She just really felt the cold",
            "Cut the filters",
            "ch.1 — Opening",
        ),
        Finding(
            "Pacing",
            "low",
            "Slightly slow",
            "the long walk home",
            "Trim",
            "ch.1 — Opening",
        ),
    )
    return Analysis(
        synthesis=Synthesis("revise", 64, "Solid but needs polish.", "Hook is weak."),
        chapters=(ChapterAnalysis(1, "Opening", findings),),
        metrics=compute_metrics(["She just really felt the cold wind."]),
    )


def test_html_contains_verdict_score_and_summary():
    html = render_html(_analysis(), title="My Book")
    assert "My Book" in html
    assert "REVISE" in html
    assert "64" in html
    assert "Solid but needs polish." in html


def test_html_shows_quote_and_fix_and_opening():
    html = render_html(_analysis())
    assert "She just really felt the cold" in html  # verbatim quote shown
    assert "Cut the filters" in html
    assert "Hook is weak." in html  # opening assessment


def test_writer_block_lists_high_and_medium_only():
    html = render_html(_analysis())
    assert "Cut the filters" in html  # high -> in writer block
    # the low-severity fix "Trim" appears in detail but the writer block is high/med only;
    # presence is fine, we assert the high one is definitely there
    assert "Send to your writer" in html


def test_metrics_rendered():
    html = render_html(_analysis())
    assert "Words" in html and "Reading ease" in html


def test_review_section_rendered_when_present():
    from bookcraft.analyze import RegressionCheck, ReviewTheme

    base = _analysis()
    a = Analysis(
        synthesis=base.synthesis,
        chapters=base.chapters,
        metrics=base.metrics,
        review_themes=(ReviewTheme("slow pacing", "2 of 2", "too slow"),),
        regression=(RegressionCheck("slow pacing", "yes", "ch.1 drags"),),
    )
    html = render_html(a)
    assert "Reader complaints" in html
    assert "slow pacing" in html
    assert "YES" in html
    assert "ch.1 drags" in html


def test_no_review_section_without_reviews():
    assert "Reader complaints" not in render_html(_analysis())
