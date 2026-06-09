"""Convert a styled book template (.docx) into a docxtpl-ready template.

Adds Jinja placeholders to the front matter and headers, replaces the
original TOC field + placeholder chapters with a self-contained fresh
TOC field plus a `{%p for chapter in chapters %}` loop, and uses the
template's dedicated body styles for proper book typography:
- `CSP - Chapter Body Text - First Paragraph` for the first body
  paragraph of each chapter (no first-line indent)
- `CSP - Chapter Body Text` for subsequent body paragraphs

`updateFields=true` is enabled so Word refreshes the TOC on open.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt
from docx.text.paragraph import Paragraph

CHAPTER_TITLE_STYLE = "CSP - Chapter Title"
FRONT_MATTER_BODY_STYLE = "CSP - Front Matter Body Text"
BODY_FIRST_PARA_STYLE = "CSP - Chapter Body Text - First Paragraph"
BODY_STYLE = "CSP - Chapter Body Text"
TOC_STYLE = "toc 1"
NORMAL_STYLE = "Normal"

# Ebook: \n suppresses page numbers; Paperback: page numbers shown.
EBOOK_TOC_INSTR = ' TOC \\o "1-3" \\h \\z \\n \\t "CSP - Chapter Title;1" '
PAPERBACK_TOC_INSTR = ' TOC \\o "1-3" \\h \\z \\t "CSP - Chapter Title;1" '

# POV: bold italic Garamond 14pt (matches template's "xxx" placeholder run).
POV_FONT = "Garamond"
POV_SIZE_PT = 14

# Page-break paragraph: sz=32 (=16pt) to match template's vertical breathing room
# between chapters.
PAGE_BREAK_SIZE_PT = 16

# Override the CSP - Chapter Body Text first-line indent to 720 twips (= 0.5").
# The style ships with 288 twips (0.2") which is correct for print typography
# but too subtle on-screen — the original template author worked around this
# by overriding indent at the paragraph level. We do the same at style level
# so the override applies everywhere consistently.
BODY_FIRST_LINE_INDENT_TWIPS = 720

# Match the template Normal-style spacing: 10pt after each paragraph + 1.15 line
# spacing. The CSP body style ships with after=0 and single line which is
# print-typography correct but visually cramps paragraphs on-screen.
BODY_SPACE_AFTER_TWIPS = 200       # = 10pt
BODY_LINE_SPACING_TWIPS = 276      # = 1.15 line spacing with lineRule=auto

_FRONT_MATTER_REPLACEMENTS = {
    "Title": "{{ title }}",
    "Subtitle": "{{ subtitle }}",
    "Series - Book 1": "{{ series }}",
    "By: Author": "By: {{ pen_name }}",
    "Copyright © 2026 by Author": "Copyright © {{ year }} by {{ pen_name }}",
    "Text about the author": "{{ about_para }}",
}

_HEADER_REPLACEMENTS = {
    "Book Name": "{{ title }}",
    "Author": "{{ pen_name }}",
}


def _set_paragraph_text(p: Paragraph, new_text: str) -> None:
    if p.runs:
        first = p.runs[0]
        first.text = new_text
        for run in p.runs[1:]:
            run.text = ""
    else:
        p.add_run(new_text)


def _delete_paragraph(p: Paragraph) -> None:
    p._element.getparent().remove(p._element)


def _ensure_pPr(p: Paragraph) -> Any:
    pPr = p._element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p._element.insert(0, pPr)
    return pPr


def _apply_run_format(
    p: Paragraph,
    *,
    font: str | None = None,
    size_pt: int | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    for run in p.runs:
        if font is not None:
            run.font.name = font
        if size_pt is not None:
            run.font.size = Pt(size_pt)
        if bold is not None:
            run.bold = bold
        if italic is not None:
            run.italic = italic


def _replace_front_matter_placeholders(doc: DocxDocument) -> None:
    for p in doc.paragraphs:
        current = p.text.strip()
        if current in _FRONT_MATTER_REPLACEMENTS:
            _set_paragraph_text(p, _FRONT_MATTER_REPLACEMENTS[current])


def _replace_running_headers(doc: DocxDocument) -> None:
    for section in doc.sections:
        for header in (
            section.header,
            section.first_page_header,
            section.even_page_header,
        ):
            for p in header.paragraphs:
                current = p.text.strip()
                if current in _HEADER_REPLACEMENTS:
                    _set_paragraph_text(p, _HEADER_REPLACEMENTS[current])


def _enable_update_fields_on_open(doc: DocxDocument) -> None:
    settings = doc.settings.element
    existing = settings.find(qn("w:updateFields"))
    if existing is None:
        node = OxmlElement("w:updateFields")
        node.set(qn("w:val"), "true")
        settings.append(node)
    else:
        existing.set(qn("w:val"), "true")


def _set_chapter_title_outline_level(doc: DocxDocument) -> None:
    """Mark CSP - Chapter Title as outline level 1 so Word's TOC picks it up."""
    style = doc.styles[CHAPTER_TITLE_STYLE]
    pPr = style.element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        style.element.append(pPr)
    outline = pPr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        pPr.append(outline)
    outline.set(qn("w:val"), "0")


def _override_chapter_title_font(doc: DocxDocument) -> None:
    """Set the CSP - Chapter Title style font to Garamond (template used Times New Roman)."""
    style = doc.styles[CHAPTER_TITLE_STYLE]
    rPr = style.element.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        style.element.append(rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), "Garamond")
    rFonts.set(qn("w:hAnsi"), "Garamond")


def _override_body_style(doc: DocxDocument) -> None:
    """Override CSP - Chapter Body Text style to match the template's actual
    visual behaviour (which uses Normal + manual overrides, not the CSP style):
    - firstLine indent 720 twips (0.5") instead of 288 (0.2") — visible on-screen
    - space-after 200 twips (10pt) instead of 0 — visible paragraph separation
    - line spacing 276/auto (1.15) instead of 240 (1.0) — matches template

    Applies to both body styles — the First Paragraph variant also gets
    the same firstLine indent so all body paragraphs are visually consistent.
    """
    style = doc.styles[BODY_STYLE]
    pPr = style.element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        style.element.append(pPr)

    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        pPr.append(ind)
    ind.set(qn("w:firstLine"), str(BODY_FIRST_LINE_INDENT_TWIPS))

    spacing = pPr.find(qn("w:spacing"))
    if spacing is None:
        spacing = OxmlElement("w:spacing")
        pPr.append(spacing)
    spacing.set(qn("w:after"), str(BODY_SPACE_AFTER_TWIPS))
    spacing.set(qn("w:line"), str(BODY_LINE_SPACING_TWIPS))
    spacing.set(qn("w:lineRule"), "auto")

    first_style = doc.styles[BODY_FIRST_PARA_STYLE]
    fp_pPr = first_style.element.find(qn("w:pPr"))
    if fp_pPr is None:
        fp_pPr = OxmlElement("w:pPr")
        first_style.element.append(fp_pPr)
    fp_ind = fp_pPr.find(qn("w:ind"))
    if fp_ind is None:
        fp_ind = OxmlElement("w:ind")
        fp_pPr.append(fp_ind)
    fp_ind.set(qn("w:firstLine"), str(BODY_FIRST_LINE_INDENT_TWIPS))


def _build_toc_field_paragraph(anchor: Paragraph, toc_instr: str) -> Paragraph:
    """Insert a fresh, self-contained Word TOC field paragraph before anchor."""
    para = anchor.insert_paragraph_before(style=TOC_STYLE)
    p_element = para._element

    r_begin = OxmlElement("w:r")
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    r_begin.append(fld_begin)
    p_element.append(r_begin)

    r_instr = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = toc_instr
    r_instr.append(instr)
    p_element.append(r_instr)

    r_sep = OxmlElement("w:r")
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    r_sep.append(fld_sep)
    p_element.append(r_sep)

    r_text = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "Right-click and Update Field to generate the table of contents."
    r_text.append(t)
    p_element.append(r_text)

    r_end = OxmlElement("w:r")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r_end.append(fld_end)
    p_element.append(r_end)

    return para


def _add_page_number_to_footer(footer: Any) -> None:
    """Replace all paragraphs in a footer with a single centered PAGE field."""
    for p in list(footer.paragraphs):
        p._element.getparent().remove(p._element)

    body = footer._element
    para = OxmlElement("w:p")
    body.append(para)

    pPr = OxmlElement("w:pPr")
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    pPr.append(jc)
    para.append(pPr)

    r_begin = OxmlElement("w:r")
    fc_begin = OxmlElement("w:fldChar")
    fc_begin.set(qn("w:fldCharType"), "begin")
    r_begin.append(fc_begin)
    para.append(r_begin)

    r_instr = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    r_instr.append(instr)
    para.append(r_instr)

    r_sep = OxmlElement("w:r")
    fc_sep = OxmlElement("w:fldChar")
    fc_sep.set(qn("w:fldCharType"), "separate")
    r_sep.append(fc_sep)
    para.append(r_sep)

    r_text = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "1"
    r_text.append(t)
    para.append(r_text)

    r_end = OxmlElement("w:r")
    fc_end = OxmlElement("w:fldChar")
    fc_end.set(qn("w:fldCharType"), "end")
    r_end.append(fc_end)
    para.append(r_end)


def _insert_section_break_before_chapters(anchor: Paragraph) -> Paragraph:
    """Insert a nextPage section break paragraph before anchor.

    Ends the pre-chapter section (TOC / front matter) and forces chapter 1
    to start on a new page. Subsequent chapters use pageBreakBefore on their
    title paragraph instead of a separate page-break paragraph.
    The new chapter section uses the document's final sectPr (modified
    by _add_page_numbers_to_footers) for its footer definitions.
    """
    para = anchor.insert_paragraph_before(style=NORMAL_STYLE)
    pPr = OxmlElement("w:pPr")
    sectPr = OxmlElement("w:sectPr")
    # No explicit type element = nextPage (the OOXML default).
    pPr.append(sectPr)
    para._element.insert(0, pPr)
    return para


def _add_page_numbers_to_footers(doc: DocxDocument) -> None:
    """Add centered page numbers to the chapter section only (last section).

    Adds to odd-page, even-page, and first-page footers so every chapter
    page — including the opening page of each chapter — shows a number.
    Pre-chapter sections (cover, copyright, TOC) keep empty footers: their
    pages are counted but the number is not displayed.

    Sections inherit footers from previous sections by default. We break
    that link for the chapter section so it gets its own distinct footer
    parts that we can fill with PAGE fields.
    """
    section = doc.sections[-1]

    # Remove titlePg from the chapter section so chapter 1 uses the same
    # header as all other chapters (titlePg would give it a blank first-page header).
    titlePg = section._sectPr.find(qn("w:titlePg"))
    if titlePg is not None:
        section._sectPr.remove(titlePg)

    # Unlink from previous to ensure this section gets new, distinct footer parts.
    section.footer.is_linked_to_previous = False
    section.even_page_footer.is_linked_to_previous = False
    _add_page_number_to_footer(section.footer)
    _add_page_number_to_footer(section.even_page_footer)


def _make_page_break_paragraph(anchor: Paragraph) -> Paragraph:
    """Insert an empty Normal paragraph with a page break + sz=32 to match
    the template's vertical breathing room between chapters.
    """
    para = anchor.insert_paragraph_before(style=NORMAL_STYLE)
    run = para.add_run()
    run.font.size = Pt(PAGE_BREAK_SIZE_PT)
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    run._element.append(br)
    return para


def _insert_chapter_title(anchor: Paragraph) -> Paragraph:
    """Chapter title: CSP - Chapter Title style, LEFT-aligned, pageBreakBefore.

    pageBreakBefore puts each chapter title at the top of a new page without
    needing a separate page-break paragraph (which can bleed onto its own
    blank page). Word ignores pageBreakBefore when the paragraph is already
    the first on a page (e.g. after a section break), so chapter 1 is safe.
    """
    p = anchor.insert_paragraph_before(
        text="{{ chapter.title }}", style=CHAPTER_TITLE_STYLE
    )
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pPr = _ensure_pPr(p)
    pgBr = OxmlElement("w:pageBreakBefore")
    pPr.append(pgBr)
    return p


def _insert_chapter_pov(anchor: Paragraph) -> Paragraph:
    """POV: Normal style with bold + italic Garamond 14pt, justified."""
    p = anchor.insert_paragraph_before(text="{{ chapter.pov }}", style=NORMAL_STYLE)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _apply_run_format(
        p, font=POV_FONT, size_pt=POV_SIZE_PT, bold=True, italic=True
    )
    return p


def _replace_toc_and_chapter_region(
    doc: DocxDocument, toc_instr: str, paperback: bool = False
) -> None:
    paragraphs = list(doc.paragraphs)
    first_toc_idx = next(
        (
            i for i, p in enumerate(paragraphs)
            if p.style is not None and p.style.name == TOC_STYLE
        ),
        None,
    )
    if first_toc_idx is None:
        raise RuntimeError(f"Template has no paragraph in style {TOC_STYLE!r}")

    first_chapter_idx = next(
        (
            i for i, p in enumerate(paragraphs)
            if p.style is not None and p.style.name == CHAPTER_TITLE_STYLE
        ),
        None,
    )
    if first_chapter_idx is None:
        raise RuntimeError(
            f"Template has no paragraph in style {CHAPTER_TITLE_STYLE!r}"
        )

    back_matter_idx = next(
        (
            i for i, p in enumerate(paragraphs)
            if i > first_chapter_idx
            and p.style is not None
            and p.style.name == FRONT_MATTER_BODY_STYLE
        ),
        None,
    )
    if back_matter_idx is None:
        raise RuntimeError(
            f"Template has no back matter marker (style "
            f"{FRONT_MATTER_BODY_STYLE!r}) after first chapter"
        )

    anchor = paragraphs[back_matter_idx]

    for p in paragraphs[first_toc_idx:back_matter_idx]:
        _delete_paragraph(p)

    # 1. Fresh self-contained TOC field.
    _build_toc_field_paragraph(anchor, toc_instr)

    # 2. Paperback: continuous section break splits TOC from chapters so
    #    only the chapter section gets footer page numbers.
    if paperback:
        _insert_section_break_before_chapters(anchor)

    # 3. Outer for-loop marker.
    anchor.insert_paragraph_before(
        text="{%p for chapter in chapters %}", style=NORMAL_STYLE
    )
    # 3b. Explicit page-break paragraph — visible as "---Page Break---" in
    #     Word's Show/Hide view.
    #
    #     Ebook: added unconditionally (all chapters, including chapter 1).
    #     Paperback: wrapped in {%p if not loop.first %} because chapter 1
    #     already gets a visible marker from the section break; an extra
    #     explicit break there would produce a blank page.
    if paperback:
        anchor.insert_paragraph_before(
            text="{%p if not loop.first %}", style=NORMAL_STYLE
        )
    pb_para = anchor.insert_paragraph_before(style=NORMAL_STYLE)
    pb_run = pb_para.add_run()
    pb_br = OxmlElement("w:br")
    pb_br.set(qn("w:type"), "page")
    pb_run._element.append(pb_br)
    if paperback:
        anchor.insert_paragraph_before(text="{%p endif %}", style=NORMAL_STYLE)
    # 4. Chapter title — pageBreakBefore forces each chapter to a new page.
    _insert_chapter_title(anchor)
    # 5. POV — bold italic Garamond.
    _insert_chapter_pov(anchor)
    # 6. Body loop — single style for all paragraphs (indent on all).
    anchor.insert_paragraph_before(
        text="{%p for body_para in chapter.body %}", style=NORMAL_STYLE
    )
    anchor.insert_paragraph_before(text="{{r body_para }}", style=BODY_STYLE)
    anchor.insert_paragraph_before(text="{%p endfor %}", style=NORMAL_STYLE)
    # 7. Close outer loop.
    anchor.insert_paragraph_before(text="{%p endfor %}", style=NORMAL_STYLE)


def _fix_copyright_page_break(doc: DocxDocument) -> None:
    """Ensure copyright starts on its own page (page 2, after the title page).

    The original section break at 'By: Author' is nextPage, which should put
    copyright on page 2. We reinforce this with pageBreakBefore on the
    copyright paragraph — Word ignores it if the paragraph is already at the
    top of a page, so there is no risk of a blank page.

    Also removes vAlign=center from the title sectPr: it is a print-layout
    artefact that can interfere with page flow in the paperback.
    """
    paragraphs = doc.paragraphs
    # Find the paragraph that has a sectPr in its pPr (= title section end).
    title_sectPr_para = next(
        (p for p in paragraphs
         if p._element.find(qn("w:pPr")) is not None
         and p._element.find(qn("w:pPr")).find(qn("w:sectPr")) is not None),
        None,
    )
    if title_sectPr_para is None:
        return

    # Remove vAlign=center from title sectPr — not meaningful for paperback.
    sectPr = title_sectPr_para._element.find(qn("w:pPr")).find(qn("w:sectPr"))
    vAlign = sectPr.find(qn("w:vAlign"))
    if vAlign is not None:
        sectPr.remove(vAlign)

    # Find the copyright paragraph (first non-empty paragraph after title sectPr).
    idx = paragraphs.index(title_sectPr_para)
    copyright_para = next(
        (p for p in paragraphs[idx + 1:] if p.text.strip()),
        None,
    )
    if copyright_para is None:
        return

    # Add pageBreakBefore to copyright — guarantees a new page without
    # inserting a separate paragraph that could itself overflow to page 2.
    pPr = _ensure_pPr(copyright_para)
    if pPr.find(qn("w:pageBreakBefore")) is None:
        pPr.append(OxmlElement("w:pageBreakBefore"))


def _add_book_number_paragraph(doc: DocxDocument) -> None:
    """Insert 'Book {{ book_number }}' centered in Garamond 11pt after the series line."""
    paragraphs = list(doc.paragraphs)
    idx = next(
        (i for i, p in enumerate(paragraphs) if p.text.strip() == "{{ series }}"),
        None,
    )
    if idx is None:
        return
    style = paragraphs[idx].style.name if paragraphs[idx].style else NORMAL_STYLE
    if idx + 1 < len(paragraphs):
        p = paragraphs[idx + 1].insert_paragraph_before(
            text="Book {{ book_number }}", style=style
        )
    else:
        p = doc.add_paragraph("Book {{ book_number }}", style=style)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _apply_run_format(p, font="Garamond", size_pt=14)


def _wrap_about_the_author_with_loop(doc: DocxDocument) -> None:
    """Wrap the '{{ about_para }}' placeholder in a for-loop over about_the_author.

    _replace_front_matter_placeholders already changed 'Text about the author'
    to '{{ about_para }}'. Here we surround it with the loop markers so
    multi-paragraph bios render as separate paragraphs in the correct style.
    """
    paragraphs = list(doc.paragraphs)
    idx = next(
        (i for i, p in enumerate(paragraphs) if p.text.strip() == "{{ about_para }}"),
        None,
    )
    if idx is None:
        return
    anchor = paragraphs[idx]
    style = anchor.style.name if anchor.style else FRONT_MATTER_BODY_STYLE
    anchor.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # Add space-after so multiple bio paragraphs are visually separated.
    pPr = _ensure_pPr(anchor)
    spacing = pPr.find(qn("w:spacing"))
    if spacing is None:
        spacing = OxmlElement("w:spacing")
        pPr.append(spacing)
    spacing.set(qn("w:after"), "200")  # 10pt gap between bio paragraphs
    anchor.insert_paragraph_before(
        text="{%p for about_para in about_the_author %}", style=style
    )
    # Insert endfor after the anchor by inserting before the next paragraph.
    # If anchor is the last paragraph, append directly to the body element.
    if idx + 1 < len(paragraphs):
        paragraphs[idx + 1].insert_paragraph_before(
            text="{%p endfor %}", style=style
        )
    else:
        doc.add_paragraph("{%p endfor %}", style=style)


def _replace_sneak_preview_region(doc: DocxDocument) -> None:
    """Replace static sneak preview body with a conditional Jinja2 loop.

    Finds the 'SNEAK PEAK' heading and the next 'ABOUT THE AUTHOR' heading.
    Deletes everything between them and inserts a conditional loop over
    sneak_preview_body so the section is omitted entirely when the list is empty.
    """
    paragraphs = list(doc.paragraphs)

    sneak_idx = next(
        (
            i for i, p in enumerate(paragraphs)
            if p.style is not None
            and p.style.name == CHAPTER_TITLE_STYLE
            and p.text.strip().upper().startswith("SNEAK")
        ),
        None,
    )
    if sneak_idx is None:
        return

    about_idx = next(
        (
            i for i, p in enumerate(paragraphs)
            if i > sneak_idx
            and p.style is not None
            and p.style.name == CHAPTER_TITLE_STYLE
            and "ABOUT" in p.text.upper()
        ),
        None,
    )
    if about_idx is None:
        return

    sneak_heading = paragraphs[sneak_idx]
    anchor = paragraphs[about_idx]

    # Delete the static body between SNEAK PEAK and ABOUT THE AUTHOR.
    for p in paragraphs[sneak_idx + 1 : about_idx]:
        _delete_paragraph(p)

    # Wrap the SNEAK PEAK heading itself in the if-block so it is hidden
    # entirely when sneak_preview_body is empty.
    sneak_heading.insert_paragraph_before(
        text="{%p if sneak_preview_body %}", style=NORMAL_STYLE
    )
    # Body loop uses BODY_STYLE so paragraphs get Garamond, first-line indent,
    # and paragraph spacing consistent with the chapter body.
    anchor.insert_paragraph_before(
        text="{%p for sneak_para in sneak_preview_body %}", style=NORMAL_STYLE
    )
    anchor.insert_paragraph_before(text="{{r sneak_para }}", style=BODY_STYLE)
    anchor.insert_paragraph_before(text="{%p endfor %}", style=NORMAL_STYLE)
    anchor.insert_paragraph_before(text="{%p endif %}", style=NORMAL_STYLE)

    # Page break before ABOUT THE AUTHOR so it always starts on a fresh page.
    pPr = _ensure_pPr(anchor)
    if pPr.find(qn("w:pageBreakBefore")) is None:
        pPr.append(OxmlElement("w:pageBreakBefore"))


def _apply_paperback_page_setup(doc: DocxDocument) -> None:
    """Apply KDP 6×9 page size and mirror margins to all sections.

    Page size: 152.4 × 228.6 mm (6 × 9 inch)
    Margins: top/bottom/inside 1.9 cm, outside 1.3 cm, gutter 0, mirror margins.
    With mirror margins, left = inside (binding side) and right = outside.
    """
    for section in doc.sections:
        section.page_width = Mm(152.4)
        section.page_height = Mm(228.6)
        section.top_margin = Cm(1.9)
        section.bottom_margin = Cm(1.9)
        section.left_margin = Cm(1.9)   # inside (binding side)
        section.right_margin = Cm(1.3)  # outside
        pgMar = section._sectPr.find(qn("w:pgMar"))
        if pgMar is not None:
            pgMar.set(qn("w:gutter"), "0")

    settings = doc.settings.element
    if settings.find(qn("w:mirrorMargins")) is None:
        settings.append(OxmlElement("w:mirrorMargins"))


def build_docxtpl_template(
    source_template: Path, output_path: Path, ebook: bool = True
) -> None:
    doc = Document(str(source_template))
    _replace_front_matter_placeholders(doc)
    _add_book_number_paragraph(doc)
    _wrap_about_the_author_with_loop(doc)
    _replace_running_headers(doc)
    _set_chapter_title_outline_level(doc)
    _override_chapter_title_font(doc)
    _override_body_style(doc)
    toc_instr = EBOOK_TOC_INSTR if ebook else PAPERBACK_TOC_INSTR
    _replace_toc_and_chapter_region(doc, toc_instr, paperback=not ebook)
    _replace_sneak_preview_region(doc)
    if not ebook:
        _fix_copyright_page_break(doc)
        _apply_paperback_page_setup(doc)
        _add_page_numbers_to_footers(doc)
    _enable_update_fields_on_open(doc)
    doc.save(str(output_path))
