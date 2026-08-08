"""Eine gepflegte **0** ct/kWh Einspeisevergütung bleibt 0 — in jeder Sicht.

Seit 08.08.2026 belegt eedc das Feld mit 0 vor, statt einen EEG-Satz aus der
Anlagengröße zu raten (T89667 #122). Damit wird eine 0 zum Regelfall — und
`wert or DEFAULT` ersetzt sie still durch 8,2 ct. Drei Stellen taten genau das,
während alle übrigen Leser korrekt `is not None` prüfen: das Vorjahr im
Cockpit-Monat, dessen T-Konto und die Wirtschaftlichkeit je Investition. Das
Ergebnis wären zwei Zahlen für dieselbe Größe auf derselben Seite.

Die Probe misst am **Quelltext**, nicht an einer Route: die drei Stellen liegen
in drei verschiedenen Antwortpfaden mit je eigenem Datenbedarf, und die
gemeinsame Aussage ist eine über die Auflösung des Wertes — nicht über eine
einzelne Endpunkt-Antwort. Der Positivfall unten belegt, dass der Grep greift.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROUTES = Path(__file__).resolve().parents[1] / "api" / "routes"

# `<irgendwas> or EINSPEISEVERGUETUNG_DEFAULT_CENT` bzw. `or (` mit dem Default
# in derselben Zeile — die Form, die eine gepflegte 0 verschluckt.
_TRUTHY = re.compile(r"\bor\s+\(?[^\n]*EINSPEISEVERGUETUNG_DEFAULT_CENT")


def _fundstellen(text: str) -> list[str]:
    return [z.strip() for z in text.splitlines() if _TRUTHY.search(z)]


def test_kein_truthy_fallback_auf_die_einspeiseverguetung():
    treffer: list[str] = []
    dateien = list(_ROUTES.rglob("*.py"))
    assert len(dateien) > 20, "Der Baum-Durchlauf hat nichts gefunden — Pfad falsch?"

    for pfad in dateien:
        for zeile in _fundstellen(pfad.read_text(encoding="utf-8")):
            treffer.append(f"{pfad.relative_to(_ROUTES)}: {zeile}")

    assert not treffer, (
        "Eine gepflegte 0 ct würde hier still durch den Default ersetzt — "
        "`is not None` statt truthy:\n" + "\n".join(treffer)
    )


def test_der_grep_greift_ueberhaupt():
    """Gegenprobe: ohne sie wäre ein leerer Treffersatz nichts wert."""
    assert _fundstellen(
        "    einsp = tarif.einspeiseverguetung_cent_kwh or EINSPEISEVERGUETUNG_DEFAULT_CENT\n"
    )
    assert _fundstellen(
        "    x = y or (a if b else EINSPEISEVERGUETUNG_DEFAULT_CENT)\n"
    )
    # Die korrigierte Form darf NICHT anschlagen.
    assert not _fundstellen(
        "    einsp = wert if wert is not None else EINSPEISEVERGUETUNG_DEFAULT_CENT\n"
    )
