# Beta Release Checklist

Use this checklist before creating the client ZIP or building the first beta executable.

## Required Client Files

The beta ZIP should include:

- `run_desktop_gui.bat`
- `run_nightly_config.bat`
- `main.py`
- `bond_story_reporting/`
- `requirements.txt`
- `README.md`
- `docs/`
- `examples/automation_saved_configs.example.json`
- `sample_data/`

The beta ZIP should not include:

- `output/`
- `logs/`
- `runtime/`
- `__pycache__/`
- `_audit_output/`
- `_tmp_phase5_scan/`
- old or redundant `.bat` launchers
- local client/test workbooks
- ad-hoc developer notes

## Build A Clean Beta ZIP

From the project folder:

```bat
python scripts\build_beta_zip.py
```

Dry run:

```bat
python scripts\build_beta_zip.py --dry-run
```

The ZIP is written to:

```text
dist_beta\
```

The package builder uses a whitelist and excludes old outputs, logs, caches, and temporary files.

## Preflight Checks

Run:

```bat
python -m compileall main.py bond_story_reporting
python main.py version
python main.py doctor
```

Then test:

```bat
run_desktop_gui.bat
```

After saving a valid config, test:

```bat
run_nightly_config.bat "Nightly BUY SELL Ideas"
```

## First Beta EXE Build

Install packaging tools:

```bat
pip install -r requirements-packaging.txt
```

Build:

```bat
pyinstaller --clean --noconfirm packaging\MBSAnalytics.spec
```

Expected result:

```text
dist\MBSAnalytics\MBSAnalytics.exe
```

Copy these two files beside the executable:

```text
run_desktop_gui.bat
run_nightly_config.bat
```

The launchers automatically use `MBSAnalytics.exe` when it exists beside them.

## Runtime Folder Model

Do not put configs, logs, or generated outputs inside the install folder for production.

Default runtime location:

```text
Documents\MBS Analytics\
```

Inside it:

```text
configs\automation_saved_configs.json
logs\
output\overnight_ideas\
diagnostics\
```

This keeps the installed app folder clean and makes the same structure work for source mode and packaged `.exe` mode.

## Final Smoke Test

Before delivery:

1. Put a real workbook in `D:\MBS_Nightly_Input`.
2. Save or install a config using `latest_file` mode.
3. Run `run_nightly_config.bat "Nightly BUY SELL Ideas"`.
4. Confirm `CLIENT_REPORT_BUY_SELL.xlsx` exists.
5. Confirm `charts\buy` and `charts\sell` contain PNG charts.
6. Confirm `diagnostics\run_metadata.json` says completed.
