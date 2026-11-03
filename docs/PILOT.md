# Pilot: Pitwall in einer Woche

Danke, dass du mittestest. Die erste Pilotwoche lief nur auf Einladung; jetzt ist Pitwall offen, und Feedback ist
weiterhin das Wertvollste, was du beitragen kannst. Teile den Link gern.

Aufwand: **30 Minuten Einrichtung**, danach **10–15 Minuten pro Tag**, und dreimal ein kurzes Feedback.

## Was du bekommst

- Ein Cockpit für wenige, wichtige Bewerbungen: Pipeline, Zielmarke, Recherche-Reihenfolge, Gesprächs-Cockpit.
- Eine Struktur für Gedankenprotokolle nach jedem Gespräch.
- Den Wochenbudget-Gedanken: weniger, aber gründlicher.

## Einrichtung (Mac, Windows, Linux)

1. **Am einfachsten:** den Installer für dein System unter <https://github.com/yslop/pitwall/releases/latest> laden
   (`.dmg` für Mac, `-setup.exe` für Windows) und starten. Python brauchst du dafür nicht.
2. **Oder mit Python 3.9+:** grüner Knopf **Code → Download ZIP**, entpacken, oder `git clone https://github.com/yslop/pitwall.git`.
3. Im Ordner starten: Mac/Linux `./pitwall`, Windows Doppelklick auf `pitwall.cmd`.
4. Der Einrichtungs-Dialog öffnet sich im Browser. Oben rechts Deutsch oder English wählen, „Beispieldaten“ angehakt lassen.
5. KI anbinden, wenn du ein Claude-, ChatGPT- oder Gemini-Abo hast. Ohne KI geht es auch.

## Die Pilotwoche

| Tag | Was du tust | Feedback |
|---|---|---|
| 1 | Einrichten, mit Beispieldaten herumklicken | **Check-in 1:** `./pitwall feedback` |
| 2–3 | Beispieldaten entfernen (`python3 demo/load_demo.py --remove`), zwei bis drei eigene Verfahren anlegen | **Check-in 2** an Tag 3 |
| 4–6 | Täglich nutzen, Auffälliges sofort als Issue notieren | Fehler und Ideen jederzeit |
| 7 | Rückblick: Was soll vor der Veröffentlichung noch besser werden? | **Check-in 3 (Abschluss)** |

## So gibst du Feedback

`./pitwall feedback` (Windows: `pitwall.cmd feedback`) erstellt eine kurze Zusammenfassung mit Zahlen und Einstellungen:
Version, System, Sprache, Art der KI-Anbindung, wie viele Tage du es genutzt hast. **Keine Namen, Firmen, Notizen,
Fragen oder Schlüssel.** Sie wird in `feedback/` gespeichert und öffnet das Pilot-Formular auf GitHub, schon ausgefüllt.
Du liest sie, änderst sie, wenn du willst, und schickst dann ab. Es wird nichts automatisch übertragen.

- **Fehler:** *Issues → Fehler melden*. Bitte mit den Beispieldaten nachstellen, nie mit deinen echten Daten.
- **Ideen und Fragen:** *Discussions*.
- **Selbst verbessern:** Issues mit `good first issue`; ein Pull Request genügt, siehe [CONTRIBUTING.md](../CONTRIBUTING.md).

## Was mit deinem Feedback passiert

Feedback wird regelmäßig gesichtet und sortiert. Was die Einrichtung blockiert, wird zuerst behoben. Wer etwas
beigetragen hat, steht im CHANGELOG, wenn du das möchtest.

## Deine Daten

Alles bleibt auf deinem Rechner. Niemand sieht deine Daten, auch wir nicht. Schicke nie Screenshots mit echten Namen,
Firmen oder Notizen; die Beispieldaten reichen für jede Fehlermeldung.
