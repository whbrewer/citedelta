# Claude Instructions for citedelta

## What this project is

citedelta tracks Google Scholar citation counts over time for a single author. On each run it fetches the author's full publication list via SerpAPI, saves a snapshot, and compares against the previous snapshot to report which papers gained or lost citations. It also calculates citation velocity and forecasts h-index milestones once enough history has accumulated.

## Author

- **Name:** Wes Brewer
- **Google Scholar ID:** `JJXxbiYAAAAJ`
- **Scholar profile:** https://scholar.google.com/citations?user=JJXxbiYAAAAJ

## Key files

| File | Purpose |
|------|---------|
| `citedelta.py` | Main script |
| `.env` | API credentials (gitignored) — `SERPAPI_KEY` and `SCHOLAR_AUTHOR_ID` |
| `snapshots/JJXxbiYAAAAJ.json` | Full snapshot history — array of snapshots, one per run |
| `projections.md` | Citation milestone projections (not committed unless asked) |
| `requirements.txt` | Python dependencies (`requests`) |

## Running the tool

```bash
python3 citedelta.py                # fetch latest, compare against last snapshot
python3 citedelta.py --log          # show full history of citation changes across all runs
python3 citedelta.py --test         # dry-run comparison using a tweaked snapshot (no network)
```

The SerpAPI key must be set in `.env` or as `$SERPAPI_KEY`. The free tier allows 100 searches/month; each run uses 1 search (all papers fit in one page).

## Snapshot format

`snapshots/JJXxbiYAAAAJ.json` stores all snapshots in a single file:

```json
{
  "author_id": "JJXxbiYAAAAJ",
  "name": "Wes Brewer",
  "snapshots": [
    {
      "fetched_at": "2026-05-19T11:01:10",
      "total_citations": 1048,
      "h_index": 18,
      "i10_index": 39,
      "papers": {
        "<article_id>": { "title": "...", "citations": 55, "year": "2020" }
      }
    }
  ]
}
```

Each run appends a new entry. The compare always diffs the last two entries. Velocity and h-index forecasts are computed across the full history once snapshots span at least 7 days.

## Citation Projections

When the user asks when a paper will reach a target citation count:

1. Look up the paper's current citation count from the latest snapshot in `snapshots/JJXxbiYAAAAJ.json`
2. Ask for (or use the provided) publication date
3. Calculate: rate = current citations ÷ months since publication
4. Calculate: ETA = today + (target − current) ÷ rate
5. Add or update a row in `projections.md` with the result
6. Do not commit `projections.md` unless asked

`projections.md` columns: Paper | Citations (date) | Target | Rate (cites/mo) | ETA | Notes

## h-index and i10-index

These are calculated fresh from each snapshot:
- **h-index:** largest h where h papers each have ≥ h citations
- **i10-index:** number of papers with ≥ 10 citations

The publication listing printed on each run shows a separator line at each threshold so the user can see at a glance which papers contribute to each index.

## Velocity and forecasting

Citation velocity (citations/month) is calculated per paper from the first and last snapshot containing that paper, provided they are at least 7 days apart. The h-index forecast projects the next 3 h-index milestones by estimating when the threshold paper will accumulate enough citations at its current pace.

## Committing

- Commit `citedelta.py`, `README.md`, `CLAUDE.md`, `.gitignore`, `requirements.txt` freely
- Do **not** commit `snapshots/` or `.env` (both gitignored)
- Do **not** commit `projections.md` unless the user explicitly asks
