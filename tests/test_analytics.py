import pandas as pd

from bond_story_reporting.analytics import (
    add_cross_sectional_zscores,
    enumerate_geo_pairs,
    summarize_stories,
    weekly_metric_by_coupon,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2024-01-05",
                    "2024-01-05",
                    "2024-01-12",
                    "2024-01-12",
                    "2024-01-19",
                    "2024-01-19",
                ]
            ),
            "story": [
                "2023 FNCL 5.0 NY",
                "2023 FNCL 5.0 FL",
                "2023 FNCL 5.0 NY",
                "2023 FNCL 5.0 FL",
                "2023 FNCL 5.0 NY",
                "2023 FNCL 5.0 FL",
            ],
            "story_bucket": ["FNCL"] * 6,
            "geo": ["NY", "FL", "NY", "FL", "NY", "FL"],
            "coupon": [5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
            "year": [2023] * 6,
            "can": [100, 104, 101, 103, 102, 105],
            "payup": [1.0, 1.3, 1.1, 1.4, 1.2, 1.5],
            "spread": [45, 44, 46, 43, 45, 42],
            "issuer": ["FNCL"] * 6,
        }
    )


def test_summary_has_expected_columns():
    df = add_cross_sectional_zscores(_sample_df())
    summary = summarize_stories(df)
    assert "mean_can" in summary.columns
    assert "mean_zscore_can" in summary.columns
    assert len(summary) == 2


def test_weekly_coupon_rollup_exists():
    df = add_cross_sectional_zscores(_sample_df())
    weekly = weekly_metric_by_coupon(df, metric="payup")
    assert not weekly.empty
    assert set(["week_end", "story_bucket", "year", "coupon", "payup"]).issubset(weekly.columns)


def test_geo_pair_enumeration():
    df = add_cross_sectional_zscores(_sample_df())
    pairs = enumerate_geo_pairs(df, metric="payup", min_points=2, max_pairs=10)
    assert len(pairs) >= 1
    assert pairs[0]["geo_a"] in {"FL", "NY"}
