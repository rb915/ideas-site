#!/usr/bin/env python3
"""
Fetch ideas from a Notion database and generate a static HTML page
with collapsible themed sections.

Requires env vars:
  NOTION_TOKEN       — Notion integration token
  NOTION_DATABASE_ID — UUID of the database (with or without dashes)

Output: ./public/index.html
"""
import os
import re
import html
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
NOTION_VERSION = "2022-06-28"

if not NOTION_TOKEN or not NOTION_DATABASE_ID:
    sys.exit("ERROR: set NOTION_TOKEN and NOTION_DATABASE_ID env vars")


# ---------------------------------------------------------------------------
# Notion API helpers
# ---------------------------------------------------------------------------
def notion_request(method, path, body=None):
    url = f"https://api.notion.com/v1{path}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {path}: {e.read().decode()}", file=sys.stderr)
        raise


def query_database(db_id):
    """Paginate through all rows of the database."""
    results = []
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = notion_request("POST", f"/databases/{db_id}/query", body)
        results.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return results


def get_page_blocks(page_id):
    """Fetch all block children of a page (paginated)."""
    blocks = []
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = notion_request("GET", path)
        blocks.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return blocks


# ---------------------------------------------------------------------------
# Extract plaintext-ish content from Notion property + block structures
# ---------------------------------------------------------------------------
def rich_text_to_md(rt_array):
    """Convert Notion rich_text array into lightweight markdown."""
    parts = []
    for rt in rt_array or []:
        text = rt.get("plain_text", "")
        ann = rt.get("annotations", {})
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if ann.get("code"):
            text = f"`{text}`"
        parts.append(text)
    return "".join(parts)


def blocks_to_md(blocks):
    """Convert Notion blocks into simple markdown text for our renderer."""
    lines = []
    for block in blocks:
        btype = block.get("type")
        bdata = block.get(btype, {})
        rt = bdata.get("rich_text", [])
        text = rich_text_to_md(rt)

        if btype == "paragraph":
            lines.append(text)
            lines.append("")
        elif btype == "heading_1":
            lines.append(f"# {text}")
            lines.append("")
        elif btype == "heading_2":
            lines.append(f"## {text}")
            lines.append("")
        elif btype == "heading_3":
            lines.append(f"### {text}")
            lines.append("")
        elif btype == "bulleted_list_item" or btype == "numbered_list_item":
            lines.append(f"• {text}")
        elif btype == "to_do":
            box = "[x]" if bdata.get("checked") else "[ ]"
            lines.append(f"• {box} {text}")
        elif btype == "quote":
            lines.append(f"> {text}")
            lines.append("")
        elif btype == "divider":
            lines.append("---")
        elif btype == "code":
            lines.append(f"```\n{text}\n```")
        elif btype == "callout":
            lines.append(text)
            lines.append("")
        else:
            if text:
                lines.append(text)
    return "\n".join(lines).strip()


def extract_property(props, name):
    """Pull a simple string value out of a Notion property."""
    p = props.get(name)
    if not p:
        return ""
    ptype = p.get("type")
    if ptype == "title":
        return rich_text_to_md(p.get("title", []))
    if ptype == "rich_text":
        return rich_text_to_md(p.get("rich_text", []))
    if ptype == "select":
        return (p.get("select") or {}).get("name", "")
    if ptype == "multi_select":
        return ", ".join(t["name"] for t in p.get("multi_select", []))
    if ptype == "date":
        d = p.get("date") or {}
        return d.get("start", "")
    if ptype == "created_time":
        return p.get("created_time", "")[:10]
    if ptype == "last_edited_time":
        return p.get("last_edited_time", "")[:10]
    if ptype == "number":
        n = p.get("number")
        return str(n) if n is not None else ""
    if ptype == "checkbox":
        return "✓" if p.get("checkbox") else ""
    if ptype == "url":
        return p.get("url", "") or ""
    return ""


# ---------------------------------------------------------------------------
# Categorization (same logic we used before)
# ---------------------------------------------------------------------------
def categorize(title, source, content):
    t = (title or "").lower()
    source = (source or "").lower()
    if source == "story-bank":
        if any(k in t for k in ["poker", "vegas", "$3,000 to become", "fidget"]):
            return "poker_vegas"
        if any(k in t for k in ["give", "gave away", "wow budget", "teachers", "la fires", "uber eats", "poker chip", "bonuses"]):
            return "giving"
        if any(k in t for k in ["raise", "vc", "never raised", "$100 million", "$180", "fat pitch", "10,000 hours", "agency", "michigan state", "broke", "20 years", "kicked out"]):
            return "origin"
        if any(k in t for k in ["confidence", "shirt", "t-shirt", "feel good", "apparel", "perfect model"]):
            return "brand_customer"
        if any(k in t for k in ["performance", "negotiate", "raises", "ben", "smart", "curious"]):
            return "team_ops"
        return "origin"
    if "$3k" in t or "$3,000" in t or "270m" in t or "270 million" in t or "without vc" in t or "blueprint" in t:
        return "brand_270m"
    if any(k in t for k in ["poker", "vegas", "bluff", "fidget"]):
        return "poker_vegas"
    if any(k in t for k in ["give", "gave away", "gift with purchase", "free", "give to sell"]):
        return "giving"
    if any(k in t for k in ["negotiat", "$40m", "$40–50", "$40-50", "$50m"]):
        return "negotiation"
    if any(k in t for k in ["constraint", "10-minute", "focus", "delegate"]):
        return "constraints"
    if "8/10" in t or "7/10" in t or "7 out of 10" in t or "8 out of 10" in t or "whole market" in t or "whole game" in t:
        return "eight_ten"
    if any(k in t for k in ["product-market", "marketing", "ad strategy"]):
        return "pmf_marketing"
    if any(k in t for k in ["confidence", "women", "coffee shop", "customer"]):
        return "brand_customer"
    if any(k in t for k in ["msu", "dropped out", "dropout", "risk", "mistake", "19-year-old"]):
        return "dropout_risk"
    if any(k in t for k in ["sold my agency", "robot", "ben"]):
        return "team_ops"
    return "other"


SECTIONS = [
    ("brand_270m", "The $270M Brand Story"),
    ("poker_vegas", "Poker & Vegas Lessons"),
    ("giving", "Giving & Generosity Strategy"),
    ("negotiation", "Negotiation & Money Saved"),
    ("constraints", "Constraints & Focus"),
    ("eight_ten", "The 8/10 Philosophy"),
    ("pmf_marketing", "Product-Market Fit & Marketing"),
    ("brand_customer", "Customers & Brand Identity"),
    ("dropout_risk", "College, Risk & Mistakes"),
    ("team_ops", "Team, Culture & Operations"),
    ("origin", "Origin Stories & Backstory"),
    ("other", "Other Ideas"),
]


# ---------------------------------------------------------------------------
# Markdown-ish → HTML renderer (same as before)
# ---------------------------------------------------------------------------
LABEL_WORDS = {
    "TITLE", "HOOK", "KEY POINTS", "PLATFORM", "CTA", "HASHTAGS", "CONTENT",
    "Hook", "Key Points", "Platform", "CTA", "Title",
    "TITLE OPTIONS", "VISUAL DIRECTION", "Visual Direction",
}


def inline_format(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", s)
    return s


def render_content(raw):
    if not raw or not raw.strip():
        return '<p class="empty-note">No content yet — just a title.</p>'

    text = html.escape(raw.strip())
    lines = text.split("\n")
    out = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        if stripped == "---":
            close_list()
            out.append("<hr>")
            continue
        h_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if h_match:
            close_list()
            level = min(len(h_match.group(1)) + 2, 6)
            out.append(f"<h{level}>{inline_format(h_match.group(2))}</h{level}>")
            continue
        if re.match(r"^[•\-\*]\s+", stripped):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^[•\-\*]\s+", "", stripped)
            out.append(f"<li>{inline_format(item)}</li>")
            continue
        label_match = re.match(r"^([A-Z][A-Z\s/]{1,25}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*):\s*(.*)$", stripped)
        if label_match and label_match.group(1).strip() in LABEL_WORDS:
            close_list()
            label = label_match.group(1).strip()
            rest = label_match.group(2).strip()
            if rest:
                out.append(f'<p><span class="label">{label}</span> {inline_format(rest)}</p>')
            else:
                out.append(f'<p class="label-only"><span class="label">{label}</span></p>')
            continue
        close_list()
        out.append(f"<p>{inline_format(stripped)}</p>")
    close_list()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Page template
# ---------------------------------------------------------------------------
PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
<title>Content Ideas</title>
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#faf7f2">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Ideas">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..900;1,9..144,300..900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #faf7f2; --bg-elevated: #fffdf8; --bg-nested: #f5f0e6;
    --ink: #1a1814; --ink-soft: #5a544a; --ink-muted: #8a8478;
    --accent: #c8472e; --accent-soft: #f4e4dc;
    --rule: #e8e2d5; --rule-strong: #d4ccba;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
  body {
    font-family: 'Fraunces', Georgia, serif;
    font-optical-sizing: auto; background: var(--bg); color: var(--ink);
    line-height: 1.55; padding: 24px 18px 80px;
    max-width: 760px; margin: 0 auto; -webkit-font-smoothing: antialiased;
  }
  header { padding: 8px 0 28px; border-bottom: 1px solid var(--rule); margin-bottom: 24px; }
  .eyebrow { font-family: 'JetBrains Mono', monospace; font-size: 11px;
    letter-spacing: 0.18em; text-transform: uppercase; color: var(--accent);
    margin-bottom: 12px; font-weight: 500; }
  h1 { font-family: 'Fraunces', serif; font-weight: 300;
    font-size: clamp(32px, 7vw, 44px); line-height: 1.05;
    letter-spacing: -0.02em; font-variation-settings: "opsz" 96; }
  h1 em { font-style: italic; font-weight: 400; color: var(--accent); }
  .subtitle { font-size: 15px; color: var(--ink-soft); margin-top: 14px; font-style: italic; }
  .meta { font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--ink-muted); margin-top: 18px; display: flex; gap: 14px; flex-wrap: wrap; }
  .meta span::before { content: "— "; }
  .meta span:first-child::before { content: ""; }
  .controls { display: flex; gap: 8px; margin-bottom: 20px;
    font-family: 'JetBrains Mono', monospace; font-size: 11px; flex-wrap: wrap; }
  .controls button { background: transparent; border: 1px solid var(--rule-strong);
    color: var(--ink-soft); padding: 8px 14px; border-radius: 6px; cursor: pointer;
    letter-spacing: 0.08em; text-transform: uppercase; font-family: inherit;
    transition: all 0.15s ease; -webkit-tap-highlight-color: transparent; }
  .controls button:hover, .controls button:active {
    background: var(--ink); color: var(--bg); border-color: var(--ink); }
  .search { flex: 1; min-width: 140px; background: var(--bg-elevated);
    border: 1px solid var(--rule-strong); color: var(--ink);
    padding: 8px 14px; border-radius: 6px;
    font-family: 'JetBrains Mono', monospace; font-size: 12px; }
  .search:focus { outline: none; border-color: var(--accent); }
  body > details { background: var(--bg-elevated); border: 1px solid var(--rule);
    border-radius: 10px; margin-bottom: 12px; overflow: hidden;
    transition: border-color 0.2s ease, box-shadow 0.2s ease; }
  body > details[open] { border-color: var(--rule-strong);
    box-shadow: 0 2px 8px rgba(26, 24, 20, 0.04); }
  body > details > summary { cursor: pointer; padding: 18px 20px; list-style: none;
    display: flex; align-items: flex-start; gap: 14px; user-select: none;
    -webkit-tap-highlight-color: transparent; }
  summary::-webkit-details-marker { display: none; }
  .section-num { font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--accent); font-weight: 500; padding-top: 4px; min-width: 28px; }
  .section-title { flex: 1; font-size: 18px; line-height: 1.25;
    font-weight: 400; letter-spacing: -0.01em; }
  .section-count { font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--ink-muted); padding-top: 5px; }
  .chevron { width: 12px; height: 12px; margin-top: 6px; flex-shrink: 0;
    transition: transform 0.25s ease; color: var(--ink-muted); }
  .chevron-sm { width: 10px; height: 10px; margin-top: 5px; flex-shrink: 0;
    transition: transform 0.25s ease; color: var(--ink-muted); }
  body > details[open] > summary .chevron { transform: rotate(90deg); }
  .idea-details[open] .chevron-sm { transform: rotate(90deg); }
  .items { padding: 6px 14px 14px; border-top: 1px solid var(--rule); }
  .idea { border-bottom: 1px solid var(--rule); }
  .idea:last-child { border-bottom: none; }
  .idea-summary { cursor: pointer; padding: 14px 6px; list-style: none;
    display: flex; align-items: flex-start; gap: 12px;
    -webkit-tap-highlight-color: transparent; user-select: none; }
  .idea-title { flex: 1; font-size: 15.5px; line-height: 1.35;
    font-weight: 400; color: var(--ink); letter-spacing: -0.005em; }
  .idea-details[open] .idea-title { color: var(--accent); font-weight: 500; }
  .item-meta { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 6px 10px; }
  .tag { font-family: 'JetBrains Mono', monospace; font-size: 10px;
    padding: 3px 7px; border-radius: 4px; letter-spacing: 0.04em;
    background: var(--bg-nested); color: var(--ink-soft); border: 1px solid var(--rule); }
  .tag-slot { color: var(--accent); border-color: var(--accent-soft); background: var(--accent-soft); }
  .breaking-section { border-left: 4px solid var(--accent) !important; }
  .breaking-section > summary .section-num { color: var(--accent); font-size: 14px; }
  .idea-content { padding: 4px 10px 20px 10px; font-size: 15px;
    line-height: 1.6; color: var(--ink-soft); }
  .idea-content p { margin-bottom: 10px; }
  .idea-content p:last-child { margin-bottom: 0; }
  .idea-content h3, .idea-content h4, .idea-content h5, .idea-content h6 {
    font-family: 'Fraunces', serif; font-weight: 500; font-size: 15.5px;
    color: var(--ink); margin: 14px 0 8px; letter-spacing: -0.01em; }
  .idea-content ul { list-style: none; padding: 0; margin: 8px 0 12px; }
  .idea-content li { position: relative; padding-left: 18px; margin-bottom: 7px; }
  .idea-content li::before { content: "—"; position: absolute; left: 0; color: var(--accent); }
  .idea-content strong { color: var(--ink); font-weight: 600; }
  .idea-content em { font-style: italic; }
  .idea-content hr { border: none; border-top: 1px solid var(--rule); margin: 14px 0; }
  .idea-content .label { font-family: 'JetBrains Mono', monospace; font-size: 10px;
    letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent);
    margin-right: 6px; font-weight: 500; }
  .idea-content .label-only { margin-top: 10px; margin-bottom: 4px; }
  .empty-note { font-style: italic; color: var(--ink-muted); font-size: 14px; }
  footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--rule);
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--ink-muted); text-align: center; letter-spacing: 0.05em; }
  .hidden { display: none !important; }
  @media (max-width: 480px) {
    body { padding: 20px 14px 60px; }
    .items { padding-left: 10px; padding-right: 10px; }
    body > details > summary { padding: 16px 16px; }
    .section-title { font-size: 16.5px; }
    .idea-title { font-size: 15px; }
    .idea-content { font-size: 14.5px; }
  }
</style>
</head>
<body>

<header>
  <div class="eyebrow">Content Library</div>
  <h1>Ideas, <em>organized</em>.</h1>
  <p class="subtitle">Tap a topic to expand. Tap an idea to read the full content.</p>
  <div class="meta">
    <span>__TOTAL__ ideas</span>
    <span>__WITH_CONTENT__ with content</span>
    <span>__SECTION_COUNT__ themes</span>
    <span>Updated __UPDATED__</span>
  </div>
</header>

<div class="controls">
  <input type="search" class="search" id="search" placeholder="Search ideas…" aria-label="Search ideas">
  <button onclick="toggleAll(true)">Expand all</button>
  <button onclick="toggleAll(false)">Collapse all</button>
</div>

__SECTIONS__

<footer>
  END OF LIBRARY · __TOTAL__ IDEAS
</footer>

<script>
  function toggleAll(open) {
    document.querySelectorAll('body > details').forEach(d => d.open = open);
  }
  const search = document.getElementById('search');
  search.addEventListener('input', e => {
    const q = e.target.value.trim().toLowerCase();
    document.querySelectorAll('body > details').forEach(section => {
      const ideas = section.querySelectorAll('.idea');
      let anyMatch = false;
      ideas.forEach(idea => {
        const text = idea.textContent.toLowerCase();
        const match = !q || text.includes(q);
        idea.classList.toggle('hidden', !match);
        if (match) anyMatch = true;
      });
      section.classList.toggle('hidden', !!q && !anyMatch);
      if (q && anyMatch) section.open = true;
    });
  });
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"Fetching database {NOTION_DATABASE_ID}...")
    pages = query_database(NOTION_DATABASE_ID)
    print(f"Got {len(pages)} pages")

    # Grab relevant property keys from the first page schema
    rows = []
    for i, page in enumerate(pages):
        props = page.get("properties", {})

        # Title is whichever property has type=title
        title = ""
        for name, p in props.items():
            if p.get("type") == "title":
                title = rich_text_to_md(p.get("title", []))
                break

        slot = extract_property(props, "Slot")
        source = extract_property(props, "Source")
        created = extract_property(props, "Created") or page.get("created_time", "")[:10]

        # Fetch the page body content
        print(f"  [{i+1}/{len(pages)}] {title[:60]}")
        try:
            blocks = get_page_blocks(page["id"])
            body_md = blocks_to_md(blocks)
        except Exception as e:
            print(f"    (failed to fetch body: {e})")
            body_md = ""

        # Also check for a "Content" rich_text property in case it's stored there
        content_prop = extract_property(props, "Content")
        content = body_md or content_prop

        rows.append({
            "title": title,
            "content": content,
            "slot": slot,
            "source": source,
            "created": created,
        })
# ---- Breaking News (sourced from Notion) ----
    # An item lands in Breaking News if ANY of these are true:
    #   1. Source is "OpenClaw Breaking News"
   
    # Group by theme (skip Breaking News items so they only appear in their own section)
    grouped = {key: [] for key, _ in SECTIONS}
    for r in rows:
        
            continue
        key = categorize(r["title"], r["source"], r["content"])
    grouped[key].append(r)

    # Build section HTML
    section_html_parts = []
    section_num = 0
    for key, name in SECTIONS:
        items = grouped[key]
        if not items:
            continue
        section_num += 1
        section_html_parts.append(f'''
<details>
  <summary>
    <span class="section-num">{section_num:02d}</span>
    <span class="section-title">{html.escape(name)}</span>
    <span class="section-count">{len(items)}</span>
    <svg class="chevron" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2 L8 6 L4 10"/></svg>
  </summary>
  <div class="items">''')

        for r in items:
            title = html.escape(r["title"].strip())
            slot = html.escape(r["slot"].strip())
            source = html.escape(r["source"].strip())
            created = html.escape(r["created"].strip())
            content_html = render_content(r["content"])
            meta_bits = []
            if slot: meta_bits.append(f'<span class="tag tag-slot">{slot}</span>')
            if source: meta_bits.append(f'<span class="tag tag-source">{source}</span>')
            if created: meta_bits.append(f'<span class="tag tag-date">{created}</span>')
            meta_html = ('<div class="item-meta">' + "".join(meta_bits) + "</div>") if meta_bits else ""
            section_html_parts.append(f'''    <article class="idea">
      <details class="idea-details">
        <summary class="idea-summary">
          <span class="idea-title">{title}</span>
          <svg class="chevron-sm" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2 L8 6 L4 10"/></svg>
        </summary>
        {meta_html}
        <div class="idea-content">
{content_html}
        </div>
      </details>
    </article>''')
        section_html_parts.append("  </div>\n</details>")
      
    
        src = row["source"].strip().lower()
        if src == "breaking news":
            return True
        if "openclaw" in src:
            return True
        title = row["title"]
        letters = [c for c in title if c.isalpha()]
        if len(letters) >= 5:
            upper_count = sum(1 for c in letters if c.isupper())
            if (upper_count / len(letters)) >= 0.7:
                return True
        return False

    breaking_news_rows = [r for r in rows if ]

    breaking_section_html = ""
    if breaking_news_rows:
        bn_items_html = []
        for r in breaking_news_rows:
            title = html.escape(r["title"].strip())
            slot = html.escape(r["slot"].strip())
            created = html.escape(r["created"].strip())
            content_html = render_content(r["content"])
            meta_bits = []
            if slot: meta_bits.append(f'<span class="tag tag-slot">{slot}</span>')
            if created: meta_bits.append(f'<span class="tag tag-date">{created}</span>')
            meta_html = ('<div class="item-meta">' + "".join(meta_bits) + "</div>") if meta_bits else ""
            bn_items_html.append(f'''    <article class="idea">
      <details class="idea-details">
        <summary class="idea-summary">
          <span class="idea-title">{title}</span>
          <svg class="chevron-sm" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2 L8 6 L4 10"/></svg>
        </summary>
        {meta_html}
        <div class="idea-content">
{content_html}
        </div>
      </details>
    </article>''')

        breaking_section_html = f'''
<details class="breaking-section" open>
  <summary>
    <span class="section-num">●</span>
    <span class="section-title">Breaking News</span>
    <span class="section-count">{len(breaking_news_rows)}</span>
    <svg class="chevron" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2 L8 6 L4 10"/></svg>
  </summary>
  <div class="items">
{chr(10).join(bn_items_html)}
  </div>
</details>'''
# ---- Format Segments (static, hard-coded) ----
    FORMAT_SEGMENTS = [
        {
            "name": '"How we actually did it" reels',
            "summary": "Walk through real True Classic decisions with specifics.",
            "body": 'Walk through real True Classic decisions. "We spent $3K on our first Facebook ad and here\'s what happened." Specifics beat generalities every time.',
        },
        {
            "name": "Myth-busting format",
            "summary": "Short, punchy, contrarian takes that position the school.",
            "body": '"Everyone says you need VC funding to scale. We did $270M with zero." Short, punchy, contrarian. Sets up the school as the alternative path.',
        },
        {
            "name": "Behind the negotiation",
            "summary": "Show the frameworks behind $40–50M/yr in savings.",
            "body": 'You save $40–50M/yr negotiating. Show the frameworks. "Here\'s how I got our shipping costs cut 30%." This is curriculum preview content.',
        },
        {
            "name": "Student zero content",
            "summary": "Document mentoring someone launching a DTC brand, in real time.",
            "body": "Start documenting someone you're mentoring through launching a DTC brand. Real time. This becomes the proof of concept for the school before it even launches.",
        },
        {
            "name": '"What I\'d do with $5K today" series',
            "summary": "A step-by-step launch walkthrough — this IS the school funnel.",
            "body": "You started with $3K. Walk people through exactly how you'd launch a brand today step by step. Dropshipping first, validate on Amazon, then build the brand. This IS the school funnel.",
        },
        {
            "name": "Origin story series",
            "summary": "Break the whole origin story into chaptered reels.",
            "body": "Your origin story reel crushed. But you told the whole thing in one video. Break it into chapters. Poker days. Music failure. The $3K bet. Each one is a hook.",
        },
        {
            "name": "Roast format",
            "summary": "Break down bad DTC sites/ads. Entertainment + education.",
            "body": 'Look at bad DTC websites/ads (without naming names) and break down what\'s wrong. Entertainment + education. Your "take your website to zero" reel was this — lean harder into it.',
        },
    ]

    format_items_html = []
    for fs in FORMAT_SEGMENTS:
        format_items_html.append(f'''    <article class="idea">
      <details class="idea-details">
        <summary class="idea-summary">
          <span class="idea-title">{html.escape(fs["name"])}</span>
          <svg class="chevron-sm" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2 L8 6 L4 10"/></svg>
        </summary>
        <div class="idea-content">
          <p><em>{html.escape(fs["summary"])}</em></p>
          <p>{html.escape(fs["body"])}</p>
        </div>
      </details>
    </article>''')

    format_section_html = f'''
<details class="format-section">
  <summary>
    <span class="section-num">✦</span>
    <span class="section-title">Format Segments</span>
    <span class="section-count">{len(FORMAT_SEGMENTS)}</span>
    <svg class="chevron" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2 L8 6 L4 10"/></svg>
  </summary>
  <div class="items">
{chr(10).join(format_items_html)}
  </div>
</details>'''
    sections_html = breaking_section_html + "\n" + format_section_html + "\n" + "\n".join(section_html_parts)

    from datetime import datetime, timezone
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(rows)
    with_content = sum(1 for r in rows if r["content"].strip())

    page = (PAGE_TEMPLATE
            .replace("__TOTAL__", str(total))
            .replace("__WITH_CONTENT__", str(with_content))
            .replace("__SECTION_COUNT__", str(section_num))
            .replace("__UPDATED__", updated)
            .replace("__SECTIONS__", sections_html))

    out_dir = Path("public")
    out_dir.mkdir(exist_ok=True)
    import shutil
    for asset in ["icon-512.png", "icon-192.png", "apple-touch-icon.png",
                  "favicon-32.png", "manifest.json"]:
        src = Path(asset)
        if src.exists():
            shutil.copy(src, out_dir / asset)
            print(f"  copied {asset}")
        else:
            print(f"  (skipped {asset} — not found)")
    
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    print(f"\n✓ Wrote public/index.html — {total} ideas, {section_num} themes")


if __name__ == "__main__":
    main()
