# MBS Analytics Beta Quick Start

This beta is desktop-only. The client should normally use the launchers, not raw Python commands.

## What To Open First

Use:

```bat
run_desktop_gui.bat
```

This opens the desktop GUI. If the packaged executable is present, double-clicking `MBSAnalytics.exe` also opens the GUI directly. Runtime files are created under:

```text
Documents\MBS Analytics\
```

If a packaged executable is present beside the launcher as `MBSAnalytics.exe`, the launcher uses it automatically. If not, it falls back to `python main.py`.

## Where Data Goes

Recommended overnight input folder:

```text
D:\MBS_Nightly_Input
```

Put the newest Bloomberg/payup workbook there. The recommended config uses:

```text
Latest file from folder
Pattern: *.xlsx
```

The app ignores temporary Excel lock files that start with `~$`.

## First Manual GUI Run

1. Run `run_desktop_gui.bat`.
2. Open `Automation`.
3. Use `Ideas Workspace` to load values from a fixed workbook or folder.
4. Save a config from `Overnight Runs / Saved Configurations`.
5. Run the idea scan.
6. Open the output folder and review `CLIENT_REPORT_BUY_SELL.xlsx` first.

## First Canned Payup Report Test

The beta seeds an example canned report named:

```text
Nightly Payup Curves
```

Open:

```text
Automation > Canned Reports
```

If no canned reports are listed, click `Load Example`.
If an older `Nightly Payup Curves` example already exists, click `Load Example` again and confirm the reload.
The example is built into the app/exe; it does not require a separate template file.
Reloading the example preserves the user's input/output folders and safety limits, but replaces the chart requests with the latest built-in sample.

The example includes four chart requests:

- LB125 2022 All Coupons
- FNCL LB225 1.5 Through 7.0 Snapshot - 2022 Vintage
- FNCL NY Coupon Curve - 2022 Vintage
- LTV Time Series

To test it:

1. Select `Nightly Payup Curves`.
2. Click `Show Report Setup` if the input file/folder or output folder needs to be changed.
3. Choose the client's payup workbook or set the latest-file input folder.
4. Click `Load Values` if dropdown values are not populated yet.
5. Click `Save Config`.
6. Click `Run Selected Now`.
7. Open the generated `CLIENT_REPORT_INDEX.xlsx`.

The generated report is saved under:

```text
Documents\MBS Analytics\output\canned_reports\<report_name>_<timestamp>\
```

`CLIENT_REPORT_INDEX.xlsx` is the client-facing file to open first. Chart links inside the workbook are clickable.
The workbook also includes an embedded `Charts` sheet, so it can still be reviewed if the Excel file is forwarded without the chart folder.

The chart request names are labels only. Filters are stored explicitly in the config, such as `loan_balance_buckets`, `origination_years`, `coupon_min`, `coupon_max`, `geographies`, and `story_tags`.
Snapshot coupon curves show 50bps coupon ticks on the X-axis when a coupon range is supplied.

Snapshot charts avoid mixing unrelated dimensions:

- Coupon curve: one vintage/year, coupons on the X-axis.
- Vintage curve: one coupon/story type, vintages/years on the X-axis.
- If a request matches multiple coupons and multiple vintages at the same time, the app skips that chart and reports a warning instead of averaging them together.

## First Nightly Test

After saving a config named `Nightly BUY SELL Ideas`, run:

```bat
run_nightly_config.bat "Nightly BUY SELL Ideas"
```

Expected behavior:

- No GUI opens.
- The newest matching input file is selected.
- A dated output package is created under `Documents\MBS Analytics\output\overnight_ideas`.
- The main client report is `CLIENT_REPORT_BUY_SELL.xlsx`, with clickable PNG links and embedded `Buy Charts` / `Sell Charts` sheets.
- Logs are written under `Documents\MBS Analytics\logs`.

## Windows Task Scheduler

Use this action:

```text
Program/script:
C:\Program Files\MBS Analytics\run_nightly_config.bat

Add arguments:
"Nightly BUY SELL Ideas"

Start in:
C:\Program Files\MBS Analytics
```

One scheduled task runs one saved config. If the client wants multiple configs overnight, create one task per config or duplicate the action with a different config name.

## Important Output Files

Open first:

```text
CLIENT_REPORT_BUY_SELL.xlsx
```

Then review:

```text
charts\buy\
charts\sell\
diagnostics\run_metadata.json
```

Technical CSVs are diagnostics. The Excel workbook is the client-facing report.

## Troubleshooting

If the GUI or nightly launcher fails, check:

```text
Documents\MBS Analytics\logs\
```

If Python source mode is used and Python is not on PATH, set:

```bat
set PYTHON_EXE=C:\Python313\python.exe
```

For packaged delivery, keep `MBSAnalytics.exe` in the same folder as both launchers.
