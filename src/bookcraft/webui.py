"""Local web UI for bookcraft — a small, friendly front-end for non-technical
authors.

Runs entirely on the user's own machine (localhost only). The author pastes
their own free Gemini API key, uploads a manuscript, fills in the book
metadata, and downloads the formatted ebook + paperback. No Claude
subscription, no server, no command line.

The heavy lifting is delegated to :func:`bookcraft.pipeline.format_book`, so
the UI and the CLI stay in lock-step.
"""

from __future__ import annotations

import io
import logging
import tempfile
import uuid
import zipfile
from pathlib import Path

from flask import (
    Flask,
    abort,
    render_template_string,
    request,
    send_file,
)
from flask.typing import ResponseReturnValue

from bookcraft.ai_chapters import DEFAULT_GEMINI_MODEL
from bookcraft.config import get_saved_api_key, save_config
from bookcraft.metadata import BookMetadata
from bookcraft.pipeline import format_book

logger = logging.getLogger(__name__)

# Where formatted results live until the user downloads them. Cleared on
# process exit (a fresh temp dir per server run).
_RESULTS: dict[str, dict[str, Path]] = {}

MAX_UPLOAD_MB = 25

_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bookcraft — format your manuscript</title>
  <style>
    :root { --bg:#f6f5f2; --card:#fff; --ink:#22201d; --muted:#6b6660;
            --accent:#8a5a44; --accent-ink:#fff; --line:#e5e1da; --ok:#2f7d55;
            --err:#b23b3b; }
    * { box-sizing: border-box; }
    body { margin:0; font:16px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
           background:var(--bg); color:var(--ink); }
    .wrap { max-width:720px; margin:0 auto; padding:32px 20px 64px; }
    h1 { font-size:1.7rem; margin:0 0 4px; }
    .sub { color:var(--muted); margin:0 0 28px; }
    .card { background:var(--card); border:1px solid var(--line);
            border-radius:14px; padding:22px 22px; margin-bottom:20px; }
    .card h2 { font-size:1.05rem; margin:0 0 12px; }
    label { display:block; font-weight:600; margin:14px 0 5px; font-size:.92rem; }
    .req::after { content:" *"; color:var(--accent); }
    input[type=text], input[type=password], input[type=file], textarea {
      width:100%; padding:10px 12px; border:1px solid var(--line);
      border-radius:9px; font:inherit; background:#fff; }
    textarea { min-height:70px; resize:vertical; }
    .row { display:flex; gap:14px; } .row > div { flex:1; }
    .hint { color:var(--muted); font-size:.82rem; margin-top:4px; }
    .steps { margin:0; padding-left:20px; color:var(--muted); font-size:.9rem; }
    .steps li { margin:4px 0; }
    a { color:var(--accent); }
    button { margin-top:22px; background:var(--accent); color:var(--accent-ink);
             border:0; border-radius:10px; padding:13px 22px; font:inherit;
             font-weight:700; cursor:pointer; width:100%; }
    button:hover { filter:brightness(1.06); }
    details { margin-top:16px; } summary { cursor:pointer; color:var(--muted); }
    .flash { padding:12px 14px; border-radius:10px; margin-bottom:20px;
             font-size:.94rem; }
    .flash.err { background:#fbeaea; color:var(--err); border:1px solid #eecccc; }
    .flash.ok  { background:#e8f4ec; color:var(--ok);  border:1px solid #cbe6d5; }
    .dl { display:inline-block; margin:6px 10px 0 0; padding:11px 16px;
          background:var(--accent); color:#fff; border-radius:9px;
          text-decoration:none; font-weight:600; }
    .foot { color:var(--muted); font-size:.8rem; text-align:center;
            margin-top:28px; }
  </style>
</head>
<body>
<div class="wrap">
  <h1>Bookcraft</h1>
  <p class="sub">Turn your manuscript into a formatted ebook &amp; paperback — on your own computer.</p>

  {% if error %}<div class="flash err">{{ error }}</div>{% endif %}
  {% if result %}
    <div class="flash ok">
      Done — {{ result.summary }}.
      {% if result.sneak %}Sneak preview included.{% endif %}
    </div>
    <div class="card">
      <h2>Download your files</h2>
      <a class="dl" href="/download/{{ result.token }}/ebook">Ebook .docx</a>
      <a class="dl" href="/download/{{ result.token }}/paperback">Paperback .docx</a>
      <a class="dl" href="/download/{{ result.token }}/zip">Both (.zip)</a>
    </div>
  {% endif %}

  <form method="post" action="/format" enctype="multipart/form-data">
    <div class="card">
      <h2>1 · Chapter detection</h2>
      <label for="backend">Method</label>
      <select id="backend" name="backend">
        <option value="claude"{{ ' selected' if sel_backend == 'claude' }}>Claude Code — uses your Claude login (handles explicit / adult content)</option>
        <option value="gemini"{{ ' selected' if sel_backend == 'gemini' }}>Gemini — free Google key</option>
        <option value="heuristic"{{ ' selected' if sel_backend == 'heuristic' }}>Offline — no AI, no account (needs clear chapter headings)</option>
      </select>
      <div class="hint">Gemini needs a free key below and may refuse explicit content.
        Claude uses your local Claude Code login (no key). Offline uses no account and
        works well when chapters start with clear "Chapter N" headings.</div>

      <label for="api_key">Gemini API key <small>(only for the Gemini method)</small></label>
      <input type="password" id="api_key" name="api_key"
             placeholder="{{ 'saved — leave blank to reuse' if has_key else 'AIza…' }}"
             autocomplete="off">
      <div class="hint">Free key at
        <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a>
        (Google account, no credit card). Stored only on this computer; leave blank to reuse your saved key.</div>
    </div>

    <div class="card">
      <h2>2 · Your manuscript</h2>
      <label class="req" for="manuscript">Manuscript (.docx)</label>
      <input type="file" id="manuscript" name="manuscript" accept=".docx" required>
      <div class="hint">Your chapter text is read locally; with the AI methods only short heading lines are sent out to find chapter boundaries. The Offline method sends nothing.</div>
    </div>

    <div class="card">
      <h2>3 · Book details</h2>
      <div class="row">
        <div><label class="req" for="title">Title</label>
          <input type="text" id="title" name="title" required></div>
        <div><label class="req" for="subtitle">Subtitle / genre</label>
          <input type="text" id="subtitle" name="subtitle" required></div>
      </div>
      <div class="row">
        <div><label class="req" for="series">Series</label>
          <input type="text" id="series" name="series" required></div>
        <div><label class="req" for="pen_name">Pen name</label>
          <input type="text" id="pen_name" name="pen_name" required></div>
      </div>
      <label for="book_number">Book number in series</label>
      <input type="text" id="book_number" name="book_number" value="1">
      <label for="about">About the author</label>
      <textarea id="about" name="about" placeholder="One paragraph per line."></textarea>

      <details>
        <summary>Advanced</summary>
        <label for="model">Gemini model</label>
        <input type="text" id="model" name="model" value="{{ default_model }}">
        <div class="hint">Leave as-is unless you know you need another model.</div>
      </details>
    </div>

    <button type="submit">Format my book</button>
  </form>

  <p class="foot">Runs locally · your key and manuscript never leave this computer except the short heading lines sent to Gemini.</p>
</div>
</body>
</html>"""


def _friendly_error(exc: Exception) -> str:
    """Turn a backend exception into a message a non-technical user understands."""
    msg = str(exc)
    low = msg.lower()
    if "no gemini api key" in low:
        return ("No Gemini API key yet. Paste your free key from "
                "aistudio.google.com/apikey in step 1.")
    if "http 400" in low or "http 403" in low or "api key" in low:
        return ("Gemini rejected the request — usually a wrong or expired API "
                "key. Double-check the key you pasted in step 1.")
    if "could not reach" in low:
        return ("Couldn't reach Gemini. Check your internet connection and try "
                "again.")
    if "no chapters detected" in low:
        return ("No chapters were found in that manuscript. Make sure chapter "
                "headings (e.g. 'Chapter 1' / 'CHAPTER ONE') are present.")
    if "non-json" in low or "no usable text" in low:
        return ("Gemini's answer couldn't be read. Please try again; if it "
                "keeps happening, try a different model under Advanced.")
    return f"Something went wrong: {msg}"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    @app.get("/")
    def index() -> str:
        return render_template_string(
            _PAGE,
            has_key=bool(get_saved_api_key()),
            default_model=DEFAULT_GEMINI_MODEL,
            sel_backend="gemini",
            error=None,
            result=None,
        )

    @app.post("/format")
    def do_format() -> str:
        backend = (request.form.get("backend") or "gemini").strip()
        if backend not in ("claude", "gemini", "heuristic"):
            backend = "gemini"

        def page(
            *,
            error: str | None = None,
            result: dict[str, object] | None = None,
        ) -> str:
            return render_template_string(
                _PAGE,
                has_key=bool(get_saved_api_key()),
                default_model=DEFAULT_GEMINI_MODEL,
                sel_backend=backend,
                error=error,
                result=result,
            )

        upload = request.files.get("manuscript")
        if upload is None or not upload.filename:
            return page(error="Please choose a manuscript .docx file (step 2).")
        if not upload.filename.lower().endswith(".docx"):
            return page(error="The manuscript must be a .docx file.")

        api_key = (request.form.get("api_key") or "").strip() or get_saved_api_key()
        if backend == "gemini" and not api_key:
            return page(error="Please paste your Gemini API key (step 1), "
                              "or pick Claude / Offline as the method.")

        required = {
            "title": "Title", "subtitle": "Subtitle", "series": "Series",
            "pen_name": "Pen name",
        }
        missing = [label for f, label in required.items()
                   if not (request.form.get(f) or "").strip()]
        if missing:
            return page(error="Please fill in: " + ", ".join(missing) + " (step 3).")

        about = [ln.strip() for ln in (request.form.get("about") or "").splitlines()
                 if ln.strip()]
        metadata = BookMetadata(
            title=request.form["title"].strip(),
            subtitle=request.form["subtitle"].strip(),
            series=request.form["series"].strip(),
            pen_name=request.form["pen_name"].strip(),
            book_number=(request.form.get("book_number") or "1").strip() or "1",
            about_the_author=about,
        )
        model = (request.form.get("model") or "").strip() or None

        work = Path(tempfile.mkdtemp(prefix="bookcraft_"))
        base = Path(upload.filename).stem
        source = work / f"{base}.docx"
        upload.save(str(source))
        output = work / f"{base}_formatted.docx"

        try:
            result = format_book(
                source_path=source,
                metadata=metadata,
                output_path=output,
                backend=backend,
                model=model,
                api_key=api_key,
            )
        except Exception as exc:  # surfaced to the user; full trace logged
            logger.exception("Formatting failed")
            return page(error=_friendly_error(exc))

        # Only persist the key once a run actually succeeded.
        if request.form.get("api_key", "").strip():
            save_config({"gemini_api_key": api_key})

        token = uuid.uuid4().hex
        _RESULTS[token] = {
            "ebook": result.ebook_path,
            "paperback": result.paperback_path,
        }
        return page(result={
            "token": token,
            "summary": result.summary,
            "sneak": result.sneak_preview_paragraphs > 0,
        })

    @app.get("/download/<token>/<which>")
    def download(token: str, which: str) -> ResponseReturnValue:
        entry = _RESULTS.get(token)
        if entry is None:
            abort(404)
        if which == "zip":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in entry.values():
                    zf.write(path, arcname=path.name)
            buf.seek(0)
            return send_file(buf, as_attachment=True,
                             download_name="formatted_book.zip")
        chosen = entry.get("ebook" if which == "ebook" else "paperback")
        if chosen is None:
            abort(404)
        return send_file(str(chosen), as_attachment=True,
                         download_name=chosen.name)

    return app
