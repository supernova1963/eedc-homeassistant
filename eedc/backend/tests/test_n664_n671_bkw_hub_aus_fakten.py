"""N-664 / N-671 (K4) — *Komponenten → Balkonkraftwerk* liest die Erzeugung aus den Monats-Fakten, wie das Cockpit.

Bis K4 baute der Hub Kopf und Monatsreihe aus der eigenen Zeile des Geräts. Zwei Folgen, beide am HEAD `4110f935`
über die Abnahme-Matrix gemessen (``test_pv_achse_matrix.py``, Formen F04/F05 bzw. F09*):

* **N-664** — ein Balkonkraftwerk ohne eigenen Zähler hat keine Zeile: Kopf 0, „Keine Verlaufsdaten erfasst",
  während die Monats-Fakten ihm seinen kWp-Anteil am Anlagenzähler geben (F04 45 kWh, F05 90 kWh).
* **N-671** — ein an Modul-Kinder abgetretenes Balkonkraftwerk zeigte seinen Zähler (90 kWh / 19,29 €), die Fakten
  führen es mit 0 (die Kinder tragen, ADR-002/P11).

Entscheid Gernot 10.10.2026: „BKW-Hub sollte mit den anderen Hubs verfahren". Die Matrix hält das über alle
Zuordnungsformen mit EINEM Balkonkraftwerk; hier stehen die Einzelwerte, die sie nicht sät — zwei Balkonkraftwerke
ohne Zähler (der Anteil je Gerät, nicht die Anlagensumme) und das Kennzeichen im Kopf.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_balkonkraftwerk import get_balkonkraftwerk_dashboard
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis
from backend.services.monats_fakten import lade_monats_fakten

J, M = 2026, 6
AB = date(2024, 1, 1)


async def _anlage(db, name: str) -> Anlage:
    a = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2023, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    return a


def _inv(a, typ, name, kwp, **kw) -> Investition:
    return Investition(anlage_id=a.id, typ=typ, bezeichnung=name, leistung_kwp=kwp, anschaffungsdatum=AB,
                       anschaffungskosten_gesamt=100.0, **kw)


@pytest.mark.asyncio
async def test_n664_zwei_bkw_ohne_zaehler_je_geraet_sein_kwp_anteil(db):
    """Dach 9 kWp mit 900 kWh, Anlagenwert 1 020 kWh ⇒ Rest 120 nach kWp: Balkon 0,8 kWp → 80, Balkon2 0,4 → 40.

    Der Hub nennt je Gerät seinen Anteil (nicht die Anlagensumme 120), mit Kennzeichen ``kwp_anteil``; Σ der Geräte =
    ``bkw_aus_anlagenwert_kwh`` der Fakten. Vorher: kein Gerät hatte eine Zeile — Kopf 0, Reihe leer."""
    a = await _anlage(db, "zwei BKW")
    dach, b1, b2 = (_inv(a, "pv-module", "Dach", 9.0), _inv(a, "balkonkraftwerk", "Balkon", 0.8),
                    _inv(a, "balkonkraftwerk", "Balkon2", 0.4))
    db.add_all([dach, b1, b2])
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=1020.0))
    db.add(InvestitionMonatsdaten(investition_id=dach.id, jahr=J, monat=M, verbrauch_daten={"pv_erzeugung_kwh": 900.0}))
    await db.commit()

    (fakt,) = await lade_monats_fakten(db, a.id, von=(J, M), bis=(J, M))
    karten = {k.investition.bezeichnung: k for k in await get_balkonkraftwerk_dashboard(
        anlage_id=a.id, strompreis_cent=None, db=db)}

    for name, soll in (("Balkon", 80.0), ("Balkon2", 40.0)):
        (m,) = karten[name].monatsreihe
        assert (m.jahr, m.monat, m.erzeugung_quelle) == (J, M, "kwp_anteil")
        assert m.erzeugung_kwh == pytest.approx(soll)
        z = karten[name].zusammenfassung
        assert z["gesamt_erzeugung_kwh"] == soll
        assert z["erzeugung_aus_anlagenwert_kwh"] == soll
        # Eigenverbrauch anteilig an der Hausbilanz: EV 1 020 − 400 = 620, Anteil soll / 1 020.
        assert m.eigenverbrauch_quelle == "anteilig"
        assert m.eigenverbrauch_kwh == pytest.approx(620.0 * soll / 1020.0)
    assert sum(k.monatsreihe[0].erzeugung_kwh for k in karten.values()) == pytest.approx(
        fakt.erzeugung.bkw_aus_anlagenwert_kwh)


@pytest.mark.asyncio
async def test_n671_abgetretenes_bkw_zeigt_null_wie_die_fakten(db):
    """Balkon mit eigenem Zähler 90 kWh und zwei Modul-Kindern: die Kinder tragen (P11), die Fakten führen das BKW
    mit 0. Der Hub folgt — Erzeugung, Eigenverbrauch, Ersparnis 0, Monat als ``abgetreten`` gekennzeichnet und im Kopf
    gezählt. Vorher 90 kWh / anteilig 64,3 kWh / 19,29 €."""
    a = await _anlage(db, "abgetreten")
    bkw = _inv(a, "balkonkraftwerk", "Balkon", 0.8)
    db.add(bkw)
    await db.flush()
    db.add_all([_inv(a, "pv-module", "Kind 1", 0.3, parent_investition_id=bkw.id),
                _inv(a, "pv-module", "Kind 2", 0.5, parent_investition_id=bkw.id)])
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=25.0, netzbezug_kwh=200.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=M, verbrauch_daten={"pv_erzeugung_kwh": 90.0}))
    await db.commit()

    (fakt,) = await lade_monats_fakten(db, a.id, von=(J, M), bis=(J, M))
    assert fakt.erzeugung.bkw_kwh == 0.0          # die Fakten: das BKW trägt nichts, die Kinder tragen
    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    (m,) = karte.monatsreihe
    assert (m.erzeugung_kwh, m.erzeugung_quelle, m.eigenverbrauch_kwh) == (0.0, "abgetreten", 0.0)
    z = karte.zusammenfassung
    assert (z["gesamt_erzeugung_kwh"], z["gesamt_eigenverbrauch_kwh"], z["gesamt_ersparnis_euro"]) == (0.0, 0.0, 0.0)
    assert z["monate_abgetreten"] == 1


@pytest.mark.asyncio
async def test_eigener_zaehler_bleibt_gemessen(db):
    """Gegenstück: ein BKW mit eigenem Wert und ohne Kinder liest seinen Wert aus den Fakten — dieselbe Zahl wie die
    Zeile (45,1), Kennzeichen ``gemessen``, kein Anteil im Kopf."""
    a = await _anlage(db, "gemessen")
    bkw = _inv(a, "balkonkraftwerk", "Balkon", 0.8)
    db.add(bkw)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=15.1, netzbezug_kwh=80.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=M, verbrauch_daten={"pv_erzeugung_kwh": 45.1}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    (m,) = karte.monatsreihe
    assert (m.erzeugung_kwh, m.erzeugung_quelle) == (pytest.approx(45.1), "gemessen")
    assert karte.zusammenfassung["erzeugung_aus_anlagenwert_kwh"] == 0.0
    assert karte.zusammenfassung["monate_abgetreten"] == 0
