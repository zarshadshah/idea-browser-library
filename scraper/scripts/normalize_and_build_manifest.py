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


def normalize_keywords(keyword_analysis: list) -> list:
    """
    deep_crawl.py's keyword_analysis is a list of:
      {"keyword": str, "stats": {"volume": "8.1K", "growth": "+50%", ...}}

    (Earlier version had a "by_time_range" dict with 4 time-range variants,
    but a real run confirmed the main Idea-of-the-Day page has no such
    control at all — that assumption came from a different, dedicated
    "Keyword Analysis" sub-page seen in early screenshots. Each keyword now
    has one real stats snapshot, matching what's actually shown inline.)
    """
    out = []
    for kw in keyword_analysis or []:
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
        return raw_text[:2000]
    after_title = raw_text.split(title, 1)[1]
    for stop_marker in ["*Analysis, scores", "\nKeyword:"]:
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


def normalize_day(raw: dict) -> dict:
    summary = raw.get("summary", {})
    subpages = raw.get("subpages", {})
    title = summary.get("title") or "Untitled idea"
    pitch = extract_pitch(summary.get("raw_text", ""), summary.get("title"))

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
        "description": pitch[:2000],
        "scores": {
            "opportunity": extract_score(summary, "opportunity"),
            "problem": extract_score(summary, "problem"),
            "feasibility": extract_score(summary, "feasibility"),
            "whyNow": extract_score(summary, "why_now"),
        },
        "keywords": normalize_keywords(raw.get("keyword_analysis", [])),
        "marketGap": market_gap_page.get("text", "")[:2000],
        "executionPlan": execution_plan_page.get("text", "")[:2000],
        "executionDifficulty": {
            "score": None,
            "note": execution_difficulty_entry.get("text", "")[:500],
        },
        "categorization": {
            "type": summary.get("type"),
            "market": summary.get("market"),
            "target": summary.get("target"),
            "competitor": summary.get("main_competitor"),
        },
        "communitySignals": summary.get("community_signals_summary", {}),
        "communitySignalsDetail": community_page.get("text", "")[:2000],
        "valueEquation": value_equation_page.get("text", "")[:1500],
        "marketMatrix": market_matrix_page.get("text", "")[:1500],
        "acpFramework": acp_page.get("text", "")[:2000],
        "valueLadderDetail": value_ladder_page.get("text", "")[:1500],
        "proofSignals": proof_signals_page.get("text", "")[:2000],
        "whyNowDetail": why_now_page.get("text", "")[:2000],
        "keywordAnalysisDetail": keywords_page.get("text", "")[:2000],
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
