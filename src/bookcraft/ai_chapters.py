"""AI-driven chapter detection with a pluggable model backend.

The chapter-detection call (candidate paragraphs -> chapters JSON) is
served by one of several interchangeable backends, all producing the
same `[{title_idx, pov_idx, pov}]` contract:

- ``claude``    — shell out to the local `claude -p` CLI. Reuses the
                  user's Claude Code auth (no API key) and bills against
                  their Claude Code subscription. This is the default so
                  existing VPS runs via `format-book.sh` are unchanged.
- ``gemini``    — POST the prompt to Google's Gemini API using the
                  caller's own `GEMINI_API_KEY`. Lets users run the tool
                  on their own machine, independent of anyone's Claude
                  subscription (Google's free tier is enough for this
                  small structural task).
- ``heuristic`` — zero-AI keyword detector (`detect_chapters_heuristic`).
                  No network, no account.

We deliberately do NOT use Claude's `--json-schema`: in agent mode
(which `-p` implies), schema-validated output is unreliable and
frequently returns an empty result. Asking for JSON in the prompt and
parsing the text output is the workaround. The Gemini backend, by
contrast, requests `application/json` output natively.

Only the SHORT paragraphs from the manuscript (likely headers) are sent
to Claude. Body prose is never seen by Claude — chapter bodies are
extracted verbatim from the source by paragraph index. This keeps cost
low and eliminates the risk of the model altering author content.

Chapter.title is formatted as "CHAPTER ONE", "CHAPTER TWO" etc. (matching
the template's house style). The POV name detected by Claude is in
Chapter.pov.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from docx.document import Document
from docx.text.paragraph import Paragraph as DocxParagraph
from docxtpl import RichText

logger = logging.getLogger(__name__)

MAX_CANDIDATE_CHARS = 80
DEFAULT_CLAUDE_BIN = "claude"
DEFAULT_TIMEOUT_SEC = 180

# Model backends selectable via detect_chapters_ai(backend=...).
BACKENDS = ("claude", "gemini", "heuristic")
DEFAULT_BACKEND = "claude"  # keeps existing VPS/format-book.sh runs unchanged

# Gemini (Google AI) backend — bring-your-own free API key.
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

_ONES = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]
_TEENS = [
    "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN",
    "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN",
]
_TENS = [
    "", "", "TWENTY", "THIRTY", "FORTY", "FIFTY",
    "SIXTY", "SEVENTY", "EIGHTY", "NINETY",
]


def number_to_words(n: int) -> str:
    """1 -> 'ONE', 21 -> 'TWENTY-ONE', etc. Supports 1-99."""
    if 1 <= n <= 9:
        return _ONES[n]
    if 10 <= n <= 19:
        return _TEENS[n - 10]
    if 20 <= n <= 99:
        tens, ones = divmod(n, 10)
        return _TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_ONES[ones]}"
    raise ValueError(f"Chapter number out of supported range (1-99): {n}")


@dataclass
class Chapter:
    """One detected chapter: number, formatted title, POV name, body paragraphs."""

    number: int
    title: str
    pov: str = ""
    body: list[str] = field(default_factory=list)


_PROMPT_TEMPLATE = """You parse the structure of manuscript .docx files.

Below is a list of short paragraphs from a manuscript with their original
paragraph indices, one per line as `[idx] (style) text`. Identify the
chapter boundaries.

Return ONE JSON object with this exact structure (no other text, no
markdown fences):

{{
  "chapters": [
    {{"title_idx": <int>, "pov_idx": <int>, "pov": "<string>"}},
    ...
  ]
}}

Per chapter:
- title_idx: paragraph index of the chapter heading
  (e.g. 'Chapter 1: Aria' or 'CHAPTER ONE').
- pov_idx: if the POV-character name appears on its own line right after
  the title, the paragraph index of that line; otherwise -1.
- pov: the POV character's name as a plain string (e.g. 'Aria').
  Empty string for prologue/epilogue/intro without a single POV.

Patterns to recognise:
- 'Chapter 1: Aria' -> pov_idx=-1, pov='Aria' (POV is in the title).
- 'Chapter 5' -> pov_idx=-1, pov=''.
- 'CHAPTER ONE' then 'Fiona' on the next line -> pov_idx is the 'Fiona'
  paragraph index, pov='Fiona'.
- PROLOGUE / EPILOGUE / INTERLUDE / PART ONE are chapters too. Use the
  heading text as pov if no separate name is given.

Do NOT invent chapters. Only report headings clearly present in the input.
If a short paragraph is dialogue, a stage direction or a chapter subtitle,
ignore it.

Candidate paragraphs:
{candidates}
"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _candidate_lines(doc: Document) -> list[tuple[int, str, str]]:
    """Return (idx, style, text) for paragraphs likely to be a header."""
    out: list[tuple[int, str, str]] = []
    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if not text:
            continue
        style = p.style.name if p.style is not None else ""
        is_heading_style = style.lower().startswith("heading")
        if is_heading_style or len(text) <= MAX_CANDIDATE_CHARS:
            out.append((i, style, text))
    logger.info("Candidate paragraphs found: %d", len(out))
    logger.debug("Candidates:\n%s", _format_candidates(out))
    return out


def _format_candidates(candidates: list[tuple[int, str, str]]) -> str:
    return "\n".join(f"[{idx}] ({style}) {text}" for idx, style, text in candidates)


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = _FENCE_RE.match(text)
    return m.group(1).strip() if m else text


def _parse_chapters_json(output: str, *, source: str) -> list[dict[str, Any]]:
    """Parse a backend's text output into the chapters list.

    Shared by every AI backend: strips any markdown fences, loads the JSON
    object and unwraps its ``chapters`` list. ``source`` names the backend
    for error messages/logging.
    """
    raw = _strip_fences(output)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse %s response as JSON:\n%s", source, output[:2000])
        raise RuntimeError(
            f"{source} returned non-JSON output:\n{output[:1000]}"
        ) from e

    chapters = payload.get("chapters", [])
    if not isinstance(chapters, list):
        raise RuntimeError(f"Response had non-list chapters: {chapters!r}")

    logger.info("%s returned %d chapters", source, len(chapters))
    logger.debug("%s chapters raw: %s", source, json.dumps(chapters, indent=2))
    return chapters


def _call_claude_cli(
    candidates: list[tuple[int, str, str]],
    *,
    claude_bin: str = DEFAULT_CLAUDE_BIN,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Invoke `claude -p` with a prompt that returns JSON; parse the text output."""
    binary = shutil.which(claude_bin) or claude_bin
    prompt = _PROMPT_TEMPLATE.format(candidates=_format_candidates(candidates))

    logger.info("Sending %d candidates to Claude (timeout %ds)", len(candidates), timeout)
    logger.debug("Full prompt sent to Claude:\n%s", prompt)

    # Pass prompt via stdin to avoid MAX_ARG_STRLEN (128 KB) OS limit.
    cmd = [binary, "-p", "/dev/stdin", "--output-format", "text"]

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Could not find `{claude_bin}` CLI. Install Claude Code or set "
            f"a custom binary via --claude-bin."
        ) from e
    except subprocess.CalledProcessError as e:
        logger.error(
            "claude CLI failed (exit %d)\nstdout: %s\nstderr: %s",
            e.returncode, e.stdout, e.stderr,
        )
        raise RuntimeError(
            f"claude CLI failed (exit {e.returncode}):\n"
            f"stdout: {e.stdout!r}\nstderr: {e.stderr!r}"
        ) from e

    logger.debug("Raw Claude response:\n%s", result.stdout)
    return _parse_chapters_json(result.stdout, source="claude")


def _call_gemini(
    candidates: list[tuple[int, str, str]],
    *,
    model: str = DEFAULT_GEMINI_MODEL,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Call Google's Gemini API with a JSON-output prompt; parse the result.

    Uses the caller's own API key (arg or ``GEMINI_API_KEY`` env), so the
    tool runs independently of any Claude Code subscription. Only the short
    candidate paragraphs are sent — never the manuscript body.
    """
    key = api_key or os.environ.get(GEMINI_API_KEY_ENV)
    if not key:
        raise RuntimeError(
            "No Gemini API key found. Set the GEMINI_API_KEY environment "
            "variable (free key from https://aistudio.google.com/apikey) "
            "or pass one to the tool."
        )

    prompt = _PROMPT_TEMPLATE.format(candidates=_format_candidates(candidates))
    logger.info(
        "Sending %d candidates to Gemini model %s (timeout %ds)",
        len(candidates), model, timeout,
    )
    logger.debug("Full prompt sent to Gemini:\n%s", prompt)

    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
    ).encode("utf-8")
    url = f"{_GEMINI_URL.format(model=model)}?key={key}"
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(
            f"Gemini API request failed (HTTP {e.code}): {detail}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach the Gemini API: {e.reason}") from e

    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        # A blocked prompt or empty candidate list lands here.
        raise RuntimeError(
            f"Gemini returned no usable text. Raw response:\n"
            f"{json.dumps(payload)[:1000]}"
        ) from e

    logger.debug("Raw Gemini response text:\n%s", text)
    return _parse_chapters_json(text, source="gemini")


def _body_paragraph_to_rich(p: DocxParagraph) -> RichText:
    """Convert a source paragraph into a RichText preserving italic / bold per run.

    Whitespace around the paragraph is stripped (handles e.g. Author B's
    tab-indented first run). Font / size are NOT copied — the body styles
    in the template own typography. Only semantic emphasis carries over.
    """
    rt = RichText()
    parts: list[tuple[str, bool, bool]] = []
    for run in p.runs:
        if not run.text:
            continue
        parts.append((run.text, bool(run.italic), bool(run.bold)))
    if not parts:
        return rt
    # Trim outer whitespace.
    first_text, fi, fb = parts[0]
    parts[0] = (first_text.lstrip(), fi, fb)
    last_text, li, lb = parts[-1]
    parts[-1] = (last_text.rstrip(), li, lb)
    for txt, italic, bold in parts:
        if not txt:
            continue
        rt.add(txt, italic=italic, bold=bold)
    return rt


def _sneak_preview_idx(paragraphs: list) -> int | None:
    """Return the paragraph index of the first SNEAK PREVIEW heading, or None."""
    for i, p in enumerate(paragraphs):
        if p.text.strip().upper().startswith("SNEAK"):
            return i
    return None


def _build_chapters(
    doc: Document, claude_chapters: list[dict[str, Any]]
) -> list[Chapter]:
    paragraphs = list(doc.paragraphs)
    n = len(paragraphs)
    sneak_idx = _sneak_preview_idx(paragraphs)

    claude_chapters = sorted(claude_chapters, key=lambda c: c["title_idx"])
    # Drop any entry whose title paragraph is the sneak preview heading or
    # inside the sneak preview section (e.g. "CHAPTER ONE" of the next book).
    if sneak_idx is not None:
        before_filter = len(claude_chapters)
        claude_chapters = [
            ch for ch in claude_chapters if int(ch["title_idx"]) < sneak_idx
        ]
        dropped = before_filter - len(claude_chapters)
        if dropped:
            logger.info("Dropped %d chapter(s) inside sneak preview section", dropped)

    result: list[Chapter] = []
    for i, ch in enumerate(claude_chapters):
        title_idx = int(ch["title_idx"])
        pov_idx = int(ch["pov_idx"])
        pov = str(ch.get("pov", "")).strip()

        body_start = max(title_idx, pov_idx) + 1
        body_end = (
            int(claude_chapters[i + 1]["title_idx"])
            if i + 1 < len(claude_chapters)
            else n
        )
        # Never let the body of a chapter spill into the sneak preview section.
        if sneak_idx is not None:
            body_end = min(body_end, sneak_idx)

        body: list[Any] = []
        for j in range(body_start, body_end):
            if not paragraphs[j].text.strip():
                continue
            body.append(_body_paragraph_to_rich(paragraphs[j]))

        number = i + 1
        title = f"CHAPTER {number_to_words(number)}"
        logger.debug("Built chapter %d: %r (pov=%r, body_paragraphs=%d)", number, title, pov, len(body))
        result.append(Chapter(number=number, title=title, pov=pov, body=body))

    logger.info("Total chapters built: %d", len(result))
    return result


def detect_chapters_ai(
    doc: Document,
    *,
    backend: str = DEFAULT_BACKEND,
    model: str | None = None,
    api_key: str | None = None,
    claude_bin: str = DEFAULT_CLAUDE_BIN,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> list[Chapter]:
    """Detect chapters via the selected model backend.

    ``backend`` is one of :data:`BACKENDS`:
    - ``"claude"``    — local Claude Code CLI (default; VPS-compatible).
    - ``"gemini"``    — Google Gemini API with the caller's own key.
    - ``"heuristic"`` — zero-AI keyword detector (no network, no account).
    """
    if backend not in BACKENDS:
        raise ValueError(
            f"Unknown backend {backend!r}; choose one of {', '.join(BACKENDS)}."
        )

    # The heuristic builds chapters directly from the document.
    if backend == "heuristic":
        return detect_chapters_heuristic(doc)

    candidates = _candidate_lines(doc)
    if not candidates:
        logger.warning("No candidate paragraphs found in document")
        return []

    if backend == "gemini":
        chapters = _call_gemini(
            candidates,
            model=model or DEFAULT_GEMINI_MODEL,
            api_key=api_key,
            timeout=timeout,
        )
    else:  # "claude"
        chapters = _call_claude_cli(
            candidates, claude_bin=claude_bin, timeout=timeout
        )
    return _build_chapters(doc, chapters)


_CHAPTER_TITLE_RE = re.compile(
    r"^(chapter|prologue|epilogue|epilog|interlude|part)\b",
    re.IGNORECASE,
)


_POV_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z\s\-']{0,24}$")


def detect_chapters_heuristic(doc: Document) -> list[Chapter]:
    """Detect chapters using keyword matching — no Claude call needed.

    Scans candidate lines (short paragraphs / heading-styled) for chapter-title
    keywords. If the very next paragraph index is also a candidate and looks like
    a POV name (short, letters/spaces/hyphens only), it is treated as the POV
    line and excluded from the body — matching what the AI detector does.
    Used by the verify tool so it does not need to shell out to Claude.
    """
    candidates = _candidate_lines(doc)
    cand_by_idx = {idx: (style, text) for idx, style, text in candidates}

    claude_output = []
    for idx, style, text in candidates:
        if not (_CHAPTER_TITLE_RE.search(text) or style.lower().startswith("heading")):
            continue
        pov_idx = -1
        pov = ""
        next_entry = cand_by_idx.get(idx + 1)
        if next_entry is not None:
            next_style, next_text = next_entry
            if (
                not _CHAPTER_TITLE_RE.search(next_text)
                and not next_style.lower().startswith("heading")
                and _POV_NAME_RE.match(next_text)
            ):
                pov_idx = idx + 1
                pov = next_text
        claude_output.append({"title_idx": idx, "pov_idx": pov_idx, "pov": pov})

    if not claude_output:
        return []
    return _build_chapters(doc, claude_output)


def detect_sneak_preview(doc: Document) -> list[RichText]:
    """Extract body paragraphs from the source's SNEAK PREVIEW section.

    Looks for a paragraph whose stripped, uppercased text starts with 'SNEAK'.
    Collects all subsequent non-empty paragraphs until end of document.
    Returns empty list if no sneak preview section is found.
    """
    paragraphs = list(doc.paragraphs)
    sneak_idx = _sneak_preview_idx(paragraphs)
    if sneak_idx is None:
        return []
    result: list[RichText] = []
    for p in paragraphs[sneak_idx + 1:]:
        if not p.text.strip():
            continue
        result.append(_body_paragraph_to_rich(p))
    return result
