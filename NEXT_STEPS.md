# Next steps — local app / bring-your-own-model (FR-120)

Branch: `feature/local-app-byo-model` (Fase 1 + 2 + 3 built, tested, pushed).
Tracked in the Opus vault as FR-120.

## Still to do

1. **Accuracy benchmark (the one real blocker).**
   - Get a free Gemini key: <https://aistudio.google.com/apikey>
   - Run Gemini vs Claude on the test manuscripts and record the delta:
     ```bash
     export GEMINI_API_KEY=...   # your free key
     uv run book-formatter format --template tests/fixtures/template.docx \
       --source tests/fixtures/book_author_A.docx \
       --metadata tests/fixtures/book_metadata.txt \
       --output /tmp/out.docx --backend gemini
     ```
     Compare chapter count + POV names against the `--backend claude` result
     (author A should be 4 chapters: Aria, Ryder, Aria, Ryder).
   - If good enough → sign off Fase 1.

2. **Merge to `master`** once the benchmark signs off (kept on the branch
   until then so the live VPS default stays `claude`).

3. **Confirm the default Gemini model** (`gemini-2.0-flash`) is still a current
   free-tier model; bump `DEFAULT_GEMINI_MODEL` in `ai_chapters.py` if not.

4. **Optional — double-click bundle for Kristiaan** (only if the uvx/pip route
   in `docs/INSTALL.md` is too fiddly). Config is ready; must be built on the
   target OS:
   ```bash
   pip install pyinstaller
   pyinstaller packaging/bookcraft.spec     # run on Windows AND on a Mac
   ```
   Result in `dist/Bookcraft/` — zip and share.

5. **Optional — publish to PyPI** so install becomes `uvx bookcraft serve`
   (no git URL). Not needed for Kristiaan; nice-to-have for wider sharing.

## Done (for reference)
- Provider-agnostic backend seam: claude / gemini / heuristic (`444ff24`).
- Local Flask web UI + `book-formatter serve` + shared pipeline + packaging
  config + install docs (`44ef0b2`).
- 59 tests green, ruff + mypy clean.
