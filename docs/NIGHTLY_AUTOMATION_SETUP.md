# Nightly Automation Setup

This project can run overnight idea scans without opening the desktop GUI.
The Windows scheduler path is:

1. Save a config from the desktop GUI Automation tab, or edit `Documents\MBS Analytics\configs\automation_saved_configs.json` if needed.
2. Drop the newest Bloomberg export into one input folder.
3. Run `run_nightly_config.bat "Config Name"` from Windows Task Scheduler.
4. Review the dated output package the next morning.

Runtime files live outside the install/source folder:

```text
Documents\MBS Analytics\configs\automation_saved_configs.json
Documents\MBS Analytics\logs\
Documents\MBS Analytics\output\overnight_ideas\
```

## Chosen Input Workflow

Use the latest file from a fixed input folder.

Recommended client folder:

```text
D:\MBS_Nightly_Input
```

Each night, place the newest Bloomberg export in that folder. The saved config
uses `input_mode: "latest_file"` and the app selects the most recently modified
matching file at runtime. Excel lock files such as `~$file.xlsx` are ignored.

Supported file extensions:

```text
.xlsx, .xls, .xlsm, .csv
```

Recommended pattern:

```text
*.xlsx
```

Use a comma-separated pattern only if needed, for example:

```text
*.xlsx,*.csv
```

## Saving The Config In The GUI

1. Open the desktop GUI:

```bat
run_desktop_gui.bat
```

2. Go to `Automation`.
3. Open `Overnight Runs / Saved Configurations`.
4. In `Nightly Input Source`, choose one:
   - `Fixed file path` for one exact CSV/XLSX file.
   - `Latest file from folder` for overnight production.
5. For production, choose:
   - Input folder: `D:\MBS_Nightly_Input`
   - File pattern: `*.xlsx`
6. Set ranking, filters, output folder, and package name as desired.
7. Click `Save Config`.
8. Test with `run_nightly_config.bat "Config Name"`.

## Saved Config Example

Add a config like this to `Documents\MBS Analytics\configs\automation_saved_configs.json`:

```json
{
  "configs": {
    "Nightly BUY SELL Ideas": {
      "workflow": "idea_scan",
      "input_mode": "latest_file",
      "input_dir": "D:\\MBS_Nightly_Input",
      "input_pattern": "*.xlsx",
      "output_dir": "C:\\Users\\ClientUser\\Documents\\MBS Analytics\\output\\overnight_ideas",
      "ranking_method": "z_score",
      "top_n": 10,
      "use_default_focus": true,
      "include_full_chart_history": true,
      "min_observations": 50,
      "filters": {
        "programs": [],
        "geographies": [],
        "loan_balance_buckets": [],
        "coupons": [],
        "origination_years": [],
        "origination_year_min": 2019,
        "origination_year_max": null,
        "story_families": [],
        "story_tags": [],
        "raw_story_names": []
      },
      "include_parse_failures": true
    }
  }
}
```

The saved config can also use a fixed file path instead:

```json
"input_path": "D:\\MBS_Nightly_Input\\BBG PUs Latest.xlsx"
```

But the recommended overnight workflow is `latest_file`, because the scheduled
task does not need to be edited when the filename changes.

## Manual Test

From the project folder:

```bat
run_nightly_config.bat "Nightly BUY SELL Ideas"
```

Expected behavior:

- No GUI window opens.
- The newest matching input file is selected.
- The run writes a package under `Documents\MBS Analytics\output\overnight_ideas\`.
- Open `CLIENT_REPORT_BUY_SELL.xlsx` first for the client-readable report sheets:
  `Run Summary`, `Buy Ideas`, `Sell Ideas`, and `Technical Metadata`.
- The launcher writes a transcript to `Documents\MBS Analytics\logs\nightly_YYYYMMDD_HHMMSS.log`.
- The app writes operational logs to `Documents\MBS Analytics\logs\bond_story_reporting.log`.
- The package writes run metadata to `diagnostics\run_metadata.json`.

## Windows Task Scheduler

Create a basic task:

1. Open `Task Scheduler`.
2. Choose `Create Task`, not `Create Basic Task`, for better control.
3. Name it `MBS Nightly Idea Scan`.
4. On `Triggers`, create a daily trigger, for example `2:00 AM`.
5. On `Actions`, choose `Start a program`.
6. Use these exact fields:

```text
Program/script:
C:\Program Files\MBS Analytics\run_nightly_config.bat

Add arguments:
"Nightly BUY SELL Ideas"

Start in:
C:\Program Files\MBS Analytics
```

If using the source/developer version and Python is not on `PATH`, set the full Python path before running the task:

```bat
set PYTHON_EXE=C:\Python313\python.exe
run_nightly_config.bat "Nightly BUY SELL Ideas"
```

For packaged delivery, place `MBSAnalytics.exe` beside `run_nightly_config.bat`.
The launcher automatically uses the executable. If no executable is present, it
falls back to `python main.py run-config`.

## Success And Failure Review

For each scheduled run, check:

```text
Documents\MBS Analytics\logs\nightly_YYYYMMDD_HHMMSS.log
Documents\MBS Analytics\logs\bond_story_reporting.log
Documents\MBS Analytics\output\overnight_ideas\<package>\diagnostics\run_metadata.json
```

Successful runs return exit code `0`. Failed runs return a non-zero exit code,
which Task Scheduler records in the task history.

## Operational Notes

- Keep only intended data files in the input folder.
- If multiple files match the pattern, the newest modified file wins.
- Do not leave a half-downloaded file in the folder at the scheduled time.
- The task should run under a Windows user that has access to the input folder,
  output folder, install folder, and Python environment when not using the packaged executable.
