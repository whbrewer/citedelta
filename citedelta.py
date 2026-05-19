#!/usr/bin/env python3
"""
Google Scholar citation tracker using SerpAPI.
Fetches an author's papers and citation counts, saves a snapshot, and on
subsequent runs reports which papers gained new citations.

Setup: get a free API key at https://serpapi.com (100 searches/month free),
then set the environment variable:
    export SERPAPI_KEY=your_key_here
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run: pip install requests")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


load_dotenv(Path(__file__).parent / ".env")

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)

SERPAPI_URL = "https://serpapi.com/search.json"
PAGE_SIZE = 100


def fetch_author(author_id: str, api_key: str) -> dict:
    """Fetch all publications for an author via SerpAPI."""
    papers = {}
    name = ""
    total_citations = 0
    start = 0

    while True:
        params = {
            "engine": "google_scholar_author",
            "author_id": author_id,
            "api_key": api_key,
            "num": PAGE_SIZE,
            "start": start,
        }
        print(f"Fetching articles {start + 1}–{start + PAGE_SIZE} ...")
        try:
            resp = requests.get(SERPAPI_URL, params=params, timeout=30)
        except requests.exceptions.Timeout:
            sys.exit("Request timed out.")
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            sys.exit(f"SerpAPI error: {data['error']}")

        if start == 0:
            author_info = data.get("author", {})
            name = author_info.get("name", "")
            cited_by = data.get("cited_by", {})
            table = cited_by.get("table", [])
            if table:
                total_citations = table[0].get("citations", {}).get("all", 0)
            print(f"Author: {name}  |  Total citations: {total_citations}")

        articles = data.get("articles", [])
        if not articles:
            break

        for article in articles:
            title = article.get("title", "")
            pub_id = article.get("article_id") or title
            citations = article.get("cited_by", {}).get("value") or 0
            year = str(article.get("year", ""))
            papers[pub_id] = {"title": title, "citations": citations, "year": year}

        if len(articles) < PAGE_SIZE:
            break

        start += PAGE_SIZE
        time.sleep(0.5)

    h = calc_hindex(papers)
    i10 = calc_i10index(papers)
    print_papers(papers, h, i10)

    return {
        "author_id": author_id,
        "name": name,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "total_citations": total_citations,
        "h_index": h,
        "i10_index": i10,
        "papers": papers,
    }


def calc_hindex(papers: dict) -> int:
    counts = sorted((p["citations"] for p in papers.values()), reverse=True)
    h = 0
    for i, c in enumerate(counts, 1):
        if c >= i:
            h = i
        else:
            break
    return h


def calc_i10index(papers: dict) -> int:
    return sum(1 for p in papers.values() if p["citations"] >= 10)


def separator(label: str) -> None:
    print(f"  {'─' * 61}")
    print(f"  {label:^61}")
    print(f"  {'─' * 61}")


def print_papers(papers: dict, h_index: int, i10_index: int) -> None:
    sorted_papers = sorted(papers.values(), key=lambda p: p["citations"], reverse=True)
    for i, info in enumerate(sorted_papers, 1):
        if i == h_index + 1:
            separator(f"h-index = {h_index}")
        elif i == i10_index + 1:
            separator(f"i10-index = {i10_index}")
        print(f"  {info['title'][:65]}  ({info['citations']})")


def snapshot_path(author_id: str) -> Path:
    return SNAPSHOT_DIR / f"{author_id}.json"


def load_snapshot(author_id: str) -> dict | None:
    path = snapshot_path(author_id)
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_snapshot(data: dict) -> None:
    path = snapshot_path(data["author_id"])
    path.write_text(json.dumps(data, indent=2))
    print(f"\nSnapshot saved to {path}")


def compare(old: dict, new: dict) -> None:
    old_papers = old["papers"]
    new_papers = new["papers"]

    gained = []
    added = []

    for pub_id, new_info in new_papers.items():
        if pub_id in old_papers:
            delta = new_info["citations"] - old_papers[pub_id]["citations"]
            if delta > 0:
                gained.append((delta, new_info["title"], old_papers[pub_id]["citations"], new_info["citations"]))
        else:
            if new_info["citations"] > 0:
                added.append(new_info)

    old_total = old.get("total_citations", 0)
    new_total = new.get("total_citations", 0)
    total_delta = new_total - old_total

    print(f"\n{'='*62}")
    print(f"Comparison: {old['fetched_at']}  →  {new['fetched_at']}")
    print(f"Overall citations: {old_total} → {new_total}  ({total_delta:+d})")
    print(f"{'='*62}")

    if gained:
        gained.sort(reverse=True)
        print(f"\nPapers with new citations ({len(gained)}):\n")
        for delta, title, before, after in gained:
            print(f"  +{delta:>4}  {title[:57]}")
            print(f"         {before} → {after} citations")
    else:
        print("\nNo citation increases detected.")

    if added:
        print(f"\nNew papers in profile ({len(added)}):")
        for p in added:
            print(f"  {p['title'][:62]}  ({p['citations']} citations)")


def make_test_data(snapshot: dict) -> dict:
    import copy, random
    random.seed(42)
    data = copy.deepcopy(snapshot)
    data["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    keys = list(data["papers"].keys())
    for key in random.sample(keys, min(5, len(keys))):
        bump = random.randint(1, 8)
        data["papers"][key]["citations"] += bump
        data["total_citations"] += bump
    return data


def main():
    parser = argparse.ArgumentParser(
        description="Track Google Scholar citations over time via SerpAPI."
    )
    parser.add_argument(
        "author_id",
        nargs="?",
        default=os.environ.get("SCHOLAR_AUTHOR_ID"),
        help="Google Scholar author ID (default: $SCHOLAR_AUTHOR_ID from .env)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Dry-run comparison using a tweaked copy of the saved snapshot (no network call).",
    )
    args = parser.parse_args()

    if not args.author_id:
        sys.exit("No author ID provided. Pass one as an argument or set SCHOLAR_AUTHOR_ID in .env")

    old_snapshot = load_snapshot(args.author_id)

    if args.test:
        if not old_snapshot:
            sys.exit("No saved snapshot found. Run without --test first to create a baseline.")
        new_data = make_test_data(old_snapshot)
        compare(old_snapshot, new_data)
        print("\n(Test mode — snapshot was NOT updated.)")
        return

    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit(
            "SERPAPI_KEY environment variable not set.\n"
            "Get a free key at https://serpapi.com, then run:\n"
            "  export SERPAPI_KEY=your_key_here"
        )

    new_data = fetch_author(args.author_id, api_key)

    if old_snapshot:
        compare(old_snapshot, new_data)
    else:
        print(f"\nFirst run for '{new_data['name']}'. Snapshot saved as baseline.")
        print(f"Total papers: {len(new_data['papers'])}")
        print(f"Total citations: {new_data['total_citations']}")

    save_snapshot(new_data)


if __name__ == "__main__":
    main()
