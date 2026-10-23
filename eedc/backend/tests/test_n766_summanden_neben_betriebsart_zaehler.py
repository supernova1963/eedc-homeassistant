"""N-766 (simon42 T89667 #435, MartyBr) — Summanden neben einem Betriebsart-Zähler.

Eine Wärmepumpe mit getrennter Strommessung (Strom Heizen · Strom Warmwasser) und einem Betriebsart-Zähler (Kühlen)
zeigte in Tag und Monat «Strom-Aufteilung nach Betriebsart» mit Heizen 0 kWh und dem ganzen Strom «nicht aufgeteilt»:
der gemessene Zweig von ``modus_strom_zeile`` las nur die Betriebsart-Felder. Jetzt zählen die Summanden dort mit —
nur, wenn sie Summanden sind (Kennzeichen ``getrennte_strommessung``, dieselbe Frage wie in ``wp_strom_aufteilung``
und ``verteile_geraet_strom``)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile, summanden_gelten
from backend.core.berechnungen.tages_stapel import (
    STUNDEN,
    StundenFormen,
    _falte,
    beitraege_des_tages,
    falte_tages_stapel,
    summanden_aus_tageswerten,
    verteile_tages_stapel_auf_stunden,
)
from backend.core.field_definitions.wp_strom import wp_strom_aufteilung

TAG = date(2026, 10, 22)
MARTY = {"strom_heizen_kwh": 5.0, "strom_warmwasser_kwh": 1.0, "betriebsart_strom_kuehlen_kwh": 0.0}
GETRENNT = {"wp_art": "sole_wasser", "getrennte_strommessung": True}


class _Inv:
    def __init__(self, parameter):
        self.parameter = parameter

    def ist_aktiv_an(self, _datum):
        return True


# ── Layer: modus_strom_zeile ─────────────────────────────────────────────────


def test_summanden_und_kuehlzaehler_ergeben_heizen_und_warmwasser_gemessen():
    z = modus_strom_zeile(MARTY, summanden_zaehlen=True)
    assert (z.heizen_kwh, z.warmwasser_kwh, z.kuehlen_kwh, z.gemessen) == (5.0, 1.0, 0.0, True)


def test_ohne_kennzeichen_wie_bisher():
    """Kennzeichen aus (alte Summandenwerte in der Zeile): keine Summanden im Balken — Default und Gate."""
    for z in (modus_strom_zeile(MARTY), modus_strom_zeile(MARTY, summanden_zaehlen=False)):
        assert (z.heizen_kwh, z.warmwasser_kwh, z.gemessen) == (0.0, 0.0, True)
    assert summanden_gelten(GETRENNT) and not summanden_gelten({"wp_art": "sole_wasser"}) and not summanden_gelten(None)


def test_betriebsart_heizen_zaehler_gewinnt_vor_dem_summanden():
    z = modus_strom_zeile({**MARTY, "betriebsart_strom_heizen_kwh": 4.0}, summanden_zaehlen=True)
    assert z.heizen_kwh == 4.0 and z.warmwasser_kwh == 1.0


def test_nur_betriebsart_zaehler_ohne_summanden_wie_bisher():
    daten = {"betriebsart_strom_heizen_kwh": 3.0, "betriebsart_strom_kuehlen_kwh": 2.0}
    assert modus_strom_zeile(daten, summanden_zaehlen=True) == modus_strom_zeile(daten)


def test_ohne_betriebsart_zaehler_bleibt_der_abgeleitete_zweig():
    """``hat_gemessene_betriebsart`` unverändert: Summanden allein machen keinen gemessenen Zweig."""
    z = modus_strom_zeile({"strom_heizen_kwh": 5.0, "strom_warmwasser_kwh": 1.0}, summanden_zaehlen=True)
    assert not z.gemessen and z.heizen_kwh == 0.0


def test_warmwasser_null_ist_eine_messung():
    z = modus_strom_zeile({**MARTY, "strom_warmwasser_kwh": 0.0}, summanden_zaehlen=True)
    assert z.warmwasser_kwh == 0.0 and z.heizen_kwh == 5.0


def test_menge_der_stufe_betriebsart_bleibt_die_summe_der_betriebsart_zaehler():
    """``gemessene_summe_kwh`` ist die Menge der K3-Stufe «betriebsart» — sie ändert sich nicht: mit Kennzeichen
    erreicht man die Stufe nur ohne Achsen, ohne Kennzeichen zählen die Achsen nicht (Randfall alte Summanden)."""
    nur_ba = {"betriebsart_strom_heizen_kwh": 3.0, "betriebsart_strom_kuehlen_kwh": 2.0}
    assert wp_strom_aufteilung(nur_ba, GETRENNT).menge_kwh == pytest.approx(5.0)
    alt = {**nur_ba, "strom_heizen_kwh": 7.0, "strom_warmwasser_kwh": 1.0}
    auf = wp_strom_aufteilung(alt, {"wp_art": "sole_wasser"})
    assert auf.stufe == "betriebsart" and auf.menge_kwh == pytest.approx(5.0)


# ── Tag: beitraege_des_tages / falte_tages_stapel ────────────────────────────


def _summanden():
    return summanden_aus_tageswerten({"wp_strom_heizen_kwh": {"7": 5.0}, "wp_strom_warmwasser_kwh": {"7": 1.0}})


def test_tag_mit_den_zahlen_des_melders():
    """Bis N-766: heizen 0, warmwasser 0, nicht aufgeteilt 6 (der Screenshot)."""
    (b,) = beitraege_des_tages({"7": {"betriebsart_strom_kuehlen_kwh": 0.0}}, {"7": 6.0}, {},
                               {"7": _Inv(GETRENNT)}, TAG, summanden_je_inv=_summanden())
    assert (b.heizen_kwh, b.warmwasser_kwh, b.kuehlen_kwh, b.nicht_aufgeteilt_kwh, b.gemessen) == (5.0, 1.0, 0.0, 0.0, True)
    # Die Felder bleiben Betriebsart-only; die Summanden stehen daneben (eigene Stundenform).
    assert b.felder == {"betriebsart_strom_kuehlen_kwh": 0.0}
    assert b.summanden == {"strom_heizen_kwh": 5.0, "strom_warmwasser_kwh": 1.0}
    stapel = _falte([b])
    assert stapel.hat_gemessen and stapel.heizen_kwh == 5.0 and stapel.warmwasser_kwh == 1.0
    assert stapel.nicht_aufgeteilt_kwh == 0.0


def test_tag_ohne_kennzeichen_oder_ohne_eingang_wie_bisher():
    for inv, summanden in ((_Inv({"wp_art": "sole_wasser"}), _summanden()), (_Inv(GETRENNT), None)):
        stapel = falte_tages_stapel({"7": {"betriebsart_strom_kuehlen_kwh": 0.0}}, {"7": 6.0}, {}, {"7": inv}, TAG,
                                    summanden_je_inv=summanden)
        assert (stapel.heizen_kwh, stapel.warmwasser_kwh, stapel.nicht_aufgeteilt_kwh) == (0.0, 0.0, 6.0)


def test_tag_toleranz_zaehlt_warmwasser_mit():
    """Heizen + Warmwasser + Kühlen über dem Bezug (jenseits der Toleranz): das Gerät passt nicht und trägt nicht bei."""
    summanden = summanden_aus_tageswerten({"wp_strom_heizen_kwh": {"7": 5.0}, "wp_strom_warmwasser_kwh": {"7": 3.0}})
    assert beitraege_des_tages({"7": {"betriebsart_strom_kuehlen_kwh": 0.0}}, {"7": 6.0}, {},
                               {"7": _Inv(GETRENNT)}, TAG, summanden_je_inv=summanden) == []


def test_stunden_verteilen_die_summanden_nach_ihrer_eigenen_form():
    """Σ Stunden ≡ Tag je Segment: Heizen nach der Form des Heizstrom-Zählers, Warmwasser nach seiner."""
    (b,) = beitraege_des_tages({"7": {"betriebsart_strom_kuehlen_kwh": 0.0}}, {"7": 6.0}, {},
                               {"7": _Inv(GETRENNT)}, TAG, summanden_je_inv=_summanden())
    heiz = [1.0 if 6 <= h < 11 else 0.0 for h in range(STUNDEN)]
    ww = [1.0 if h == 18 else 0.0 for h in range(STUNDEN)]
    formen = StundenFormen(
        felder_je_inv={"7": {"betriebsart_strom_kuehlen_kwh": [0.0] * STUNDEN,
                             "strom_heizen_kwh": heiz, "strom_warmwasser_kwh": ww}},
        gesamt_je_inv={"7": [a + c for a, c in zip(heiz, ww)]},
    )
    v = verteile_tages_stapel_auf_stunden([b], formen)
    assert v.ohne_stundenform_kwh == pytest.approx(0.0)
    assert sum(s.heizen_kwh for s in v.stunden) == pytest.approx(5.0)
    assert sum(s.warmwasser_kwh for s in v.stunden) == pytest.approx(1.0)
    assert sum(s.nicht_aufgeteilt_kwh for s in v.stunden) == pytest.approx(0.0)
    assert v.stunden[7].heizen_kwh == pytest.approx(1.0) and v.stunden[18].warmwasser_kwh == pytest.approx(1.0)
    assert v.stunden[18].heizen_kwh == 0.0


# ── Monat: Monats-Fakten über imd_monatsaggregat ─────────────────────────────


async def test_monat_mit_summanden_und_kuehlzaehler(db):
    from backend.models import Anlage, Investition
    from backend.models.investition import InvestitionMonatsdaten
    from backend.services.monats_fakten import lade_monats_fakten

    anlage = Anlage(anlagenname="N-766", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    werte = {}
    for name, parameter in (("getrennt", GETRENNT), ("ohne Kennzeichen", {"wp_art": "sole_wasser"})):
        inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung=f"Vitocal {name}",
                          anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=20000.0, parameter=parameter)
        db.add(inv)
        await db.flush()
        werte[name] = inv.id
    db.add(InvestitionMonatsdaten(investition_id=werte["getrennt"], jahr=2026, monat=9,
                                  verbrauch_daten=dict(MARTY), source_provenance={}))
    db.add(InvestitionMonatsdaten(investition_id=werte["ohne Kennzeichen"], jahr=2026, monat=8,
                                  verbrauch_daten={**MARTY, "stromverbrauch_kwh": 6.0}, source_provenance={}))
    await db.commit()

    (sep,) = await lade_monats_fakten(db, anlage.id, von=(2026, 9), bis=(2026, 9))
    assert sep.wp.modus_strom_heizen_kwh == pytest.approx(5.0)
    assert sep.wp.modus_strom_warmwasser_kwh == pytest.approx(1.0)
    assert sep.wp.modus_strom_kuehlen_kwh == pytest.approx(0.0)
    assert sep.wp.modus_nicht_aufgeteilt_kwh == pytest.approx(0.0)
    assert sep.wp.modus_gemessen

    # Gegenprobe ohne Kennzeichen: die Summanden sind keine Summanden — wie bisher alles «nicht aufgeteilt».
    (aug,) = await lade_monats_fakten(db, anlage.id, von=(2026, 8), bis=(2026, 8))
    assert aug.wp.modus_strom_heizen_kwh == pytest.approx(0.0)
    assert aug.wp.modus_strom_warmwasser_kwh == pytest.approx(0.0)
    assert aug.wp.modus_nicht_aufgeteilt_kwh == pytest.approx(6.0)
