# Sales-Ready Checklist

## Product
- [x] Unified desktop GUI
- [x] Saved automation presets
- [x] CLI preset execution (`run-config`) for scheduled automation
- [x] Windows nightly launcher (`run_nightly_config.bat`) with timestamped logs
- [x] Clean final launcher model: GUI launcher + nightly scheduler launcher
- [x] Latest-file input folder workflow for overnight Bloomberg exports
- [x] GUI controls for fixed-file vs latest-file input mode
- [x] Client-readable `CLIENT_REPORT_BUY_SELL.xlsx` output
- [x] Ranking criteria control (`Z-Score`, `Current Pay-up`, `Mean`)
- [x] Output toggles (stats / charts / versus)
- [x] Progress bar for long-running jobs
- [x] Date range filtering for time-slice runs

## Reliability
- [x] Structured logs in `Documents\MBS Analytics\logs\`
- [x] Environment diagnostics command (`doctor`)
- [x] Artifact bundling command (`bundle-output`)
- [x] Automated tests for analytics/report pipeline

## Delivery
- [x] README with run instructions
- [x] Client handoff runbook
- [x] Example data and output structure

## Pre-Demo Script
1. `python main.py doctor`
2. `run_desktop_gui.bat`
3. Load preset, run automation
4. Show progress bar + metadata
5. `python main.py list-configs`
6. `run_nightly_config.bat "Nightly BUY SELL Ideas"`
7. `python main.py bundle-output --source "%USERPROFILE%\Documents\MBS Analytics\output"`
