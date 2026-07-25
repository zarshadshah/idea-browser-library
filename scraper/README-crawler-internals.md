# Idea of the Day — Deep Library

Full daily crawl of ideabrowser.com's "Idea of the Day": every keyword
in the Keyword Analysis dropdown, every time range (6 Months / 1 Year /
2 Years / All Time) for each keyword, and every "View Analysis" sub-page
(Value Equation, Market Matrix, Value Ladder, Market Gap, Execution
Difficulty, Execution Plan, Community Signals breakdown).

## ⚠️ Read this before running

This script was written from screenshots of the page, not by running it
against the live site (the environment it was built in can't reach
ideabrowser.com — the site blocks non-browser requests, and the sandbox's
network is separately locked to package registries only). That means:

- **CSS/text selectors are best-effort guesses**, based on visible labels
  and structure in the screenshots you provided (e.g. clicking on the text
  "Keyword:", or on time range labels like "1 Year").
- **It will very likely need one round of real debugging** the first time
  you run it — some selector will probably not match the live DOM exactly.
- Every step is wrapped in try/except and logged to
  `library/<year>/<date>.crawl-log.json`, and nothing crashes the whole
  run if one step fails — so after the first run, check that log file to
  see exactly which steps failed and why, then send me the log (or the
  page's live HTML) and I'll fix the specific selectors.
- The safest way to debug: run it locally first (not in CI) with
  `headless=False` temporarily changed in `build_browser()`, so you can
  watch the browser click through the page and see where it diverges from
  what's expected.

## What gets captured

For each day:
- `library/<year>/<date>.deep.json` — full structured data: summary
  scores, every keyword × time range combination, every sub-page's
  rendered text
- `library/<year>/<date>.deep.md` — human-readable Markdown version
- `library/<year>/<date>.crawl-log.json` — step-by-step log, including
  any errors, so failures are visible and debuggable rather than silent

## Why this is slow

A single idea can have 10-15+ keywords, each needing 4 time-range clicks,
plus ~7-8 sub-pages — each interaction needs a click + a wait for the SPA
to re-render (1–2 seconds). That's realistically 70-100+ browser
interactions and **several minutes per run**, not seconds. The GitHub
Actions workflow gives it a 30-minute ceiling and runs once a day, which
comfortably fits GitHub's free tier (2,000 min/month for private repos,
unlimited for public).

## Setup

1. Push this to a GitHub repo.
2. Actions tab → "Daily Deep Idea Crawl" → Run workflow (to test immediately).
3. Check the run logs and the `.crawl-log.json` output for errors.
4. Report back any selector mismatches and I'll patch `deep_crawl.py`.

## Local test run

```bash
pip install playwright
playwright install --with-deps chromium
python scripts/deep_crawl.py
```

## Limitations

- Still only captures what's visible without a paid login (per your free
  tier account) — no deeper gated content.
- If ideabrowser.com changes its layout, selectors will need updates —
  but raw text/log is always saved, so nothing is silently lost even when
  a selector breaks.
