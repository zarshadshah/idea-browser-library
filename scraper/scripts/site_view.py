"""
site_view.py — turns one day's raw crawl (deep.json) into a structured,
site-ordered "siteView" that the app renders like the real ideabrowser.com
idea page: same sections, same order, real links attached to the things
they belong to (sources, receipts, competitors, Reddit threads), the
"go deeper" content folded in under the section it expands, and every
paid / agent-only / promo part left out.

Built and tested against the real captures in scraper/library/2026:
  v2 layout  2026-08-27 .. 2026-10-06  (THE IDEA / THE CUSTOMER / glance stats)
  v3 layout  2026-10-07 .. today       (hero card: THE PITCH / WHO IT'S FOR /
                                         THE GAP / AT A GLANCE / BIGGEST RISK)
Both share the same main sections from WHY NOW to NAPKIN MATH.

Returns None for old-layout days (before 2026-08-27); the app keeps its
existing tabbed view for those.
"""

import re

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return (s or "").replace("’", "'").replace("‘", "'").strip()


def _lines(text: str) -> list:
    return [l.strip() for l in (text or "").split("\n") if l.strip()]


def _is_caps_label(line: str, max_len: int = 40) -> bool:
    """Short ALL-CAPS line such as 'THE PITCH', 'REDDIT', 'YEAR 1, DONE RIGHT',
    'SHOPIFY FOOD & BEVERAGE…'. Must contain at least 2 letters and no
    lowercase letters."""
    l = line.strip()
    if not l or len(l) > max_len:
        return False
    letters = [c for c in l if c.isalpha()]
    return len(letters) >= 2 and not any(c.islower() for c in l)


def _clean_for_match(s: str) -> str:
    s = _norm(s).lower()
    s = s.replace("“", "").replace("”", "").replace('"', "").replace("…", "").replace("...", "")
    return re.sub(r"\s+", " ", s).strip()


class LinkIndex:
    """Matches a piece of page text (a quote, a competitor name, a source
    label) to the real href captured for it. Link texts on the site are the
    whole card's text truncated to 200 chars, e.g.
        "Canny\\n\\nINCUMBENT\\n\\nThe dominant public feedback-board…"
        "“If a potential deal, is > $20k…\\n\\nSaaStr"
    so matching is by first line (exact) or by a long-enough common prefix."""

    def __init__(self, links):
        self.items = []
        seen = set()
        for l in links or []:
            href, text = l.get("href"), l.get("text") or ""
            if not href or (text, href) in seen:
                continue
            seen.add((text, href))
            first = _clean_for_match(text.split("\n")[0])
            whole = _clean_for_match(text)
            self.items.append({"href": href, "text": text, "first": first, "whole": whole})

    def find(self, text: str, min_prefix: int = 24):
        t = _clean_for_match(text)
        if not t:
            return None
        for it in self.items:            # exact first-line / whole-text match
            if it["first"] == t or it["whole"] == t:
                return it["href"]
        if len(t) >= min_prefix:          # long text: shared prefix
            probe = t[:60]
            for it in self.items:
                cand = it["first"] if len(it["first"]) >= min_prefix else it["whole"]
                n = min(len(probe), len(cand))
                if n >= min_prefix and probe[:n] == cand[:n]:
                    return it["href"]
        return None

    def short_labels(self, max_len: int = 70) -> list:
        """Single-line link labels the client can linkify inline in prose
        (e.g. 'Software Equity Group', 'DISHER', 'Shopify Changelog')."""
        out, seen = [], set()
        for it in self.items:
            label = it["text"].strip()
            if "\n" in label or not (2 < len(label) <= max_len) or label in seen:
                continue
            seen.add(label)
            out.append({"text": label, "href": it["href"]})
        return out


# Lines that are UI chrome / paid / agent prompts, never content.
DROP_LINES = {
    "keep reading", "see the full timing case", "explore the evidence", "understand the opening",
    "see the detailed plan", "view the full value ladder", "run the model on your numbers",
    "roast it with your agent", "build this with your agent", "test the fit with your agent",
    "run this angle with your agent", "build this idea", "interested?", "add to project",
    "get your card", "go pro", "upgrade", "save", "share",
}


def _drop(line: str) -> bool:
    l = _norm(line).lower()
    return l in DROP_LINES or l.endswith("with your agent")


# ---------------------------------------------------------------------------
# section finding
# ---------------------------------------------------------------------------

MAIN_SECTIONS = [
    ("whyNow", "WHY NOW", "Why now"),
    ("marketSnapshot", "MARKET SNAPSHOT", "Market snapshot"),
    ("whitespace", "WHITESPACE", "Whitespace"),
    ("proof", "PROOF & SIGNALS", "Proof & signals"),
    ("competitors", "WHO YOU'RE UP AGAINST", "Who you're up against"),
    ("asking", "PEOPLE ARE ASKING FOR IT", "People are asking for it"),
    ("verdict", "THE VERDICT", "The verdict"),
    ("founderFit", "FOUNDER FIT", "Founder fit"),
    ("valueLadder", "WHAT YOU'D SELL", "What you'd sell"),
    ("plan", "THE PLAN", "The plan"),
    ("napkin", "NAPKIN MATH", "Napkin math"),
]
END_MARKERS = {"THE PLAYBOOKS", "THE AGENTS"}


def _find_sections(lines: list):
    """Returns (hero_lines, {id: lines}, tail_lines)."""
    normed = [_norm(l) for l in lines]
    try:
        snap = normed.index("MARKET SNAPSHOT")
    except ValueError:
        return None, {}, []
    # The full WHY NOW section is the LAST 'WHY NOW' before MARKET SNAPSHOT
    # (v3 also has a 'WHY NOW' headline inside the hero card).
    why_idx = max((i for i in range(snap) if normed[i] == "WHY NOW"), default=None)

    positions = []
    cursor = 0
    for sid, header, _ in MAIN_SECTIONS:
        start_from = why_idx if sid == "whyNow" and why_idx is not None else cursor
        idx = None
        for i in range(start_from, len(normed)):
            if normed[i] == header:
                idx = i
                break
        if idx is not None:
            positions.append((sid, idx))
            cursor = idx + 1
    end = len(lines)
    for i in range(cursor, len(normed)):
        if normed[i] in END_MARKERS:
            end = i
            break

    sections = {}
    for n, (sid, idx) in enumerate(positions):
        nxt = positions[n + 1][1] if n + 1 < len(positions) else end
        sections[sid] = lines[idx + 1:nxt]
    hero_end = positions[0][1] if positions else snap
    return lines[:hero_end], sections, lines[end:]


# ---------------------------------------------------------------------------
# per-section parsers
# ---------------------------------------------------------------------------

def _quotes(lines, links, platform_labels=False):
    """“quote…” followed by its attribution line. Optionally groups under
    ALL-CAPS platform labels (REDDIT, X, YOUTUBE…)."""
    out, platform = [], None
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("“") or l.startswith('"'):
            source = None
            if i + 1 < len(lines) and not lines[i + 1].startswith("“") and not re.match(r"^All \d+ receipts", lines[i + 1]) \
                    and not (platform_labels and _is_caps_label(lines[i + 1], 20)):
                source = lines[i + 1]
                i += 1
            out.append({"quote": l, "source": source, "href": links.find(l), "platform": platform})
        elif platform_labels and _is_caps_label(l, 20):
            platform = l
        i += 1
    return out


def parse_why_now(lines, links):
    body = [l for l in lines if not _drop(l)]
    headline = body[0] if body else ""
    paras, sources, in_sources = [], [], False
    for l in body[1:]:
        if _norm(l) == "SOURCES":
            in_sources = True
            continue
        if in_sources:
            sources.append({"label": l, "href": links.find(l)})
        else:
            paras.append(l)
    return {"headline": headline, "paragraphs": paras, "sources": sources}


def parse_market_snapshot(lines, links):
    body = [l for l in lines if not _drop(l)]
    title = body[0] if body and not body[0].isupper() else None
    severity = None
    for l in body:
        m = re.match(r"^(\d+(?:\.\d+)?)\s*/\s*10\s+SEVERITY", l, re.I)
        if m:
            severity = m.group(1)
            break
    receipts_line = next((l for l in body if re.match(r"^All \d+ receipts", l)), None)
    return {"title": title, "painSeverity": severity, "quotes": _quotes(body, links), "receiptsLabel": receipts_line}


def parse_whitespace(lines, links):
    body = [l for l in lines if not _drop(l)]
    out = {"gap": None, "wedge": [], "incumbent": None, "other": []}
    mode = None
    for l in body:
        n = _norm(l)
        if n == "MARKET GAP":
            mode = "gap"
            continue
        if n == "THE WEDGE":
            mode = "wedge"
            continue
        m = re.match(r"^The incumbent to beat:\s*(.+)$", l)
        if m:
            out["incumbent"] = {"name": m.group(1), "href": links.find(m.group(1))}
            continue
        if mode == "gap" and out["gap"] is None:
            out["gap"] = l
        elif mode == "wedge":
            out["wedge"].append(l)
        else:
            out["other"].append(l)
    return out


def parse_proof(lines, links):
    body = [l for l in lines if not _drop(l)]
    items, pending = [], []
    for l in body:
        if _is_caps_label(l, 70) and pending:
            items.append({"text": " ".join(pending), "source": l, "href": links.find(l)})
            pending = []
        else:
            pending.append(l)
    if pending:
        items.append({"text": " ".join(pending), "source": None, "href": None})
    return {"items": items}


def parse_competitors(lines, links):
    body = [l for l in lines if not _drop(l)]
    count = None
    if body and re.match(r"^\d+\s+PLAYERS?$", body[0], re.I):
        count = int(body[0].split()[0])
        body = body[1:]
    players, cur = [], None
    for l in body:
        if _norm(l) == "INCUMBENT" and cur:
            cur["incumbent"] = True
            continue
        is_desc = len(l) > 70 or l.endswith(".") or l.startswith("(")
        if not is_desc:
            cur = {"name": l, "incumbent": False, "description": "", "href": links.find(l)}
            players.append(cur)
        elif cur:
            cur["description"] = (cur["description"] + " " + l).strip()
    return {"count": count, "players": players}


def parse_asking(lines, links):
    body = [l for l in lines if not _drop(l)]
    return {"quotes": _quotes(body, links, platform_labels=True)}


def parse_verdict(lines, links):
    body = [l for l in lines if not _drop(l)]
    title = body[0] if body and not _is_caps_label(body[0]) else None
    build, notb, mode = [], [], None
    for l in body:
        n = _norm(l)
        if n == "REASONS TO BUILD":
            mode = "b"
            continue
        if n in ("REASONS TO NOT BUILD", "REASONS NOT TO BUILD"):
            mode = "n"
            continue
        if mode == "b":
            build.append(l)
        elif mode == "n":
            notb.append(l)
    return {"title": title, "build": build, "notBuild": notb}


def _pairs(lines):
    """label / value alternating lines (THE REALITY, demand scores)."""
    out = []
    for i in range(0, len(lines) - 1, 2):
        out.append({"label": lines[i], "value": lines[i + 1]})
    return out


def parse_founder_fit(lines, links):
    body = []
    for l in lines:
        if _norm(l).lower().startswith("so, is it good for you"):
            break
        if not _drop(l):
            body.append(l)
    title = body[0] if body and not _is_caps_label(body[0]) else None
    best, persona, demands, reality = [], [], [], []
    mode = None
    for l in body[1:] if title else body:
        n = _norm(l)
        if n == "WHO IT'S BEST FOR":
            mode = "best"
            continue
        if n == "WHAT IT DEMANDS":
            mode = "demands"
            continue
        if n == "THE REALITY":
            mode = "reality"
            continue
        if mode == "best":
            (persona if len(l) > 150 else best).append(l)
        elif mode == "demands":
            demands.append(l)
        elif mode == "reality":
            reality.append(l)
        else:
            persona.append(l)
    demand_pairs = []
    for i in range(0, len(demands) - 1, 2):
        val = demands[i + 1]
        if re.match(r"^\d+(\.\d+)?$", val):
            demand_pairs.append({"label": demands[i], "score": float(val)})
    return {"title": title, "bestFor": best, "persona": persona, "demands": demand_pairs, "reality": _pairs(reality)}


def parse_value_ladder(lines, links):
    body = [l for l in lines if not _drop(l)]
    title = body[0] if body and not _is_caps_label(body[0]) else None
    intro, steps, cur = [], [], None
    i = 1 if title else 0
    while i < len(body):
        l = body[i]
        if re.match(r"^\d$", l) and i + 1 < len(body) and _is_caps_label(body[i + 1]):
            tier = body[i + 1]
            name_line = body[i + 2] if i + 2 < len(body) else ""
            m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", name_line)
            cur = {"step": int(l), "tier": tier,
                   "name": m.group(1) if m else name_line,
                   "price": m.group(2) if m else None, "description": ""}
            steps.append(cur)
            i += 3
            continue
        if cur:
            cur["description"] = (cur["description"] + " " + l).strip()
        else:
            intro.append(l)
        i += 1
    return {"title": title, "intro": intro, "steps": steps}


def parse_plan(lines, links):
    body = [l for l in lines if not _drop(l)]
    if body and body[-1].lower().startswith("year one, on a napkin"):
        body = body[:-1]
    title = body[0] if body else None
    rest = body[1:]
    sub = None
    if rest and len(rest[0]) < 40 and rest[0].endswith("."):
        sub, rest = rest[0], rest[1:]
    return {"title": title, "subtitle": sub, "paragraphs": rest}


def parse_napkin(lines, links):
    body = [l for l in lines if not _drop(l)]
    intro = body[0] if body and len(body[0]) > 60 else None
    rest = body[1:] if intro else body
    rows, summary, ceiling = [], [], None
    i = 0
    while i < len(rest):
        l = rest[i]
        if _norm(l).startswith("THE CEILING"):
            ceiling = rest[i + 1] if i + 1 < len(rest) else None
            i += 2
            continue
        if len(l) > 140:
            summary.append(l)
            i += 1
            continue
        if i + 1 < len(rest) and len(rest[i + 1]) <= 45 and not _norm(rest[i + 1]).startswith("THE CEILING"):
            rows.append({"label": l, "value": rest[i + 1]})
            i += 2
            continue
        summary.append(l)
        i += 1
    return {"title": "Year one, on a napkin.", "intro": intro, "rows": rows, "summary": summary, "ceiling": ceiling}


PARSERS = {
    "whyNow": parse_why_now, "marketSnapshot": parse_market_snapshot, "whitespace": parse_whitespace,
    "proof": parse_proof, "competitors": parse_competitors, "asking": parse_asking,
    "verdict": parse_verdict, "founderFit": parse_founder_fit, "valueLadder": parse_value_ladder,
    "plan": parse_plan, "napkin": parse_napkin,
}


# ---------------------------------------------------------------------------
# hero (top of page) + header
# ---------------------------------------------------------------------------

HERO_STOP = {"interested?", "add to project", "build this idea", "build this with your agent"}
# Labels whose content is prose (rendered as paragraphs, full width).
KNOWN_HERO_LABELS = {
    "THE IDEA", "THE CUSTOMER", "CONCEPT MOCKUP", "PAIN", "TIMING", "YEAR 1, DONE RIGHT",
    "WHAT IT DEMANDS", "THE REALITY", "UP AGAINST", "THE PITCH", "WHO IT'S FOR", "THE GAP",
    "WHY NOW", "AT A GLANCE", "WHAT YOU SELL", "BIGGEST RISK",
}
PROSE_LABELS = {"THE IDEA", "THE PITCH", "WHO IT'S FOR", "THE GAP", "WHY NOW", "BIGGEST RISK"}


def parse_hero(hero_lines, title, links):
    lines = list(hero_lines)
    # Skip sidebar / nav: start right after the title line.
    start = 0
    for i, l in enumerate(lines):
        if _norm(l) == _norm(title):
            start = i + 1
            break
    else:
        for i, l in enumerate(lines):
            if l == "Browse all":
                start = i + 2
                break
    lines = lines[start:]

    header = {"ibIndex": None, "tags": []}
    cards, cur = [], None
    for l in lines:
        n = _norm(l)
        if n.lower() in HERO_STOP or _drop(l):
            continue
        m = re.match(r"^IB Index\s+([\d.]+)$", l)
        if m:
            header["ibIndex"] = m.group(1)
            continue
        if cur is None and n not in KNOWN_HERO_LABELS:
            # v3 tag line(s): "B2B · SaaS", "$8M-$15M ARR"; v2: "6.8" "/10"
            if l in ("·", "/10"):
                continue
            if re.match(r"^\d+(\.\d+)?$", l):
                header["ibIndex"] = header["ibIndex"] or l
                continue
            header["tags"].extend([t.strip() for t in l.split("·") if t.strip()])
            continue
        # A new card starts at a known hero label, or at the idea-specific
        # first stat ("REDDIT THREADS", "USED EV BUYERS", "SHOPIFY FOOD &
        # BEVERAGE…") which always directly follows the CONCEPT MOCKUP slot.
        after_mockup = bool(cards) and cards[-1]["label"] == "CONCEPT MOCKUP" and not cards[-1]["lines"]
        if _is_caps_label(l) and (n in KNOWN_HERO_LABELS or after_mockup):
            cur = {"label": n, "lines": []}
            cards.append(cur)
            continue
        if cur is None:
            header["tags"].extend([t.strip() for t in l.split("·") if t.strip() and t.strip() != "·"])
            continue
        if cur is not None:
            cur["lines"].append(l)

    out_cards = []
    for c in cards:
        if c["label"] == "CONCEPT MOCKUP" and not c["lines"]:
            continue
        card = {"label": c["label"], "lines": c["lines"], "prose": c["label"] in PROSE_LABELS}
        if c["label"] == "UP AGAINST" and c["lines"]:
            card["href"] = links.find(c["lines"][0])
        if c["label"] == "THE REALITY":
            card["pairs"] = _pairs(c["lines"])
        if c["label"] == "AT A GLANCE":
            card["pairs"] = _pairs(c["lines"])
        if c["label"] == "THE CUSTOMER" and c["lines"]:
            card["pairs"] = _pairs(c["lines"][1:])
            card["lead"] = c["lines"][0]
        if c["label"] == "WHAT YOU SELL" and c["lines"]:
            m = re.match(r"^(.*?)((?:\$|Free).*)$", c["lines"][0])
            if m:
                card["name"], card["price"] = m.group(1).strip(), m.group(2).strip()
        out_cards.append(card)
    return header, out_cards


def parse_tail_glance(tail_lines, links):
    """v2 put an AT A GLANCE sidebar after the playbooks."""
    normed = [_norm(l) for l in tail_lines]
    if "AT A GLANCE" not in normed:
        return None
    i = normed.index("AT A GLANCE") + 1
    out = []
    while i < len(tail_lines):
        l = tail_lines[i]
        if _norm(l).upper() in ("SAVE", "SHARE", "AGENT NOT CONNECTED"):
            break
        out.append(l)
        i += 1
    return out


# ---------------------------------------------------------------------------
# "go deeper" pages + popups: only the NEW text they reveal
# ---------------------------------------------------------------------------

EXPANDED_TO_SECTION = {
    "Keep reading": "hero",
    "See the full timing case": "whyNow",
    "All receipts": "marketSnapshot",
    "Understand the opening": "whitespace",
    "Explore the evidence": "proof",
    "See the detailed plan": "plan",
    "View the full value ladder": "valueLadder",
}


def _novel_blocks(text, base_set):
    blocks, title = [], None
    for l in _lines(text):
        if l in base_set or _drop(l):
            continue
        n = _norm(l)
        if n.upper() == "THE NEXT STEP":
            break
        if (l.startswith("“") and "argue the other side" in l) or n.startswith("PRO"):
            continue
        if title is None and not blocks and l.endswith(".") and len(l) < 40:
            title = l
            continue
        blocks.append({"type": "h" if _is_caps_label(l, 60) else "p", "text": l})
    return title, blocks


def build_site_view(raw: dict):
    summary = raw.get("summary") or {}
    raw_text = summary.get("raw_text") or ""
    # Also accepts days the crawler wrongly flagged "blocked_by_checkpoint"
    # while the real page was captured (2026-10-09, 2026-10-29).
    if summary.get("layout_detected") != "new" and "\nMARKET SNAPSHOT\n" not in raw_text:
        return None
    lines = _lines(raw_text)
    title = summary.get("title") or ""
    if not title and "Browse all" in lines:
        i = lines.index("Browse all")
        title = lines[i + 1] if i + 1 < len(lines) else ""

    all_links = list(raw.get("main_links") or [])
    for sp in (raw.get("subpages") or {}).values():
        all_links.extend(sp.get("links") or [])
    for pp in (raw.get("glance_popups") or {}).values():
        if isinstance(pp, dict):
            all_links.extend(pp.get("links") or [])
    links = LinkIndex(all_links)

    hero_lines, sec_lines, tail = _find_sections(lines)
    if hero_lines is None:
        return None

    header, cards = parse_hero(hero_lines, title, links)
    date_label = None
    for l in lines[:80]:
        m = re.match(r"^IDEA OF THE DAY\s*·\s*(.+)$", l)
        if m:
            date_label = m.group(1)
            break
    tail_glance = parse_tail_glance(tail, links)
    if tail_glance and not any(c["label"] == "AT A GLANCE" for c in cards):
        tg = tail_glance[1:] if tail_glance and re.match(r"^\d+(\.\d+)?$", tail_glance[0]) else tail_glance
        cards.append({"label": "AT A GLANCE", "lines": tg, "prose": False, "pairs": _pairs(tg)})

    sections = []
    for sid, header_text, label in MAIN_SECTIONS:
        if sid not in sec_lines:
            continue
        data = PARSERS[sid](sec_lines[sid], links)
        sections.append({"id": sid, "kicker": label, "data": data})

    # Expanded "go deeper" content, as only the text it adds to the page.
    base_set = set(lines)
    expansions = {}
    for key, sp in (raw.get("subpages") or {}).items():
        sid = EXPANDED_TO_SECTION.get(key)
        if not sid or "/pro" in (sp.get("url") or ""):
            continue
        t, blocks = _novel_blocks(sp.get("text", ""), base_set)
        if blocks:
            expansions[sid] = {"label": key, "title": t, "blocks": blocks}
    for sec in sections:
        if sec["id"] in expansions:
            sec["more"] = expansions[sec["id"]]

    popups = []
    for key, pp in (raw.get("glance_popups") or {}).items():
        if not isinstance(pp, dict) or not pp.get("text"):
            continue
        if re.match(r"^(legal|build gallery|start here|master money model)\b", key.strip(), re.I):
            continue  # site chrome / paid playbooks, not idea content
        t, blocks = _novel_blocks(pp["text"], base_set)
        if blocks:
            popups.append({"label": key, "title": t, "blocks": blocks})

    pain = next((s["data"].get("painSeverity") for s in sections if s["id"] == "marketSnapshot"), None)
    return {
        "version": "v3" if any(c["label"] == "THE PITCH" for c in cards) else "v2",
        "dateLabel": date_label,
        "title": title,
        "ibIndex": header["ibIndex"] or (str(summary.get("overall_score")) if summary.get("overall_score") else None),
        "tags": header["tags"],
        "painSeverity": pain,
        "hero": cards,
        "heroMore": expansions.get("hero"),
        "sections": sections,
        "popups": popups,
        "inlineLinks": links.short_labels(),
        "linkCount": len(links.items),
        "sourceUrl": raw.get("source_url"),
    }
