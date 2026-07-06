from pathlib import Path

import pandas as pd

from bond_story_reporting.automation import run_weekly_batch
from bond_story_reporting.dashboard import main as dashboard_main
from bond_story_reporting.data import apply_filters, load_dataset
from bond_story_reporting.gui import create_desktop_root, launch_desktop_gui
from bond_story_reporting.reporting import run_weekly_reports


def test_boundary_imports_are_available():
    assert callable(load_dataset)
    assert callable(apply_filters)
    assert callable(run_weekly_reports)
    assert callable(run_weekly_batch)
    assert callable(create_desktop_root)
    assert callable(launch_desktop_gui)


def test_dashboard_entrypoint_is_removed():
    try:
        dashboard_main()
    except SystemExit as exc:
        assert "removed" in str(exc).lower()
    else:
        raise AssertionError("dashboard_main should exit with removal message")


def test_run_weekly_batch_smoke(tmp_path: Path):
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
            ]
        )
    input_path = tmp_path / "sample.csv"
    pd.DataFrame(rows).to_csv(input_path, index=False)

    output_dir = tmp_path / "out"
    metadata = run_weekly_batch(
        input_path=input_path,
        output_dir=output_dir,
        years=[2023, 2025],
        geos=["NY", "FL", "TX"],
        coupons=[4.5, 5.0],
        story_buckets=["FNCL", "Texas"],
        best_n=2,
        worst_n=2,
        max_geo_pairs=10,
    )

    assert metadata["records"] > 0
    assert (output_dir / "report_metadata.json").exists()
