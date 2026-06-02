"""Tests for book-formatter."""

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from docx import Document

from book_formatter.ai_chapters import (
    Chapter,
    _build_chapters,
    _candidate_lines,
    detect_sneak_preview,
    number_to_words,
)
from book_formatter.formatter import render
from book_formatter.main import cli
from book_formatter.metadata import BookMetadata, parse_metadata_file
from book_formatter.template_builder import build_docxtpl_template

FIXTURES = Path(__file__).parent / "fixtures"


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_number_to_words():
    assert number_to_words(1) == "ONE"
    assert number_to_words(20) == "TWENTY"
    assert number_to_words(21) == "TWENTY-ONE"
    with pytest.raises(ValueError):
        number_to_words(0)
    with pytest.raises(ValueError):
        number_to_words(100)


def test_parse_metadata():
    meta = parse_metadata_file(FIXTURES / "book_metadata.txt")
    assert meta.title == "Claimed by the Enemy"
    assert meta.subtitle == "A Steamy Mafia Romance"
    assert meta.series == "Claimed Series"
    assert meta.pen_name == "Sylvia Heart"
    assert meta.about_the_author[0] == "Sylvia Heart is a romance author who loves writing about love and suspense."
    assert meta.about_the_author[1] == "She lives in the Netherlands with her cats and a very patient husband."


def test_candidate_lines_filters_long_paragraphs():
    doc = Document(str(FIXTURES / "book_author_A.docx"))
    candidates = _candidate_lines(doc)
    for _idx, style, text in candidates:
        assert len(text) <= 80 or style.lower().startswith("heading")
    cand_texts = {c[2] for c in candidates}
    assert "Chapter 1: Aria" in cand_texts


def test_candidate_lines_keeps_all_heading_styled():
    doc = Document(str(FIXTURES / "book_author_B.docx"))
    candidates = _candidate_lines(doc)
    heading_candidates = [c for c in candidates if c[1] == "Heading 1"]
    assert len(heading_candidates) == 4


def _rich_text_to_str(rt) -> str:
    """Extract plain text from a docxtpl RichText by walking its XML."""
    import re
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", rt.xml))


def test_build_chapters_formats_title_as_chapter_word():
    """Chapter.title is rendered as 'CHAPTER ONE' etc., POV stays separate."""
    doc = Document(str(FIXTURES / "book_author_A.docx"))
    claude_output = [
        {"title_idx": 0, "pov_idx": -1, "pov": "Aria"},
        {"title_idx": 102, "pov_idx": -1, "pov": "Ryder"},
    ]
    chapters = _build_chapters(doc, claude_output)
    assert len(chapters) == 2
    assert chapters[0].title == "CHAPTER ONE"
    assert chapters[0].pov == "Aria"
    assert chapters[1].title == "CHAPTER TWO"
    assert chapters[1].pov == "Ryder"
    expected = doc.paragraphs[1].text.strip()
    assert _rich_text_to_str(chapters[0].body[0]) == expected


def test_build_chapters_preserves_italic_runs():
    """Italic in source body must be preserved as run-level italic in RichText."""
    doc = Document(str(FIXTURES / "book_author_B.docx"))
    # book_author_B paragraph 2 is "\tI hate this." in italic.
    # We use a hand-crafted chapter list (no AI) to isolate the conversion.
    claude_output = [{"title_idx": 0, "pov_idx": 1, "pov": "Fiona"}]
    chapters = _build_chapters(doc, claude_output)
    body_xml = chapters[0].body[0].xml
    # The italic toggle must be on the first run.
    assert "<w:i/>" in body_xml or '<w:i w:val="true"' in body_xml
    # And the text must be the source text verbatim (after strip).
    assert "I hate this" in body_xml


def test_detect_sneak_preview_no_section():
    doc = Document(str(FIXTURES / "book_author_A.docx"))
    assert detect_sneak_preview(doc) == []


def test_build_template_creates_docxtpl_markers(tmp_path):
    output = tmp_path / "template-docxtpl.docx"
    build_docxtpl_template(FIXTURES / "template.docx", output)

    doc = Document(str(output))
    texts = [p.text for p in doc.paragraphs]

    assert "{{ title }}" in texts
    assert "{{ subtitle }}" in texts
    assert "{{ series }}" in texts
    assert "Book {{ book_number }}" in texts
    assert "By: {{ pen_name }}" in texts
    assert "{%p for about_para in about_the_author %}" in texts
    assert "{{ about_para }}" in texts
    assert "{%p for chapter in chapters %}" in texts
    assert "{%p if not loop.first %}" not in texts  # ebook: break is unconditional
    assert "{%p endif %}" in texts  # still present from sneak preview block
    assert "{{ chapter.title }}" in texts
    assert "{{ chapter.pov }}" in texts
    assert "{%p for body_para in chapter.body %}" in texts
    assert "{{r body_para }}" in texts
    assert texts.count("{%p endfor %}") == 4
    assert "{%p if sneak_preview_body %}" in texts
    assert "{%p for sneak_para in sneak_preview_body %}" in texts
    assert "{{r sneak_para }}" in texts
    assert "{%p endif %}" in texts


def test_render_with_docxtpl_template(tmp_path):
    template_out = tmp_path / "template-docxtpl.docx"
    build_docxtpl_template(FIXTURES / "template.docx", template_out)

    meta = BookMetadata(
        title="Test Title",
        subtitle="Test Subtitle",
        series="Test Series",
        pen_name="Test Pen",
        book_number="3",
        about_the_author=["Test Pen is a bestselling author.", "She lives in Amsterdam."],
    )
    chapters = [
        Chapter(number=1, title="CHAPTER ONE", pov="Aria", body=["Body 1.", "Body 2."]),
        Chapter(number=2, title="CHAPTER TWO", pov="Ryder", body=["Ryder line."]),
    ]

    output = tmp_path / "out.docx"
    render(template_out, meta, chapters, output)

    result = Document(str(output))
    texts = [p.text.strip() for p in result.paragraphs]
    assert "Test Title" in texts
    assert "Test Subtitle" in texts
    assert "Test Series" in texts
    assert "Book 3" in texts
    assert "By: Test Pen" in texts
    assert "Test Pen is a bestselling author." in texts
    assert "She lives in Amsterdam." in texts

    from docx.enum.text import WD_ALIGN_PARAGRAPH
    about_paras = [
        p for p in result.paragraphs
        if p.text.strip() in {"Test Pen is a bestselling author.", "She lives in Amsterdam."}
    ]
    assert len(about_paras) == 2
    for p in about_paras:
        assert p.alignment == WD_ALIGN_PARAGRAPH.CENTER, f"Expected center alignment on: {p.text!r}"

    chapter_titles = [
        p.text.strip() for p in result.paragraphs
        if p.style is not None and p.style.name == "CSP - Chapter Title"
    ]
    assert chapter_titles[:2] == ["CHAPTER ONE", "CHAPTER TWO"]
    assert "Aria" in texts
    assert "Ryder" in texts
    assert "THE END" in texts
    assert "ABOUT THE AUTHOR" in chapter_titles


def test_paperback_template_has_page_numbers_in_footer(tmp_path):
    output = tmp_path / "template-paperback.docx"
    build_docxtpl_template(FIXTURES / "template.docx", output, ebook=False)

    from lxml import etree
    doc = Document(str(output))

    # Only the last section (chapters) should have page numbers.
    last = doc.sections[-1]
    assert "PAGE" in etree.tostring(last.footer._element).decode(), \
        "Odd-page footer must contain PAGE field"
    assert "PAGE" in etree.tostring(last.even_page_footer._element).decode(), \
        "Even-page footer must contain PAGE field"

    # Pre-chapter sections must not have page numbers.
    for section in doc.sections[:-1]:
        assert "PAGE" not in etree.tostring(section.footer._element).decode(), \
            "Pre-chapter footer must not contain PAGE field"

    # A nextPage section break should be present before the chapter loop.
    from docx.oxml.ns import qn as _qn
    texts = [p.text for p in doc.paragraphs]
    assert "{%p for chapter in chapters %}" in texts
    # Chapter title paragraphs must have pageBreakBefore.
    chapter_titles = [
        p for p in doc.paragraphs
        if p.style and p.style.name == "CSP - Chapter Title"
        and "{{ chapter.title }}" in p.text
    ]
    assert len(chapter_titles) == 1
    pPr = chapter_titles[0]._element.find(_qn("w:pPr"))
    assert pPr is not None and pPr.find(_qn("w:pageBreakBefore")) is not None


def test_paperback_template_page_setup(tmp_path):
    from docx.shared import Mm, Cm
    from docx.oxml.ns import qn as _qn

    output = tmp_path / "template-paperback.docx"
    build_docxtpl_template(FIXTURES / "template.docx", output, ebook=False)

    doc = Document(str(output))

    tol = 500  # EMU tolerance for twips rounding (~0.5mm)
    for section in doc.sections:
        assert abs(section.page_width - Mm(152.4)) < tol, "Page width must be 152.4 mm"
        assert abs(section.page_height - Mm(228.6)) < tol, "Page height must be 228.6 mm"
        assert abs(section.top_margin - Cm(1.9)) < tol
        assert abs(section.bottom_margin - Cm(1.9)) < tol
        assert abs(section.left_margin - Cm(1.9)) < tol
        assert abs(section.right_margin - Cm(1.3)) < tol

    settings = doc.settings.element
    assert settings.find(_qn("w:mirrorMargins")) is not None, "Mirror margins must be set"


def test_render_rejects_empty_chapter_list(tmp_path):
    template_out = tmp_path / "template-docxtpl.docx"
    build_docxtpl_template(FIXTURES / "template.docx", template_out)
    meta = BookMetadata(title="t", subtitle="s", series="x", pen_name="p")
    with pytest.raises(ValueError, match="No chapters"):
        render(template_out, meta, [], tmp_path / "out.docx")


@pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="claude CLI not on PATH",
)
def test_ai_detector_on_author_a():
    """Integration test: shell out to `claude -p`. Skipped if CLI not found."""
    from book_formatter.ai_chapters import detect_chapters_ai

    doc = Document(str(FIXTURES / "book_author_A.docx"))
    chapters = detect_chapters_ai(doc)
    assert len(chapters) == 4
    assert [c.pov for c in chapters] == ["Aria", "Ryder", "Aria", "Ryder"]
    assert chapters[0].title == "CHAPTER ONE"


@pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="claude CLI not on PATH",
)
def test_ai_detector_on_author_b():
    from book_formatter.ai_chapters import detect_chapters_ai

    doc = Document(str(FIXTURES / "book_author_B.docx"))
    chapters = detect_chapters_ai(doc)
    assert len(chapters) == 4
    assert chapters[0].pov == "Fiona"
