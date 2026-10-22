# Contributing

Thank you for helping. This project believes in open knowledge: what helped you should help others.

1. **Issue first** for anything larger than a typo: problem, proposal, who benefits.
2. **Fork and branch**, then run `python3 -m pytest -q` and `python3 tools/leak_guard.py .` locally.
3. **Pull request** against `main`, one topic per PR, using the template.

Three non-negotiable rules:

1. **No real personal data.** Examples are invented ("Beispiel …", "Alex Muster"). The leak guard checks every PR.
2. **No third-party protected content.** No text from books, course material, official exam questions or paid sources.
3. **Local first.** New network calls need a reason in the PR and must respect "local only".

Python ≥ 3.9, standard library in the engine. German and English UI text are both welcome; new UI strings need an entry in
the English catalogue (`i18n_en.json`). By contributing you agree that your work is published under the project licence.
