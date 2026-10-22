# Datenmodell — Job Search 2026

Eine Datei ist die Wahrheit über den Zustand: **`_system/pipeline.csv`**.
Sie wird bei jedem Lauf aus **Drive-Ordnerstruktur + Gmail** neu abgeglichen.
Alle vier Browser-Ansichten und der Google-Sheet-Export werden daraus erzeugt —
nirgendwo sonst werden Daten gepflegt.

```
Drive-Ordner + Gmail   →   pipeline.csv   →   render.py   →   4 Ansichten + sheet_export.csv
   (Quelle der Wahrheit)     (Zustand)         (Darstellung)
```

## Stufen (ersetzt Ideation / CAM / Implementation / Testing & Go-Live / Support)

| Stufe | Bedeutung | Übergang hierher |
|---|---|---|
| `Watchlist` | verifiziert, aber noch nicht beworben | Rolle im Radar bestätigt |
| `Applied` | Bewerbung raus, noch kein Mensch geantwortet | Eingangsbestätigung / ATS-Ack |
| `Screening` | erster menschlicher Kontakt, HR oder Recruiter | Rückfrage, Terminvorschlag, Telefonat |
| `Interviewing` | Fach- oder Panelrunden mit Datum | Termin bestätigt |
| `Final` | Endrunde, C-Level, Vertragsgespräch | Einladung Endrunde / Vertragsthema |
| `Closed` | beendet, gleich aus welchem Grund | siehe `outcome` |

`outcome` wird nur bei `Closed` gesetzt:
`rejected` · `withdrawn` (selbst zurückgezogen) · `declined` (Angebot abgelehnt) ·
`signed` (Vertrag) · `lapsed` (60+ Tage ohne Reaktion, bewusst geschlossen).

## Spalten in `pipeline.csv`

| Spalte | Inhalt |
|---|---|
| `uid` | Ordnernummer in Drive. Stabil. Ändert sich nie. |
| `company`, `role` | Arbeitgeber und Rollentitel |
| `lane` | Data/AI Arch · IT Leadership · Transformation · Public · Operations · Executive · Other |
| `stage`, `outcome` | siehe oben |
| `applied` | ISO-Datum der Bewerbung |
| `last_event` | ISO-Datum des letzten bekannten Signals |
| `days_idle` | Tage seit `last_event` — treibt die „wird kalt"-Logik |
| `score` | 0–100 Konversionswahrscheinlichkeit, Formel unten |
| `salary_fit` | `top` · `high` · `mid` · `stretch` · `below` relative to your band in `preferences.json` → `salary_band` {floor, target} |
| `location`, `contacts` | Standort, benannte Gesprächspartner |
| `folder_id` | Drive-Ordner-ID → jeder Zeilenlink im Dashboard |
| `next_action`, `due` | was geschuldet ist und bis wann — speist das Cockpit |
| `note` | letztes Signal im Klartext (kein HTML) |
| `ts_confidence` | TypeSafe Klassifikations-Konfidenz 0–1 (Schritt 2); leer bei manuell klassifizierten Zeilen |
| `ts_fit_score` | TypeSafe Fit-Score 0–1 (Schritt 4c); leer bis zum ersten Discovery-Lauf |

## Score-Formel (deterministisch, jederzeit nachrechenbar)

```
  Stufe        Watchlist 5 · Applied 20 · Screening 45 · Interviewing 65 · Final 85 · Closed 0
+ Gehalt       top +10 · high +5 · mid 0 · stretch −10 · below −20
+ Aktualität   ≤7 Tage +10 · ≤14 +5 · ≤30 0 · ≤60 −10 · >60 −20
+ Lane         Data/AI Arch, IT Leadership, Transformation +5
+ Boost        + Alt-Boost/2 (Übernahme aus dem früheren 0–14-Ledger)
= geklemmt auf 0–100
```

Keine Heuristik im Kopf des Modells: derselbe Datensatz ergibt bei jedem Lauf denselben Score.

## Ordnerkonvention

```
Bewerbungsordner/
├── _system/                    ← die gesamte Mechanik, ein Ort
│   ├── pipeline.csv            ← Zustand (Wahrheit: Ordner + Gmail)
│   ├── events.csv              ← Ereignisprotokoll, nur angehängt
│   ├── folders.tsv             ← Drive-Inventar für den Abgleich
│   ├── prep.json               ← Briefing-Inhalte je UID
│   ├── render.py · theme.css · core.js · templates/
│   ├── SCHEMA.md · RUNBOOK.md
│   └── archive/                ← datierte Schnappschüsse, .bak
├── 00 references/ · 01 templates/
├── NNN Firma/                  ← OHNE Statuszusatz. Der Status steht in den Daten.
│   └── Rollenname/
│       ├── 10 Bewerbung/       CV, Anschreiben, Ausschreibung, Portalbelege
│       ├── 20 Vorbereitung/    Briefing, Cheat-Sheet, 100-Tage-Plan
│       └── 30 Verlauf/         Mailbelege, Mitschrifte, Notizen
└── 01_cockpit.html · 02_pipeline_crm.html · 03_briefings.html · 04_agentur_report.html/.pdf
```

Warum ohne `(active)` / `(rejected)` im Ordnernamen: der Status ändert sich oft,
der Ordner nie. Kein Umbenennen, keine toten Lesezeichen, keine zwei Wahrheiten.

## Warum die Daten als striktes JSON in den Seiten liegen

Die alten Dashboards trugen ihre Daten als JavaScript-Array-Literal. Ein fehlendes
Komma hat dort im Juli zwei Zeilen stillschweigend verschluckt — die Seite sah heil aus.
Jetzt liegen die Daten in `<script type="application/json">` und werden mit `JSON.parse`
gelesen: ein Syntaxfehler wirft laut, und zusätzlich vergleicht jede Seite die geparste
Zeilenzahl mit der erwarteten und blendet ein rotes Banner ein, wenn sie abweicht.
Eine Ansicht kann nicht mehr unbemerkt unvollständig sein.
