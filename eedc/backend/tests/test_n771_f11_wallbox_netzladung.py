"""N-771 F11 (Entscheid Gernot 31.10.2026) — der gemessene Netzbezug zum Wallbox-Tarif IST die Netzladung der Wallbox.

Wo das Feld «Netzbezug zum Wallbox-Tarif» (``netzbezug_eigener_tarif_kwh``) an einer Wallbox-Zeile steht, ist N_wb ihre
Netzladung — auch gegen einen gepflegten evcc-Wert; PV-Ladung = Ladung − N_wb (Trias geschlossen), N_wb auf [0, Ladung]
geklemmt (Nachtrag Master: die zweite Klemme auf Netzbezug − N_wp gilt nur der Stromrechnung). Die E-Mob-Ersparnis
liest diese Netzladung: Wallbox 200 kWh, evcc PV 150 / Netz 50, N_wb = 120 ⇒ Netz 120, PV 80; die E-Auto-Ersparnis
bewegt sich um 70 kWh × (EV-Preis 30 ct − Wallbox-Tarif 20 ct) = +7,00 € (N-672: PV-Ladung zum Preis der
Eigenverbrauchs-Ersparnis, Netzladung zum Wallbox-Tarif).

Sprengsatz (im Bericht gefahren): ``reader.netzladung_des_zaehlers`` liefert ``None`` ⇒ die Proben mit Feld rot.

Schwesterdateien: test_n771_e6_reste_gemeinsamer_zaehler.py (Zuordnungsmonat, laufender Monat, gemeinsamer Zähler),
test_n770_e3_tag_stunde.py, test_n767_wp_eigener_tarif.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.core.field_definitions import get_emob_pv_netz_kwh, netzladung_des_zaehlers
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.monats_fakten import lade_monats_fakten

J = 2025


def test_netzladung_des_zaehlers_klemmt_auf_die_ladung():
    assert netzladung_des_zaehlers({"ladung_kwh": 200.0}) is None
    assert netzladung_des_zaehlers({"ladung_kwh": 200.0, "netzbezug_eigener_tarif_kwh": 120.0}) == (80.0, 120.0)
    assert netzladung_des_zaehlers({"ladung_kwh": 200.0, "netzbezug_eigener_tarif_kwh": 250.0}) == (0.0, 200.0)
    assert netzladung_des_zaehlers({"ladung_kwh": 200.0, "netzbezug_eigener_tarif_kwh": -3.0}) == (200.0, 0.0)
    # gegen evcc: der Zähler gewinnt
    assert get_emob_pv_netz_kwh({"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0, "ladung_netz_kwh": 50.0,
                                 "netzbezug_eigener_tarif_kwh": 120.0}) == (80.0, 120.0)
    assert get_emob_pv_netz_kwh({"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0, "ladung_netz_kwh": 50.0}) == (150.0, 50.0)


async def _anlage(db, *, n_wb: float | None, auto_daten: dict | None = None) -> Anlage:
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="N-771 F11", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=14.0))
    db.add(Strompreis(anlage_id=anlage.id, verwendung="wallbox", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=20.0, einspeiseverguetung_cent_kwh=0.0, grundpreis_euro_monat=8.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Garage", anschaffungsdatum=date(2024, 1, 1))
    auto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1),
                       parameter={"vergleich_verbrauch_l_100km": 7.0, "benzinpreis_euro": 1.70})
    db.add_all([pv, wb, auto])
    await db.flush()
    wb_daten = {"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0, "ladung_netz_kwh": 50.0}
    if n_wb is not None:
        wb_daten["netzbezug_eigener_tarif_kwh"] = n_wb
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=J, monat=1, verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=J, monat=1, verbrauch_daten=wb_daten))
    db.add(InvestitionMonatsdaten(investition_id=auto.id, jahr=J, monat=1,
                                  verbrauch_daten=auto_daten or {"km_gefahren": 1000.0}))
    md = Monatsdaten(anlage_id=anlage.id, jahr=J, monat=1, netzbezug_kwh=400.0, einspeisung_kwh=100.0)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    return anlage


async def test_fakten_netzladung_aus_dem_feld_trias_geschlossen(db):
    mit = await _anlage(db, n_wb=120.0)
    (f,) = [x for x in await lade_monats_fakten(db, mit.id) if (x.jahr, x.monat) == (J, 1)]
    assert (f.emob.ladung_kwh, f.emob.ladung_pv_kwh, f.emob.ladung_netz_kwh) == pytest.approx((200.0, 80.0, 120.0))
    ohne = await _anlage(db, n_wb=None)
    (g,) = [x for x in await lade_monats_fakten(db, ohne.id) if (x.jahr, x.monat) == (J, 1)]
    assert (g.emob.ladung_pv_kwh, g.emob.ladung_netz_kwh) == pytest.approx((150.0, 50.0))


async def test_emob_ersparnis_liest_die_netzladung_des_zaehlers(db):
    mit = await get_aktueller_monat((await _anlage(db, n_wb=120.0)).id, J, 1, db)
    ohne = await get_aktueller_monat((await _anlage(db, n_wb=None)).id, J, 1, db)
    assert mit.emob_ersparnis_euro - ohne.emob_ersparnis_euro == pytest.approx(70 * (0.30 - 0.20), abs=0.011)
    # Stromrechnung: (400 − 120) × 30 + 120 × 20 + 14 + 8
    assert mit.netzbezug_kosten_euro == pytest.approx(280 * 0.30 + 120 * 0.20 + 22.0, abs=0.005)
    zeile = next(d for d in mit.investitionen_financials if d.typ == "e-auto")
    assert "Netzladung: Zähler des Versorgers" in zeile.berechnung
    zeile_ohne = next(d for d in ohne.investitionen_financials if d.typ == "e-auto")
    assert "Zähler des Versorgers" not in (zeile_ohne.berechnung or "")


async def test_auto_mit_eigener_messung_behaelt_seine_aufteilung(db):
    """Regel 2 Schritt 1 (N-555): ein Auto, das seine Heimladung selbst misst, behält sie; der Zähler teilt nur die
    Wallbox-Zeile (hier ganz vom Auto belegt) — E-Mob-Ersparnis gleich, die Auto-Zeile ohne den Herkunfts-Satz."""
    eigen = {"km_gefahren": 1000.0, "ladung_kwh": 200.0, "ladung_pv_kwh": 150.0, "ladung_netz_kwh": 50.0}
    mit = await get_aktueller_monat((await _anlage(db, n_wb=120.0, auto_daten=eigen)).id, J, 1, db)
    ohne = await get_aktueller_monat((await _anlage(db, n_wb=None, auto_daten=eigen)).id, J, 1, db)
    assert mit.emob_ersparnis_euro == ohne.emob_ersparnis_euro
    auto = next(d for d in mit.investitionen_financials if d.typ == "e-auto")
    assert "Zähler des Versorgers" not in (auto.berechnung or "")
