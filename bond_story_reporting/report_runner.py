from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from .analytics import (
    build_latest_rankings,
    enrich_dataset,
    enumerate_geo_pairs,
    geo_comparison_frame,
    pick_best_and_worst,
    summarize_stories,
    time_series_for_stories,
    weekly_metric_by_coupon,
    weekly_metric_by_year,
)
from .charts import (
    save_geo_pair_chart,
    save_ranked_bar,
    save_story_lines,
    save_story_versus,
    save_weekly_coupon_chart,
    save_weekly_year_chart,
)
from .config import get_default_config
from .utils import ensure_dir, now_iso, write_json

ProgressCallback = Callable[[int, int, str], None]


def _merge_config(base: dict, overrides: dict | None) -> dict:
    merged = dict(base)
    if not overrides:
        return merged
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _to_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def _resolve_rank_by(value: object) -> tuple[str, str]:
    raw = str(value or "").strip().lower()
    aliases = {
        "z_score_can": "z_score_can",
        "zscore": "z_score_can",
        "z-score": "z_score_can",
        "payup": "payup",
        "current_payup": "payup",
        "current pay-up": "payup",
        "current payup": "payup",
        "mean": "mean_payup",
        "mean_payup": "mean_payup",
        "mean pay-up": "mean_payup",
        "mean payup": "mean_payup",
    }
    metric = aliases.get(raw, "z_score_can")
    labels = {
        "z_score_can": "Z-Score",
        "payup": "Current Pay-up",
        "mean_payup": "Mean Pay-up",
    }
    return metric, labels[metric]


def _best_worst_by_mean(summary: pd.DataFrame, n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    ranked = (
        summary.groupby("story", dropna=False)["mean_payup"]
        .mean()
        .reset_index()
        .sort_values("mean_payup", ascending=True)
        .reset_index(drop=True)
    )
    best = ranked.head(n).copy()
    worst = ranked.tail(n).sort_values("mean_payup", ascending=False).copy()
    return best, worst


def run_weekly_reports(
    df: pd.DataFrame,
    output_dir: str | Path,
    midweek_rerun: bool = False,
    config_overrides: dict | None = None,
    progress_cb: ProgressCallback | None = None,
) -> dict:
    cfg = _merge_config(get_default_config(), config_overrides)

    week_period = cfg.get("weekly_rollup", {}).get("period", "W-FRI")
    df = enrich_dataset(df, week_period=week_period)

    years_filter = cfg.get("filters", {}).get("years", [])
    if years_filter:
        df = df[df["year"].isin(years_filter)]

    geos_filter = cfg.get("filters", {}).get("geos", [])
    if geos_filter:
        df = df[df["geo"].isin(geos_filter)]

    coupons_filter = cfg.get("filters", {}).get("coupons", [])
    if coupons_filter:
        df = df[df["coupon"].isin(coupons_filter)]

    if df.empty:
        raise ValueError("No records available after applying filters.")

    output_options = cfg.get("output_options", {})
    generate_excel_stats = _to_bool(output_options.get("generate_excel_stats"), default=True)
    generate_individual_charts = _to_bool(output_options.get("generate_individual_charts"), default=True)
    generate_versus_charts = _to_bool(output_options.get("generate_versus_charts"), default=True)

    output_dir = ensure_dir(output_dir)
    tables_dir = Path(output_dir) / "tables"
    if generate_excel_stats:
        ensure_dir(tables_dir)
    charts_dir = Path(output_dir) / "charts"
    if generate_individual_charts or generate_versus_charts:
        ensure_dir(charts_dir)
    z_dir = charts_dir / "zscore"
    p_dir = charts_dir / "payup"
    v_dir = charts_dir / "versus"
    focus_dir = charts_dir / "focus"
    coupon_dir = charts_dir / "coupon_packs"
    year_dir = charts_dir / "year_packs"
    geo_dir = charts_dir / "geo_pairs"

    summary = summarize_stories(df)
    rankings = build_latest_rankings(df)
    weekly_coupon = weekly_metric_by_coupon(df, metric="payup", week_period=week_period)
    weekly_year = weekly_metric_by_year(df, metric="payup", week_period=week_period)
    geo_weekly = geo_comparison_frame(df, metric="payup", week_period=week_period)

    best_n = _to_int(cfg.get("best_n"), 5)
    worst_n = _to_int(cfg.get("worst_n"), 5)
    count_n = max(best_n, worst_n)
    rank_by, rank_by_label = _resolve_rank_by(cfg.get("rank_by"))

    z_best, z_worst = pick_best_and_worst(rankings, metric="z_score_can", n=count_n, ascending_best=True)
    p_best, p_worst = pick_best_and_worst(rankings, metric="payup", n=count_n, ascending_best=True)

    if rank_by == "mean_payup":
        focus_best, focus_worst = _best_worst_by_mean(summary, n=count_n)
        focus_bar_metric = "mean_payup"
        focus_ts_metric = "payup"
    else:
        focus_best, focus_worst = pick_best_and_worst(rankings, metric=rank_by, n=count_n, ascending_best=True)
        focus_bar_metric = rank_by
        focus_ts_metric = rank_by
    focus_rankings = pd.concat([focus_best, focus_worst], ignore_index=True)

    automation_cfg = cfg.get("automation", {})
    min_coupons = _to_int(automation_cfg.get("coupon_pack_min_coupons"), 2)
    min_years = _to_int(automation_cfg.get("year_pack_min_years"), 2)
    max_coupon_charts = _to_int(automation_cfg.get("max_coupon_pack_charts"), 250)
    max_year_charts = _to_int(automation_cfg.get("max_year_pack_charts"), 250)
    max_geo_pairs = _to_int(automation_cfg.get("max_geo_pairs"), 200)
    geo_pair_min_points = _to_int(automation_cfg.get("geo_pair_min_points"), 4)

    coupon_targets: list[tuple[str, str, int]] = []
    if generate_individual_charts:
        for (story_bucket, issuer, year), group in weekly_coupon.groupby(["story_bucket", "issuer", "year"], dropna=False):
            if group["coupon"].nunique() < min_coupons:
                continue
            coupon_targets.append((str(story_bucket), str(issuer), int(year)))
            if len(coupon_targets) >= max_coupon_charts:
                break

    year_targets: list[tuple[str, str, float]] = []
    if generate_individual_charts:
        for (story_bucket, issuer, coupon), group in weekly_year.groupby(["story_bucket", "issuer", "coupon"], dropna=False):
            if group["year"].nunique() < min_years:
                continue
            year_targets.append((str(story_bucket), str(issuer), float(coupon)))
            if len(year_targets) >= max_year_charts:
                break

    geo_pairs: list[dict[str, object]] = []
    if generate_individual_charts:
        geo_pairs = enumerate_geo_pairs(
            df,
            metric="payup",
            week_period=week_period,
            min_points=geo_pair_min_points,
            max_pairs=max_geo_pairs,
        )

    planned_steps = 1  # metadata write
    if generate_excel_stats:
        planned_steps += 8  # five csv, workbook, focus csv, focus worksheet
    if generate_individual_charts:
        planned_steps += 12  # z/payup and focus bars + timeseries
        planned_steps += len(coupon_targets) + len(year_targets) + len(geo_pairs)
    if generate_versus_charts:
        planned_steps += int(not z_best.empty and not z_worst.empty)
        planned_steps += int(not p_best.empty and not p_worst.empty)
        planned_steps += int(not focus_best.empty and not focus_worst.empty)
    planned_steps = max(planned_steps, 1)

    completed_steps = 0

    def _publish_progress(message: str) -> None:
        nonlocal completed_steps
        completed_steps += 1
        if progress_cb is not None:
            progress_cb(completed_steps, planned_steps, message)

    if progress_cb is not None:
        progress_cb(0, planned_steps, "Starting automation run...")

    if generate_excel_stats:
        summary.to_csv(tables_dir / "story_summary.csv", index=False)
        _publish_progress("Saved table: story_summary.csv")
        rankings.to_csv(tables_dir / "rankings_latest.csv", index=False)
        _publish_progress("Saved table: rankings_latest.csv")
        weekly_coupon.to_csv(tables_dir / "weekly_payup_by_coupon.csv", index=False)
        _publish_progress("Saved table: weekly_payup_by_coupon.csv")
        weekly_year.to_csv(tables_dir / "weekly_payup_by_year.csv", index=False)
        _publish_progress("Saved table: weekly_payup_by_year.csv")
        geo_weekly.to_csv(tables_dir / "weekly_payup_by_geo.csv", index=False)
        _publish_progress("Saved table: weekly_payup_by_geo.csv")

        with pd.ExcelWriter(tables_dir / "story_summary.xlsx", engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="story_summary", index=False)
            rankings.to_excel(writer, sheet_name="latest_rankings", index=False)
            weekly_coupon.to_excel(writer, sheet_name="weekly_by_coupon", index=False)
            weekly_year.to_excel(writer, sheet_name="weekly_by_year", index=False)
            geo_weekly.to_excel(writer, sheet_name="weekly_by_geo", index=False)
        _publish_progress("Saved workbook: story_summary.xlsx")

    if generate_individual_charts:
        save_ranked_bar(z_best, "z_score_can", "Best/Cheapest Stories by Z-score", "zscore_best.png", z_dir)
        _publish_progress("Chart: zscore_best.png")
        save_ranked_bar(z_worst, "z_score_can", "Worst/Richest Stories by Z-score", "zscore_worst.png", z_dir)
        _publish_progress("Chart: zscore_worst.png")
        save_ranked_bar(p_best, "payup", "Best/Cheapest Stories by Payup", "payup_best.png", p_dir)
        _publish_progress("Chart: payup_best.png")
        save_ranked_bar(p_worst, "payup", "Worst/Richest Stories by Payup", "payup_worst.png", p_dir)
        _publish_progress("Chart: payup_worst.png")

        z_best_ts = time_series_for_stories(df, z_best["story"].tolist(), "z_score_can")
        save_story_lines(z_best_ts, "z_score_can", z_dir, "Best/Cheapest Z-score Time Series", "zscore_best_timeseries.png")
        _publish_progress("Chart: zscore_best_timeseries.png")
        z_worst_ts = time_series_for_stories(df, z_worst["story"].tolist(), "z_score_can")
        save_story_lines(z_worst_ts, "z_score_can", z_dir, "Worst/Richest Z-score Time Series", "zscore_worst_timeseries.png")
        _publish_progress("Chart: zscore_worst_timeseries.png")
        p_best_ts = time_series_for_stories(df, p_best["story"].tolist(), "payup")
        save_story_lines(p_best_ts, "payup", p_dir, "Best/Cheapest Payup Time Series", "payup_best_timeseries.png")
        _publish_progress("Chart: payup_best_timeseries.png")
        p_worst_ts = time_series_for_stories(df, p_worst["story"].tolist(), "payup")
        save_story_lines(p_worst_ts, "payup", p_dir, "Worst/Richest Payup Time Series", "payup_worst_timeseries.png")
        _publish_progress("Chart: payup_worst_timeseries.png")

    versus_paths: list[str] = []
    if generate_versus_charts and not z_best.empty and not z_worst.empty:
        versus_paths.append(str(save_story_versus(df, "z_score_can", z_best.iloc[0]["story"], z_worst.iloc[0]["story"], v_dir)))
        _publish_progress("Versus chart: z-score")
    if generate_versus_charts and not p_best.empty and not p_worst.empty:
        versus_paths.append(str(save_story_versus(df, "payup", p_best.iloc[0]["story"], p_worst.iloc[0]["story"], v_dir)))
        _publish_progress("Versus chart: payup")

    if generate_individual_charts:
        save_ranked_bar(
            focus_best,
            focus_bar_metric,
            f"Best/Cheapest Stories by {rank_by_label}",
            "focus_best.png",
            focus_dir,
        )
        _publish_progress("Chart: focus_best.png")
        save_ranked_bar(
            focus_worst,
            focus_bar_metric,
            f"Worst/Richest Stories by {rank_by_label}",
            "focus_worst.png",
            focus_dir,
        )
        _publish_progress("Chart: focus_worst.png")

        focus_best_ts = time_series_for_stories(df, focus_best["story"].tolist(), focus_ts_metric)
        save_story_lines(
            focus_best_ts,
            focus_ts_metric,
            focus_dir,
            f"Best/Cheapest Time Series by {rank_by_label}",
            "focus_best_timeseries.png",
        )
        _publish_progress("Chart: focus_best_timeseries.png")
        focus_worst_ts = time_series_for_stories(df, focus_worst["story"].tolist(), focus_ts_metric)
        save_story_lines(
            focus_worst_ts,
            focus_ts_metric,
            focus_dir,
            f"Worst/Richest Time Series by {rank_by_label}",
            "focus_worst_timeseries.png",
        )
        _publish_progress("Chart: focus_worst_timeseries.png")

    focus_versus_path: str | None = None
    if generate_versus_charts and not focus_best.empty and not focus_worst.empty:
        focus_versus_path = str(
            save_story_versus(
                df,
                focus_ts_metric,
                str(focus_best.iloc[0]["story"]),
                str(focus_worst.iloc[0]["story"]),
                focus_dir,
            )
        )
        _publish_progress("Versus chart: focus")

    if generate_excel_stats:
        focus_rankings.to_csv(tables_dir / "rankings_focus.csv", index=False)
        _publish_progress("Saved table: rankings_focus.csv")
        with pd.ExcelWriter(tables_dir / "story_summary.xlsx", engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            focus_rankings.to_excel(writer, sheet_name="focus_rankings", index=False)
        _publish_progress("Updated workbook: focus_rankings")

    coupon_chart_paths: list[str] = []
    if generate_individual_charts:
        for idx, (story_bucket, issuer, year) in enumerate(coupon_targets, start=1):
            chart_path = save_weekly_coupon_chart(
                weekly_coupon,
                metric="payup",
                output_dir=coupon_dir,
                story_bucket=story_bucket,
                year=year,
                issuer=issuer,
            )
            if chart_path is not None:
                coupon_chart_paths.append(str(chart_path))
            _publish_progress(f"Coupon charts: {idx}/{len(coupon_targets)}")

    year_chart_paths: list[str] = []
    if generate_individual_charts:
        for idx, (story_bucket, issuer, coupon) in enumerate(year_targets, start=1):
            chart_path = save_weekly_year_chart(
                weekly_year,
                metric="payup",
                output_dir=year_dir,
                story_bucket=story_bucket,
                coupon=coupon,
                issuer=issuer,
            )
            if chart_path is not None:
                year_chart_paths.append(str(chart_path))
            _publish_progress(f"Year charts: {idx}/{len(year_targets)}")

    geo_chart_paths: list[str] = []
    if generate_individual_charts:
        for idx, pair in enumerate(geo_pairs, start=1):
            chart_path = save_geo_pair_chart(
                geo_weekly,
                metric="payup",
                output_dir=geo_dir,
                story_bucket=str(pair["story_bucket"]),
                year=int(pair["year"]),
                coupon=float(pair["coupon"]),
                geo_a=str(pair["geo_a"]),
                geo_b=str(pair["geo_b"]),
                issuer=str(pair["issuer"]),
            )
            if chart_path is not None:
                geo_chart_paths.append(str(chart_path))
            _publish_progress(f"Geo charts: {idx}/{len(geo_pairs)}")

    metadata = {
        "generated_at": now_iso(),
        "midweek_rerun": midweek_rerun,
        "output_options": {
            "generate_excel_stats": generate_excel_stats,
            "generate_individual_charts": generate_individual_charts,
            "generate_versus_charts": generate_versus_charts,
        },
        "rank_by": rank_by,
        "rank_by_label": rank_by_label,
        "rank_timeseries_metric": focus_ts_metric,
        "records": int(len(df)),
        "stories": int(df["story"].nunique()),
        "story_buckets": int(df["story_bucket"].nunique()),
        "date_range": {
            "start": str(df["date"].min().date()),
            "end": str(df["date"].max().date()),
        },
        "top_zscore_story": None if z_best.empty else z_best.iloc[0]["story"],
        "worst_zscore_story": None if z_worst.empty else z_worst.iloc[0]["story"],
        "top_payup_story": None if p_best.empty else p_best.iloc[0]["story"],
        "worst_payup_story": None if p_worst.empty else p_worst.iloc[0]["story"],
        "top_ranked_story": None if focus_best.empty else str(focus_best.iloc[0]["story"]),
        "worst_ranked_story": None if focus_worst.empty else str(focus_worst.iloc[0]["story"]),
        "chart_counts": {
            "coupon_packs": len(coupon_chart_paths),
            "year_packs": len(year_chart_paths),
            "geo_pairs": len(geo_chart_paths),
            "versus": len(versus_paths),
            "focus_versus": 1 if focus_versus_path else 0,
        },
        "sample_charts": {
            "versus": versus_paths[:10],
            "coupon_packs": coupon_chart_paths[:10],
            "year_packs": year_chart_paths[:10],
            "geo_pairs": geo_chart_paths[:10],
            "focus_versus": [] if not focus_versus_path else [focus_versus_path],
        },
    }
    write_json(Path(output_dir) / "report_metadata.json", metadata)
    _publish_progress("Saved report_metadata.json")
    if progress_cb is not None and completed_steps < planned_steps:
        progress_cb(planned_steps, planned_steps, "Automation completed")
    return metadata
