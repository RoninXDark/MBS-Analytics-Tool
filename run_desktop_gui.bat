@echo off
setlocal

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
  pause
  exit /b 1
)

set "MBS_ANALYTICS_HOME=%APP_HOME%"
set "LOG_DIR=%APP_HOME%\logs"

for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TS=%%I"
set "RUN_LOG=%LOG_DIR%\desktop_gui_%RUN_TS%.log"

set "EXE_PATH=%SCRIPT_DIR%MBSAnalytics.exe"
set "EXE_OVERRIDE="
if defined MBS_ANALYTICS_EXE set "EXE_OVERRIDE=%MBS_ANALYTICS_EXE:"=%"
if not "%EXE_OVERRIDE%"=="" set "EXE_PATH=%EXE_OVERRIDE%"

set "PYTHON_CMD="
if defined PYTHON_EXE set "PYTHON_CMD=%PYTHON_EXE:"=%"
if "%PYTHON_CMD%"=="" set "PYTHON_CMD=python"
set "PYTHON_ARGS="

echo [%date% %time%] Starting desktop GUI > "%RUN_LOG%"
echo Runtime folder: %APP_HOME% >> "%RUN_LOG%"
echo Script folder: %SCRIPT_DIR% >> "%RUN_LOG%"
echo. >> "%RUN_LOG%"

if exist "%EXE_PATH%" (
  echo Executable: %EXE_PATH% >> "%RUN_LOG%"
  "%EXE_PATH%" desktop-gui >> "%RUN_LOG%" 2>&1
) else (
  cd /d "%SCRIPT_DIR%"
  if /I "%PYTHON_CMD%"=="python" (
    where python >> "%RUN_LOG%" 2>&1
    if errorlevel 1 (
      where py >> "%RUN_LOG%" 2>&1
      if not errorlevel 1 (
        set "PYTHON_CMD=py"
        set "PYTHON_ARGS=-3"
      )
    )
  )
  echo Python command: %PYTHON_CMD% %PYTHON_ARGS% >> "%RUN_LOG%"
  "%PYTHON_CMD%" %PYTHON_ARGS% main.py desktop-gui >> "%RUN_LOG%" 2>&1
)
set "EXIT_CODE=%ERRORLEVEL%"

echo. >> "%RUN_LOG%"
echo [%date% %time%] Desktop GUI process exited with code %EXIT_CODE%. >> "%RUN_LOG%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Desktop GUI failed to launch.
  echo Launcher log: "%RUN_LOG%"
  echo App log: "%LOG_DIR%\bond_story_reporting.log"
  echo.
  type "%RUN_LOG%"
  pause
  exit /b %EXIT_CODE%
)

echo Desktop GUI process ended.
echo If the app closed immediately, check this launcher log:
echo "%RUN_LOG%"
echo.
type "%RUN_LOG%"
pause

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
