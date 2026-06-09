"""Parse the per-book metadata file (key: value lines)."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BookMetadata:
    title: str
    subtitle: str
    series: str
    pen_name: str
    book_number: str = "1"
    about_the_author: list[str] = field(default_factory=list)


# Canonical keys we expect, with aliases for tolerance.
_ALIASES = {
    "title": "title", "titel": "title",
    "subtitle": "subtitle", "genre": "subtitle", "genre / subtitle": "subtitle",
    "series": "series",
    "pen name": "pen_name", "pen_name": "pen_name", "author": "pen_name",
    "book number": "book_number", "book_number": "book_number",
    "boek nummer": "book_number", "boek number": "book_number",
    "about the author": "about_the_author", "about_the_author": "about_the_author",
    "over de auteur": "about_the_author",
}


def parse_metadata_file(path: Path) -> BookMetadata:
    """Parse a key: value metadata file.

    Lines after 'About the Author:' that are not themselves a known key are
    treated as additional paragraphs of the author bio (one paragraph per line).
    """
    raw: dict[str, str] = {}
    about_paragraphs: list[str] = []
    current_key: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        canonical: str | None = None
        value_part = ""
        if ":" in stripped:
            key_part, _, val = stripped.partition(":")
            canonical = _ALIASES.get(key_part.strip().lower())
            if canonical:
                value_part = val.strip()

        if canonical:
            current_key = canonical
            if canonical == "about_the_author":
                if value_part:
                    about_paragraphs.append(value_part)
            else:
                if value_part:
                    raw[canonical] = value_part
        elif current_key == "about_the_author":
            # Continuation line: another paragraph of the author bio.
            about_paragraphs.append(stripped)

    missing = {"title", "subtitle", "series", "pen_name"} - raw.keys()
    if missing:
        raise ValueError(f"Metadata file {path} missing keys: {sorted(missing)}")

    return BookMetadata(
        title=raw["title"],
        subtitle=raw["subtitle"],
        series=raw["series"],
        pen_name=raw["pen_name"],
        book_number=raw.get("book_number", "1"),
        about_the_author=about_paragraphs,
    )
