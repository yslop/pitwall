# Pilot: STAR in einer Woche

Danke, dass du dabei bist. STAR ist in dieser Woche **nur auf Einladung** sichtbar. Danach wird es mit euren
Verbesserungen für alle veröffentlicht. Bitte teile den Link bis dahin nicht weiter.

Aufwand: **30 Minuten Einrichtung**, danach **10–15 Minuten pro Tag**, und dreimal ein kurzes Feedback.

## Was du bekommst

- Ein Cockpit für wenige, wichtige Bewerbungen: Pipeline, Zielmarke, Recherche-Reihenfolge, Gesprächs-Cockpit.
- Eine Struktur für Gedankenprotokolle nach jedem Gespräch.
- Den Wochenbudget-Gedanken: weniger, aber gründlicher.

## Einrichtung (Mac, Windows, Linux)

1. Python 3.9 oder neuer installieren: <https://www.python.org/downloads/> (Mac: oft schon da, `python3 --version`).
2. Die Einladung von GitHub annehmen (E-Mail oder <https://github.com/notifications>).
3. Repository holen: grüner Knopf **Code → Download ZIP**, entpacken. Oder mit Git:
   `git clone https://github.com/yslop/xlrte-star.git`
4. Im Ordner starten: Mac/Linux `./star`, Windows Doppelklick auf `star.cmd`.
5. Der Einrichtungs-Dialog öffnet sich im Browser. Oben rechts Deutsch oder English wählen, „Beispieldaten“ angehakt lassen.
6. KI anbinden, wenn du ein Claude-, ChatGPT- oder Gemini-Abo hast. Ohne KI geht es auch.

## Die Pilotwoche

| Tag | Was du tust | Feedback |
|---|---|---|
| 1 | Einrichten, mit Beispieldaten herumklicken | **Check-in 1:** `./star feedback` |
| 2–3 | Beispieldaten entfernen (`python3 demo/load_demo.py --remove`), zwei bis drei eigene Verfahren anlegen | **Check-in 2** an Tag 3 |
| 4–6 | Täglich nutzen, Auffälliges sofort als Issue notieren | Fehler und Ideen jederzeit |
| 7 | Rückblick: Was soll vor der Veröffentlichung noch besser werden? | **Check-in 3 (Abschluss)** |

## So gibst du Feedback

`./star feedback` (Windows: `star.cmd feedback`) erstellt eine kurze Zusammenfassung mit Zahlen und Einstellungen:
Version, System, Sprache, Art der KI-Anbindung, wie viele Tage du es genutzt hast. **Keine Namen, Firmen, Notizen,
Fragen oder Schlüssel.** Sie wird in `feedback/` gespeichert und öffnet das Pilot-Formular auf GitHub, schon ausgefüllt.
Du liest sie, änderst sie, wenn du willst, und schickst dann ab. Es wird nichts automatisch übertragen.

- **Fehler:** *Issues → Fehler melden*. Bitte mit den Beispieldaten nachstellen, nie mit deinen echten Daten.
- **Ideen und Fragen:** *Discussions*.
- **Selbst verbessern:** Issues mit `good first issue`; ein Pull Request genügt, siehe [CONTRIBUTING.md](../CONTRIBUTING.md).

## Was mit deinem Feedback passiert

Jeden Abend der Pilotwoche wird das Feedback gesichtet und sortiert. Was die Einrichtung blockiert, wird sofort behoben.
Nach Tag 7 folgt eine Auswertung im Pilot-Issue mit allen Antworten (anonym zusammengefasst), dann Version 0.2.0 und die
Veröffentlichung. Wer etwas beigetragen hat, steht im CHANGELOG, wenn du das möchtest.

## Deine Daten

Alles bleibt auf deinem Rechner. Niemand sieht deine Daten, auch wir nicht. Schicke nie Screenshots mit echten Namen,
Firmen oder Notizen; die Beispieldaten reichen für jede Fehlermeldung.
