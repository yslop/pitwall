# Changelog

Alle wichtigen Änderungen an Pitwall. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach
[SemVer](https://semver.org/lang/de/).

## [0.2.0] – unveröffentlicht
### Neu
- **Entscheidungsmatrix** im Gesprächs-Cockpit: Ampel pro Kriterium, Empfehlung Go / Prüfen / Stopp, gemessen an deinem
  Maßstab (Ziel, Gehaltsband, Rahmen). Kriterien aus der Einrichtung oder pro Stelle von deiner KI geschärft
  (`Prep_Inhalt.json` → `entscheidung`). Gesicherte Matrizen erscheinen im Cockpit neben dem Verfahren.
- **Installer ohne Voraussetzungen** für macOS (Apple Silicon, Intel), Windows und Linux mit eigener Python-Laufzeit
  (geprüfte Prüfsumme); GitHub baut sie bei jedem Release (`installer/build.py`).
- Einrichtung: eigene Entscheidungskriterien und dein Rahmen in einem Satz.
- Ein Doppelklick auf `pitwall` öffnet nach der Einrichtung direkt das Cockpit.
- **Live-Demo** ohne Installation unter https://yslop.github.io/pitwall/ (erfundene Daten, `demo/build_site.py`, baut bei jedem Push neu).

### Geändert
- `./pitwall setup` aktualisiert Zielmarke, Termin und Gehaltsband zuverlässig, auch im `Zielbild.md`, und lädt keine
  Beispieldaten erneut.
- Diagramme laufen offline: Chart.js 4.4.1 (MIT) wird mitgeliefert statt aus dem Netz geladen.

## [0.1.0] – 2026-10-23
### Neu
- Erste öffentliche Ausgabe.
- Einrichtungs-Dialog nach der Installation mit KI-Anbindung (Abo, API-Schlüssel, EU-Anbieter, lokales Modell) und „Nur lokal“.
- Fiktive Demo-Daten zum Ausprobieren.
- Leak-Guard in der CI.
