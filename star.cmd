@echo off
setlocal
set "DIR=%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
if /I "%~1"=="setup" (shift & %PY% "%DIR%setup\xlrte_setup.py" %* & exit /b)
if not exist "%DIR%config\settings.json" (
  echo Erste Nutzung: die Einrichtung oeffnet sich im Browser.
  %PY% "%DIR%setup\xlrte_setup.py"
  if "%~1"=="" exit /b
)
if "%~1"=="" (echo Cockpit: %DIR%01_cockpit.html & exit /b)
set "NAME=%~1"
shift
%PY% "%DIR%_system\%NAME%.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
