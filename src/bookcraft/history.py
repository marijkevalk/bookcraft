"""Per-analysis history + the ghostwriter scorecard (Fase 3).

Each analysis is written to ``data/history/`` as JSON; aggregating those records
per ghostwriter yields a track record (average score, recurring weak dimensions),
the steering tool for who to rehire and where to push back.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from bookcraft.analyze import Analysis

HISTORY_DIR = Path(__file__).resolve().parents[2] / "data" / "history"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class HistoryRecord:
    date: str  # ISO date
    book: str
    ghostwriter: str
    verdict: str
    score: int
    findings_by_dimension: dict[str, int] = field(default_factory=dict)
    high_count: int = 0
    regression: dict[str, str] = field(default_factory=dict)


@dataclass
class GhostwriterStats:
    ghostwriter: str
    book_count: int
    avg_score: float
    weak_dimensions: list[tuple[str, int]]  # (dimension, total high/medium findings)
    books: list[tuple[str, int]]  # (book title, score)


def record_from_analysis(
    analysis: Analysis,
    book: str,
    ghostwriter: str,
    when: datetime | None = None,
) -> HistoryRecord:
    by_dim: Counter[str] = Counter()
    high = 0
    for f in analysis.all_findings:
        if f.severity in ("high", "medium"):
            by_dim[f.dimension] += 1
        if f.severity == "high":
            high += 1
    stamp = when or datetime.now(UTC)
    return HistoryRecord(
        date=stamp.date().isoformat(),
        book=book or "(untitled)",
        ghostwriter=ghostwriter or "(unknown)",
        verdict=analysis.synthesis.verdict,
        score=analysis.synthesis.score,
        findings_by_dimension=dict(by_dim),
        high_count=high,
        regression={r.theme: r.recurs for r in analysis.regression},
    )


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "untitled"


def save_record(record: HistoryRecord, history_dir: Path = HISTORY_DIR) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{record.date}-{_slug(record.book)}.json"
    path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
    return path


def load_history(history_dir: Path = HISTORY_DIR) -> list[HistoryRecord]:
    if not history_dir.exists():
        return []
    out: list[HistoryRecord] = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(HistoryRecord(**data))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def build_scorecard(records: list[HistoryRecord]) -> list[GhostwriterStats]:
    by_gw: dict[str, list[HistoryRecord]] = defaultdict(list)
    for r in records:
        by_gw[r.ghostwriter].append(r)
    stats: list[GhostwriterStats] = []
    for gw, recs in sorted(by_gw.items()):
        dims: Counter[str] = Counter()
        for r in recs:
            dims.update(r.findings_by_dimension)
        avg = round(sum(r.score for r in recs) / len(recs), 1)
        stats.append(
            GhostwriterStats(
                ghostwriter=gw,
                book_count=len(recs),
                avg_score=avg,
                weak_dimensions=dims.most_common(3),
                books=[(r.book, r.score) for r in recs],
            )
        )
    return stats
