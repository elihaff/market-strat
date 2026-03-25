# Stage 1 Session Log (v1.0 -> v1.3)

All times are UTC/GMT.

## Version Timeline

| Version | Change Timestamp (UTC) | Timestamp Source | What Changed | Status |
|---|---|---|---|---|
| Stage1_v1.0 | 2026-03-25 16:50:49 | `stage1.py` file modification time | Implemented executable Stage 1 pipeline from locked protocol in `stage1.py`; added deterministic script execution path and diagnostics/output flow. | Baseline implementation complete |
| Stage1_v1.1 | 2026-03-25 (time not persisted) | Chat-session revision only (no dedicated file artifact saved at that step) | Added hardening draft: pre-spec concept, inferential rule formalization, and initial denominator-coupling validity gate. | Draft hardening (reviewed, not final) |
| Stage1_v1.2 | 2026-03-25 (time not persisted) | Chat-session revision only (no dedicated file artifact saved at that step) | Fixed no-discretion structure: single external pre-commit path, strengthened ATR gate (stratified permutation framing), contradiction-free terminal states (at that step). | Near-final hardening (reviewed, not final) |
| Stage1_v1.3 | 2026-03-25 17:04:13 | `prespec/stage1_v1_3/stage1_prespec.json` file modification time | Finalized accepted exploratory protocol: strict `commit_time_utc < run_start_time_utc`, explicit fixed seeds, separated `invalid_insufficient_data`, and exhaustive terminal taxonomy. | Structurally accepted exploratory protocol |

## Artifact Timestamps (v1.3 package)

| Artifact | Last Modified (UTC) |
|---|---|
| `prespec/stage1_v1_3/stage1_prespec.json` | 2026-03-25 17:04:13 |
| `prespec/stage1_v1_3/stage1_env.txt` | 2026-03-25 17:04:23 |
| `prespec/stage1_v1_3/sha256_manifest.txt` | 2026-03-25 17:04:30 |

## Hash Snapshot (current)

- `stage1.py`: `1a41342635a792368bcde1a19fc308e2d0966ca7fabc38180182fdbbade6d61f`
- `stage1_prespec.json`: `88d190c97e6a4064670d10c8b3debda883a735a79a8c4fff26512e5f0df72833`
- `stage1_env.txt`: `27454a6bec647989688fbb79279397a5dc99544e93317c1c2337d01e2582bb2d`
- `EURUSD_15 Mins_Bid_2019.01.01_2026.03.25.csv`: `bae88f1e0dc7730fb0be85ddc285a9001b46189b4eef83cb1ba0e660a1e0513b`

## Notes

- v1.1 and v1.2 were protocol refinements performed in-session but not persisted as separate versioned files at the moment they were defined, so exact clock-time cannot be proven from filesystem metadata.
