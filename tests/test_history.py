"""Tests for analysis history + the ghostwriter scorecard."""

from datetime import UTC, datetime

from bookcraft.analyze import (
    Analysis,
    ChapterAnalysis,
    Finding,
    RegressionCheck,
    Synthesis,
)
from bookcraft.history import (
    HistoryRecord,
    build_scorecard,
    load_history,
    record_from_analysis,
    save_record,
)
from bookcraft.metrics import compute_metrics


def _analysis(score: int = 60, findings: tuple[Finding, ...] = ()) -> Analysis:
    return Analysis(
        synthesis=Synthesis("revise", score, "s", "o"),
        chapters=(ChapterAnalysis(1, "C", findings),),
        metrics=compute_metrics(["x."]),
        regression=(RegressionCheck("slow pacing", "yes", "e"),),
    )


def test_record_counts_dimensions_high_and_regression():
    findings = (
        Finding("Pacing", "high", "a", "q", "f"),
        Finding("Pacing", "medium", "b", "q", "f"),
        Finding("Voice", "low", "c", "q", "f"),  # low excluded from dimension counts
    )
    rec = record_from_analysis(
        _analysis(findings=findings),
        "Book",
        "Writer A",
        when=datetime(2026, 6, 9, tzinfo=UTC),
    )
    assert rec.date == "2026-06-09"
    assert rec.findings_by_dimension == {"Pacing": 2}
    assert rec.high_count == 1
    assert rec.regression == {"slow pacing": "yes"}
    assert rec.ghostwriter == "Writer A"


def test_save_load_roundtrip(tmp_path):
    path = save_record(
        record_from_analysis(_analysis(), "My Book", "Writer B"), tmp_path
    )
    assert path.exists()
    loaded = load_history(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].book == "My Book"
    assert loaded[0].ghostwriter == "Writer B"


def test_load_missing_dir_is_empty(tmp_path):
    assert load_history(tmp_path / "nope") == []


def test_scorecard_aggregates_per_ghostwriter():
    recs = [
        HistoryRecord(
            "2026-06-01",
            "B1",
            "Writer A",
            "revise",
            50,
            {"Pacing": 3, "Voice": 1},
            2,
            {},
        ),
        HistoryRecord(
            "2026-06-05", "B2", "Writer A", "publish", 80, {"Pacing": 1}, 0, {}
        ),
        HistoryRecord(
            "2026-06-03", "B3", "Writer B", "reject", 30, {"Consistency": 4}, 3, {}
        ),
    ]
    cards = build_scorecard(recs)
    assert len(cards) == 2
    a = next(c for c in cards if c.ghostwriter == "Writer A")
    assert a.book_count == 2
    assert a.avg_score == 65.0
    assert a.weak_dimensions[0] == ("Pacing", 4)  # 3 + 1 across both books
