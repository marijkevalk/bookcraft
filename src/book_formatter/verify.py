"""Character-level verification: source manuscript vs rendered output.

Compares each body paragraph in the source `.docx` (detected via the AI
chapter detector) against the corresponding paragraph in the rendered
output. Comparison covers text content and italic-run positions. Results
are grouped per chapter so the per-paragraph table is split into one
section per chapter.

Body prose is the only thing we compare — chapter titles, POV markers,
front matter, TOC and back matter all live in the template, not the source.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from book_formatter.ai_chapters import detect_chapters_heuristic

CHAPTER_TITLE_STYLE = "CSP - Chapter Title"
FRONT_MATTER_BODY_STYLE = "CSP - Front Matter Body Text"
BODY_STYLES = (
    "CSP - Chapter Body Text",
    "CSP - Chapter Body Text - First Paragraph",
)


@dataclass
class ParagraphCheck:
    index: int
    source_text: str
    output_text: str
    source_italic_marked: str
    output_italic_marked: str

    @property
    def source_chars(self) -> int:
        return len(self.source_text)

    @property
    def output_chars(self) -> int:
        return len(self.output_text)

    @property
    def text_match(self) -> bool:
        return self.source_text == self.output_text

    @property
    def italic_match(self) -> bool:
        return self.source_italic_marked == self.output_italic_marked


@dataclass
class ChapterCheck:
    number: int
    title: str  # e.g. "CHAPTER ONE"
    pov: str  # e.g. "Aria"
    paragraphs: list[ParagraphCheck] = field(default_factory=list)
    source_para_count: int = 0
    output_para_count: int = 0

    @property
    def source_chars(self) -> int:
        return sum(p.source_chars for p in self.paragraphs)

    @property
    def output_chars(self) -> int:
        return sum(p.output_chars for p in self.paragraphs)

    @property
    def text_mismatches(self) -> int:
        return sum(1 for p in self.paragraphs if not p.text_match)

    @property
    def italic_mismatches(self) -> int:
        return sum(1 for p in self.paragraphs if not p.italic_match)


@dataclass
class VerifyResult:
    chapters: list[ChapterCheck] = field(default_factory=list)
    source_chapter_count: int = 0
    output_chapter_count: int = 0

    @property
    def all_paragraphs(self) -> list[ParagraphCheck]:
        return [p for c in self.chapters for p in c.paragraphs]

    @property
    def source_para_count(self) -> int:
        return sum(c.source_para_count for c in self.chapters)

    @property
    def output_para_count(self) -> int:
        return sum(c.output_para_count for c in self.chapters)

    @property
    def total_source_chars(self) -> int:
        return sum(c.source_chars for c in self.chapters)

    @property
    def total_output_chars(self) -> int:
        return sum(c.output_chars for c in self.chapters)

    @property
    def text_mismatches(self) -> int:
        return sum(c.text_mismatches for c in self.chapters)

    @property
    def italic_mismatches(self) -> int:
        return sum(c.italic_mismatches for c in self.chapters)

    @property
    def content_clean(self) -> bool:
        """True when all compared paragraphs have matching text and italic runs."""
        return self.text_mismatches == 0 and self.italic_mismatches == 0

    @property
    def structure_clean(self) -> bool:
        """True when chapter and paragraph counts match between source and output."""
        return (
            self.source_chapter_count == self.output_chapter_count
            and self.source_para_count == self.output_para_count
        )

    @property
    def all_clear(self) -> bool:
        return self.content_clean and self.structure_clean


_RUN_RE = re.compile(r"<w:r[^>]*>(.*?)</w:r>", re.DOTALL)
_ITALIC_RE = re.compile(r"<w:i\s*/>|<w:i\s+w:val=\"(?:true|1)\"\s*/>")
_T_RE = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")


def _rich_text_runs(rt: object) -> list[tuple[str, bool]]:
    runs: list[tuple[str, bool]] = []
    xml: str = getattr(rt, "xml", "") or ""
    for match in _RUN_RE.finditer(xml):
        run_xml = match.group(1)
        italic = bool(_ITALIC_RE.search(run_xml))
        text_match = _T_RE.search(run_xml)
        text = html.unescape(text_match.group(1)) if text_match else ""
        if text:
            runs.append((text, italic))
    return runs


def _output_paragraph_runs(p: Paragraph) -> list[tuple[str, bool]]:
    runs: list[tuple[str, bool]] = []
    for run in p.runs:
        if not run.text:
            continue
        rPr = run._element.find(qn("w:rPr"))
        italic = False
        if rPr is not None:
            i_el = rPr.find(qn("w:i"))
            if i_el is not None and i_el.get(qn("w:val")) != "0":
                italic = True
        runs.append((run.text, italic))
    return runs


def _runs_to_plain(runs: list[tuple[str, bool]]) -> str:
    return "".join(t for t, _ in runs)


def _runs_to_italic_marked(runs: list[tuple[str, bool]]) -> str:
    return "".join(f"*{t}*" if it else t for t, it in runs)


def _extract_output_chapters(
    doc: DocxDocument,
) -> list[tuple[str, list[list[tuple[str, bool]]]]]:
    """Walk the rendered output and split body into chapters.

    Returns a list of (title, [run-tuples-per-paragraph]) — one per chapter.
    Stops at the first paragraph styled CSP - Front Matter Body Text after
    the first chapter title (back matter marker).
    """
    chapters: list[tuple[str, list[list[tuple[str, bool]]]]] = []
    current_title: str | None = None
    current_body: list[list[tuple[str, bool]]] = []
    in_back_matter = False
    for p in doc.paragraphs:
        if in_back_matter:
            break
        style = p.style.name if p.style is not None else ""
        text = p.text.strip()
        if style == CHAPTER_TITLE_STYLE and text.startswith("CHAPTER "):
            if current_title is not None:
                chapters.append((current_title, current_body))
            current_title = text
            current_body = []
        elif style == CHAPTER_TITLE_STYLE and current_title is not None:
            # Non-chapter title (SNEAK PREVIEW, ABOUT THE AUTHOR, etc.) — stop.
            in_back_matter = True
        elif style == FRONT_MATTER_BODY_STYLE and current_title is not None:
            in_back_matter = True
        elif style in BODY_STYLES and current_title is not None:
            runs = _output_paragraph_runs(p)
            if runs:
                current_body.append(runs)
    if current_title is not None:
        chapters.append((current_title, current_body))
    return chapters


def verify(source_path: Path, output_path: Path) -> VerifyResult:
    source = Document(str(source_path))
    output = Document(str(output_path))

    src_chapters = detect_chapters_heuristic(source)
    out_chapters = _extract_output_chapters(output)

    result = VerifyResult(
        source_chapter_count=len(src_chapters),
        output_chapter_count=len(out_chapters),
    )

    for src_ch, out_pair in zip(src_chapters, out_chapters, strict=False):
        out_title, out_body = out_pair
        src_runs_list = [_rich_text_runs(item) for item in src_ch.body]

        chapter_check = ChapterCheck(
            number=src_ch.number,
            title=out_title,
            pov=src_ch.pov,
            source_para_count=len(src_runs_list),
            output_para_count=len(out_body),
        )

        for j, (s_runs, o_runs) in enumerate(
            zip(src_runs_list, out_body, strict=False)
        ):
            chapter_check.paragraphs.append(
                ParagraphCheck(
                    index=j,
                    source_text=_runs_to_plain(s_runs),
                    output_text=_runs_to_plain(o_runs),
                    source_italic_marked=_runs_to_italic_marked(s_runs),
                    output_italic_marked=_runs_to_italic_marked(o_runs),
                )
            )
        result.chapters.append(chapter_check)

    return result


def _format_chapter_section(c: ChapterCheck) -> list[str]:
    header_line = f"CHAPTER {c.number}"
    if c.title and c.title != header_line:
        header_line = c.title
    if c.pov:
        header_line = f"{header_line} — {c.pov}"
    bar = "=" * 78

    lines = [
        "",
        bar,
        header_line,
        bar,
        f"Paragraphs:  {c.source_para_count} source, {c.output_para_count} output",
        f"Characters:  {c.source_chars:,} source, {c.output_chars:,} output",
        (
            f"Mismatches:  text {c.text_mismatches} / {len(c.paragraphs)},  "
            f"italic {c.italic_mismatches} / {len(c.paragraphs)}"
        ),
        "",
    ]
    header = (
        f"{'para':>5}  {'src_chars':>10}  {'out_chars':>10}  "
        f"{'text':>6}  {'italic':>7}"
    )
    lines.append(header)
    lines.append("-" * 78)
    for p in c.paragraphs:
        lines.append(
            f"{p.index:>5}  {p.source_chars:>10}  {p.output_chars:>10}  "
            f"{'OK' if p.text_match else 'DIFF':>6}  "
            f"{'OK' if p.italic_match else 'DIFF':>7}"
        )

    if c.source_para_count != c.output_para_count:
        lines.append("")
        lines.append(
            f"⚠️ paragraph-count mismatch in this chapter: "
            f"{c.source_para_count} source vs {c.output_para_count} output"
        )

    mismatches = [
        p for p in c.paragraphs if not p.text_match or not p.italic_match
    ]
    if mismatches:
        lines.append("")
        lines.append("Mismatch details for this chapter:")
        for p in mismatches:
            lines.append(f"\n  Para {p.index}:")
            if not p.text_match:
                lines.append(
                    f"    TEXT source ({p.source_chars} chars): "
                    f"{p.source_text!r}"
                )
                lines.append(
                    f"    TEXT output ({p.output_chars} chars): "
                    f"{p.output_text!r}"
                )
                for i, (cs, co) in enumerate(
                    zip(p.source_text, p.output_text, strict=False)
                ):
                    if cs != co:
                        lines.append(
                            f"    first text diff at char {i}: "
                            f"src={cs!r} (U+{ord(cs):04X}) vs "
                            f"out={co!r} (U+{ord(co):04X})"
                        )
                        break
            if not p.italic_match:
                lines.append(
                    f"    ITALIC source: {p.source_italic_marked!r}"
                )
                lines.append(
                    f"    ITALIC output: {p.output_italic_marked!r}"
                )
    return lines


def format_report(
    result: VerifyResult, *, source_path: Path, output_path: Path
) -> str:
    lines: list[str] = []
    bar = "=" * 78
    lines.append(bar)
    lines.append("BOOK-FORMATTER VERIFICATION REPORT")
    lines.append(bar)
    lines.append(f"source: {source_path}")
    lines.append(f"output: {output_path}")
    lines.append("")
    lines.append(
        "Body paragraphs are detected in the source via the AI chapter"
    )
    lines.append(
        "detector (chapter title lines and POV-marker lines are excluded)."
    )
    lines.append(
        "The output's body paragraphs are those styled CSP - Chapter Body"
    )
    lines.append("Text or its First Paragraph variant.")
    lines.append("")
    lines.append("Per-paragraph columns (one row per body paragraph):")
    lines.append(
        "  para        - body paragraph index within the chapter (0 = first)"
    )
    lines.append("  src_chars   - number of characters in the source paragraph")
    lines.append(
        "  out_chars   - number of characters in the rendered output paragraph"
    )
    lines.append(
        "  text        - OK if text content matches verbatim, DIFF otherwise"
    )
    lines.append(
        "  italic      - OK if italic-run positions match, DIFF otherwise"
    )
    lines.append("")
    lines.append(bar)
    lines.append("OVERALL SUMMARY")
    lines.append(bar)
    lines.append(
        f"Chapters detected: {result.source_chapter_count} source, "
        f"{result.output_chapter_count} output"
    )
    lines.append(
        f"Body paragraphs:  {result.source_para_count} source, "
        f"{result.output_para_count} output"
    )
    lines.append(
        f"Total characters: {result.total_source_chars:,} source, "
        f"{result.total_output_chars:,} output"
    )
    lines.append(
        f"Text mismatches:   {result.text_mismatches} / "
        f"{len(result.all_paragraphs)}"
    )
    lines.append(
        f"Italic mismatches: {result.italic_mismatches} / "
        f"{len(result.all_paragraphs)}"
    )
    if result.all_clear:
        verdict = "✓ ALL CLEAR"
    elif result.content_clean:
        verdict = (
            "✓ CONTENT OK — structure mismatch only "
            f"({result.source_chapter_count} source chapters vs "
            f"{result.output_chapter_count} output; Claude may have missed a "
            "chapter heading — check the output manually)"
        )
    else:
        verdict = "⚠️ CONTENT MISMATCHES FOUND"
    lines.append(f"Verdict: {verdict}")

    for chapter in result.chapters:
        lines.extend(_format_chapter_section(chapter))

    return "\n".join(lines) + "\n"


def default_report_path(output_path: Path) -> Path:
    """Default location for the .txt report: alongside the output file."""
    return output_path.with_name(output_path.stem + "_verification.txt")
