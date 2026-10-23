@echo off
setlocal
set "DIR=%~dp0"
set "SYS=python"
where py >nul 2>nul && set "SYS=py -3"
set "PY=%DIR%.venv\Scripts\python.exe"
if exist "%PY%" "%PY%" -c "import jinja2" >nul 2>nul && goto ready
%SYS% -c "import jinja2" >nul 2>nul && (for /f "delims=" %%i in ('%SYS% -c "import sys;print(sys.executable)"') do set "PY=%%i") && goto ready
echo Einmalig: Pakete in %DIR%.venv installieren (jinja2, requests, beautifulsoup4) ...
%SYS% -m venv "%DIR%.venv" || goto fail
"%PY%" -m pip install -q -r "%DIR%requirements.txt" || goto fail
:ready
if /I "%~1"=="feedback" ("%PY%" "%DIR%setup\feedback.py" & exit /b)
if /I "%~1"=="setup" (shift & "%PY%" "%DIR%setup\xlrte_setup.py" %* & exit /b)
if not exist "%DIR%config\settings.json" (
  echo Erste Nutzung: die Einrichtung oeffnet sich im Browser.
  "%PY%" "%DIR%setup\xlrte_setup.py"
  if "%~1"=="" exit /b
)
if "%~1"=="" (echo Cockpit: %DIR%01_cockpit.html & exit /b)
set "NAME=%~1"
shift
"%PY%" "%DIR%_system\%NAME%.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b
:fail
echo Installation fehlgeschlagen. Manuell: python -m pip install -r requirements.txt
exit /b 1
