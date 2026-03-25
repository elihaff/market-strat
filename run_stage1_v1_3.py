import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from stage1 import (
    assign_volatility_buckets,
    build_features,
    build_quality_flags,
    extract_events,
    load_data,
)

PROTOCOL_ID = "Stage1_v1.3"
ATR_GATE_ALPHA = 0.01
NFAM_ALPHA = 0.05
ATR_GATE_SEED = 42001
NFAM_SEED = 42002
BASE_PERMUTATIONS = 100000
BOUNDARY_PERMUTATIONS = 1000000
H = 12


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_iso(s):
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError("commit_time_utc must include timezone")
    return dt.astimezone(timezone.utc)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_manifest(path):
    manifest = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"Invalid manifest line: {line}")
            name, digest = parts[0], parts[1]
            manifest[name] = digest
    return manifest


def median_difference(x, y):
    return float(np.nanmedian(x) - np.nanmedian(y))


def stratified_permutation_pvalue(values, groups, buckets, n_permutations, seed):
    values = np.asarray(values, dtype=float)
    groups = np.asarray(groups)
    buckets = np.asarray(buckets)

    observed = median_difference(values[groups == "A"], values[groups == "B"])
    rng = np.random.default_rng(seed)
    perm_stats = np.empty(n_permutations, dtype=float)

    bucket_indices = {b: np.where(buckets == b)[0] for b in np.unique(buckets)}

    for i in range(n_permutations):
        perm_groups = groups.copy()
        for idx in bucket_indices.values():
            perm_groups[idx] = rng.permutation(perm_groups[idx])

        a_vals = values[perm_groups == "A"]
        b_vals = values[perm_groups == "B"]
        if a_vals.size == 0 or b_vals.size == 0:
            perm_stats[i] = np.nan
        else:
            perm_stats[i] = median_difference(a_vals, b_vals)

    valid = perm_stats[~np.isnan(perm_stats)]
    if valid.size == 0:
        return observed, np.nan, np.nan

    p = (np.sum(np.abs(valid) >= abs(observed)) + 1) / (valid.size + 1)
    mcse = float(np.sqrt(p * (1.0 - p) / valid.size))
    return observed, float(p), mcse


def run_test_with_boundary(values, groups, buckets, alpha_test, seed):
    stat, p, mcse = stratified_permutation_pvalue(
        values, groups, buckets, BASE_PERMUTATIONS, seed
    )
    rerun = False
    if np.isnan(p):
        return stat, p, mcse, rerun

    if abs(p - alpha_test) <= 2.0 * mcse:
        stat, p, mcse = stratified_permutation_pvalue(
            values, groups, buckets, BOUNDARY_PERMUTATIONS, seed
        )
        rerun = True
    return stat, p, mcse, rerun


def main():
    run_start_time_utc = utc_now_iso()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default="EURUSD_15 Mins_Bid_2019.01.01_2026.03.25.csv",
    )
    parser.add_argument(
        "--prespec",
        default="prespec/stage1_v1_3/stage1_prespec.json",
    )
    parser.add_argument(
        "--manifest",
        default="prespec/stage1_v1_3/sha256_manifest.txt",
    )
    parser.add_argument(
        "--env-file",
        default="prespec/stage1_v1_3/stage1_env.txt",
    )
    parser.add_argument(
        "--stage1-script",
        default="stage1.py",
    )
    parser.add_argument("--github-repo", default="")
    parser.add_argument("--github-commit-hash", required=True)
    parser.add_argument("--commit-time-utc", required=True)
    parser.add_argument(
        "--report-template",
        default="bundle/stage1_v1_3/run_report_template.json",
    )
    parser.add_argument(
        "--report-out",
        default="bundle/stage1_v1_3/run_report.json",
    )
    args = parser.parse_args()

    with open(args.report_template, "r", encoding="utf-8") as f:
        report = json.load(f)

    report["protocol_id"] = PROTOCOL_ID
    report["precommit"]["github_repo"] = args.github_repo
    report["precommit"]["github_commit_hash"] = args.github_commit_hash
    report["precommit"]["commit_time_utc"] = args.commit_time_utc
    report["runtime"]["run_start_time_utc"] = run_start_time_utc

    commit_dt = parse_utc_iso(args.commit_time_utc)
    run_dt = parse_utc_iso(run_start_time_utc)
    timestamp_ok = commit_dt < run_dt
    report["audit_checks"]["timestamp_check_commit_before_run"] = bool(timestamp_ok)

    manifest = parse_manifest(args.manifest)
    expected = {
        "stage1_prespec.json": manifest.get("stage1_prespec.json", ""),
        "data_csv": manifest.get("data_csv", ""),
        "stage1.py": manifest.get("stage1.py", ""),
        "stage1_env.txt": manifest.get("stage1_env.txt", ""),
    }
    actual = {
        "stage1_prespec.json": sha256_file(args.prespec),
        "data_csv": sha256_file(args.csv),
        "stage1.py": sha256_file(args.stage1_script),
        "stage1_env.txt": sha256_file(args.env_file),
    }

    report["audit_checks"]["hash_match_prespec"] = actual["stage1_prespec.json"] == expected["stage1_prespec.json"]
    report["audit_checks"]["hash_match_data_csv"] = actual["data_csv"] == expected["data_csv"]
    report["audit_checks"]["hash_match_stage1_py"] = actual["stage1.py"] == expected["stage1.py"]
    report["audit_checks"]["hash_match_env_manifest"] = actual["stage1_env.txt"] == expected["stage1_env.txt"]

    if not (
        report["audit_checks"]["timestamp_check_commit_before_run"]
        and report["audit_checks"]["hash_match_prespec"]
        and report["audit_checks"]["hash_match_data_csv"]
        and report["audit_checks"]["hash_match_stage1_py"]
        and report["audit_checks"]["hash_match_env_manifest"]
    ):
        report["terminal_state"] = "invalid_non_auditable"
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return

    df = load_data(args.csv)
    features = build_features(df)
    quality_flags = build_quality_flags(df)
    total_candidates, exclusions, events_df = extract_events(df, features, quality_flags)

    report["sufficiency"]["total_candidates"] = int(total_candidates)
    report["sufficiency"]["valid_events"] = int(len(events_df))
    report["sufficiency"]["exclusions_by_type"]["timestamp_gaps"] = int(exclusions["timestamp_gaps"])
    report["sufficiency"]["exclusions_by_type"]["weekend_gaps"] = int(exclusions["weekend_gaps"])
    report["sufficiency"]["exclusions_by_type"]["other_anomaly_rules"] = int(exclusions["other_anomaly_rules"])

    if events_df.empty:
        report["sufficiency"]["sufficient_for_testing"] = False
        report["terminal_state"] = "invalid_insufficient_data"
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return

    events_df, _ = assign_volatility_buckets(events_df, len(df))

    group_counts = events_df["group"].value_counts().to_dict()
    report["sufficiency"]["group_a_count"] = int(group_counts.get("A", 0))
    report["sufficiency"]["group_b_count"] = int(group_counts.get("B", 0))

    overall = events_df["bucket"].value_counts().sort_index()
    report["sufficiency"]["bucket_counts_overall"] = {
        f"bucket_{int(k)}": int(v) for k, v in overall.items()
    }

    by_group = events_df.groupby(["group", "bucket"]).size()
    report["sufficiency"]["bucket_counts_by_group"] = {
        f"group_{g}_bucket_{int(b)}": int(v) for (g, b), v in by_group.items()
    }

    by_half = events_df.groupby(["half", "bucket"]).size()
    report["sufficiency"]["bucket_counts_by_half"] = {
        f"{h}_half_bucket_{int(b)}": int(v) for (h, b), v in by_half.items()
    }

    if report["sufficiency"]["group_a_count"] == 0 or report["sufficiency"]["group_b_count"] == 0:
        report["sufficiency"]["sufficient_for_testing"] = False
        report["terminal_state"] = "invalid_insufficient_data"
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return

    report["sufficiency"]["sufficient_for_testing"] = True

    atr_values = events_df["atr_t"].to_numpy()
    groups = events_df["group"].to_numpy()
    buckets = events_df["bucket"].to_numpy()

    _, p_atr, mcse_atr, atr_rerun = run_test_with_boundary(
        atr_values, groups, buckets, ATR_GATE_ALPHA, ATR_GATE_SEED
    )
    report["atr_gate"]["p_value"] = p_atr
    report["atr_gate"]["mcse"] = mcse_atr
    report["atr_gate"]["boundary_rerun_used"] = atr_rerun

    if np.isnan(p_atr):
        report["terminal_state"] = "invalid_insufficient_data"
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return

    gate_pass = p_atr > ATR_GATE_ALPHA
    report["atr_gate"]["gate_pass"] = bool(gate_pass)

    if not gate_pass:
        report["terminal_state"] = "invalid_for_inference"
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return

    close_arr = df["close"].to_numpy()
    t_vals = events_df["t"].to_numpy()
    event_idx = events_df["event_index"].to_numpy()
    atr = events_df["atr_t"].to_numpy()
    numerator = np.abs(close_arr[t_vals + H] - close_arr[event_idx])
    nfam = np.divide(
        numerator,
        atr,
        out=np.full(numerator.shape, np.nan, dtype=float),
        where=atr != 0,
    )
    events_df = events_df.copy()
    events_df["nfam"] = nfam

    nfam_a = events_df.loc[events_df["group"] == "A", "nfam"].to_numpy()
    nfam_b = events_df.loc[events_df["group"] == "B", "nfam"].to_numpy()
    if np.all(np.isnan(nfam_a)) or np.all(np.isnan(nfam_b)):
        report["terminal_state"] = "invalid_insufficient_data"
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return

    report["nfam_test"]["median_nfam_group_a"] = float(np.nanmedian(nfam_a))
    report["nfam_test"]["median_nfam_group_b"] = float(np.nanmedian(nfam_b))

    stat_nfam, p_nfam, mcse_nfam, nfam_rerun = run_test_with_boundary(
        events_df["nfam"].to_numpy(),
        events_df["group"].to_numpy(),
        events_df["bucket"].to_numpy(),
        NFAM_ALPHA,
        NFAM_SEED,
    )
    if np.isnan(p_nfam):
        report["terminal_state"] = "invalid_insufficient_data"
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
        return

    report["nfam_test"]["difference_a_minus_b"] = float(stat_nfam)
    report["nfam_test"]["p_value"] = float(p_nfam)
    report["nfam_test"]["mcse"] = float(mcse_nfam)
    report["nfam_test"]["boundary_rerun_used"] = bool(nfam_rerun)

    report["terminal_state"] = "reject_null" if p_nfam <= NFAM_ALPHA else "fail_to_reject_null"

    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.report_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
