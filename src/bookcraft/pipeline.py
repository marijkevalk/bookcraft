"""Shared format pipeline used by both the CLI and the local web UI.

`format_book` runs the full manuscript -> formatted-docx flow once, so the
`format` command and the web UI cannot drift apart. It takes an already
parsed :class:`BookMetadata` (the CLI reads it from a file, the UI builds
it from form fields) and returns the paths it wrote.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from docx import Document

from bookcraft.ai_chapters import (
    DEFAULT_BACKEND,
    DEFAULT_CLAUDE_BIN,
    detect_chapters_ai,
    detect_sneak_preview,
)
from bookcraft.formatter import render
from bookcraft.metadata import BookMetadata
from bookcraft.template_builder import build_docxtpl_template


@dataclass
class FormatResult:
    """What `format_book` produced."""

    ebook_path: Path
    paperback_path: Path
    chapter_count: int
    chapter_titles: list[str]
    sneak_preview_paragraphs: int

    @property
    def summary(self) -> str:
        return (
            f"{self.chapter_count} chapters: " + ", ".join(self.chapter_titles)
        )


def bundled_template_path() -> Path:
    """Absolute path to the template shipped inside the package.

    Used as the default styled template so an end user never has to supply
    one. `resources.files` resolves correctly both from a normal install
    and from a PyInstaller bundle.
    """
    return Path(str(resources.files("bookcraft.assets") / "template.docx"))


def format_book(
    *,
    source_path: Path,
    metadata: BookMetadata,
    output_path: Path,
    template_path: Path | None = None,
    backend: str = DEFAULT_BACKEND,
    model: str | None = None,
    api_key: str | None = None,
    claude_bin: str = DEFAULT_CLAUDE_BIN,
) -> FormatResult:
    """Format one manuscript into ebook + paperback .docx files.

    Returns the written paths. Raises ``ValueError`` if no chapters are
    detected. ``template_path`` defaults to the bundled standard template.
    """
    template = template_path or bundled_template_path()
    source_doc = Document(str(source_path))

    chapters = detect_chapters_ai(
        source_doc,
        backend=backend,
        model=model,
        api_key=api_key,
        claude_bin=claude_bin,
    )
    if not chapters:
        raise ValueError(f"No chapters detected in {source_path.name}")

    sneak_preview = detect_sneak_preview(source_doc)

    paperback_path = output_path.with_name(
        output_path.stem + "_paperback" + output_path.suffix
    )

    with tempfile.TemporaryDirectory() as tmp:
        ebook_tpl = Path(tmp) / "template-ebook.docx"
        pb_tpl = Path(tmp) / "template-paperback.docx"
        build_docxtpl_template(template, ebook_tpl, ebook=True)
        build_docxtpl_template(template, pb_tpl, ebook=False)
        render(
            ebook_tpl, metadata, chapters, output_path,
            sneak_preview_body=sneak_preview,
        )
        render(
            pb_tpl, metadata, chapters, paperback_path,
            sneak_preview_body=sneak_preview,
        )

    return FormatResult(
        ebook_path=output_path,
        paperback_path=paperback_path,
        chapter_count=len(chapters),
        chapter_titles=[c.title for c in chapters],
        sneak_preview_paragraphs=len(sneak_preview),
    )
