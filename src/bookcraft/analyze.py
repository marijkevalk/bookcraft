"""AI quality analysis — per-chapter findings + an overall synthesis.

The intelligence runs through the local Claude Code CLI (same pattern as
ai_chapters: ``claude -p``, JSON-in-text, no API key). The ``runner`` is injected
so parsing, quote-verification and orchestration are unit-tested without spending
a Claude call.

Credibility rule (the whole point of the tool): every finding must quote the
manuscript **verbatim**. We verify each quote actually occurs in the chapter and
drop any that don't — a fabricated quote would destroy trust.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bookcraft.metrics import Metrics

logger = logging.getLogger(__name__)

DEFAULT_CLAUDE_BIN = "claude"
RUBRIC_PATH = Path(__file__).resolve().parent / "knowledge" / "rubric.md"
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# A runner takes a prompt and returns the model's raw text output.
Runner = Callable[[str], str]

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)
_WS_RE = re.compile(r"\s+")
_CHAPTER_HEAD_RE = re.compile(
    r"^\s*(chapter\b|prologue|epilogue|interlude|part\b)", re.IGNORECASE
)


@dataclass(frozen=True)
class Finding:
    dimension: str
    severity: str  # high | medium | low
    issue: str
    quote: str  # verbatim from the manuscript
    fix: str
    location: str = ""


@dataclass(frozen=True)
class ChapterAnalysis:
    index: int
    title: str
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class Synthesis:
    verdict: str  # publish | revise | reject
    score: int  # 0-100
    summary: str
    opening_assessment: str


@dataclass(frozen=True)
class Analysis:
    synthesis: Synthesis
    chapters: tuple[ChapterAnalysis, ...]
    metrics: Metrics

    @property
    def all_findings(self) -> list[Finding]:
        return [f for ch in self.chapters for f in ch.findings]

    def top_issues(self, n: int = 3) -> list[Finding]:
        ordered = sorted(
            self.all_findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9)
        )
        return ordered[:n]


def load_rubric() -> str:
    return RUBRIC_PATH.read_text(encoding="utf-8")


def claude_runner(prompt: str, claude_bin: str = DEFAULT_CLAUDE_BIN) -> str:
    """Invoke ``claude -p`` with the prompt on stdin; return raw stdout text."""
    binary = shutil.which(claude_bin) or claude_bin
    result = subprocess.run(
        [binary, "-p"],
        input=prompt,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _strip_fences(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    return match.group(1) if match else text.strip()


# Fold smart quotes/dashes so a verbatim quote still matches when the model and
# the manuscript differ only in punctuation style (apostrophes, em/en dashes).
_SMART = str.maketrans(
    {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": "-",
        "\u2013": "-",
    }
)


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text.translate(_SMART)).strip().lower()


def _quote_in_text(quote: str, text: str) -> bool:
    needle = _normalize(quote)
    return bool(needle) and needle in _normalize(text)


_CHAPTER_PROMPT = """You are a ruthless but fair developmental editor for steamy \
romance novels. Evaluate ONE chapter against this rubric:

{rubric}

Return ONLY a JSON object, no prose:
{{"findings": [{{"dimension": "<rubric layer>", "severity": "high|medium|low", \
"issue": "<what is wrong, one sentence>", "quote": "<short VERBATIM excerpt from \
the chapter that shows it>", "fix": "<concrete fix>"}}]}}

Rules:
- Quote VERBATIM from the chapter text below — copy exact words, never paraphrase.
- Only real, specific problems. If the chapter is clean, return {{"findings": []}}.

Chapter title: {title}

Chapter text:
{text}
"""

_SYNTH_PROMPT = """You are the editor-in-chief deciding whether a steamy romance \
manuscript is ready to publish. Use the per-chapter findings and the hard metrics.

Return ONLY a JSON object:
{{"verdict": "publish|revise|reject", "score": <integer 0-100>, \
"summary": "<2-3 sentences>", "opening_assessment": "<does chapter 1 hook a \
browsing Amazon reader? 2-3 sentences>"}}

Metrics: {metrics}

Findings by chapter:
{findings}
"""


def analyze_chapter(
    index: int, title: str, text: str, rubric: str, runner: Runner
) -> ChapterAnalysis:
    prompt = _CHAPTER_PROMPT.format(rubric=rubric, title=title, text=text)
    raw = _strip_fences(runner(prompt))
    location = f"ch.{index} — {title}" if title else f"ch.{index}"
    findings = _parse_findings(raw, text, location)
    return ChapterAnalysis(index=index, title=title, findings=tuple(findings))


def _parse_findings(raw: str, chapter_text: str, location: str) -> list[Finding]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("chapter findings not valid JSON: %s", raw[:200])
        return []
    items = payload.get("findings", []) if isinstance(payload, dict) else []
    out: list[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote", ""))
        if not _quote_in_text(quote, chapter_text):
            logger.info("dropping finding with unverifiable quote: %r", quote[:80])
            continue
        out.append(
            Finding(
                dimension=str(item.get("dimension", "")),
                severity=str(item.get("severity", "")).lower(),
                issue=str(item.get("issue", "")),
                quote=quote,
                fix=str(item.get("fix", "")),
                location=location,
            )
        )
    return out


def _findings_digest(chapters: tuple[ChapterAnalysis, ...]) -> str:
    lines: list[str] = []
    for ch in chapters:
        for f in ch.findings:
            lines.append(f"- [{f.severity}] {ch.title}: {f.issue}")
    return "\n".join(lines) if lines else "(no chapter-level findings)"


def synthesize(
    chapters: tuple[ChapterAnalysis, ...], metrics: Metrics, runner: Runner
) -> Synthesis:
    prompt = _SYNTH_PROMPT.format(metrics=metrics, findings=_findings_digest(chapters))
    raw = _strip_fences(runner(prompt))
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("synthesis not valid JSON: %s", raw[:200])
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        score = int(payload.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    return Synthesis(
        verdict=str(payload.get("verdict", "revise")).lower(),
        score=max(0, min(100, score)),
        summary=str(payload.get("summary", "")),
        opening_assessment=str(payload.get("opening_assessment", "")),
    )


def analyze_manuscript(
    chapters: list[tuple[str, str]],
    metrics: Metrics,
    runner: Runner,
    rubric: str | None = None,
) -> Analysis:
    """Analyse a manuscript given its (title, text) chapters + computed metrics."""
    rubric_text = rubric if rubric is not None else load_rubric()
    analysed = tuple(
        analyze_chapter(i, title, text, rubric_text, runner)
        for i, (title, text) in enumerate(chapters, start=1)
    )
    synthesis = synthesize(analysed, metrics, runner)
    return Analysis(synthesis=synthesis, chapters=analysed, metrics=metrics)


def split_chapters(paragraphs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Split ``(style_name, text)`` paragraphs into ``(title, body_text)`` chapters.

    A heading is a non-empty paragraph that either matches a chapter marker
    (Chapter/Prologue/Epilogue/Part…) or carries a short "Heading" style. Plain,
    deterministic, unit-tested — no AI and no formatter coupling.
    """
    chapters: list[tuple[str, list[str]]] = []
    for style, text in paragraphs:
        stripped = text.strip()
        is_heading = bool(stripped) and (
            _CHAPTER_HEAD_RE.match(stripped) is not None
            or (style.lower().startswith("heading") and len(stripped) < 80)
        )
        if is_heading:
            chapters.append((stripped, []))
            continue
        if not chapters:
            chapters.append(("(front matter)", []))
        if stripped:
            chapters[-1][1].append(stripped)
    return [(title, "\n".join(body)) for title, body in chapters if body]
