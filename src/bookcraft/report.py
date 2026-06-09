"""Render an Analysis into a credible PDF report.

Two layers, matching the brief: a page-1 executive dashboard (verdict, score,
hard metrics, top issues, chapter heatmap) with the extensive per-chapter detail
behind it, and a ready-to-forward "send to your writer" block. ``render_html`` is
pure and unit-tested; ``write_pdf`` renders that HTML via Playwright.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from bookcraft.analyze import Analysis, Finding

_SEV_COLOR = {"high": "#c0392b", "medium": "#e67e22", "low": "#7f8c8d"}
_VERDICT_COLOR = {"publish": "#27ae60", "revise": "#e67e22", "reject": "#c0392b"}


def _sev_counts(findings: list[Finding]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        if f.severity in counts:
            counts[f.severity] += 1
    return counts


def _finding_card(f: Finding) -> str:
    color = _SEV_COLOR.get(f.severity, "#7f8c8d")
    return (
        f'<div class="finding" style="border-left:4px solid {color}">'
        f'<div class="sev" style="color:{color}">{escape(f.severity.upper())}'
        f" · {escape(f.dimension)} · {escape(f.location)}</div>"
        f'<div class="issue">{escape(f.issue)}</div>'
        f"<blockquote>{escape(f.quote)}</blockquote>"
        f'<div class="fix"><b>Fix:</b> {escape(f.fix)}</div>'
        f"</div>"
    )


def _metrics_grid(analysis: Analysis) -> str:
    m = analysis.metrics
    top_crutch = ", ".join(
        f"{w} {n}" for w, n in sorted(m.crutch_counts.items(), key=lambda x: -x[1])[:4]
    )
    cells = [
        ("Words", f"{m.word_count:,}"),
        ("Chapters", str(len(m.chapters) or len(analysis.chapters))),
        ("Avg sentence", f"{m.avg_sentence_length} words"),
        ("Dialogue", f"{m.dialogue_ratio:.0%}"),
        ("Reading ease", f"{m.reading_ease}"),
        ("Crutch words /10k", top_crutch or "—"),
    ]
    return "".join(
        f'<div class="metric"><div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div></div>'
        for label, value in cells
    )


def _heatmap(analysis: Analysis) -> str:
    rows = []
    for ch in analysis.chapters:
        c = _sev_counts(list(ch.findings))
        rows.append(
            f"<tr><td>{escape(ch.title or f'Chapter {ch.index}')}</td>"
            f'<td style="color:{_SEV_COLOR["high"]}">{c["high"]}</td>'
            f'<td style="color:{_SEV_COLOR["medium"]}">{c["medium"]}</td>'
            f'<td style="color:{_SEV_COLOR["low"]}">{c["low"]}</td></tr>'
        )
    return (
        "<table class='heatmap'><tr><th>Chapter</th><th>High</th>"
        "<th>Med</th><th>Low</th></tr>" + "".join(rows) + "</table>"
    )


def _writer_block(analysis: Analysis) -> str:
    items = "".join(
        f"<li>[{escape(f.severity)}] {escape(f.location)}: {escape(f.fix)}</li>"
        for f in analysis.all_findings
        if f.severity in ("high", "medium")
    )
    return f"<ul>{items or '<li>No high/medium fixes flagged.</li>'}</ul>"


_RECUR_COLOR = {"yes": "#c0392b", "no": "#27ae60", "unclear": "#e67e22"}


def _review_section(analysis: Analysis) -> str:
    if not analysis.review_themes and not analysis.regression:
        return ""
    themes = "".join(
        f"<li><b>{escape(th.theme)}</b> ({escape(th.frequency)})"
        + (f" — <i>{escape(th.example)}</i>" if th.example else "")
        + "</li>"
        for th in analysis.review_themes
    )
    checks = "".join(
        f"<tr><td>{escape(rc.theme)}</td>"
        f'<td style="color:{_RECUR_COLOR.get(rc.recurs, "#7f8c8d")};'
        f'font-weight:bold">{escape(rc.recurs.upper())}</td>'
        f"<td>{escape(rc.evidence)}</td></tr>"
        for rc in analysis.regression
    )
    out = "<h2>Reader complaints (related book)</h2>"
    if themes:
        out += f"<ul>{themes}</ul>"
    if checks:
        out += (
            "<h3>Does this manuscript repeat them?</h3>"
            "<table class='heatmap'><tr><th>Complaint</th><th>Recurs?</th>"
            "<th>Evidence</th></tr>" + checks + "</table>"
        )
    return out


def render_html(analysis: Analysis, title: str = "Manuscript analysis") -> str:
    """Build the full HTML report. Pure — no I/O."""
    s = analysis.synthesis
    vcolor = _VERDICT_COLOR.get(s.verdict, "#7f8c8d")
    top = "".join(_finding_card(f) for f in analysis.top_issues(3))
    detail = "".join(
        f"<h3>{escape(ch.title or f'Chapter {ch.index}')}</h3>"
        + ("".join(_finding_card(f) for f in ch.findings) or "<p>No issues found.</p>")
        for ch in analysis.chapters
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{font-family:Georgia,serif;color:#222;margin:40px;line-height:1.5}}
h1{{margin:0 0 4px}} .sub{{color:#888;margin-bottom:24px}}
.verdict{{display:inline-block;padding:6px 16px;border-radius:6px;color:#fff;
font-weight:bold;background:{vcolor};font-family:sans-serif}}
.score{{font-size:42px;font-weight:bold;margin-left:16px}}
.grid{{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}}
.metric{{background:#f5f5f5;border-radius:6px;padding:10px 14px;min-width:120px}}
.metric .label{{font-size:11px;color:#888;text-transform:uppercase;
font-family:sans-serif}}
.metric .value{{font-size:18px;font-weight:bold}}
.finding{{background:#fafafa;padding:10px 14px;margin:8px 0;border-radius:4px}}
.finding .sev{{font-size:11px;font-weight:bold;font-family:sans-serif}}
.finding blockquote{{margin:6px 0;color:#555;font-style:italic;
border-left:2px solid #ddd;padding-left:10px}}
.heatmap{{border-collapse:collapse;font-family:sans-serif;font-size:13px}}
.heatmap th,.heatmap td{{border:1px solid #eee;padding:4px 10px;text-align:left}}
.pagebreak{{page-break-before:always}}
h2{{border-bottom:2px solid #eee;padding-bottom:4px;margin-top:32px}}
</style></head><body>
<h1>{escape(title)}</h1><div class="sub">bookcraft analysis</div>
<div><span class="verdict">{escape(s.verdict.upper())}</span>
<span class="score" style="color:{vcolor}">{s.score}
<span style="font-size:16px;color:#888">/100</span></span></div>
<p>{escape(s.summary)}</p>
<div class="grid">{_metrics_grid(analysis)}</div>
<h2>Opening (Look Inside)</h2><p>{escape(s.opening_assessment)}</p>
<h2>Top issues</h2>{top or "<p>None flagged.</p>"}
<h2>Chapter heatmap</h2>{_heatmap(analysis)}
{_review_section(analysis)}
<h2>Send to your writer</h2>{_writer_block(analysis)}
<div class="pagebreak"></div><h2>Full detail</h2>{detail}
</body></html>"""


def write_pdf(
    analysis: Analysis, output_path: Path, title: str = "Manuscript analysis"
) -> None:
    """Render the report to PDF via Playwright (Chromium)."""
    from playwright.sync_api import sync_playwright

    html = render_html(analysis, title=title)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.pdf(path=str(output_path), format="A4", print_background=True)
        browser.close()
