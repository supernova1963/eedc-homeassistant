"""Jahresroute — was die Kopfzahl enthält und was ihr fehlt, steht in der Antwort (ADR-002/P4).

1. **E11** (Entscheid Gernot 03.10.2026, N-584): Cockpit → Jahr behält abgeschlossene Monate OHNE Monatsabschluss mit
   ihren Werten aus Home Assistant (N-65) und nennt sie in einer Hinweiszeile; Übersicht und Jahresbericht zählen nur
   abgeschlossene Monate. Fixture wie P1 (`test_n584_jahr_grundgesamtheit.py`): acht Monate mit Abschluss, September nur
   aus HA.
2. **Ein Monat, dessen Berechnung wirft** (Nachmessung 03.10., Vor-Release-Punkt c): bis dahin übersprang die Route ihn
   still (`except Exception: continue`) — die Summe war eine Teilsumme ohne Ausweis. Jetzt in `hinweise` und
   `fehlende_posten`.

Schwesterdateien: test_n584_jahr_grundgesamtheit.py, test_ergebnis_jahr_portiert.py.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.api.routes.cockpit.jahr import get_cockpit_jahr
from backend.tests.test_n584_jahr_grundgesamtheit import JAHR, _anlage


def _ha_september(monkeypatch):
    import backend.api.routes.aktueller_monat as am

    async def _ha(anlage, j, m):
        if (j, m) != (JAHR, 9):
            return {}
        info = am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92, zeitpunkt=datetime(JAHR, 10, 1).isoformat())
        return {"einspeisung_kwh": (100.0, info), "pv_erzeugung_kwh": (649.0, info)}

    async def _leer(*_a, **_k):
        return {}

    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha)
    monkeypatch.setattr(am, "_collect_connector_data", _leer)


@pytest.mark.asyncio
async def test_e11_monat_ohne_abschluss_wird_genannt(db, monkeypatch):
    aid = await _anlage(db)
    _ha_september(monkeypatch)
    jahr = await get_cockpit_jahr(anlage_id=aid, jahr=JAHR, db=db)
    hinweise = jahr["kopf"]["hinweise"]
    assert any(h.startswith("1 Monat ohne Monatsabschluss (Sep), Werte aus Home Assistant") for h in hinweise), hinweise
    assert 9 in jahr["monate_nr"], "der Monat bleibt in der Kopfzahl (N-65) — er wird beschriftet, nicht entfernt"


@pytest.mark.asyncio
async def test_e11_ohne_solchen_monat_kein_hinweis(db):
    aid = await _anlage(db)
    jahr = await get_cockpit_jahr(anlage_id=aid, jahr=JAHR, db=db)
    assert not any("ohne Monatsabschluss" in h for h in jahr["kopf"]["hinweise"])


@pytest.mark.asyncio
async def test_ein_monat_der_wirft_fehlt_nicht_still(db, monkeypatch):
    import backend.api.routes.aktueller_monat as am

    aid = await _anlage(db)
    original = am._berechne_monat

    async def _wirft_im_maerz(anlage_id, j, m, db_, **kw):
        if m == 3:
            raise RuntimeError("Probe: Monat nicht berechenbar")
        return await original(anlage_id, j, m, db_, **kw)

    monkeypatch.setattr(am, "_berechne_monat", _wirft_im_maerz)
    jahr = await get_cockpit_jahr(anlage_id=aid, jahr=JAHR, db=db)
    kopf = jahr["kopf"]
    assert 3 not in jahr["monate_nr"]
    assert any("Mär 2025 konnte nicht berechnet werden" in h for h in kopf["hinweise"]), kopf["hinweise"]
    assert "Monat Mär 2025" in kopf["fehlende_posten"]
