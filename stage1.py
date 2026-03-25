import argparse
import numpy as np
import pandas as pd
from scipy import stats

L = 20
L_REF = 100
THETA_C = 0.30
ALPHA = 0.10
H = 12
N_PERMUTATIONS = 10000
RNG_SEED = 42


def normalize_columns(columns):
    return [c.strip().lower().replace(" ", "_") for c in columns]


def load_data(csv_path):
    df = pd.read_csv(csv_path)
    df.columns = normalize_columns(df.columns)

    column_map = {
        "time_(eet)": "timestamp",
        "timestamp": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
    }

    renamed = {}
    for col in df.columns:
        if col in column_map:
            renamed[col] = column_map[col]

    df = df.rename(columns=renamed)

    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[required].copy()

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="%Y.%m.%d %H:%M:%S", errors="coerce"
    )

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    return df


def build_features(df):
    prev_close = df["close"].shift(1)

    tr_components = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    tr = tr_components.max(axis=1)
    atr = tr.rolling(L, min_periods=L).mean()

    rolling_high_short = df["high"].rolling(L, min_periods=L).max()
    rolling_low_short = df["low"].rolling(L, min_periods=L).min()
    range_short = rolling_high_short - rolling_low_short

    rolling_high_ref = df["high"].rolling(L_REF, min_periods=L_REF).max()
    rolling_low_ref = df["low"].rolling(L_REF, min_periods=L_REF).min()
    range_ref = rolling_high_ref - rolling_low_ref

    cr = range_short / range_ref
    compression = cr <= THETA_C

    upper = rolling_high_short
    lower = rolling_low_short

    log_returns = np.log(df["close"] / df["close"].shift(1))
    rv = log_returns.rolling(L, min_periods=L).std(ddof=0)

    return {
        "atr": atr,
        "upper": upper,
        "lower": lower,
        "compression": compression,
        "rv": rv,
    }


def build_quality_flags(df):
    duplicate_timestamp = df["timestamp"].duplicated(keep=False)
    missing_ohlc = df[["open", "high", "low", "close"]].isna().any(axis=1)
    high_below_low = df["high"] < df["low"]
    open_outside = (df["open"] < df["low"]) | (df["open"] > df["high"])
    close_outside = (df["close"] < df["low"]) | (df["close"] > df["high"])

    invalid_bar = (
        duplicate_timestamp
        | missing_ohlc
        | high_below_low
        | open_outside
        | close_outside
        | df["timestamp"].isna()
    )

    ts_diff = df["timestamp"].diff()
    gap_pair = ts_diff > pd.Timedelta(minutes=15)

    prev_ts = df["timestamp"].shift(1)
    weekend_gap_pair = (
        gap_pair
        & (prev_ts.dt.weekday == 4)
        & (df["timestamp"].dt.weekday == 0)
    )
    timestamp_gap_pair = gap_pair & (~weekend_gap_pair)

    return {
        "invalid_bar": invalid_bar,
        "weekend_gap_pair": weekend_gap_pair,
        "timestamp_gap_pair": timestamp_gap_pair,
    }


def extract_events(df, features, quality_flags):
    n = len(df)

    atr = features["atr"]
    upper = features["upper"]
    lower = features["lower"]
    compression = features["compression"]
    rv = features["rv"]

    invalid_bar = quality_flags["invalid_bar"]
    weekend_gap_pair = quality_flags["weekend_gap_pair"]
    timestamp_gap_pair = quality_flags["timestamp_gap_pair"]

    total_candidates = 0
    exclusions = {
        "timestamp_gaps": 0,
        "weekend_gaps": 0,
        "other_anomaly_rules": 0,
    }

    filtered_candidates = []

    start_t = L_REF - 1
    end_t = n - H - 1

    for t in range(start_t, end_t + 1):
        atr_t = atr.iat[t]
        u_t = upper.iat[t]
        d_t = lower.iat[t]

        if pd.isna(atr_t) or pd.isna(u_t) or pd.isna(d_t):
            continue

        close_next = df["close"].iat[t + 1]
        breakout_up = close_next > (u_t + ALPHA * atr_t)
        breakout_down = close_next < (d_t - ALPHA * atr_t)

        if not (breakout_up or breakout_down):
            continue

        total_candidates += 1

        group = "A" if bool(compression.iat[t]) else "B"

        w_start = t - (L_REF - 1)
        w_end = t + H

        has_timestamp_gap = bool(timestamp_gap_pair.iloc[w_start + 1 : w_end + 1].any())
        has_weekend_gap = bool(weekend_gap_pair.iloc[w_start + 1 : w_end + 1].any())
        has_invalid_bar = bool(invalid_bar.iloc[w_start : w_end + 1].any())

        if has_timestamp_gap:
            exclusions["timestamp_gaps"] += 1
            continue
        if has_weekend_gap:
            exclusions["weekend_gaps"] += 1
            continue
        if has_invalid_bar:
            exclusions["other_anomaly_rules"] += 1
            continue

        filtered_candidates.append(
            {
                "t": t,
                "event_index": t + 1,
                "group": group,
                "atr_t": atr_t,
                "rv_t": rv.iat[t],
            }
        )

    separated_events = []
    last_event_index = -10**12

    for ev in filtered_candidates:
        event_index = ev["event_index"]
        if event_index <= last_event_index + H:
            continue
        separated_events.append(ev)
        last_event_index = event_index

    return total_candidates, exclusions, pd.DataFrame(separated_events)


def assign_volatility_buckets(events_df, n_rows):
    if events_df.empty:
        raise ValueError("No valid events after filtering and separation.")

    half_point = n_rows // 2
    events_df = events_df.copy()
    events_df["half"] = np.where(events_df["event_index"] < half_point, "first", "second")

    rv_first_half = events_df.loc[events_df["half"] == "first", "rv_t"].dropna().to_numpy()

    if rv_first_half.size == 0:
        raise ValueError("No first-half events available for volatility bucket cutpoints.")

    cutpoints = np.quantile(rv_first_half, [0.2, 0.4, 0.6, 0.8])
    if not np.all(np.diff(cutpoints) > 0):
        raise ValueError("Volatility cutpoints are not strictly increasing.")

    bins = np.concatenate(([-np.inf], cutpoints, [np.inf]))
    events_df["bucket"] = pd.cut(
        events_df["rv_t"], bins=bins, labels=[1, 2, 3, 4, 5], include_lowest=True
    ).astype(int)

    return events_df, cutpoints


def median_difference(group_a, group_b):
    return float(np.nanmedian(group_a) - np.nanmedian(group_b))


def stratified_permutation_test(events_df, n_permutations=N_PERMUTATIONS, seed=RNG_SEED):
    if events_df.empty:
        raise ValueError("No events to test.")

    nfam = events_df["nfam"].to_numpy()
    groups = events_df["group"].to_numpy()
    buckets = events_df["bucket"].to_numpy()

    a_mask = groups == "A"
    b_mask = groups == "B"

    if not a_mask.any() or not b_mask.any():
        raise ValueError("Both Group A and Group B must have at least one event.")

    observed = median_difference(nfam[a_mask], nfam[b_mask])

    rng = np.random.default_rng(seed)
    perm_stats = np.empty(n_permutations, dtype=float)

    bucket_indices = {
        b: np.where(buckets == b)[0]
        for b in np.unique(buckets)
    }

    for i in range(n_permutations):
        perm_groups = groups.copy()
        for idx in bucket_indices.values():
            perm_groups[idx] = rng.permutation(perm_groups[idx])

        perm_a = nfam[perm_groups == "A"]
        perm_b = nfam[perm_groups == "B"]

        if perm_a.size == 0 or perm_b.size == 0:
            perm_stats[i] = np.nan
        else:
            perm_stats[i] = median_difference(perm_a, perm_b)

    valid_perm_stats = perm_stats[~np.isnan(perm_stats)]
    if valid_perm_stats.size == 0:
        raise ValueError("No valid permutations produced both groups.")

    p_value = (
        np.sum(np.abs(valid_perm_stats) >= abs(observed)) + 1
    ) / (valid_perm_stats.size + 1)

    return observed, float(p_value)


def print_diagnostics(total_candidates, exclusions, events_df):
    print("=== PRE-OUTCOME DIAGNOSTICS ===")
    print(f"total_candidates: {total_candidates}")
    print(f"valid_events: {len(events_df)}")

    group_counts = events_df["group"].value_counts().reindex(["A", "B"], fill_value=0)
    print(f"group_a_count: {int(group_counts['A'])}")
    print(f"group_b_count: {int(group_counts['B'])}")

    overall_bucket = events_df["bucket"].value_counts().sort_index().reindex([1, 2, 3, 4, 5], fill_value=0)
    print("bucket_counts_overall:")
    for bucket, count in overall_bucket.items():
        print(f"  bucket_{bucket}: {int(count)}")

    by_group = (
        events_df.groupby(["group", "bucket"]).size().unstack(fill_value=0)
        .reindex(index=["A", "B"], columns=[1, 2, 3, 4, 5], fill_value=0)
    )
    print("bucket_counts_by_group:")
    for group in ["A", "B"]:
        for bucket in [1, 2, 3, 4, 5]:
            print(f"  group_{group}_bucket_{bucket}: {int(by_group.loc[group, bucket])}")

    by_half = (
        events_df.groupby(["half", "bucket"]).size().unstack(fill_value=0)
        .reindex(index=["first", "second"], columns=[1, 2, 3, 4, 5], fill_value=0)
    )
    print("bucket_counts_by_half:")
    for half in ["first", "second"]:
        for bucket in [1, 2, 3, 4, 5]:
            print(f"  {half}_half_bucket_{bucket}: {int(by_half.loc[half, bucket])}")

    print("exclusions_by_type:")
    print(f"  timestamp_gaps: {exclusions['timestamp_gaps']}")
    print(f"  weekend_gaps: {exclusions['weekend_gaps']}")
    print(f"  other_anomaly_rules: {exclusions['other_anomaly_rules']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default="EURUSD_15 Mins_Bid_2019.01.01_2026.03.25.csv",
        help="Path to Dukascopy EUR/USD 15-minute CSV",
    )
    args = parser.parse_args()

    df = load_data(args.csv)
    features = build_features(df)
    quality_flags = build_quality_flags(df)

    total_candidates, exclusions, events_df = extract_events(df, features, quality_flags)
    events_df, _ = assign_volatility_buckets(events_df, len(df))

    print_diagnostics(total_candidates, exclusions, events_df)

    close_arr = df["close"].to_numpy()
    events_df = events_df.copy()
    numerator = np.abs(
        close_arr[events_df["t"].to_numpy() + H] - close_arr[events_df["event_index"].to_numpy()]
    )
    denominator = events_df["atr_t"].to_numpy()
    events_df["nfam"] = np.divide(
        numerator,
        denominator,
        out=np.full(numerator.shape, np.nan, dtype=float),
        where=denominator != 0,
    )

    median_a = float(np.nanmedian(events_df.loc[events_df["group"] == "A", "nfam"].to_numpy()))
    median_b = float(np.nanmedian(events_df.loc[events_df["group"] == "B", "nfam"].to_numpy()))
    diff, p_value = stratified_permutation_test(events_df)

    print("=== OUTCOME ===")
    print(f"median_nfam_group_a: {median_a}")
    print(f"median_nfam_group_b: {median_b}")
    print(f"difference_median_a_minus_b: {diff}")
    print(f"p_value_two_sided: {p_value}")


if __name__ == "__main__":
    main()
