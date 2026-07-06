import json
import os
from pathlib import Path

import pandas as pd

from bond_story_reporting.automation import (
    IdeaScanRunDefinition,
    available_ranking_methods,
    resolve_ranking_strategy,
    run_idea_scan,
    run_idea_scan_definition,
    run_saved_batch,
)


def _write_wide_input(path: Path) -> None:
    pd.DataFrame(
        {
            "Story": [
                "2023 FNCL 5.0 NY LB125",
                "2023 FNCL 5.0 FL LB125",
                "2025 GNMA 4.5 TX",
            ],
            "2018-12-28": [100.0, 101.0, 102.0],
            "2019-01-04": [100.0, 101.0, 102.0],
            "2019-01-11": [99.0, 103.0, 101.0],
            "2019-01-18": [98.0, 105.0, 100.0],
        }
    ).to_csv(path, index=False)


def test_ranking_strategy_registry_is_explicit():
    methods = available_ranking_methods()
    assert "z_score" in methods
    assert "payup" in methods
    assert resolve_ranking_strategy("z-score").ranking_basis == "z_score"


def test_run_idea_scan_writes_complete_package(tmp_path: Path):
    input_path = tmp_path / "wide.csv"
    _write_wide_input(input_path)

    result = run_idea_scan(
        input_path=input_path,
        output_dir=tmp_path / "overnight",
        ranking_method="z_score",
        top_n=1,
        package_name="nightly_test",
        min_observations=2,
    )

    package_dir = tmp_path / "overnight" / "nightly_test"
    assert result.output_dir == package_dir
    assert (package_dir / "diagnostics" / "technical_buy_candidates.csv").exists()
    assert (package_dir / "diagnostics" / "technical_sell_candidates.csv").exists()
    assert (package_dir / "diagnostics" / "technical_buy_sell_summary.csv").exists()
    assert (package_dir / "CLIENT_REPORT_BUY_SELL.xlsx").exists()
    assert not (package_dir / "buy_sell_summary.xlsx").exists()
    assert (package_dir / "charts" / "buy").exists()
    assert (package_dir / "charts" / "sell").exists()
    assert (package_dir / "diagnostics" / "chart_metadata.csv").exists()
    assert (package_dir / "diagnostics" / "package_metadata.json").exists()
    assert (package_dir / "diagnostics" / "run_metadata.json").exists()
    assert len(list((package_dir / "charts" / "buy").glob("*.png"))) == 1
    assert len(list((package_dir / "charts" / "sell").glob("*.png"))) == 1
    assert result.run_metadata["ranking_strategy"]["name"] == "z_score"
    assert result.run_metadata["client_summary"]["summary_workbook"].endswith("CLIENT_REPORT_BUY_SELL.xlsx")
    assert result.run_metadata["normalization_diagnostics"]["source_layout"] == "wide"


def test_run_idea_scan_supports_filters_and_full_history(tmp_path: Path):
    input_path = tmp_path / "wide.csv"
    _write_wide_input(input_path)

    result = run_idea_scan(
        input_path=input_path,
        output_dir=tmp_path / "overnight",
        ranking_method="payup",
        top_n=1,
        use_default_focus=False,
        include_full_chart_history=False,
        package_name="filtered_test",
        min_observations=2,
        programs=["FNCL"],
        geographies=["NY"],
        coupons=[5.0],
        origination_year_min=2020,
    )

    assert result.run_metadata["use_default_focus"] is False
    assert result.run_metadata["include_full_chart_history"] is False
    assert result.run_metadata["ranking_strategy"]["name"] == "payup"
    assert result.package_result.metadata["charts_generated"] >= 1


def test_run_definition_can_be_loaded_from_saved_config_mapping(tmp_path: Path):
    input_path = tmp_path / "wide.csv"
    _write_wide_input(input_path)

    definition = IdeaScanRunDefinition.from_mapping(
        {
            "workflow": "idea_scan",
            "input_path": "wide.csv",
            "output_dir": "overnight",
            "ranking_method": "z-score",
            "top_n": "1",
            "full_history": True,
            "chart_active_only": True,
            "package_name": "definition_test",
            "min_observations": 2,
            "filters": {
                "programs": "FNCL",
                "geographies": ["NY"],
                "coupons": "5.0",
                "origination_year_min": "2020",
            },
        },
        base_dir=tmp_path,
    )

    assert definition.input_path == tmp_path / "wide.csv"
    assert definition.output_dir == tmp_path / "overnight"
    assert definition.ranking_method == "z_score"
    assert definition.use_default_focus is False
    assert definition.include_full_chart_history is False
    assert definition.programs == ["FNCL"]
    assert definition.geographies == ["NY"]
    assert definition.coupons == [5.0]

    result = run_idea_scan_definition(definition)
    assert result.run_metadata["run_definition"]["workflow"] == "idea_scan"
    assert (tmp_path / "overnight" / "definition_test" / "diagnostics" / "run_metadata.json").exists()


def test_run_definition_can_select_latest_file_from_input_folder(tmp_path: Path):
    input_dir = tmp_path / "nightly_input"
    input_dir.mkdir()
    older = input_dir / "older.csv"
    newer = input_dir / "newer.csv"
    ignored_lock = input_dir / "~$newer.csv"
    _write_wide_input(older)
    _write_wide_input(newer)
    _write_wide_input(ignored_lock)
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    os.utime(ignored_lock, (300, 300))

    definition = IdeaScanRunDefinition.from_mapping(
        {
            "workflow": "idea_scan",
            "input_mode": "latest_file",
            "input_dir": "nightly_input",
            "input_pattern": "*.csv",
            "output_dir": "overnight",
            "ranking_method": "z_score",
            "top_n": 1,
            "package_name": "latest_file_test",
            "min_observations": 2,
        },
        base_dir=tmp_path,
    )

    assert definition.input_path == newer
    assert definition.input_mode == "latest_file"
    assert definition.input_dir == input_dir
    assert definition.input_pattern == "*.csv"

    result = run_idea_scan_definition(definition)
    assert result.run_metadata["input_resolution"]["mode"] == "latest_file"
    assert result.run_metadata["input_resolution"]["resolved_input_path"] == str(newer)
    assert (tmp_path / "overnight" / "latest_file_test" / "diagnostics" / "run_metadata.json").exists()


def test_run_config_dispatches_idea_scan_workflow(tmp_path: Path):
    input_path = tmp_path / "wide.csv"
    _write_wide_input(input_path)
    store = tmp_path / "configs.json"
    store.write_text(
        json.dumps(
            {
                "configs": {
                    "Nightly Ideas": {
                        "workflow": "idea_scan",
                        "input_path": "wide.csv",
                        "output_dir": "overnight",
                        "ranking_method": "payup",
                        "top_n": 1,
                        "package_name": "from_saved_config",
                        "min_observations": 2,
                        "filters": {
                            "programs": ["FNCL"],
                            "geographies": ["NY"],
                            "coupons": [5.0],
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_saved_batch(
        "Nightly Ideas",
        config_store_path=store,
        base_dir=tmp_path,
    )

    package_dir = tmp_path / "overnight" / "from_saved_config"
    assert result["workflow"] == "idea_scan"
    assert result["metadata"]["ranking_strategy"]["name"] == "payup"
    assert (package_dir / "diagnostics" / "technical_buy_candidates.csv").exists()
    assert (package_dir / "diagnostics" / "technical_sell_candidates.csv").exists()
