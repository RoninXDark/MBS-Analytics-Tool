# MBS Analytics Tool

Desktop Python application for analyzing Mortgage-Backed Securities data from Bloomberg-style Excel/CSV files.

This project is positioned as a practical analyst workflow tool, not a toy demo: it ingests MBS datasets, normalizes bond/story fields, generates charts and rankings, and produces Excel reports for repeatable rich/cheap analysis.

## Business Problem

Mortgage analysts often work with large Bloomberg-style workbooks where prices, payups, coupons, vintages, geographies, and residual metrics are spread across many columns or tabs. Manually cleaning these files and creating repeatable charts is slow, error-prone, and hard to scale across hundreds of bonds.

The tool helps analysts answer questions such as:

- Which bonds or stories look rich or cheap versus recent history?
- How do payups compare by coupon, vintage, geography, or loan-balance bucket?
- Which BUY/SELL ideas should be reviewed first?
- Can a repeatable report package be produced from the latest workbook without manual chart work?

## Features

- Excel/CSV ingestion with support for canonical long format and Bloomberg-style wide files.
- Automatic date-header detection and dataset normalization.
- MBS 32nds price parsing and formatting, including extended tick formats.
- Batch chart generation for large bond/story universes.
- Payup, Z-score, spread, and residual analysis workflows.
- Rich/cheap BUY/SELL idea scanner with configurable ranking method and filters.
- Client-readable Excel report generation with chart links and embedded chart sheets.
- Tkinter/ttkbootstrap desktop GUI for analyst workflows.
- CLI commands for scheduled runs, diagnostics, report generation, and packaging.
- Tests covering parsing, normalization, reporting, automation, scoring, and desktop boundaries.

## Tech Stack

- Python
- pandas / NumPy
- matplotlib
- Tkinter / ttkbootstrap
- openpyxl
- scikit-learn
- PyYAML
- pytest
- PyInstaller packaging support

## Architecture

```text
MBS-Analytics-Tool/
|-- bond_story_reporting/
|   |-- automation/          # saved configs, workflow registry, batch runs
|   |-- data/                # Bloomberg/canonical normalization and story parsing
|   |-- foundation/          # legacy MBS desktop workflows: charts, spreads, residuals
|   |-- gui/                 # desktop launch boundary
|   |-- reporting/           # report packages, scoring, BUY/SELL idea workbooks
|   |-- analytics.py         # metrics, ranking, weekly aggregation
|   |-- charts.py            # reusable chart builders
|   |-- cli.py               # command-line interface
|   |-- report_runner.py     # weekly/canned report orchestration
|   `-- runtime_paths.py     # safe runtime folders for logs/output/configs
|-- config/                  # default report templates
|-- docs/                    # operator and release notes
|-- examples/                # example saved configs and input format docs
|-- sample_data/             # small anonymized sample dataset
|-- tests/                   # automated regression tests
|-- main.py                  # CLI entrypoint
|-- requirements.txt
`-- requirements-dev.txt
```

The code is kept as a normal Python package (`bond_story_reporting`) instead of hiding it inside generated build folders. Runtime files are written outside the source tree or ignored by Git.

## Quick Start

Create an environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

Run diagnostics:

```bash
python main.py doctor
```

Launch the desktop app:

```bash
python main.py desktop-gui
```

Windows launcher:

```bat
run_desktop_gui.bat
```

## Example CLI Workflows

Run a BUY/SELL idea scan against the sample dataset:

```bash
python main.py scan-ideas --input sample_data/bond_stories_sample.csv --ranking-method z_score --top-n 10
```

Generate a weekly report package:

```bash
python main.py run-weekly --input sample_data/bond_stories_sample.csv --output output
```

Run a saved automation config:

```bash
python main.py run-config --name "Nightly BUY SELL Ideas"
```

List saved configs:

```bash
python main.py list-configs
```

## Input Data

The app supports two broad input styles:

- Canonical long format with fields such as `date`, `story`, `story_bucket`, `geo`, `coupon`, `year`, `can`, `payup`, `spread`, and `issuer`.
- Bloomberg-style wide exports where date columns are detected and normalized into analysis-ready records.

See `examples/sample_input_format.md` and `sample_data/bond_stories_sample.csv`.

## Outputs

Generated outputs are intentionally ignored by Git. A typical run can create:

- `CLIENT_REPORT_BUY_SELL.xlsx`
- `CLIENT_REPORT_INDEX.xlsx`
- chart PNG folders
- technical CSV diagnostics
- metadata JSON files
- runtime logs

These files are deliverables, not source code, so they should not be committed to the repository.

## Tests

Run the test suite:

```bash
python -m pytest
```

The tests cover core analytics, data normalization, MBS price parsing, report package generation, workflow routing, and GUI/desktop boundaries.

## Portfolio Highlights

This project demonstrates:

- Real business context in fixed-income / mortgage analytics.
- Desktop application development with Python and Tkinter.
- Data engineering around messy Excel/CSV analyst workflows.
- Financial-data parsing, ranking, and report automation.
- Production-oriented hygiene: tests, CLI, runtime paths, docs, sample data, and Git cleanup.

## Repository Hygiene

The repository excludes generated artifacts such as `build/`, `dist/`, `output/`, `logs/`, `.pytest_cache/`, `__pycache__/`, `.exe`, and large analyst workbooks. This keeps GitHub language statistics focused on the Python application code.
