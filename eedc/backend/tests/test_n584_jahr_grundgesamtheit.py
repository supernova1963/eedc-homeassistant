"""P1 — N-584 (#421 Raia-Jicin): ein Jahr rechnet seine Quoten über EINE Grundgesamtheit.

Der Melderfall: acht Monate mit Eigenverbrauch UND Gesamtverbrauch, dazu ein Monat mit Eigenverbrauch, aber ohne
Netzbezugswert (also ohne Gesamtverbrauch und ohne Stromrechnung). Die Feld-für-Feld-Faltung im Browser rechnete
Σ EV ÷ Σ GV über verschiedene Monate: 1 108 ÷ 559 = 198 % Autarkie. Die Jahresroute rechnet paarweise
(``quote_paarweise``) und nennt das Fenster; das Jahresergebnis ist ``None`` mit genanntem Monat (G2/E10).

Echte Einstiege: ``GET /api/cockpit/jahr`` in-process (``get_cockpit_jahr``). Der neunte Monat hat keinen
Monatsabschluss, seine Mengen liefert die HA-Statistik (gepatcht — dieselbe Form wie
``test_aktueller_monat_datenquellen_prioritaet.py``): Einspeisung und PV, aber kein Netzbezug.

Schwesterdateien: test_ergebnis_jahr_portiert.py, test_ergebnis_symmetrie_monat_jahr.py.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.jahr import get_cockpit_jahr
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR = 2025


async def _anlage(db) -> int:
    anlage = Anlage(anlagenname="N-584", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    db.add(pv)
    await db.flush()
    # Jan–Aug: je 559/8 kWh Eigenverbrauch bei 0 kWh Netzbezug (Volleinspeiser-Muster) ⇒ EV = GV.
    ev_je_monat = 559.0 / 8
    for m in range(1, 9):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=m, einspeisung_kwh=300.0, netzbezug_kwh=0.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=JAHR, monat=m,
                                      verbrauch_daten={"pv_erzeugung_kwh": 300.0 + ev_je_monat}))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_p1_autarkie_paarweise_und_kein_jahresergebnis_ohne_stromrechnung(db, monkeypatch):
    import backend.api.routes.aktueller_monat as am
    anlage_id = await _anlage(db)

    async def _ha(anlage, j, m):
        if (j, m) != (JAHR, 9):
            return {}
        info = am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92, zeitpunkt=datetime(JAHR, 10, 1).isoformat())
        # September ohne Abschluss: Einspeisung und PV aus HA, Netzbezug fehlt (N-585) ⇒ EV 549, GV None.
        return {"einspeisung_kwh": (100.0, info), "pv_erzeugung_kwh": (649.0, info)}

    async def _leer(*_a, **_k):
        return {}

    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha)
    monkeypatch.setattr(am, "_collect_connector_data", _leer)

    jahr = await get_cockpit_jahr(anlage_id=anlage_id, jahr=JAHR, db=db)
    kopf = jahr["kopf"]
    sept = next(m for m in jahr["monate"] if m["monat"] == 9)
    assert sept["eigenverbrauch_kwh"] == pytest.approx(549.0)
    assert sept["gesamtverbrauch_kwh"] is None, "Fixture: der Monat trägt EV, aber keinen Gesamtverbrauch"

    assert kopf["eigenverbrauch_kwh"] == pytest.approx(1108.0, abs=0.1), "die Summe selbst bleibt die Summe aller Monate"
    assert kopf["autarkie_prozent"] == pytest.approx(100.0), "198 % war Σ EV (9 Monate) ÷ Σ GV (8 Monate)"
    assert kopf["autarkie_zaehler_kwh"] == pytest.approx(559.0, abs=0.1)  # Monats-EV auf 2 Stellen gerundet
    assert kopf["autarkie_nenner_kwh"] == pytest.approx(559.0, abs=0.1)
    assert kopf["autarkie_fenster"] == "aus 8 von 9 Monaten"
    assert kopf["autarkie_prozent"] <= 100.0

    # G2/E10: der Netto-Ertrag läuft über alle neun Monate, das Jahresergebnis gibt es nicht — mit genanntem Monat.
    assert kopf["netto_ertrag_euro"] is not None
    assert kopf["ergebnis_euro"] is None
    assert "Stromrechnung (Sep 2025)" in kopf["fehlende_posten"]
