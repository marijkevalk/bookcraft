# bookcraft — plan & design

> Status: plan (approved in conversation, not yet built). Renames `book-formatter`
> into a generic `bookcraft` umbrella and adds a manuscript **quality-analysis**
> tool alongside the existing formatter.

## Goal

Kristiaan runs an Amazon business publishing steamy-romance novels written by
ghostwriters, and has quality problems. `bookcraft` gives, per manuscript, a
**credible, actionable quality report (PDF)** that predicts and prevents bad
reviews — and that gets sharper over time from the AI's own analyses + real
Amazon reviews.

## Users & workflow

- **Marijke** runs the CLI (same way as the formatter) and sends Kristiaan the PDF.
- **Kristiaan** is purely a consumer of the PDF. He gives no feedback, types
  nothing. The only inputs to the learning system are (a) the AI's analyses and
  (b) the Amazon reviews.

## CLI / UX (mirrors book-formatter)

Same shape as the formatter: a command with a path to the Word doc, optionally
a link to the Amazon book, output is a PDF.

```
bookcraft analyze \
  --source path/to/manuscript.docx \      # the ghostwriter's Word doc
  --book https://www.amazon.nl/dp/ASIN \  # OPTIONAL Amazon book link/ASIN (reviews)
  --ghostwriter "name" \                  # OPTIONAL, for the scorecard
  --output path/to/report.pdf
```

The **purpose and output differ by whether the book is already published** —
see *Output modes* below.

## Output modes (purpose drives the report)

The report's shape depends on whether the book is published yet:

1. **Pre-publication — general (no reviews).** Forward-looking. "Can this go
   out?" Verdict (publish / revise / reject) + preventive fix list. Emphasis on
   craft, genre fit, consistency. The default when there is no `--book`.

2. **Post-publication — review diagnostic (`--book` for the published book).**
   Backward-looking. The report is *about the reviews*: what readers actually
   complain about, each mapped to concrete passages, the root cause, and lessons
   for next time (which also feed the learning overview). No publish/revise
   verdict — the book is already out.

3. **Pre-publication + regression (new manuscript + a *previous* book's reviews).**
   The general pre-publication report, plus a regression section: "do the
   complaints from the prior book recur in this new manuscript?" This is the
   highest-value case for catching a bad review before it happens.

How the mode is chosen: no `--book` -> mode 1. With `--book`, the source
manuscript being the published book -> mode 2; the source being a new manuscript
with `--book` pointing at a prior title -> mode 3. (Exact flag naming, e.g.
`--prior-book` for the regression reference, finalised in Fase 1.)

## Repo structure (rename, legacy preserved)

- Folder + GitHub repo `book-formatter` -> `bookcraft`; package -> `bookcraft`.
- **Legacy guaranteed:** register two console scripts — `bookcraft` *and* an
  alias `book-formatter`. Kristiaan's current `book-formatter format ...` keeps
  working byte-for-byte; the `format` code is moved, not changed.
- Layout:
  - `src/bookcraft/format/`   — existing formatter (formatter, template_builder, metadata, ai_chapters, verify)
  - `src/bookcraft/analyze/`  — new analysis
  - `src/bookcraft/reviews/`  — amazon review fetching (shared; existing amazon_reviews)
  - `src/bookcraft/report/`   — PDF rendering (shared; reuses Playwright)
  - `src/bookcraft/knowledge/`— rubric + learning overview (data, in-repo)
- **All data in the app folder** (per requirement: code + info + learnings together):
  - `data/manuscripts/`, `data/reviews/`, `data/reports/` — inputs/outputs
  - `src/bookcraft/knowledge/` + `data/history/` — rubric, learning, past analyses

## analyze pipeline

1. **Parse manuscript** (python-docx); reuse chapter detection from the formatter.
2. **Hard metrics first (the credibility anchor)** — verifiable numbers, no opinion:
   word count, chapter count + per-chapter word counts, sentence-length
   distribution, dialogue %, reading ease, crutch-word/repetition counts, spice-
   scene count. (Same spirit as the formatter's word-count integrity check that
   Kristiaan already trusts.)
3. **Load knowledge**: current `rubric.md` + `learning.md` + (if `--book`) the
   fetched reviews and known recurring complaints for that series/ghostwriter.
4. **AI analysis, chapter-by-chapter** via the local Claude Code CLI (no API key;
   same pattern as ai_chapters). Each chapter -> structured findings, each with a
   **verbatim quote + location + severity**, mapped to a rubric dimension. Then a
   **synthesis pass** -> overall verdict, top issues, opening/Look-Inside
   analysis, and the review-regression mapping.
5. **Render PDF** (HTML -> PDF via Playwright).

### Credibility (the core requirement)

- **Verifiable facts before opinions** — metrics lead; judgments follow.
- **Every qualitative claim carries a verbatim quote + location.** Quotes are
  extracted from the manuscript and verified to exist — never AI-generated. A
  single fabricated quote would destroy trust.
- **Review-linked findings cite the real review** + book ASIN, e.g.
  "this is the 1-star complaint on book XXX: '...'".
- Honest confidence; say "uncertain" rather than bluff.

## The rubric (starting set — extensible)

Six layers (the agreed checklist; grows over time via the learning overview):
1. **Language/line-level** — spelling/grammar/punctuation, typos, crutch words &
   repetition, filter words, POV/tense slips.
2. **Prose & voice** — show-vs-tell, sensory detail, dialogue quality & tags,
   sentence rhythm/variety, cliché/purple prose, consistent pen-name voice.
3. **Structure & pacing** — chapter-1 hook (Look-Inside conversion), pacing
   (slow open / saggy middle / rushed end), chapter balance & cliffhangers,
   **satisfying HEA/HFN ending** (genre requirement).
4. **Characters & relationship arc** — likability/agency, distinct voices,
   believable relationship build (insta-love), chemistry/tension.
5. **Genre & market fit (steamy romance)** — heat level & spice pacing vs.
   cover/blurb/category promise, trope execution, repetition in spice scenes,
   consent/dynamics handled sensitively, length vs. category/price.
6. **Consistency & continuity** — names, physical details, ages, timeline,
   series continuity, loose threads / plot holes.

### Review mode adds (highest value)
- Map each recurring reader complaint to **concrete manuscript locations**.
- **Regression check**: do complaints from a previous book recur in this new
  manuscript? This is the strongest signal for the learning overview.

## The report

Layout is shared across modes; the **framing** follows the mode above (pre-pub verdict vs. review diagnostic).

- **Page 1 = executive dashboard** (the "overview with the most important
  things"): verdict (publish / revise / reject) + score, per-chapter quality
  heatmap, top-3 issues with quote + fix, key metrics.
- **Behind it = the extensive report** (the equivalent of the formatter's .txt
  report — backing he trusts even if he doesn't read it): per-chapter findings,
  full metrics, all flagged passages.
- **"Send to your writer" block** — ready-to-forward, concrete, polite fix list.

## Learning overview (under the hood)

- `knowledge/rubric.md` — the checks (extensible).
- `knowledge/learning.md` — accumulated insights: per-ghostwriter patterns, which
  manuscript patterns correlated with which real review complaints, heat/length
  calibration for Kristiaan's actual readers.
- `data/history/` — each analysis (metrics + findings) + later the reviews per
  book/ASIN.
- After an analysis-with-reviews, the AI updates `learning.md` itself from
  (a) the analysis + (b) the reviews — **no Kristiaan input**. Marijke can inspect
  it (it lives in the repo). Future analyses load `learning.md` as context, so the
  checks get sharper and more tailored over time. Deterministic, inspectable; no ML.

## Ghostwriter scorecard (business value)

Once `data/history/` fills, the report includes a per-writer track record
("Writer A consistently weak on spice pacing") — a steering tool for who to
rehire and where to push back.

## Review fetching — reliability (dependency/risk)

Fetching Amazon reviews hits the same anti-bot fingerprinting that blocked the
plain `requests` scraper (503) on 2026-06-08. The reviews fetcher should reuse
the **`curl_cffi` (Chrome impersonation) + dedicated-IP** approach already proven
on this server. Without reliable review fetching, the regression check (half the
"wow") is lost.

## Quality bar

New code meets the app's existing standards: ruff, mypy --strict, pytest, CI
green. Pure/parsing logic and the report builder are unit-tested; AI calls are
injectable so tests run without spending Claude calls (same pattern as the
formatter's AI tests).

## Phasing

- **Fase 0** — rename to `bookcraft`, legacy `format` preserved (dual entry point).
- **Fase 1** — `analyze` command: metrics, chapter-by-chapter AI, credible PDF
  with page-1 dashboard + backing detail + send-to-writer block; review mode.
- **Fase 2** — learning overview (`knowledge/` + `data/history/`, auto-updated).
- **Fase 3** — ghostwriter scorecard (emerges as history accumulates).

**v1 nails a few things brilliantly** — page-1 verdict, review-regression,
opening analysis, send-to-writer list, clean PDF — all evidence-backed. The rest
of the rubric grows via the learning overview. Run time is not a constraint.
