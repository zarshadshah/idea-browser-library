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

SITE REDESIGN — confirmed directly on 2026-08-27: ideabrowser.com's Idea
of the Day layout changed substantially. The old layout had a "Keyword:"
dropdown, emoji-led "Business Fit" cards, and a "Categorization" block;
the new layout uses section headers like "THE IDEA", "AT A GLANCE", "THE
CUSTOMER", "WHY NOW", "THE VERDICT", "FOUNDER FIT", "THE PLAN", "NAPKIN
MATH" instead, and appears to have DROPPED the keyword-volume dropdown
and chart entirely. Sites like this can and do change layout without
notice, so this file now has two layers of defense against that instead
of just hardcoded selectors that quietly break:
  1. extract_new_layout_fields(): parses the new layout's real section
     headers into structured fields, the same way extract_summary_fields()
     did for the old layout. Both are tried; whichever actually matches
     the live page wins.
  2. Regardless of which (if either) parser matches, the FULL raw page
     text is always saved verbatim in summary.raw_text — so even a THIRD
     future redesign that neither parser recognizes still never loses a
     day's idea outright, it just falls back to being unparsed text
     instead of structured fields.

NEW-LAYOUT SKIP GUARDS — confirmed directly via a real 2026-08-28 crawl
log: on a new-layout day, crawl_keyword_analysis(), crawl_score_cards_deep(),
crawl_business_fit_deep(), and crawl_community_signals_deep() ALL fail
every single selector they try (the old layout's "Keyword:" label, its 4
score cards, its Business Fit cards, and its "View detailed breakdown"
community-signals link genuinely do not exist in the new layout), burning
real time on retries — one one selector timeout in that log runs to
several thousand words of Playwright retry log for a single click — for
zero data. crawler.safe() already stopped this from crashing the run, but
it was still real wasted time on every new-layout day. Each of these four
functions now takes a layout_detected flag and returns early when it's
"new", exactly as if the crawl_log said so (a "skipped: new layout"
log entry is written either way, so this is visible in the log rather
than a silent no-op).

HREF CAPTURE — a real 2026-08-28 crawl confirmed every inline citation on
the new layout (e.g. "r/shopify · r/shopify OP (rant thread)", "SHOPIFY
NEWS", "YOUTUBE", "GIGRADAR") was being captured as plain text with zero
href, identical to the old layout's numbered Citations & Sources problem.
get_page_text_and_links() now captures both the page's visible text AND
every real <a href> on the page in one pass, so normalize_and_build_
manifest.py has real URLs to match citation labels against instead of
inventing links from bare strings (which is impossible) or leaving every
source as unclickable text (which is what shipped before this).

SETUP TUTORIAL VIEWS POPUP — confirmed directly via real screenshots
(2026-08-28): the "AT A GLANCE" stat teasers on the new layout (Setup
Tutorial Views / Pain / Timing / Year One) are each a short label already
present in the base page's own text — NOT a separate crawl target
requiring its own click-through, since pain_score/timing_score are
already extracted correctly by extract_new_layout_fields. Clicking one
opens an expanded popup with real additional depth (a linked source,
inline-cited prose, and — confirmed directly by hovering, real user
testing: selecting a different keyword swaps the Volume/Growth/CPC/chart
shown) its own scoped keyword dropdown, structurally the same shape as
crawl_keyword_analysis() but scoped to this popup's own trigger and
dropdown rather than the main page's (now-removed-on-new-layout) one.
crawl_glance_popup() opens each of the 4 popups by their exact visible
label text and captures this expanded content; for "Setup Tutorial
Views" specifically, it also runs the same per-keyword stat-capture loop
crawl_keyword_analysis() already uses elsewhere, scoped to this popup's
own dropdown trigger instead of the page-level one.

IMPORTANT — this script needs live debugging against the real site.
It was written from screenshots of the page, not by running against the
live DOM (the authoring environment cannot reach ideabrowser.com), so
CSS selectors below are best-effort guesses based on visible structure
and will likely need small fixes after the first real run. Every
selector attempt is wrapped in try/except and logged, and raw HTML +
screenshots are saved at every step so nothing is silently lost — if a
selector is wrong you'll be able to see exactly what the DOM looked like
and patch the selector. This applies doubly to crawl_glance_popup(),
which is entirely new and unverified against a live run.

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

# Confirmed live 2026-08-28 via real screenshots: the 4 "AT A GLANCE" stat
# teasers, each opening its own popup on click. Exact visible label text —
# used as the click target, so this must match the page's own rendering
# verbatim (confirmed against real screenshots for all 4).
GLANCE_POPUP_LABELS = ["Setup Tutorial Views", "Pain", "Timing", "Year 1, Done Right"]


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

    The login page's own layout has changed at least twice independent
    of the Idea-of-the-Day redesign — confirmed directly via real
    DevTools screenshots at two different points: an earlier capture
    showed a magic-link-first view requiring a "Sign in with Password"
    toggle click before email/password fields appeared, while a real
    2026-08-29 screenshot showed both fields, plus the "Sign in with
    Password" button, visible immediately on page load with no toggle
    needed at all. Rather than assume either shape, this function
    checks for the toggle text and only clicks it if actually present
    (see the match_count check below), then searches for both fields
    directly regardless — this handles both the toggle-required and
    fields-already-visible cases without needing to know in advance
    which one is currently live.

    Returns True if login appears to have succeeded (no longer on the
    login page / no login form visible), False otherwise. Selectors here
    are a best effort based on real captured page structure, refined
    across multiple real runs — but the login page has proven to change
    shape on its own timeline, so this may still need adjustment after
    future runs. Every step is logged.
    """
    email = os.environ.get("IDEABROWSER_EMAIL")
    password = os.environ.get("IDEABROWSER_PASSWORD")

    if not email or not password:
        log.append({"step": "login", "error": "IDEABROWSER_EMAIL or IDEABROWSER_PASSWORD not set"})
        return False

    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(3000)

        # Switch from default magic-link view to password mode. A real
        # 2026-08-28 run confirmed this page no longer ALWAYS shows a
        # "Sign in with Password" toggle (0 matches found, vs 2 on an
        # earlier run) — the login form itself has apparently also
        # changed shape at some point, independent of the Idea-of-the-Day
        # redesign. This still worked end-to-end that run (email/password
        # fields were found and filled directly, login succeeded), so
        # rather than treat 0 matches as an error, only attempt the
        # toggle click when the text is actually present — the password
        # fields are searched for either way, further down.
        text_matches = page.get_by_text("Sign in with Password", exact=False)
        match_count = text_matches.count()
        log.append({"step": "login", "note": f"Found {match_count} element(s) matching 'Sign in with Password' text."})

        clicked = False
        if match_count > 0:
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

        if match_count > 0 and not clicked:
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

        # Fill password field. A real 2026-08-29 run confirmed via direct
        # DevTools inspection that the password input DOES have
        # type="password" (placeholder="Enter your password",
        # autocomplete="current-password") — exactly what the selector
        # list below already searches for — yet the fill still failed
        # with "Could not find password input field" on that run. Since
        # the element genuinely exists with the expected attribute, the
        # most likely cause is the same class of timing/visibility race
        # already confirmed once before on this site (the leftover-
        # dropdown-overlay issue in the keyword crawler): is_visible()
        # can return false for an element that's present but not yet
        # settled (mid-animation, mid-hydration) at the exact instant
        # this check runs, especially right after the page's own
        # 1500ms post-toggle wait — which that same 2026-08-29 run never
        # even executed, since match_count was 0 and skipped straight to
        # filling fields with no settle time at all for the page's own
        # client-side render. Retry the password fill specifically
        # (cheap — a few hundred ms each, capped attempts) rather than
        # failing immediately on the first miss, and add the confirmed
        # real placeholder text as another selector alongside the two
        # already-correct ones, in case a future capture shows a page
        # variant that drops the name/type attributes but keeps the
        # placeholder.
        password_selectors = [
            'input[type="password"]', 'input[name="password"]',
            'input[placeholder*="password" i]',
        ]
        password_filled = fill_first_visible(password_selectors, password, "password")
        if not password_filled:
            for attempt in range(4):  # up to ~2s total extra settle time
                page.wait_for_timeout(500)
                password_filled = fill_first_visible(password_selectors, password, "password")
                if password_filled:
                    log.append({"step": "login", "note": f"Password field filled on retry attempt {attempt + 1}"})
                    break
        if not password_filled:
            try:
                screenshot_path = str(ROOT / "library" / "login_debug_screenshot.png")
                page.screenshot(path=screenshot_path, full_page=True)
                log.append({"step": "login", "note": f"Saved debug screenshot to {screenshot_path}"})
            except Exception as e:
                log.append({"step": "login", "note": f"Could not save debug screenshot: {e}"})
            log.append({"step": "login", "error": "Could not find password input field after retries"})
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

    A site redesign on 2026-08-27 was confirmed to have DROPPED the
    "Keyword:" label this function used as its "is this real content"
    marker entirely (the new layout has no keyword-volume dropdown at
    all) — the crawler misread a genuinely successful, unblocked page load
    as still being stuck behind the checkpoint, and stopped the entire
    crawl immediately even though login had succeeded and real content was
    on screen the whole time. A single fixed marker string is fragile
    against exactly this kind of redesign, so this now accepts ANY of
    several markers that have been directly confirmed present across both
    the old and new real layouts, rather than requiring one specific
    string that a future redesign could just as easily drop again.
    """
    checkpoint_markers = [
        "Security Checkpoint", "Verifying your browser", "verify you are human",
        "Failed to verify your browser", "Website owner? Click here to fix",
        "Checking your browser", "Just a moment", "Please wait while we verify",
        "Access denied", "blocked", "captcha", "Enable JavaScript and cookies",
    ]
    # Each of these has been directly confirmed present on a real,
    # successfully-loaded page: "Keyword:" on the old layout, "Idea of the
    # Day" / "Browse all" / "THE IDEA" on both old and new real captures.
    # Requiring only ONE of these (not all) means the marker set can keep
    # growing as the site changes without ever needing every single one to
    # simultaneously match.
    real_content_markers = ["Keyword:", "Idea of the Day", "Browse all", "THE IDEA"]

    waited = 0
    interval = 1000
    while waited < max_wait_ms:
        try:
            text = page.inner_text("body")
        except Exception:
            text = ""

        has_checkpoint_text = any(m.lower() in text.lower() for m in checkpoint_markers)
        has_real_content = any(m.lower() in text.lower() for m in real_content_markers)

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


def get_page_text_and_links(page, max_links=200):
    """
    Captures BOTH the page's visible text (as get_visible_text always has)
    AND every real <a href> on the page in one pass — confirmed necessary
    directly via a real 2026-08-28 crawl, which showed every inline
    citation on the new layout (e.g. "r/shopify · r/shopify OP (rant
    thread)", "SHOPIFY NEWS", "YOUTUBE", "GIGRADAR") captured as plain
    text with zero href, the same underlying gap the old layout's
    numbered Citations & Sources list already had. No amount of text
    parsing can recover a link that was never captured — the href has to
    be read from the live DOM at crawl time via get_attribute("href"),
    which plain inner_text() never exposes.

    Returns (text, links) where links is a list of {"text": ..., "href":
    ...} dicts, one per <a> tag with a non-empty href, in document order,
    deduplicated by (text, href) pair. Internal ideabrowser.com nav links
    (sidebar, "Browse all", etc) are excluded via the same boilerplate-nav
    href patterns already known from real captures, so the list stays
    focused on genuine outbound citation links a reader would want to
    click, not the page's own navigation chrome. Capped at max_links as a
    safety net against a page with an unexpectedly large number of links.
    """
    text = page.inner_text("body")

    links = []
    seen = set()
    try:
        anchors = page.locator("a[href]")
        count = anchors.count()
        for i in range(min(count, max_links * 2)):  # scan more than max_links since some get filtered
            try:
                el = anchors.nth(i)
                href = el.get_attribute("href")
                if not href:
                    continue
                # Exclude internal nav — same-site relative paths and
                # ideabrowser.com's own domain, confirmed via real captures
                # to always be sidebar/nav/breadcrumb chrome, never a real
                # citation source.
                if href.startswith("/") or "ideabrowser.com" in href:
                    continue
                if not (href.startswith("http://") or href.startswith("https://")):
                    continue
                link_text = (el.inner_text(timeout=1000) or "").strip()
                key = (link_text, href)
                if key in seen:
                    continue
                seen.add(key)
                links.append({"text": link_text[:200], "href": href})
                if len(links) >= max_links:
                    break
            except Exception:
                continue
    except Exception:
        pass

    return text, links


def extract_new_layout_fields(text: str) -> dict:
    """
    Parses the NEW layout confirmed live on 2026-08-27, which uses
    distinct ALL-CAPS section header lines (THE IDEA, AT A GLANCE, THE
    CUSTOMER, WHY NOW, THE VERDICT, FOUNDER FIT, THE PLAN, NAPKIN MATH,
    etc) rather than the old layout's "Keyword:" dropdown and emoji cards.
    These header strings are used as split points directly, since they've
    been directly confirmed present verbatim in a real capture — far more
    stable anchors than CSS classes or DOM structure, which is exactly
    what changed in this redesign.

    Returns {} (not a dict with mostly-null fields) if NONE of the known
    new-layout headers are found at all, so the caller can tell "this
    parser doesn't apply to what's on the page right now" apart from
    "this parser applies but a couple of optional fields were missing" —
    the first case should fall through to raw-text-only rather than
    reporting a mostly-empty structured result as if it were complete.
    """
    out = {}
    known_sections = [
        "THE IDEA", "AT A GLANCE", "THE CUSTOMER", "WHY NOW",
        "PROOF & SIGNALS", "MARKET SNAPSHOT", "WHITESPACE",
        "WHO YOU'RE UP AGAINST", "PEOPLE ARE ASKING FOR IT", "THE VERDICT",
        "FOUNDER FIT", "WHAT YOU'D SELL", "THE PLAN", "NAPKIN MATH",
        "THE PLAYBOOKS",
    ]
    present_sections = [s for s in known_sections if s in text]
    if not present_sections:
        return {}

    # Title: on a real capture this is the line right after the LAST
    # "Browse all" occurrence and before the numeric score that follows it
    # (e.g. "...Browse all\nLaunch products with street marketing\n7.3\n
    # /10"), mirroring the same anchor strategy extract_summary_fields
    # already uses successfully for the old layout.
    if "Browse all" in text:
        after_nav = text.rsplit("Browse all", 1)[1]
        candidate_lines = [l.strip() for l in after_nav.split("\n") if l.strip()]
        for l in candidate_lines:
            if len(l) > 8 and not re.match(r"^[\d./]+$", l):
                out["title"] = l
                break

    # Overall score: confirmed to appear directly after the title as a
    # bare "7.3\n/10" pair, distinct from the old layout's separate
    # Opportunity/Problem/Feasibility/Why Now four-way breakdown — this
    # new layout appears to have collapsed those into one overall score
    # shown at the top, with the individual PAIN/TIMING scores appearing
    # later as their own separate labeled sections instead.
    m = re.search(r"\n([\d.]+)\s*\n\s*/\s*10\b", text)
    if m:
        try:
            out["overall_score"] = float(m.group(1))
        except ValueError:
            pass

    # A real screenshot showed multiple DISTINCT UI widgets (an AI-agent
    # promo box, a workshop/event invite box, AND a separate feedback
    # widget with its own "Not for me" / "Share a win" / "Problem"
    # quick-reply buttons) genuinely interleaved THROUGHOUT a section's
    # captured text, not neatly bunched at the very end the way a single
    # stop-marker assumes. A stop-marker approach can only ever cut off
    # content after the FIRST piece of noise it finds — any real content
    # that happens to sit further down, past that first noise fragment,
    # gets silently lost too. Filtering line-by-line for known noise
    # patterns, regardless of where each one sits, is more robust: it
    # removes exactly the noise and nothing else, wherever it appears.
    noise_line_patterns = [
        r"^Build with", r"^Jam on it with your agent",
        r"^Workshop (today|tomorrow)",
        r"^What'd you think of this idea", r"^Chef's kiss$",
        r"^Pretty interesting$", r"^You didn't bring the heat$",
        r"^Not for me:", r"^Share a win:", r"^Problem:",
        r"^Send feedback$", r"^Hide this widget", r"^Feature request$",
        r"^You're invited$", r"^Register", r"^RSVP",
        r"^Yes, I'?d (want|attend)", r"^No, I'?m",
        r"^WHAT IF THIS WERE FEEDBACK\??$", r"^Feedback$",
    ]
    noise_line_regex = re.compile("|".join(noise_line_patterns))

    def strip_noise_lines(section_text):
        line_filtered = "\n".join(
            l for l in section_text.split("\n") if not noise_line_regex.match(l.strip())
        )
        # A real screenshot confirmed line-level filtering alone wasn't
        # enough: two distinct promo-box widgets (an AI-agent plugin box
        # listing "Claude / Grok / Gemini / Groq / OpenClaw", and a
        # workshop/event invite box with "YOU'RE INVITED" / "Reserve @
        # ..." / a date+seat-count line / "Would you attend?") each have
        # their OWN substantial internal text that doesn't match any
        # simple per-line noise pattern — they need removing as whole
        # blocks, from their own real start marker to their own real end
        # marker, rather than line by line.
        block_bounds = [
            ("Copy: '", "OpenClaw"),  # the AI-agent plugin box's own real start/end text
            ("YOU'RE INVITED", "Would you attend?"),  # the workshop/event invite box
        ]
        for start, end in block_bounds:
            start_idx = line_filtered.find(start)
            if start_idx == -1:
                continue
            end_idx = line_filtered.find(end, start_idx)
            if end_idx == -1:
                continue
            end_idx += len(end)
            line_filtered = line_filtered[:start_idx] + line_filtered[end_idx:]
        return line_filtered

    def section_text(start_marker, end_markers):
        if start_marker not in text:
            return None
        seg = text.split(start_marker, 1)[1]
        end_idx = len(seg)
        for end_marker in end_markers:
            idx = seg.find(end_marker)
            if idx != -1 and idx < end_idx:
                end_idx = idx
        # A real capture showed "WHY NOW" actually renders on the page as
        # "WHY NOW?" — the marker itself matches fine (it's a substring),
        # but the leftover "?" then leads the captured section text. Strip
        # a stray leading "?" (and any whitespace around it) rather than
        # add a second near-duplicate marker string to maintain.
        raw = seg[:end_idx].strip().lstrip("?").strip()[:3000]
        return strip_noise_lines(raw)

    section_order = present_sections + ["SOURCES"]  # SOURCES as a safe trailing bound for the last real section
    for i, section in enumerate(present_sections):
        remaining_markers = section_order[i + 1:]
        key = re.sub(r"[^a-z0-9]+", "_", section.lower()).strip("_")
        val = section_text(section, remaining_markers)
        if val:
            out[f"section_{key}"] = val

    # PAIN / TIMING scores: confirmed present as "PAIN\n8\n/10 severity"
    # and "TIMING\n8\n/10" patterns distinct from the old layout's
    # Opportunity/Problem/Feasibility/Why Now block.
    for label, key in [("PAIN", "pain_score"), ("TIMING", "timing_score")]:
        m = re.search(rf"{label}\s*\n\s*(\d+)\s*\n\s*/\s*10", text)
        if m:
            try:
                out[key] = int(m.group(1))
            except ValueError:
                pass

    return out


def extract_summary_fields(text: str) -> dict:
    """Heuristic parse of the main page's plain text into structured fields.

    Tries BOTH the old layout's parser (this function's own body, below)
    and the new layout's parser (extract_new_layout_fields) and merges
    whichever fields each one actually found — rather than assuming only
    one layout can ever be live at a time. If a future redesign changes
    things AGAIN and neither parser recognizes it, "raw_text" (the full,
    verbatim page text, always saved regardless) is what the app and any
    future maintenance work falls back to — nothing is ever silently lost
    to a parser mismatch, only to genuine capture failures (login/
    checkpoint), which are handled and logged separately.
    """
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

    # Merge in whatever the new-layout parser independently found. Real
    # fields from either parser win; out's own fields (set above) are
    # never overwritten by an empty/None value from the other parser.
    new_layout_fields = extract_new_layout_fields(text)
    for k, v in new_layout_fields.items():
        if v is not None and (k not in out or out[k] is None):
            out[k] = v
    out["layout_detected"] = "new" if new_layout_fields else "old"

    return out


def crawl_keyword_analysis(crawler: Crawler, layout_detected: str = "old") -> list:
    """
    Opens the Keyword Analysis dropdown, enumerates every keyword option,
    and for each keyword cycles through every time range, recording the
    Volume/Growth/CPC/Competition numbers shown.

    NEW-LAYOUT SKIP GUARD — a real 2026-08-28 crawl log confirmed the
    "Keyword:" trigger this function depends on genuinely does not exist
    on the new layout (open_keyword_dropdown_for_listing timed out after
    8s, keyword_discovery found 0 options, and every keyword-selection
    step downstream failed the same way) — the page-level keyword
    dropdown this function targets was removed in the redesign, not
    merely relocated. Every one of those failures was already caught
    safely by crawler.safe() so the run itself didn't crash, but it still
    burned real time on guaranteed-to-fail retries for zero data. Skip
    entirely on a new-layout day rather than repeat that — the new
    layout's own keyword data instead lives inside the Setup Tutorial
    Views popup, captured separately by crawl_glance_popup() below, which
    is genuinely new UI, not this same dropdown moved elsewhere.
    """
    if layout_detected == "new":
        crawler.log.append({"step": "crawl_keyword_analysis", "note": "skipped: new layout has no page-level 'Keyword:' dropdown (confirmed via real 2026-08-28 crawl log) — see crawl_glance_popup for this layout's keyword data"})
        return []

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


def crawl_glance_popup(crawler: Crawler, base_url: str, label: str) -> dict:
    """
    Opens one of the 4 new-layout "AT A GLANCE" stat-teaser popups (Setup
    Tutorial Views / Pain / Timing / Year 1, Done Right) by its exact
    visible label text, and captures the expanded content shown — real
    additional depth beyond what's already in the base page's own text
    (confirmed directly via real screenshots: e.g. the Setup Tutorial
    Views popup's "Where the Demand Lives" prose with inline-cited
    r/shopify and Shopify Community links, and the Pain popup's numbered
    "In Their Own Words" sourced-quote list, neither of which appear
    anywhere in section_the_customer's own short teaser text).

    UNVERIFIED AGAINST A LIVE RUN — this entire function is new and has
    never been run against the real site (the authoring environment
    cannot reach ideabrowser.com). The trigger-click strategy mirrors
    crawl_business_fit_deep's already-proven approach (click the visible
    label text, look for a dialog/modal), since these popups appear
    structurally similar in the real screenshots reviewed, but the exact
    selectors WILL likely need adjustment after the first real run, same
    as every other selector in this file when it was first written.

    Returns a dict shaped like:
    {
      "text": "<full popup text, links captured separately below>",
      "links": [{"text": "...", "href": "..."}, ...],
      "keywords": [...]  # only present for the "Setup Tutorial Views" popup
    }
    or {} if the popup couldn't be opened/found — fails safely so one
    popup's selector being wrong doesn't lose the other 3 (the caller
    wraps each call in crawler.safe() individually).
    """
    page = crawler.page
    log = crawler.log

    page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
    page.wait_for_timeout(WAIT_CHART)

    # Prefer a visible match since this page renders duplicate (responsive)
    # copies of many elements elsewhere — same pattern already proven
    # necessary for the old layout's dropdown/form fields.
    candidates = page.get_by_text(label, exact=False)
    count = candidates.count()
    trigger = None
    for i in range(count):
        c = candidates.nth(i)
        if c.is_visible():
            trigger = c
            break
    if trigger is None:
        raise Exception(f"'{label}' glance stat not visible on main page")

    trigger.scroll_into_view_if_needed(timeout=5000)
    trigger.click(timeout=8000)
    page.wait_for_timeout(WAIT_CHART)

    # Mirrors crawl_business_fit_deep's already-proven modal-detection
    # approach: look for a real dialog role first, since that's what a
    # popup overlay should use; this is the one part of this function with
    # any prior confirmation behind it, everything else here is a first
    # attempt.
    modal = page.locator("[role='dialog'], .modal, [class*='Modal']").first
    if modal.count() == 0:
        raise Exception(f"No modal dialog detected after clicking '{label}'")

    popup_text, popup_links = get_page_text_and_links(page)
    # Scope the captured text to roughly the modal's own content where
    # possible, since get_page_text_and_links reads the whole page —
    # matches the same "whole page, then trim in the normalizer" approach
    # already used elsewhere in this file (e.g. crawl_business_fit_deep's
    # modal_text), rather than trying to scope the DOM read itself, which
    # is more fragile against small structural differences between the 4
    # popups.
    result = {"text": popup_text.strip(), "links": popup_links}

    # Setup Tutorial Views is the one popup confirmed (via real user
    # testing: selecting a different keyword swaps the Volume/Growth/CPC/
    # chart shown) to contain its OWN scoped keyword dropdown, distinct
    # from the page-level "Keyword:" dropdown crawl_keyword_analysis
    # targets (which doesn't exist at all on this layout — see that
    # function's own new-layout skip guard above). Structurally the same
    # per-keyword stat-capture loop, just scoped to this popup's own
    # dropdown trigger.
    if label == "Setup Tutorial Views":
        result["keywords"] = crawler.safe(
            lambda: crawl_glance_keyword_dropdown(crawler), "crawl_glance_keyword_dropdown", default=[]
        ) or []

    # Close the popup before returning, so the next popup's trigger-click
    # isn't landing on a leftover overlay — same defensive pattern already
    # proven necessary for the old layout's keyword dropdown.
    try:
        close_btn = modal.locator("button", has_text=re.compile(r"^(×|X|Close)$", re.IGNORECASE)).first
        if close_btn.count() > 0:
            close_btn.click(timeout=3000)
        else:
            page.keyboard.press("Escape")
    except Exception:
        page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    return result


def crawl_glance_keyword_dropdown(crawler: Crawler) -> list:
    """
    Per-keyword stat capture for the Setup Tutorial Views popup's own
    scoped keyword dropdown — structurally the same loop as
    crawl_keyword_analysis, just scoped to this popup's own dropdown
    trigger rather than the (nonexistent-on-this-layout) page-level one.

    UNVERIFIED AGAINST A LIVE RUN, same caveat as crawl_glance_popup
    above — the dropdown-open/option-list/read-stats selectors below are
    a best-effort adaptation of crawl_keyword_analysis's already-proven
    approach, not independently confirmed against this specific popup's
    real DOM.
    """
    page = crawler.page
    log = crawler.log
    results = []

    def open_dropdown():
        # Confirmed via real screenshots: the trigger inside this popup
        # shows the currently-selected keyword in quotes (e.g. '"b2b on
        # shopify"') with a chevron, inside the "WHAT SEARCH SHOWS"
        # section — distinct from the old layout's "Keyword: <value>"
        # label text, so matched by role instead (a combobox/select-style
        # trigger is the most likely real element given the visible
        # dropdown-with-checkmark UI in the screenshot).
        candidates = page.get_by_role("combobox")
        count = candidates.count()
        for i in range(count):
            c = candidates.nth(i)
            if c.is_visible():
                c.click(timeout=8000)
                page.wait_for_timeout(WAIT_SHORT)
                return
        raise Exception("No visible combobox trigger found for glance popup's keyword dropdown")

    def get_options():
        options = page.locator("[role='option']").all()
        if options:
            return options
        return page.locator("[role='listbox'] li, [role='listbox'] div").all()

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

    crawler.safe(open_dropdown, "open_glance_keyword_dropdown_for_listing")
    page.wait_for_timeout(WAIT_SHORT)

    raw_options = crawler.safe(get_options, "list_glance_keyword_options", default=[])
    keyword_names = []
    for el in raw_options[:30]:
        try:
            t = el.inner_text().strip()
            if t and 3 <= len(t) <= 80 and "\n" not in t:
                keyword_names.append(t)
        except Exception:
            continue

    log.append({"step": "glance_keyword_discovery", "note": f"Found {len(keyword_names)} plausible keyword option(s) after filtering."})
    page.keyboard.press("Escape")
    page.wait_for_timeout(WAIT_SHORT)

    seen = set()
    for kw in keyword_names:
        kw_clean = kw.strip()
        if not kw_clean or kw_clean in seen or len(kw_clean) < 3:
            continue
        seen.add(kw_clean)

        def select_keyword(k=kw_clean):
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            open_dropdown()
            page.get_by_text(k, exact=True).first.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        crawler.safe(select_keyword, f"select_glance_keyword:{kw_clean}")
        stats = crawler.safe(read_current_stats, f"read_glance_stats:{kw_clean}", default={})
        results.append({"keyword": kw_clean, "stats": stats})
        log.append({"step": "glance_keyword_done", "keyword": kw_clean, "stats_captured": bool(stats)})

    return results


def crawl_community_signals_deep(crawler: Crawler, community_signals_url: str, idea_title: str = "", layout_detected: str = "old") -> dict:
    """
    Drills into the Community Signals page to capture the REAL underlying
    data the summary counts are based on: actual platform sections (Reddit,
    Facebook, YouTube, Other), the individual community/subreddit cards
    inside each (name, member count, why-relevant blurb), and — one level
    deeper — the actual discussion post titles and their real external
    href URLs (e.g. real reddit.com links), captured via get_attribute
    rather than visible text, since link destinations aren't shown as text
    on the page at all.

    NEW-LAYOUT SKIP GUARD — a real 2026-08-28 crawl log confirmed this
    function's caller never even had a URL to pass in: no "View detailed
    breakdown" subpage exists on the new layout at all (the log's own
    community_signals_deep entry reads "no community-signals subpage URL
    found to drill into"). This guard makes that explicit and immediate
    rather than relying on the caller's absent-URL check alone, so the
    reason is visible directly on this function's own log line too. The
    new layout's community-adjacent content (real Reddit/Shopify Community
    quotes) already comes through elsewhere — section_people_are_asking_
    for_it and the "Explore the evidence" subpage's own text — just not
    broken out per-platform the way this function's old-layout output is.

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
    if layout_detected == "new":
        crawler.log.append({"step": "crawl_community_signals_deep", "note": "skipped: new layout has no 'View detailed breakdown' subpage to drill into (confirmed via real 2026-08-28 crawl log) — community-adjacent content instead lives in section_people_are_asking_for_it and the 'Explore the evidence' subpage"})
        return {}

    page = crawler.page
    log = crawler.log
    result = {"reddit": [], "facebook": [], "youtube": [], "other": []}
    # Kept fully separate from `result` (see the "IMPORTANT" comment near
    # where this is populated, in the "other" platform's block below) so
    # downstream code that iterates result's platform -> [community, ...]
    # pairs never encounters this non-list value.
    other_communities_extra = {}

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
            # covering these two Facebook-specific labels). "Content
            # Strategies" / "Partnership Opportunities" / "Citations &
            # Sources" (and their own sub-headings) are the "Other
            # Communities" page's trailing sections, already captured
            # separately via the dedicated otherCommunitiesExtra
            # mechanism below — excluded here too now that card_count can
            # reach far enough into the page to otherwise re-capture them
            # a second time as fake extra "communities".
            exclude_pattern = r"^(ideabrowser|Community Signals|Take the quiz|Discover your founder archetype|Relevant Communities|Relevant Groups|Analysis Overview|Community Types|Community Segments|Key Findings|In-Depth|Why It'?s Relevant|Opportunity|Relevant Discussions?|DESCRIPTION|RELEVANCE SIGNALS|Content Strategies|Partnership Opportunities|Citations\s*&\s*Sources)"
            if idea_title:
                exclude_pattern = re.escape(idea_title[:40]) + "|" + exclude_pattern
            heading_els = page.locator("h1, h2, h3, h4").filter(has_not_text=re.compile(exclude_pattern, re.IGNORECASE))
            all_heading_count = heading_els.count()
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

            # `expected_count` (from the page's own "Analyzed N ..." line)
            # counts ONLY real content entries — it does NOT include the
            # page's own leading non-content heading(s) that always
            # appear first in the filtered heading list, ahead of the real
            # entries (e.g. "Reddit Community Analysis", "Other
            # Communities", or on YouTube specifically BOTH "YouTube
            # Content Analysis" AND "Top Channels" — two, not one).
            # min(expected_count, all_heading_count) therefore always
            # undercounted whenever such heading(s) were present —
            # confirmed directly across ALL FOUR platforms in one real
            # crawl: Reddit was missing its true last subreddit
            # (r/AI_Agents), Facebook its 5th group, YouTube its final TWO
            # channels, and Other its 4th segment ("AI Builder / LLM
            # Evaluation & Monitoring Communities") — every single one
            # silently dropped because the loop below ran short, spending
            # its last available slot(s) on content that was actually
            # still within bounds but never reached.
            #
            # For "other" specifically, cap at expected_count + 1 (its one
            # known leading "Other Communities" boilerplate heading,
            # confirmed directly) rather than the full
            # len(surviving_heading_texts) — that list also includes the
            # Content Strategies section's own per-audience sub-headings
            # (e.g. "AI Customer Service & Chatbot Operators"), which
            # aren't excludable by a fixed string the way the 3 section
            # headers themselves are (their names are dynamic per idea),
            # so reaching that far would re-capture them a second time as
            # fake extra "communities" alongside the real segment cards.
            # Those sections are already captured properly and separately
            # via the dedicated otherCommunitiesExtra mechanism below.
            #
            # For the other 3 platforms, use the full
            # len(surviving_heading_texts) — the real, already-verified
            # list of everything that survived the exclusion filter — as
            # the correct number of iterations needed to reach every real
            # entry, since none of them have this same trailing-sections
            # complication.
            if platform_key == "other" and expected_count:
                card_count = min(expected_count + 1, all_heading_count)
            else:
                card_count = min(len(surviving_heading_texts), all_heading_count)

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
                        best_candidate = None
                        for depth in [1, 2, 3, 4, 5]:
                            candidate = heading.locator(f"xpath=ancestor::*[self::div][{depth}]")
                            if candidate.count() == 0:
                                continue
                            try:
                                candidate_text = candidate.inner_text(timeout=2000)
                            except Exception:
                                continue
                            stripped = candidate_text.strip()
                            if not (stripped.startswith(name[:20]) and len(candidate_text) < 2000):
                                continue
                            # A real capture of the FIRST "Other Communities"
                            # segment showed this deepest-wins strategy
                            # over-reaching: since nothing precedes the
                            # first card, an ancestor wide enough to also
                            # include the NEXT sibling card still passed
                            # both checks above (it still started with this
                            # card's name, and stayed under the 2000-char
                            # cap) — confirmed directly, the saved text
                            # continued straight into the next card's own
                            # title/tagline/Pain Points after this card's
                            # tags. "Pain Points" is a structural marker
                            # that appears exactly once per genuine single
                            # card on this platform's real pages — if a
                            # candidate contains it twice, this depth has
                            # already spilled into a second card, so keep
                            # the previous (shallower) candidate instead of
                            # this wider one.
                            if candidate_text.count("Pain Points") > 1:
                                break
                            best_candidate = candidate
                        container = best_candidate
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
                                # A real crawl confirmed popup.url stays "" /
                                # about:blank immediately after
                                # wait_for_load_state("domcontentloaded") —
                                # a known Playwright behavior (confirmed via
                                # a documented GitHub issue showing the exact
                                # same symptom): window.open() opens the tab
                                # blank first, then the real destination is
                                # set asynchronously via JS a moment later,
                                # so "domcontentloaded" resolves against
                                # that initial blank state, not the eventual
                                # real one. Poll briefly for a real
                                # (non-blank, non-empty) URL instead of
                                # trusting a single read right after the
                                # popup opens.
                                popup_url = ""
                                for _ in range(20):  # up to ~4s total (20 * 200ms)
                                    popup_url = popup.url
                                    if popup_url and popup_url != "about:blank":
                                        break
                                    popup.wait_for_timeout(200)
                                popup.close()
                                if popup_url and popup_url != "about:blank" and popup_url not in seen_urls and "ideabrowser.com" not in popup_url:
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

            # "Content Strategies", "Partnership Opportunities", and
            # "Citations & Sources" are PAGE-LEVEL sections on the "Other
            # Communities" sub-page — siblings of the community segment
            # cards above, not nested inside any of them (confirmed
            # directly: surviving_headings_dump showed them appearing as
            # real headings AFTER the last community segment card, not as
            # part of its container). The per-card loop above deliberately
            # stops at expected_count (the "Analyzed N community segments"
            # figure), so it never reaches these — this is genuinely
            # separate, additive content, not something the existing loop
            # was supposed to already capture.
            #
            # page_text_for_count already holds the FULL page text (it's
            # captured once via get_visible_text(page) before any of the
            # per-card navigation above happens), so these sections can be
            # extracted directly from it via string parsing — no new
            # navigation needed, and no risk of the per-card loop's
            # repeated page.goto() calls having changed what's on the page
            # by this point.
            #
            # IMPORTANT: stored on the OUTER "extra" dict (closed over
            # from the enclosing function), NOT inside result[platform_key]
            # or as a new top-level key of `result` itself — result's keys
            # are iterated elsewhere (normalize_and_build_manifest.py) as
            # platform -> [community, ...] pairs, and a dict value there
            # instead of a list would break that iteration (e.g. slicing a
            # dict like a list raises a TypeError). Keeping this fully
            # separate avoids that risk entirely.
            if platform_key == "other":
                def crawl_other_page_sections():
                    text = page_text_for_count
                    captured = {}

                    # Both "Content Strategies" and "Partnership
                    # Opportunities" appear TWICE on this page — once as a
                    # stat label in the "Analysis Overview" table near the
                    # top (e.g. "Content Strategies\n\n3"), and once again
                    # as the real section heading further down, after all
                    # the community segment cards. Confirmed directly: a
                    # real capture using re.search (which always matches
                    # the FIRST occurrence) grabbed just "3" for
                    # contentStrategies, and swept the ENTIRE page between
                    # the first "Partnership Opportunities" and the real
                    # "Citations & Sources" into partnershipOpportunities —
                    # including every community card's full Pain
                    # Points/Interests/tags content. Use the LAST match of
                    # each heading instead, since the real content section
                    # always comes after the stat-label occurrence.
                    def last_match_start(pattern):
                        matches = list(re.finditer(pattern, text))
                        return matches[-1].end() if matches else None

                    cs_start = last_match_start(r"Content Strategies\n")
                    po_start = last_match_start(r"Partnership Opportunities\n")
                    cit_start = last_match_start(r"Citations\s*&\s*Sources\n")

                    if cs_start is not None and po_start is not None and po_start > cs_start:
                        captured["contentStrategies"] = text[cs_start:po_start].rsplit("Partnership Opportunities", 1)[0].strip()[:3000]

                    if po_start is not None and cit_start is not None and cit_start > po_start:
                        captured["partnershipOpportunities"] = text[po_start:cit_start].rsplit("Citations", 1)[0].strip()[:1500]

                    # Citations & Sources: confirmed via a real screenshot
                    # of the live site that each citation row displays as
                    # "- https://..." with NO visible leading number in the
                    # actual rendered row text (numbering is likely a CSS
                    # counter or separate small index element, not part of
                    # the same text node inner_text() captures) — the
                    # original regex required a leading digit and could
                    # therefore never match a single real line, which is
                    # exactly why citations_count came back 0 on a real
                    # crawl despite the section itself being present.
                    # Accept lines with OR without a leading number.
                    if cit_start is not None:
                        citations = []
                        n = 0
                        for line in text[cit_start:].strip().split("\n"):
                            line = line.strip()
                            if not line or line == "0":
                                continue
                            m = re.match(r"^(\d+)\s*-\s*(.+)$", line)
                            if m:
                                citations.append({"n": m.group(1), "url": m.group(2).strip()})
                                continue
                            m2 = re.match(r"^-\s*(https?://\S+)$", line)
                            if m2:
                                n += 1
                                citations.append({"n": str(n), "url": m2.group(1).strip()})
                                continue
                            if citations:
                                # A line that's neither a numbered citation
                                # nor a bare "- url" line, appearing after
                                # we've already started collecting real
                                # citations, means we've run past the end
                                # of this block — stop rather than keep
                                # scanning indefinitely.
                                break
                        if citations:
                            captured["citations"] = citations[:20]

                    other_communities_extra.update(captured)
                    log.append({
                        "step": "crawl_platform:other:page_sections_captured",
                        "has_content_strategies": "contentStrategies" in captured,
                        "has_partnership_opportunities": "partnershipOpportunities" in captured,
                        "citations_count": len(captured.get("citations", [])),
                    })

                crawler.safe(crawl_other_page_sections, "crawl_platform:other:page_sections")


        crawler.safe(crawl_platform, f"community_platform:{platform_key}")
        log.append({
            "step": f"crawl_platform:{platform_key}:finished",
            "communities_found": len(result[platform_key]),
        })

    # Attached under a key distinct from the 4 platform names (reddit,
    # facebook, youtube, other) specifically so downstream code iterating
    # result.items() as platform -> [community, ...] pairs (see
    # normalize_and_build_manifest.py) can simply skip it by name rather
    # than needing to guess at its shape.
    if other_communities_extra:
        result["_otherCommunitiesExtra"] = other_communities_extra

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

    try:
        chart_screenshot_before = str(ROOT / "library" / "chart_before_debug_screenshot.png")
        chart.screenshot(path=chart_screenshot_before)
        log.append({"step": "crawl_chart_history:screenshot_before", "path": chart_screenshot_before})
    except Exception as e:
        log.append({"step": "crawl_chart_history:screenshot_before", "error": str(e)})

    page.mouse.move(box["x"] - 20, box["y"] + box["height"] / 2)
    page.wait_for_timeout(200)

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

    try:
        full_page_screenshot = str(ROOT / "library" / "chart_fullpage_debug_screenshot.png")
        page.screenshot(path=full_page_screenshot, full_page=False)
        log.append({"step": "crawl_chart_history:screenshot_fullpage", "path": full_page_screenshot})
    except Exception as e:
        log.append({"step": "crawl_chart_history:screenshot_fullpage", "error": str(e)})

    try:
        chart_html = chart.evaluate("el => el.outerHTML") or ""
        log.append({"step": "crawl_chart_history:chart_html_sample", "html": chart_html[:3000]})
    except Exception as e:
        log.append({"step": "crawl_chart_history:chart_html_sample", "error": str(e)})

    sample_count = 24  # roughly monthly resolution across a 2-year chart
    seen_labels = set()
    for i in range(sample_count):
        frac = i / (sample_count - 1)
        x = box["x"] + frac * box["width"]
        y = box["y"] + box["height"] * 0.5  # vertical center is safest for line charts
        try:
            page.mouse.move(x - 5, y, steps=3)
            page.mouse.move(x, y, steps=3)
            page.wait_for_timeout(200)  # let the tooltip re-render
            tooltip = page.locator(".recharts-tooltip-wrapper, [role='tooltip']").first
            tooltip_count = tooltip.count()
            tooltip_visible = tooltip.is_visible() if tooltip_count > 0 else False

            if tooltip_count > 0 and not tooltip_visible:
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

            tooltip_text_raw = ""
            if tooltip_count > 0:
                try:
                    tooltip_text_raw = tooltip.evaluate("el => el.innerText || el.textContent || ''") or ""
                except Exception:
                    tooltip_text_raw = ""

            if not tooltip_text_raw.strip():
                try:
                    chart.hover(position={"x": x - box["x"], "y": y - box["y"]}, force=True, timeout=2000)
                    page.wait_for_timeout(200)
                    if tooltip.count() > 0:
                        tooltip_text_raw = tooltip.evaluate("el => el.innerText || el.textContent || ''") or ""
                except Exception as e:
                    log.append({"step": f"crawl_chart_history:element_hover_fallback:{i}", "error": str(e)})

            has_real_tooltip_content = bool(tooltip_text_raw.strip())

            if i < 3:
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


def crawl_score_cards_deep(crawler: Crawler, base_url: str, layout_detected: str = "old") -> dict:
    """
    The main page's 4 top score cards (Opportunity, Problem, Feasibility,
    Why Now) each open a small modal on click showing the score, a short
    description, and a "View detailed analysis" button — confirmed via
    real screenshots. That button navigates to a genuinely deeper page
    with its own real sub-sections.

    NEW-LAYOUT SKIP GUARD — a real 2026-08-28 crawl log confirmed all 4 of
    these cards genuinely do not exist on the new layout ("'Opportunity'
    card not visible on main page", and the "Problem" attempt in
    particular burned an enormous multi-thousand-word Playwright retry
    log clicking on what turned out to be an unrelated feedback button,
    before finally timing out at 8s) — the new layout's scoring shows up
    as pain_score/timing_score/overall_score instead (see
    extract_new_layout_fields), not these 4 cards. Skip immediately on a
    new-layout day rather than repeat those doomed retries.
    """
    if layout_detected == "new":
        crawler.log.append({"step": "crawl_score_cards_deep", "note": "skipped: new layout has no Opportunity/Problem/Feasibility/Why Now score cards (confirmed via real 2026-08-28 crawl log) — see pain_score/timing_score/overall_score instead"})
        return {}

    page = crawler.page
    log = crawler.log
    result = {}

    card_labels = ["Opportunity", "Problem", "Feasibility", "Why Now"]

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

            result[card_label] = strip_boilerplate(get_visible_text(page))[:8000]

            page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)

        crawler.safe(crawl_card, f"score_card:{card_label}")

    return result


def crawl_business_fit_deep(crawler: Crawler, base_url: str, layout_detected: str = "old") -> dict:
    """
    The main page's "Business Fit" section shows 4 short summary cards
    (Revenue Potential, Execution Difficulty, Go-To-Market, Right for You)
    — each already captured as plain one-line text in the main page's own
    raw_text. Clicking any of these cards opens a genuinely deeper modal
    with real additional structured content.

    NEW-LAYOUT SKIP GUARD — a real 2026-08-28 crawl log confirmed all 3 of
    these cards genuinely do not exist on the new layout ("'Revenue
    Potential' card not visible", "'Execution Difficulty' card not
    visible", "'Go-To-Market' card not visible" — the same
    execution_difficulty_modal attempt earlier in that log also failed
    outright: "Could not find a visible 'Execution Difficulty' element to
    click"). Skip immediately on a new-layout day rather than repeat
    those doomed retries.
    """
    if layout_detected == "new":
        crawler.log.append({"step": "crawl_business_fit_deep", "note": "skipped: new layout has no Revenue Potential/Execution Difficulty/Go-To-Market Business Fit cards (confirmed via real 2026-08-28 crawl log)"})
        return {}

    page = crawler.page
    log = crawler.log
    result = {}

    card_labels = ["Revenue Potential", "Execution Difficulty", "Go-To-Market"]

    for card_label in card_labels:

        def crawl_card(card_label=card_label):
            page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
            page.wait_for_timeout(WAIT_CHART)
            url_before = page.url

            card_heading = page.get_by_text(card_label, exact=False).first
            if not card_heading.is_visible():
                raise Exception(f"'{card_label}' card not visible on main page")
            card_heading.scroll_into_view_if_needed(timeout=5000)
            card_heading.click(timeout=8000)
            page.wait_for_timeout(WAIT_CHART)

            modal = page.locator("[role='dialog'], .modal, [class*='Modal']").first
            if modal.count() == 0:
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

    HREF CAPTURE — each subpage's entry now also carries "links": every
    real outbound <a href> found on that subpage, alongside its existing
    "text" and "url" fields (see get_page_text_and_links's own docstring
    for why this can't be recovered later from text alone). This is what
    lets the normalizer wire real citation links into e.g. the "Explore
    the evidence" and "Understand the opening" subpages' rendered
    content, instead of every inline source (SHOPIFY NEWS, GIGRADAR,
    r/shopify OP...) staying unclickable plain text.
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
        # New layout (confirmed 2026-08-27) uses different CTA link text
        # for the same kind of "go deeper" links — added as additional
        # labels to try, alongside the old ones above, rather than
        # replacing them, since we don't yet know if the old layout is
        # gone everywhere or might still appear for some ideas/accounts.
        "Keep reading",
        "See the full timing case",
        "Explore the evidence",
        "Understand the opening",
        "See the detailed plan",
        "Run the model on your numbers",
        "View the full value ladder",
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
                text, links = get_page_text_and_links(page)
                subpages[key] = {"text": text.strip(), "url": page.url, "links": links}
                page.goto(base_url, wait_until="networkidle", timeout=NAV_TIMEOUT)
                page.wait_for_timeout(WAIT_CHART)

            crawler.safe(click_and_capture, f"subpage:{label}#{i}")

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
        text, links = get_page_text_and_links(page)
        subpages["Execution Difficulty"] = {"text": text.strip(), "url": page.url, "links": links}

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
                # Save whatever the checkpoint page looked like, for
                # debugging — but this is now a MUCH rarer path than
                # before, since wait_out_bot_checkpoint accepts multiple
                # real-content markers rather than one that a redesign can
                # silently remove. If this genuinely still fires, save the
                # raw text as the safety net it's meant to be, since even
                # a "blocked" page's raw text can hold useful diagnostic
                # value (as the 2026-08-27 capture proved directly: the
                # "blocked" page's raw_text actually contained the ENTIRE
                # real idea content, just misclassified as blocked).
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
        layout_detected = record["summary"].get("layout_detected", "old")
        log.append({
            "step": "layout_detection",
            "layout_detected": layout_detected,
            "note": "old = Keyword:/emoji-card layout, new = THE IDEA/AT A GLANCE layout confirmed live 2026-08-27",
        })

        record["keyword_analysis"] = crawler.safe(
            lambda: crawl_keyword_analysis(crawler, layout_detected), "crawl_keyword_analysis", default=[]
        ) or []

        # Return to a clean main-page state before sub-page crawling
        crawler.safe(lambda: page.goto(URL, wait_until="networkidle", timeout=NAV_TIMEOUT), "reload_before_subpages")
        page.wait_for_timeout(2000)
        wait_out_bot_checkpoint(page, log, max_wait_ms=8000)

        record["subpages"] = crawler.safe(
            lambda: crawl_subpages(crawler, URL), "crawl_subpages", default={}
        ) or {}

        record["business_fit_deep"] = crawler.safe(
            lambda: crawl_business_fit_deep(crawler, URL, layout_detected), "crawl_business_fit_deep", default={}
        ) or {}

        record["score_cards_deep"] = crawler.safe(
            lambda: crawl_score_cards_deep(crawler, URL, layout_detected), "crawl_score_cards_deep", default={}
        ) or {}

        # NEW: the 4 "AT A GLANCE" popups (Setup Tutorial Views / Pain /
        # Timing / Year 1, Done Right), confirmed live only on the new
        # layout — genuinely new UI, not an equivalent of anything the old
        # layout had, so this only runs when layout_detected == "new"
        # rather than needing its own separate skip-guard convention.
        record["glance_popups"] = {}
        if layout_detected == "new":
            for glance_label in GLANCE_POPUP_LABELS:
                popup_data = crawler.safe(
                    lambda l=glance_label: crawl_glance_popup(crawler, URL, l),
                    f"glance_popup:{glance_label}",
                    default={},
                )
                if popup_data:
                    record["glance_popups"][glance_label] = popup_data
        else:
            log.append({"step": "crawl_glance_popups", "note": "skipped: old layout has no 'AT A GLANCE' stat-teaser popups"})

        community_page = record["subpages"].get("View detailed breakdown")
        if community_page and community_page.get("url"):
            record["community_signals_deep"] = crawler.safe(
                lambda: crawl_community_signals_deep(crawler, community_page["url"], record["summary"].get("title", ""), layout_detected),
                "crawl_community_signals_deep",
                default={},
            ) or {}
        else:
            record["community_signals_deep"] = {}
            if layout_detected == "new":
                log.append({"step": "crawl_community_signals_deep", "note": "skipped: new layout has no 'View detailed breakdown' subpage to drill into (confirmed via real 2026-08-28 crawl log)"})
            else:
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
    print(f"  Glance popups captured: {len(record.get('glance_popups', {}))}")
    print(f"  Errors logged: {len(errors)} (see {log_path})")


if __name__ == "__main__":
    main()
