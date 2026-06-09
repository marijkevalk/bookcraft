"""Render a manuscript into a styled book .docx using a docxtpl template.

The template is created by `template_builder.build_docxtpl_template` from
the user's original styled .docx — it carries placeholders for front matter
and a `{%p for chapter in chapters %}` loop for the body. This module just
calls docxtpl to render that template against the detected chapters.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate, RichText

from bookcraft.ai_chapters import Chapter
from bookcraft.metadata import BookMetadata


def _coerce_body_items(items: list[Any]) -> list[RichText]:
    """Strings get wrapped in a single-run RichText; RichText passes through.

    The template uses `{{r body_para }}` which requires RichText values.
    Allowing strings in `Chapter.body` keeps the API simple for tests
    and synthetic-data callers.
    """
    out: list[RichText] = []
    for item in items:
        if isinstance(item, RichText):
            out.append(item)
        else:
            rt = RichText()
            rt.add(str(item))
            out.append(rt)
    return out


def render(
    template_path: Path,
    metadata: BookMetadata,
    chapters: list[Chapter],
    output_path: Path,
    sneak_preview_body: list[Any] | None = None,
) -> None:
    if not chapters:
        raise ValueError("No chapters detected in source document")

    tpl = DocxTemplate(str(template_path))
    tpl.render(
        {
            "title": metadata.title,
            "subtitle": metadata.subtitle,
            "series": metadata.series,
            "pen_name": metadata.pen_name,
            "book_number": metadata.book_number,
            "about_the_author": metadata.about_the_author,  # list[str]
            "year": datetime.now().year,
            "chapters": [
                {
                    "title": c.title,
                    "pov": c.pov,
                    "body": _coerce_body_items(c.body),
                }
                for c in chapters
            ],
            "sneak_preview_body": _coerce_body_items(sneak_preview_body or []),
        }
    )
    tpl.save(str(output_path))
