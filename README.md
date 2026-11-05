# Pitwall · weniger Bewerbungen, bessere Gespräche

[English](README.en.md) · Teil von [yslop](https://github.com/yslop): *why slop?* Werkzeuge für alle, die lieber gründlich als viel machen.

**[Live-Demo ansehen](https://yslop.github.io/pitwall/)**, ohne Installation, mit erfundenen Daten.

![Pitwall in 25 Sekunden: Cockpit, Stellenanalyse mit Fit-Score, Briefing, Gesprächs-Cockpit mit Panikkarte](docs/media/pitwall_de.gif)

**Pitwall ist ein lokales Bewerbungs-Cockpit mit KI-Unterstützung.** Es hilft dir, dich auf wenige, wirklich passende Stellen
zu konzentrieren und jedes Gespräch gründlich vorzubereiten: Pipeline, stufengesteuerte Recherche, Briefing und ein
Gesprächs-Cockpit mit Leitfaden, Bio für genau diese Rolle, Panikkarte und den besten Fragen an das Panel.

> Der Arbeitsmarkt wird schneller. Wer da mithalten will, braucht nicht mehr Bewerbungen, sondern einen klaren Blick
> darauf, welche sich lohnen, und eine Vorbereitung, die jedes Gespräch ernst nimmt. Pitwall ist dafür gebaut.

**Weniger Verwaltung, mehr Wirkung.** Statt zahlreiche Bewerbungsprozesse in Excel zu pflegen, konzentrierst du dich auf
das, was entscheidet: deine Leistung im Gespräch und den nächsten guten Schritt in deinem Berufsleben, auch nach einer
Kündigung oder in einer Umbruchphase. Pitwall hält Pipeline, Fristen und Recherche für dich zusammen.

## Was Pitwall anders macht

- **Fokus statt Masse.** Ein Wochenbudget für neue Bewerbungen, eine Fit-Bewertung vor jedem Aufwand, eine Erinnerung,
  wenn du anfängst zu streuen. Pitwall ist ausdrücklich kein Werkzeug für Massenbewerbungen.
- **Belegt oder als Annahme markiert.** Jede Aussage im Briefing ist entweder mit Quelle belegt (FAKT) oder als Annahme
  gekennzeichnet (INFERENZ). Ein Prüfschritt (lint) hält das ein.
- **Deine Daten bleiben bei dir.** Alles liegt als Dateien in diesem Ordner. Kein Konto, kein Server, keine Telemetrie.
- **Zweisprachig.** Oberfläche Deutsch und Englisch, umschaltbar unten links.
- **Entscheiden mit Maßstab.** Nach jedem Gespräch eine Ampel-Matrix im Gesprächs-Cockpit: Budget, Rollen-Zuschnitt,
  Chemie, Gehalt, Arbeitsmodell (oder deine eigenen Kriterien). Ein Rot ist ein Stopp-Signal; die Empfehlung Go / Prüfen /
  Stopp steht danach im Cockpit neben dem Verfahren.
- **Deine Zielmarke, dein Band.** Ziel („Vertrag unterschrieben“) mit Datum, Gehalts-Untergrenze und Zielgehalt legst du im Einrichtungs-Dialog fest; alles bleibt lokal.
- **Deine KI, deine Wahl.** Claude-Abo, ChatGPT-Abo, eigener API-Schlüssel, ein EU-Anbieter oder ein lokales Modell
  (Ollama): Du verbindest, was du hast. Ohne KI läuft alles Deterministische trotzdem.

## In fünf Minuten startklar

**Am einfachsten: Installer laden.** Unter [Releases](https://github.com/yslop/pitwall/releases/latest) liegen
`Pitwall-…-mac-arm64.dmg` (Apple Silicon), `…-mac-intel.dmg`, `…-windows-setup.exe` und `…-linux-x64.tar.gz`. Sie bringen
ihre eigene Python-Laufzeit mit; du brauchst nichts vorher zu installieren. Die Installer sind (noch) nicht signiert:
macOS fragt beim ersten Öffnen nach (Rechtsklick → Öffnen), Windows zeigt „Der Computer wurde durch Windows geschützt“
(→ Weitere Informationen → Trotzdem ausführen).

**Oder mit Git und Python 3.9+.** Beim ersten Start legt `./pitwall` im Ordner eine lokale `.venv` an und installiert drei
Pakete (Jinja2, requests, Beautiful Soup); danach läuft alles offline.

```bash
git clone https://github.com/yslop/pitwall.git
cd pitwall
./pitwall                     # Windows: pitwall.cmd
```

Beim ersten Start öffnet sich der **Einrichtungs-Dialog** im Browser (nur lokal, 127.0.0.1): Name oder Pseudonym,
Zielrollen, Orte, Arbeitsmodell, Wochenbudget und deine KI-Anbindung mit Verbindungstest. Danach öffnest du
`01_cockpit.html`.

Lieber im Terminal? `python3 setup/xlrte_setup.py --cli`

### Mit Beispieldaten ausprobieren

Im Dialog ist „Mit Beispieldaten starten“ vorausgewählt: Die fiktive Person **Alex Muster** bringt 40 Verfahren in allen
Stufen und einige Gedächtnisprotokolle mit. Entfernen mit `python3 demo/load_demo.py --remove` und `./pitwall kit_demo --remove`.
Beides archiviert nur, was die Demo angelegt hat.

## So arbeitest du damit

| Schritt | Was passiert | Befehl |
|---|---|---|
| Einrichten | Profil, Zielbild, KI-Anbindung | `./pitwall setup` |
| Verlauf einspielen | bisherige Suche aus Excel, Notion oder Notizen | `./pitwall kit_import verlauf.csv` (Vorschau), dann `--apply` |
| Recherche | die wichtigste offene Frage je Verfahren zuerst | `./pitwall intel_queue --json` |
| Gespräch vorbereiten | Briefing → Cockpit mit Leitfaden, Bio, Fragen | `./pitwall prep_engine --uid N --from-content` |
| Nach dem Gespräch | Gedächtnisprotokoll in `30 Verlauf` ablegen | Markdown oder Text |
| Entscheiden | Ampel-Matrix im Gesprächs-Cockpit, „Matrix sichern“ in `30 Verlauf` | Klick im Cockpit, dann `./pitwall render` |
| Ziele ändern | Zielmarke, Termin, Gehaltsband, Kriterien | `./pitwall setup` (deine Daten bleiben) |
| Überblick | Pipeline, Heute-Ansicht, Agentur-Bericht | `./pitwall render` |

Die eigentliche Arbeit machst du gemeinsam mit deiner KI in diesem Ordner: Starte sie hier (z. B. `claude`) und lass
sie `ONBOARDING.md` mit dir durchgehen. `AGENTS.md` sagt jeder KI, welche Regeln gelten.

## Datenschutz: Governance by Design

- Alles Persönliche ist per `.gitignore` vom Repository ausgeschlossen. Wer forkt, veröffentlicht nur Code.
- Schlüssel liegen nur in `.env` (Dateirechte 600), nie in Einstellungen oder Logs.
- „Nur lokal“ im Dialog sperrt jeden entfernten KI-Anbieter, auch im Code (`setup/ai.py`).
- Protokolliert wird nur, *dass* eine KI-Anfrage lief, nie ihr Inhalt (`logs/ai_calls.jsonl`).
- Jeder Pull Request durchläuft einen Leak-Guard (`tools/leak_guard.py`), der persönliche Daten und Schlüssel abweist.

Details: [PRIVACY.md](PRIVACY.md).

## Mitmachen

Pitwall lebt von Erfahrungen aus echten Bewerbungsprozessen. Besonders willkommen sind Verbesserungen an Leitfäden und
Fragen, neue Import-Formate, Übersetzungen und Tests. Lies [CONTRIBUTING.md](CONTRIBUTING.md); für den ersten Beitrag
gibt es Issues mit dem Label `good first issue`. Pilotphase: [docs/PILOT.md](docs/PILOT.md) · Fragen und Ideen: GitHub Discussions.

## Haftung

Pitwall unterstützt deine Vorbereitung. Es garantiert keine Einladung, keine Zusage und keine Richtigkeit von Recherchen.
Prüfe Fakten über Arbeitgeber und Personen selbst. Recherchiere nur öffentliche Quellen und halte die Nutzungsbedingungen
von Jobbörsen und Netzwerken ein; Pitwall enthält bewusst keine Scraper.

## Lizenz und Herkunft

Code: [MIT](LICENSE). Pitwall ist ein Projekt von **XLRTE** (Prasanna Easwarananthan), entstanden aus der eigenen
Jobsuche.
