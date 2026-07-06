from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd


def add_cross_sectional_zscores(
    df: pd.DataFrame,
    value_col: str = "can",
    group_cols: list[str] | None = None,
    output_col: str | None = None,
) -> pd.DataFrame:
    if group_cols is None:
        group_cols = ["date"]
    if output_col is None:
        output_col = f"z_score_{value_col}"

    out = df.copy()

    def _z(s: pd.Series) -> pd.Series:
        std = s.std(ddof=0)
        if pd.isna(std) or std == 0:
            return pd.Series(np.zeros(len(s)), index=s.index)
        return (s - s.mean()) / std

    out[output_col] = out.groupby(group_cols)[value_col].transform(_z)
    return out


def add_week_bucket(df: pd.DataFrame, period: str = "W-FRI", output_col: str = "week_end") -> pd.DataFrame:
    out = df.copy()
    out[output_col] = out["date"].dt.to_period(period).dt.end_time.dt.normalize()
    return out


def enrich_dataset(df: pd.DataFrame, week_period: str = "W-FRI") -> pd.DataFrame:
    out = df.copy()
    if "z_score_can" not in out.columns:
        out = add_cross_sectional_zscores(out, value_col="can", group_cols=["date"], output_col="z_score_can")
    if "z_score_payup" not in out.columns:
        out = add_cross_sectional_zscores(out, value_col="payup", group_cols=["date"], output_col="z_score_payup")
    if "week_end" not in out.columns:
        out = add_week_bucket(out, period=week_period, output_col="week_end")
    return out


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    latest_date = df["date"].max()
    return df[df["date"] == latest_date].copy()


def summarize_stories(df: pd.DataFrame) -> pd.DataFrame:
    out = enrich_dataset(df)
    grouped = out.groupby(["story", "story_bucket", "geo", "coupon", "year", "issuer"], dropna=False)
    summary = grouped.agg(
        observations=("can", "size"),
        first_date=("date", "min"),
        latest_date=("date", "max"),
        low_can=("can", "min"),
        high_can=("can", "max"),
        mean_can=("can", "mean"),
        std_can=("can", lambda s: float(s.std(ddof=0) if len(s) else 0.0)),
        low_payup=("payup", "min"),
        high_payup=("payup", "max"),
        mean_payup=("payup", "mean"),
        std_payup=("payup", lambda s: float(s.std(ddof=0) if len(s) else 0.0)),
        low_zscore_can=("z_score_can", "min"),
        high_zscore_can=("z_score_can", "max"),
        mean_zscore_can=("z_score_can", "mean"),
        low_zscore_payup=("z_score_payup", "min"),
        high_zscore_payup=("z_score_payup", "max"),
        mean_zscore_payup=("z_score_payup", "mean"),
    ).reset_index()
    return summary.sort_values(["issuer", "story_bucket", "year", "coupon", "story"]).reset_index(drop=True)


def build_latest_rankings(df: pd.DataFrame) -> pd.DataFrame:
    out = enrich_dataset(df)
    snap = latest_snapshot(out)
    cols = [
        "date",
        "story",
        "story_bucket",
        "geo",
        "coupon",
        "year",
        "issuer",
        "can",
        "payup",
        "spread",
        "z_score_can",
        "z_score_payup",
    ]
    snap = snap[cols].copy()
    snap["rank_best_zscore_can"] = snap["z_score_can"].rank(method="dense", ascending=True)
    snap["rank_worst_zscore_can"] = snap["z_score_can"].rank(method="dense", ascending=False)
    snap["rank_best_payup"] = snap["payup"].rank(method="dense", ascending=True)
    snap["rank_worst_payup"] = snap["payup"].rank(method="dense", ascending=False)
    return snap.sort_values("story").reset_index(drop=True)


def pick_best_and_worst(
    rankings: pd.DataFrame,
    metric: str,
    n: int = 5,
    ascending_best: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if metric not in rankings.columns:
        raise ValueError(f"Metric '{metric}' not found in rankings.")
    ordered = rankings.sort_values(metric, ascending=ascending_best)
    best = ordered.head(n).copy()
    worst = ordered.tail(n).sort_values(metric, ascending=not ascending_best).copy()
    return best, worst


def time_series_for_stories(df: pd.DataFrame, stories: list[str], metric: str) -> pd.DataFrame:
    out = enrich_dataset(df)
    return (
        out[out["story"].isin(stories)][["date", "story", metric]]
        .sort_values(["story", "date"])
        .reset_index(drop=True)
    )


def weekly_metric_by_coupon(df: pd.DataFrame, metric: str = "payup", week_period: str = "W-FRI") -> pd.DataFrame:
    out = enrich_dataset(df, week_period=week_period)
    grouped = (
        out.groupby(["week_end", "story_bucket", "issuer", "year", "coupon"], dropna=False)[metric]
        .mean()
        .reset_index()
    )
    grouped["coupon_label"] = grouped["coupon"].map(
        lambda x: "NA" if pd.isna(x) else f"{float(x):.1f}"
    )
    return grouped.sort_values(["story_bucket", "year", "coupon", "week_end"]).reset_index(drop=True)


def weekly_metric_by_year(df: pd.DataFrame, metric: str = "payup", week_period: str = "W-FRI") -> pd.DataFrame:
    out = enrich_dataset(df, week_period=week_period)
    grouped = (
        out.groupby(["week_end", "story_bucket", "issuer", "coupon", "year"], dropna=False)[metric]
        .mean()
        .reset_index()
    )
    grouped["year_label"] = grouped["year"].astype(str)
    return grouped.sort_values(["story_bucket", "coupon", "year", "week_end"]).reset_index(drop=True)


def geo_comparison_frame(df: pd.DataFrame, metric: str = "payup", week_period: str = "W-FRI") -> pd.DataFrame:
    out = enrich_dataset(df, week_period=week_period)
    grouped = (
        out.groupby(["week_end", "story_bucket", "issuer", "year", "coupon", "geo"], dropna=False)[metric]
        .mean()
        .reset_index()
    )
    return grouped.sort_values(["story_bucket", "year", "coupon", "geo", "week_end"]).reset_index(drop=True)


def enumerate_geo_pairs(
    df: pd.DataFrame,
    metric: str = "payup",
    week_period: str = "W-FRI",
    min_points: int = 4,
    max_pairs: int | None = None,
) -> list[dict[str, object]]:
    geo_df = geo_comparison_frame(df, metric=metric, week_period=week_period)
    pairs: list[dict[str, object]] = []

    grouped = geo_df.groupby(["story_bucket", "issuer", "year", "coupon"], dropna=False)
    for (story_bucket, issuer, year, coupon), group in grouped:
        geos = sorted(str(g) for g in group["geo"].dropna().unique())
        if len(geos) < 2:
            continue
        for geo_a, geo_b in combinations(geos, 2):
            pair_subset = group[group["geo"].isin([geo_a, geo_b])]
            points_per_geo = pair_subset.groupby("geo")["week_end"].nunique()
            if points_per_geo.min() < min_points:
                continue
            pairs.append(
                {
                    "story_bucket": story_bucket,
                    "issuer": issuer,
                    "year": year,
                    "coupon": coupon,
                    "geo_a": geo_a,
                    "geo_b": geo_b,
                }
            )
            if max_pairs is not None and len(pairs) >= max_pairs:
                return pairs
    return pairs
