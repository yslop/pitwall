import os, pytest, json

os.environ.setdefault("TYPESAFE_LEDGER", "off")  # keep test runs out of the token ledger

REJECTION_EMAIL = {
    "subject": "Ihre Bewerbung bei Musterfirma GmbH",
    "body": "Vielen Dank für Ihre Bewerbung. Leider müssen wir Ihnen mitteilen, "
            "dass wir Ihren Bewerbungsunterlagen nicht entsprechen können. "
            "Wir haben uns entschieden, den Prozess mit anderen Kandidaten fortzuführen."
}

INTERVIEW_EMAIL = {
    "subject": "Einladung zum Vorstellungsgespräch — Head of Data",
    "body": "Sehr geehrter Herr Testnachname, wir freuen uns, Sie zu einem "
            "Vorstellungsgespräch am Dienstag, 30. September 2026 um 10:00 Uhr einzuladen. "
            "Panel: Frau Müller (HR) und Herr Schmidt (CIO)."
}

HOLD_EMAIL = {
    "subject": "Re: Ihre Bewerbung",
    "body": "Guten Tag, wir benötigen noch etwas Zeit für unsere interne Abstimmung. "
            "Sobald wir eine Rückmeldung haben, melden wir uns bei Ihnen."
}

ATS_ACK_EMAIL = {
    "subject": "Eingangsbestätigung Ihrer Bewerbung",
    "body": "Wir haben Ihre Bewerbungsunterlagen erhalten und bestätigen den Eingang. "
            "Ihre Bewerbung wird nun von unserem Recruiting-Team gesichtet."
}

MOCK_REJECTION_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "signal": {
            "type": "choice",
            "choice": "closed_rejected",
            "confidence": 0.92,
            "probabilities": {
                "closed_rejected": 0.92, "applied": 0.02, "screening": 0.01,
                "interviewing": 0.01, "final": 0.01, "closed_withdrawn": 0.01,
                "closed_declined": 0.01, "closed_signed": 0.01, "no_match": 0.0
            }
        }
    },
    "usage": {"input_tokens": 200, "output_tokens": 15},
}

MOCK_LOW_CONFIDENCE_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "signal": {
            "type": "choice",
            "choice": "screening",
            "confidence": 0.55,
            "probabilities": {
                "screening": 0.55, "applied": 0.25, "interviewing": 0.10,
                "final": 0.05, "closed_rejected": 0.03, "closed_withdrawn": 0.01,
                "closed_declined": 0.005, "closed_signed": 0.005, "no_match": 0.0
            }
        }
    },
    "usage": {"input_tokens": 200, "output_tokens": 15},
}


# Tests that read the live Drive data (pipeline.csv, sheet_export.csv, employer folders). The data never
# enters git, so in the repo and in CI they are skipped; after a deploy they run in Drive with the data.
_LIVE_DATA_MODULES = {"test_boundary_and_export_safety.py", "test_empirical_stress.py"}
_SYSTEM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pytest_collection_modifyitems(config, items):
    if os.path.exists(os.path.join(_SYSTEM_DIR, "pipeline.csv")):
        return
    skip = pytest.mark.skip(reason="needs live Drive data (pipeline.csv); runs in Drive after deploy")
    for item in items:
        if os.path.basename(str(item.fspath)) in _LIVE_DATA_MODULES:
            item.add_marker(skip)
