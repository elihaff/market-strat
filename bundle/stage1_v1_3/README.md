# Stage1_v1.3 Reproducibility Bundle

## Created artifacts (Step 1)
- `prespec/stage1_v1_3/stage1_prespec.json`
- `prespec/stage1_v1_3/stage1_env.txt`
- `prespec/stage1_v1_3/sha256_manifest.txt`

## Run-report package (Step 5 template)
- `bundle/stage1_v1_3/run_report_template.json`
- `bundle/stage1_v1_3/audit_checklist.md`

## Required GitHub pre-commit action
Commit the full folder `prespec/stage1_v1_3/` in one public GitHub commit.

Capture and store:
- `github_commit_hash`
- `commit_time_utc` from GitHub metadata (`commit.committer.date`)

## Execution-time requirements
Before running, capture:
- `run_start_time_utc` (system UTC timestamp)

Mandatory audit check:
- `commit_time_utc < run_start_time_utc`

Then validate runtime SHA256 values against `sha256_manifest.txt`.

## Terminal states (Stage1_v1.3)
- `invalid_non_auditable`
- `invalid_insufficient_data`
- `invalid_for_inference`
- `reject_null`
- `fail_to_reject_null`
