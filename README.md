# citedelta

Track citation count changes in your Google Scholar profile over time.

On each run, citedelta fetches your publications via SerpAPI and compares against the last snapshot, reporting which papers gained citations since you last checked.

## Setup

**1. Get a free SerpAPI key**

Sign up at [serpapi.com](https://serpapi.com) — the free tier includes 100 searches/month, enough for weekly runs.

**2. Install dependencies**

```bash
pip install requests
```

**3. Configure credentials**

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

```ini
SERPAPI_KEY=your_serpapi_key_here
SCHOLAR_AUTHOR_ID=your_scholar_id_here
```

Your Scholar author ID is the `user=` value in your Google Scholar profile URL:
`https://scholar.google.com/citations?user=XXXXXXXX`

## Usage

```bash
# Fetch latest citations and compare against last snapshot
python3 citedelta.py

# Test the comparison output without hitting the network
python3 citedelta.py --test

# Override the author ID for a one-off lookup
python3 citedelta.py AUTHOR_ID
```

## Example output

```
Fetching articles 1–100 ...
Author: Jane Smith  |  Total citations: 1048

==============================================================
Comparison: 2026-05-01T09:00:00  →  2026-05-19T10:30:00
Overall citations: 1048 → 1063  (+15)
==============================================================

Papers with new citations (3):

  +   8  A fast algorithm for approximate nearest neighbors
         120 → 128 citations
  +   5  Scalable distributed training of deep neural networks
         43 → 48 citations
  +   2  Benchmark evaluation of large language models
         11 → 13 citations
```

Snapshots are saved to `snapshots/<author_id>.json` and updated on each real run.
