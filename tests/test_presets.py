from pathlib import Path

import pandas as pd

from bond_story_reporting.presets import (
    load_saved_configs_map,
    list_saved_config_names,
    read_saved_config,
    run_saved_configuration,
    write_saved_configs_map,
)


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
            ]
        )
    return pd.DataFrame(rows)


def test_saved_config_roundtrip(tmp_path: Path):
    store_path = tmp_path / "automation_saved_configs.json"
    payload = {"Demo Config": {"auto_input": "sample_data.csv", "auto_output": "output"}}
    write_saved_configs_map(payload, config_store_path=store_path)

    names = list_saved_config_names(config_store_path=store_path)
    cfg = read_saved_config(config_name="Demo Config", config_store_path=store_path)

    assert names == ["Demo Config"]
    assert cfg["auto_input"] == "sample_data.csv"


def test_saved_config_supports_utf8_bom(tmp_path: Path):
    store_path = tmp_path / "automation_saved_configs.json"
    raw = '\ufeff{"configs": {"BOM Config": {"auto_input": "sample.csv"}}}'
    store_path.write_text(raw, encoding="utf-8")

    loaded = load_saved_configs_map(config_store_path=store_path)
    assert "BOM Config" in loaded


def test_run_saved_configuration_smoke(tmp_path: Path):
    input_path = tmp_path / "sample.csv"
    _sample_df().to_csv(input_path, index=False)
    output_dir = tmp_path / "out"
    store_path = tmp_path / "automation_saved_configs.json"

    write_saved_configs_map(
        {
            "Texas Mid-Coupons": {
                "auto_input": str(input_path),
                "auto_output": str(output_dir),
                "auto_midweek": False,
                "auto_years": "2023,2025",
                "auto_geos": "NY,FL,TX",
                "auto_coupons": "4.5,5.0",
                "auto_buckets": "Texas,FNCL",
                "auto_issuer": "",
                "auto_date_from": "2024-01-05",
                "auto_date_to": "2024-01-26",
                "auto_rank_by": "Z-Score",
                "auto_generate_excel_stats": True,
                "auto_generate_individual_charts": True,
                "auto_generate_versus_charts": True,
                "auto_best_n": "2",
                "auto_worst_n": "2",
                "auto_max_geo_pairs": "5",
            }
        },
        config_store_path=store_path,
    )

    result = run_saved_configuration(
        config_name="Texas Mid-Coupons",
        config_store_path=store_path,
        base_dir=tmp_path,
    )

    assert result["config_name"] == "Texas Mid-Coupons"
    assert result["rank_label"] == "Z-Score"
    assert (output_dir / "report_metadata.json").exists()
