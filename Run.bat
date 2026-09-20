@echo off
setlocal

rem Run the NFL analytics pipeline on Windows: create a virtual environment
rem if one doesn't exist yet, activate it, install dependencies, and run the
rem full historical pipeline (ingest -> merge -> features -> signal testing
rem -> model). See README.md's "Forward-looking predictions" section for
rem the separate current-season predictor -- it's not run automatically
rem here since it needs a season argument and its own fresh data pull.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment. Is Python installed and on PATH?
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed -- see the error above.
    pause
    exit /b 1
)

echo.
echo Running pipeline: ingest...
python -m src.ingest.pull_all
if errorlevel 1 goto :error

echo.
echo Running pipeline: merge...
python -m src.build_player_week
if errorlevel 1 goto :error

echo.
echo Running pipeline: feature engineering...
python -m src.features.build_features
if errorlevel 1 goto :error

echo.
echo Running pipeline: signal testing...
python -m src.signals.signal_testing
if errorlevel 1 goto :error

echo.
echo Running pipeline: model...
python -m src.signals.model
if errorlevel 1 goto :error

echo.
echo Done. Results are in data\processed\ and reports\report.md.
pause
exit /b 0

:error
echo.
echo Pipeline step failed -- see the error above.
pause
exit /b 1
