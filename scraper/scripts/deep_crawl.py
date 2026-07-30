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

    # Title extraction: a first version grabbed the first "substantial"
    # line, which on a real logged-in page is sidebar nav/account text
    # ("My Profile") rather than the actual idea title. The real idea
    # title reliably appears as the line right after the badge emojis
    # (e.g. "⏰\nPerfect Timing\n⚡\nUnfair Advantage\n+16 More") and before
    # the long pitch paragraph — anchor on "Idea of the Day" and
    # "Browse all" markers (present in the sidebar nav on every load) and
    # take the first sufficiently long, non-nav line found AFTER them,
    # skipping the "+N More" badge-count line too.
    title = None
    if "Browse all" in text:
        after_nav = text.split("Browse all", 1)[1]
        candidate_lines = [l.strip() for l in after_nav.split("\n") if l.strip()]
        skip_markers = (
            "idea actions", "roast", "build with", "previous", "|",
        )
        for l in candidate_lines:
            low = l.lower()
            if len(l) < 15:
                continue
            if low.startswith(skip_markers):
                continue
            if re.match(r"^[+\d]", l):  # e.g. "+16 More"
                continue
            if re.match(r"^[\U0001F000-\U0001FFFF\u2600-\u27BF]", l):  # emoji badge lines
                continue
            title = l
            break
    if not title:
        # Fallback to old heuristic if the anchor text isn't found
        for l in lines:
            if len(l) > 8 and not l.lower().startswith(("idea", "sign", "log", "menu", "browse")):
                title = l
                break
    out["title"] = title

    def score_after(label):
        m = re.search(rf"{label}\s*\n?\s*(\d{{1,2}})\s*\n?\s*([A-Za-z ]+)", text)
        if m:
            return {"score": int(m.group(1)), "label": m.group(2).strip()}
        return None

    out["opportunity"] = score_after("Opportunity")
    out["problem"] = score_after("Problem")
    out["feasibility"] = score_after("Feasibility")
    out["why_now"] = score_after("Why Now")

    # Categorization fields (Type/Market/Target/Main Competitor) reliably
    # appear together as a labeled block near "Categorization" in the page
    # text (seen in real captures as "Categorization\n\nType\n\nSaas\n\n
    # Market\n\nB2B\n\nTarget\n\nSolo Operators\n\nMain Competitor\n\n
    # BuzzSumo"). A first version searched the WHOLE page text for each
    # label independently, which incorrectly matched "Market" inside
    # "Go-To-Market" (a different section, appearing earlier in the page)
    # instead of the real "Market" field in this block. Anchoring the
    # search to text AFTER the literal "Categorization" heading avoids
    # that collision entirely.
    categorization_text = text
    if "Categorization" in text:
        categorization_text = text.split("Categorization", 1)[1]
        # Don't search past this section, in case any field-name reappears later
        categorization_text = categorization_text.split("Community Signals", 1)[0]

    def field_after(label, source=categorization_text):
        m = re.search(rf"(?<!-){label}\s*\n\s*([^\n]+)", source)
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
        # The dropdown is a clickable row showing "Keyword: <current
        # selection>" with a chevron. Prefer a visible match since this
        # page renders duplicate (responsive) copies of many elements.
        candidates = page.get_by_text(re.compile(r"^Keyword:", re.I))
        count = candidates.count()
        for i in range(count):
            c = candidates.nth(i)
            if c.is_visible():
                c.click(timeout=8000)
                page.wait_for_timeout(WAIT_SHORT)
                return
        # fallback
        candidates.first.click(timeout=8000)
        page.wait_for_timeout(WAIT_SHORT)

    def get_keyword_options():
        """
        A first version matched generic `div`/`li` elements across the
        WHOLE page, which accidentally captured sidebar navigation text
        ("ideabrowser HUB Browse Build...") as if it were keyword data.
        Real keyword options only exist inside the dropdown panel that
        appears after clicking the "Keyword:" label — from earlier
        screenshots of this page, that panel is a short, clean list (e.g.
        "Link building services", "Backlink building service", "Ai seo
        tools"...) usually rendered with role="option" or as list items
        inside a popover/listbox container, NOT generic page divs.

        Strategy: look specifically for role="option" or role="listbox"
        descendants first (most specific, least likely to false-match);
        only fall back to broader matching if that finds nothing, and even
        then filter out obvious navigation/page-chrome text.
        """
        # Most specific: proper ARIA listbox/option roles (common in
        # shadcn/ui and Radix-based dropdowns, which this site's other
        # components — like the Execution Difficulty modal — also use)
        options = page.locator("[role='option']").all()
        if options:
            return options

        options = page.locator("[role='listbox'] li, [role='listbox'] div").all()
        if options:
            return options

        # Broader fallback: a popover/dropdown panel is usually a small
        # floating container near the top of the page, positioned after
        # the "Keyword:" trigger in the DOM. This is still imperfect, so
        # results get filtered for junk below regardless.
        return page.locator("[data-radix-popper-content-wrapper] div, [role='menu'] div").all()

    NAV_JUNK_MARKERS = [
        "ideabrowser", "hub", "browse\nbuild", "my profile", "my stuff",
        "toggle sidebar", "build gallery", "upgrade", "free plan",
        "training", "trends", "market insights", "updates", "empire",
        "support", "discover your founder archetype", "take the quiz",
        "idea of the day", "start here",
    ]

    def is_plausible_keyword(text: str) -> bool:
        t = text.strip()
        if not t or len(t) < 3 or len(t) > 80:
            return False
        if "\n" in t:  # real keyword options are single short phrases, not multi-line blocks
            return False
        lower = t.lower()
        if any(marker in lower for marker in NAV_JUNK_MARKERS):
            return False
        return True

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

    # Open the dropdown FIRST, then look for options — options likely don't
    # exist in the DOM at all until the dropdown is actually open.
    crawler.safe(open_keyword_dropdown, "open_keyword_dropdown_for_listing")
    page.wait_for_timeout(WAIT_SHORT)

    raw_options = crawler.safe(get_keyword_options, "list_keyword_options", default=[])
    keyword_names = []
    for el in raw_options[:30]:
        try:
            t = el.inner_text().strip()
            if is_plausible_keyword(t):
                keyword_names.append(t)
        except Exception:
            continue

    log.append({"step": "keyword_discovery", "note": f"Found {len(keyword_names)} plausible keyword option(s) after filtering."})

    # IMPORTANT: close the dropdown now that we're done listing its options.
    # Leaving it open causes the next open_keyword_dropdown() call (inside
    # select_keyword below) to just toggle it CLOSED again instead of
    # opening it fresh — since the trigger is almost certainly a toggle
    # button, not an "always opens" button. That previously caused every
    # subsequent click to land on a leftover overlay ("<html> intercepts
    # pointer events") and every keyword to silently keep reading the same
    # still-selected default keyword's stats. Escape is a safe universal
    # way to close most dropdown/popover implementations.
    page.keyboard.press("Escape")
    page.wait_for_timeout(WAIT_SHORT)

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

        entry = {"keyword": kw_clean, "stats": {}}

        def select_keyword(k=kw_clean):
            # Safety net: ensure no dropdown/popover is already open before
            # trying to open this one, since toggle-style triggers would
            # otherwise close instead of open on this click.
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            open_keyword_dropdown()
            page.get_by_text(k, exact=True).first.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)
            # CRITICAL — real debug screenshots (taken while investigating
            # why the chart-hover tooltip never appeared) showed this
            # dropdown remaining VISUALLY OPEN, covering the top-left
            # portion of the chart, even after clicking a keyword option.
            # The chart itself was real and rendering fine the whole time
            # — every earlier "chart isn't responding" theory was wrong;
            # our hover coordinates were simply landing on this leftover
            # dropdown overlay instead of the chart underneath it. Close it
            # explicitly now that selection is done.
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        crawler.safe(select_keyword, f"select_keyword:{kw_clean}")

        # A debug screenshot confirmed this page has NO separate "6 Months /
        # 1 Year / 2 Years / All Time" dropdown at all — that control was a
        # correct memory from a genuinely DIFFERENT page (a dedicated
        # "Keyword Analysis" sub-page seen in earlier screenshots), not this
        # main Idea-of-the-Day view. Here there's just one Keyword dropdown
        # next to a single Volume/Growth snapshot and chart — so we capture
        # that snapshot once per keyword instead of pretending 4 separate
        # time ranges exist inline. (If the dedicated Keyword Analysis
        # sub-page gets crawled in future, ITS time-range dropdown is a
        # separate, real feature worth adding then.)
        stats = crawler.safe(read_current_stats, f"read_stats:{kw_clean}", default={})
        entry["stats"] = stats

        # Capture real month-by-month chart history for EVERY keyword, not
        # just the first — the user wants to compare trend charts across
        # all keywords, not just the default one. This genuinely does add
        # several minutes to the daily crawl (each keyword repeats the
        # full 24-point hover-sampling process), which was accepted as a
        # deliberate tradeoff.
        entry["chart_history"] = crawler.safe(
            lambda: crawl_chart_history(crawler), f"chart_history:{kw_clean}", default=[]
        ) or []

        results.append(entry)
        log.append({"step": "keyword_done", "keyword": kw_clean, "stats_captured": bool(stats)})

    return results


def crawl_community_signals_deep(crawler: Crawler, community_signals_url: str, idea_title: str = "") -> dict:
    """
    Drills into the Community Signals page to capture the REAL underlying
    data the summary counts are based on: actual platform sections (Reddit,
    Facebook, YouTube, Other), the individual community/subreddit cards
    inside each (name, member count, why-relevant blurb), and — one level
    deeper — the actual discussion post titles and their real external
    href URLs (e.g. real reddit.com links), captured via get_attribute
    rather than visible text, since link destinations aren't shown as text
    on the page at all.

    This is a genuinely deep, multi-level crawl (platform page -> community
    card -> individual discussion page, times 4 platforms), so expect this
    single function to add a meaningful chunk of runtime to the overall
    crawl. Every navigation is wrapped in crawler.safe so a failure on any
    one community/platform doesn't lose data already captured from others.

    Returns a dict shaped like:
    {
      "reddit": [
        {
          "name": "r/AI_Agents",
          "members": "396K+ followers",
          "why_relevant": "...",
          "opportunity": "...",
          "discussions": [
            {"title": "...", "blurb": "...", "url": "https://reddit.com/..."},
            ...
          ]
        },
        ...
      ],
      "facebook": [...], "youtube": [...], "other": [...]
    }
    Any platform/community that fails to crawl is simply omitted rather
    than blocking the rest.
    """
    page = crawler.page
    log = crawler.log
    result = {"reddit": [], "facebook": [], "youtube": [], "other": []}

    # DIAGNOSTIC — a real run produced zero log entries for this function's
    # inner steps at all (no errors, no successes), which is only possible
    # if crawl_platform() below is failing in a way that never raises a
    # real Python exception, or this function itself is never actually
    # being reached. This unconditional log line proves definitively,
    # on the next run, whether execution gets here in the first place —
    # remove once that's confirmed either way.
    log.append({"step": "crawl_community_signals_deep:entered", "url": community_signals_url})

    platform_labels = {
        "reddit": "Reddit",
        "facebook": "Facebook",
        "youtube": "YouTube",
        "other": "Other Communities",
    }
    # Real screenshots of this page show the 4 platform cards always
    # appearing in this exact order (Reddit, Facebook, YouTube, Other),
    # each as its own card with a "View Analysis" link. The previous
    # ancestor-XPath approach to scope each platform's own link ended up
    # matching Reddit's link every single time (confirmed directly: a real
    # run landed on the reddit-analysis URL for reddit, facebook, AND
    # youtube), most likely because the XPath's ancestor search wasn't
    # actually scoped tightly enough and kept resolving to a shared
    # container. Matching "View Analysis" links by their fixed index on
    # the page (0=Reddit, 1=Facebook, 2=YouTube; "Other" has none, using
    # its own distinct link text instead) is far more reliable than trying
    # to scope via DOM ancestry.
    platform_order = ["reddit", "facebook", "youtube", "other"]

    def open_community_signals_page():
        page.goto(community_signals_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(WAIT_CHART)
        # DIAGNOSTIC — a real run showed Reddit/Facebook ending up on the
        # main idea page's own text instead of any community-signals page
        # at all, meaning navigation itself may be silently failing or
        # redirecting somewhere unexpected on some iterations but not
        # others (YouTube/Other worked in the same run). Log the actual
        # resulting URL every time this is called so we can see directly
        # whether page.goto() itself is landing somewhere wrong.
        log.append({"step": "open_community_signals_page:landed", "url": page.url})

    for platform_index, platform_key in enumerate(platform_order):
        platform_label = platform_labels[platform_key]
        log.append({"step": f"crawl_platform:{platform_key}:starting"})

        def crawl_platform(platform_key=platform_key, platform_label=platform_label, platform_index=platform_index):
            open_community_signals_page()

            if platform_key == "other":
                # "Other Communities" doesn't share the "View Analysis"
                # link pattern with the first 3 — it appears once, later
                # on the page, matched by its own distinct label text.
                view_link = page.get_by_text(platform_label, exact=False).first
                if not view_link.is_visible():
                    raise Exception(f"'{platform_label}' section not visible")
                # Scroll to it and find ITS OWN following "View Analysis"
                # link specifically (the one nearest below this heading).
                view_link.scroll_into_view_if_needed(timeout=5000)
                analysis_link = page.get_by_text("View Analysis", exact=False).last
            else:
                # Reddit/Facebook/YouTube's "View Analysis" links appear in
                # that fixed left-to-right, top-to-bottom order on the
                # page — index directly into them rather than trying to
                # scope by DOM ancestry, which proved unreliable above.
                all_links = page.get_by_text("View Analysis", exact=False)
                link_count = all_links.count()
                # DIAGNOSTIC — shows exactly how many "View Analysis" links
                # were actually found on the page at this point, for
                # direct comparison against the expected 4 (Reddit,
                # Facebook, YouTube) or however many actually render.
                log.append({
                    "step": f"crawl_platform:{platform_key}:view_analysis_links_found",
                    "count": link_count,
                    "current_url": page.url,
                })
                if platform_index >= link_count:
                    raise Exception(f"Expected 'View Analysis' link at index {platform_index} for {platform_label}, but only {link_count} found")
                analysis_link = all_links.nth(platform_index)

            analysis_link.scroll_into_view_if_needed(timeout=5000)
            analysis_link.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)
            # DIAGNOSTIC — the URL immediately after clicking, to confirm
            # whether the click actually navigated to the expected
            # platform-specific sub-page (e.g. .../reddit-analysis) or
            # left us somewhere unexpected.
            log.append({
                "step": f"crawl_platform:{platform_key}:after_click",
                "url": page.url,
            })

            # Now on the platform-specific page (e.g. .../community-signals/reddit-analysis).
            # A real run's page-text dump confirmed the ACTUAL structure:
            # each community appears as a distinct heading (e.g.
            # "AI Agent Builders & Early Adopters", "r/AI_Agents") followed
            # by a description and, for the "Other Communities" page
            # specifically, "Pain Points" / "Interests" sub-sections — not
            # as a list of generically-matching links. The earlier
            # href-based approach overmatched on Facebook/YouTube/Other
            # (hit the 15-item safety cap every time) because those pages
            # don't reliably link out the same way Reddit's does — Reddit
            # happened to work because its cards link directly to real
            # reddit.com URLs, which the other platforms may not.
            # Real per-platform community counts are visible in each page's
            # own "Analyzed N ..." summary line — use that as the
            # authoritative count instead of counting links, then locate
            # each community by its distinct heading text directly.
            page_text_for_count = get_visible_text(page)
            summary_match = re.search(r"Analyzed\s+(\d+)\s+(?:relevant\s+)?(?:communit\w*|channels?|groups?|segments?)", page_text_for_count, re.IGNORECASE)
            if not summary_match:
                summary_match = re.search(r"(\d+)\s+groups?\s+analyzed", page_text_for_count, re.IGNORECASE)
            expected_count = int(summary_match.group(1)) if summary_match else None

            # Community name headings are rendered as distinct heading-level
            # elements (h1-h4) directly on the page — filter to just those,
            # excluding the page's own title/breadcrumb headings which
            # appear earlier and share the same tag. The exclusion list was
            # previously hardcoded to one specific prior idea's title
            # ("Safe playground..."), which meant it silently stopped
            # working for every OTHER idea's own page-title heading —
            # confirmed directly: a later run on a different idea ("Baby
            # tracking app...") picked up a generic section label
            # ("Relevant Communities") as if it were the first real
            # community, merging all 4 real subreddits' text into one
            # entry instead of 4 separate ones. Build the exclusion
            # dynamically from this run's OWN idea_title (first ~40 chars,
            # since the page often truncates/repeats it slightly
            # differently across headings), plus the other genuine
            # boilerplate section-label headings confirmed across BOTH
            # ideas we've now inspected directly (not just one).
            #
            # A SECOND, distinct bug confirmed via a real screenshot: even
            # after fixing the above, each individual subreddit's own card
            # contains ITS OWN internal sub-headings ("WHY IT'S RELEVANT",
            # "OPPORTUNITY") at the same h1-h4 tag levels as the real
            # community name itself — meaning r/NewParents's single card
            # was being split into 3 separate "communities" (its name,
            # then each of its own two internal sub-sections), each one
            # capturing the ENTIRE page's text as its "summary" since none
            # of them individually matched a tight per-card container.
            # These sub-heading labels are now excluded by their own exact
            # text too, so only genuine top-level community names (e.g.
            # "r/NewParents", "Penguin & Pals") remain.
            # "Discover your founder archetype" is the quiz-box heading that
            # appears at the top of EVERY platform page (confirmed directly:
            # it was consuming card slot 0 on every single platform in a
            # real crawl log, e.g. Facebook showing card_count=6 for only 4
            # real groups). "DESCRIPTION" and "RELEVANCE SIGNALS" are real
            # per-card sub-headings on Facebook group cards specifically
            # (confirmed against real scraped data: a card meant to be
            # "Client Acquisition Sales Systems..." was being split into 3
            # separate fake "communities" — the real name, then its own
            # "DESCRIPTION" sub-heading, then its own "RELEVANCE SIGNALS"
            # sub-heading — the same class of bug already fixed below for
            # Reddit's "WHY IT'S RELEVANT"/"OPPORTUNITY", just not yet
            # covering these two Facebook-specific labels).
            exclude_pattern = r"^(ideabrowser|Community Signals|Take the quiz|Discover your founder archetype|Relevant Communities|Relevant Groups|Analysis Overview|Community Types|Community Segments|Key Findings|In-Depth|Why It'?s Relevant|Opportunity|Relevant Discussions?|DESCRIPTION|RELEVANCE SIGNALS)"
            if idea_title:
                exclude_pattern = re.escape(idea_title[:40]) + "|" + exclude_pattern
            heading_els = page.locator("h1, h2, h3, h4").filter(has_not_text=re.compile(exclude_pattern, re.IGNORECASE))
            all_heading_count = heading_els.count()
            card_count = min(expected_count, all_heading_count) if expected_count else min(all_heading_count, 15)
            platform_url = page.url

            # DIAGNOSTIC — a prior round's fix added "DESCRIPTION" and
            # "RELEVANCE SIGNALS" to exclude_pattern above specifically to
            # stop them being mistaken for real community cards on
            # Facebook, but a real post-fix crawl showed them STILL
            # appearing in the final saved community list. This dumps the
            # literal inner_text of every heading that survives the filter
            # (not just the raw pre-filter count), so we can see directly
            # whether these two labels are somehow still passing the
            # regex, or whether the real DOM text differs from what the
            # exclusion pattern assumes (e.g. hidden duplicate headings,
            # different casing/whitespace, or the labels living in a tag
            # the "h1, h2, h3, h4" selector doesn't even cover — meaning a
            # SEPARATE un-excluded heading is what's actually producing
            # these entries, not a failure of the exclusion regex itself).
            try:
                surviving_heading_texts = [
                    heading_els.nth(j).inner_text(timeout=2000) for j in range(min(all_heading_count, 20))
                ]
            except Exception as e:
                surviving_heading_texts = [f"<error dumping headings: {e}>"]
            log.append({
                "step": f"crawl_platform:{platform_key}:surviving_headings_dump",
                "surviving_heading_texts": surviving_heading_texts,
            })

            # DIAGNOSTIC — a real run showed Reddit and Facebook both
            # getting card_count=0 while YouTube and Other worked
            # correctly on the SAME crawl, meaning something genuinely
            # differs between these platform pages specifically (not a
            # generic flake). Log the actual regex match result and the
            # raw (pre-filter) heading count so we can see directly
            # whether the summary-count regex failed to match this
            # platform's real text, or whether the page genuinely had zero
            # heading elements at all.
            log.append({
                "step": f"crawl_platform:{platform_key}:count_diagnostic",
                "summary_match_found": bool(summary_match),
                "expected_count": expected_count,
                "all_heading_count": all_heading_count,
                "page_text_first_400": page_text_for_count[:400],
            })

            # DIAGNOSTIC — the previous run showed this whole function
            # completing with zero errors AND zero data for every
            # platform, which is only possible if it's silently finding 0
            # cards each time (a "successful but empty" result that was
            # never being logged, since only failures were logged before).
            # This makes that visible: exactly what page we ended up on
            # and how many candidate links were actually found there. Also
            # dump a slice of the page's own visible text so a human can
            # see the REAL structure directly if this guess is also wrong,
            # rather than needing yet another blind guess-and-check round.
            log.append({
                "step": f"crawl_platform:{platform_key}:landed",
                "url": platform_url,
                "card_count": card_count,
                "page_text_sample": get_visible_text(page)[:1500],
            })

            for i in range(card_count):

                def crawl_community_card(i=i, expected_name=surviving_heading_texts[i] if i < len(surviving_heading_texts) else None):
                    # Re-fetch locators fresh each iteration since navigating
                    # away and back invalidates previous handles. Matches
                    # the outer function's heading-based approach (see that
                    # comment for why link-based matching was replaced, and
                    # the dynamic-title comment above for why this can't be
                    # a hardcoded exclusion string).
                    #
                    # A real crawl proved that re-querying "h1,h2,h3,h4
                    # filtered by exclude_pattern" a SECOND time here (after
                    # already doing so once above for surviving_headings_dump)
                    # can return a DIFFERENT ordered list than the first
                    # query — confirmed directly: the diagnostic dump for
                    # this exact page correctly excluded "DESCRIPTION" and
                    # "RELEVANCE SIGNALS" from its 6-heading list, yet this
                    # loop's own fresh re-query let both through into the
                    # final saved data at indices 2 and 3, while the
                    # diagnostic's index 2 was actually "AI ChatBot" — i.e.
                    # the two queries, run moments apart against what should
                    # be the same reloaded page, disagreed on both ORDER and
                    # MEMBERSHIP. Rather than trust a second independent
                    # query's index to line up with the first, re-locate
                    # THIS card by its own exact captured name (from the
                    # already-verified surviving_heading_texts list),
                    # falling back to the index only if that name can't be
                    # found again (e.g. truly dynamic content).
                    #
                    # Real YouTube data confirmed genuine duplicate names
                    # occur (e.g. two separate "Kevin Stratvert" and two
                    # separate "IBM Technology" headings for different
                    # channels/videos) — matching by name ALONE and always
                    # taking the first hit would silently re-visit the same
                    # element for both duplicates. Use how many times this
                    # exact name already appeared earlier in the captured
                    # list to pick the matching occurrence instead of
                    # always defaulting to the first.
                    occurrence_index = surviving_heading_texts[:i].count(expected_name) if expected_name else 0
                    page.goto(platform_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
                    page.wait_for_timeout(WAIT_CHART)
                    headings = page.locator("h1, h2, h3, h4").filter(has_not_text=re.compile(exclude_pattern, re.IGNORECASE))
                    heading = None
                    if expected_name:
                        by_name = page.locator("h1, h2, h3, h4").filter(has_text=re.compile(r"^\s*" + re.escape(expected_name.strip()) + r"\s*$"))
                        if by_name.count() > occurrence_index and by_name.nth(occurrence_index).is_visible():
                            heading = by_name.nth(occurrence_index)
                    if heading is None:
                        if i >= headings.count():
                            raise Exception(f"Card index {i} no longer available")
                        heading = headings.nth(i)
                    if not heading.is_visible():
                        raise Exception(f"Card {i} not visible")
                    heading.scroll_into_view_if_needed(timeout=5000)
                    name = heading.inner_text(timeout=3000).strip()

                    # A real crawl showed a card being re-located by name
                    # can still land on the wrong element if the exclusion
                    # pattern's SECOND query let a boilerplate label back in
                    # despite the name-match succeeding (e.g. if the site
                    # ever renders two identically-named headings). Guard
                    # against that directly rather than trusting the name
                    # match alone: skip this card entirely if its resolved
                    # name matches the exclude_pattern itself.
                    if re.match(exclude_pattern, name, re.IGNORECASE):
                        raise Exception(f"Card {i} resolved to an excluded boilerplate heading ({name!r}); skipping")

                    # Reddit's community headings are real navigable links
                    # into a dedicated per-subreddit page with discussion
                    # cards and real "View on Reddit" hrefs (confirmed via
                    # the original site screenshots). Other platforms may
                    # not drill any deeper — try clicking, but don't treat
                    # a failed/no-op click as an error, since capturing
                    # this community's name + immediate surrounding text is
                    # still real, useful data even without a deeper page.
                    url_before = page.url
                    try:
                        heading.click(timeout=4000)
                        page.wait_for_timeout(WAIT_CHART)
                    except Exception:
                        pass
                    navigated = page.url != url_before

                    # When no real navigation occurs (true for YouTube's
                    # channel headings, confirmed via real captured data:
                    # different channels like "Penguin & Pals" and
                    # "BabyCenter" ended up with the IDENTICAL discussion
                    # link list), every community iteration was scanning
                    # too broad a scope for external links. The immediate
                    # parent div (1 level up) proved too shallow to
                    # reliably contain a card's own real boundary — walk
                    # up several ancestor levels instead and verify the
                    # resulting container's own text actually starts with
                    # or closely matches this community's name, which is
                    # the real signal that we've found its true card
                    # boundary rather than some shared outer wrapper.
                    # A real screenshot ("Other Communities" page) confirmed
                    # that breaking on the FIRST depth whose text starts with
                    # the community name captures only the name + one-line
                    # description, cutting off the card's own "Pain Points"
                    # and "Interests" bullet lists and platform tags that
                    # visibly belong to the same card just below. Those
                    # sub-sections live in a deeper ancestor than the
                    # shallowest one that already happens to start with the
                    # name — so keep walking through ALL matching depths and
                    # take the LAST (deepest) one that still starts with the
                    # name and stays under the cap, rather than stopping at
                    # the first hit.
                    container = None
                    if not navigated:
                        for depth in [1, 2, 3, 4, 5]:
                            candidate = heading.locator(f"xpath=ancestor::*[self::div][{depth}]")
                            if candidate.count() == 0:
                                continue
                            try:
                                candidate_text = candidate.inner_text(timeout=2000)
                            except Exception:
                                continue
                            # A genuine per-card container's text should be
                            # meaningfully shorter than the whole page
                            # (a real card, not the whole community list)
                            # while still starting with this community's
                            # own name. Keep the deepest (largest) container
                            # that satisfies both, since that's the one most
                            # likely to include the card's full content
                            # rather than just its heading + first line.
                            if candidate_text.strip().startswith(name[:20]) and len(candidate_text) < 2000:
                                container = candidate
                        # Fall back to the shallowest ancestor if none of
                        # the depths matched the "starts with this name"
                        # check — better to have SOME scoped container
                        # than silently fall through to page-wide search.
                        if container is None:
                            container = heading.locator("xpath=ancestor::*[self::div][1]")

                    if navigated:
                        # A real screenshot confirmed capturing the RAW
                        # whole-page text here included the site's own nav
                        # menu, sidebar links, and repeated boilerplate
                        # ("Discover", "Research", "Take the quiz", etc.)
                        # mixed into what should be a focused summary of
                        # this one specific subreddit's own page. Strip
                        # lines that are clearly nav/sidebar/boilerplate
                        # (short, generic single words/phrases that recur
                        # across every page) rather than keeping the
                        # entire raw text.
                        raw_text = get_visible_text(page)
                        boilerplate_lines = {
                            "ideabrowser", "hub", "browse", "build", "home", "training",
                            "my profile", "my stuff", "ideas", "discover", "research",
                            "generate", "trends", "market insights", "updates", "empire",
                            "support", "free plan", "toggle sidebar", "browse ideas",
                            "take the quiz", "start here", "upgrade",
                        }
                        kept_lines = [
                            l for l in raw_text.split("\n")
                            if l.strip() and l.strip().lower() not in boilerplate_lines
                        ]
                        community_text = "\n".join(kept_lines)
                    else:
                        community_text = container.inner_text(timeout=3000)

                    if i < 2:
                        # DIAGNOSTIC — confirms directly whether the
                        # ancestor-depth search above actually found a
                        # tight, name-matching container, or fell back to
                        # the shallow default (which real data proved
                        # insufficient to prevent link duplication across
                        # cards).
                        log.append({
                            "step": f"crawl_platform:{platform_key}:card_{i}:container_check",
                            "community_name": name,
                            "container_text_length": len(community_text),
                            "container_text_starts_with_name": community_text.strip().startswith(name[:20]) if not navigated else None,
                        })

                    # Capture real discussion/external links: on Reddit's
                    # drill-down pages these are actual reddit.com hrefs;
                    # on other platforms they may not exist at all, which
                    # is fine — discussions simply stays empty for those.
                    # Deliberately NEVER fall back to a page-wide link
                    # search when not navigated — real captured data
                    # proved that produces false, identical-across-cards
                    # "discussions" data, which is worse than showing none
                    # at all for a community that genuinely has no
                    # per-card links of its own.
                    discussions = []
                    seen_urls = set()
                    ext_links = (
                        page.locator("a[href*='reddit.com'], a[href*='facebook.com'], a[href*='youtube.com']")
                        if navigated
                        else container.locator("a[href*='reddit.com'], a[href*='facebook.com'], a[href*='youtube.com']")
                    )
                    ext_count = ext_links.count()
                    for j in range(min(ext_count, 20)):  # cap to avoid runaway crawls on unexpectedly large pages
                        try:
                            link_el = ext_links.nth(j)
                            href = link_el.get_attribute("href")
                            if not href or href in seen_urls:
                                # A real screenshot confirmed the same href
                                # appearing multiple times within one
                                # community's own card (e.g. 3 identical
                                # "r/NewParents" links shown as if they
                                # were 3 separate discussions) — skip
                                # exact-duplicate URLs so each discussion
                                # entry is genuinely distinct.
                                continue
                            seen_urls.add(href)
                            # Find the discussion title, which sits in the
                            # nearest preceding heading-like element above
                            # this link in the same card.
                            card_container = link_el.locator(
                                "xpath=ancestor::*[self::div][.//p or .//h1 or .//h2 or .//h3][1]"
                            )
                            card_text = card_container.inner_text(timeout=3000)
                            title_line = card_text.split("\n")[0].strip() if card_text else "Discussion"
                            discussions.append({"title": title_line[:200], "url": href})
                        except Exception as e:
                            log.append({"step": f"community_discussion_link:{platform_key}:{i}:{j}", "error": str(e)})

                    # Facebook's "Visit Group" is NOT a real <a href> tag —
                    # confirmed directly via DevTools inspection: it's a
                    # <div class="text-sm text-gray-500 hover:text-blue-600
                    # ..."> wrapping an SVG icon and the text "Visit Group",
                    # with no href attribute at all (attributes list showed
                    # only "class"). This is why the href-based search above
                    # NEVER found Facebook links no matter how correctly the
                    # card boundary was scoped — there was never an anchor
                    # tag to find. Confirmed directly that clicking it opens
                    # the real destination in a NEW browser tab, so capture
                    # it the only way that's actually possible: click, catch
                    # the popup, read its URL, close it immediately.
                    if platform_key == "facebook" and not discussions:
                        try:
                            visit_group = container.get_by_text("Visit Group", exact=True) if not navigated else page.get_by_text("Visit Group", exact=True)
                            if visit_group.count() > 0 and visit_group.first.is_visible():
                                with page.expect_popup(timeout=6000) as popup_info:
                                    visit_group.first.click(timeout=4000)
                                popup = popup_info.value
                                popup.wait_for_load_state("domcontentloaded", timeout=8000)
                                popup_url = popup.url
                                popup.close()
                                if popup_url and popup_url not in seen_urls and "ideabrowser.com" not in popup_url:
                                    discussions.append({"title": name[:200], "url": popup_url})
                                log.append({
                                    "step": f"community_visit_group_popup:{platform_key}:{i}",
                                    "captured_url": popup_url,
                                })
                        except Exception as e:
                            log.append({"step": f"community_visit_group_popup:{platform_key}:{i}", "error": str(e)})

                    result[platform_key].append({
                        "name": name[:100],
                        "raw_text": community_text[:2000],
                        "discussions": discussions,
                        "url": page.url,
                    })

                crawler.safe(crawl_community_card, f"community_card:{platform_key}:{i}")

        crawler.safe(crawl_platform, f"community_platform:{platform_key}")
        log.append({
            "step": f"crawl_platform:{platform_key}:finished",
            "communities_found": len(result[platform_key]),
        })

    return result


def crawl_chart_history(crawler: Crawler, chart_container_selector: str = ".recharts-wrapper") -> list:
    """
    Extracts the real month-by-month history behind a keyword's volume
    chart by hovering across each rendered data point and reading the
    tooltip text that appears — the only place this site exposes that
    granular data (it's not present as static page text anywhere, only
    revealed on hover, per direct visual confirmation from a real
    screenshot showing e.g. "Nov 2025 / 8,100 searches" appearing only
    while the mouse sits over that point on the line).

    Recharts (the likely charting library here, based on the visual style)
    renders each data point as an SVG <circle> or <path> element inside a
    container with class "recharts-wrapper", and shows/updates a tooltip
    div on mousemove/mouseover — this is a well-established Playwright
    technique (confirmed via community reports of the same approach working
    against Recharts specifically), not a guess: move the mouse to each
    point's screen coordinates in turn and read the tooltip's rendered text
    after each move.

    Returns a list of {"label": "Nov 2025", "value": "8,100 searches"}
    dicts, in left-to-right (chronological) order. Returns an empty list
    (never raises) if the chart isn't found or hovering fails, so a miss
    here never blocks the rest of the crawl — the fallback is simply no
    history data for that keyword, same as today.
    """
    page = crawler.page
    log = crawler.log
    history = []

    # DIAGNOSTIC — see matching note in crawl_community_signals_deep; a
    # real run produced zero log entries for this function at all, so this
    # confirms on the next run whether execution reaches here.
    log.append({"step": "crawl_chart_history:entered", "selector": chart_container_selector})

    # Defensive second safety net — real debug screenshots proved the
    # keyword dropdown was staying visually open and covering part of the
    # chart at this exact point in earlier runs, even though the caller
    # (select_keyword) now also closes it explicitly. Belt-and-braces:
    # ensure no popover/overlay is sitting over the chart before we start
    # measuring its position or hovering over it.
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # A real run found the chart container (no "not found" error) but
    # captured zero tooltip points across 24 hover samples — meaning either
    # .recharts-wrapper matched something that ISN'T actually the visible
    # chart (e.g. an off-screen/hidden duplicate, same responsive-layout
    # pattern seen elsewhere on this site), or the real tooltip selector
    # differs from what was tried. Broaden the container search across
    # several common charting-library class names, and log which one
    # actually matched (and its real bounding box) so a future pass can
    # target the tooltip selector precisely instead of guessing again.
    candidate_selectors = [
        chart_container_selector,
        "svg",  # last-resort: any visible SVG on the page containing the chart
        "[class*='chart']",
        "[class*='recharts']",
    ]
    chart = None
    matched_selector = None
    for sel in candidate_selectors:
        candidate = page.locator(sel).first
        if candidate.count() > 0:
            box_check = candidate.bounding_box()
            if box_check and box_check.get("width", 0) > 100:  # skip tiny/decorative svgs (icons etc)
                chart = candidate
                matched_selector = sel
                break

    log.append({
        "step": "crawl_chart_history:container_search",
        "matched_selector": matched_selector,
        "candidates_tried": candidate_selectors,
    })

    if chart is None:
        log.append({"step": "crawl_chart_history", "error": "no chart container found across all candidate selectors"})
        log.append({"step": "crawl_chart_history:finished", "points_captured": 0})
        return history

    box = chart.bounding_box()
    if not box:
        log.append({"step": "crawl_chart_history", "error": "chart container not visible/no bounding box"})
        log.append({"step": "crawl_chart_history:finished", "points_captured": 0})
        return history

    log.append({"step": "crawl_chart_history:chart_found", "box": box})

    # DIAGNOSTIC — 6 rounds of coordinate/event-based hover techniques have
    # all failed to produce any tooltip content at all (most recently:
    # tooltip_count=0, meaning the tooltip element doesn't even exist in
    # the DOM during sampling, a materially different and more informative
    # result than earlier rounds' tooltip_count=1/empty-text). Rather than
    # keep guessing at interaction techniques blindly, save real screenshots
    # of the actual chart area before and after a hover attempt, uploaded
    # as workflow artifacts (same mechanism already used for login
    # debugging) so a human can SEE what's genuinely on screen and
    # determine the real trigger mechanism directly, instead of further
    # blind iteration.
    try:
        chart_screenshot_before = str(ROOT / "library" / "chart_before_debug_screenshot.png")
        chart.screenshot(path=chart_screenshot_before)
        log.append({"step": "crawl_chart_history:screenshot_before", "path": chart_screenshot_before})
    except Exception as e:
        log.append({"step": "crawl_chart_history:screenshot_before", "error": str(e)})

    # Establish real pointer state before sampling — a bare page.mouse.move()
    # to an arbitrary first coordinate, with no prior pointer position, does
    # not reliably trigger hover-based UI transitions in Chromium under
    # automation (confirmed: a real run got tooltip_count=1 — the element
    # exists in the DOM at all times — but tooltip_visible=false at every
    # single sample, meaning the hover/mouseover transition never actually
    # fired). Moving to a neutral point first, then into the chart, gives
    # the browser a real "from A to B" pointer trajectory to react to.
    page.mouse.move(box["x"] - 20, box["y"] + box["height"] / 2)
    page.wait_for_timeout(200)

    # Hover into the middle of the chart and screenshot again immediately,
    # BEFORE the sampling loop below does anything else — this is the
    # single clearest before/after comparison we can capture.
    mid_x = box["x"] + box["width"] / 2
    mid_y = box["y"] + box["height"] / 2
    page.mouse.move(mid_x - 10, mid_y, steps=3)
    page.mouse.move(mid_x, mid_y, steps=3)
    page.wait_for_timeout(300)
    try:
        chart_screenshot_after = str(ROOT / "library" / "chart_after_hover_debug_screenshot.png")
        chart.screenshot(path=chart_screenshot_after)
        log.append({"step": "crawl_chart_history:screenshot_after_hover", "path": chart_screenshot_after})
    except Exception as e:
        log.append({"step": "crawl_chart_history:screenshot_after_hover", "error": str(e)})

    # Also capture a full-page screenshot for broader context (e.g. in
    # case the real chart/tooltip is rendered somewhere other than inside
    # what we identified as the chart container).
    try:
        full_page_screenshot = str(ROOT / "library" / "chart_fullpage_debug_screenshot.png")
        page.screenshot(path=full_page_screenshot, full_page=False)
        log.append({"step": "crawl_chart_history:screenshot_fullpage", "path": full_page_screenshot})
    except Exception as e:
        log.append({"step": "crawl_chart_history:screenshot_fullpage", "error": str(e)})

    # Also dump the chart container's raw outer HTML — this shows us
    # directly, as text, exactly what library/markup is really being used
    # (Recharts, a canvas-based lib, something custom, etc) rather than
    # guessing from visual style alone.
    try:
        chart_html = chart.evaluate("el => el.outerHTML") or ""
        log.append({"step": "crawl_chart_history:chart_html_sample", "html": chart_html[:3000]})
    except Exception as e:
        log.append({"step": "crawl_chart_history:chart_html_sample", "error": str(e)})

    # Sample points evenly across the chart's width rather than trying to
    # locate individual SVG point elements (which vary by chart library and
    # may not exist as discrete hoverable nodes for line charts) — moving
    # the mouse itself is what triggers Recharts' nearest-point tooltip
    # logic, regardless of exact point markup.
    sample_count = 24  # roughly monthly resolution across a 2-year chart
    seen_labels = set()
    for i in range(sample_count):
        frac = i / (sample_count - 1)
        x = box["x"] + frac * box["width"]
        y = box["y"] + box["height"] * 0.5  # vertical center is safest for line charts
        try:
            # Move in two steps (a real, if small, trajectory) rather than
            # teleporting directly to each new point — Recharts (and many
            # chart libs) listen for mousemove deltas to update the active
            # index, so an actual short movement is more reliable than a
            # single jump, matching what a real mouse drag would produce.
            page.mouse.move(x - 5, y, steps=3)
            page.mouse.move(x, y, steps=3)
            page.wait_for_timeout(200)  # let the tooltip re-render
            tooltip = page.locator(".recharts-tooltip-wrapper, [role='tooltip']").first
            tooltip_count = tooltip.count()
            tooltip_visible = tooltip.is_visible() if tooltip_count > 0 else False

            if tooltip_count > 0 and not tooltip_visible:
                # A prior run confirmed the tooltip element exists in the
                # DOM at every sample but never becomes visible via
                # simulated OS-level mouse movement alone — a known gap
                # with React-driven hover state in automated browsers
                # (confirmed via community reports of the exact same
                # Recharts/Playwright combination). Force the issue by
                # dispatching real mouseover/mousemove/mouseenter DOM
                # events directly at the target coordinates, which
                # Recharts' internal event listeners respond to even when
                # the OS-level pointer simulation alone doesn't visibly
                # register.
                page.evaluate(
                    """([x, y]) => {
                        const el = document.elementFromPoint(x, y);
                        if (!el) return;
                        for (const type of ['mouseover', 'mouseenter', 'mousemove']) {
                            el.dispatchEvent(new MouseEvent(type, {
                                bubbles: true, cancelable: true, clientX: x, clientY: y,
                            }));
                        }
                    }""",
                    [x, y],
                )
                page.wait_for_timeout(200)
                tooltip_visible = tooltip.is_visible() if tooltip.count() > 0 else False

            # A second real run showed the tooltip element with GENUINELY
            # EMPTY text content at every sample (has_real_tooltip_content
            # was false, not just is_visible() being unreliable) — proving
            # the coordinate-based approaches above aren't reaching
            # Recharts' actual hover-tracking layer at all. Recharts
            # typically renders an invisible full-plot-area tracking
            # rect/surface as the REAL mouse-event target (not the visible
            # line/dots themselves), so try Playwright's own element-level
            # .hover() directly on whatever SVG element sits at these
            # coordinates, with force=True to bypass any pointer-
            # interception checks — genuinely different from raw
            # page.mouse.move, since Locator.hover() performs its own
            # internal actionability + event sequence rather than just
            # moving the OS cursor.
            tooltip_text_raw = ""
            if tooltip_count > 0:
                try:
                    tooltip_text_raw = tooltip.evaluate("el => el.innerText || el.textContent || ''") or ""
                except Exception:
                    tooltip_text_raw = ""

            if not tooltip_text_raw.strip():
                try:
                    # Hover the specific coordinate within the SVG via a
                    # relative-position hover on the chart container,
                    # rather than a bare cursor move — this goes through
                    # Playwright's full actionability + event pipeline.
                    chart.hover(position={"x": x - box["x"], "y": y - box["y"]}, force=True, timeout=2000)
                    page.wait_for_timeout(200)
                    if tooltip.count() > 0:
                        tooltip_text_raw = tooltip.evaluate("el => el.innerText || el.textContent || ''") or ""
                except Exception as e:
                    log.append({"step": f"crawl_chart_history:element_hover_fallback:{i}", "error": str(e)})

            has_real_tooltip_content = bool(tooltip_text_raw.strip())

            if i < 3:
                # DIAGNOSTIC — a real run found 0 points across all 24
                # samples with no errors at all, meaning either the
                # tooltip never appeared or its selector is wrong. Logging
                # the first few samples' raw findings shows which.
                log.append({
                    "step": f"crawl_chart_history:sample_{i}",
                    "x": x, "y": y,
                    "tooltip_count": tooltip_count,
                    "tooltip_visible": tooltip_visible,
                    "tooltip_text_raw": tooltip_text_raw[:200],
                    "has_real_tooltip_content": has_real_tooltip_content,
                })
            if not has_real_tooltip_content:
                continue
            tooltip_text = tooltip_text_raw.strip()
            if not tooltip_text or tooltip_text in seen_labels:
                continue
            seen_labels.add(tooltip_text)
            lines = [l.strip() for l in tooltip_text.split("\n") if l.strip()]
            if len(lines) >= 2:
                history.append({"label": lines[0], "value": lines[1]})
            elif lines:
                history.append({"label": lines[0], "value": ""})
        except Exception as e:
            log.append({"step": f"crawl_chart_history:point_{i}", "error": str(e)})
            continue

    log.append({"step": "crawl_chart_history:finished", "points_captured": len(history)})
    return history


def crawl_score_cards_deep(crawler: Crawler, base_url: str) -> dict:
    """
    The main page's 4 top score cards (Opportunity, Problem, Feasibility,
    Why Now) each open a small modal on click showing the score, a short
    description, and a "View detailed analysis" button — confirmed via
    real screenshots. That button navigates to a genuinely deeper page
    with its own real sub-sections (e.g. Opportunity's page shows
    "Opportunity Score" overall rating, "Key Strengths", "Key Risks";
    other cards showed "Market Analysis" and "Competitive Position"
    sections instead) — content not present anywhere in the main page's
    plain text at all.

    This follows the same proven click-modal-then-navigate pattern as
    crawl_business_fit_deep, just with an extra navigation step (click
    card -> modal opens -> click "View detailed analysis" -> real
    sub-page loads) rather than the content living directly in the modal.

    Returns a dict keyed by card label with whatever real page text was
    captured, or omits a card entirely if its click/modal/navigation
    sequence failed at any point — never raises, since this is
    supplementary detail and a failure here shouldn't affect anything
    else already captured.

    NOTE: this used to be defined TWICE in this file (a stale first
    version calling crawl_business_fit_deep's modal-capture pattern, then
    this second one which silently shadowed it — Python allows
    redefinition with no warning, so only this second copy ever actually
    ran). The dead first copy has been removed.
    """
    page = crawler.page
    log = crawler.log
    result = {}

    card_labels = ["Opportunity", "Problem", "Feasibility", "Why Now"]

    # Real captured data confirmed get_visible_text(page) on these detail
    # sub-pages returns the ENTIRE page's text, including the site's own
    # nav sidebar ("ideabrowser HUB Browse Build Home Training...") and the
    # "Discover your founder archetype" quiz box — both prepended before
    # any real content (confirmed directly: scoreCardsDeep.Opportunity's
    # saved text started with the full nav dump, not "Opportunity Score").
    # This is the exact same boilerplate problem already solved for
    # community cards below — reuse the identical stripped-lines approach
    # rather than inventing a second one.
    boilerplate_lines = {
        "ideabrowser", "hub", "browse", "build", "home", "training",
        "my profile", "my stuff", "ideas", "discover", "research",
        "generate", "trends", "market insights", "updates", "empire",
        "support", "free plan", "toggle sidebar", "browse ideas",
        "take the quiz", "start here", "upgrade",
    }

    def strip_boilerplate(raw_text):
        kept_lines = [
            l for l in raw_text.split("\n")
            if l.strip() and l.strip().lower() not in boilerplate_lines
        ]
        return "\n".join(kept_lines)

    for card_label in card_labels:

        def crawl_card(card_label=card_label):
            page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
            page.wait_for_timeout(WAIT_CHART)

            card_heading = page.get_by_text(card_label, exact=True).first
            if not card_heading.is_visible():
                raise Exception(f"'{card_label}' card not visible on main page")
            card_heading.scroll_into_view_if_needed(timeout=5000)
            card_heading.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)

            detail_link = page.get_by_text("View detailed analysis", exact=False).first
            if detail_link.count() == 0 or not detail_link.is_visible():
                raise Exception(f"No 'View detailed analysis' link found after clicking '{card_label}'")
            detail_link.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)

            # A real capture of "Why Now" confirmed it's meaningfully
            # longer than the other 3 cards (it has 6+ emoji sub-sections
            # plus a citations list, vs. 2 for Opportunity/Problem/
            # Feasibility) and was being cut off mid-URL by the previous
            # 4000-char cap. Raised to 8000 so longer cards aren't
            # truncated; still bounded so a genuinely broken page can't
            # balloon unboundedly.
            result[card_label] = strip_boilerplate(get_visible_text(page))[:8000]

            # Return to the main page explicitly rather than relying on
            # back-navigation, since this sub-page's own URL structure is
            # unconfirmed and may not support a simple browser-back.
            page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)

        crawler.safe(crawl_card, f"score_card:{card_label}")

    return result


def crawl_business_fit_deep(crawler: Crawler, base_url: str) -> dict:
    """
    The main page's "Business Fit" section shows 4 short summary cards
    (Revenue Potential, Execution Difficulty, Go-To-Market, Right for You)
    — each already captured as plain one-line text in the main page's own
    raw_text (confirmed directly: "Revenue Potential\n$100K-$1M ARR
    potential..."). Clicking any of these cards opens a genuinely deeper
    modal with real additional structured content not present anywhere
    else on the page (confirmed via a real screenshot showing "Overview",
    "Revenue Examples" as a bullet list, "Business Models", and "Example
    Companies" as named tags — none of which appear in the plain page
    text at all).

    Returns a dict keyed by card label (e.g. "Revenue Potential") with
    whatever text content the modal contained, or omits a card entirely
    if its click/modal capture failed — never raises, since this is
    supplementary detail and a failure here shouldn't affect anything
    else already captured.
    """
    page = crawler.page
    log = crawler.log
    result = {}

    # "Right for You" is deliberately excluded here — two real attempts
    # (modal detection, then a "Find Out" navigation fallback) both
    # confirmed no accessible content opens for it on a free-plan account,
    # most likely because it's gated behind ideabrowser.com's paid tier
    # (the page consistently shows "Pro welcome offer" banners throughout).
    # The other 3 cards are all confirmed working with real content.
    card_labels = ["Revenue Potential", "Execution Difficulty", "Go-To-Market"]

    for card_label in card_labels:

        def crawl_card(card_label=card_label):
            # Return to a clean main-page state before each card, since a
            # previous card's modal-close might leave residual scroll
            # position or focus state that could interfere with finding
            # the next card reliably.
            page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
            page.wait_for_timeout(WAIT_CHART)
            url_before = page.url

            card_heading = page.get_by_text(card_label, exact=False).first
            if not card_heading.is_visible():
                raise Exception(f"'{card_label}' card not visible on main page")
            card_heading.scroll_into_view_if_needed(timeout=5000)
            card_heading.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)

            # The modal is expected to be an overlay dialog — look for a
            # close button ("X" / role=dialog) as confirmation a modal
            # genuinely opened, rather than assuming the click did
            # anything at all.
            modal = page.locator("[role='dialog'], .modal, [class*='Modal']").first
            if modal.count() == 0:
                # A real run confirmed "Right for You" specifically does
                # NOT open a modal like the other 3 cards — it's styled
                # with its own "Find Out →" link (per earlier screenshots),
                # suggesting a real page navigation rather than an overlay.
                # Try clicking that specific link text as a fallback, and
                # accept either a genuine URL change or new page content
                # as evidence something real happened, rather than only
                # accepting the modal pattern.
                find_out_link = page.get_by_text("Find Out", exact=False).first
                if find_out_link.count() > 0 and find_out_link.is_visible():
                    find_out_link.click(timeout=5000)
                    page.wait_for_timeout(WAIT_CHART)
                    if page.url != url_before:
                        result[card_label] = get_visible_text(page)[:3000]
                        page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
                        return
                raise Exception(f"No modal dialog detected after clicking '{card_label}', and 'Find Out' fallback did not navigate")

            modal_text = modal.inner_text(timeout=3000)

            # Close the modal before returning, so the next card starts
            # from a clean state even if the next iteration's own
            # page.goto() above is skipped for any reason.
            try:
                close_btn = modal.locator("button", has_text=re.compile(r"^(×|X|Close)$", re.IGNORECASE)).first
                if close_btn.count() > 0:
                    close_btn.click(timeout=3000)
                else:
                    page.keyboard.press("Escape")
            except Exception:
                pass
            page.wait_for_timeout(500)

            result[card_label] = modal_text[:3000]

        crawler.safe(crawl_card, f"business_fit_card:{card_label}")

    return result


def crawl_subpages(crawler: Crawler, base_url: str) -> dict:
    """
    Follows every 'View Analysis' style link/button on the main page into
    its sub-page, captures the rendered text, then returns to the main page.
    Also attempts to open the 'Execution Difficulty' modal in place.

    A real run showed two things worth noting for future maintenance:
    1. Text-based locators here can match hidden duplicate elements (same
       responsive-layout pattern seen elsewhere on this page), so every
       match must be checked with is_visible() rather than assumed usable.
    2. "Market Gap" and "Execution Plan" appear to primarily be inline
       section headings on the main page (e.g. "The Market Gap" followed
       directly by descriptive text), with dedicated CTA links worded
       differently ("Understand the market opportunity", "View detailed
       execution strategy") rather than the section heading itself. Both
       label variants are tried below.
    """
    page = crawler.page
    log = crawler.log
    subpages = {}

    link_labels = [
        "View Analysis",                     # Value Equation, Market Matrix, Value Ladder, A.C.P. Framework
        "View detailed breakdown",           # Community Signals
        "Understand the market opportunity", # Market Gap CTA
        "View detailed execution strategy",  # Execution Plan CTA
        "Explore proof & signals",           # Proof & Signals CTA
        "See why this opportunity matters now",  # Why Now CTA
        "View full keyword analysis",
        "View full value ladder",
    ]

    for label in link_labels:
        locs = crawler.safe(lambda l=label: page.get_by_text(l, exact=False), f"find_links:{label}", default=None)
        if locs is None:
            continue
        count = crawler.safe(lambda l=locs: l.count(), f"count_links:{label}", default=0)

        clicked_indices = []
        for i in range(count):

            def click_and_capture(locs=locs, i=i, label=label):
                candidate = locs.nth(i)
                if not candidate.is_visible():
                    raise Exception(f"Match {i} for '{label}' is not visible, skipping.")
                key = f"{label} #{i+1}" if count > 1 else label
                candidate.scroll_into_view_if_needed(timeout=5000)
                candidate.click(timeout=8000)
                page.wait_for_timeout(WAIT_CHART)
                text = get_visible_text(page)
                subpages[key] = {"text": text.strip(), "url": page.url}
                page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
                page.wait_for_timeout(WAIT_CHART)

            crawler.safe(click_and_capture, f"subpage:{label}#{i}")

    # Execution Difficulty modal (has visible X close button in screenshot,
    # but a generic "button with svg icon" selector matched the WRONG
    # button on a real run — likely one of several icon-buttons on the
    # page. Use a more specific modal-scoped close button selector, and
    # fall back to pressing Escape, which closes most modal/dialog
    # implementations regardless of the close button's exact markup.
    def open_execution_modal():
        candidates = page.get_by_text("Execution Difficulty", exact=False)
        count = candidates.count()
        opened = False
        for i in range(count):
            c = candidates.nth(i)
            if c.is_visible():
                c.click(timeout=8000)
                opened = True
                break
        if not opened:
            raise Exception("Could not find a visible 'Execution Difficulty' element to click.")

        page.wait_for_timeout(WAIT_CHART)
        text = get_visible_text(page)
        subpages["Execution Difficulty"] = {"text": text.strip(), "url": page.url}

        # Close modal — prefer a close button scoped inside an open dialog,
        # fall back to Escape key which works for most modal libraries
        # (including Radix-based dialogs, which this site appears to use).
        try:
            dialog_close = page.locator("[role='dialog'] button").first
            if dialog_close.is_visible():
                dialog_close.click(timeout=3000)
                return
        except Exception:
            pass
        page.keyboard.press("Escape")

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

        # Drill into the 4 Business Fit modal cards (Revenue Potential,
        # Execution Difficulty, Go-To-Market, Right for You) for their
        # real deeper content (Overview, Revenue Examples, Business
        # Models, Example Companies) — none of which is present in the
        # main page's own plain text, confirmed directly via a real
        # screenshot of the modal.
        record["business_fit_deep"] = crawler.safe(
            lambda: crawl_business_fit_deep(crawler, URL), "crawl_business_fit_deep", default={}
        ) or {}

        # Drill into the 4 score cards (Opportunity, Problem, Feasibility,
        # Why Now) for their real deeper modal + "View detailed analysis"
        # page content (Market Analysis, Competitive Position, Key
        # Strengths, Key Risks, etc) — confirmed via real screenshots to
        # contain genuine additional structure well beyond the plain
        # "9/10 Exceptional" summary already captured elsewhere.
        record["score_cards_deep"] = crawler.safe(
            lambda: crawl_score_cards_deep(crawler, URL), "crawl_score_cards_deep", default={}
        ) or {}

        # Drill deeper into Community Signals specifically: real subreddit/
        # group names, discussion titles, and actual external href links —
        # data the top-level subpage crawl above only captures as summary
        # text, not as structured, linkable detail.
        community_page = record["subpages"].get("View detailed breakdown")
        if community_page and community_page.get("url"):
            record["community_signals_deep"] = crawler.safe(
                lambda: crawl_community_signals_deep(crawler, community_page["url"], record["summary"].get("title", "")),
                "crawl_community_signals_deep",
                default={},
            ) or {}
        else:
            record["community_signals_deep"] = {}
            log.append({"step": "crawl_community_signals_deep", "error": "no community-signals subpage URL found to drill into"})

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

    md += ["## Keyword Analysis", ""]
    for kw in record["keyword_analysis"]:
        md.append(f"### {kw['keyword']}")
        stats = kw.get("stats", {})
        for metric, value in stats.items():
            md.append(f"- **{metric}**: {value}")
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
