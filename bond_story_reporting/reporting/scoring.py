from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..data.normalization import DEFAULT_ACTIVE_ORIGINATION_YEAR

COMPARABLE_KEY_COLUMNS = [
    "program",
    "origination_year",
    "coupon",
    "geography",
    "loan_balance_bucket",
    "story_family",
    "story_tag",
]

SCORE_COLUMNS = [
    "comparable_key",
    "raw_story_name",
    "program",
    "origination_year",
    "coupon",
    "geography",
    "loan_balance_bucket",
    "story_family",
    "story_tag",
    "latest_date",
    "current_value",
    "low",
    "high",
    "mean",
    "std",
    "z_score",
    "observations",
    "parse_success_rate",
]

DEFAULT_MIN_OBSERVATIONS = 50


@dataclass(frozen=True)
class ScoringFilters:
    """Reusable filters for normalized bond/story universes."""

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


@dataclass(frozen=True)
class RankingResult:
    """Structured output for GUI, batch, and future chart packaging."""

    scores: pd.DataFrame
    buy_candidates: pd.DataFrame
    sell_candidates: pd.DataFrame
    diagnostics: dict[str, Any]


def _normalize_label(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return text.upper()


def _normalize_year(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return _normalize_label(value)


def _normalize_coupon(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    try:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return _normalize_label(value)


def _key_part(column: str, value: Any) -> str:
    if column == "origination_year":
        normalized = _normalize_year(value)
    elif column == "coupon":
        normalized = _normalize_coupon(value)
    else:
        normalized = _normalize_label(value)
    return normalized or "NA"


def build_comparable_key(row: pd.Series) -> str:
    """Build a stable comparable story-slice key from parsed dimensions.

    When parsing fails completely, the raw story name is used as a fallback so
    malformed labels remain traceable instead of disappearing from the scan.
    """

    parts = [_key_part(column, row.get(column)) for column in COMPARABLE_KEY_COLUMNS]
    if all(part == "NA" for part in parts):
        raw_name = _normalize_label(row.get("raw_story_name")) or "UNKNOWN"
        return f"RAW={raw_name}"
    return "|".join(f"{column}={part}" for column, part in zip(COMPARABLE_KEY_COLUMNS, parts))


def add_comparable_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the normalized frame with `comparable_key` populated."""

    out = frame.copy()
    missing = [col for col in ["raw_story_name", "date", "value"] if col not in out.columns]
    if missing:
        raise ValueError(f"Normalized scoring input missing columns: {missing}")
    for col in COMPARABLE_KEY_COLUMNS:
        if col not in out.columns:
            out[col] = None
    out["comparable_key"] = out.apply(build_comparable_key, axis=1)
    return out


def _as_upper_set(values: list[str]) -> set[str]:
    return {str(value).strip().upper() for value in values if str(value).strip()}


def _as_float_set(values: list[float]) -> set[float]:
    parsed: set[float] = set()
    for value in values:
        try:
            parsed.add(float(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _as_int_set(values: list[int]) -> set[int]:
    parsed: set[int] = set()
    for value in values:
        try:
            parsed.add(int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def filter_scoring_universe(
    frame: pd.DataFrame,
    filters: ScoringFilters | None = None,
    *,
    use_default_focus: bool = True,
) -> pd.DataFrame:
    """Apply active-universe and dimensional filters to normalized data."""

    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "value"])

    filters = filters or ScoringFilters()
    if not filters.include_parse_failures and "parse_success" in out.columns:
        out = out[out["parse_success"].fillna(False)]

    def _filter_text(column: str, values: list[str]) -> None:
        nonlocal out
        normalized = _as_upper_set(values)
        if normalized and column in out.columns:
            out = out[out[column].map(_normalize_label).isin(normalized)]

    _filter_text("program", filters.programs)
    _filter_text("geography", filters.geographies)
    _filter_text("loan_balance_bucket", filters.loan_balance_buckets)
    _filter_text("story_family", filters.story_families)
    _filter_text("story_tag", filters.story_tags)
    _filter_text("raw_story_name", filters.raw_story_names)

    coupon_values = _as_float_set(filters.coupons)
    if coupon_values and "coupon" in out.columns:
        out = out[pd.to_numeric(out["coupon"], errors="coerce").isin(coupon_values)]

    year_values = _as_int_set(filters.origination_years)
    if "origination_year" in out.columns:
        years = pd.to_numeric(out["origination_year"], errors="coerce")
        if use_default_focus:
            out = out[years >= DEFAULT_ACTIVE_ORIGINATION_YEAR]
            years = pd.to_numeric(out["origination_year"], errors="coerce")
        if year_values:
            out = out[years.isin(year_values)]
            years = pd.to_numeric(out["origination_year"], errors="coerce")
        if filters.origination_year_min is not None:
            out = out[years >= int(filters.origination_year_min)]
            years = pd.to_numeric(out["origination_year"], errors="coerce")
        if filters.origination_year_max is not None:
            out = out[years <= int(filters.origination_year_max)]
    elif use_default_focus and "is_default_focus_vintage" in out.columns:
        out = out[out["is_default_focus_vintage"].fillna(False)]
    elif use_default_focus and "is_default_focus_window" in out.columns:
        out = out[out["is_default_focus_window"].fillna(False)]

    return add_comparable_keys(out).reset_index(drop=True)


def score_story_slices(
    frame: pd.DataFrame,
    filters: ScoringFilters | None = None,
    *,
    use_default_focus: bool = True,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score each comparable story slice using latest value vs historical distribution."""

    universe = filter_scoring_universe(frame, filters=filters, use_default_focus=use_default_focus)
    input_years = pd.to_numeric(frame.get("origination_year"), errors="coerce")
    input_active_mask = input_years >= DEFAULT_ACTIVE_ORIGINATION_YEAR
    input_historical_mask = input_years < DEFAULT_ACTIVE_ORIGINATION_YEAR
    if universe.empty:
        empty = pd.DataFrame(columns=SCORE_COLUMNS)
        return empty, {
            "input_rows": int(len(frame)),
            "filtered_rows": 0,
            "scored_slices": 0,
            "insufficient_observation_slices": 0,
            "use_default_focus": use_default_focus,
            "default_focus_basis": "origination_year",
            "default_focus_origination_year_min": DEFAULT_ACTIVE_ORIGINATION_YEAR,
            "input_default_focus_rows_2019_plus": int(input_active_mask.sum()),
            "input_historical_rows_pre_2019": int(input_historical_mask.sum()),
            "filtered_default_focus_rows_2019_plus": 0,
            "filtered_historical_rows_pre_2019": 0,
            "filtered_historical_slices_pre_2019": 0,
            "min_observations": min_observations,
        }

    rows: list[dict[str, Any]] = []
    insufficient = 0
    grouped = universe.sort_values(["comparable_key", "date"]).groupby("comparable_key", dropna=False)
    for comparable_key, group in grouped:
        values = pd.to_numeric(group["value"], errors="coerce").dropna()
        if len(values) < min_observations:
            insufficient += 1
            continue

        latest_date = group["date"].max()
        latest_group = group[group["date"] == latest_date]
        current_value = float(pd.to_numeric(latest_group["value"], errors="coerce").mean())
        mean = float(values.mean())
        std = float(values.std(ddof=0))
        z_score = 0.0 if std == 0 else float((current_value - mean) / std)

        first = group.sort_values("date").iloc[-1]
        rows.append(
            {
                "comparable_key": str(comparable_key),
                "raw_story_name": first.get("raw_story_name"),
                "program": first.get("program"),
                "origination_year": first.get("origination_year"),
                "coupon": first.get("coupon"),
                "geography": first.get("geography"),
                "loan_balance_bucket": first.get("loan_balance_bucket"),
                "story_family": first.get("story_family"),
                "story_tag": first.get("story_tag"),
                "latest_date": latest_date,
                "current_value": current_value,
                "low": float(values.min()),
                "high": float(values.max()),
                "mean": mean,
                "std": std,
                "z_score": z_score,
                "observations": int(len(values)),
                "parse_success_rate": float(group.get("parse_success", pd.Series([True])).fillna(False).mean()),
            }
        )

    scores = pd.DataFrame(rows, columns=SCORE_COLUMNS)
    if not scores.empty:
        scores = scores.sort_values(["z_score", "current_value", "comparable_key"]).reset_index(drop=True)

    universe_years = pd.to_numeric(universe.get("origination_year"), errors="coerce")
    universe_active_mask = universe_years >= DEFAULT_ACTIVE_ORIGINATION_YEAR
    universe_historical_mask = universe_years < DEFAULT_ACTIVE_ORIGINATION_YEAR
    diagnostics = {
        "input_rows": int(len(frame)),
        "filtered_rows": int(len(universe)),
        "scored_slices": int(len(scores)),
        "insufficient_observation_slices": int(insufficient),
        "use_default_focus": use_default_focus,
        "default_focus_basis": "origination_year",
        "default_focus_origination_year_min": DEFAULT_ACTIVE_ORIGINATION_YEAR,
        "input_default_focus_rows_2019_plus": int(input_active_mask.sum()),
        "input_historical_rows_pre_2019": int(input_historical_mask.sum()),
        "filtered_default_focus_rows_2019_plus": int(universe_active_mask.sum()),
        "filtered_historical_rows_pre_2019": int(universe_historical_mask.sum()),
        "filtered_default_focus_slices_2019_plus": int(universe.loc[universe_active_mask, "comparable_key"].nunique()),
        "filtered_historical_slices_pre_2019": int(universe.loc[universe_historical_mask, "comparable_key"].nunique()),
        "min_observations": int(min_observations),
        "date_min": None if universe.empty else str(universe["date"].min().date()),
        "date_max": None if universe.empty else str(universe["date"].max().date()),
        "parse_failed_rows": int((~universe.get("parse_success", pd.Series([True] * len(universe))).fillna(False)).sum()),
    }
    return scores, diagnostics


def resolve_ranking_basis(ranking_basis: str) -> str:
    """Map public ranking aliases to score DataFrame columns."""

    normalized = str(ranking_basis or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "z": "z_score",
        "zscore": "z_score",
        "z_score": "z_score",
        "value": "current_value",
        "raw_value": "current_value",
        "payup": "current_value",
        "current_payup": "current_value",
        "current_value": "current_value",
    }
    metric = aliases.get(normalized)
    if metric is None:
        raise ValueError("ranking_basis must be one of: z_score, value, raw_value, payup")
    return metric


def rank_story_slices(
    scores: pd.DataFrame,
    *,
    ranking_basis: str = "z_score",
    top_n: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return BUY and SELL candidates from scored slices.

    BUY candidates are cheapest/lowest by the selected basis. SELL candidates
    are richest/highest by the same basis.
    """

    metric = resolve_ranking_basis(ranking_basis)
    if metric not in scores.columns:
        raise ValueError(f"Scoring column missing for ranking basis: {metric}")

    ranked = scores.dropna(subset=[metric]).copy()
    if ranked.empty:
        return ranked.copy(), ranked.copy()

    count = max(int(top_n), 0)
    buy = ranked.sort_values([metric, "current_value", "comparable_key"], ascending=[True, True, True]).head(count)
    sell = ranked.sort_values([metric, "current_value", "comparable_key"], ascending=[False, False, True]).head(count)
    return buy.reset_index(drop=True), sell.reset_index(drop=True)


def generate_ranked_ideas(
    frame: pd.DataFrame,
    filters: ScoringFilters | None = None,
    *,
    ranking_basis: str = "z_score",
    top_n: int = 10,
    use_default_focus: bool = True,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> RankingResult:
    """Score a normalized universe and return BUY/SELL candidate tables."""

    scores, diagnostics = score_story_slices(
        frame,
        filters=filters,
        use_default_focus=use_default_focus,
        min_observations=min_observations,
    )
    buy, sell = rank_story_slices(scores, ranking_basis=ranking_basis, top_n=top_n)
    diagnostics = dict(diagnostics)
    diagnostics["ranking_basis"] = resolve_ranking_basis(ranking_basis)
    diagnostics["top_n"] = int(top_n)
    diagnostics["buy_candidates"] = int(len(buy))
    diagnostics["sell_candidates"] = int(len(sell))
    return RankingResult(
        scores=scores,
        buy_candidates=buy,
        sell_candidates=sell,
        diagnostics=diagnostics,
    )
