#!/usr/bin/env python3
"""Restore the failed page 'ユースケース: 組織作成' from the markdown source."""

import os
import re
import sys
import time
import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
if not NOTION_TOKEN:
    print("ERROR: Set NOTION_TOKEN environment variable")
    sys.exit(1)
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
PAGE_ID = "313b26f4-eb96-81ea-bc83-f4631ddc5048"
REQUEST_DELAY = 0.35
MD_FILE = "/Users/coa/claudecode/dev/prj-bmg/lean_quest.worktrees/aoki-bmg-1480/docs/usecase/use-case-organization-create.md"


def api_request(method, url, **kwargs):
    time.sleep(REQUEST_DELAY)
    resp = getattr(requests, method)(url, headers=HEADERS, **kwargs)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 2))
        time.sleep(retry_after)
        resp = getattr(requests, method)(url, headers=HEADERS, **kwargs)
    return resp


def rt_text(content, bold=False, code=False, link=None):
    rt = {"type": "text", "text": {"content": content}}
    if link and link.startswith(("http://", "https://")):
        rt["text"]["link"] = {"url": link}
    annotations = {}
    if bold:
        annotations["bold"] = True
    if code:
        annotations["code"] = True
    if annotations:
        rt["annotations"] = annotations
    return rt


def parse_inline(text_str):
    if not text_str or not text_str.strip():
        return [rt_text("")]
    rich_texts = []
    pattern = r'(`[^`]+`|\[[^\]]*\]\([^)]+\))'
    parts = re.split(pattern, text_str)
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            rich_texts.append(rt_text(part[1:-1], code=True))
        elif re.match(r'\[([^\]]*)\]\(([^)]+)\)', part):
            m = re.match(r'\[([^\]]*)\]\(([^)]+)\)', part)
            url = m.group(2)
            if url.startswith(("http://", "https://")):
                rich_texts.append(rt_text(m.group(1), link=url))
            else:
                rich_texts.append(rt_text(m.group(1)))
        else:
            rich_texts.append(rt_text(part))
    return rich_texts if rich_texts else [rt_text("")]


def heading1(title):
    return {"type": "heading_1", "heading_1": {"rich_text": [rt_text(title)]}}

def heading2(title):
    return {"type": "heading_2", "heading_2": {"rich_text": [rt_text(title)]}}

def heading3(title):
    return {"type": "heading_3", "heading_3": {"rich_text": [rt_text(title)]}}

def divider():
    return {"type": "divider", "divider": {}}

def paragraph(rich_texts):
    return {"type": "paragraph", "paragraph": {"rich_text": rich_texts}}

def bullet_item(rich_texts):
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_texts}}

def parse_table_row(line):
    line = line.strip()
    if not line.startswith("|"):
        return None
    parts = line.split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]

def is_separator_row(cells):
    return all(re.match(r'^:?-+:?$', c.strip()) for c in cells if c.strip())

def make_table(rows):
    if not rows:
        return None
    width = len(rows[0])
    table_rows = []
    for row in rows:
        cells = []
        for cell_text in row:
            cells.append(parse_inline(cell_text.strip()))
        while len(cells) < width:
            cells.append([rt_text("")])
        cells = cells[:width]
        table_rows.append({"type": "table_row", "table_row": {"cells": cells}})
    return {
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows,
        },
    }


def parse_markdown(filepath):
    """Parse a markdown file into Notion blocks."""
    with open(filepath, "r") as f:
        lines = f.readlines()

    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Headings
        if line.startswith("# "):
            # Skip h1 (page title)
            i += 1
            continue
        if line.startswith("### "):
            blocks.append(heading3(line[4:].strip()))
            i += 1
            continue
        if line.startswith("## "):
            blocks.append(heading1(line[3:].strip()))
            i += 1
            continue

        # Horizontal rule
        if line.strip() == "---":
            blocks.append(divider())
            i += 1
            continue

        # Bullet list
        if line.strip().startswith("- "):
            text = line.strip()[2:]
            blocks.append(bullet_item(parse_inline(text)))
            i += 1
            continue

        # Table
        if line.strip().startswith("|"):
            table_rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = parse_table_row(lines[i])
                if cells and not is_separator_row(cells):
                    table_rows.append(cells)
                i += 1
            if table_rows:
                tbl = make_table(table_rows)
                if tbl:
                    blocks.append(tbl)
            continue

        # Regular paragraph
        blocks.append(paragraph(parse_inline(line.strip())))
        i += 1

    return blocks


def main():
    print(f"Parsing markdown: {MD_FILE}")
    blocks = parse_markdown(MD_FILE)
    print(f"Generated {len(blocks)} blocks")

    # Show block types
    types = {}
    for b in blocks:
        t = b["type"]
        types[t] = types.get(t, 0) + 1
    print(f"Block types: {types}")

    # Append to page
    print(f"Appending to page {PAGE_ID}...")
    for i in range(0, len(blocks), 100):
        batch = blocks[i:i+100]
        resp = api_request("patch", f"https://api.notion.com/v1/blocks/{PAGE_ID}/children", json={"children": batch})
        if resp.status_code == 200:
            print(f"  Appended blocks {i+1}-{i+len(batch)}")
        else:
            print(f"  ERROR: {resp.status_code} {resp.text[:300]}")
            return

    print("Done!")


if __name__ == "__main__":
    main()
