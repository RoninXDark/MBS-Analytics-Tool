from pathlib import Path

import pandas as pd

from bond_story_reporting.foundation import format_32nds, load_timeseries_data, parse_mbs_price
from bond_story_reporting.foundation.backend import generate_curve_analysis, parse_mbs_price_extended


def test_foundation_price_parsers():
    assert parse_mbs_price("100-163") == 100.51171875
    assert parse_mbs_price_extended("100-097") == 100.30859375
    assert format_32nds(100.5) == "100-16"


def test_foundation_loader_reads_wide_csv(tmp_path: Path):
    csv_path = tmp_path / "wide_prices.csv"
    csv_path.write_text(
        "Bond,2024-01-05,2024-01-12\n"
        "2023 FNCL 4.5 NY,100-16,100-17\n"
        "2023 FNCL 5.0 FL,101-00,101-01\n",
        encoding="utf-8",
    )

    statuses: list[str] = []
    frame = load_timeseries_data(str(csv_path), statuses.append, is_price_mode=True)

    assert frame.shape == (2, 2)
    assert list(frame.columns) == ["2023 FNCL 4.5 NY", "2023 FNCL 5.0 FL"]
    assert pd.api.types.is_datetime64_any_dtype(frame.index)
    assert statuses


def test_foundation_curve_generation_smoke(tmp_path: Path):
    idx = pd.to_datetime(["2024-01-05", "2024-01-12", "2024-01-19"])
    df = pd.DataFrame(
        {
            "2023 FNCL 4.5 NY": [100.0, 100.2, 100.4],
            "2023 FNCL 5.0 NY": [101.0, 101.1, 101.3],
        },
        index=idx,
    )

    anchor_file = tmp_path / "source.csv"
    anchor_file.write_text("placeholder", encoding="utf-8")

    chart_path = generate_curve_analysis(
        df=df,
        filepath=str(anchor_file),
        filter_txt="2023 FNCL",
        mode="Time Series",
        period="All History",
    )

    assert Path(chart_path).exists()
