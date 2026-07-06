from __future__ import annotations

import argparse
import json
import logging
import threading
from pathlib import Path

from . import __app_name__, __version__
from .automation import (
    DEFAULT_CONFIG_STORE_PATH,
    DEFAULT_MIN_OBSERVATIONS,
    available_ranking_methods,
    list_saved_batches,
    run_idea_scan,
    run_saved_batch,
    run_weekly_batch,
    show_saved_batch,
)
from .logging_setup import configure_logging
from .ops import bundle_output_artifacts, run_doctor
from .runtime_paths import resolve_default_diagnostics_dir, resolve_default_overnight_output_dir


def _parse_int_csv(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_float_csv(raw: str | None) -> list[float]:
    if not raw:
        return []
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_str_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _status_print(message: str) -> None:
    print(message)


def _add_foundation_subcommands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    periods = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]

    charts = sub.add_parser(
        "foundation-charts",
        help="Run integrated legacy MBS chart generation from wide timeseries files.",
    )
    charts.add_argument("--input", required=True, help="CSV or Excel file")
    charts.add_argument("--mode", choices=["price", "general"], default="price", help="Input metric mode")
    charts.add_argument("--period", choices=periods, default="All History", help="Timeline window")
    charts.add_argument("--normalize", action="store_true", help="Normalize each series to start at zero")
    charts.add_argument("--filter", default="", help="Text filter for bond names")

    spread = sub.add_parser("foundation-spread", help="Build spread chart from integrated legacy foundation.")
    spread.add_argument("--input", required=True, help="CSV or Excel file")
    spread.add_argument("--bond-a", required=True, help="Long bond name")
    spread.add_argument("--bond-b", required=True, help="Short bond name")
    spread.add_argument("--mode", choices=["price", "general"], default="price", help="Input metric mode")
    spread.add_argument("--period", choices=periods, default="All History", help="Timeline window")

    curve = sub.add_parser("foundation-curve", help="Build pay-up history/curve chart from legacy foundation.")
    curve.add_argument("--input", required=True, help="CSV or Excel file")
    curve.add_argument("--filter", required=True, help="Search text for matching stories/bonds")
    curve.add_argument(
        "--chart-mode",
        choices=["time_series", "snapshot"],
        default="time_series",
        help="time_series for history lines, snapshot for latest coupon-vs-price curve",
    )
    curve.add_argument("--period", choices=periods, default="3 Months", help="Timeline window")

    residual_line = sub.add_parser(
        "foundation-residual-line",
        help="Build residual line chart for a selected bond from integrated legacy foundation.",
    )
    residual_line.add_argument("--input", required=True, help="CSV or Excel residuals file")
    residual_line.add_argument("--bond", required=True, help="Exact bond name")
    residual_line.add_argument("--period", choices=periods, default="All History", help="Timeline window")

    residual_scatter = sub.add_parser(
        "foundation-residual-scatter",
        help="Build residual market overview and rich/cheap report from integrated legacy foundation.",
    )
    residual_scatter.add_argument("--input", required=True, help="CSV or Excel residuals file")
    residual_scatter.add_argument("--period", choices=periods, default="All History", help="Timeline window")

    sub.add_parser(
        "foundation-tk",
        help="Launch the unified desktop GUI (legacy tabs + automation).",
    )
    sub.add_parser(
        "desktop-gui",
        help="Launch the unified desktop GUI (legacy tabs + automation).",
    )

    doctor = sub.add_parser("doctor", help="Run environment diagnostics and write doctor_report.json.")
    doctor.add_argument(
        "--output",
        default=str(resolve_default_diagnostics_dir()),
        help="Diagnostics output directory",
    )

    bundle = sub.add_parser("bundle-output", help="Create zip bundle from an output directory.")
    bundle.add_argument("--source", required=True, help="Output directory to bundle")
    bundle.add_argument("--bundle-path", required=False, help="Optional resulting zip path")

    list_configs = sub.add_parser("list-configs", help="List saved automation configurations.")
    list_configs.add_argument(
        "--store",
        default=str(DEFAULT_CONFIG_STORE_PATH),
        help="Path to automation saved-configs JSON file",
    )

    show_config = sub.add_parser("show-config", help="Show one saved automation configuration.")
    show_config.add_argument("--name", required=True, help="Saved configuration name")
    show_config.add_argument(
        "--store",
        default=str(DEFAULT_CONFIG_STORE_PATH),
        help="Path to automation saved-configs JSON file",
    )

    run_config = sub.add_parser(
        "run-config",
        help="Run automation from a saved configuration, including weekly reports or idea scans.",
    )
    run_config.add_argument("--name", required=True, help="Saved configuration name")
    run_config.add_argument(
        "--store",
        default=str(DEFAULT_CONFIG_STORE_PATH),
        help="Path to automation saved-configs JSON file",
    )
    run_config.add_argument(
        "--base-dir",
        required=False,
        help="Base directory for relative preset paths (defaults to current working directory)",
    )

    sub.add_parser("version", help="Print app name and version")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bond Story Reporting Tool")
    sub = parser.add_subparsers(dest="command", required=False)

    weekly = sub.add_parser("run-weekly", help="Run the weekly canned report pack")
    weekly.add_argument("--input", required=True, help="CSV or Excel input file")
    weekly.add_argument("--output", required=True, help="Output directory")
    weekly.add_argument("--midweek-rerun", action="store_true", help="Flag a midweek rerun")

    weekly.add_argument("--years", required=False, help="Comma-separated years (example: 2023,2024,2025,2026)")
    weekly.add_argument("--geos", required=False, help="Comma-separated geos (example: NY,FL,LB125,LIB250)")
    weekly.add_argument("--coupons", required=False, help="Comma-separated coupons (example: 4.5,5.0)")
    weekly.add_argument("--story-buckets", required=False, help="Comma-separated story buckets (example: Texas,FNCL)")
    weekly.add_argument("--issuer", required=False, help="Filter by issuer")
    weekly.add_argument(
        "--rank-by",
        required=False,
        choices=["z_score_can", "payup", "mean_payup"],
        help="Ranking metric for Best/Worst focus charts",
    )

    weekly.add_argument("--best-n", type=int, default=None, help="Top N stories for best/worst ranking charts")
    weekly.add_argument("--worst-n", type=int, default=None, help="Top N stories for worst/richest ranking charts")
    weekly.add_argument("--max-geo-pairs", type=int, default=None, help="Limit auto-generated geo pair charts")

    scan = sub.add_parser(
        "scan-ideas",
        help="Run headless overnight BUY/SELL idea scan with chart package output.",
    )
    scan.add_argument("--input", required=True, help="CSV or Excel input file")
    scan.add_argument(
        "--output",
        default=str(resolve_default_overnight_output_dir()),
        help="Root output directory for dated idea packages",
    )
    scan.add_argument(
        "--ranking-method",
        choices=available_ranking_methods(),
        default="z_score",
        help="Explicit ranking strategy to use for BUY/SELL selection",
    )
    scan.add_argument("--top-n", type=int, default=10, help="Number of BUY and SELL ideas to package")
    scan.add_argument(
        "--full-history",
        action="store_true",
        help="Include full history in scoring instead of the default 2019+ active universe focus",
    )
    scan.add_argument(
        "--chart-active-only",
        action="store_true",
        help="Limit generated charts to the active universe date window instead of full chart history",
    )
    scan.add_argument(
        "--min-observations",
        type=int,
        default=DEFAULT_MIN_OBSERVATIONS,
        help=f"Minimum observations required to score a slice (default: {DEFAULT_MIN_OBSERVATIONS})",
    )
    scan.add_argument("--package-name", required=False, help="Optional fixed package folder name")
    scan.add_argument("--programs", required=False, help="Comma-separated programs (example: FNCL,GNMA)")
    scan.add_argument("--geographies", required=False, help="Comma-separated geographies (example: NY,FL,TX)")
    scan.add_argument("--loan-balance-buckets", required=False, help="Comma-separated loan balance buckets")
    scan.add_argument("--coupons", required=False, help="Comma-separated coupons (example: 4.5,5.0)")
    scan.add_argument("--origination-years", required=False, help="Comma-separated origination years")
    scan.add_argument("--origination-year-min", type=int, default=None, help="Minimum origination year")
    scan.add_argument("--origination-year-max", type=int, default=None, help="Maximum origination year")
    scan.add_argument("--story-families", required=False, help="Comma-separated story families")
    scan.add_argument("--story-tags", required=False, help="Comma-separated story tags/subtypes")
    scan.add_argument("--raw-story-names", required=False, help="Comma-separated exact raw story names")
    scan.add_argument(
        "--exclude-parse-failures",
        action="store_true",
        help="Exclude rows whose story labels could not be parsed",
    )

    _add_foundation_subcommands(sub)

    return parser


def main() -> None:
    log_path = configure_logging()
    logger = logging.getLogger(__name__)

    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        args.command = "desktop-gui"
    logger.info("Command started: %s", args.command)
    logger.info("Application log file: %s", log_path)

    try:
        if args.command == "run-weekly":
            years = _parse_int_csv(args.years)
            geos = _parse_str_csv(args.geos)
            coupons = _parse_float_csv(args.coupons)
            story_buckets = _parse_str_csv(args.story_buckets)

            metadata = run_weekly_batch(
                input_path=Path(args.input),
                output_dir=Path(args.output),
                midweek_rerun=args.midweek_rerun,
                years=years,
                geos=geos,
                coupons=coupons,
                issuer=args.issuer,
                story_buckets=story_buckets,
                rank_by=args.rank_by,
                best_n=args.best_n,
                worst_n=args.worst_n,
                max_geo_pairs=args.max_geo_pairs,
            )
            print("Weekly reports completed")
            print(json.dumps(metadata, indent=2, ensure_ascii=False))
            return

        if args.command == "scan-ideas":
            result = run_idea_scan(
                input_path=Path(args.input),
                output_dir=Path(args.output),
                ranking_method=args.ranking_method,
                top_n=args.top_n,
                use_default_focus=not args.full_history,
                include_full_chart_history=not args.chart_active_only,
                min_observations=args.min_observations,
                package_name=args.package_name,
                programs=_parse_str_csv(args.programs),
                geographies=_parse_str_csv(args.geographies),
                loan_balance_buckets=_parse_str_csv(args.loan_balance_buckets),
                coupons=_parse_float_csv(args.coupons),
                origination_years=_parse_int_csv(args.origination_years),
                origination_year_min=args.origination_year_min,
                origination_year_max=args.origination_year_max,
                story_families=_parse_str_csv(args.story_families),
                story_tags=_parse_str_csv(args.story_tags),
                raw_story_names=_parse_str_csv(args.raw_story_names),
                include_parse_failures=not args.exclude_parse_failures,
            )
            print("Idea scan completed")
            print(json.dumps(result.run_metadata, indent=2, ensure_ascii=False))
            return

        if args.command == "foundation-charts":
            from .foundation import generate_charts, load_timeseries_data

            is_price_mode = args.mode == "price"
            input_path = Path(args.input)
            df = load_timeseries_data(str(input_path), _status_print, is_price_mode=is_price_mode)
            output_path = generate_charts(
                df=df,
                filepath=str(input_path),
                normalize=args.normalize,
                filter_txt=args.filter.strip(),
                period=args.period,
                is_price_mode=is_price_mode,
                stop_event=threading.Event(),
                status_cb=_status_print,
            )
            print(f"Foundation charts generated: {output_path}")
            return

        if args.command == "foundation-spread":
            from .foundation import generate_spread_chart, load_timeseries_data

            is_price_mode = args.mode == "price"
            input_path = Path(args.input)
            df = load_timeseries_data(str(input_path), _status_print, is_price_mode=is_price_mode)
            output_path = generate_spread_chart(
                df=df,
                bond_a=args.bond_a,
                bond_b=args.bond_b,
                filepath=str(input_path),
                period=args.period,
                is_price_mode=is_price_mode,
            )
            print(f"Foundation spread chart generated: {output_path}")
            return

        if args.command == "foundation-curve":
            from .foundation import generate_curve_analysis, load_timeseries_data

            input_path = Path(args.input)
            df = load_timeseries_data(str(input_path), _status_print, is_price_mode=True)
            chart_mode = "Time Series" if args.chart_mode == "time_series" else "Curve"
            output_path = generate_curve_analysis(
                df=df,
                filepath=str(input_path),
                filter_txt=args.filter.strip(),
                mode=chart_mode,
                period=args.period,
            )
            print(f"Foundation curve chart generated: {output_path}")
            return

        if args.command == "foundation-residual-line":
            from .foundation import generate_residual_line_chart, load_residuals_data

            input_path = Path(args.input)
            df = load_residuals_data(str(input_path), _status_print)
            output_path = generate_residual_line_chart(
                df=df,
                bond_name=args.bond,
                filepath=str(input_path),
                period=args.period,
            )
            print(f"Foundation residual line chart generated: {output_path}")
            return

        if args.command == "foundation-residual-scatter":
            from .foundation import load_residuals_data, process_residuals_scatter

            input_path = Path(args.input)
            df = load_residuals_data(str(input_path), _status_print)
            output_path = process_residuals_scatter(
                df=df,
                filepath=str(input_path),
                period=args.period,
                stop_event=threading.Event(),
                status_cb=_status_print,
            )
            print(f"Foundation residual package generated: {output_path}")
            return

        if args.command in {"foundation-tk", "desktop-gui"}:
            from .gui import launch_desktop_gui

            launch_desktop_gui()
            return

        if args.command == "doctor":
            report = run_doctor(output_dir=args.output)
            print("Environment diagnostics completed")
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return

        if args.command == "bundle-output":
            zip_path = bundle_output_artifacts(source_dir=args.source, bundle_path=args.bundle_path)
            print(f"Bundle created: {zip_path}")
            return

        if args.command == "list-configs":
            names = list_saved_batches(config_store_path=args.store)
            payload = {
                "store": str(Path(args.store).resolve()),
                "count": len(names),
                "configs": names,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        if args.command == "show-config":
            config_payload = show_saved_batch(config_name=args.name, config_store_path=args.store)
            payload = {
                "store": str(Path(args.store).resolve()),
                "name": args.name,
                "config": config_payload,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        if args.command == "run-config":
            result = run_saved_batch(
                config_name=args.name,
                config_store_path=args.store,
                base_dir=args.base_dir,
            )
            print(f"Saved config '{args.name}' completed")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return

        if args.command == "version":
            print(f"{__app_name__} v{__version__}")
            return
    except Exception as exc:
        logger.exception("Command failed: %s", args.command)
        print(f"Error: {exc}")
        print(f"See log for details: {log_path}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
