#!/usr/bin/env python3
"""
Kingshot Wiki — static site builder
------------------------------------
Reads the Markdown vault in content/ and generates a full static wiki
website into docs/ (served directly by GitHub Pages, no server needed).

Usage:
    python3 build.py

Requires: pip install -r requirements.txt   (just the `markdown` package)
"""
import re
import json
import shutil
import random
import hashlib
from pathlib import Path

import markdown

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
OUTPUT_DIR = ROOT / "docs"
STATIC_SRC = ROOT / "static"


def _compute_asset_version():
    """Short hash of the actual CSS+JS content, so any edit to either file
    automatically busts browser/CDN cache — no more 'I updated the code but
    my browser still shows the old version' during active development."""
    h = hashlib.sha256()
    for rel in ("css/style.css", "js/main.js"):
        p = STATIC_SRC / rel
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


ASSET_VERSION = _compute_asset_version()

SITE_NAME = "Kingshot Wiki"
SITE_TAGLINE = "[ONE]OneForAll Alliance Knowledge Vault"

# Free, privacy-friendly visit counter — https://www.goatcounter.com/
# Dashboard: https://hsrohrbaugh.goatcounter.com
GOATCOUNTER_CODE = "hsrohrbaugh"

# Maps the vault's folder names -> (category slug, sidebar label)
CATEGORY_FOLDERS = {
    "00 Home": "home",
    "01 Events": "events",
    "02 Heroes": "heroes",
    "03 Gear": "gear",
    "04 Announcements": "announcements",
    "05 Reference": "reference",
    "06 Game Systems": "systems",
}

CATEGORY_LABELS = {
    "events": "Events",
    "heroes": "Heroes",
    "gear": "Gear",
    "announcements": "Announcements",
    "reference": "Reference",
    "systems": "Game Systems",
}

CATEGORY_DESCRIPTIONS = {
    "events": "What each alliance and kingdom event is, how it works, and how to prep for it.",
    "heroes": "Every hero across seven generations — kits, roles, and F2P priority notes.",
    "gear": "Hero Gear, Governor Gear, and Governor Charms progression guides.",
    "announcements": "Copy-paste-ready announcements to drop straight into alliance chat.",
    "reference": "Glossary, the event calendar, the F2P priority guide, and about this wiki.",
    "systems": "Core systems: the beginner's guide, arena/conquest, pets, troops, gems.",
}

# Order in which category cards / sidebar sections appear
CATEGORY_ORDER = ["events", "heroes", "gear", "announcements", "reference", "systems"]

# Home.md's own section headings, mapped to the category they order.
# (Parsed once to inherit the vault author's intended reading order.)
HOME_SECTION_TO_CATEGORY = {
    "Events": "events",
    "Announcements": "announcements",
    "Heroes": "heroes",
    "Gear": "gear",
    "Reference": "reference",
    "Game Systems": "systems",
}

CALLOUT_ICONS = {
    "tip": "&#128161;",       # 💡
    "warning": "&#9888;",     # ⚠
    "info": "&#8505;",        # ℹ
    "important": "&#10071;",  # ❗
    "note": "&#128220;",      # 📜
}

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    text = text.lower().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def render_inline_md(text: str) -> str:
    """Render a short markdown snippet (already wikilink-resolved) and strip
    the wrapping <p> tag markdown.markdown() adds for single-line input."""
    html = markdown.markdown(text, extensions=MD_EXTENSIONS)
    html = html.strip()
    m = re.match(r"^<p>(.*)</p>$", html, flags=re.DOTALL)
    return m.group(1) if m else html


def make_rel(url: str, depth: int) -> str:
    """Turn a canonical absolute-style url ('/events/bear-hunt/') into a path
    relative to a page living `depth` folders deep, so the site works at any
    GitHub Pages base path (project page, user page, or custom domain)."""
    prefix = "../" * depth
    return prefix + url.lstrip("/")


def depth_of(url: str) -> int:
    return len([p for p in url.strip("/").split("/") if p])


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def parse_frontmatter(raw: str):
    """This vault only ever uses a few simple flat keys, so a tiny custom
    parser is more predictable here than pulling in a full YAML dependency."""
    tags, aliases = [], []
    is_calendar = False
    is_gear_index = False
    nav_pin = None  # None, "top", or "bottom"
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            block = raw[3:end]
            body = raw[end + 4:].lstrip("\n")
            for line in block.splitlines():
                line = line.strip()
                m = re.match(r"^tags:\s*\[(.*)\]$", line)
                if m:
                    tags = [t.strip() for t in m.group(1).split(",") if t.strip()]
                m = re.match(r"^aliases:\s*\[(.*)\]$", line)
                if m:
                    aliases = [a.strip() for a in m.group(1).split(",") if a.strip()]
                m = re.match(r"^calendar:\s*(true|false)$", line, re.IGNORECASE)
                if m:
                    is_calendar = m.group(1).lower() == "true"
                m = re.match(r"^gear_index:\s*(true|false)$", line, re.IGNORECASE)
                if m:
                    is_gear_index = m.group(1).lower() == "true"
                m = re.match(r"^nav_pin:\s*(true|top|bottom|false)$", line, re.IGNORECASE)
                if m:
                    val = m.group(1).lower()
                    nav_pin = None if val == "false" else ("top" if val == "true" else val)
    return tags, aliases, is_calendar, is_gear_index, nav_pin, body


def split_title(body: str):
    """Pull out the first H1 line as the title; return (title, rest-of-body)."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("# "):
            title = line.strip()[2:].strip()
            rest = "\n".join(lines[i + 1:])
            return title, rest
    return None, body


FACT_LINE_RE = re.compile(r"^\*\*([^*:]+):\*\*\s*(.*)$")


def extract_infobox_facts(body: str):
    """Consume consecutive '**Key:** value' lines right at the top of the
    article body (after skipping any leading blank lines). Returns
    (facts_list, remaining_body)."""
    lines = body.split("\n")
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    facts = []
    while i < len(lines):
        m = FACT_LINE_RE.match(lines[i])
        if not m:
            break
        facts.append((m.group(1).strip(), m.group(2).strip()))
        i += 1
    return facts, "\n".join(lines[i:])


def make_meta_description(body_md: str, fallback_title: str, max_len: int = 155) -> str:
    """Build a plain-text summary straight from source markdown: skip
    headings, callouts/blockquotes, and table rows, resolve wikilinks to
    their display text, and strip emphasis markers."""
    lines = []
    for raw_line in body_md.split("\n"):
        s = raw_line.strip()
        if not s or s.startswith(">") or s.startswith("#") or s.startswith("|"):
            continue
        s = re.sub(r"^[-*]\s*\[[ xX]\]\s*", "", s)
        s = re.sub(r"^[-*]\s+", "", s)
        s = re.sub(r"^\d+\.\s+", "", s)
        lines.append(s)
    text = " ".join(lines)
    text = WIKILINK_RE.sub(lambda m: m.group(1).split("|")[-1].split("#")[0].strip(), text)
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = f"{fallback_title} — part of the Kingshot alliance knowledge vault."
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"
    return text


SEE_ALSO_RE = re.compile(r"^See also:\s*(.*)$", re.MULTILINE)


def extract_see_also(body: str):
    """Pull out the trailing 'See also: [[X]], [[Y]]' line if present."""
    m = SEE_ALSO_RE.search(body)
    if not m:
        return None, body
    line_text = m.group(1)
    new_body = body[:m.start()] + body[m.end():]
    return line_text, new_body


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def resolve_wikilinks(text: str, notes: dict) -> str:
    def repl(m):
        target = m.group(1)
        page = target.split("|")[0].split("#")[0].strip()
        if "|" in target:
            display = target.split("|", 1)[1].strip()
        else:
            display = target.split("#")[0].strip()
        note = notes.get(page)
        if not note:
            return display
        return f'[{display}]({note["url"]})'
    return WIKILINK_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# Callouts  ( > [!tip] Title \n > body... )
# ---------------------------------------------------------------------------

CALLOUT_START_RE = re.compile(r"^>\s?\[!(\w+)\]\s*(.*)$")


def extract_callouts(text: str):
    lines = text.split("\n")
    out = []
    callouts = []
    i = 0
    while i < len(lines):
        m = CALLOUT_START_RE.match(lines[i])
        if m:
            ctype = m.group(1).lower()
            title = m.group(2).strip()
            body_lines = []
            i += 1
            while i < len(lines) and lines[i].startswith(">"):
                content = lines[i][1:]
                if content.startswith(" "):
                    content = content[1:]
                body_lines.append(content)
                i += 1
            placeholder = f"@@CALLOUT{len(callouts)}@@"
            callouts.append((ctype, title, "\n".join(body_lines)))
            out.append(placeholder)
            out.append("")
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), callouts


def render_callout(ctype, title, body_md, notes):
    icon = CALLOUT_ICONS.get(ctype, "&#128204;")
    if not title:
        title = ctype.capitalize()
    body_resolved = resolve_wikilinks(body_md, notes)
    body_html = markdown.markdown(body_resolved, extensions=MD_EXTENSIONS)
    return (
        f'<div class="callout callout-{ctype}">'
        f'<p class="callout-title"><span class="callout-icon">{icon}</span>{title}</p>'
        f'<div class="callout-body">{body_html}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Post-processing on rendered HTML
# ---------------------------------------------------------------------------

def process_task_lists(html: str) -> str:
    html = re.sub(
        r"<li>\[ \]\s*(.*?)</li>",
        r'<li class="task-item"><input type="checkbox" disabled> \1</li>',
        html,
    )
    html = re.sub(
        r"<li>\[[xX]\]\s*(.*?)</li>",
        r'<li class="task-item"><input type="checkbox" checked disabled> \1</li>',
        html,
    )
    return html


_copy_counter = [0]


def add_copy_buttons(html: str) -> str:
    def repl(m):
        code_content = m.group(1)
        idx = _copy_counter[0]
        _copy_counter[0] += 1
        return (
            f'<div class="code-block">'
            f'<button type="button" class="copy-btn" onclick="copyCode(this)">Copy</button>'
            f'<pre><code id="code-{idx}">{code_content}</code></pre>'
            f"</div>"
        )
    return re.sub(r"<pre><code>(.*?)</code></pre>", repl, html, flags=re.DOTALL)


def add_heading_ids(html: str) -> str:
    counts = {}
    def repl(m):
        tag, text = m.group(1), m.group(2)
        base = slugify(strip_tags(text)) or "section"
        if base in counts:
            counts[base] += 1
            hid = f"{base}-{counts[base]}"
        else:
            counts[base] = 0
            hid = base
        return f'<{tag} id="{hid}">{text}</{tag}>'
    return re.sub(r"<(h[23])>(.*?)</\1>", repl, html)


def linkify_internal_hrefs(html: str, depth: int) -> str:
    """Convert canonical '/category/slug/' hrefs (produced by resolve_wikilinks)
    into depth-correct relative paths, and tag them as wikilinks."""
    def repl(m):
        url = m.group(1)
        return f'href="{make_rel(url, depth)}" class="wikilink"'
    return re.sub(r'href="(/[a-z0-9\-/]*/?)"', repl, html)


TROOP_COLORS = {
    "infantry": "steel",
    "cavalry": "brass",
    "archer": "banner",
}

TROOP_ICONS = {
    "infantry": "&#128737;",  # shield
    "cavalry": "&#128014;",   # horse
    "archer": "&#127993;",    # bow and arrow
}


def infobox_troop_class(key: str, plain_value: str):
    if key.strip().lower() != "troop type":
        return None
    low = plain_value.lower()
    for troop, cls in TROOP_COLORS.items():
        if troop in low:
            return cls
    return None


def find_troop_type(facts):
    """Scan infobox facts for a Troop Type row; returns (troop_name, css_class) or (None, None)."""
    for key, value in facts:
        if key.strip().lower() == "troop type":
            low = value.lower()
            for troop, cls in TROOP_COLORS.items():
                if troop in low:
                    return troop.capitalize(), cls
    return None, None


def render_portrait_badge(title, css_class, icon_html=None):
    """A small original circular badge (initial + troop color) — not derived
    from any game artwork. icon_html, if given, renders inside instead of
    the initial (used for gear items)."""
    initial = esc(title.strip()[0].upper()) if title.strip() else "?"
    inner = icon_html if icon_html else initial
    return f'<div class="portrait-badge portrait-{css_class}">{inner}</div>'


def render_troop_badge(troop_name, css_class):
    icon = TROOP_ICONS.get(troop_name.lower(), "")
    return f'<span class="troop-badge troop-badge-{css_class}">{icon} {esc(troop_name)}</span>'


# ---------------------------------------------------------------------------
# Pass 1: discover every note
# ---------------------------------------------------------------------------

def discover_notes():
    notes = {}
    for folder_name, category in CATEGORY_FOLDERS.items():
        folder_path = CONTENT_DIR / folder_name
        if not folder_path.exists():
            continue
        for md_path in sorted(folder_path.rglob("*.md")):
            raw = md_path.read_text(encoding="utf-8")
            tags, aliases, is_calendar, is_gear_index, nav_pin, body = parse_frontmatter(raw)
            title, _ = split_title(body)
            key = md_path.stem
            if not title:
                title = key
            if category == "home":
                url = "/"
            elif nav_pin:
                url = f"/{slugify(key)}/"
            else:
                url = f"/{category}/{slugify(key)}/"
            notes[key] = {
                "key": key,
                "category": category,
                "title": title,
                "url": url,
                "tags": tags,
                "aliases": aliases,
                "is_calendar": is_calendar,
                "is_gear_index": is_gear_index,
                "nav_pin": nav_pin,
                "body": body,
                "source_path": md_path,
            }
    return notes


def get_generation(note):
    for t in note["tags"]:
        m = re.match(r"generation-(\d+)$", t)
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Pass 2: parse Home.md's own outline for canonical ordering
# ---------------------------------------------------------------------------

def parse_home_order(home_body: str):
    sections = {}
    heroes_by_gen = {}
    current_section = None
    current_sub = None
    link_re = re.compile(r"\[\[([^\]|#]+)")

    for line in home_body.splitlines():
        h2 = re.match(r"^##\s+(.*)", line)
        h3 = re.match(r"^###\s+(.*)", line)
        if h2:
            current_section = h2.group(1).strip()
            current_sub = None
            sections.setdefault(current_section, [])
            continue
        if h3:
            current_sub = h3.group(1).strip()
            continue
        targets = [m.group(1).strip() for m in link_re.finditer(line)]
        if not targets:
            continue
        if current_section == "Heroes" and current_sub and current_sub.startswith("Generation"):
            heroes_by_gen.setdefault(current_sub, []).extend(targets)
        elif current_section in sections:
            sections[current_section].extend(targets)
    return sections, heroes_by_gen


def ordered_keys_for_category(category, sections, notes):
    """Keys in this category, ordered per Home.md, with any stragglers
    (present in content/ but not linked from Home.md) appended alphabetically.
    Pages pinned to the top-level nav are excluded — they've moved out of
    their category listing entirely."""
    home_heading = next((h for h, c in HOME_SECTION_TO_CATEGORY.items() if c == category), None)
    preferred = sections.get(home_heading, []) if home_heading else []
    all_keys = [k for k, n in notes.items() if n["category"] == category and not n.get("nav_pin")]
    seen = set()
    ordered = []
    for k in preferred:
        if k in notes and notes[k]["category"] == category and not notes[k].get("nav_pin") and k not in seen:
            ordered.append(k)
            seen.add(k)
    leftovers = sorted([k for k in all_keys if k not in seen], key=lambda k: notes[k]["title"])
    return ordered + leftovers


# ---------------------------------------------------------------------------
# Pass 3: backlink graph
# ---------------------------------------------------------------------------

def build_backlink_graph(notes):
    graph = {k: [] for k in notes}
    for key, note in notes.items():
        for m in WIKILINK_RE.finditer(note["body"]):
            target = m.group(1).split("|")[0].split("#")[0].strip()
            if target in notes and target != key:
                graph[target].append(key)
    for k in graph:
        # de-dupe, keep order
        seen = set()
        deduped = []
        for v in graph[k]:
            if v not in seen:
                deduped.append(v)
                seen.add(v)
        graph[k] = deduped
    return graph


CATEGORY_ICONS = {
    "events": "&#9876;",         # crossed swords
    "heroes": "&#128737;",       # shield
    "gear": "&#9881;",           # gear
    "announcements": "&#128227;",# megaphone
    "reference": "&#128214;",    # open book
    "systems": "&#129517;",      # compass
}

SEAL_SVG = (
    '<svg class="seal" viewBox="0 0 40 40" aria-hidden="true">'
    '<circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" stroke-width="1.4"/>'
    '<circle cx="20" cy="20" r="12.5" fill="none" stroke="currentColor" stroke-width="1"/>'
    '<path d="M20 2 L20 7.5 M20 32.5 L20 38 M2 20 L7.5 20 M32.5 20 L38 20" '
    'stroke="currentColor" stroke-width="1.4"/>'
    '<rect x="15.5" y="15.5" width="9" height="9" fill="currentColor" transform="rotate(45 20 20)"/>'
    "</svg>"
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(notes, sections, heroes_by_gen, current_category, depth):
    is_pin_view = isinstance(current_category, str) and current_category.startswith("pin:")
    active_pin_key = current_category[4:] if is_pin_view else None
    category_for_details = None if is_pin_view else current_category

    parts = ['<div class="sidebar-inner">']
    home_active = " active" if current_category == "home" else ""
    parts.append(f'<a class="sidebar-link home-link{home_active}" href="{make_rel("/", depth)}">'
                  f'<span class="si">&#8962;</span> Home</a>')

    top_pins = [k for k, n in notes.items() if n.get("nav_pin") == "top"]
    for k in top_pins:
        n = notes[k]
        active = " active" if k == active_pin_key else ""
        parts.append(f'<a class="sidebar-link pinned-link{active}" href="{make_rel(n["url"], depth)}">'
                      f'<span class="si">&#128197;</span> {esc(n["title"])}</a>')

    parts.append('<div class="sidebar-scroll">')

    for category in CATEGORY_ORDER:
        label = CATEGORY_LABELS[category]
        icon = CATEGORY_ICONS[category]
        keys = ordered_keys_for_category(category, sections, notes)
        is_open = " open" if category == category_for_details else ""
        cat_url = make_rel(f"/{category}/", depth)
        parts.append(f'<details class="sidebar-group"{is_open}>')
        parts.append(
            f'<summary><a href="{cat_url}">{icon} {label}</a>'
            f'<span class="count">{len(keys)}</span></summary>'
        )
        if category == "heroes":
            overview_keys = sections.get("Heroes", [])
            parts.append('<div class="sidebar-subgroup-label">Overview</div><ul>')
            for k in overview_keys:
                n = notes[k]
                parts.append(f'<li><a href="{make_rel(n["url"], depth)}">{esc(n["title"])}</a></li>')
            parts.append("</ul>")
            for gen in range(1, 8):
                gen_keys = heroes_by_gen.get(f"Generation {gen}", [])
                if not gen_keys:
                    continue
                parts.append(f'<div class="sidebar-subgroup-label">Generation {gen}</div><ul>')
                for k in gen_keys:
                    n = notes.get(k)
                    if not n:
                        continue
                    parts.append(f'<li><a href="{make_rel(n["url"], depth)}">{esc(n["title"])}</a></li>')
                parts.append("</ul>")
        else:
            parts.append("<ul>")
            for k in keys:
                n = notes[k]
                parts.append(f'<li><a href="{make_rel(n["url"], depth)}">{esc(n["title"])}</a></li>')
            parts.append("</ul>")
        parts.append("</details>")

    bottom_pins = [k for k, n in notes.items() if n.get("nav_pin") == "bottom"]
    if bottom_pins:
        parts.append('<div class="sidebar-divider"></div>')
        for k in bottom_pins:
            n = notes[k]
            active = " active" if k == active_pin_key else ""
            parts.append(f'<a class="sidebar-link pinned-link{active}" href="{make_rel(n["url"], depth)}">'
                          f'<span class="si">&#8505;</span> {esc(n["title"])}</a>')

    parts.append("</div></div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Page shell (shared by every page type)
# ---------------------------------------------------------------------------

def page_shell(*, title, meta_desc, depth, content_html, sidebar_html, page_count):
    # `title` arrives already fully composed (e.g. "Bear Hunt &middot; Kingshot Wiki")
    # and already HTML-escaped by the caller.
    rel = make_rel("/", depth)
    full_title = title
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{full_title}</title>
<meta name="description" content="{meta_desc}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{make_rel('/static/css/style.css', depth)}?v={ASSET_VERSION}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='8' fill='%230F151C'/%3E%3Ccircle cx='20' cy='20' r='13' fill='none' stroke='%23C9A227' stroke-width='2'/%3E%3C/svg%3E">
<script data-goatcounter="https://{GOATCOUNTER_CODE}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>
<script>window.SITE_ROOT = "{rel}";</script>
<a class="skip-link" href="#main-content">Skip to content</a>
<header class="site-header">
  <button type="button" class="sidebar-toggle" id="sidebarToggle" aria-label="Toggle navigation" aria-expanded="false">
    <span></span><span></span><span></span>
  </button>
  <a class="wordmark" href="{rel}">
    <span class="seal-wrap">{SEAL_SVG}</span>
    <span class="wordmark-text">{SITE_NAME}<small>{SITE_TAGLINE}</small></span>
  </a>
  <div class="search-wrap">
    <input type="text" id="searchInput" placeholder="Search the vault…" autocomplete="off" aria-label="Search the wiki">
    <div class="search-results" id="searchResults" hidden></div>
  </div>
  <button type="button" class="random-btn-header" id="randomPageBtn" title="Random page" aria-label="Random page">&#127922;</button>
</header>
<div class="shell">
  <div class="sidebar-backdrop" id="sidebarBackdrop"></div>
  <nav class="sidebar" id="sidebar" aria-label="Wiki categories">
    {sidebar_html}
  </nav>
  <main class="main" id="main-content">
    {content_html}
  </main>
</div>
<footer class="site-footer">
  <p>Fan-made reference wiki for Kingshot, maintained by <strong>[ONE]OneForAll</strong>. Not affiliated with or endorsed by Kingshot's developer or publisher. Treat numbers as current best understanding — patches change things.</p>
  <p class="footer-meta">{page_count} pages in the vault &middot; Built by Hunter</p>
</footer>
<script src="{make_rel('/static/js/main.js', depth)}?v={ASSET_VERSION}"></script>
</body>
</html>"""


def breadcrumb(depth, category=None, category_label=None, current=None):
    parts = [f'<a href="{make_rel("/", depth)}">Home</a>']
    if category:
        parts.append(
            f'<span class="sep">/</span><a href="{make_rel(f"/{category}/", depth)}">{esc(category_label)}</a>'
        )
    if current:
        parts.append(f'<span class="sep">/</span><span class="current">{esc(current)}</span>')
    return f'<div class="breadcrumb">{"".join(parts)}</div>'


def tag_pills(tags, depth):
    if not tags:
        return ""
    visible = [t for t in tags if t != "kingshot"]
    if not visible:
        return ""
    q = make_rel("/search/", depth)
    pills = "".join(f'<a class="tag-pill" href="{q}?q={t}">{t}</a>' for t in visible)
    return f'<div class="tag-row">{pills}</div>'


from html import escape as esc


# ---------------------------------------------------------------------------
# Infobox
# ---------------------------------------------------------------------------

def render_infobox(facts, category_label, title, notes, depth):
    if not facts:
        return ""
    rows = []
    for key, value in facts:
        resolved = resolve_wikilinks(value, notes)
        value_html = render_inline_md(resolved)
        value_html = linkify_internal_hrefs(value_html, depth)
        plain = strip_tags(value_html)
        troop_class = infobox_troop_class(key, plain)
        dot = f'<span class="troop-dot troop-{troop_class}"></span>' if troop_class else ""
        rows.append(f'<div class="infobox-row"><dt>{esc(key)}</dt><dd>{dot}{value_html}</dd></div>')

    troop_name, troop_class = find_troop_type(facts)
    portrait_html = ""
    if troop_name:
        portrait_html = (
            '<div class="infobox-portrait-wrap">'
            f'{render_portrait_badge(title, troop_class)}'
            f'{render_troop_badge(troop_name, troop_class)}'
            "</div>"
        )

    return (
        '<aside class="infobox">'
        f'<div class="infobox-tab">{esc(category_label)}</div>'
        f'{portrait_html}'
        f'<h2 class="infobox-title">{esc(title)}</h2>'
        f'<dl class="infobox-facts">{"".join(rows)}</dl>'
        "</aside>"
    )


# ---------------------------------------------------------------------------
# See also
# ---------------------------------------------------------------------------

def render_see_also(raw_text, notes, depth):
    parts = [p.strip() for p in raw_text.split(",") if p.strip()]
    items = []
    for p in parts:
        resolved = resolve_wikilinks(p, notes)
        item_html = render_inline_md(resolved)
        item_html = linkify_internal_hrefs(item_html, depth)
        items.append(f"<li>{item_html}</li>")
    return f'<div class="see-also"><h2>See also</h2><ul class="see-also-list">{"".join(items)}</ul></div>'


# ---------------------------------------------------------------------------
# Full article body pipeline
# ---------------------------------------------------------------------------

CALENDAR_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?")


def parse_calendar_date(cell_text: str):
    """Pull a YYYY-MM-DD[ HH:MM] date out of a table cell. Returns
    (date_str, time_str) or (None, None) if nothing parseable is found —
    e.g. a still-unfilled '_TBD_' placeholder."""
    m = CALENDAR_DATE_RE.search(cell_text)
    if not m:
        return None, None
    y, mo, d, h, mi = m.groups()
    try:
        import datetime as _dt
        _dt.date(int(y), int(mo), int(d))
    except ValueError:
        return None, None
    return f"{y}-{mo}-{d}", (f"{h}:{mi}" if h else None)


def extract_first_table(md_text: str):
    """Find the first GFM pipe-table in raw markdown. Returns
    (header_cells, [row_cells, ...]) or (None, []) if there isn't one."""
    lines = md_text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if i + 1 >= len(lines):
            break
        sep = lines[i + 1].strip()
        if not re.match(r"^\|?[\s:|-]+\|?$", sep) or "-" not in sep:
            continue
        header = [c.strip() for c in stripped.strip("|").split("|")]
        rows = []
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
            j += 1
        return header, rows
    return None, []


def extract_calendar_entries(body_md: str, notes: dict):
    """Turn the note's first table into a list of calendar entry dicts,
    matching columns by header name so the table stays human-editable."""
    header, rows = extract_first_table(body_md)
    if not header:
        return []

    def find_col(*keywords):
        for idx, h in enumerate(header):
            hl = h.lower()
            if any(k in hl for k in keywords):
                return idx
        return None

    date_idx = find_col("date")
    title_idx = find_col("milestone", "event", "title")
    cat_idx = find_col("category", "type")
    notes_idx = find_col("notes")

    def cell(row, idx):
        return row[idx] if idx is not None and idx < len(row) else ""

    entries = []
    for row in rows:
        date_str, time_str = parse_calendar_date(cell(row, date_idx))
        title_resolved = resolve_wikilinks(cell(row, title_idx), notes)
        title_plain = re.sub(r"[*_`]", "", strip_tags(render_inline_md(title_resolved))).strip()
        category = cell(row, cat_idx).strip()
        notes_cell = cell(row, notes_idx)
        notes_html = render_inline_md(resolve_wikilinks(notes_cell, notes)) if notes_cell.strip() else ""
        if not title_plain:
            continue
        entries.append({
            "date": date_str, "time": time_str,
            "title": title_plain, "category": category, "notes": notes_html,
        })
    return entries


_CAL_WIDGET_COUNTER = [0]


def render_calendar_widget(entries, depth):
    idx = _CAL_WIDGET_COUNTER[0]
    _CAL_WIDGET_COUNTER[0] += 1
    fixed_entries = []
    for e in entries:
        e = dict(e)
        if e["notes"]:
            e["notes"] = linkify_internal_hrefs(e["notes"], depth)
        fixed_entries.append(e)
    data_json = json.dumps(fixed_entries).replace("</", "<\\/")
    unscheduled_count = sum(1 for e in fixed_entries if not e["date"])
    plural = "s" if unscheduled_count != 1 else ""
    return f"""
    <div class="milestone-calendar" id="mcal-{idx}">
      <div class="mc-header">
        <button type="button" class="mc-nav mc-prev" aria-label="Previous month">&#8592;</button>
        <div class="mc-month-label"></div>
        <button type="button" class="mc-nav mc-next" aria-label="Next month">&#8594;</button>
      </div>
      <div class="mc-weekdays">
        <div>Sun</div><div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div>
      </div>
      <div class="mc-grid"></div>
      <div class="mc-footer-row">
        <button type="button" class="mc-today-btn">Jump to today</button>
        <span class="mc-unscheduled-note">{unscheduled_count} milestone{plural} not yet scheduled</span>
      </div>
      <div class="mc-detail" hidden></div>
      <script type="application/json" class="mc-data">{data_json}</script>
    </div>
    """


STAR_MULTIPLIERS = {1: 0.50, 2: 0.60, 3: 0.70, 4: 0.80, 5: 0.90, 6: 1.00}


def extract_hero_base_stats(body_md: str):
    """Look for a 'Stat | Value' table (Attack/Defense/Health rows) on a hero
    page and return {'Attack': int, 'Defense': int, 'Health': int} or None."""
    header, rows = extract_first_table(body_md)
    if not header:
        return None
    hl = [h.lower() for h in header]
    if "stat" not in hl or "value" not in hl:
        return None
    stat_idx, val_idx = hl.index("stat"), hl.index("value")
    stats = {}
    for row in rows:
        if len(row) <= max(stat_idx, val_idx):
            continue
        key = row[stat_idx].strip()
        try:
            val = int(re.sub(r"[^\d]", "", row[val_idx]))
        except ValueError:
            continue
        if key in ("Attack", "Defense", "Health"):
            stats[key] = val
    if not all(k in stats for k in ("Attack", "Defense", "Health")):
        return None
    return stats


_HERO_WIDGET_COUNTER = [0]


def render_hero_stat_widget(base_stats):
    idx = _HERO_WIDGET_COUNTER[0]
    _HERO_WIDGET_COUNTER[0] += 1
    data_json = json.dumps({"base": base_stats, "multipliers": STAR_MULTIPLIERS}).replace("</", "<\\/")
    return f"""
    <div class="hero-stat-widget" id="hsw-{idx}">
      <div class="hsw-header">
        <span class="hsw-label">Star Level</span>
        <span class="hsw-star-value">6&#9733;</span>
      </div>
      <input type="range" min="1" max="6" step="1" value="6" class="hsw-slider">
      <div class="hsw-stats">
        <div class="hsw-stat"><span class="hsw-stat-label">Attack</span><span class="hsw-stat-value" data-stat="Attack"></span></div>
        <div class="hsw-stat"><span class="hsw-stat-label">Defense</span><span class="hsw-stat-value" data-stat="Defense"></span></div>
        <div class="hsw-stat"><span class="hsw-stat-label">Health</span><span class="hsw-stat-value" data-stat="Health"></span></div>
      </div>
      <p class="hsw-note">Conquest stats at 6&#9733; sourced from community data (kingshot.net) — verify against your own hero screen, since fan-site numbers can drift after patches.</p>
      <script type="application/json" class="hsw-data">{data_json}</script>
    </div>
    """


def extract_gear_pieces(body_md: str):
    """Parse the 'Piece | Troop Type | Stat | At +0 | At +100' table into a
    list of gear piece dicts."""
    header, rows = extract_first_table(body_md)
    if not header:
        return []
    hl = [h.lower() for h in header]
    needed = ["piece", "troop type", "stat", "at +0", "at +100"]
    if not all(n in hl for n in needed):
        return []
    idx = {n: hl.index(n) for n in needed}
    pieces = []
    for row in rows:
        if len(row) < len(header):
            continue
        try:
            start = float(row[idx["at +0"]].strip().rstrip("%"))
            end = float(row[idx["at +100"]].strip().rstrip("%"))
        except ValueError:
            continue
        troop = row[idx["troop type"]].strip()
        troop_class = TROOP_COLORS.get(troop.lower(), "")
        pieces.append({
            "name": f'{troop} {row[idx["piece"]].strip()}',
            "troop": troop,
            "troopClass": troop_class,
            "stat": row[idx["stat"]].strip(),
            "start": start,
            "end": end,
        })
    return pieces


def render_gear_widget(pieces):
    if not pieces:
        return ""
    data_json = json.dumps(pieces).replace("</", "<\\/")
    options = "".join(f'<option value="{i}">{esc(p["name"])} ({esc(p["stat"])})</option>' for i, p in enumerate(pieces))
    return f"""
    <div class="gear-widget">
      <div class="gw-row">
        <select class="gw-piece-select">{options}</select>
      </div>
      <div class="gw-row gw-badge-row">
        <span class="gw-troop-badge"></span>
        <span class="gw-level-wrap"><span class="hsw-label">Enhancement Level</span> <span class="gw-level-value">100</span></span>
      </div>
      <input type="range" min="0" max="100" step="1" value="100" class="gw-slider">
      <div class="gw-output">
        <span class="hsw-stat-label gw-output-label"></span>
        <span class="gw-output-value"></span>
      </div>
      <p class="hsw-note">Mythic tier only (level 0–100), linearly interpolated between the documented endpoints. Red tier (101–200) isn't modeled — see the warning above.</p>
      <script type="application/json" class="gw-data">{data_json}</script>
    </div>
    """


def render_note_body(note, notes, depth):
    _, rest = split_title(note["body"])
    facts, rest = extract_infobox_facts(rest)
    see_also_raw, rest = extract_see_also(rest)
    raw_body_for_summary = rest

    resolved = resolve_wikilinks(rest, notes)
    stripped, callouts = extract_callouts(resolved)
    body_html = markdown.markdown(stripped, extensions=MD_EXTENSIONS)

    for idx, (ctype, ctitle, cbody) in enumerate(callouts):
        callout_html = render_callout(ctype, ctitle, cbody, notes)
        body_html = re.sub(rf"<p>@@CALLOUT{idx}@@</p>", lambda _m: callout_html, body_html)

    body_html = process_task_lists(body_html)
    body_html = add_copy_buttons(body_html)
    body_html = add_heading_ids(body_html)
    body_html = linkify_internal_hrefs(body_html, depth)

    if note.get("is_calendar"):
        entries = extract_calendar_entries(raw_body_for_summary, notes)
        if entries:
            body_html = render_calendar_widget(entries, depth) + body_html

    if note["category"] == "heroes":
        base_stats = extract_hero_base_stats(raw_body_for_summary)
        if base_stats:
            body_html = render_hero_stat_widget(base_stats) + body_html

    if note.get("is_gear_index"):
        pieces = extract_gear_pieces(raw_body_for_summary)
        if pieces:
            body_html = render_gear_widget(pieces) + body_html

    infobox_html = render_infobox(
        facts, CATEGORY_LABELS.get(note["category"], ""), note["title"], notes, depth
    )

    see_also_html = render_see_also(see_also_raw, notes, depth) if see_also_raw else ""

    return infobox_html, body_html, see_also_html, raw_body_for_summary


# ---------------------------------------------------------------------------
# Category index page
# ---------------------------------------------------------------------------

def render_category_index(category, notes, sections, heroes_by_gen, depth):
    label = CATEGORY_LABELS[category]
    desc = CATEGORY_DESCRIPTIONS[category]
    keys = ordered_keys_for_category(category, sections, notes)

    out = [breadcrumb(depth, current=label)]
    out.append(f'<h1><span class="h1-icon">{CATEGORY_ICONS[category]}</span> {esc(label)}</h1>')
    out.append(f'<p class="category-desc">{esc(desc)}</p>')

    if category == "heroes":
        overview_keys = sections.get("Heroes", [])
        out.append('<h2 class="section-label">Overview &amp; Guides</h2>')
        out.append('<ul class="page-grid">')
        for k in overview_keys:
            n = notes[k]
            out.append(f'<li><a href="{make_rel(n["url"], depth)}">{esc(n["title"])}</a></li>')
        out.append("</ul>")
        for gen in range(1, 8):
            gen_keys = heroes_by_gen.get(f"Generation {gen}", [])
            if not gen_keys:
                continue
            out.append(f'<h2 class="section-label">Generation {gen}</h2>')
            out.append('<ul class="page-grid hero-grid">')
            for k in gen_keys:
                n = notes.get(k)
                if not n:
                    continue
                out.append(f'<li><a href="{make_rel(n["url"], depth)}">{esc(n["title"])}</a></li>')
            out.append("</ul>")
    else:
        out.append(f'<p class="page-count-label">{len(keys)} pages</p>')
        out.append('<ul class="page-grid">')
        for k in keys:
            n = notes[k]
            out.append(f'<li><a href="{make_rel(n["url"], depth)}">{esc(n["title"])}</a></li>')
        out.append("</ul>")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

def render_home(notes, sections, heroes_by_gen, depth):
    cards = []
    for category in CATEGORY_ORDER:
        keys = ordered_keys_for_category(category, sections, notes)
        label = CATEGORY_LABELS[category]
        desc = CATEGORY_DESCRIPTIONS[category]
        icon = CATEGORY_ICONS[category]
        url = make_rel(f"/{category}/", depth)
        cards.append(
            f'<a class="dossier-card" href="{url}">'
            f'<span class="dossier-tab"></span>'
            f'<span class="dossier-icon">{icon}</span>'
            f"<h3>{esc(label)}</h3>"
            f"<p>{esc(desc)}</p>"
            f'<span class="dossier-count">{len(keys)} pages</span>'
            "</a>"
        )

    r4_callout = render_callout(
        "warning",
        "Keep this updated",
        'Kingshot patches events and hero balance regularly. Treat numbers in here as "current '
        'best understanding," and correct notes as your alliance discovers patch changes.',
        notes,
    )

    r4_text = (
        "New to the alliance? Start with [[Beginner's Guide]], then read "
        "[[Hero Overview and Roles]] and [[Hero Gear Guide]] before anything else — that's the "
        "foundation almost everything else builds on. When an event is coming up, open its page "
        "and skim it before the window opens. If you're an officer, the matching Announcement "
        "page is ready to paste straight into alliance chat. Keep "
        "[[Event Calendar and 4-Week Cycle]] pinned so you know what's coming next."
    )
    r4_html = markdown.markdown(resolve_wikilinks(r4_text, notes), extensions=MD_EXTENSIONS)
    r4_html = linkify_internal_hrefs(r4_html, depth)

    wiki_tip_html = (
        "<p>Use the search box at the top of any page to jump straight to a hero, event, or guide "
        'by name or tag. Every article ends with a <strong>&ldquo;What links here&rdquo;</strong> '
        "list, so you can trace how systems connect the same way Obsidian's graph view did. Actual "
        "game artwork isn't included here since it can't be sourced without infringing the "
        "developer's copyright.</p>"
    )

    return f"""
    <div class="home-hero">
      <p class="home-eyebrow">Field Manual &middot; {len(notes) - 1} pages on record</p>
      <h1>Kingshot Alliance<br>Knowledge Vault</h1>
      <p class="home-intro">The one-stop vault for learning Kingshot deeply — for every
      [ONE]OneForAll member, not just officers. Study it yourself, help a new recruit catch up,
      or copy pieces straight into alliance chat.</p>
    </div>
    <div class="dossier-grid">
      {"".join(cards)}
    </div>
    <div class="home-sections">
      <section>
        <h2>How to use this vault</h2>
        {r4_html}
        {r4_callout}
      </section>
      <section>
        <h2>Using this as your own wiki</h2>
        {wiki_tip_html}
      </section>
    </div>
    """


# ---------------------------------------------------------------------------
# Search page (client-rendered — see static/js/main.js)
# ---------------------------------------------------------------------------

def render_search_page(depth):
    return f"""
    {breadcrumb(depth, current="Search")}
    <h1>Search the vault</h1>
    <p id="searchPageHint">Type below, or use the search box at the top of any page.</p>
    <input type="text" id="searchPageInput" placeholder="Search titles and tags…" autocomplete="off">
    <ul class="page-grid" id="searchPageResults"></ul>
    """


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main():
    print("Discovering notes...")
    notes = discover_notes()
    print(f"  found {len(notes)} notes")

    home_note = notes["Home"]
    sections, heroes_by_gen = parse_home_order(home_note["body"])
    backlink_graph = build_backlink_graph(notes)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    (OUTPUT_DIR / ".nojekyll").write_text("")

    shutil.copytree(STATIC_SRC, OUTPUT_DIR / "static")

    page_count = len(notes) - 1

    def write_page(url, title, meta_desc, depth, content_html, current_category):
        sidebar_html = render_sidebar(notes, sections, heroes_by_gen, current_category, depth)
        full_title = title if title == SITE_NAME else f"{esc(title)} &middot; {SITE_NAME}"
        html_out = page_shell(
            title=full_title,
            meta_desc=esc(meta_desc),
            depth=depth,
            content_html=content_html,
            sidebar_html=sidebar_html,
            page_count=page_count,
        )
        out_path = (OUTPUT_DIR / "index.html") if url == "/" else (OUTPUT_DIR / url.strip("/") / "index.html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_out, encoding="utf-8")

    print("Rendering home page...")
    home_html = render_home(notes, sections, heroes_by_gen, depth=0)
    write_page(
        "/", SITE_NAME,
        "A community wiki for Kingshot: every event, hero, gear guide, and alliance strategy note in one place.",
        0, home_html, "home",
    )

    for category in CATEGORY_ORDER:
        print(f"Rendering /{category}/ index...")
        content = render_category_index(category, notes, sections, heroes_by_gen, depth=1)
        write_page(f"/{category}/", CATEGORY_LABELS[category], CATEGORY_DESCRIPTIONS[category], 1, content, category)

    print("Rendering /search/...")
    write_page("/search/", "Search", "Search the Kingshot wiki.", 1, render_search_page(1), None)

    print("Rendering articles...")
    search_index = []
    for key, note in notes.items():
        if note["category"] == "home":
            continue
        depth = depth_of(note["url"])
        infobox_html, body_html, see_also_html, raw_body_for_summary = render_note_body(note, notes, depth)

        backlinks = [b for b in backlink_graph.get(key, []) if b != "Home"]
        backlinks_html = ""
        if backlinks:
            items = "".join(
                f'<li><a href="{make_rel(notes[b]["url"], depth)}">{esc(notes[b]["title"])}</a></li>'
                for b in backlinks
            )
            backlinks_html = (
                f'<details class="backlinks"><summary>What links here ({len(backlinks)})</summary>'
                f"<ul>{items}</ul></details>"
            )

        cat_label = CATEGORY_LABELS[note["category"]]
        if note.get("nav_pin"):
            content = breadcrumb(depth, current=note["title"])
        else:
            content = breadcrumb(depth, note["category"], cat_label, note["title"])
        content += '<article class="article">'
        content += infobox_html
        content += f"<h1>{esc(note['title'])}</h1>"
        content += tag_pills(note["tags"], depth)
        content += f'<div class="article-body">{body_html}</div>'
        content += see_also_html
        content += backlinks_html
        content += "</article>"

        meta_desc = make_meta_description(raw_body_for_summary, note["title"])

        nav_key = f"pin:{key}" if note.get("nav_pin") else note["category"]
        write_page(note["url"], note["title"], meta_desc, depth, content, nav_key)

        search_index.append({
            "title": note["title"],
            "url": note["url"],
            "category": note["category"],
            "categoryLabel": cat_label,
            "tags": [t for t in note["tags"] if t != "kingshot"],
        })

    (OUTPUT_DIR / "search-index.json").write_text(json.dumps(search_index), encoding="utf-8")

    print(f"\nDone — {page_count} articles, {len(CATEGORY_ORDER)} category pages, home, and search built.")
    print(f"Output written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
