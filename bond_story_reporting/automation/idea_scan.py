from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..data import load_and_normalize_dataset
from ..reporting import (
    DEFAULT_MIN_OBSERVATIONS,
    IdeaChartPackageResult,
    RankingResult,
    ScoringFilters,
    build_idea_chart_package,
    generate_ranked_ideas,
)
from ..runtime_paths import default_log_path, resolve_default_overnight_output_dir
from ..utils import ensure_dir, now_iso, write_json


@dataclass(frozen=True)
class RankingStrategy:
    """Named ranking strategy used by batch workflows."""

    name: str
    ranking_basis: str
    value_label: str
    description: str


@dataclass(frozen=True)
class IdeaScanResult:
    """Structured result for a complete overnight idea scan."""

    output_dir: Path
    run_metadata_path: Path
    run_metadata: dict[str, Any]
    ranking_result: RankingResult
    package_result: IdeaChartPackageResult


@dataclass(frozen=True)
class IdeaScanRunDefinition:
    """Serializable run definition for CLI, saved configs, and future GUI presets.

    Keeping the overnight scan inputs in this small object prevents future GUI
    saved-config execution from growing a separate code path. The GUI can save
    this shape to JSON, the CLI can rebuild it, and the batch runner executes it.

    Scheduler-facing configs may either use a fixed ``input_path`` or set
    ``input_mode=latest_file`` with ``input_dir``/``input_pattern``. The latter
    resolves to one concrete file before the existing analysis pipeline runs.
    """

    input_path: Path
    output_dir: Path
    input_mode: str = "fixed_file"
    input_dir: Path | None = None
    input_pattern: str = "*.xlsx"
    ranking_method: str = "z_score"
    top_n: int = 10
    use_default_focus: bool = True
    include_full_chart_history: bool = True
    min_observations: int = DEFAULT_MIN_OBSERVATIONS
    package_name: str | None = None
    programs: list[str] = field(default_factory=list)
    geographies: list[str] = field(default_factory=list)
    loan_balance_buckets: list[str] = field(default_factory=list)
    coupons: list[float] = field(default_factory=list)
    origination_years: list[int] = field(default_factory=list)
    origination_year_min: int | None = None
    origination_year_max: int | None = None
    story_families: list[str] = field(default_factory=list)
    story_tags: list[str] = field(default_factory=list)
    raw_story_names: list[str] = field(default_factory=list)
    include_parse_failures: bool = True

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: str | Path | None = None,
    ) -> "IdeaScanRunDefinition":
        """Build a run definition from a saved JSON-compatible mapping."""

        config = dict(payload)
        filters = config.get("filters")
        filter_map = dict(filters) if isinstance(filters, Mapping) else {}
        input_map = dict(config.get("input")) if isinstance(config.get("input"), Mapping) else {}
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
        if input_raw is None and not isinstance(config.get("input"), Mapping):
            input_raw = config.get("input")

        if input_mode in {"latest", "latest_file"} or str(input_dir_raw or "").strip():
            if not str(input_dir_raw or "").strip():
                raise ValueError("Idea scan latest-file config is missing 'input_dir'.")
            input_dir = _resolve_config_path(str(input_dir_raw), run_base)
            input_path = _resolve_latest_input_file(input_dir, input_pattern_raw)
            resolved_input_mode = "latest_file"
        else:
            if not str(input_raw or "").strip():
                raise ValueError("Idea scan config is missing 'input_path' or latest-file 'input_dir'.")
            input_dir = None
            input_path = _resolve_config_path(str(input_raw), run_base)
            resolved_input_mode = "fixed_file"

        output_raw = _first_present(
            config,
            "output_dir",
            "output",
            "auto_output",
            default=str(resolve_default_overnight_output_dir()),
        )

        use_default_focus = _bool_from_config(config, "use_default_focus", default=True)
        if "full_history" in config:
            use_default_focus = not _as_bool(config.get("full_history"), default=False)

        include_full_chart_history = _bool_from_config(config, "include_full_chart_history", default=True)
        if "chart_active_only" in config:
            include_full_chart_history = not _as_bool(config.get("chart_active_only"), default=False)

        ranking_method = _normalize_saved_ranking_method(
            _first_present(config, "ranking_method", "rank_by", "auto_idea_ranking_method", "auto_rank_by")
        )

        return cls(
            input_path=input_path,
            output_dir=_resolve_config_path(str(output_raw), run_base),
            input_mode=resolved_input_mode,
            input_dir=input_dir,
            input_pattern=",".join(_as_str_list(input_pattern_raw)) or "*.xlsx",
            ranking_method=ranking_method,
            top_n=_as_int(_first_present(config, "top_n", "auto_top_n"), default=10),
            use_default_focus=use_default_focus,
            include_full_chart_history=include_full_chart_history,
            min_observations=_as_int(config.get("min_observations"), default=DEFAULT_MIN_OBSERVATIONS),
            package_name=_optional_str(config.get("package_name")),
            programs=_as_str_list(_filter_value(config, filter_map, "programs", "program")),
            geographies=_as_str_list(_filter_value(config, filter_map, "geographies", "geos", "geo")),
            loan_balance_buckets=_as_str_list(
                _filter_value(config, filter_map, "loan_balance_buckets", "loan_balances")
            ),
            coupons=_as_float_list(_filter_value(config, filter_map, "coupons", "coupon", "auto_coupons")),
            origination_years=_as_int_list(
                _filter_value(config, filter_map, "origination_years", "years", "auto_years")
            ),
            origination_year_min=_as_optional_int(
                _filter_value(config, filter_map, "origination_year_min", "year_min")
            ),
            origination_year_max=_as_optional_int(
                _filter_value(config, filter_map, "origination_year_max", "year_max")
            ),
            story_families=_as_str_list(_filter_value(config, filter_map, "story_families", "story_buckets")),
            story_tags=_as_str_list(_filter_value(config, filter_map, "story_tags", "story_tag")),
            raw_story_names=_as_str_list(_filter_value(config, filter_map, "raw_story_names", "stories")),
            include_parse_failures=_bool_from_config(config, "include_parse_failures", default=True),
        )

    def to_mapping(self) -> dict[str, Any]:
        """Return a JSON-friendly representation suitable for saved configs."""

        payload = {
            "workflow": "idea_scan",
            "output_dir": str(self.output_dir),
            "ranking_method": self.ranking_method,
            "top_n": self.top_n,
            "use_default_focus": self.use_default_focus,
            "include_full_chart_history": self.include_full_chart_history,
            "min_observations": self.min_observations,
            "package_name": self.package_name,
            "filters": {
                "programs": self.programs,
                "geographies": self.geographies,
                "loan_balance_buckets": self.loan_balance_buckets,
                "coupons": self.coupons,
                "origination_years": self.origination_years,
                "origination_year_min": self.origination_year_min,
                "origination_year_max": self.origination_year_max,
                "story_families": self.story_families,
                "story_tags": self.story_tags,
                "raw_story_names": self.raw_story_names,
            },
            "include_parse_failures": self.include_parse_failures,
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


RANKING_STRATEGIES: dict[str, RankingStrategy] = {
    "z_score": RankingStrategy(
        name="z_score",
        ranking_basis="z_score",
        value_label="Value",
        description="Rank by latest value z-score versus each story slice history.",
    ),
    "value": RankingStrategy(
        name="value",
        ranking_basis="value",
        value_label="Value",
        description="Rank by latest raw normalized value.",
    ),
    "payup": RankingStrategy(
        name="payup",
        ranking_basis="payup",
        value_label="Payup",
        description="Rank by latest normalized value interpreted as payup.",
    ),
}


SAVED_RANKING_LABELS = {
    "z-score": "z_score",
    "z score": "z_score",
    "zscore": "z_score",
    "current pay-up": "payup",
    "current payup": "payup",
    "pay-up": "payup",
    "payup": "payup",
    "raw value": "value",
    "value": "value",
}


def available_ranking_methods() -> list[str]:
    return sorted(RANKING_STRATEGIES.keys())


def resolve_ranking_strategy(name: str) -> RankingStrategy:
    method = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if method not in RANKING_STRATEGIES:
        available = ", ".join(available_ranking_methods())
        raise ValueError(f"Unknown ranking method '{name}'. Available methods: {available}")
    return RANKING_STRATEGIES[method]


def _first_present(config: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in config and config[name] not in (None, ""):
            return config[name]
    return default


def _filter_value(config: Mapping[str, Any], filters: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in filters and filters[name] not in (None, ""):
            return filters[name]
        if name in config and config[name] not in (None, ""):
            return config[name]
    return None


def _resolve_config_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    return path


def resolve_latest_input_file(input_dir: str | Path, pattern_value: Any = "*.xlsx") -> Path:
    """Return the newest matching input file for scheduler-based runs."""

    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise ValueError(f"Latest-file input folder does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise ValueError(f"Latest-file input path is not a folder: {input_dir}")

    patterns = _as_str_list(pattern_value) or ["*.xlsx"]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(input_dir.glob(pattern))

    valid_suffixes = {".csv", ".xls", ".xlsx", ".xlsm"}
    files = [
        path
        for path in candidates
        if path.is_file()
        and path.suffix.lower() in valid_suffixes
        and not path.name.startswith("~$")
    ]

    if not files:
        pattern_text = ", ".join(patterns)
        raise ValueError(f"No input files matched '{pattern_text}' in folder: {input_dir}")

    return max(files, key=lambda path: (path.stat().st_mtime, path.name.lower()))


def _resolve_latest_input_file(input_dir: Path, pattern_value: Any) -> Path:
    return resolve_latest_input_file(input_dir, pattern_value)


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


def _as_float_list(value: Any) -> list[float]:
    return [float(item) for item in _split_list(value) if str(item).strip()]


def _as_int_list(value: Any) -> list[int]:
    return [int(item) for item in _split_list(value) if str(item).strip()]


def _as_int(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _as_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def _bool_from_config(config: Mapping[str, Any], name: str, *, default: bool) -> bool:
    if name not in config:
        return default
    return _as_bool(config.get(name), default=default)


def _normalize_saved_ranking_method(value: Any) -> str:
    raw = str(value or "z_score").strip().lower().replace("_", " ")
    normalized = SAVED_RANKING_LABELS.get(raw, raw.replace("-", "_").replace(" ", "_"))
    resolve_ranking_strategy(normalized)
    return normalized


def _dated_package_name(prefix: str = "BUY_SELL_Report") -> str:
    return f"{prefix}_{datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')}"


def _build_filters(
    *,
    programs: list[str] | None = None,
    geographies: list[str] | None = None,
    loan_balance_buckets: list[str] | None = None,
    coupons: list[float] | None = None,
    origination_years: list[int] | None = None,
    origination_year_min: int | None = None,
    origination_year_max: int | None = None,
    story_families: list[str] | None = None,
    story_tags: list[str] | None = None,
    raw_story_names: list[str] | None = None,
    include_parse_failures: bool = True,
) -> ScoringFilters:
    return ScoringFilters(
        programs=programs or [],
        geographies=geographies or [],
        loan_balance_buckets=loan_balance_buckets or [],
        coupons=coupons or [],
        origination_years=origination_years or [],
        origination_year_min=origination_year_min,
        origination_year_max=origination_year_max,
        story_families=story_families or [],
        story_tags=story_tags or [],
        raw_story_names=raw_story_names or [],
        include_parse_failures=include_parse_failures,
    )


def run_idea_scan(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    ranking_method: str = "z_score",
    top_n: int = 10,
    use_default_focus: bool = True,
    include_full_chart_history: bool = True,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    package_name: str | None = None,
    programs: list[str] | None = None,
    geographies: list[str] | None = None,
    loan_balance_buckets: list[str] | None = None,
    coupons: list[float] | None = None,
    origination_years: list[int] | None = None,
    origination_year_min: int | None = None,
    origination_year_max: int | None = None,
    story_families: list[str] | None = None,
    story_tags: list[str] | None = None,
    raw_story_names: list[str] | None = None,
    include_parse_failures: bool = True,
) -> IdeaScanResult:
    definition = IdeaScanRunDefinition(
        input_path=Path(input_path),
        output_dir=Path(output_dir),
        ranking_method=ranking_method,
        top_n=top_n,
        use_default_focus=use_default_focus,
        include_full_chart_history=include_full_chart_history,
        min_observations=min_observations,
        package_name=package_name,
        programs=programs or [],
        geographies=geographies or [],
        loan_balance_buckets=loan_balance_buckets or [],
        coupons=coupons or [],
        origination_years=origination_years or [],
        origination_year_min=origination_year_min,
        origination_year_max=origination_year_max,
        story_families=story_families or [],
        story_tags=story_tags or [],
        raw_story_names=raw_story_names or [],
        include_parse_failures=include_parse_failures,
    )
    return run_idea_scan_definition(definition)


def run_idea_scan_definition(
    definition: IdeaScanRunDefinition,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> IdeaScanResult:
    """Run the full headless idea scan workflow.

    This is the batch-facing chain used by CLI and future scheduled jobs:
    load/normalize -> score/rank -> package BUY/SELL charts -> write metadata.
    """

    def _progress(completed: int, total: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(completed, total, message)

    _progress(1, 5, "Preparing filters and ranking method...")
    strategy = resolve_ranking_strategy(definition.ranking_method)
    filters = _build_filters(
        programs=definition.programs,
        geographies=definition.geographies,
        loan_balance_buckets=definition.loan_balance_buckets,
        coupons=definition.coupons,
        origination_years=definition.origination_years,
        origination_year_min=definition.origination_year_min,
        origination_year_max=definition.origination_year_max,
        story_families=definition.story_families,
        story_tags=definition.story_tags,
        raw_story_names=definition.raw_story_names,
        include_parse_failures=definition.include_parse_failures,
    )

    _progress(2, 5, f"Loading and normalizing {definition.input_path.name}...")
    normalized, normalization_diagnostics = load_and_normalize_dataset(definition.input_path)
    _progress(3, 5, "Scoring and ranking BUY/SELL candidates...")
    ranking_result = generate_ranked_ideas(
        normalized,
        filters=filters,
        ranking_basis=strategy.ranking_basis,
        top_n=definition.top_n,
        use_default_focus=definition.use_default_focus,
        min_observations=definition.min_observations,
    )

    package_root = ensure_dir(definition.output_dir)
    package_dir = ensure_dir(package_root / (definition.package_name or _dated_package_name()))
    _progress(4, 5, "Generating charts and client-readable summaries...")
    package_result = build_idea_chart_package(
        normalized,
        ranking_result,
        package_dir,
        top_n=definition.top_n,
        include_full_history=definition.include_full_chart_history,
        value_label=strategy.value_label,
    )

    _progress(5, 5, "Writing run metadata and finishing package...")
    charts_generated = int(package_result.metadata.get("charts_generated", 0))
    client_outputs = package_result.metadata.get("client_readable_outputs", {})
    run_metadata = {
        "generated_at": now_iso(),
        "status": "completed",
        "client_summary": {
            "result": "Completed" if charts_generated else "Completed with no charts generated",
            "input_file": str(definition.input_path),
            "output_folder": str(package_dir),
            "buy_ideas": int(len(ranking_result.buy_candidates)),
            "sell_ideas": int(len(ranking_result.sell_candidates)),
            "charts_generated": charts_generated,
            "technical_csv": client_outputs.get("technical_summary_csv"),
            "summary_workbook": client_outputs.get("client_report_xlsx") or client_outputs.get("buy_sell_summary_xlsx"),
            "review_next": "Open CLIENT_REPORT_BUY_SELL.xlsx first. CSV files are secondary exports.",
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
        "ranking_strategy": asdict(strategy),
        "top_n": int(definition.top_n),
        "use_default_focus": bool(definition.use_default_focus),
        "include_full_chart_history": bool(definition.include_full_chart_history),
        "min_observations": int(definition.min_observations),
        "filters": asdict(filters),
        "normalization_diagnostics": normalization_diagnostics,
        "ranking_diagnostics": ranking_result.diagnostics,
        "package_metadata": package_result.metadata,
        "log_summary": {
            "message": "Headless idea scan completed successfully.",
            "log_file": str(default_log_path()),
        },
    }
    run_metadata_path = package_dir / "diagnostics" / "run_metadata.json"
    write_json(run_metadata_path, run_metadata)

    return IdeaScanResult(
        output_dir=package_dir,
        run_metadata_path=run_metadata_path,
        run_metadata=run_metadata,
        ranking_result=ranking_result,
        package_result=package_result,
    )
