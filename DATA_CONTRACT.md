# Idea Library — Data Contract

This is the single source of truth for the JSON shape that connects the
scraper (`scraper/`) to the web app (`app/`). If you change one side,
update this file and the other side together.

## File layout produced by the scraper

```
library/
  manifest.json              <- list of all captured days (the app reads this first)
  2026/
    2026-07-25.json          <- full data for that day's idea
    2026-07-24.json
    ...
```

## manifest.json

```json
{
  "ideas": [
    { "id": "2026-07-25", "title": "Ad Fraud Guardian", "path": "library/2026/2026-07-25.json" },
    { "id": "2026-07-24", "title": "AI Visibility & Link Building Platform", "path": "library/2026/2026-07-24.json" }
  ]
}
```

## Per-day idea JSON (2026-07-25.json)

This mirrors exactly what `IdeaCard` in the app expects — same field names,
same nesting. If the scraper can't fill a field, omit it or set it to
`null`/empty array; the app already handles missing sections gracefully.

```json
{
  "id": "2026-07-25",
  "date": "2026-07-25",
  "title": "Ad Fraud Guardian",
  "tagline": "Recover thousands in wasted PPC budget lost to ad fraud",
  "badges": ["Perfect Timing"],
  "description": "Full pitch text...",
  "scores": {
    "opportunity": { "score": 8, "label": "Strong" },
    "problem": { "score": 8, "label": "Real Pain" },
    "feasibility": { "score": 7, "label": "Moderate" },
    "whyNow": { "score": 9, "label": "Perfect Timing" }
  },
  "keywords": [
    { "keyword": "click fraud detection", "volume": 2400, "growth": 45 }
  ],
  "marketGap": "Text describing the gap...",
  "executionPlan": "Text describing suggested rollout...",
  "executionDifficulty": { "score": 5, "note": "short note" },
  "categorization": {
    "type": "SaaS",
    "market": "B2B",
    "target": "Digital agencies & SMBs",
    "competitor": "Lunio, ClickCease"
  },
  "communitySignals": {
    "reddit": "Active in r/PPC",
    "facebook": "Several agency owner groups",
    "youtube": "Moderate coverage"
  },
  "status": "not_started",
  "notes": ""
}
```

Notes:
- `status` and `notes` are **seed defaults only** — once you interact with
  an idea in the app, its live status/notes live in the app's own
  persistent storage (keyed by `id`), not in this file. The scraper never
  needs to update these after first write.
- `id` should just be the date string (`YYYY-MM-DD`) — simple, sortable,
  stable.
