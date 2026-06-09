"""Tests for the learning overview (load/save + AI-driven update)."""

import bookcraft.learning as learning
from bookcraft.analyze import (
    Analysis,
    ChapterAnalysis,
    Finding,
    RegressionCheck,
    Synthesis,
)
from bookcraft.metrics import compute_metrics


def _analysis() -> Analysis:
    return Analysis(
        synthesis=Synthesis("revise", 60, "s", "o"),
        chapters=(
            ChapterAnalysis(
                1, "C", (Finding("Pacing", "high", "slow", "cold wind", "trim", "ch.1"),)
            ),
        ),
        metrics=compute_metrics(["cold wind here."]),
        regression=(RegressionCheck("slow pacing", "yes", "ch.1 drags"),),
    )


class CapturingRunner:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    def __call__(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


def test_update_learning_folds_in_details_and_strips_fences():
    runner = CapturingRunner("```markdown\n# Learning\n- writers slip tense\n```")
    out = learning.update_learning("(first run)", _analysis(), runner, book="My Book")
    assert out == "# Learning\n- writers slip tense"  # code fences stripped
    assert "My Book" in runner.prompt
    assert "slow pacing=yes" in runner.prompt  # regression fed in
    assert "revise (60/100)" in runner.prompt  # verdict fed in


def test_update_learning_passthrough_without_fences():
    runner = CapturingRunner("# Learning\n- x")
    assert learning.update_learning("", _analysis(), runner) == "# Learning\n- x"


def test_load_save_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "learning.md"
    monkeypatch.setattr(learning, "LEARNING_PATH", path)
    learning.save_learning("# L\n- a\n\n")
    assert learning.load_learning() == "# L\n- a\n"


def test_load_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "LEARNING_PATH", tmp_path / "nope.md")
    assert learning.load_learning() == ""
