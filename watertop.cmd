@echo off
REM Local checkout launcher — works from this repo without pip Scripts on PATH.
cd /d "%~dp0"
python -m desktop.watertop %*
if %ERRORLEVEL% neq 0 (
  echo.
  echo If that failed:  pip install -e .
  echo Then open a new terminal and type:  watertop
  exit /b 1
)
