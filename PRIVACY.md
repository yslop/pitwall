# Datenschutz: Governance by Design

STAR ist so gebaut, dass Datenschutz nicht von guten Vorsätzen abhängt, sondern von der Architektur.

| Prinzip | Umsetzung |
|---|---|
| Lokal zuerst | Alles Deterministische läuft in Python auf deinem Rechner. Ergebnisse sind Dateien in diesem Ordner. |
| Kein Konto, keine Telemetrie | Es gibt keinen Server von STAR. Nichts wird gezählt oder gemeldet. |
| Deine KI, deine Entscheidung | Du wählst im Einrichtungs-Dialog Abo, eigenen Schlüssel, EU-Anbieter oder ein lokales Modell. |
| Nur lokal | Ein Schalter sperrt jeden entfernten KI-Anbieter, im Dialog und im Code (`setup/ai.py`). |
| Geheimnisse getrennt | API-Schlüssel stehen nur in `.env` (Dateirechte 600), nie in `config/settings.json`, nie im Log. |
| Protokoll ohne Inhalt | `logs/ai_calls.jsonl` hält Zeit, Anbieter, Zweck und Zeichenzahl fest, nie Prompt oder Antwort. |
| Nichts Persönliches in Git | `.gitignore` schließt alle persönlichen Dateien aus; der Leak-Guard prüft jeden Pull Request. |

**Was trotzdem deine Verantwortung bleibt:** Wenn du einen entfernten KI-Anbieter nutzt, gelten dessen Bedingungen für das,
was du ihm schickst. Schicke keine Daten Dritter, die du nicht teilen darfst. Gesprächsnotizen über andere Menschen sind
personenbezogene Daten: Halte sie sparsam und nur für dich.

Dies ist eine Beschreibung der Technik, keine Rechtsberatung.
