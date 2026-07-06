# Client Handoff Guide

## What This Product Delivers
- Desktop GUI for daily analyst workflows (`run_desktop_gui.bat`, packaged `MBSAnalytics.exe`, or `MBSAnalytics.exe desktop-gui`)
- Automation tab for canned runs with saved presets
- Optional outputs for speed control:
- Excel stats
- Individual charts
- Versus charts
- Progress bar and live status for long runs
- Diagnostics + support tooling:
- `python main.py doctor`
- `python main.py bundle-output --source "%USERPROFILE%\Documents\MBS Analytics\output"`
- Scheduler-friendly preset automation:
- `python main.py list-configs`
- `python main.py run-config --name "Texas Mid-Coupons"`
- `run_nightly_config.bat "Nightly BUY SELL Ideas"`
- Client-readable summary workbook:
- `Documents\MBS Analytics\output\overnight_ideas\<package>\CLIENT_REPORT_BUY_SELL.xlsx` with `Run Summary`, `Buy Ideas`, `Sell Ideas`, and `Technical Metadata`
- Example canned payup report:
- `Nightly Payup Curves` is auto-seeded on first GUI launch when no `payup_curve_pack` config exists.
- Canned report packages write `CLIENT_REPORT_INDEX.xlsx`, charts, and diagnostics under `Documents\MBS Analytics\output\canned_reports`.
- BUY/SELL and canned report workbooks keep external PNG links for full output folders, and also embed chart sheets for one-file Excel sharing.

## Recommended Delivery Package
1. `run_desktop_gui.bat`
2. `run_nightly_config.bat`
3. Source app folder `bond_story_reporting/`
4. `main.py`, `requirements.txt`, and `README.md`
5. `docs/`, especially `BETA_QUICK_START.md` and `NIGHTLY_AUTOMATION_SETUP.md`
6. `examples/automation_saved_configs.example.json`
7. `sample_data/` example file

Use the package builder to avoid shipping old logs, old outputs, caches, and developer scratch files:

```bat
python scripts\build_beta_zip.py
```

The generated ZIP includes a `BETA_MANIFEST.txt` so the shipped contents are auditable.

Do not manually include:

- `output/`
- `logs/`
- `runtime/`
- `__pycache__/`
- `_audit_output/`
- `_tmp_phase5_scan/`
- local client/test workbooks

## Operator Runbook
1. Install dependencies:
   - `pip install -r requirements.txt`
2. Launch desktop app:
   - `run_desktop_gui.bat`
3. Load preset in the `Automation` tab
4. Click `RUN AUTOMATION`
5. Open output folder and review:
   - `tables/`
   - `charts/`
   - `report_metadata.json`
6. Deliver package to client:
   - `python main.py bundle-output --source "%USERPROFILE%\Documents\MBS Analytics\output"`

## First Canned Reports Test
1. Launch `run_desktop_gui.bat` or double-click `MBSAnalytics.exe`.
2. Open `Automation > Canned Reports`.
3. If the list is empty, click `Load Example`. If an older example is already present, click `Load Example` again and confirm the reload.
4. Select `Nightly Payup Curves`.
5. Click `Show Report Setup` if the input file/folder or output folder needs to be changed.
6. Choose a fixed payup workbook, or use latest-file mode and select an input folder.
7. Click `Load Values` to populate dropdowns from the workbook.
8. Review the chart requests. Use `Add`, `Edit`, `Duplicate`, and `Delete` only if changes are needed.
9. Click `Save Config`.
10. Click `Run Selected Now`.
11. Open `CLIENT_REPORT_INDEX.xlsx` from the generated canned report output folder.

The example canned report is built into the app/exe. No external template file is required. Clicking `Load Example` writes the sample `Nightly Payup Curves` config into:

```text
Documents\MBS Analytics\configs\automation_saved_configs.json
```

If `Nightly Payup Curves` already exists, `Load Example` can refresh the chart requests with the latest built-in sample
while preserving the user's machine-specific input/output paths and safety limits.

The generated canned report package is written under:

```text
Documents\MBS Analytics\output\canned_reports\<report_name>_<timestamp>\
```

Snapshot chart behavior:

- Coupon curves use one vintage/year and label coupons on the X-axis.
- Vintage curves use one coupon/story type and label vintages/years on the X-axis.
- Ambiguous requests that match multiple coupons and multiple vintages are skipped with a warning instead of silently averaging unrelated stories.

## Scheduling (No GUI Needed)
1. Save one or more presets in the `Automation` tab (`Save Config` button)
2. For nightly production, use the latest-file input workflow:
   - Put the newest Bloomberg export in `D:\MBS_Nightly_Input`
   - In `Nightly Input Source`, choose `Latest file from folder`
   - Set input folder to `D:\MBS_Nightly_Input`
   - Set file pattern to `*.xlsx`
2. Verify preset names:
   - `python main.py list-configs`
3. Manually test the scheduler launcher:
   - `run_nightly_config.bat "Nightly BUY SELL Ideas"`
4. Schedule command in Windows Task Scheduler:
   - Program/script: `C:\Program Files\MBS Analytics\run_nightly_config.bat`
   - Add arguments: `"Nightly BUY SELL Ideas"`
   - Start in: `C:\Program Files\MBS Analytics`
5. Review success/failure logs:
   - `Documents\MBS Analytics\logs\nightly_YYYYMMDD_HHMMSS.log`
   - `Documents\MBS Analytics\logs\bond_story_reporting.log`
   - `Documents\MBS Analytics\output\overnight_ideas\<package>\diagnostics\run_metadata.json`
6. Open next-morning client output:
   - `Documents\MBS Analytics\output\overnight_ideas\<package>\CLIENT_REPORT_BUY_SELL.xlsx`
   - `Documents\MBS Analytics\output\overnight_ideas\<package>\charts\buy`
   - `Documents\MBS Analytics\output\overnight_ideas\<package>\charts\sell`

In the desktop GUI, use `Automation > Ideas Workspace` or `Automation > BUY/SELL Runs / Saved Configs` for BUY/SELL idea scans.
Use `Automation > Canned Reports` for canned payup curve packs. This keeps the two workflow types separate for operators.

See `docs/NIGHTLY_AUTOMATION_SETUP.md` for the full setup guide.

## Future EXE Packaging

The launchers are already exe-aware:

- If `MBSAnalytics.exe` is beside the launcher, the launcher uses it.
- If no exe exists, the launcher falls back to `python main.py`.
- Double-clicking `MBSAnalytics.exe` with no command opens the desktop GUI.
- Command-line usage still works for automation, for example `MBSAnalytics.exe run-config --name "Nightly Payup Curves"`.

Build notes are in `docs/BETA_RELEASE_CHECKLIST.md`.

## Support / Troubleshooting
1. If app fails to start, run:
   - `python main.py doctor`
2. Check logs:
   - `Documents\MBS Analytics\logs\bond_story_reporting.log`
3. If UI theme causes issues, set fallback:
   - `set MBS_THEME=cosmo` (Windows)

## Commercial Notes (Positioning for $1,400-$1,800)
- Ready-to-use desktop workflow (no browser ops burden)
- Canned-report presets for repeatability
- Controlled output generation for speed
- Diagnostics + logging for supportability
- Clear handoff materials and operator runbook
