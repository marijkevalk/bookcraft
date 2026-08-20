# Installing Bookcraft on your own computer

Bookcraft formats a manuscript `.docx` into a styled ebook + paperback. It
runs entirely on **your** computer and uses **your own free Google Gemini
key** to detect chapters — no Claude subscription, no server.

There are two ways to install it.

---

## Get your free Gemini key first (both routes need it)

1. Go to <https://aistudio.google.com/apikey> and sign in with a Google
   account (no credit card).
2. Click **Create API key** and copy it.
3. You paste this into Bookcraft once; it is stored only on your computer.

Gemini's free tier is more than enough for formatting books.

---

## Route A — Install the app (works today, Mac + Windows)

This needs Python once. After that, one command starts the app.

### 1. Install Python 3.12+
- **Windows:** download from <https://www.python.org/downloads/> and, in the
  installer, tick **"Add Python to PATH"**.
- **macOS:** `brew install python@3.12` (or download from python.org).

### 2. Install `uv` (a fast Python tool runner)
- **Windows (PowerShell):**
  ```powershell
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **macOS/Linux:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### 3. Start Bookcraft
```bash
uvx --from git+https://github.com/marijkevalk/bookcraft.git book-formatter serve
```
This downloads the app and opens the UI in your browser at
<http://127.0.0.1:8765>. Paste your Gemini key, upload your manuscript, fill in
the book details, and click **Format my book**.

> Until the UI branch is merged to `master`, add `@feature/local-app-byo-model`
> to the URL above:
> `git+https://github.com/marijkevalk/bookcraft.git@feature/local-app-byo-model`

Alternatively, clone the repo and run it in place:
```bash
git clone https://github.com/marijkevalk/bookcraft.git
cd bookcraft
uv run book-formatter serve
```

To stop the app, press **Ctrl+C** in the terminal.

---

## Route B — Double-click bundle (no Python needed) — build later

For a true double-click app (no terminal, no Python install), Bookcraft ships
a ready PyInstaller config. The bundle must be **built on the same kind of
computer it will run on** (a Windows `.exe` on Windows, a macOS `.app` on a
Mac):

```bash
pip install pyinstaller
pyinstaller packaging/bookcraft.spec
```

The result appears in `dist/Bookcraft/`. Zip that folder and share it; the user
just unzips and double-clicks **Bookcraft**.

First-run security notes (because the bundle is unsigned):
- **Windows:** SmartScreen may warn — click **More info → Run anyway**.
- **macOS:** right-click the app → **Open** the first time (Gatekeeper).

Signing/notarising to remove those warnings is a separate later step.

---

## Which chapter-detection backend?

The UI uses **Gemini** (your key) by default. The command line also supports:
- `--backend heuristic` — no AI, no key, no internet (keyword-based; good for a
  quick offline pass).
- `--backend claude` — the original local Claude Code CLI path (used on
  Marijke's server).

Example CLI run without the UI:
```bash
uv run book-formatter format \
  --template your-template.docx --source manuscript.docx \
  --metadata book_metadata.txt --output out.docx \
  --backend gemini
# with GEMINI_API_KEY set in your environment
```
