#!/usr/bin/env python3
"""
Google Scholar citation tracker using SerpAPI.
Fetches an author's papers and citation counts, saves a snapshot history,
and on each run reports citation changes, velocity, and h-index forecast.

Setup: get a free API key at https://serpapi.com (100 searches/month free),
then set the environment variable:
    export SERPAPI_KEY=your_key_here
"""

import copy
import json
import os
import random
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
MIN_DAYS_FOR_VELOCITY = 7  # don't show velocity until snapshots span at least this long


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

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
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "total_citations": total_citations,
        "h_index": h,
        "i10_index": i10,
        "papers": papers,
    }


# ---------------------------------------------------------------------------
# Indices and display
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# History storage  (each run appends a snapshot; old single-snapshot files
# are migrated automatically on first load)
# ---------------------------------------------------------------------------

def history_path(author_id: str) -> Path:
    return SNAPSHOT_DIR / f"{author_id}.json"


def load_history(author_id: str) -> dict | None:
    path = history_path(author_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    # Migrate old single-snapshot format
    if "snapshots" not in data:
        snap = {k: v for k, v in data.items() if k not in ("author_id", "name")}
        data = {"author_id": data["author_id"], "name": data.get("name", ""), "snapshots": [snap]}
    return data


def append_snapshot(history: dict, snapshot: dict, author_id: str, name: str) -> None:
    history["name"] = name
    history["snapshots"].append(snapshot)
    path = history_path(author_id)
    path.write_text(json.dumps(history, indent=2))
    print(f"\nSnapshot saved ({len(history['snapshots'])} total).")


# ---------------------------------------------------------------------------
# Velocity  (citations per month for a given paper across all history)
# ---------------------------------------------------------------------------

def _days_between(t1: str, t2: str) -> float:
    dt1 = datetime.fromisoformat(t1)
    dt2 = datetime.fromisoformat(t2)
    return (dt2 - dt1).total_seconds() / 86400


def paper_velocity(history: dict, pub_id: str) -> float | None:
    """Citations per month for a paper, using first and last snapshot that contain it."""
    points = [
        (s["fetched_at"], s["papers"][pub_id]["citations"])
        for s in history["snapshots"]
        if pub_id in s.get("papers", {})
    ]
    if len(points) < 2:
        return None
    days = _days_between(points[0][0], points[-1][0])
    if days < MIN_DAYS_FOR_VELOCITY:
        return None
    return (points[-1][1] - points[0][1]) / days * 30.44  # → per month


def history_span_days(history: dict) -> float:
    snaps = history["snapshots"]
    if len(snaps) < 2:
        return 0
    return _days_between(snaps[0]["fetched_at"], snaps[-1]["fetched_at"])


# ---------------------------------------------------------------------------
# Compare and forecast
# ---------------------------------------------------------------------------

def compare(old_snap: dict, new_snap: dict, history: dict) -> None:
    old_papers = old_snap["papers"]
    new_papers = new_snap["papers"]

    gained = []
    added = []

    for pub_id, new_info in new_papers.items():
        if pub_id in old_papers:
            delta = new_info["citations"] - old_papers[pub_id]["citations"]
            if delta > 0:
                vel = paper_velocity(history, pub_id)
                gained.append((delta, pub_id, new_info["title"],
                                old_papers[pub_id]["citations"], new_info["citations"], vel))
        else:
            if new_info["citations"] > 0:
                added.append(new_info)

    old_total = old_snap.get("total_citations", 0)
    new_total = new_snap.get("total_citations", 0)
    total_delta = new_total - old_total

    print(f"\n{'='*62}")
    print(f"Comparison: {old_snap['fetched_at']}  →  {new_snap['fetched_at']}")
    print(f"Overall citations: {old_total} → {new_total}  ({total_delta:+d})")
    print(f"{'='*62}")

    if gained:
        gained.sort(reverse=True)
        has_velocity = any(vel is not None for *_, vel in gained)
        print(f"\nPapers with new citations ({len(gained)}):\n")
        for delta, pub_id, title, before, after, vel in gained:
            vel_str = f"  ({vel:+.1f}/mo)" if vel is not None else ""
            print(f"  +{delta:>4}  {title[:55]}{vel_str}")
            print(f"         {before} → {after} citations")
    else:
        print("\nNo citation increases detected.")

    if added:
        print(f"\nNew papers in profile ({len(added)}):")
        for p in added:
            print(f"  {p['title'][:62]}  ({p['citations']} citations)")

    if history_span_days(history) >= MIN_DAYS_FOR_VELOCITY:
        forecast_hindex(history, new_snap)


def forecast_hindex(history: dict, latest: dict) -> None:
    papers = latest["papers"]
    h = latest.get("h_index", calc_hindex(papers))
    sorted_ids = [
        pub_id for pub_id, _ in
        sorted(papers.items(), key=lambda x: x[1]["citations"], reverse=True)
    ]

    lines = []
    for target_h in range(h + 1, h + 4):
        if target_h > len(sorted_ids):
            break
        pub_id = sorted_ids[target_h - 1]
        info = papers[pub_id]
        needed = target_h - info["citations"]
        if needed <= 0:
            lines.append(f"  h={target_h}: already qualified (recheck next run)")
            continue
        vel = paper_velocity(history, pub_id)
        if vel and vel > 0:
            months = needed / vel
            lines.append(
                f"  h={target_h}: ~{months:.1f} months  "
                f"({info['title'][:40]}  needs +{needed}, pace {vel:.1f}/mo)"
            )
        else:
            lines.append(
                f"  h={target_h}: insufficient velocity data  "
                f"({info['title'][:40]}  needs +{needed})"
            )

    if lines:
        print(f"\n{'='*62}")
        print(f"h-index forecast  (current: {h})")
        print(f"{'='*62}")
        for line in lines:
            print(line)


# ---------------------------------------------------------------------------
# Historical log
# ---------------------------------------------------------------------------

def show_log(history: dict) -> None:
    """Print a chronological log of citation changes across all snapshot pairs."""
    snaps = history["snapshots"]
    if len(snaps) < 2:
        print("Only one snapshot — run again later to build up history.")
        return

    for i in range(1, len(snaps)):
        old, new = snaps[i - 1], snaps[i]
        old_papers = old["papers"]
        new_papers = new["papers"]

        gained = []
        for pub_id, new_info in new_papers.items():
            if pub_id in old_papers:
                delta = new_info["citations"] - old_papers[pub_id]["citations"]
                if delta > 0:
                    gained.append((delta, new_info["title"],
                                   old_papers[pub_id]["citations"], new_info["citations"]))

        old_total = old.get("total_citations", 0)
        new_total = new.get("total_citations", 0)
        total_delta = new_total - old_total

        print(f"\n{'='*62}")
        print(f"Run #{i}  {old['fetched_at']}  →  {new['fetched_at']}  ({total_delta:+d} citations)")
        print(f"{'='*62}")

        if gained:
            gained.sort(reverse=True)
            for delta, title, before, after in gained:
                print(f"  +{delta:>4}  {title[:55]}")
                print(f"         {before} → {after} citations")
        else:
            print("  No citation changes.")


# ---------------------------------------------------------------------------
# Test mode
# ---------------------------------------------------------------------------

def make_test_snapshot(latest: dict) -> dict:
    snap = copy.deepcopy(latest)
    snap["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    keys = list(snap["papers"].keys())
    for key in random.sample(keys, min(5, len(keys))):
        bump = random.randint(1, 8)
        snap["papers"][key]["citations"] += bump
        snap["total_citations"] += bump
    snap["h_index"] = calc_hindex(snap["papers"])
    snap["i10_index"] = calc_i10index(snap["papers"])
    return snap


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    random.seed(42)
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
        help="Dry-run comparison using a tweaked copy of the latest snapshot (no network call).",
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Show the full history of citation changes across all past runs.",
    )
    args = parser.parse_args()

    if not args.author_id:
        sys.exit("No author ID provided. Pass one as an argument or set SCHOLAR_AUTHOR_ID in .env")

    history = load_history(args.author_id)

    if args.log:
        if not history:
            sys.exit("No snapshot history found.")
        show_log(history)
        return

    if args.test:
        if not history:
            sys.exit("No snapshot history found. Run without --test first to create a baseline.")
        latest = history["snapshots"][-1]
        test_snap = make_test_snapshot(latest)
        # Temporarily extend history so velocity works in test mode
        test_history = copy.deepcopy(history)
        test_history["snapshots"].append(test_snap)
        compare(latest, test_snap, test_history)
        print("\n(Test mode — history was NOT updated.)")
        return

    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit(
            "SERPAPI_KEY environment variable not set.\n"
            "Get a free key at https://serpapi.com, then run:\n"
            "  export SERPAPI_KEY=your_key_here"
        )

    new_snap = fetch_author(args.author_id, api_key)

    if history:
        compare(history["snapshots"][-1], new_snap, history)
        append_snapshot(history, new_snap, args.author_id, history["name"])
    else:
        name = new_snap.pop("name", "")
        history = {"author_id": args.author_id, "name": name, "snapshots": [new_snap]}
        history_path(args.author_id).write_text(json.dumps(history, indent=2))
        print(f"\nFirst run for '{name}'. Snapshot saved as baseline.")
        print(f"Total papers: {len(new_snap['papers'])}")
        print(f"Total citations: {new_snap['total_citations']}")


if __name__ == "__main__":
    main()
