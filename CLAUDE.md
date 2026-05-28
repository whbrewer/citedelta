# Claude Instructions for citedelta

## Citation Projections

When the user asks when a paper will reach a target citation count:

1. Look up the paper's current citation count from the latest snapshot in `snapshots/wJItLaAAAAAJ.json`
2. Ask for (or use the provided) publication date
3. Calculate: rate = current citations ÷ months since publication
4. Calculate: ETA = today + (target − current) ÷ rate
5. Add or update a row in `projections.md` with the result
6. Do not commit `projections.md` unless asked

`projections.md` columns: Paper | Citations (date) | Target | Rate (cites/mo) | ETA | Notes
