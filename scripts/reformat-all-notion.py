#!/usr/bin/env python3
"""
Reformat ALL Notion pages under a parent page:
Convert plain-text markdown tables/headers to native Notion blocks.

Target structure:
  312b26f4-eb96-80d3-bfb4-c76b5522f155 (root)
    ├── 画面仕様書 (25 child pages)
    ├── ユースケース (23 child pages)
    └── テスト計画書 (empty)

Usage:
  python3 tmp/reformat-all-notion.py [--dry-run] [--page PAGE_ID] [--skip-already-done]
"""

import os
import re
import sys
import time
import json
import argparse
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

# Root page and section pages
ROOT_PAGE_ID = "312b26f4-eb96-80d3-bfb4-c76b5522f155"
SCREEN_SPEC_PAGE_ID = "313b26f4-eb96-812a-b09b-eef91ad505d1"
USECASE_PAGE_ID = "313b26f4-eb96-817f-b658-e10ae5d132ad"

# Already reformatted page (skip)
ALREADY_DONE = {"313b26f4-eb96-8160-8d05-f228bf1bc8ca"}  # 管理者ダッシュボード

# Rate limit handling
REQUEST_DELAY = 0.35  # seconds between requests to avoid 429


def api_request(method, url, **kwargs):
    """Make an API request with rate limit handling."""
    time.sleep(REQUEST_DELAY)
    resp = getattr(requests, method)(url, headers=HEADERS, **kwargs)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 2))
        print(f"    Rate limited, waiting {retry_after}s...")
        time.sleep(retry_after)
        resp = getattr(requests, method)(url, headers=HEADERS, **kwargs)
    return resp


# ─── Notion API helpers ───


def get_child_pages(parent_id):
    """Get all child_page blocks under a parent."""
    pages = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = api_request("get", f"https://api.notion.com/v1/blocks/{parent_id}/children", params=params)
        data = resp.json()
        for block in data.get("results", []):
            if block["type"] == "child_page":
                pages.append({"id": block["id"], "title": block["child_page"]["title"]})
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return pages


def get_all_blocks(page_id):
    """Get all blocks in a page."""
    blocks = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = api_request("get", f"https://api.notion.com/v1/blocks/{page_id}/children", params=params)
        data = resp.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def delete_block(block_id):
    """Delete (archive) a block."""
    resp = api_request("delete", f"https://api.notion.com/v1/blocks/{block_id}")
    if resp.status_code not in (200, 404):
        print(f"    Warning: delete {block_id} returned {resp.status_code}")


def append_blocks(page_id, blocks):
    """Append blocks to a page in batches of 100."""
    for i in range(0, len(blocks), 100):
        batch = blocks[i : i + 100]
        resp = api_request(
            "patch",
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            json={"children": batch},
        )
        if resp.status_code != 200:
            err = resp.text[:300]
            print(f"    ERROR appending blocks {i+1}-{i+len(batch)}: {resp.status_code} {err}")
            return False
    return True


# ─── Rich Text Parser ───


def parse_inline_formatting(text_str):
    """Parse inline markdown formatting to Notion rich text array.

    Handles:
    - `code` → code annotation
    - [link text](url) → link
    - Regular text
    """
    if not text_str or not text_str.strip():
        return [rt_text("")]

    rich_texts = []
    # Pattern to match `code` or [text](url)
    pattern = r'(`[^`]+`|\[[^\]]*\]\([^)]+\))'
    parts = re.split(pattern, text_str)

    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            # Code span
            code_content = part[1:-1]
            rich_texts.append(rt_text(code_content, code=True))
        elif re.match(r'\[([^\]]*)\]\(([^)]+)\)', part):
            # Markdown link - only create link if URL is valid (http/https)
            m = re.match(r'\[([^\]]*)\]\(([^)]+)\)', part)
            url = m.group(2)
            if url.startswith(("http://", "https://")):
                rich_texts.append(rt_text(m.group(1), link=url))
            else:
                # Relative path or invalid URL - render as plain text
                rich_texts.append(rt_text(m.group(1)))
        else:
            rich_texts.append(rt_text(part))

    return rich_texts if rich_texts else [rt_text("")]


def rt_text(content, bold=False, code=False, link=None):
    """Create a single rich text element."""
    rt = {"type": "text", "text": {"content": content}}
    if link:
        rt["text"]["link"] = {"url": link}
    annotations = {}
    if bold:
        annotations["bold"] = True
    if code:
        annotations["code"] = True
    if annotations:
        rt["annotations"] = annotations
    return rt


# ─── Block Builders ───


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


def empty_paragraph():
    return {"type": "paragraph", "paragraph": {"rich_text": []}}


def bullet_item(rich_texts):
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_texts}}


def make_table(rows):
    """Create a table block from parsed rows.
    Each row is a list of cell strings (raw markdown text).
    First row is treated as header.
    """
    if not rows or len(rows) < 1:
        return None

    width = len(rows[0])
    table_rows = []
    for row in rows:
        cells = []
        for cell_text in row:
            cell_text = cell_text.strip()
            rich_texts = parse_inline_formatting(cell_text)
            cells.append(rich_texts)
        # Pad or trim to match width
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


# ─── Content Parser ───


def extract_plain_text(block):
    """Extract plain text from a block's rich_text array."""
    btype = block["type"]
    rt_list = block.get(btype, {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rt_list)


def parse_table_row(line):
    """Parse a markdown table row '| col1 | col2 | col3 |' into list of cell strings."""
    line = line.strip()
    if not line.startswith("|"):
        return None
    # Split by |, remove first/last empty elements
    parts = line.split("|")
    # Remove leading/trailing empty strings from split
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]


def is_separator_row(cells):
    """Check if a row is a markdown table separator (| --- | --- |)."""
    return all(re.match(r'^:?-+:?$', c.strip()) for c in cells if c.strip())


def is_already_reformatted(blocks):
    """Check if a page has already been reformatted (contains native heading/table blocks)."""
    for b in blocks:
        if b["type"] in ("heading_1", "heading_2", "heading_3", "table"):
            return True
    return False


def parse_page_blocks(blocks):
    """Parse raw Notion blocks into a list of new formatted blocks."""
    new_blocks = []
    i = 0

    while i < len(blocks):
        block = blocks[i]
        btype = block["type"]

        if btype == "paragraph":
            text = extract_plain_text(block)

            # Skip empty paragraphs
            if not text.strip():
                i += 1
                continue

            # Decorative title: ━━━ タイトル ━━━
            if "━━━" in text:
                i += 1
                continue

            # Horizontal rule: ---
            if text.strip() == "---":
                new_blocks.append(divider())
                i += 1
                continue

            # Section header: ■ セクション名
            if text.startswith("■ "):
                section_name = text[2:].strip()
                new_blocks.append(heading1(section_name))
                i += 1
                continue

            # Sub-section header: ▸ サブセクション名
            if text.startswith("▸ "):
                subsection_name = text[2:].strip()
                new_blocks.append(heading2(subsection_name))
                i += 1
                continue

            # Markdown table row
            if text.strip().startswith("|"):
                table_rows = []
                while i < len(blocks):
                    b = blocks[i]
                    if b["type"] != "paragraph":
                        break
                    t = extract_plain_text(b)
                    if not t.strip().startswith("|"):
                        break
                    cells = parse_table_row(t)
                    if cells is None:
                        break
                    if not is_separator_row(cells):
                        table_rows.append(cells)
                    i += 1

                if table_rows:
                    tbl = make_table(table_rows)
                    if tbl:
                        new_blocks.append(tbl)
                continue

            # Regular paragraph - preserve with inline formatting
            rich_texts = parse_inline_formatting(text)
            new_blocks.append(paragraph(rich_texts))
            i += 1
            continue

        elif btype == "bulleted_list_item":
            text = extract_plain_text(block)
            rich_texts = parse_inline_formatting(text)
            new_blocks.append(bullet_item(rich_texts))
            i += 1
            continue

        else:
            # Skip unknown block types
            i += 1
            continue

    return new_blocks


# ─── Main Processing ───


def process_page(page_id, page_title, dry_run=False):
    """Process a single page: read blocks, parse, delete old, create new."""
    print(f"  Processing: {page_title} ({page_id})")

    # Get existing blocks
    blocks = get_all_blocks(page_id)
    if not blocks:
        print(f"    Empty page, skipping")
        return True

    # Check if already reformatted
    if is_already_reformatted(blocks):
        print(f"    Already reformatted (contains native headings/tables), skipping")
        return True

    # Parse blocks into new format
    new_blocks = parse_page_blocks(blocks)
    if not new_blocks:
        print(f"    No content to reformat, skipping")
        return True

    block_ids = [b["id"] for b in blocks]

    print(f"    Old blocks: {len(blocks)} → New blocks: {len(new_blocks)}")

    if dry_run:
        print(f"    [DRY RUN] Would delete {len(block_ids)} blocks and create {len(new_blocks)} blocks")
        # Show preview of new block types
        types = {}
        for nb in new_blocks:
            t = nb["type"]
            types[t] = types.get(t, 0) + 1
        print(f"    New block types: {types}")
        return True

    # Delete all old blocks
    print(f"    Deleting {len(block_ids)} old blocks...")
    for bid in block_ids:
        delete_block(bid)

    # Create new blocks
    print(f"    Creating {len(new_blocks)} new blocks...")
    success = append_blocks(page_id, new_blocks)
    if success:
        print(f"    Done!")
    else:
        print(f"    FAILED to create some blocks")
    return success


def main():
    parser = argparse.ArgumentParser(description="Reformat Notion pages")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying")
    parser.add_argument("--page", help="Process only a specific page ID")
    parser.add_argument("--skip-already-done", action="store_true", default=True,
                        help="Skip pages that are already reformatted")
    args = parser.parse_args()

    if args.page:
        # Process a single page
        process_page(args.page, "Single page", dry_run=args.dry_run)
        return

    # Discover all child pages
    print("Discovering pages...")

    print("\n=== 画面仕様書 ===")
    screen_pages = get_child_pages(SCREEN_SPEC_PAGE_ID)
    print(f"Found {len(screen_pages)} pages")

    print("\n=== ユースケース ===")
    usecase_pages = get_child_pages(USECASE_PAGE_ID)
    print(f"Found {len(usecase_pages)} pages")

    all_pages = []
    for p in screen_pages:
        all_pages.append({"section": "画面仕様書", **p})
    for p in usecase_pages:
        all_pages.append({"section": "ユースケース", **p})

    # Filter out already done pages
    todo_pages = [p for p in all_pages if p["id"] not in ALREADY_DONE]
    print(f"\nTotal pages to process: {len(todo_pages)} (skipping {len(all_pages) - len(todo_pages)} already done)")

    if args.dry_run:
        print("\n[DRY RUN MODE]")

    # Process each page
    success_count = 0
    fail_count = 0
    skip_count = 0

    for idx, page in enumerate(todo_pages, 1):
        print(f"\n[{idx}/{len(todo_pages)}] ({page['section']})")
        result = process_page(page["id"], page["title"], dry_run=args.dry_run)
        if result:
            success_count += 1
        else:
            fail_count += 1

    print(f"\n{'=' * 50}")
    print(f"Completed: {success_count} success, {fail_count} failed")
    if args.dry_run:
        print("(Dry run - no changes made)")


if __name__ == "__main__":
    main()
