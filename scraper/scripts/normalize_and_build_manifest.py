#!/usr/bin/env python3
"""
Takes the raw output of deep_crawl.py (library/<year>/<date>.deep.json) and
normalizes it into the exact shape the web app expects (see
../DATA_CONTRACT.md), writing library/<year>/<date>.json. Then rebuilds
library/manifest.json so the app knows every day that's been captured.

This is a separate step from deep_crawl.py on purpose: the crawler's raw
output depends on fragile CSS selectors against a live SPA and needs
independent debugging, while this normalizer just reshapes whatever JSON
the crawler produced — it can be fixed/improved without touching the
crawling logic at all.

Run this AFTER deep_crawl.py in the same daily job.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = ROOT / "library"
MANIFEST_PATH = LIBRARY_DIR / "manifest.json"


def extract_score(raw_scores: dict, key: str) -> dict:
    """raw_scores comes from deep_crawl's regex-based summary extraction."""
    val = raw_scores.get(key) if raw_scores else None
    if isinstance(val, dict) and "score" in val:
        return {"score": val["score"], "label": val.get("label", "")}
    return {"score": None, "label": ""}


def _is_boilerplate_community_name(name: str) -> bool:
    """
    Excludes page-navigation/section-heading text that the crawler's
    heading-based community matching swept up alongside genuine community
    entries — confirmed via real captured data showing entries like
    "Discover your founder archetype" (a site-wide quiz CTA appearing on
    every community-signals sub-page), "Reddit Community Analysis" /
    "YouTube Content Analysis" (the page's own section title, repeated
    per-platform), "Key Findings" / "Analysis Overview" / "Community
    Types" / "Community Segments" (generic sub-headings), and bare
    platform-name headings ("Facebook Groups", "Other Communities").
    None of these are real community/channel/group names — genuine
    entries look like "r/AI_Agents", "IBM Technology and IBM Developer",
    "Jeff Su", etc.
    """
    if not name:
        return True
    noise_patterns = [
        "discover your founder archetype",
        "community analysis", "content analysis",
        "key findings", "analysis overview",
        "community types", "community segments",
        "facebook groups", "other communities",
        "top channels",
    ]
    name_lower = name.strip().lower()
    return any(pattern in name_lower for pattern in noise_patterns)


def normalize_keywords(keyword_analysis: list) -> list:
    """
    deep_crawl.py's keyword_analysis is a list of:
      {"keyword": str, "stats": {"volume": "8.1K", "growth": "+50%", ...}}

    (Earlier version had a "by_time_range" dict with 4 time-range variants,
    but a real run confirmed the main Idea-of-the-Day page has no such
    control at all — that assumption came from a different, dedicated
    "Keyword Analysis" sub-page seen in early screenshots. Each keyword now
    has one real stats snapshot, matching what's actually shown inline.)

    A site redesign confirmed live 2026-08-27 dropped the keyword-volume
    dropdown/chart entirely — a real crawl of the new layout produced a
    single synthetic entry {"keyword": "unknown", "stats": {}}, since the
    crawler's fallback path (used when it can't enumerate real options)
    always emits SOME entry rather than none. That placeholder carries no
    real data and would render as a fake "unknown" keyword row in the app,
    so it's filtered out here rather than passed through as if it were
    real.
    """
    out = []
    for kw in keyword_analysis or []:
        if kw.get("keyword") == "unknown" and not kw.get("stats"):
            continue

        stats = kw.get("stats", {})
        volume_raw = stats.get("volume", "0")
        growth_raw = stats.get("growth", "0%")

        # "8.1K" -> 8100, "480" -> 480
        vol_match = re.match(r"([\d.]+)(K)?", str(volume_raw).replace(",", ""))
        volume = 0
        if vol_match:
            num = float(vol_match.group(1))
            if vol_match.group(2):
                num *= 1000
            volume = int(num)

        growth_match = re.match(r"([+\-]?[\d.]+)%", str(growth_raw).replace(",", ""))
        growth = float(growth_match.group(1)) if growth_match else 0

        out.append({
            "keyword": kw["keyword"],
            "volume": volume,
            "growth": growth,
            "cpc": stats.get("cpc"),
            "competition": stats.get("competition"),
            # Real month-by-month history from hovering the site's own
            # chart (see deep_crawl.py's crawl_chart_history) — now
            # captured for every keyword, not just the first, per explicit
            # request (accepting the real added crawl time). Absent
            # entirely (rather than an empty list) if the scraper couldn't
            # find/hover the chart for a given keyword that day, so the app
            # can distinguish "no history captured" from "captured but
            # genuinely empty".
            **({"chartHistory": kw["chart_history"]} if kw.get("chart_history") else {}),
        })
    return out



def extract_pitch(raw_text: str, title: str) -> str:
    """
    The raw page text starts with sidebar navigation junk before the real
    pitch paragraph. If we know the real title (extracted by the crawler),
    the actual pitch is everything after it, up to the next major section
    marker (e.g. "*Analysis, scores" disclaimer or "Keyword:").
    """
    if not title or title not in raw_text:
        return raw_text[:4000]
    after_title = raw_text.split(title, 1)[1]
    for stop_marker in ["*Analysis, scores", "\nKeyword:", "\nTHE IDEA\n"]:
        if stop_marker in after_title:
            after_title = after_title.split(stop_marker, 1)[0]
            break

    # Trim leading badge/emoji lines (e.g. "⏰\nPerfect Timing\n⚡\n
    # Unfair Advantage\n+16 More") so the pitch starts at the first real
    # sentence, not decorative badges.
    lines = after_title.strip().split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^[+\d]", stripped):  # "+16 More"
            continue
        if re.match(r"^[\U0001F000-\U0001FFFF\u2600-\u27BF]", stripped):  # emoji-only line
            continue
        if len(stripped) < 25:  # short badge labels like "Perfect Timing"
            continue
        start_idx = i
        break
    return "\n".join(lines[start_idx:]).strip()


def find_subpage_by_url_pattern(subpages: dict, url_pattern: str) -> dict:
    """
    Sub-pages are stored keyed by the LINK TEXT that was clicked to reach
    them (e.g. "Understand the market opportunity", "View Analysis #1"),
    not by what the page actually contains — and several different links
    share generic labels like "View Analysis" for genuinely different
    pages (Value Equation, Market Matrix, ACP framework all use it). The
    one reliable identifier is each sub-page's captured URL, which always
    ends in a stable slug (e.g. "/market-gap", "/value-equation",
    "/execution-plan"). Matching on that instead of the link label is far
    more robust.
    """
    for entry in subpages.values():
        if url_pattern in entry.get("url", ""):
            return entry
    return {}


def trim_subpage_nav(text: str) -> str:
    """
    Every sub-page's captured text starts with the same sidebar navigation
    boilerplate before the real content: "...Free plan\nToggle Sidebar\n
    Browse Ideas\n<idea title>\n<Section Name>\nBuild Gallery\nUpgrade\n\n
    START HERE\n\nDiscover your founder archetype\n\n...Take the quiz\n"
    then the actual section content begins. A first version of the
    normalizer stored this raw, so every field (Market Gap, Execution
    Plan, etc) displayed identical-looking nav junk before its real,
    genuinely distinct content — confusing since the content WAS correct,
    just buried under an unstripped, repeated prefix.

    "Take the quiz" reliably marks the end of that boilerplate across every
    sub-page sampled so far, so we cut everything up to and including it.
    """
    if not text:
        return text
    # Two real marker variants have been confirmed present depending on
    # exactly which capture path text comes through: the separate button
    # text "Take the quiz", and — confirmed directly missing from a real
    # community summary capture — the descriptive sentence just above it
    # ("Take a quick quiz to discover..."), which ends in a period rather
    # than matching the shorter button phrase at all. Try both, using
    # whichever is actually found, and split on its LAST occurrence since
    # this same boilerplate block has been observed repeating twice in a
    # single captured community summary.
    markers = ["Take the quiz", "waste time on the wrong thing."]
    for marker in markers:
        if marker in text:
            return text.rsplit(marker, 1)[1].strip()
    return text.strip()


def trim_execution_difficulty(text: str) -> str:
    """
    The Execution Difficulty modal is captured while the main Idea-of-the-
    Day page is still showing underneath it, so its raw text is the ENTIRE
    main page's content, with the actual modal content appended at the very
    end (after the page's own "Execution Difficulty" section heading
    appears a second time, this time followed by the real modal body:
    "Overview", "Execution Risks", "Technical Challenges", etc). We want
    only that final, real modal section, not the whole page above it.
    """
    if not text:
        return text
    # The modal's own content starts with a repeated "Execution Difficulty"
    # heading immediately followed by the difficulty score (e.g. "3/10")
    # and then "Solo-friendly build..." — find the LAST occurrence of this
    # heading, since it appears once in the page's Framework Fit summary
    # and again for the actual modal body.
    marker = "Execution Difficulty"
    last_idx = text.rfind(marker)
    if last_idx == -1:
        return text.strip()
    return text[last_idx:].strip()


# Maps a new-layout section_* key (as written by deep_crawl.py's
# extract_new_layout_fields) to a clean display label for the app. Keeping
# this list here (not in deep_crawl.py) means adding/renaming a displayed
# label never requires touching the crawler at all — only what got
# captured does.
NEW_LAYOUT_SECTION_LABELS = {
    "section_the_idea": "The Idea",
    "section_at_a_glance": "At a Glance",
    "section_the_customer": "The Customer",
    "section_why_now": "Why Now",
    "section_proof_signals": "Proof & Signals",
    "section_market_snapshot": "Market Snapshot",
    "section_whitespace": "Whitespace",
    "section_who_you_re_up_against": "Who You're Up Against",
    "section_people_are_asking_for_it": "People Are Asking For It",
    "section_the_verdict": "The Verdict",
    "section_founder_fit": "Founder Fit",
    "section_what_you_d_sell": "What You'd Sell",
    "section_the_plan": "The Plan",
    "section_napkin_math": "Napkin Math",
    "section_the_playbooks": "The Playbooks",
}


def extract_new_layout_sections(summary: dict) -> dict:
    """
    Pulls every section_* field deep_crawl.py's extract_new_layout_fields
    captured (confirmed live 2026-08-27) into an ordered {label: text}
    dict the app can render directly, same shape as businessFitDeep/
    scoreCardsDeep already use. Returns {} entirely if this day's summary
    has no new-layout fields at all (i.e. layout_detected == "old" or the
    key is simply absent), so the app can tell "nothing to show here" from
    "this day genuinely has an empty section" — an absent key, not an
    empty dict value under a present key.
    """
    out = {}
    for key, label in NEW_LAYOUT_SECTION_LABELS.items():
        val = summary.get(key)
        if val:
            out[label] = val
    return out


def normalize_day(raw: dict) -> dict:
    summary = raw.get("summary", {})
    subpages = raw.get("subpages", {})
    title = summary.get("title") or "Untitled idea"
    pitch = extract_pitch(summary.get("raw_text", ""), summary.get("title"))

    # New layout (confirmed live 2026-08-27) has its own real "THE IDEA"
    # section which is a cleaner, more complete pitch than what
    # extract_pitch's old-layout-oriented heuristic manages to isolate
    # from raw_text (that heuristic's stop markers/badge-skipping logic
    # was written against the OLD layout's structure and was never
    # updated for the new one) — prefer it directly when present, falling
    # back to the heuristic extraction only for old-layout days or any
    # day where, for whatever reason, that specific section wasn't
    # captured.
    if summary.get("section_the_idea"):
        pitch = summary["section_the_idea"]

    market_gap_page = find_subpage_by_url_pattern(subpages, "/market-gap")
    execution_plan_page = find_subpage_by_url_pattern(subpages, "/execution-plan")
    value_equation_page = find_subpage_by_url_pattern(subpages, "/value-equation")
    market_matrix_page = find_subpage_by_url_pattern(subpages, "/value-matrix")
    acp_page = find_subpage_by_url_pattern(subpages, "/acp")
    value_ladder_page = find_subpage_by_url_pattern(subpages, "/value-ladder")
    community_page = find_subpage_by_url_pattern(subpages, "/community-signals")
    proof_signals_page = find_subpage_by_url_pattern(subpages, "/proof-signals")
    why_now_page = find_subpage_by_url_pattern(subpages, "/why-now")
    keywords_page = find_subpage_by_url_pattern(subpages, "/keywords")
    # Execution Difficulty is a modal on the main page itself, not a
    # separate URL — its captured url stays "/hub/ideas/today" (or ends
    # with the idea's own slug with no extra suffix). We identify it by
    # matching on its own dict key instead, which the crawler always
    # writes as exactly "Execution Difficulty".
    execution_difficulty_entry = subpages.get("Execution Difficulty", {})

    normalized = {
        "id": raw["date"],
        "date": raw["date"],
        "title": title,
        "tagline": (pitch[:160] + "...") if len(pitch) > 160 else pitch,
        "badges": [],
        "description": pitch[:4000],
        "scores": {
            "opportunity": extract_score(summary, "opportunity"),
            "problem": extract_score(summary, "problem"),
            "feasibility": extract_score(summary, "feasibility"),
            "whyNow": extract_score(summary, "why_now"),
        },
        "keywords": normalize_keywords(raw.get("keyword_analysis", [])),
        "marketGap": trim_subpage_nav(market_gap_page.get("text", ""))[:6000],
        "executionPlan": trim_subpage_nav(execution_plan_page.get("text", ""))[:6000],
        "executionDifficulty": {
            "score": None,
            "note": trim_execution_difficulty(execution_difficulty_entry.get("text", ""))[:3000],
        },
        "categorization": {
            "type": summary.get("type"),
            "market": summary.get("market"),
            "target": summary.get("target"),
            "competitor": summary.get("main_competitor"),
        },
        "communitySignals": summary.get("community_signals_summary", {}),
        "communitySignalsDetail": trim_subpage_nav(community_page.get("text", ""))[:6000],
        # Real, structured community data (actual subreddit/group names,
        # discussion titles, and real external links) from
        # crawl_community_signals_deep in deep_crawl.py — distinct from
        # communitySignalsDetail above, which is just the summary page's
        # raw paragraph text. Each discussion's "url" is a genuine href
        # captured from the live page, not fabricated. Trimmed defensively
        # in case a platform's community list is unexpectedly large.
        #
        # The crawler's heading-based matching (necessary since these pages
        # don't reliably expose "View Analysis"-style links at this level)
        # also sweeps up genuine page-navigation/boilerplate headings
        # alongside real community entries — e.g. "Discover your founder
        # archetype" (a site-wide quiz CTA), "Reddit Community Analysis" /
        # "Analysis Overview" / generic platform-name headings (the page's
        # own section titles, not real communities). Filter those out by
        # name pattern so only genuine entries (e.g. "IBM Technology and
        # IBM Developer", "r/AI_Agents") reach the app.
        "communitySignalsRich": {
            platform: [
                {
                    "name": community.get("name", ""),
                    # A real screenshot confirmed each community's own
                    # summary text still started with the same repeated
                    # sidebar/quiz boilerplate every other sub-page field
                    # already has stripped via trim_subpage_nav — this was
                    # simply never applied here, unlike valueEquation,
                    # marketMatrix, etc below. Fixed for consistency.
                    "summary": trim_subpage_nav(community.get("raw_text", "") or "")[:1500],
                    "discussions": (community.get("discussions", []) or [])[:10],
                    # Deliberately NOT including the community's own "url"
                    # field here — that's the ideabrowser.com page it was
                    # captured from, not a real external link, and per
                    # explicit request only genuine external links
                    # (Reddit/Facebook/YouTube/etc, already captured in
                    # "discussions" above) should ever reach the app.
                }
                for community in (communities or [])[:10]
                if not _is_boilerplate_community_name(community.get("name", ""))
            ]
            for platform, communities in (raw.get("community_signals_deep") or {}).items()
            # "_otherCommunitiesExtra" is a distinct, non-platform key
            # (Content Strategies / Partnership Opportunities / Citations
            # from the "Other Communities" sub-page — see deep_crawl.py's
            # crawl_community_signals_deep) that deliberately does NOT
            # hold a list of communities like the 4 real platform keys do.
            # Skip it here so it isn't sliced like a list (which would
            # raise, since it's a dict) — it's surfaced separately below
            # as its own top-level field instead.
            if platform != "_otherCommunitiesExtra"
        },
        # Content Strategies / Partnership Opportunities / Citations for
        # the "Other Communities" page — page-level sections that sit
        # alongside (not inside) the community segment cards above.
        "otherCommunitiesExtra": (raw.get("community_signals_deep") or {}).get("_otherCommunitiesExtra") or {},
        # Real deeper modal content for the 4 Business Fit summary cards
        # (Revenue Potential, Execution Difficulty, Go-To-Market, Right
        # for You) — confirmed via a real screenshot to contain genuine
        # additional structure (Overview, Revenue Examples, Business
        # Models, Example Companies) not present in the main page's own
        # plain summary text at all.
        "businessFitDeep": raw.get("business_fit_deep") or {},
        # Real deeper modal + "View detailed analysis" page content for
        # the 4 score cards (Opportunity, Problem, Feasibility, Why Now)
        # — confirmed via real screenshots to contain genuine additional
        # structure (Market Analysis, Competitive Position, Key
        # Strengths, Key Risks) beyond the plain score already captured
        # in "scores" above.
        "scoreCardsDeep": raw.get("score_cards_deep") or {},
        "valueEquation": trim_subpage_nav(value_equation_page.get("text", ""))[:6000],
        "marketMatrix": trim_subpage_nav(market_matrix_page.get("text", ""))[:6000],
        "acpFramework": trim_subpage_nav(acp_page.get("text", ""))[:6000],
        "valueLadderDetail": trim_subpage_nav(value_ladder_page.get("text", ""))[:6000],
        "proofSignals": trim_subpage_nav(proof_signals_page.get("text", ""))[:6000],
        "whyNowDetail": trim_subpage_nav(why_now_page.get("text", ""))[:6000],
        "keywordAnalysisDetail": trim_subpage_nav(keywords_page.get("text", ""))[:6000],
        # NEW: site redesign fields confirmed live 2026-08-27. Every
        # section_* field the crawler managed to isolate (The Idea, The
        # Customer, Why Now, The Verdict, Founder Fit, The Plan, Napkin
        # Math, etc), keyed by clean display label — {} on any old-layout
        # day, or any new-layout day where extraction genuinely found
        # nothing (distinct from the app's existing raw_text-only fallback
        # for a day where NEITHER parser matched at all).
        "newLayoutSections": extract_new_layout_sections(summary),
        # overall_score/pain_score/timing_score are the new layout's own
        # distinct scoring shape (one combined score up top, PAIN/TIMING
        # shown as separate sub-scores later) rather than the old
        # layout's 4-way Opportunity/Problem/Feasibility/Why Now split —
        # None on any day that doesn't have them, so the app can tell
        # "not applicable" from "genuinely zero".
        "overallScore": summary.get("overall_score"),
        "painScore": summary.get("pain_score"),
        "timingScore": summary.get("timing_score"),
        "layoutDetected": summary.get("layout_detected", "old"),
        # Always present regardless of which layout/parser matched (or
        # neither) — the one guaranteed safety net so a day's real content
        # is never fully lost even if both structured parsers miss
        # entirely on some future third redesign. Capped generously since
        # this is meant as a genuine fallback read, not a duplicate of
        # the structured fields above.
        "rawText": (summary.get("raw_text") or "")[:20000],
        "status": "not_started",
        "notes": "",
        "_source_url": raw.get("source_url"),
        "_scraped_at": raw.get("scraped_at"),
        "_crawl_had_errors": len([l for l in raw.get("crawl_log", []) if "error" in l]) > 0,
    }
    return normalized


def main():
    if not LIBRARY_DIR.exists():
        print("No library/ directory found — has deep_crawl.py run yet?")
        return

    manifest_entries = []

    for year_dir in sorted(LIBRARY_DIR.glob("*")):
        if not year_dir.is_dir():
            continue
        for raw_file in sorted(year_dir.glob("*.deep.json")):
            date_str = raw_file.name.replace(".deep.json", "")
            raw = json.loads(raw_file.read_text(encoding="utf-8"))
            normalized = normalize_day(raw)

            out_path = year_dir / f"{date_str}.json"
            out_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

            manifest_entries.append({
                "id": normalized["id"],
                "title": normalized["title"],
                "path": str(out_path.relative_to(ROOT)),
                "had_errors": normalized["_crawl_had_errors"],
            })
            print(f"Normalized {date_str} -> {out_path}")

    manifest_entries.sort(key=lambda e: e["id"], reverse=True)
    MANIFEST_PATH.write_text(
        json.dumps({"ideas": manifest_entries}, indent=2), encoding="utf-8"
    )
    print(f"\nManifest updated: {len(manifest_entries)} ideas -> {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
