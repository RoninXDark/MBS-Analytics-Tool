from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from .story_parser import parse_story_label

DEFAULT_REPORT_FOCUS_START = "2019-01-01"
DEFAULT_ACTIVE_ORIGINATION_YEAR = 2019
_BLOOMBERG_TICK_RE = re.compile(r"^-?\d+(?:-\d{1,3}\+?)?$")
_DATE_SHAPED_RE = re.compile(
    r"(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})|"
    r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})|"
    r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})|"
    r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})"
)
_LONG_REQUIRED_COLUMNS = {
    "date",
    "story",
    "story_bucket",
    "geo",
    "coupon",
    "year",
    "can",
    "payup",
    "spread",
    "issuer",
}

NORMALIZED_SCHEMA_COLUMNS = [
    "raw_story_name",
    "date",
    "value",
    "program",
    "coupon",
    "origination_year",
    "geography",
    "loan_balance_bucket",
    "story_family",
    "story_tag",
    "parse_success",
    "parse_error",
    "is_default_focus_window",
    "is_default_focus_vintage",
]


class DatasetLayoutError(ValueError):
    """Raised when input data cannot be classified as long or wide format."""


@dataclass(frozen=True)
class WideTableCandidate:
    """Detected location of a Bloomberg-style wide table inside a raw sheet."""

    header_row_index: int
    story_column_index: int
    date_column_indices: list[int]
    story_non_empty_rows: int
    numeric_value_count: int
    score: float
    sheet_name: str | None = None


def _is_non_empty(value: Any) -> bool:
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _excel_column_name(index: int) -> str:
    """Convert zero-based column index to an Excel-style column label."""

    number = int(index) + 1
    label = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _coerce_header_date(value: Any) -> pd.Timestamp | pd.NaT:
    """Best-effort parser for wide-sheet date headers.

    Supports:
    - ISO/date-like strings
    - Excel serial day numbers
    """

    if pd.isna(value):
        return pd.NaT

    if isinstance(value, (pd.Timestamp, datetime, date)):
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed) or parsed.year < 1900 or parsed.year > 2100:
            return pd.NaT
        return parsed.normalize()

    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            num = float(value)
            if 20000 <= num <= 80000:
                parsed = pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce")
                if pd.notna(parsed):
                    return parsed.normalize()
        except Exception:
            pass
        return pd.NaT

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return pd.NaT
        if _BLOOMBERG_TICK_RE.match(text):
            return pd.NaT
        if not _DATE_SHAPED_RE.search(text):
            return pd.NaT

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    if parsed.year < 1900 or parsed.year > 2100:
        return pd.NaT
    return parsed.normalize()


def _parse_numeric_value(raw: Any) -> float:
    """Parse numeric values including Bloomberg-style 32nds."""

    if isinstance(raw, (int, float, np.integer, np.floating)):
        return float(raw)

    text = str(raw or "").strip().replace(",", "")
    if not text:
        return float("nan")

    # Bloomberg variants:
    # - 100-163 -> 100 + 16/32 + 3/256
    # - -0-001  -> negative 1/256
    sign = 1.0
    bloomberg_text = text
    if text.startswith("-") and text[1:].count("-") == 1:
        sign = -1.0
        bloomberg_text = text[1:]

    if "-" in bloomberg_text:
        parts = bloomberg_text.split("-")
        if len(parts) == 2:
            base_raw, ticks_raw = parts
            try:
                base = float(base_raw)
            except ValueError:
                base = None
            if base is not None:
                ticks_text = ticks_raw.strip()
                if ticks_text.isdigit() and len(ticks_text) == 3:
                    ticks = float(ticks_text[:2])
                    eighths = float(ticks_text[2])
                    return sign * (base + (ticks / 32.0) + (eighths / 256.0))
                try:
                    plus = ticks_text.endswith("+")
                    ticks_numeric = float(ticks_text[:-1] if plus else ticks_text)
                    return sign * (base + ((ticks_numeric + (0.5 if plus else 0.0)) / 32.0))
                except ValueError:
                    pass

    try:
        return float(text)
    except ValueError:
        return float("nan")


def _parse_numeric_series(series: pd.Series) -> pd.Series:
    """Parse a value series using a unique-value cache for wide Bloomberg sheets."""

    unique_values = pd.unique(series.dropna())
    parsed_lookup = {value: _parse_numeric_value(value) for value in unique_values}
    return series.map(parsed_lookup).astype(float)


def _date_column_map(df: pd.DataFrame) -> dict[str, pd.Timestamp]:
    mapping: dict[str, pd.Timestamp] = {}
    for col in df.columns:
        parsed = _coerce_header_date(col)
        if pd.notna(parsed):
            mapping[str(col)] = parsed
    return mapping


def _row_date_indices(raw_df: pd.DataFrame, row_index: int) -> list[int]:
    values = raw_df.iloc[row_index].tolist()
    indices: list[int] = []
    for idx, value in enumerate(values):
        parsed = _coerce_header_date(value)
        if pd.notna(parsed):
            indices.append(idx)
    return indices


def _story_column_candidates(date_indices: list[int], column_count: int) -> list[int]:
    if not date_indices:
        return list(range(column_count))

    first_date = min(date_indices)
    candidates: list[int] = []

    # Bloomberg exports commonly place story labels immediately left of the first date.
    for idx in range(first_date - 1, -1, -1):
        candidates.append(idx)

    for idx in range(column_count):
        if idx not in date_indices and idx not in candidates:
            candidates.append(idx)

    return candidates


def _score_story_column(
    raw_df: pd.DataFrame,
    *,
    header_row_index: int,
    story_column_index: int,
    date_column_indices: list[int],
) -> tuple[int, int, float]:
    story_non_empty_rows = 0
    numeric_value_count = 0

    data = raw_df.iloc[header_row_index + 1 :]
    if data.empty:
        return 0, 0, 0.0

    story_mask = data.iloc[:, story_column_index].map(_is_non_empty)
    if not bool(story_mask.any()):
        return 0, 0, 0.0

    values = data.iloc[:, date_column_indices]
    value_mask = values.notna()
    if value_mask.empty:
        return 0, 0, 0.0

    candidate_values = value_mask.loc[story_mask]
    story_non_empty_rows = int(candidate_values.any(axis=1).sum())
    numeric_value_count = int(candidate_values.sum().sum())

    # Heavy weight on date columns, then rows with real stories and values.
    score = (len(date_column_indices) * 1000.0) + (story_non_empty_rows * 10.0) + numeric_value_count
    return story_non_empty_rows, numeric_value_count, score


def _find_wide_table_candidate(
    raw_df: pd.DataFrame,
    *,
    min_wide_date_columns: int = 3,
    sheet_name: str | None = None,
) -> WideTableCandidate | None:
    """Find a wide table even when title/blank rows precede the date header row."""

    if raw_df.empty:
        return None

    best: WideTableCandidate | None = None
    column_count = int(len(raw_df.columns))

    for row_index in range(len(raw_df)):
        date_indices = _row_date_indices(raw_df, row_index)
        if len(date_indices) < min_wide_date_columns:
            continue

        for story_idx in _story_column_candidates(date_indices, column_count):
            if story_idx in date_indices:
                continue

            story_rows, numeric_count, score = _score_story_column(
                raw_df,
                header_row_index=row_index,
                story_column_index=story_idx,
                date_column_indices=date_indices,
            )
            if story_rows < 1 or numeric_count < min_wide_date_columns:
                continue

            candidate = WideTableCandidate(
                header_row_index=row_index,
                story_column_index=story_idx,
                date_column_indices=date_indices,
                story_non_empty_rows=story_rows,
                numeric_value_count=numeric_count,
                score=score,
                sheet_name=sheet_name,
            )
            if best is None or candidate.score > best.score:
                best = candidate

    return best


def _wide_scan_summary(raw_df: pd.DataFrame) -> dict[str, Any]:
    best_row_index: int | None = None
    best_date_count = 0
    for row_index in range(len(raw_df)):
        date_count = len(_row_date_indices(raw_df, row_index))
        if date_count > best_date_count:
            best_date_count = date_count
            best_row_index = row_index

    return {
        "rows": int(len(raw_df)),
        "columns": int(len(raw_df.columns)),
        "best_date_header_row_index": best_row_index,
        "best_date_header_row_excel": None if best_row_index is None else int(best_row_index + 1),
        "best_date_header_count": int(best_date_count),
    }


def detect_input_layout(df: pd.DataFrame, min_wide_date_columns: int = 3) -> str:
    """Detect whether a frame is long-format analytics data or Bloomberg-style wide data."""

    lowered = {str(col).strip().lower() for col in df.columns}
    if _LONG_REQUIRED_COLUMNS.issubset(lowered):
        return "long"

    date_cols = _date_column_map(df)
    non_date_cols = [col for col in df.columns if str(col) not in date_cols]

    if len(date_cols) >= min_wide_date_columns and len(non_date_cols) >= 1:
        return "wide"
    if _find_wide_table_candidate(df, min_wide_date_columns=min_wide_date_columns) is not None:
        return "wide"
    return "unknown"


def _extract_story_column(df: pd.DataFrame, date_cols: dict[str, pd.Timestamp]) -> str:
    non_date = [str(col) for col in df.columns if str(col) not in date_cols]
    if not non_date:
        raise ValueError("Could not identify story column in wide format dataset.")

    # Prefer canonical labels first.
    prioritized = ["story", "stories", "name", "raw_story_name", "security", "description"]
    lowered_map = {col.lower(): col for col in non_date}
    for key in prioritized:
        if key in lowered_map:
            return lowered_map[key]

    # Fallback: left-most non-date column.
    return non_date[0]


def _normalize_story_fields(frame: pd.DataFrame) -> pd.DataFrame:
    unique_stories = frame[["raw_story_name"]].drop_duplicates().reset_index(drop=True)
    parsed = unique_stories["raw_story_name"].map(parse_story_label).apply(pd.Series)
    lookup = pd.concat([unique_stories, parsed], axis=1)
    parsed_columns = [col for col in lookup.columns if col != "raw_story_name"]
    base = frame.drop(columns=[col for col in parsed_columns if col in frame.columns], errors="ignore")
    return base.merge(lookup, on="raw_story_name", how="left")


def _build_diagnostics(
    frame: pd.DataFrame,
    *,
    source_layout: str,
    story_column: str | None = None,
    date_column_count: int | None = None,
    source_row_count: int | None = None,
    source_column_count: int | None = None,
) -> dict[str, Any]:
    failures = frame[~frame["parse_success"]]
    origination_years = pd.to_numeric(frame.get("origination_year"), errors="coerce")
    focus_mask = origination_years >= DEFAULT_ACTIVE_ORIGINATION_YEAR
    pre_focus_mask = origination_years < DEFAULT_ACTIVE_ORIGINATION_YEAR
    missing_year_mask = origination_years.isna()
    focus_rows = frame[focus_mask]
    history_rows = frame[pre_focus_mask]
    focus_slices = frame.loc[focus_mask, "raw_story_name"].nunique() if "raw_story_name" in frame.columns else 0
    history_slices = frame.loc[pre_focus_mask, "raw_story_name"].nunique() if "raw_story_name" in frame.columns else 0
    parse_success_count = int(frame["parse_success"].sum())
    total_rows = int(len(frame))
    parse_rate = float(parse_success_count / total_rows) if total_rows else 0.0

    diagnostics: dict[str, Any] = {
        "source_layout": source_layout,
        "source_rows": source_row_count if source_row_count is not None else total_rows,
        "source_columns": source_column_count,
        "story_column": story_column,
        "date_column_count": date_column_count,
        "normalized_rows": total_rows,
        "parse_success_rows": parse_success_count,
        "parse_failed_rows": int(total_rows - parse_success_count),
        "parse_success_rate": round(parse_rate, 4),
        "default_focus_basis": "origination_year",
        "default_focus_origination_year_min": DEFAULT_ACTIVE_ORIGINATION_YEAR,
        "default_focus_rows_2019_plus": int(len(focus_rows)),
        "historical_rows_pre_2019": int(len(history_rows)),
        "default_focus_slices_2019_plus": int(focus_slices),
        "historical_slices_pre_2019": int(history_slices),
        "rows_missing_origination_year": int(missing_year_mask.sum()),
        "date_min": None if frame.empty else str(frame["date"].min().date()),
        "date_max": None if frame.empty else str(frame["date"].max().date()),
        "failed_story_examples": failures["raw_story_name"].head(10).tolist(),
    }
    return diagnostics


def normalize_bloomberg_wide_frame(
    df: pd.DataFrame,
    *,
    focus_start: str = DEFAULT_REPORT_FOCUS_START,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize Bloomberg-style wide data (stories as rows, dates as columns) into long format."""

    work = df.copy()
    work.columns = [str(col).strip() for col in work.columns]
    date_cols = _date_column_map(work)
    if len(date_cols) < 1:
        raise ValueError("No date-like columns found in wide-format dataset.")

    story_col = _extract_story_column(work, date_cols=date_cols)
    value_cols = list(date_cols.keys())
    melted = work.melt(
        id_vars=[story_col],
        value_vars=value_cols,
        var_name="_header_date",
        value_name="_raw_value",
    )
    melted = melted.rename(columns={story_col: "raw_story_name"})
    melted["raw_story_name"] = melted["raw_story_name"].astype(str).str.strip()
    melted["date"] = melted["_header_date"].map(date_cols)
    melted["value"] = _parse_numeric_series(melted["_raw_value"])

    melted = melted.dropna(subset=["date", "value"])
    melted = melted[melted["raw_story_name"] != ""].copy()
    melted = _normalize_story_fields(melted)

    origination_years = pd.to_numeric(melted["origination_year"], errors="coerce")
    active_vintage_mask = origination_years >= DEFAULT_ACTIVE_ORIGINATION_YEAR
    melted["is_default_focus_window"] = active_vintage_mask
    melted["is_default_focus_vintage"] = active_vintage_mask

    normalized = melted[NORMALIZED_SCHEMA_COLUMNS].copy()
    normalized = normalized.sort_values(["date", "raw_story_name"]).reset_index(drop=True)

    diagnostics = _build_diagnostics(
        normalized,
        source_layout="wide",
        story_column=story_col,
        date_column_count=len(value_cols),
        source_row_count=int(len(work)),
        source_column_count=int(len(work.columns)),
    )
    return normalized, diagnostics


def _wide_frame_from_candidate(raw_df: pd.DataFrame, candidate: WideTableCandidate) -> pd.DataFrame:
    header = raw_df.iloc[candidate.header_row_index]
    story_header = header.iloc[candidate.story_column_index]
    story_column_name = str(story_header).strip() if _is_non_empty(story_header) else "Story"

    selected_indices = [candidate.story_column_index] + candidate.date_column_indices
    table = raw_df.iloc[candidate.header_row_index + 1 :, selected_indices].copy()
    table.columns = [story_column_name] + [header.iloc[idx] for idx in candidate.date_column_indices]

    date_columns = list(table.columns[1:])
    keep_mask = table[story_column_name].map(_is_non_empty)
    if date_columns:
        keep_mask = keep_mask & table[date_columns].notna().any(axis=1)
    return table[keep_mask].reset_index(drop=True)


def normalize_preamble_bloomberg_wide_frame(
    raw_df: pd.DataFrame,
    *,
    focus_start: str = DEFAULT_REPORT_FOCUS_START,
    sheet_name: str | None = None,
    min_wide_date_columns: int = 3,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize wide data when title/blank rows precede the real date header row."""

    candidate = _find_wide_table_candidate(
        raw_df,
        min_wide_date_columns=min_wide_date_columns,
        sheet_name=sheet_name,
    )
    if candidate is None:
        summary = _wide_scan_summary(raw_df)
        raise DatasetLayoutError(
            "Could not find a Bloomberg-style wide table in the sheet. "
            f"Best date-like row had {summary['best_date_header_count']} date-like cells "
            f"at Excel row {summary['best_date_header_row_excel']}."
        )

    table = _wide_frame_from_candidate(raw_df, candidate)
    normalized, diagnostics = normalize_bloomberg_wide_frame(table, focus_start=focus_start)
    diagnostics.update(
        {
            "source_layout": "wide",
            "source_layout_detail": "preamble_wide",
            "sheet_name": sheet_name,
            "source_rows": int(len(raw_df)),
            "source_columns": int(len(raw_df.columns)),
            "detected_header_row_index": int(candidate.header_row_index),
            "detected_header_row_excel": int(candidate.header_row_index + 1),
            "detected_story_column_index": int(candidate.story_column_index),
            "detected_story_column_excel": _excel_column_name(candidate.story_column_index),
            "detected_first_date_column_excel": _excel_column_name(min(candidate.date_column_indices)),
            "detected_last_date_column_excel": _excel_column_name(max(candidate.date_column_indices)),
            "date_column_count": int(len(candidate.date_column_indices)),
            "candidate_story_rows": int(candidate.story_non_empty_rows),
            "candidate_numeric_values": int(candidate.numeric_value_count),
        }
    )
    return normalized, diagnostics


def normalize_long_format_frame(
    df: pd.DataFrame,
    *,
    focus_start: str = DEFAULT_REPORT_FOCUS_START,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Add normalized parsing fields to canonical long-format dataset."""

    work = df.copy()
    work.columns = [str(col).strip().lower() for col in work.columns]
    missing = _LONG_REQUIRED_COLUMNS - set(work.columns)
    if missing:
        raise ValueError(f"Missing required columns for long format: {sorted(missing)}")

    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["value"] = pd.to_numeric(work["can"], errors="coerce")
    work["raw_story_name"] = work["story"].astype(str).str.strip()

    work = work.dropna(subset=["date", "value"])
    work = work[work["raw_story_name"] != ""].copy()
    canonical_coupon = pd.to_numeric(work["coupon"], errors="coerce")
    canonical_year = pd.to_numeric(work["year"], errors="coerce")
    canonical_geo = work["geo"].astype(str).str.upper()
    canonical_story_family = work["story_bucket"].astype(str).str.upper()
    work = _normalize_story_fields(work)

    # Fill parser gaps from canonical long columns when available.
    work["coupon"] = pd.to_numeric(work["coupon"], errors="coerce")
    work["coupon"] = work["coupon"].fillna(canonical_coupon)
    work["origination_year"] = pd.to_numeric(work["origination_year"], errors="coerce")
    work["origination_year"] = work["origination_year"].fillna(canonical_year)
    work["geography"] = work["geography"].fillna(canonical_geo)
    work["story_family"] = work["story_family"].fillna(canonical_story_family)

    origination_years = pd.to_numeric(work["origination_year"], errors="coerce")
    active_vintage_mask = origination_years >= DEFAULT_ACTIVE_ORIGINATION_YEAR
    work["is_default_focus_window"] = active_vintage_mask
    work["is_default_focus_vintage"] = active_vintage_mask

    normalized = work[NORMALIZED_SCHEMA_COLUMNS].copy()
    normalized = normalized.sort_values(["date", "raw_story_name"]).reset_index(drop=True)

    diagnostics = _build_diagnostics(
        normalized,
        source_layout="long",
        source_row_count=int(len(df)),
        source_column_count=int(len(df.columns)),
    )
    return normalized, diagnostics


def normalize_dataset_frame(
    df: pd.DataFrame,
    *,
    focus_start: str = DEFAULT_REPORT_FOCUS_START,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize either long-format or Bloomberg-wide input."""

    layout = detect_input_layout(df)
    if layout == "long":
        return normalize_long_format_frame(df, focus_start=focus_start)
    if layout == "wide":
        date_cols = _date_column_map(df)
        if len(date_cols) >= 1:
            return normalize_bloomberg_wide_frame(df, focus_start=focus_start)
        return normalize_preamble_bloomberg_wide_frame(df, focus_start=focus_start)

    raise DatasetLayoutError(_layout_error_message(df))


def _layout_error_message(
    df: pd.DataFrame,
    *,
    source_label: str | None = None,
    sheet_summaries: list[dict[str, Any]] | None = None,
) -> str:
    lowered = {str(col).strip().lower() for col in df.columns}
    missing_long = sorted(_LONG_REQUIRED_COLUMNS - lowered)
    header_date_count = len(_date_column_map(df))
    scan_summary = _wide_scan_summary(df)

    prefix = "Unrecognized dataset layout"
    if source_label:
        prefix += f" in {source_label}"

    details = [
        f"{prefix}. Expected canonical long format or Bloomberg-style wide format.",
        f"Missing long-format columns: {missing_long}",
        f"Date-like columns in current header: {header_date_count}",
        (
            "Best date-like row scan: "
            f"Excel row {scan_summary['best_date_header_row_excel']} with "
            f"{scan_summary['best_date_header_count']} date-like cells"
        ),
        f"Frame shape: {scan_summary['rows']} rows x {scan_summary['columns']} columns",
    ]
    if sheet_summaries:
        compact = [
            {
                "sheet": item.get("sheet_name"),
                "rows": item.get("rows"),
                "columns": item.get("columns"),
                "best_date_header_row_excel": item.get("best_date_header_row_excel"),
                "best_date_header_count": item.get("best_date_header_count"),
            }
            for item in sheet_summaries
        ]
        details.append(f"Workbook sheet scan: {compact}")
    return " ".join(details)


def _normalize_loaded_sheet_frame(
    frame: pd.DataFrame,
    *,
    focus_start: str,
    sheet_name: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    normalized, diagnostics = normalize_dataset_frame(frame, focus_start=focus_start)
    if sheet_name:
        diagnostics.setdefault("sheet_name", sheet_name)
    return normalized, diagnostics


def _load_excel_candidates(
    source: Path,
    *,
    focus_start: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    excel = pd.ExcelFile(source)
    sheet_summaries: list[dict[str, Any]] = []
    preamble_candidates: list[tuple[WideTableCandidate, pd.DataFrame, str]] = []

    for sheet_name in excel.sheet_names:
        try:
            frame = pd.read_excel(excel, sheet_name=sheet_name)
            layout = detect_input_layout(frame)
            if layout in {"long", "wide"} and len(_date_column_map(frame)) >= 1:
                return _normalize_loaded_sheet_frame(frame, focus_start=focus_start, sheet_name=sheet_name)
            if layout == "long":
                return _normalize_loaded_sheet_frame(frame, focus_start=focus_start, sheet_name=sheet_name)
        except Exception:
            pass

        raw = pd.read_excel(excel, sheet_name=sheet_name, header=None)
        summary = _wide_scan_summary(raw)
        summary["sheet_name"] = sheet_name
        sheet_summaries.append(summary)
        candidate = _find_wide_table_candidate(raw, sheet_name=sheet_name)
        if candidate is not None:
            preamble_candidates.append((candidate, raw, sheet_name))

    if preamble_candidates:
        candidate, raw, sheet_name = max(preamble_candidates, key=lambda item: item[0].score)
        normalized, diagnostics = normalize_preamble_bloomberg_wide_frame(
            raw,
            focus_start=focus_start,
            sheet_name=sheet_name,
        )
        diagnostics["workbook_sheet_count"] = int(len(excel.sheet_names))
        diagnostics["workbook_sheets"] = list(excel.sheet_names)
        diagnostics["selected_sheet"] = sheet_name
        diagnostics["candidate_score"] = float(candidate.score)
        return normalized, diagnostics

    first_raw = pd.read_excel(excel, sheet_name=excel.sheet_names[0], header=None)
    raise DatasetLayoutError(
        _layout_error_message(
            first_raw,
            source_label=str(source),
            sheet_summaries=sheet_summaries,
        )
    )


def load_and_normalize_dataset(
    path: str | Path,
    *,
    focus_start: str = DEFAULT_REPORT_FOCUS_START,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load CSV/XLSX and normalize to long schema with parsing diagnostics."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Input file not found: {source}")

    if source.suffix.lower() in {".xlsx", ".xls"}:
        return _load_excel_candidates(source, focus_start=focus_start)
    else:
        frame = pd.read_csv(source)
        try:
            return normalize_dataset_frame(frame, focus_start=focus_start)
        except DatasetLayoutError:
            raw = pd.read_csv(source, header=None)
            return normalize_preamble_bloomberg_wide_frame(raw, focus_start=focus_start)


def default_reporting_focus(
    frame: pd.DataFrame,
    *,
    focus_start: str = DEFAULT_REPORT_FOCUS_START,
) -> pd.DataFrame:
    """Return 2019+ origination-year focus while preserving full history in the source frame."""

    if "is_default_focus_vintage" in frame.columns:
        return frame[frame["is_default_focus_vintage"].fillna(False)].copy()
    if "is_default_focus_window" in frame.columns:
        return frame[frame["is_default_focus_window"].fillna(False)].copy()

    work = frame.copy()
    years = pd.to_numeric(work.get("origination_year"), errors="coerce")
    return work[years >= DEFAULT_ACTIVE_ORIGINATION_YEAR].copy()
