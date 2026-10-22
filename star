#!/bin/sh
# STAR: ./star                  erste Nutzung: Einrichtungs-Dialog
#       ./star setup            Einrichtung erneut öffnen
#       ./star <name> [Args]    startet _system/<name>.py, z. B. ./star intel_queue --json
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3 || command -v python)"
[ -z "$PY" ] && { echo "Python 3.9+ fehlt: https://www.python.org/downloads/"; exit 1; }
if [ "$1" = "setup" ]; then shift; exec "$PY" "$DIR/setup/xlrte_setup.py" "$@"; fi
if [ ! -f "$DIR/config/settings.json" ]; then
  echo "Erste Nutzung: die Einrichtung öffnet sich im Browser."
  "$PY" "$DIR/setup/xlrte_setup.py" || exit $?
  [ -z "$1" ] && exit 0
fi
if [ -z "$1" ]; then echo "Cockpit: $DIR/01_cockpit.html  ·  Befehle: ./star <name>, z. B. ./star render"; exit 0; fi
NAME="$1"; shift
exec "$PY" "$DIR/_system/$NAME.py" "$@"
