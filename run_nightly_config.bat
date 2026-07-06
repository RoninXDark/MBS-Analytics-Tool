@echo off
setlocal

if "%~1"=="" (
  echo Usage: run_nightly_config.bat "Config Name"
  echo Example: run_nightly_config.bat "Nightly BUY SELL Ideas"
  exit /b 1
)

set "CONFIG_NAME=%~1"
set "SCRIPT_DIR=%~dp0"
set "APP_HOME=%USERPROFILE%\Documents\MBS Analytics"
set "APP_HOME_OVERRIDE="
if defined MBS_ANALYTICS_HOME set "APP_HOME_OVERRIDE=%MBS_ANALYTICS_HOME:"=%"
if not "%APP_HOME_OVERRIDE%"=="" set "APP_HOME=%APP_HOME_OVERRIDE%"

call :prepare_runtime "%APP_HOME%"
if "%RUNTIME_OK%"=="" if not "%LOCALAPPDATA%"=="" call :prepare_runtime "%LOCALAPPDATA%\MBS Analytics"
if "%RUNTIME_OK%"=="" if not "%TEMP%"=="" call :prepare_runtime "%TEMP%\MBS Analytics"
if "%RUNTIME_OK%"=="" call :prepare_runtime "%SCRIPT_DIR%runtime"

if "%RUNTIME_OK%"=="" (
  echo Could not create a writable runtime folder for MBS Analytics.
  exit /b 1
)

set "MBS_ANALYTICS_HOME=%APP_HOME%"
set "CONFIG_STORE=%APP_HOME%\configs\automation_saved_configs.json"
set "LOG_DIR=%APP_HOME%\logs"

for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TS=%%I"
set "RUN_LOG=%LOG_DIR%\nightly_%RUN_TS%.log"

set "EXE_PATH=%SCRIPT_DIR%MBSAnalytics.exe"
set "EXE_OVERRIDE="
if defined MBS_ANALYTICS_EXE set "EXE_OVERRIDE=%MBS_ANALYTICS_EXE:"=%"
if not "%EXE_OVERRIDE%"=="" set "EXE_PATH=%EXE_OVERRIDE%"

set "PYTHON_CMD="
if defined PYTHON_EXE set "PYTHON_CMD=%PYTHON_EXE:"=%"
if "%PYTHON_CMD%"=="" set "PYTHON_CMD=python"

echo [%date% %time%] Starting nightly saved config "%CONFIG_NAME%" > "%RUN_LOG%"
echo Runtime folder: %APP_HOME% >> "%RUN_LOG%"
echo Config store: %CONFIG_STORE% >> "%RUN_LOG%"
echo. >> "%RUN_LOG%"

if exist "%EXE_PATH%" (
  echo Executable: %EXE_PATH% >> "%RUN_LOG%"
  "%EXE_PATH%" run-config --name "%CONFIG_NAME%" --store "%CONFIG_STORE%" --base-dir "%APP_HOME%" >> "%RUN_LOG%" 2>&1
) else (
  echo Python command: %PYTHON_CMD% >> "%RUN_LOG%"
  cd /d "%SCRIPT_DIR%"
  "%PYTHON_CMD%" main.py run-config --name "%CONFIG_NAME%" --store "%CONFIG_STORE%" --base-dir "%APP_HOME%" >> "%RUN_LOG%" 2>&1
)
set "EXIT_CODE=%ERRORLEVEL%"

echo. >> "%RUN_LOG%"
if not "%EXIT_CODE%"=="0" (
  echo [%date% %time%] FAILED with exit code %EXIT_CODE%. >> "%RUN_LOG%"
  echo Nightly run FAILED for "%CONFIG_NAME%".
  echo Log file: "%RUN_LOG%"
  type "%RUN_LOG%"
  exit /b %EXIT_CODE%
)

echo [%date% %time%] SUCCESS. >> "%RUN_LOG%"
echo Nightly run completed for "%CONFIG_NAME%".
echo Log file: "%RUN_LOG%"
type "%RUN_LOG%"

endlocal
exit /b 0

:prepare_runtime
set "APP_HOME=%~1"
set "RUNTIME_OK=1"
if not exist "%APP_HOME%\logs" mkdir "%APP_HOME%\logs" >nul 2>&1
if not exist "%APP_HOME%\configs" mkdir "%APP_HOME%\configs" >nul 2>&1
if not exist "%APP_HOME%\logs" set "RUNTIME_OK="
if not exist "%APP_HOME%\configs" set "RUNTIME_OK="
exit /b 0
