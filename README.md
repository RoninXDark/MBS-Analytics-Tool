# MBS Analytics Tool

Desktop Python application for analyzing Mortgage-Backed Securities data from Bloomberg-style Excel/CSV exports.

This project packages a real analyst workflow into a Tkinter desktop tool: load MBS price and residual datasets, parse market price notation, generate batch charts, compare spreads, and export rich/cheap Excel reports.

## Business Problem

Mortgage analysts often receive large Bloomberg-style workbooks with hundreds of bonds and date columns. Manually cleaning those files, plotting histories, comparing spreads, and identifying rich/cheap securities is slow and error-prone.

MBS Analytics Tool reduces that workflow to a desktop interface with repeatable data loading, chart generation, spread analysis, and Excel reporting.

## Features

- Excel/CSV ingestion with automatic date-header detection.
- MBS 32nds price parsing and formatting, including Bloomberg-style tick strings.
- Price history chart generation for single bonds or full batch universes.
- Batch processing for hundreds of securities.
- General/OAS charting workflow for non-price time series.
- Interactive spread calculator for two selected bonds or metrics.
- Residuals analysis with line charts and market overview scatter plots.
- Rich/Cheap Excel report generation for residual outliers.
- Threaded Tkinter UI with status updates and stop control for long runs.

## Tech Stack

- Python
- Tkinter / ttk
- pandas
- matplotlib
- openpyxl
- threading
- PyInstaller-ready desktop packaging workflow

## Repository Structure

```text
MBS-Analytics-Tool-main/
├── src/
│   ├── main.py
│   ├── mbs_backend.py
│   └── mbs_utils.py
├── docs/
│   ├── CLIENT_QUICK_START.md
│   └── screenshots/
├── examples/
│   └── sample_input_format.md
├── README.md
├── requirements.txt
├── .gitignore
└── .gitattributes
```

Generated files such as `build/`, `dist/`, `.exe`, `.idea/`, `__pycache__/`, logs, and analyst Excel outputs are intentionally excluded from Git.

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Launch the desktop app:

```bash
python src/main.py
```

## Input Data

The app expects Bloomberg-style CSV/XLSX files where one column identifies the bond/security and multiple columns contain date-based observations.

For price workflows, values can be standard decimal numbers or MBS 32nds notation such as:

```text
100-16
100-163
99-28+
```

Residuals workflows expect a file with bond/security names, dates, and a residual-style metric column. See `examples/sample_input_format.md` for example layouts.

## Output

The app writes generated charts and reports next to the selected input file, for example:

- `MBS_PRICES_OUTPUT/`
- `MBS_GENERAL_OUTPUT/`
- `MBS_SPREADS/`
- `MBS_RESIDUALS_OUTPUT/`
- `REPORT_RICH_CHEAP.xlsx`
- `REPORT_TOP_MOVERS.xlsx`

These are runtime deliverables and should not be committed to Git.

## Portfolio Highlights

This project demonstrates:

- Real fixed-income analytics context.
- Desktop GUI development with Tkinter.
- Data cleaning for messy Excel/CSV analyst workflows.
- Financial market price parsing in MBS 32nds format.
- Batch chart generation and Excel report automation.
- Threaded UI design for long-running data processing tasks.

## Notes

A previous client-facing guide is preserved in `docs/CLIENT_QUICK_START.md`. The repository root is now optimized for GitHub and portfolio review.