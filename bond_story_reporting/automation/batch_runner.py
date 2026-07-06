from __future__ import annotations

from pathlib import Path
from typing import Any

from ..data import apply_filters, load_dataset
from ..presets import (
    DEFAULT_CONFIG_STORE_PATH,
    list_saved_config_names,
    read_saved_config,
)
from ..reporting import run_weekly_reports
from .workflow_registry import run_saved_idea_scan_workflow, run_saved_workflow


def run_weekly_batch(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    midweek_rerun: bool = False,
    years: list[int] | None = None,
    geos: list[str] | None = None,
    coupons: list[float] | None = None,
    story_buckets: list[str] | None = None,
    issuer: str | None = None,
    rank_by: str | None = None,
    best_n: int | None = None,
    worst_n: int | None = None,
    max_geo_pairs: int | None = None,
) -> dict[str, Any]:
    years = years or []
    geos = geos or []
    coupons = coupons or []
    story_buckets = story_buckets or []

    df = load_dataset(Path(input_path))
    df = apply_filters(
        df,
        years=years,
        geos=geos,
        coupons=coupons,
        issuer=issuer,
        story_buckets=story_buckets,
    )

    overrides: dict[str, Any] = {}
    if years or geos or coupons:
        overrides["filters"] = {
            "years": years,
            "geos": geos,
            "coupons": coupons,
        }
    if best_n is not None:
        overrides["best_n"] = best_n
    if worst_n is not None:
        overrides["worst_n"] = worst_n
    if max_geo_pairs is not None:
        overrides["automation"] = {"max_geo_pairs": max_geo_pairs}
    if rank_by is not None:
        overrides["rank_by"] = rank_by

    metadata = run_weekly_reports(
        df=df,
        output_dir=Path(output_dir),
        midweek_rerun=midweek_rerun,
        config_overrides=overrides if overrides else None,
    )
    return metadata


def list_saved_batches(config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH) -> list[str]:
    return list_saved_config_names(config_store_path=config_store_path)


def show_saved_batch(config_name: str, config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH) -> dict:
    return read_saved_config(config_name=config_name, config_store_path=config_store_path)


def run_saved_idea_scan(
    config_name: str,
    config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run an idea scan from a saved JSON config without duplicating workflow logic."""

    config = read_saved_config(config_name=config_name, config_store_path=config_store_path)
    return run_saved_idea_scan_workflow(config_name=config_name, config=config, base_dir=base_dir)


def run_saved_batch(
    config_name: str,
    config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    return run_saved_workflow(
        config_name=config_name,
        config_store_path=config_store_path,
        base_dir=base_dir,
    )
