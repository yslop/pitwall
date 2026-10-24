# Mitmachen bei Pitwall

Danke, dass du Pitwall besser machen willst. Dieses Projekt glaubt an offenes Wissen: Was dir geholfen hat, soll auch
anderen helfen.

## Was besonders willkommen ist

- Gesprächsleitfäden und Fragen an das Panel, die sich in echten Gesprächen bewährt haben (ohne echte Namen)
- Import-Formate für bisherige Bewerbungslisten (Excel, Notion, andere Tracker)
- Übersetzungen der Oberfläche
- Tests, besonders für Windows
- Barrierefreiheit der Cockpit-Seiten

## So läuft ein Beitrag

1. **Issue zuerst** bei allem, was größer als ein Tippfehler ist. Kurz beschreiben: Problem, Vorschlag, wer profitiert.
2. **Fork und Branch**: `git checkout -b kurz-beschreibender-name`.
3. **Tests und Leak-Guard lokal**:
   ```bash
   python3 -m pytest -q
   python3 tools/leak_guard.py .
   ```
4. **Pull Request** gegen `main` mit der Vorlage. Ein Thema pro PR.

## Drei Regeln, die nicht verhandelbar sind

1. **Keine echten personenbezogenen Daten.** Keine Namen, Mailadressen, Telefonnummern, Firmen aus deiner eigenen Suche,
   keine echten Gesprächsnotizen. Beispiele sind erfunden und heißen „Beispiel …“ oder „Alex Muster“. Der Leak-Guard
   prüft jeden PR, er ersetzt aber nicht dein eigenes Hinsehen.
2. **Keine fremden geschützten Inhalte.** Keine Texte aus Büchern, Kursunterlagen, offiziellen Prüfungsfragen oder
   kostenpflichtigen Quellen. Eigene Formulierungen, mit Quelle für Fakten.
3. **Lokal zuerst.** Was in Python auf dem Rechner der Nutzer:innen gehen kann, geht dort. Neue Netzwerkaufrufe brauchen
   eine Begründung im PR und müssen sich über „Nur lokal“ abschalten lassen.

## Stil

- Python ≥ 3.9; zur Laufzeit nur die Pakete aus `requirements.txt` (Jinja2, requests, Beautiful Soup). Neue Abhängigkeiten nur nach Rücksprache.
- Deutsch in Oberfläche und Dokumentation, Englisch in Code-Bezeichnern ist in Ordnung.
- Kurze Funktionen, sprechende Namen, ein Test je Fehlerpfad.

## Wie Beiträge in Releases kommen

Pitwall wird von XLRTE gepflegt. Beiträge werden im öffentlichen Repository geprüft und gemergt und fließen mit dem
nächsten Release ein. Wer beiträgt, steht im CHANGELOG. Mit deinem Beitrag stimmst du zu, dass er unter der Lizenz des
Projekts veröffentlicht wird.
