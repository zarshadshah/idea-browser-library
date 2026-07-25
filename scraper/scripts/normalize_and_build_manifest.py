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
      {"keyword": str, "by_time_range": {"6 Months": {...}, "1 Year": {...}, ...}}
    The app wants a flat list of {keyword, volume, growth}. We prefer the
    "1 Year" figures as the representative snapshot (matches what the site
    shows by default), falling back to whichever time range has data.
    """
    out = []
    for kw in keyword_analysis or []:
        by_range = kw.get("by_time_range", {})
        stats = by_range.get("1 Year") or next(iter(by_range.values()), {})
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
            "all_time_ranges": by_range,  # kept for the app's future use / debugging
        })
    return out


def normalize_day(raw: dict) -> dict:
    summary = raw.get("summary", {})
    subpages = raw.get("subpages", {})

    normalized = {
        "id": raw["date"],
        "date": raw["date"],
        "title": summary.get("title") or "Untitled idea",
        "tagline": (summary.get("raw_text", "")[:160] + "...") if summary.get("raw_text") else "",
        "badges": [],
        "description": summary.get("raw_text", "")[:2000],
        "scores": {
            "opportunity": extract_score(summary, "opportunity"),
            "problem": extract_score(summary, "problem"),
            "feasibility": extract_score(summary, "feasibility"),
            "whyNow": extract_score(summary, "why_now"),
        },
        "keywords": normalize_keywords(raw.get("keyword_analysis", [])),
        "marketGap": subpages.get("Market Gap", {}).get("text", "")[:2000],
        "executionPlan": subpages.get("Execution Plan", {}).get("text", "")[:2000],
        "executionDifficulty": {
            "score": None,
            "note": subpages.get("Execution Difficulty", {}).get("text", "")[:500],
        },
        "categorization": {
            "type": summary.get("type"),
            "market": summary.get("market"),
            "target": summary.get("target"),
            "competitor": summary.get("main_competitor"),
        },
        "communitySignals": summary.get("community_signals_summary", {}),
        "valueEquation": subpages.get("Value Equation", {}).get("text", "")[:500],
        "marketMatrix": subpages.get("Market Matrix", {}).get("text", "")[:500],
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
