#!/usr/bin/env python3
"""
DEEP crawl of the ideabrowser.com "Idea of the Day" page.

Captures, for the current day's idea:
  1. The main page summary (title, pitch, scores: Opportunity/Problem/
     Feasibility/Why Now, Categorization, Community Signals summary, etc)
  2. EVERY keyword in the "Keyword Analysis" dropdown
     x EVERY time range (6 Months / 1 Year / 2 Years / All Time)
     -> Volume, Growth, CPC, Competition for each combination
  3. Every "View Analysis" sub-page reachable from the main page
     (Value Equation, Market Matrix, Value Ladder, Market Gap,
     Execution Difficulty, Execution Plan, Community Signals detail, etc)

This is a genuinely heavy crawl (can be 70-100+ browser interactions for a
single idea) since it must click through dropdowns and sub-pages one at a
time, waiting for the SPA to re-render each time. Expect this to take
several minutes per run, not seconds.

IMPORTANT — this script needs live debugging against the real site.
It was written from screenshots of the page, not by running against the
live DOM (the authoring environment cannot reach ideabrowser.com), so
CSS selectors below are best-effort guesses based on visible structure
and will likely need small fixes after the first real run. Every
selector attempt is wrapped in try/except and logged, and raw HTML +
screenshots are saved at every step so nothing is silently lost — if a
selector is wrong you'll be able to see exactly what the DOM looked like
and patch the selector.

BOT DETECTION — ideabrowser.com sits behind a Vercel bot-detection
checkpoint that blocks plain headless browsers outright (confirmed via a
real run: every "keyword" the crawler saw was actually checkpoint
interstitial text like "Vercel Security Checkpoint" / "Verifying your
browser"). This version adds:
  - playwright-stealth, patching the common automated-browser fingerprints
    (navigator.webdriver, missing plugins, etc)
  - launching real installed Chrome (channel="chrome") instead of bundled
    Chromium, which has a more genuine fingerprint
  - a wait_out_bot_checkpoint() step that polls for checkpoint text and
    gives its JS challenge time to clear before proceeding
These measures may still not be enough — Vercel's checkpoint is
specifically designed to catch automated traffic, and there's no
guarantee of success. If a run still gets blocked, it now detects that
explicitly (rather than crawling checkpoint text as if it were real
content) and stops early, saving diagnostic info instead of wasting the
full ~10 minute run on a wall.
"""

import json
import os
import re
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth

URL = "https://www.ideabrowser.com/hub/ideas/today"
LOGIN_URL = "https://www.ideabrowser.com/login"
ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = ROOT / "library"
TIME_RANGES = ["6 Months", "1 Year", "2 Years", "All Time"]

WAIT_SHORT = 1200   # ms, after simple UI clicks
WAIT_CHART = 2000   # ms, after triggering a chart/data re-render
NAV_TIMEOUT = 45000  # ms


class Crawler:
    def __init__(self, page, log):
        self.page = page
        self.log = log

    def safe(self, fn, label, default=None):
        """Run fn(), catching+logging errors instead of crashing the whole run."""
        try:
            return fn()
        except Exception as e:
            self.log.append({"step": label, "error": str(e)})
            return default


def build_browser(p):
    # Real Chrome (not the bundled Chromium) is meaningfully harder for
    # bot-detection services (Vercel's checkpoint, Cloudflare, etc) to flag,
    # since it has a genuine Chrome fingerprint rather than headless
    # Chromium's. Falls back to bundled Chromium if Chrome isn't installed
    # on the runner.
    try:
        browser = p.chromium.launch(headless=True, channel="chrome")
    except Exception:
        browser = p.chromium.launch(headless=True)

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        color_scheme="light",
    )
    return browser, context


def login(page, log) -> bool:
    """
    Logs into ideabrowser.com using email+password credentials from the
    IDEABROWSER_EMAIL / IDEABROWSER_PASSWORD environment variables (set as
    GitHub Actions secrets — never hardcoded, never logged).

    Based on the captured login page text, the flow is:
      1. Land on the login page (default view offers "Sign in with your
         email - we'll send a magic link" or a password toggle)
      2. Click "Sign in with Password" to switch to password mode
      3. Fill email + password fields
      4. Submit

    Returns True if login appears to have succeeded (no longer on the
    login page / no login form visible), False otherwise. Selectors here
    are a best effort based on the page's captured text, not a live DOM
    inspection, so may need adjustment — every step is logged.
    """
    email = os.environ.get("IDEABROWSER_EMAIL")
    password = os.environ.get("IDEABROWSER_PASSWORD")

    if not email or not password:
        log.append({"step": "login", "error": "IDEABROWSER_EMAIL or IDEABROWSER_PASSWORD not set"})
        return False

    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(3000)

        # Switch from default magic-link view to password mode. A first
        # attempt found the button in the DOM but Playwright reported it as
        # never visible (even forced), which usually means either: (a) there
        # are multiple matching elements and we're grabbing a hidden
        # duplicate (e.g. a mobile/desktop responsive variant), or (b) the
        # button is genuinely inside a collapsed/hidden panel. We check how
        # many matches exist and log that, then try a role-based locator
        # (often more robust than text matching for real <button> elements),
        # and save a screenshot either way so a human can see exactly what
        # the page looked like if this still fails.
        text_matches = page.get_by_text("Sign in with Password", exact=False)
        match_count = text_matches.count()
        log.append({"step": "login", "note": f"Found {match_count} element(s) matching 'Sign in with Password' text."})

        clicked = False
        try:
            # Prefer a visible match if there are multiple
            for i in range(match_count):
                candidate = text_matches.nth(i)
                if candidate.is_visible():
                    candidate.click(timeout=5000)
                    clicked = True
                    break
        except Exception as e:
            log.append({"step": "login", "note": f"Visible-match click attempt failed: {e}"})

        if not clicked:
            try:
                page.get_by_role("button", name=re.compile("Sign in with Password", re.I)).first.click(timeout=5000)
                clicked = True
            except Exception as e:
                log.append({"step": "login", "note": f"Role-based click attempt failed: {e}"})

        if not clicked:
            # Save a screenshot for human debugging before giving up on this step
            try:
                screenshot_path = str(ROOT / "library" / "login_debug_screenshot.png")
                page.screenshot(path=screenshot_path, full_page=True)
                log.append({"step": "login", "note": f"Saved debug screenshot to {screenshot_path}"})
            except Exception as e:
                log.append({"step": "login", "note": f"Could not save debug screenshot: {e}"})
            log.append({"step": "login", "error": "Could not click 'Sign in with Password' by any method."})
            return False

        page.wait_for_timeout(1500)

        def fill_first_visible(selectors, value, field_label):
            """Try each selector, and within each, prefer a visible match
            over just .first — since this page appears to render duplicate
            (likely responsive mobile/desktop) copies of form elements."""
            for selector in selectors:
                try:
                    loc = page.locator(selector)
                    count = loc.count()
                    for i in range(count):
                        candidate = loc.nth(i)
                        if candidate.is_visible():
                            candidate.fill(value, timeout=3000)
                            log.append({"step": "login", "note": f"Filled {field_label} via '{selector}' (match {i+1}/{count})"})
                            return True
                except Exception:
                    continue
            return False

        # Fill email field — try common attribute patterns, preferring a
        # genuinely visible match given this page has duplicate elements.
        email_filled = fill_first_visible(
            ['input[type="email"]', 'input[name="email"]', 'input[placeholder*="email" i]'],
            email, "email",
        )
        if not email_filled:
            try:
                screenshot_path = str(ROOT / "library" / "login_debug_screenshot.png")
                page.screenshot(path=screenshot_path, full_page=True)
                log.append({"step": "login", "note": f"Saved debug screenshot to {screenshot_path}"})
            except Exception as e:
                log.append({"step": "login", "note": f"Could not save debug screenshot: {e}"})
            log.append({"step": "login", "error": "Could not find a visible email input field"})
            return False

        # Fill password field
        password_filled = fill_first_visible(
            ['input[type="password"]', 'input[name="password"]'],
            password, "password",
        )
        if not password_filled:
            log.append({"step": "login", "error": "Could not find password input field"})
            return False

        # Submit — try a button labeled Sign in / Log in / Continue, or press Enter
        submitted = False
        for label in ["Sign in", "Log in", "Continue", "Submit"]:
            try:
                candidates = page.get_by_role("button", name=re.compile(label, re.I))
                count = candidates.count()
                clicked_submit = False
                for i in range(count):
                    candidate = candidates.nth(i)
                    if candidate.is_visible():
                        candidate.click(timeout=3000)
                        clicked_submit = True
                        break
                if clicked_submit:
                    submitted = True
                    break
            except Exception:
                continue
        if not submitted:
            page.keyboard.press("Enter")

        page.wait_for_timeout(4000)

        # Verify login succeeded. A first attempt checked for "welcome back"
        # being gone, but the real dashboard ALSO has a "Welcome Back"
        # heading (just without the exclamation mark the login page uses),
        # producing a false negative even on successful login. Instead,
        # check for markers that only exist once actually logged in
        # (profile/account nav, plan status) — much less ambiguous.
        text = ""
        try:
            text = page.inner_text("body")
        except Exception:
            pass

        dashboard_markers = ["My Profile", "My Stuff", "Free plan", "Toggle Sidebar", "Build Gallery"]
        login_form_markers = ["Sign in with Password", "Continue with Google", "Don't have an account"]

        looks_logged_in = any(m.lower() in text.lower() for m in dashboard_markers)
        still_has_login_form = any(m.lower() in text.lower() for m in login_form_markers)

        if looks_logged_in and not still_has_login_form:
            log.append({"step": "login", "success": True})
            return True

        log.append({
            "step": "login",
            "error": "Could not confirm successful login (no dashboard markers found, or login form still present).",
            "page_text_sample": text[:500],
        })
        return False

    except Exception as e:
        log.append({"step": "login", "error": f"Unexpected error during login: {e}"})
        return False


def wait_out_bot_checkpoint(page, log, max_wait_ms=15000):
    """
    Vercel's bot-detection checkpoint shows an interstitial page (text like
    "Verifying your browser", "Vercel Security Checkpoint") before the real
    content loads, then auto-redirects once its JS challenge passes (or
    blocks permanently if the browser is flagged as automated).

    This polls the page for that interstitial text and waits for it to
    disappear before proceeding, instead of immediately trying to interact
    with what might just be the checkpoint page.

    IMPORTANT: a first run showed the checkpoint text disappearing (this
    function returning True) while the page still wasn't real content —
    meaning Vercel may serve additional/different block screens after the
    first interstitial clears. So beyond just checking these markers are
    gone, we also positively confirm real page content is present (the
    "Keyword:" label, which should exist on every real idea-of-the-day
    page) before declaring success.
    """
    checkpoint_markers = [
        "Security Checkpoint", "Verifying your browser", "verify you are human",
        "Failed to verify your browser", "Website owner? Click here to fix",
        "Checking your browser", "Just a moment", "Please wait while we verify",
        "Access denied", "blocked", "captcha", "Enable JavaScript and cookies",
    ]
    real_content_marker = "Keyword:"

    waited = 0
    interval = 1000
    while waited < max_wait_ms:
        try:
            text = page.inner_text("body")
        except Exception:
            text = ""

        has_checkpoint_text = any(m.lower() in text.lower() for m in checkpoint_markers)
        has_real_content = real_content_marker.lower() in text.lower()

        if has_real_content and not has_checkpoint_text:
            return True  # genuinely real content, no checkpoint text present
        page.wait_for_timeout(interval)
        waited += interval

    # Timed out — capture exactly what was on the page for debugging, since
    # "blocked" can mean several different things (checkpoint text still
    # present, OR checkpoint text gone but real content still never showed).
    try:
        final_text = page.inner_text("body")
    except Exception:
        final_text = "(couldn't read page text)"
    log.append({
        "step": "bot_checkpoint",
        "error": f"Checkpoint/block still present after {max_wait_ms}ms — likely blocked as automated.",
        "final_page_text_sample": final_text[:500],
    })
    return False


def get_visible_text(page):
    return page.inner_text("body")


def extract_summary_fields(text: str) -> dict:
    """Heuristic parse of the main page's plain text into structured fields."""
    out = {"raw_text": text.strip()}
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for l in lines:
        if len(l) > 8 and not l.lower().startswith(("idea", "sign", "log", "menu", "browse")):
            out["title"] = l
            break

    def score_after(label):
        m = re.search(rf"{label}\s*\n?\s*(\d{{1,2}})\s*\n?\s*([A-Za-z ]+)", text)
        if m:
            return {"score": int(m.group(1)), "label": m.group(2).strip()}
        return None

    out["opportunity"] = score_after("Opportunity")
    out["problem"] = score_after("Problem")
    out["feasibility"] = score_after("Feasibility")
    out["why_now"] = score_after("Why Now")

    def field_after(label):
        m = re.search(rf"{label}\s*\n\s*([^\n]+)", text)
        return m.group(1).strip() if m else None

    out["type"] = field_after("Type")
    out["market"] = field_after("Market")
    out["target"] = field_after("Target")
    out["main_competitor"] = field_after("Main Competitor")

    if "Trend Analysis" in text:
        seg = text.split("Trend Analysis", 1)[1]
        seg = seg.split("Community Signals", 1)[0]
        out["trend_analysis"] = seg.strip()[:2000]

    # Community signals counts, e.g. "Reddit \n 5 subreddits found"
    community = {}
    for platform in ["Reddit", "Facebook", "YouTube", "Other"]:
        m = re.search(rf"{platform}\s*\n\s*([^\n]+)", text)
        if m:
            community[platform.lower()] = m.group(1).strip()
    out["community_signals_summary"] = community

    return out


def crawl_keyword_analysis(crawler: Crawler) -> list:
    """
    Opens the Keyword Analysis dropdown, enumerates every keyword option,
    and for each keyword cycles through every time range, recording the
    Volume/Growth/CPC/Competition numbers shown.
    """
    page = crawler.page
    log = crawler.log
    results = []

    def open_keyword_dropdown():
        # Best-effort: the dropdown appears to be a clickable row showing
        # "Keyword: <current selection>" with a chevron.
        page.get_by_text(re.compile(r"^Keyword:", re.I)).first.click(timeout=8000)
        page.wait_for_timeout(WAIT_SHORT)

    def get_keyword_options():
        # Options appear to be plain text rows below the current selection
        # inside the opened dropdown panel.
        return page.locator("text=/^[A-Z][a-z].{2,60}$/").all()

    def open_time_dropdown():
        page.get_by_text(re.compile(r"^(6 Months|1 Year|2 Years|All Time)$")).first.click(timeout=8000)
        page.wait_for_timeout(WAIT_SHORT)

    def read_current_stats():
        text = get_visible_text(page)
        stats = {}
        for metric, pattern in [
            ("volume", r"([\d,.]+K?)\s*\n\s*Volume"),
            ("growth", r"([+\-][\d,.]+%)\s*\n\s*Growth"),
            ("cpc", r"\$([\d.,]+)\s*\n\s*CPC"),
            ("competition", r"([A-Za-z]+)\s*\n\s*Competition"),
        ]:
            m = re.search(pattern, text)
            if m:
                stats[metric] = m.group(1)
        return stats

    keyword_names = crawler.safe(
        lambda: [
            el.inner_text().strip()
            for el in page.locator("[role='option'], li, div").filter(
                has_text=re.compile(r".+")
            ).all()[:30]
        ],
        "list_keyword_options",
        default=[],
    )

    # Fallback: if we can't enumerate reliably, at least capture the
    # currently-selected keyword's stats across time ranges.
    if not keyword_names:
        current_kw = crawler.safe(
            lambda: page.get_by_text(re.compile(r"^Keyword:")).first.inner_text(),
            "read_current_keyword_label",
            default="unknown",
        )
        keyword_names = [current_kw]

    seen = set()
    for kw in keyword_names:
        kw_clean = kw.strip()
        if not kw_clean or kw_clean in seen or len(kw_clean) < 3:
            continue
        seen.add(kw_clean)

        entry = {"keyword": kw_clean, "by_time_range": {}}

        def select_keyword(k=kw_clean):
            open_keyword_dropdown()
            page.get_by_text(k, exact=True).first.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)

        crawler.safe(select_keyword, f"select_keyword:{kw_clean}")

        for tr in TIME_RANGES:
            def select_time_range(t=tr):
                open_time_dropdown()
                page.get_by_text(t, exact=True).first.click(timeout=8000)
                page.wait_for_timeout(WAIT_CHART)

            ok = crawler.safe(select_time_range, f"select_time_range:{kw_clean}:{tr}")
            stats = crawler.safe(read_current_stats, f"read_stats:{kw_clean}:{tr}", default={})
            entry["by_time_range"][tr] = stats

        results.append(entry)
        log.append({"step": "keyword_done", "keyword": kw_clean, "time_ranges_captured": len(entry["by_time_range"])})

    return results


def crawl_subpages(crawler: Crawler, base_url: str) -> dict:
    """
    Follows every 'View Analysis' style link/button on the main page into
    its sub-page, captures the rendered text, then returns to the main page.
    Also attempts to open the 'Execution Difficulty' modal in place.
    """
    page = crawler.page
    log = crawler.log
    subpages = {}

    link_labels = [
        "View Analysis",       # appears multiple times (Value Equation, Market Matrix, Value Ladder)
        "View detailed breakdown",  # Community Signals
        "Execution Plan",
        "Market Gap",
    ]

    for label in link_labels:
        locs = crawler.safe(lambda l=label: page.get_by_text(l, exact=False).all(), f"find_links:{label}", default=[])
        for i, loc in enumerate(locs or []):
            key = f"{label} #{i+1}" if len(locs) > 1 else label

            def click_and_capture(loc=loc, key=key):
                loc.scroll_into_view_if_needed(timeout=5000)
                loc.click(timeout=8000)
                page.wait_for_timeout(WAIT_CHART)
                text = get_visible_text(page)
                subpages[key] = {
                    "text": text.strip(),
                    "url": page.url,
                }
                # Navigate back to main page for the next link
                page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
                page.wait_for_timeout(WAIT_CHART)

            crawler.safe(click_and_capture, f"subpage:{key}")

    # Execution Difficulty modal (has visible X close button in screenshot)
    def open_execution_modal():
        page.get_by_text("Execution Difficulty", exact=False).first.click(timeout=8000)
        page.wait_for_timeout(WAIT_CHART)
        text = get_visible_text(page)
        subpages["Execution Difficulty"] = {"text": text.strip(), "url": page.url}
        # Close modal
        close_btn = page.locator("button:has(svg)").first
        crawler.safe(lambda: close_btn.click(timeout=5000), "close_execution_modal")

    crawler.safe(open_execution_modal, "execution_difficulty_modal")

    return subpages


def main():
    today = date.today()
    date_str = today.isoformat()
    year_dir = LIBRARY_DIR / str(today.year)
    year_dir.mkdir(parents=True, exist_ok=True)

    out_json = year_dir / f"{date_str}.deep.json"
    out_md = year_dir / f"{date_str}.deep.md"
    log_path = year_dir / f"{date_str}.crawl-log.json"

    # GitHub Actions sets GITHUB_EVENT_NAME to "schedule" for the automatic
    # daily run, and "workflow_dispatch" for a manual "Run workflow" click.
    # We only want the automatic run to skip an already-scraped day (so it
    # doesn't waste time re-scraping); a manual run is almost always someone
    # deliberately testing/retrying, so it should always run fresh even if
    # today's file already exists (e.g. from a previous failed attempt).
    is_manual_run = os.environ.get("GITHUB_EVENT_NAME") != "schedule"

    if out_json.exists() and not is_manual_run:
        print(f"Deep crawl already saved for {date_str}, skipping (scheduled run).")
        return
    elif out_json.exists():
        print(f"Deep crawl already exists for {date_str} — re-running anyway (manual trigger).")

    log = []
    record = {
        "date": date_str,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": URL,
        "summary": {},
        "keyword_analysis": [],
        "subpages": {},
    }

    with Stealth().use_sync(sync_playwright()) as p:
        browser, context = build_browser(p)
        page = context.new_page()
        crawler = Crawler(page, log)

        logged_in = login(page, log)
        if not logged_in:
            print("Login failed — saving diagnostic info and stopping early.")
            record["summary"] = {"raw_text": "", "login_failed": True}
            record["crawl_log"] = log
            out_json.write_text(json.dumps(record, indent=2), encoding="utf-8")
            log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
            browser.close()
            return

        try:
            page.goto(URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
            page.wait_for_timeout(3000)
            cleared = wait_out_bot_checkpoint(page, log)
            if not cleared:
                # Save whatever the checkpoint page looked like, for debugging,
                # and stop early rather than burning the full crawl on a wall.
                record["summary"] = {"raw_text": get_visible_text(page), "blocked_by_checkpoint": True}
                record["crawl_log"] = log
                out_json.write_text(json.dumps(record, indent=2), encoding="utf-8")
                log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
                print("Blocked by bot checkpoint — saved diagnostic info and stopping early.")
                browser.close()
                return
        except PWTimeout:
            log.append({"step": "initial_load", "error": "timeout"})

        main_text = crawler.safe(lambda: get_visible_text(page), "get_main_text", default="")
        record["summary"] = extract_summary_fields(main_text)

        record["keyword_analysis"] = crawler.safe(
            lambda: crawl_keyword_analysis(crawler), "crawl_keyword_analysis", default=[]
        ) or []

        # Return to a clean main-page state before sub-page crawling
        crawler.safe(lambda: page.goto(URL, wait_until="networkidle", timeout=NAV_TIMEOUT), "reload_before_subpages")
        page.wait_for_timeout(2000)
        wait_out_bot_checkpoint(page, log, max_wait_ms=8000)

        record["subpages"] = crawler.safe(
            lambda: crawl_subpages(crawler, URL), "crawl_subpages", default={}
        ) or {}

        browser.close()

    record["crawl_log"] = log

    out_json.write_text(json.dumps(record, indent=2), encoding="utf-8")
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    # Markdown summary for human reading
    md = [f"# {record['summary'].get('title', 'Idea of the Day')} — {date_str} (DEEP)", ""]
    md += [f"*Scraped: {record['scraped_at']}*  ", f"*Source: {URL}*", ""]
    md += [f"**{len(record['keyword_analysis'])} keywords captured, "
           f"{len(record['subpages'])} sub-pages captured, "
           f"{len(log)} log entries (see .crawl-log.json for any errors)**", ""]

    md += ["## Summary", "", "```json", json.dumps(record["summary"], indent=2)[:3000], "```", ""]

    md += ["## Keyword Analysis (all keywords x all time ranges)", ""]
    for kw in record["keyword_analysis"]:
        md.append(f"### {kw['keyword']}")
        for tr, stats in kw["by_time_range"].items():
            md.append(f"- **{tr}**: {stats}")
        md.append("")

    md += ["## Sub-pages", ""]
    for name, content in record["subpages"].items():
        md.append(f"### {name}")
        md.append(f"URL: {content.get('url')}")
        md.append("")
        md.append("```")
        md.append(content.get("text", "")[:4000])
        md.append("```")
        md.append("")

    out_md.write_text("\n".join(md), encoding="utf-8")

    errors = [l for l in log if "error" in l]
    print(f"Deep crawl saved: {out_json}")
    print(f"  Keywords captured: {len(record['keyword_analysis'])}")
    print(f"  Sub-pages captured: {len(record['subpages'])}")
    print(f"  Errors logged: {len(errors)} (see {log_path})")


if __name__ == "__main__":
    main()
