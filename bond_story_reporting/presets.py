from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .data import apply_filters, load_dataset
from .reporting import run_weekly_reports
from .runtime_paths import (
    default_config_store_path,
    resolve_default_config_store_path,
    resolve_default_overnight_output_dir,
)

ProgressCallback = Callable[[int, int, str], None]

DEFAULT_CONFIG_STORE_PATH = default_config_store_path()

RANK_LABEL_TO_METRIC = {
    "z-score": "z_score_can",
    "z score": "z_score_can",
    "zscore": "z_score_can",
    "current pay-up": "payup",
    "current payup": "payup",
    "payup": "payup",
    "mean": "mean_payup",
    "mean pay-up": "mean_payup",
    "mean payup": "mean_payup",
}

RANK_METRIC_TO_LABEL = {
    "z_score_can": "Z-Score",
    "payup": "Current Pay-up",
    "mean_payup": "Mean",
}


def _parse_int_csv(raw: str | None) -> list[int]:
    value = str(raw or "").strip()
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_float_csv(raw: str | None) -> list[float]:
    value = str(raw or "").strip()
    if not value:
        return []
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_str_csv(raw: str | None) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_optional_int(raw: str | None) -> int | None:
    value = str(raw or "").strip()
    if not value:
        return None
    return int(value)


def _parse_optional_date(raw: str | None, field_name: str) -> str | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format.") from exc
    return value


def _config_bool(value: Any, default: bool = True) -> bool:
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


def _normalize_rank_metric(raw: str | None) -> str:
    rank_raw = str(raw or "").strip().lower()
    if not rank_raw:
        return "z_score_can"
    return RANK_LABEL_TO_METRIC.get(rank_raw, "z_score_can")


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    return path


def _resolve_config_store(config_store_path: str | Path) -> Path:
    store = Path(config_store_path)
    if store == DEFAULT_CONFIG_STORE_PATH:
        return resolve_default_config_store_path()
    return store


def load_saved_configs_map(config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH) -> dict[str, dict]:
    store = _resolve_config_store(config_store_path)
    if not store.exists():
        return {}
    try:
        raw = store.read_text(encoding="utf-8")
        payload = json.loads(raw.lstrip("\ufeff"))
    except Exception:
        try:
            payload = json.loads(store.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
    if isinstance(payload, dict) and isinstance(payload.get("configs"), dict):
        return {str(k): dict(v) for k, v in payload["configs"].items() if isinstance(v, dict)}
    if isinstance(payload, dict):
        return {str(k): dict(v) for k, v in payload.items() if isinstance(v, dict)}
    return {}


def write_saved_configs_map(
    configs: dict[str, dict],
    config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH,
) -> Path:
    store = _resolve_config_store(config_store_path)
    store.parent.mkdir(parents=True, exist_ok=True)
    payload = {"configs": configs}
    store.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return store


def list_saved_config_names(config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH) -> list[str]:
    configs = load_saved_configs_map(config_store_path=config_store_path)
    return sorted(configs.keys())


def read_saved_config(
    config_name: str,
    config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH,
) -> dict:
    name = str(config_name or "").strip()
    if not name:
        raise ValueError("Configuration name is required.")
    configs = load_saved_configs_map(config_store_path=config_store_path)
    if name not in configs:
        raise KeyError(f"Configuration '{name}' not found in {_resolve_config_store(config_store_path)}")
    return configs[name]


def resolve_saved_config_runtime(
    config: dict,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    run_base = Path(base_dir) if base_dir is not None else Path.cwd()
    run_base = run_base.resolve()

    input_raw = str(config.get("auto_input", "")).strip()
    if not input_raw:
        raise ValueError("Saved config is missing 'auto_input'.")
    input_path = _resolve_path(input_raw, run_base)

    output_raw = str(config.get("auto_output", resolve_default_overnight_output_dir())).strip()
    output_raw = output_raw or str(resolve_default_overnight_output_dir())
    output_path = _resolve_path(output_raw, run_base)

    years = _parse_int_csv(config.get("auto_years"))
    geos = _parse_str_csv(config.get("auto_geos"))
    coupons = _parse_float_csv(config.get("auto_coupons"))
    story_buckets = _parse_str_csv(config.get("auto_buckets"))
    issuer = str(config.get("auto_issuer", "")).strip() or None
    date_from = _parse_optional_date(config.get("auto_date_from"), "Start Date")
    date_to = _parse_optional_date(config.get("auto_date_to"), "End Date")
    if date_from and date_to and date_from > date_to:
        raise ValueError("Start Date must be less than or equal to End Date.")

    rank_metric = _normalize_rank_metric(config.get("auto_rank_by"))
    rank_label = RANK_METRIC_TO_LABEL.get(rank_metric, "Z-Score")

    overrides: dict[str, Any] = {
        "rank_by": rank_metric,
        "output_options": {
            "generate_excel_stats": _config_bool(config.get("auto_generate_excel_stats"), default=True),
            "generate_individual_charts": _config_bool(config.get("auto_generate_individual_charts"), default=True),
            "generate_versus_charts": _config_bool(config.get("auto_generate_versus_charts"), default=True),
        },
    }

    best_n = _parse_optional_int(config.get("auto_best_n"))
    worst_n = _parse_optional_int(config.get("auto_worst_n"))
    max_geo_pairs = _parse_optional_int(config.get("auto_max_geo_pairs"))

    if years or geos or coupons:
        overrides["filters"] = {"years": years, "geos": geos, "coupons": coupons}
    if best_n is not None:
        overrides["best_n"] = best_n
    if worst_n is not None:
        overrides["worst_n"] = worst_n
    if max_geo_pairs is not None:
        overrides["automation"] = {"max_geo_pairs": max_geo_pairs}

    return {
        "input_path": input_path,
        "output_path": output_path,
        "midweek_rerun": _config_bool(config.get("auto_midweek"), default=False),
        "filters": {
            "years": years,
            "geos": geos,
            "coupons": coupons,
            "issuer": issuer,
            "story_buckets": story_buckets,
            "date_from": date_from,
            "date_to": date_to,
        },
        "overrides": overrides,
        "rank_label": rank_label,
    }


def run_saved_configuration(
    config_name: str,
    config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH,
    base_dir: str | Path | None = None,
    progress_cb: ProgressCallback | None = None,
) -> dict[str, Any]:
    config = read_saved_config(config_name=config_name, config_store_path=config_store_path)
    runtime = resolve_saved_config_runtime(config=config, base_dir=base_dir)

    df = load_dataset(runtime["input_path"])
    filters = runtime["filters"]
    df = apply_filters(
        df,
        years=filters["years"],
        geos=filters["geos"],
        coupons=filters["coupons"],
        issuer=filters["issuer"],
        story_buckets=filters["story_buckets"],
        date_from=filters["date_from"],
        date_to=filters["date_to"],
    )
    if df.empty:
        raise ValueError("No records left after filters. Broaden filters and run again.")

    metadata = run_weekly_reports(
        df=df,
        output_dir=runtime["output_path"],
        midweek_rerun=bool(runtime["midweek_rerun"]),
        config_overrides=runtime["overrides"],
        progress_cb=progress_cb,
    )

    return {
        "config_name": config_name,
        "input_path": str(runtime["input_path"]),
        "output_path": str(runtime["output_path"]),
        "rank_label": runtime["rank_label"],
        "metadata": metadata,
    }
