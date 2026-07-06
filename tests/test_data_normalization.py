from pathlib import Path

import pandas as pd

from bond_story_reporting.data import (
    DEFAULT_REPORT_FOCUS_START,
    detect_input_layout,
    load_and_normalize_dataset,
    normalize_bloomberg_wide_frame,
    normalize_dataset_frame,
    parse_story_label,
)


def test_parse_story_label_handles_structured_and_malformed_values():
    parsed = parse_story_label("2023 FNCL 5.0 NY LB125 Spec")
    assert parsed["parse_success"] is True
    assert parsed["coupon"] == 5.0
    assert parsed["origination_year"] == 2023
    assert parsed["geography"] == "NY"

    malformed = parse_story_label("???")
    assert malformed["parse_success"] is False
    assert malformed["parse_error"] is not None


def test_detect_input_layout_for_long_and_wide():
    long_df = pd.DataFrame(
        {
            "date": ["2024-01-05"],
            "story": ["2023 FNCL 5.0 NY"],
            "story_bucket": ["FNCL"],
            "geo": ["NY"],
            "coupon": [5.0],
            "year": [2023],
            "can": [101.0],
            "payup": [1.2],
            "spread": [45.0],
            "issuer": ["FNCL"],
        }
    )
    wide_df = pd.DataFrame(
        {
            "Story": ["2023 FNCL 5.0 NY"],
            "2018-12-28": ["100-16"],
            "2019-01-04": ["100-17+"],
            "2019-01-11": ["100-18"],
        }
    )
    assert detect_input_layout(long_df) == "long"
    assert detect_input_layout(wide_df) == "wide"


def test_normalize_bloomberg_wide_frame_with_historical_and_focus_rows():
    wide_df = pd.DataFrame(
        {
            "Story": [
                "2023 FNCL 5.0 NY",
                "100% Texas 2025 4.5 LB125 FL",
                "2017 FNCL 4.0 NY",
                "???",
            ],
            "2018-12-28": ["100-16", "101-00", "95-00", None],
            "2019-01-04": ["100-17+", "101-04", "96-00", "99-00"],
            "2019-01-11": ["100-18", "101-05", "97-00", "99-02"],
        }
    )

    normalized, diagnostics = normalize_bloomberg_wide_frame(wide_df, focus_start=DEFAULT_REPORT_FOCUS_START)

    assert {"raw_story_name", "date", "value", "parse_success", "is_default_focus_window"}.issubset(
        normalized.columns
    )
    assert not normalized.empty
    assert normalized["date"].min().year <= 2018
    assert normalized["date"].max().year >= 2019
    assert diagnostics["default_focus_basis"] == "origination_year"
    assert diagnostics["historical_rows_pre_2019"] == 3
    assert diagnostics["default_focus_rows_2019_plus"] > 0
    assert diagnostics["parse_failed_rows"] >= 1


def test_normalize_preamble_wide_frame_detects_real_header_row():
    raw_df = pd.DataFrame(
        [
            [None, None, None, None, None],
            ["Bloomberg export", None, None, None, None],
            [None, None, pd.Timestamp("2018-12-28"), pd.Timestamp("2019-01-04"), pd.Timestamp("2019-01-11")],
            [None, "FNCL 1.5 2021 LB175", "1-005", "1-006", "1-007"],
            [None, "FNCL 2 2006 NY", "0-160", "0-170", "0-180"],
        ]
    )

    normalized, diagnostics = normalize_dataset_frame(raw_df)

    assert detect_input_layout(raw_df) == "wide"
    assert len(normalized) == 6
    assert diagnostics["source_layout"] == "wide"
    assert diagnostics["source_layout_detail"] == "preamble_wide"
    assert diagnostics["detected_header_row_excel"] == 3
    assert diagnostics["detected_story_column_excel"] == "B"
    assert diagnostics["date_column_count"] == 3
    assert diagnostics["historical_rows_pre_2019"] == 3


def test_load_and_normalize_dataset_detects_preamble_excel_sheet(tmp_path: Path):
    xlsx_path = tmp_path / "bbg_style.xlsx"
    raw_df = pd.DataFrame(
        [
            [None, None, None, None, None],
            [None, None, pd.Timestamp("2026-04-22"), pd.Timestamp("2026-04-21"), pd.Timestamp("2026-04-20")],
            [None, "FNCL 1.5 2021 LB175", "1-005", "1-005", "1-004"],
            [None, "FNCL 1.5 2020 TX", "0-090", "0-091", "0-090"],
        ]
    )
    raw_df.to_excel(xlsx_path, index=False, header=False, sheet_name="Sheet1")

    normalized, diagnostics = load_and_normalize_dataset(xlsx_path)

    assert len(normalized) == 6
    assert diagnostics["selected_sheet"] == "Sheet1"
    assert diagnostics["detected_header_row_excel"] == 2
    assert diagnostics["detected_story_column_excel"] == "B"


def test_normalize_dataset_frame_with_long_input():
    long_df = pd.DataFrame(
        {
            "date": ["2018-12-28", "2019-01-04"],
            "story": ["2023 FNCL 5.0 NY", "2018 FNCL 5.0 NY"],
            "story_bucket": ["FNCL", "FNCL"],
            "geo": ["NY", "NY"],
            "coupon": [5.0, 5.0],
            "year": [2023, 2018],
            "can": [100.5, 100.75],
            "payup": [1.2, 1.25],
            "spread": [45.0, 45.2],
            "issuer": ["FNCL", "FNCL"],
        }
    )

    normalized, diagnostics = normalize_dataset_frame(long_df)
    assert len(normalized) == 2
    assert diagnostics["source_layout"] == "long"
    assert diagnostics["historical_rows_pre_2019"] == 1
    assert normalized["is_default_focus_window"].tolist() == [True, False]


def test_load_and_normalize_dataset_smoke(tmp_path: Path):
    csv_path = tmp_path / "wide_input.csv"
    pd.DataFrame(
        {
            "Story": ["2023 FNCL 5.0 NY"],
            "2019-01-04": ["100-17+"],
            "2019-01-11": ["100-18"],
            "2019-01-18": ["100-19"],
        }
    ).to_csv(csv_path, index=False)

    normalized, diagnostics = load_and_normalize_dataset(csv_path)
    assert len(normalized) == 3
    assert diagnostics["source_layout"] == "wide"
