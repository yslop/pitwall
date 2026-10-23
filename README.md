# STAR · weniger Bewerbungen, bessere Gespräche

[English](README.en.md) · Teil von [ylsop](https://github.com/ylsop): *why slop?* Werkzeuge für alle, die lieber gründlich als viel machen.

**STAR ist ein lokales Bewerbungs-Cockpit mit KI-Unterstützung.** Es hilft dir, dich auf wenige, wirklich passende Stellen
zu konzentrieren und jedes Gespräch gründlich vorzubereiten: Pipeline, stufengesteuerte Recherche, Briefing und ein
Gesprächs-Cockpit mit Leitfaden, Bio für genau diese Rolle, Panikkarte und den besten Fragen an das Panel.

> Der Arbeitsmarkt wird schneller. Wer da mithalten will, braucht nicht mehr Bewerbungen, sondern einen klaren Blick
> darauf, welche sich lohnen, und eine Vorbereitung, die jedes Gespräch ernst nimmt. STAR ist dafür gebaut.

<!-- HERO: 30-Sekunden-GIF Stellenanzeige → Fit-Bewertung → Gesprächs-Cockpit (docs/hero.gif) -->

## Was STAR anders macht

- **Fokus statt Masse.** Ein Wochenbudget für neue Bewerbungen, eine Fit-Bewertung vor jedem Aufwand, eine Erinnerung,
  wenn du anfängst zu streuen. STAR ist ausdrücklich kein Werkzeug für Massenbewerbungen.
- **Belegt oder als Annahme markiert.** Jede Aussage im Briefing ist entweder mit Quelle belegt (FAKT) oder als Annahme
  gekennzeichnet (INFERENZ). Ein Prüfschritt (lint) hält das ein.
- **Deine Daten bleiben bei dir.** Alles liegt als Dateien in diesem Ordner. Kein Konto, kein Server, keine Telemetrie.
- **Zweisprachig.** Oberfläche Deutsch und Englisch, umschaltbar unten links.
- **Deine Zielmarke, dein Band.** Ziel („Vertrag unterschrieben“) mit Datum, Gehalts-Untergrenze und Zielgehalt legst du im Einrichtungs-Dialog fest; alles bleibt lokal.
- **Deine KI, deine Wahl.** Claude-Abo, ChatGPT-Abo, eigener API-Schlüssel, ein EU-Anbieter oder ein lokales Modell
  (Ollama): Du verbindest, was du hast. Ohne KI läuft alles Deterministische trotzdem.

## In fünf Minuten startklar

Voraussetzung: Python 3.9 oder neuer (macOS, Windows, Linux). Beim ersten Start legt `./star` im Ordner eine lokale
`.venv` an und installiert drei Pakete (Jinja2, requests, Beautiful Soup); danach läuft alles offline.

```bash
git clone https://github.com/ylsop/xlrte-star.git
cd xlrte-star
./star                     # Windows: star.cmd
```

Beim ersten Start öffnet sich der **Einrichtungs-Dialog** im Browser (nur lokal, 127.0.0.1): Name oder Pseudonym,
Zielrollen, Orte, Arbeitsmodell, Wochenbudget und deine KI-Anbindung mit Verbindungstest. Danach öffnest du
`01_cockpit.html`.

Lieber im Terminal? `python3 setup/xlrte_setup.py --cli`

### Mit Beispieldaten ausprobieren

Im Dialog ist „Mit Beispieldaten starten“ vorausgewählt: Die fiktive Person **Alex Muster** bringt 40 Verfahren in allen
Stufen und einige Gedankenprotokolle mit. Entfernen mit `python3 demo/load_demo.py --remove` und `./star kit_demo --remove`.
Beides archiviert nur, was die Demo angelegt hat.

## So arbeitest du damit

| Schritt | Was passiert | Befehl |
|---|---|---|
| Einrichten | Profil, Zielbild, KI-Anbindung | `./star setup` |
| Verlauf einspielen | bisherige Suche aus Excel, Notion oder Notizen | `./star kit_import verlauf.csv` (Vorschau), dann `--apply` |
| Recherche | die wichtigste offene Frage je Verfahren zuerst | `./star intel_queue --json` |
| Gespräch vorbereiten | Briefing → Cockpit mit Leitfaden, Bio, Fragen | `./star prep_engine --uid N --from-content` |
| Nach dem Gespräch | Gedankenprotokoll in `30 Verlauf` ablegen | Markdown oder Text |
| Überblick | Pipeline, Heute-Ansicht, Agentur-Bericht | `./star render` |

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

STAR lebt von Erfahrungen aus echten Bewerbungsprozessen. Besonders willkommen sind Verbesserungen an Leitfäden und
Fragen, neue Import-Formate, Übersetzungen und Tests. Lies [CONTRIBUTING.md](CONTRIBUTING.md); für den ersten Beitrag
gibt es Issues mit dem Label `good first issue`. Pilotphase: [docs/PILOT.md](docs/PILOT.md) · Fragen und Ideen: GitHub Discussions.

## Haftung

STAR unterstützt deine Vorbereitung. Es garantiert keine Einladung, keine Zusage und keine Richtigkeit von Recherchen.
Prüfe Fakten über Arbeitgeber und Personen selbst. Recherchiere nur öffentliche Quellen und halte die Nutzungsbedingungen
von Jobbörsen und Netzwerken ein; STAR enthält bewusst keine Scraper.

## Lizenz und Herkunft

Code: [MIT](LICENSE). STAR ist ein Projekt von **XLRTE** (Prasanna Easwarananthan), entstanden aus der eigenen
Jobsuche.
