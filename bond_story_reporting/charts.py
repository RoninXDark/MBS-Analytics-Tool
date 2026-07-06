from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from .utils import ensure_dir, slugify


def _finish(fig, title: str, path: Path) -> None:
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_multi_line(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    line_col: str,
    output_path: str | Path,
    title: str,
    x_label: str = "Date",
    y_label: str | None = None,
) -> Path:
    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    fig, ax = plt.subplots(figsize=(12, 6))
    for line_name, group in df.groupby(line_col):
        ax.plot(group[x_col], group[y_col], label=str(line_name), linewidth=2)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label or y_col.replace("_", " ").title())
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.25)
    _finish(fig, title, output_path)
    return output_path


def save_story_lines(df: pd.DataFrame, metric: str, output_dir: str | Path, title: str, filename: str) -> Path:
    output_dir = ensure_dir(output_dir)
    path = Path(output_dir) / filename
    return save_multi_line(df, "date", metric, "story", path, title, x_label="Date")


def save_story_versus(df: pd.DataFrame, metric: str, story_a: str, story_b: str, output_dir: str | Path) -> Path:
    output_dir = ensure_dir(output_dir)
    subset = df[df["story"].isin([story_a, story_b])].copy()
    filename = f"versus_{slugify(story_a)}__{slugify(story_b)}__{slugify(metric)}.png"
    path = Path(output_dir) / filename
    return save_multi_line(
        subset,
        "date",
        metric,
        "story",
        path,
        f"{story_a} vs {story_b} - {metric}",
        x_label="Date",
    )


def save_ranked_bar(rankings: pd.DataFrame, metric: str, title: str, filename: str, output_dir: str | Path) -> Path:
    output_dir = ensure_dir(output_dir)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(rankings["story"], rankings[metric])
    ax.set_xlabel(metric.replace("_", " ").title())
    ax.set_ylabel("Story")
    ax.grid(alpha=0.25, axis="x")
    path = Path(output_dir) / filename
    _finish(fig, title, path)
    return path


def save_weekly_coupon_chart(
    weekly_coupon_df: pd.DataFrame,
    metric: str,
    output_dir: str | Path,
    story_bucket: str,
    year: int,
    issuer: str | None = None,
) -> Path | None:
    output_dir = ensure_dir(output_dir)
    subset = weekly_coupon_df[
        (weekly_coupon_df["story_bucket"] == story_bucket)
        & (weekly_coupon_df["year"] == year)
    ].copy()
    if issuer is not None:
        subset = subset[subset["issuer"] == issuer]
    if subset.empty or subset["coupon"].nunique() < 2:
        return None
    filename = f"coupon_pack__{slugify(story_bucket)}__{slugify(str(issuer or 'all'))}__year_{year}__{slugify(metric)}.png"
    title = f"{story_bucket} {year} - Weekly {metric} by coupon"
    path = Path(output_dir) / filename
    return save_multi_line(
        subset,
        "week_end",
        metric,
        "coupon_label",
        path,
        title=title,
        x_label="Week End",
    )


def save_weekly_year_chart(
    weekly_year_df: pd.DataFrame,
    metric: str,
    output_dir: str | Path,
    story_bucket: str,
    coupon: float,
    issuer: str | None = None,
) -> Path | None:
    output_dir = ensure_dir(output_dir)
    subset = weekly_year_df[
        (weekly_year_df["story_bucket"] == story_bucket)
        & (weekly_year_df["coupon"] == coupon)
    ].copy()
    if issuer is not None:
        subset = subset[subset["issuer"] == issuer]
    if subset.empty or subset["year"].nunique() < 2:
        return None
    coupon_label = f"{float(coupon):.1f}" if pd.notna(coupon) else "na"
    filename = f"year_pack__{slugify(story_bucket)}__{slugify(str(issuer or 'all'))}__coupon_{slugify(coupon_label)}__{slugify(metric)}.png"
    title = f"{story_bucket} {coupon_label}s - Weekly {metric} by year"
    path = Path(output_dir) / filename
    return save_multi_line(
        subset,
        "week_end",
        metric,
        "year_label",
        path,
        title=title,
        x_label="Week End",
    )


def save_geo_pair_chart(
    geo_df: pd.DataFrame,
    metric: str,
    output_dir: str | Path,
    story_bucket: str,
    year: int,
    coupon: float,
    geo_a: str,
    geo_b: str,
    issuer: str | None = None,
) -> Path | None:
    output_dir = ensure_dir(output_dir)
    subset = geo_df[
        (geo_df["story_bucket"] == story_bucket)
        & (geo_df["year"] == year)
        & (geo_df["coupon"] == coupon)
        & (geo_df["geo"].isin([geo_a, geo_b]))
    ].copy()
    if issuer is not None:
        subset = subset[subset["issuer"] == issuer]
    if subset.empty or subset["geo"].nunique() < 2:
        return None
    coupon_label = f"{float(coupon):.1f}" if pd.notna(coupon) else "na"
    filename = (
        f"geo_pair__{slugify(story_bucket)}__{year}__{slugify(coupon_label)}__"
        f"{slugify(geo_a)}_vs_{slugify(geo_b)}__{slugify(metric)}.png"
    )
    title = f"{story_bucket} {year} {coupon_label}s - {geo_a} vs {geo_b} ({metric})"
    path = Path(output_dir) / filename
    return save_multi_line(
        subset,
        "week_end",
        metric,
        "geo",
        path,
        title=title,
        x_label="Week End",
    )
