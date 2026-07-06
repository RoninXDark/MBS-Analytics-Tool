from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..data import load_and_normalize_dataset
from ..reporting import PayupCurvePackageResult, build_payup_curve_package
from ..runtime_paths import ensure_runtime_paths
from ..utils import ensure_dir, now_iso, slugify, write_json
from .idea_scan import resolve_latest_input_file


DEFAULT_CANNED_REPORT_NAME = "Payup Curve Pack"
DEFAULT_MAX_CHARTS_PER_REQUEST = 50
DEFAULT_MAX_TOTAL_CHARTS = 250
DEFAULT_MAX_SERIES_PER_CHART = 50
PAYUP_CHART_FILTER_FIELDS = {
    "program",
    "programs",
    "coupon",
    "coupons",
    "coupon_min",
    "coupon_max",
    "origination_years",
    "origination_year_min",
    "origination_year_max",
    "year_min",
    "year_max",
    "years",
    "geo",
    "geographies",
    "loan_balance_buckets",
    "loan_balances",
    "story_family",
    "story_families",
    "story_tag",
    "story_tags",
    "raw_story_names",
    "stories",
}


@dataclass(frozen=True)
class PayupCurvePackRunDefinition:
    input_path: Path
    output_dir: Path
    input_mode: str = "fixed_file"
    input_dir: Path | None = None
    input_pattern: str = "*.xlsx"
    report_name: str = DEFAULT_CANNED_REPORT_NAME
    chart_requests: list[dict[str, Any]] = field(default_factory=list)
    max_charts_per_request: int = DEFAULT_MAX_CHARTS_PER_REQUEST
    max_total_charts: int = DEFAULT_MAX_TOTAL_CHARTS
    max_series_per_chart: int = DEFAULT_MAX_SERIES_PER_CHART
    package_name: str | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: dict[str, Any],
        *,
        base_dir: str | Path | None = None,
    ) -> "PayupCurvePackRunDefinition":
        config = dict(payload or {})
        input_map = dict(config.get("input")) if isinstance(config.get("input"), dict) else {}
        run_base = Path(base_dir).resolve() if base_dir is not None else Path.cwd().resolve()

        input_mode_raw = _first_present(input_map, "mode", default=None)
        input_mode_raw = _first_present(config, "input_mode", "input_source", default=input_mode_raw)
        input_mode = str(input_mode_raw or "").strip().lower().replace("-", "_").replace(" ", "_")

        input_dir_raw = _first_present(input_map, "dir", "folder", "input_dir", "input_folder", default=None)
        input_dir_raw = _first_present(
            config,
            "input_dir",
            "input_folder",
            "latest_input_dir",
            "latest_input_folder",
            default=input_dir_raw,
        )
        input_pattern_raw = _first_present(input_map, "pattern", "glob", default=None)
        input_pattern_raw = _first_present(
            config,
            "input_pattern",
            "input_glob",
            "latest_input_pattern",
            default=input_pattern_raw or "*.xlsx",
        )
        input_raw = _first_present(input_map, "path", "input_path", default=None)
        input_raw = _first_present(config, "input_path", "auto_input", default=input_raw)
        if input_raw is None and not isinstance(config.get("input"), dict):
            input_raw = config.get("input")

        if input_mode in {"latest", "latest_file"} or str(input_dir_raw or "").strip():
            if not str(input_dir_raw or "").strip():
                raise ValueError("Payup curve pack latest-file config is missing 'input_dir'.")
            input_dir = _resolve_config_path(str(input_dir_raw), run_base)
            input_path = resolve_latest_input_file(input_dir, input_pattern_raw)
            resolved_input_mode = "latest_file"
        else:
            if not str(input_raw or "").strip():
                raise ValueError("Payup curve pack config is missing 'input_path' or latest-file 'input_dir'.")
            input_dir = None
            input_path = _resolve_config_path(str(input_raw), run_base)
            resolved_input_mode = "fixed_file"

        chart_requests = config.get("chart_requests") or config.get("charts") or []
        if not isinstance(chart_requests, list):
            raise ValueError("Payup curve pack config field 'chart_requests' must be a list.")
        chart_requests = _validate_chart_requests(chart_requests)

        return cls(
            input_path=input_path,
            output_dir=_resolve_config_path(
                str(config.get("output_dir") or config.get("output") or _default_canned_output_dir()),
                run_base,
            ),
            input_mode=resolved_input_mode,
            input_dir=input_dir,
            input_pattern=",".join(_as_str_list(input_pattern_raw)) or "*.xlsx",
            report_name=str(config.get("report_name") or DEFAULT_CANNED_REPORT_NAME).strip()
            or DEFAULT_CANNED_REPORT_NAME,
            chart_requests=chart_requests,
            max_charts_per_request=_as_int(
                config.get("max_charts_per_request"),
                default=DEFAULT_MAX_CHARTS_PER_REQUEST,
            ),
            max_total_charts=_as_int(config.get("max_total_charts"), default=DEFAULT_MAX_TOTAL_CHARTS),
            max_series_per_chart=_as_int(config.get("max_series_per_chart"), default=DEFAULT_MAX_SERIES_PER_CHART),
            package_name=_optional_str(config.get("package_name")),
        )

    def to_mapping(self) -> dict[str, Any]:
        payload = {
            "workflow": "payup_curve_pack",
            "output_dir": str(self.output_dir),
            "report_name": self.report_name,
            "chart_requests": self.chart_requests,
            "max_charts_per_request": self.max_charts_per_request,
            "max_total_charts": self.max_total_charts,
            "max_series_per_chart": self.max_series_per_chart,
            "package_name": self.package_name,
        }
        if self.input_mode == "latest_file":
            payload.update(
                {
                    "input_mode": "latest_file",
                    "input_dir": str(self.input_dir) if self.input_dir else None,
                    "input_pattern": self.input_pattern,
                    "resolved_input_path": str(self.input_path),
                }
            )
        else:
            payload["input_path"] = str(self.input_path)
        return payload


@dataclass(frozen=True)
class PayupCurvePackResult:
    output_dir: Path
    run_metadata_path: Path
    run_metadata: dict[str, Any]
    package_result: PayupCurvePackageResult


def run_payup_curve_pack_definition(definition: PayupCurvePackRunDefinition) -> PayupCurvePackResult:
    normalized, parse_diagnostics = load_and_normalize_dataset(definition.input_path)
    package_root = ensure_dir(definition.output_dir)
    package_dir = ensure_dir(package_root / (definition.package_name or _dated_package_name(definition.report_name)))
    package_result = build_payup_curve_package(
        normalized,
        package_dir,
        report_name=definition.report_name,
        chart_requests=definition.chart_requests,
        parse_diagnostics=parse_diagnostics,
        input_path=definition.input_path,
        max_charts_per_request=definition.max_charts_per_request,
        max_total_charts=definition.max_total_charts,
        max_series_per_chart=definition.max_series_per_chart,
    )

    charts_generated = int(package_result.metadata.get("charts_generated", 0))
    run_metadata = {
        "generated_at": now_iso(),
        "status": package_result.metadata.get("status", "completed"),
        "workflow": "payup_curve_pack",
        "client_summary": {
            "result": _client_result_label(str(package_result.metadata.get("status", ""))),
            "input_file": str(definition.input_path),
            "output_folder": str(package_dir),
            "report_name": definition.report_name,
            "chart_requests": int(len(definition.chart_requests)),
            "charts_generated": charts_generated,
            "skipped_requests": int(package_result.metadata.get("skipped_requests", 0)),
            "client_report_index": str(package_result.index_workbook_path) if package_result.index_workbook_path else None,
            "review_next": "Open CLIENT_REPORT_INDEX.xlsx first, then review charts/.",
        },
        "input_path": str(definition.input_path),
        "input_resolution": {
            "mode": definition.input_mode,
            "input_dir": str(definition.input_dir) if definition.input_dir else None,
            "input_pattern": definition.input_pattern if definition.input_mode == "latest_file" else None,
            "resolved_input_path": str(definition.input_path),
        },
        "output_dir": str(package_dir),
        "run_definition": definition.to_mapping(),
        "normalization_diagnostics": parse_diagnostics,
        "package_metadata": package_result.metadata,
        "paths": {
            "client_report_index": str(package_result.index_workbook_path) if package_result.index_workbook_path else None,
            "chart_metadata": str(package_result.chart_metadata_path),
            "parse_diagnostics": str(package_result.parse_diagnostics_path),
            "package_metadata": str(package_result.package_metadata_path),
        },
    }
    run_metadata_path = package_dir / "diagnostics" / "run_metadata.json"
    write_json(run_metadata_path, run_metadata)
    return PayupCurvePackResult(
        output_dir=package_dir,
        run_metadata_path=run_metadata_path,
        run_metadata=run_metadata,
        package_result=package_result,
    )


def run_saved_payup_curve_pack(
    config_name: str,
    config: dict[str, Any],
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    definition = PayupCurvePackRunDefinition.from_mapping(config, base_dir=base_dir)
    result = run_payup_curve_pack_definition(definition)
    return {
        "config_name": config_name,
        "workflow": "payup_curve_pack",
        "input_path": str(definition.input_path),
        "output_path": str(result.output_dir),
        "run_metadata_path": str(result.run_metadata_path),
        "metadata": result.run_metadata,
    }


def _client_result_label(status: str) -> str:
    if status == "completed":
        return "Completed"
    if status == "completed_with_warnings":
        return "Completed with warnings"
    if status == "completed_no_charts":
        return "Completed with no charts generated"
    return status or "Completed"


def _validate_chart_requests(chart_requests: list[Any]) -> list[dict[str, Any]]:
    """Require explicit filter criteria for every canned payup chart request.

    The request name is only a label for humans. Automation must never infer
    filters from names such as "LB125 2022"; those dimensions must be stored as
    real config fields so nightly runs are deterministic and auditable.
    """

    if not chart_requests:
        raise ValueError("Payup curve pack config must include at least one chart request.")

    validated: list[dict[str, Any]] = []
    for index, item in enumerate(chart_requests, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Payup chart request #{index} must be an object/dictionary.")
        request = dict(item)
        if not _request_has_explicit_filters(request):
            name = str(request.get("name") or f"#{index}")
            supported = ", ".join(sorted(PAYUP_CHART_FILTER_FIELDS))
            raise ValueError(
                f"Payup chart request '{name}' is missing explicit filter criteria. "
                "Do not rely on the request name for filtering. Add at least one explicit filter field, "
                f"for example loan_balance_buckets, origination_years, geographies, story_tags, "
                f"coupon_min/coupon_max, or raw_story_names. Supported filter fields: {supported}."
            )
        validated.append(request)
    return validated


def _request_has_explicit_filters(request: dict[str, Any]) -> bool:
    for key in PAYUP_CHART_FILTER_FIELDS:
        if key in request and _has_config_value(request.get(key)):
            return True
    return False


def _has_config_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _default_canned_output_dir() -> Path:
    return ensure_runtime_paths(migrate_legacy_config=False).output / "canned_reports"


def _dated_package_name(report_name: str) -> str:
    clean = _client_folder_label(report_name) or "Payup_Curve_Pack"
    return f"{clean}_{datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')}"


def _client_folder_label(value: str) -> str:
    parts = [part for part in slugify(value).split("_") if part]
    return "_".join(part.upper() if len(part) <= 3 else part.capitalize() for part in parts)


def _resolve_config_path(raw_path: str, base_dir: Path) -> Path:
    expanded = os.path.expandvars(raw_path)
    path = Path(expanded).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0].lower() == "documents":
        return Path.home().joinpath(*parts)
    return base_dir / path


def _first_present(config: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = config.get(name)
        if value not in (None, ""):
            return value
    return default


def _split_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _as_str_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _split_list(value) if str(item).strip()]


def _as_int(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    return int(float(value))


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
