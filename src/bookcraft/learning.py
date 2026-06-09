"""The learning overview — the under-the-hood memory that sharpens analyses.

The only inputs are the AI's own analyses and the reader reviews (never typed
human feedback). After each run the overview is rewritten by the model to fold in
durable lessons; future analyses load it as extra context for the synthesis. It
lives in the repo (knowledge/learning.md) so it stays inspectable and versioned.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from bookcraft.analyze import Analysis, Runner

logger = logging.getLogger(__name__)

LEARNING_PATH = Path(__file__).resolve().parent / "knowledge" / "learning.md"
_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def load_learning() -> str:
    try:
        return LEARNING_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def save_learning(text: str) -> None:
    LEARNING_PATH.write_text(text.strip() + "\n", encoding="utf-8")


_UPDATE_PROMPT = """You maintain a durable "learning overview" for a steamy-romance \
publisher's quality analyser. It accumulates patterns that make FUTURE checks \
sharper: recurring ghostwriter weaknesses, which manuscript patterns correlated \
with real reader complaints, and heat/length calibration for this publisher.

Rewrite and return the FULL updated overview as Markdown — nothing else. Merge the \
new analysis into what is there (de-duplicate; do not just append). Record only \
durable, evidence-based patterns, not one-off details. Keep the section headings.

Current overview:
{current}

New analysis to fold in:
- Book: {book}
- Verdict: {verdict} ({score}/100)
- Top issues found: {issues}
- Reader-complaint regression: {regression}
"""


def update_learning(
    current: str, analysis: Analysis, runner: Runner, book: str = ""
) -> str:
    """Fold one analysis into the overview; return the rewritten Markdown."""
    issues = (
        "; ".join(
            f"{f.severity} {f.dimension}: {f.issue}" for f in analysis.top_issues(8)
        )
        or "(none)"
    )
    regression = (
        "; ".join(f"{r.theme}={r.recurs}" for r in analysis.regression)
        or "(no reviews this run)"
    )
    prompt = _UPDATE_PROMPT.format(
        current=current.strip() or "(empty — first run)",
        verdict=analysis.synthesis.verdict,
        score=analysis.synthesis.score,
        book=book or "(untitled)",
        issues=issues,
        regression=regression,
    )
    raw = runner(prompt).strip()
    match = _FENCE_RE.match(raw)
    return match.group(1) if match else raw
