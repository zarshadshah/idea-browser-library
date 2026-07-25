# Idea Library — Full System

This is the complete pipeline: a daily scraper that crawls ideabrowser.com's
"Idea of the Day" in depth, and an interactive web app where you browse,
track, and launch build sessions on any idea.

```
idea-system/
  scraper/            <- crawls the site daily, saves + normalizes data
  app/IdeaLibrary.jsx <- the interactive React app you view/use
  DATA_CONTRACT.md    <- the JSON shape connecting the two (reference only)
  .github/workflows/  <- automation that runs it all daily
```

---

## Step 1 — Create your GitHub repo

1. Go to github.com → **New repository**. Name it anything (e.g. `idea-library`).
   Public or private both work fine.
2. Push everything in this folder to that repo:
   ```bash
   cd idea-system
   git init
   git add .
   git commit -m "Initial idea library system"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

## Step 2 — Turn on the daily automation

1. In your repo, go to the **Actions** tab.
2. You should see "Daily Idea Crawl + Library Update" listed. Click it.
3. Click **Run workflow** (top right) to trigger it immediately rather than
   waiting for the 07:00 UTC schedule — this is how you test it right away.
4. Watch the run. It takes several minutes (the crawl clicks through many
   keywords and sub-pages, see `scraper/README-crawler-internals.md` for why).

**Expect the first run to surface selector issues.** The crawler was written
from screenshots, not a live test (ideabrowser.com blocks non-browser
scraping tools, including the one available in this chat — see the
conversation history for the full story of what was tried). After the first
run:
- Check the run's logs in the Actions tab for errors.
- Check `scraper/library/<year>/<date>.crawl-log.json` in your repo — every
  step that failed is listed there with an error message, nothing fails
  silently.
- Send me that log (paste it in chat, or share the repo) and I'll patch the
  specific selectors in `scraper/scripts/deep_crawl.py`. This is a quick,
  targeted fix once we can see what the real DOM looked like — the first
  run's raw HTML/text captures are saved specifically so this debugging
  works well.

## Step 3 — Connect the app to your repo's live data

Once at least one day has been crawled and normalized successfully:

1. Open `app/IdeaLibrary.jsx`.
2. Find this line near the top of the component:
   ```js
   const LIBRARY_BASE_URL = null;
   ```
3. Replace `null` with your repo's raw content URL:
   ```js
   const LIBRARY_BASE_URL = "https://raw.githubusercontent.com/<you>/<repo>/main";
   ```
4. Re-render the artifact (paste the updated file back into a Claude chat,
   or ask me to update it directly). The header will now show
   **"● Live data from your repo"** instead of the sample-data notice.

The app fetches `scraper/library/manifest.json` first, then each day's
individual JSON file listed in it — so as the crawler adds new days, they
appear automatically the next time you open the app. Nothing else needs to
change.

## Step 4 — Using the app day to day

- **Browse**: cards are collapsed by default, showing title + average score.
  Click to expand into tabs (Overview / Keywords / Market / Execution /
  Community).
- **Track**: click a status pill (New / Researching / Building / Launched /
  Shelved) to update it — this is saved automatically and persists between
  visits.
- **Notes**: jot anything in the notes box per idea; also auto-saved.
- **Search & filter**: the search bar matches titles, taglines, and
  keywords; the filter pills narrow by status.

## Step 5 — Actually building an idea

When an idea looks worth pursuing:

1. Expand its card, click **"Build this with Claude."**
2. A prompt appears pre-filled with everything captured about that idea —
   description, market gap, execution plan, keywords, your notes.
3. Copy it, paste it into a new chat with me (or continue in this one).
4. From there we work the way we have on your other projects — Halal
   Finder, Gluco Diary, the tutor-report autofill script: I'll help pick a
   stack suited to a solo build, scope a real MVP, and start writing actual
   project files with you, not just a plan on paper.

You can run this for as many ideas as you want, whenever you're ready —
there's no limit or expiry on an idea sitting in "Researching" for a while.

---

## Troubleshooting

**The crawl workflow fails or times out.**
Check the Actions log first. Common causes: ideabrowser.com's bot
detection blocking the run entirely (the crawler has no special stealth
measures — see `scraper/README-crawler-internals.md` for what a more
robust fallback would need), or a specific selector no longer matching the
live page. Both are visible in the logs / crawl-log.json.

**The app shows "sample data" even after Step 3.**
Check the browser console for a fetch error — usually either the URL is
slightly wrong (double check `<you>` and `<repo>` are substituted, no
trailing slash mismatch) or `manifest.json` doesn't exist yet because no
successful crawl has completed. Trigger the workflow manually and confirm
`scraper/library/manifest.json` actually appears in your repo before
troubleshooting the app side.

**I want to change how often it runs.**
Edit the `cron` line in `.github/workflows/daily.yml`. It's standard cron
syntax, currently `"0 7 * * *"` (07:00 UTC daily).
