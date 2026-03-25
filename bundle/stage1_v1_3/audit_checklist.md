# Stage1_v1.3 Audit Checklist

1. Precommit files exist in `prespec/stage1_v1_3/`.
2. `stage1_prespec.json` hash recorded in `sha256_manifest.txt`.
3. Data CSV hash recorded in `sha256_manifest.txt`.
4. `stage1.py` hash recorded in `sha256_manifest.txt`.
5. `stage1_env.txt` hash recorded in `sha256_manifest.txt`.
6. Files are committed to public GitHub in one commit.
7. `commit_time_utc` extracted from GitHub metadata.
8. `run_start_time_utc` captured before execution starts.
9. Mandatory check: `commit_time_utc < run_start_time_utc`.
10. Runtime hashes match precommitted hashes exactly.
11. Sufficiency check completed.
12. ATR gate run with seed `42001` and declared permutation counts.
13. NFAM test run with seed `42002` only if ATR gate passes.
14. Terminal state assigned from Stage1_v1.3 allowed states only.
15. `run_report_template.json` filled and saved as final run report.
