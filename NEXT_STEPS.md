# Next steps — local app / bring-your-own-model (FR-120)

Branch: `feature/local-app-byo-model` (Fase 1 + 2 + 3 built, tested, pushed).
Tracked in the Opus vault as FR-120.

## Still to do

1. **Merge to `master`** — benchmark signed off (see below), so the branch can
   land. Once merged, the install command drops the `@feature/...` suffix:
   `uvx --from git+https://github.com/marijkevalk/bookcraft.git book-formatter serve`.

2. **Optional — double-click bundle for Kristiaan** (only if the uvx/pip route
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
- **Accuracy benchmark signed off (2026-08-26).** Gemini matches Claude on both
  fixtures: author A → 4 chapters (Aria, Ryder, Aria, Ryder); author B → 4
  chapters (Fiona, Dimitri, Fiona, Fiona). Non-ai suite: 37 passed.
- **Default Gemini model bumped** `gemini-2.0-flash` → `gemini-3.5-flash-lite`
  in `ai_chapters.py`. The old model was retired (404). Avoid "thinking" models
  (gemini-3.x-flash): they stall on the JSON-output prompt (13-min hang). The
  lite model returns in ~1s. Verified end-to-end via the default (no `--model`).
- **UI backend selector added (2026-08-27).** The web UI now offers Claude /
  Gemini / Offline as the chapter-detection method (was hardcoded to Gemini).
  Reason: **Gemini refuses explicit/adult content** — a real romance manuscript
  returns `promptFeedback.blockReason: PROHIBITED_CONTENT`, which the normal
  `safetySettings` cannot override (it's Google's non-configurable filter). For
  Kristiaan's steamy-romance books, use **Claude** (his own Claude Code login,
  no key, handles the content — same path the server `format-book` uses) or
  **Offline** (no AI/account; nails clean "Chapter N" headings — 4/4 on both
  fixtures). All three verified end-to-end through the UI; ruff+mypy+37 tests green.
- Note: on the VPS, the app's `urllib` call hangs because IPv6 is broken there
  (DNS returns an AAAA first; `urllib` has no happy-eyeballs, `curl` does). This
  is VPS-only — a normal Mac is unaffected. To run the app on the VPS, force
  IPv4 (patch `socket.getaddrinfo` to `AF_INET`).
