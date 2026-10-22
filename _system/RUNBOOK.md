# STAR Runbook (STAR)

Für deine KI-Sitzung. Täglich oder vor einem Gespräch ausführen. {{MARK:send}}

## 1. Stand
`./star sync --kit --skip-preflight` aktualisiert Scores, Index, Gesundheit und die Seiten und druckt die Intel-Queue.

## 2. Recherche nach Stufe (höchstens 3 Elemente pro Lauf)
`./star intel_queue --json --limit 3` und die Elemente in dieser Reihenfolge abarbeiten.
- `stage_doc` / `after_interview`: den Auftrag (`order_file`) öffnen, im Web mit öffentlichen Quellen recherchieren und die Datei
  `<Firma>_<CheatSheet|Briefing|Strategy_Doc>_<Datum>_v<N>.md` in `20 Vorbereitung` schreiben. Jede Aussage FACT oder INFERENCE,
  jedes FACT mit URL und Abrufdatum, Abschnitt „Offen / nicht verifiziert“. {{MARK:overwrite}}
  Danach `./star intel_lint --uid N` und Befunde beheben.
- `prep_content`: `Prep_Inhalt.json` aus dem aktuellen Briefing schreiben (Schlüssel siehe `kit_examples` und das Beispiel unten),
  dann `./star prep_engine --uid N --from-content`.

## 3. Prep_Inhalt.json
Schlüssel: `company_snapshot`, `strategic_context`, `contacts` (name, title, background, open_question), `keyfacts` (diagnosed_pain,
value_statement, followup_sent, agenda_artifact), `open_hook`, `close_hook`, `questions` (rank, question, to, why; mindestens 3),
`open_items`, `intel` (snapshot, jd_bullets, diagnosed_pain, decision_maker, scope_signal, salary_estimate) und `cockpit`
(termin, lage, stand, vorschlag, fuehrung, flanken, faktenhygiene, vorher, bio, panik). Inhalt nur aus dem Briefing; {{MARK:open}}

## 4. Bio
Nur aus `00 references/Bio_Bausteine.json`. Titel und Zahlen genau so. Formulierungen aus `nicht_sagen_woerter` sind verboten
(das Rendern meldet sie). Keine Erfahrung behaupten, die nicht belegt ist.

## 5. Nach einem Gespräch
Notizen aus dem Cockpit als `Interview_Notizen_<Firma>_<Datum>.txt` in `30 Verlauf` legen. Dann Nachbereitung:
`./star intel_job --uid N --after-interview`, Debrief schreiben, nächste Version des Briefings, Cockpit neu rendern.
Neue Lernpunkte in `00 references/Gespraechs_Playbook.json` ergänzen (nie löschen).

## 6. Wochenbericht
`./star pilot_report` erzeugt eine Wochenübersicht nur mit Zahlen, für dich selbst.
