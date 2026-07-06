import pandas as pd

from bond_story_reporting.data import normalize_bloomberg_wide_frame
from bond_story_reporting.reporting import (
    COMPARABLE_KEY_COLUMNS,
    DEFAULT_MIN_OBSERVATIONS,
    ScoringFilters,
    add_comparable_keys,
    filter_scoring_universe,
    generate_ranked_ideas,
    rank_story_slices,
    score_story_slices,
)


def _normalized_sample() -> pd.DataFrame:
    wide = pd.DataFrame(
        {
            "Story": [
                "2023 FNCL 5.0 NY LB125",
                "2023 FNCL 5.0 FL LB125",
                "2025 GNMA 4.5 TX",
                "2017 FNCL 4.0 NY",
            ],
            "2018-12-28": [100.0, 101.0, 102.0, 95.0],
            "2019-01-04": [100.0, 101.0, 102.0, 96.0],
            "2019-01-11": [99.0, 103.0, 101.0, 97.0],
            "2019-01-18": [98.0, 105.0, 100.0, 98.0],
        }
    )
    normalized, _ = normalize_bloomberg_wide_frame(wide)
    return normalized


def test_add_comparable_keys_uses_parsed_dimensions():
    frame = add_comparable_keys(_normalized_sample())

    assert "comparable_key" in frame.columns
    assert all(column in frame["comparable_key"].iloc[0] for column in COMPARABLE_KEY_COLUMNS)
    assert frame["comparable_key"].nunique() == 4


def test_score_story_slices_defaults_to_2019_focus():
    scores, diagnostics = score_story_slices(_normalized_sample(), min_observations=2)

    assert diagnostics["use_default_focus"] is True
    assert diagnostics["default_focus_basis"] == "origination_year"
    assert diagnostics["filtered_rows"] == 12
    assert diagnostics["filtered_historical_rows_pre_2019"] == 0
    assert diagnostics["min_observations"] == 2
    assert len(scores) == 3
    assert set(scores["origination_year"].astype(int)) == {2023, 2025}
    assert {"current_value", "low", "high", "mean", "std", "z_score"}.issubset(scores.columns)


def test_score_story_slices_can_include_full_history():
    _, focus_diag = score_story_slices(_normalized_sample(), use_default_focus=True, min_observations=2)
    _, full_diag = score_story_slices(_normalized_sample(), use_default_focus=False, min_observations=2)

    assert full_diag["filtered_rows"] > focus_diag["filtered_rows"]
    assert full_diag["filtered_historical_rows_pre_2019"] > 0


def test_filter_scoring_universe_supports_core_dimensions():
    frame = _normalized_sample()
    filtered = filter_scoring_universe(
        frame,
        filters=ScoringFilters(
            programs=["FNCL"],
            geographies=["NY"],
            loan_balance_buckets=["LB125"],
            coupons=[5.0],
            origination_year_min=2020,
            origination_year_max=2024,
        ),
    )

    assert not filtered.empty
    assert filtered["program"].eq("FNCL").all()
    assert filtered["geography"].eq("NY").all()
    assert filtered["coupon"].eq(5.0).all()


def test_generate_ranked_ideas_returns_buy_and_sell_lists():
    result = generate_ranked_ideas(_normalized_sample(), ranking_basis="z_score", top_n=2, min_observations=2)

    assert len(result.buy_candidates) == 2
    assert len(result.sell_candidates) == 2
    assert result.buy_candidates.iloc[0]["z_score"] <= result.buy_candidates.iloc[-1]["z_score"]
    assert result.sell_candidates.iloc[0]["z_score"] >= result.sell_candidates.iloc[-1]["z_score"]
    assert result.diagnostics["ranking_basis"] == "z_score"


def test_rank_story_slices_supports_raw_value_payup_alias():
    scores, _ = score_story_slices(_normalized_sample(), min_observations=2)
    buy, sell = rank_story_slices(scores, ranking_basis="payup", top_n=1)

    assert buy.iloc[0]["current_value"] == scores["current_value"].min()
    assert sell.iloc[0]["current_value"] == scores["current_value"].max()


def test_default_min_observations_is_50():
    scores, diagnostics = score_story_slices(_normalized_sample())

    assert DEFAULT_MIN_OBSERVATIONS == 50
    assert diagnostics["min_observations"] == 50
    assert scores.empty
    assert diagnostics["insufficient_observation_slices"] == 3
