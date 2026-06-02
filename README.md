# book-formatter

Format a manuscript `.docx` into a styled book layout by merging it into a
template `.docx`. Uses your local **Claude Code CLI** for chapter
detection (no extra API key needed — bills against your Claude Code
subscription) and **docxtpl** for rendering. Your template stays the
source of truth for layout.

## Setup (one-time)

1. **Install deps**:
   ```bash
   uv sync
   ```

2. **Verify the `claude` CLI is on your PATH**:
   ```bash
   claude --version
   ```
   If not, install Claude Code first.

3. **Convert your styled template into a docxtpl-ready template**:
   ```bash
   uv run book-formatter build-template \
     --source path/to/your-template.docx \
     --output path/to/your-template-docxtpl.docx
   ```
   This adds `{{ title }}`, `{{ subtitle }}` etc. placeholders, replaces
   the placeholder chapters with a `{% for chapter %}` loop, and enables
   page numbers in the TOC field. Run again only if you tweak the
   source template in Word.

## Per-book usage

1. **Write `book_metadata.txt`** with the per-book values:
   ```
   Title: Claimed by the Enemy
   Subtitle: A Steamy Mafia Romance
   Series: Claimed Series
   Pen Name: Sylvia Heart
   ```

2. **Run the format command**:
   ```bash
   uv run book-formatter format \
     --template path/to/your-template-docxtpl.docx \
     --source path/to/manuscript.docx \
     --metadata path/to/book_metadata.txt \
     --output path/to/output.docx
   ```
   Claude detects chapter boundaries (works with any chapter format —
   "Chapter 1: Aria", "CHAPTER ONE" + POV line, "PROLOGUE", etc.). Body
   text is extracted verbatim from the source — Claude only sees short
   header-like paragraphs and never sees or rewrites prose.

3. **Open the output in Word**. When prompted "Update fields in this
   document?", click **Yes** — the Table of Contents will populate with
   chapter titles and page numbers. (Without the prompt: Ctrl+A then F9.)

## Development

```bash
uv run pytest          # tests (AI tests skip if `claude` CLI not on PATH)
uv run ruff check .    # lint
uv run mypy src        # type check
```
