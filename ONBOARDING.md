# Onboarding (für deine KI-Sitzung)

Arbeite diese Schritte mit mir ab, einen nach dem anderen. Frage nach, wenn etwas fehlt. **Erfinde nichts.**

1. **Profil.** Lies `_system/profile.json`. Frage nach Name und Marke und trage sie ein. Optional: ein Foto und ein kurzer Ausscheiden-Text
   (`exit_summary`, Deutsch und Englisch) mit Pfad zu einer Datei in `00 references`.
2. **Bio-Bausteine.** Lies meinen CV (Datei in `00 references`). Schlage je Station, Zahl und Ergebnis einen Baustein für
   `00 references/Bio_Bausteine.json` vor (`id`, `text`, `beleg`). **Ich bestätige jeden Fakt einzeln**, bevor er eingetragen wird. Trage
   falsche Titel, die ich nicht verwenden will, in `nicht_sagen_woerter` ein.
2b. **Beispieldaten.** Im Ordner liegen zwei erfundene Demo-Verfahren („Beispiel Maschinenbau AG“, „Beispiel Versicherung SE“), damit die Seiten gefüllt sind.
   Zeige sie mir kurz (Pipeline, Briefing in der Lesezone, Cockpit). Wenn ich bereit bin: `./pitwall kit_demo --remove` legt nur ab, was die Demo angelegt hat (nach `_Archiv`; eigene Dateien bleiben).
2c. **Verlauf einspielen.** Frage mich, ob ich meine bisherige Suche einspielen will (Excel, Notion, Mails, Notizen). Wandle sie in eine CSV nach dem
   Muster `_system/kit_examples/history_import.example.csv` um (Pflicht: Firma und Position; dazu Status, Beworben am, Letzter Kontakt, Ort, Notiz),
   zeige mir `./pitwall kit_import verlauf.csv` als Vorschau und führe erst nach meinem Ja `./pitwall kit_import verlauf.csv --apply` aus. Erfinde nichts.
3. **Erste Verfahren.** Frage nach meinen laufenden Bewerbungen und lege sie in `_system/pipeline.csv` an (Spalten siehe Kopfzeile;
   Stufen: Watchlist, Applied, Screening, Interviewing, Final).
4. **Erste Recherche.** Führe `RUNBOOK.md` Schritt „Intel-Queue" aus: `./pitwall intel_queue --json`, dann das oberste Element.
5. **Erstes Cockpit.** Schreibe `Prep_Inhalt.json` aus dem Briefing und rendere mit
   `./pitwall prep_engine --uid N --from-content`. Zeige mir das Cockpit und frage, was fehlt.
