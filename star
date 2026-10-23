#!/bin/sh
# STAR: ./star                  erste Nutzung: lokale .venv + Einrichtungs-Dialog
#       ./star setup            Einrichtung erneut öffnen
#       ./star <name> [Args]    startet _system/<name>.py, z. B. ./star render
DIR="$(cd "$(dirname "$0")" && pwd)"
SYS="$(command -v python3 || command -v python)"
[ -z "$SYS" ] && { echo "Python 3.9+ fehlt / missing: https://www.python.org/downloads/"; exit 1; }
PY="$DIR/.venv/bin/python"
if [ ! -x "$PY" ] || ! "$PY" -c "import jinja2" 2>/dev/null; then
  if "$SYS" -c "import jinja2" 2>/dev/null; then
    PY="$SYS"
  else
    echo "Einmalig: Pakete in $DIR/.venv installieren (jinja2, requests, beautifulsoup4) …"
    "$SYS" -m venv "$DIR/.venv" && "$DIR/.venv/bin/python" -m pip install -q -r "$DIR/requirements.txt" || {
      echo "Installation fehlgeschlagen. Manuell: $SYS -m pip install -r requirements.txt"; exit 1; }
  fi
fi
if [ "$1" = "setup" ]; then shift; exec "$PY" "$DIR/setup/xlrte_setup.py" "$@"; fi
if [ ! -f "$DIR/config/settings.json" ]; then
  echo "Erste Nutzung: die Einrichtung öffnet sich im Browser."
  "$PY" "$DIR/setup/xlrte_setup.py" || exit $?
  [ -z "$1" ] && exit 0
fi
if [ -z "$1" ]; then echo "Cockpit: $DIR/01_cockpit.html  ·  Befehle: ./star <name>, z. B. ./star render"; exit 0; fi
NAME="$1"; shift
exec "$PY" "$DIR/_system/$NAME.py" "$@"
