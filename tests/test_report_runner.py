from pathlib import Path

import pandas as pd

from bond_story_reporting.report_runner import run_weekly_reports


def _sample_df() -> pd.DataFrame:
    rows = []
    for dt in pd.to_datetime(["2024-01-05", "2024-01-12", "2024-01-19", "2024-01-26"]):
        rows.extend(
            [
                {
                    "date": dt,
                    "story": "2023 FNCL 5.0 NY",
                    "story_bucket": "FNCL",
                    "geo": "NY",
                    "coupon": 5.0,
                    "year": 2023,
                    "can": 101.0,
                    "payup": 1.2,
                    "spread": 45.0,
                    "issuer": "FNCL",
                },
                {
                    "date": dt,
                    "story": "2023 FNCL 5.0 FL",
                    "story_bucket": "FNCL",
                    "geo": "FL",
                    "coupon": 5.0,
                    "year": 2023,
                    "can": 103.0,
                    "payup": 1.4,
                    "spread": 43.0,
                    "issuer": "FNCL",
                },
                {
                    "date": dt,
                    "story": "100% Texas 2025 4.5",
                    "story_bucket": "Texas",
                    "geo": "TX",
                    "coupon": 4.5,
                    "year": 2025,
                    "can": 110.0,
                    "payup": 2.1,
                    "spread": 42.0,
                    "issuer": "Texas",
                },
                {
                    "date": dt,
                    "story": "100% Texas 2025 5.0",
                    "story_bucket": "Texas",
                    "geo": "TX",
                    "coupon": 5.0,
                    "year": 2025,
                    "can": 112.0,
                    "payup": 2.4,
                    "spread": 41.0,
                    "issuer": "Texas",
                },
                {
                    "date": dt,
                    "story": "100% Texas 2026 5.0",
                    "story_bucket": "Texas",
                    "geo": "TX",
                    "coupon": 5.0,
                    "year": 2026,
                    "can": 113.0,
                    "payup": 2.6,
                    "spread": 40.0,
                    "issuer": "Texas",
                },
            ]
        )
    return pd.DataFrame(rows)


def test_weekly_report_writes_expected_outputs(tmp_path: Path):
    df = _sample_df()
    metadata = run_weekly_reports(df, output_dir=tmp_path, midweek_rerun=True)

    assert metadata["midweek_rerun"] is True
    assert metadata["rank_by"] == "z_score_can"
    assert (tmp_path / "tables" / "story_summary.csv").exists()
    assert (tmp_path / "tables" / "rankings_latest.csv").exists()
    assert (tmp_path / "tables" / "rankings_focus.csv").exists()
    assert (tmp_path / "charts" / "coupon_packs").exists()
    assert (tmp_path / "report_metadata.json").exists()


def test_weekly_report_supports_mean_rank_by(tmp_path: Path):
    df = _sample_df()
    metadata = run_weekly_reports(
        df,
        output_dir=tmp_path,
        config_overrides={"rank_by": "mean_payup"},
    )

    assert metadata["rank_by"] == "mean_payup"
    assert metadata["rank_by_label"] == "Mean Pay-up"
    assert (tmp_path / "tables" / "rankings_focus.csv").exists()


def test_weekly_report_respects_output_options(tmp_path: Path):
    df = _sample_df()
    metadata = run_weekly_reports(
        df,
        output_dir=tmp_path,
        config_overrides={
            "output_options": {
                "generate_excel_stats": False,
                "generate_individual_charts": False,
                "generate_versus_charts": False,
            }
        },
    )

    assert metadata["output_options"]["generate_excel_stats"] is False
    assert metadata["chart_counts"]["coupon_packs"] == 0
    assert metadata["chart_counts"]["versus"] == 0
    assert not (tmp_path / "tables" / "story_summary.csv").exists()


def test_weekly_report_progress_callback(tmp_path: Path):
    df = _sample_df()
    events: list[tuple[int, int, str]] = []

    run_weekly_reports(
        df,
        output_dir=tmp_path,
        config_overrides={
            "output_options": {
                "generate_excel_stats": True,
                "generate_individual_charts": True,
                "generate_versus_charts": True,
            }
        },
        progress_cb=lambda done, total, msg: events.append((done, total, msg)),
    )

    assert events, "Expected progress callback events"
    start_done, start_total, _ = events[0]
    end_done, end_total, _ = events[-1]
    assert start_done == 0
    assert start_total >= 1
    assert end_done == end_total
