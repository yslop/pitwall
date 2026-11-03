#!/bin/bash
# Pitwall installieren (macOS). Kopiert Pitwall mit eigener Python-Laufzeit in einen Ordner deiner Wahl und startet die Einrichtung.
# Es wird nichts systemweit installiert, nichts gesendet. Deinstallieren: den Ordner löschen.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ask() { osascript -e "text returned of (display dialog \"$1\" default answer \"$2\" buttons {\"OK\"} default button 1 with title \"Pitwall\")"; }
TARGET="${PITWALL_TARGET:-}"
[ -z "$TARGET" ] && TARGET="$(ask 'In welchen Ordner soll Pitwall? Dort liegen später deine Bewerbungsunterlagen. · Where should Pitwall live?' "$HOME/Documents/Pitwall")"
if [ -e "$TARGET/config/settings.json" ]; then
  echo "Pitwall ist dort schon eingerichtet: aktualisiere Programmdateien, deine Daten bleiben unverändert."
  rsync -a --exclude 'config/' --exclude '_system/pipeline.csv' --exclude '_system/preferences.json' --exclude '_system/profile.json' "$HERE/payload/" "$TARGET/"
else
  mkdir -p "$TARGET"
  cp -R "$HERE/payload/." "$TARGET/"
fi
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
chmod +x "$TARGET/pitwall" "$TARGET/star" "$TARGET/runtime/bin/"* 2>/dev/null || true
echo "Pitwall liegt in: $TARGET"
echo "Die Einrichtung öffnet sich im Browser. Dieses Fenster offen lassen, bis sie fertig ist."
cd "$TARGET" && ./pitwall
open "$TARGET" 2>/dev/null || true
