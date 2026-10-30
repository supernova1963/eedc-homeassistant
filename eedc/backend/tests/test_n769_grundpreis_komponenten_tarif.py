"""N-769 — die Stromrechnung trägt die Grundpreise ALLER im Monat gültigen Tarife (30.10.2026).

Bis dahin las jede Sicht nur ``allgemein.grundpreis_euro_monat``: der Grundpreis eines eigenen Wärmepumpen- oder
Wallbox-Tarifs (zweiter Zähler, im Strompreis-Formular erfassbar) ging in keine Zahl ein — die «Stromrechnung» stand um
ihn zu niedrig, Monats- und Jahresergebnis um ihn zu hoch (gemessen: Januar 2025, Kopie r28, WP-Tarif 22 ct / 10 €/Monat
⇒ 126,17 € statt 136,17 €). Seitdem bildet ``monats_fakten.tarif.grundpreis_des_monats`` den Grundpreis an EINER Stelle
(Tarif-Fakten, Cockpit → Monat, ``GET /monatsdaten/{id}``), und ein Komponenten-Tarif zählt nur, wenn ein EIGENER
Datensatz dieser Verwendung gilt — nicht der Rückfall auf den allgemeinen Tarif (sonst doppelt). Der Komponenten-Grundpreis
steht nur in der Stromrechnung, nicht zusätzlich in WP-Kosten/WP-Ersparnis/E-Mob-Ersparnis (Vorentscheid 30.10.2026).

Sprengsatz: ``grundpreis_des_monats`` auf ``allgemein`` allein zurück ⇒ die Proben mit Komponenten-Tarif werden rot.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.monats_fakten import grundpreis_des_monats, tarife_der_monate

JAHR = 2025
NETZ_KWH = 200.0
CENT = 30.0
GP_ALLGEMEIN = 14.0
GP_WP = 10.0
GP_WB = 5.0


async def _anlage(db: AsyncSession, *, wp: bool = False, wallbox: bool = False, wp_bis: date | None = None,
                  netzbezug: float = NETZ_KWH, monate=range(1, 13), jahre=(JAHR,), mit_pv: bool = False) -> Anlage:
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="N-769", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=CENT, einspeiseverguetung_cent_kwh=8.0,
                      grundpreis_euro_monat=GP_ALLGEMEIN))
    if wp:
        db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2024, 1, 1), gueltig_bis=wp_bis,
                          netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=0.0,
                          grundpreis_euro_monat=GP_WP))
    if wallbox:
        db.add(Strompreis(anlage_id=anlage.id, verwendung="wallbox", gueltig_ab=date(2024, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=25.0, einspeiseverguetung_cent_kwh=0.0,
                          grundpreis_euro_monat=GP_WB))
    pv = None
    if mit_pv:
        pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                         anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0)
        db.add(pv)
        await db.flush()
    for j in jahre:
        for m in monate:
            if pv is not None:
                db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m,
                                              verbrauch_daten={"pv_erzeugung_kwh": 400.0}))
            md = Monatsdaten(anlage_id=anlage.id, jahr=j, monat=m, netzbezug_kwh=netzbezug, einspeisung_kwh=50.0)
            db.add(md)
            await db.flush()
            # N-734: Netzbezug und Einspeisung sind EINGETRAGEN (auch eine 0) — so stempelt sie das Formular.
            seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    return anlage


def _arbeitspreis(kwh: float = NETZ_KWH) -> float:
    return kwh * CENT / 100


# ── Die eine Bildungsstelle ─────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("wp, wallbox, summe, aufteilung", [
    (False, False, GP_ALLGEMEIN, None),
    (True, False, GP_ALLGEMEIN + GP_WP, {"allgemein": GP_ALLGEMEIN, "waermepumpe": GP_WP}),
    (False, True, GP_ALLGEMEIN + GP_WB, {"allgemein": GP_ALLGEMEIN, "wallbox": GP_WB}),
    (True, True, GP_ALLGEMEIN + GP_WP + GP_WB, {"allgemein": GP_ALLGEMEIN, "waermepumpe": GP_WP, "wallbox": GP_WB}),
])
async def test_tarif_fakten_tragen_die_summe_aller_gueltigen_tarife(db, wp, wallbox, summe, aufteilung):
    anlage = await _anlage(db, wp=wp, wallbox=wallbox, monate=(3,))
    fakt = (await tarife_der_monate(db, anlage.id, [(JAHR, 3)]))[(JAHR, 3)]
    assert fakt.grundpreis_euro_monat == pytest.approx(summe)

    from backend.api.routes.strompreise import lade_tarife_fuer_anlage
    gp = grundpreis_des_monats(await lade_tarife_fuer_anlage(db, anlage.id, target_date=date(JAHR, 3, 1)))
    assert gp.summe_euro == pytest.approx(summe)
    assert gp.aufteilung == aufteilung


def test_rueckfall_auf_allgemein_zaehlt_nicht_doppelt():
    """Ohne eigenen WP-/Wallbox-Datensatz zeigt die Verwendung auf DENSELBEN allgemeinen Datensatz (Rückfall)."""
    class _T:
        def __init__(self, gp):
            self.grundpreis_euro_monat = gp
    allg = _T(GP_ALLGEMEIN)
    gp = grundpreis_des_monats({"allgemein": allg, "waermepumpe": allg, "wallbox": allg})
    assert gp.summe_euro == pytest.approx(GP_ALLGEMEIN)
    assert gp.aufteilung is None
    # Kein allgemeiner Tarif, nur ein eigener WP-Tarif: dessen Grundpreis allein, und die Aufteilung nennt ihn.
    wp = _T(GP_WP)
    gp = grundpreis_des_monats({"allgemein": None, "waermepumpe": wp, "wallbox": None})
    assert gp.summe_euro == pytest.approx(GP_WP)
    assert gp.aufteilung == {"waermepumpe": GP_WP}
    # Ein eigener Tarif ohne Grundpreis ändert nichts und braucht keine Aufteilung.
    gp = grundpreis_des_monats({"allgemein": allg, "waermepumpe": _T(None), "wallbox": _T(0.0)})
    assert gp.summe_euro == pytest.approx(GP_ALLGEMEIN)
    assert gp.aufteilung is None
    # Kein Tarif: 0.0 (float, wie bisher).
    gp = grundpreis_des_monats({"allgemein": None, "waermepumpe": None, "wallbox": None})
    assert gp.summe_euro == 0.0 and isinstance(gp.summe_euro, float) and gp.aufteilung is None


# ── Cockpit → Monat ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("wp, wallbox, grund", [
    (True, False, GP_ALLGEMEIN + GP_WP),
    (False, True, GP_ALLGEMEIN + GP_WB),
    (True, True, GP_ALLGEMEIN + GP_WP + GP_WB),
])
async def test_monat_stromrechnung_traegt_den_komponenten_grundpreis(db, wp, wallbox, grund):
    anlage = await _anlage(db, wp=wp, wallbox=wallbox, monate=(4,))
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=4, db=db)
    assert res.netzbezug_kosten_euro == pytest.approx(_arbeitspreis() + grund)
    assert res.grundgebuehr_euro == pytest.approx(grund)
    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(_arbeitspreis())
    assert res.grundgebuehr_aufteilung["allgemein"] == pytest.approx(GP_ALLGEMEIN)
    assert sum(res.grundgebuehr_aufteilung.values()) == pytest.approx(grund)


@pytest.mark.asyncio
async def test_abgelaufener_komponenten_tarif_zaehlt_nicht(db):
    """WP-Tarif bis 31.03. — April (Stichtag 01.04.) hat keinen eigenen WP-Tarif mehr ⇒ nur der allgemeine Grundpreis."""
    anlage = await _anlage(db, wp=True, wp_bis=date(JAHR, 3, 31), monate=(3, 4))
    maerz = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=3, db=db)
    april = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=4, db=db)
    assert maerz.grundgebuehr_euro == pytest.approx(GP_ALLGEMEIN + GP_WP)
    assert april.grundgebuehr_euro == pytest.approx(GP_ALLGEMEIN)
    assert april.grundgebuehr_aufteilung is None
    assert april.netzbezug_kosten_euro == pytest.approx(_arbeitspreis() + GP_ALLGEMEIN)


@pytest.mark.asyncio
async def test_ohne_eigenen_komponenten_tarif_bleibt_alles_wie_bisher(db):
    anlage = await _anlage(db, monate=(4,))
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=4, db=db)
    assert res.netzbezug_kosten_euro == pytest.approx(_arbeitspreis() + GP_ALLGEMEIN)
    assert res.grundgebuehr_euro == pytest.approx(GP_ALLGEMEIN)
    assert res.grundgebuehr_aufteilung is None


@pytest.mark.asyncio
async def test_monat_ohne_netzbezug_traegt_alle_grundpreise(db):
    """BERECHNUNGEN §3.2: ein Monat mit 0 kWh Bezug trägt die Grundgebühr als Stromrechnung — jetzt alle."""
    anlage = await _anlage(db, wp=True, wallbox=True, netzbezug=0.0, monate=(6,))
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=6, db=db)
    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(0.0)
    assert res.netzbezug_kosten_euro == pytest.approx(GP_ALLGEMEIN + GP_WP + GP_WB)


@pytest.mark.asyncio
async def test_komponenten_grundpreis_nur_in_der_stromrechnung(db):
    """Vorentscheid 30.10.2026: der WP-Grundpreis steht NUR in der Stromrechnung — Ergebnis genau −10 €, Netto-Ertrag
    und alle Ersparnisse unverändert (sonst stünde er im Ergebnis doppelt, Muster N-606)."""
    from backend.models import Strompreis as SP
    from sqlalchemy import select, update

    ohne = await _anlage(db, wp=True, monate=(4,), mit_pv=True)
    await db.execute(update(SP).where(SP.anlage_id == ohne.id, SP.verwendung == "waermepumpe")
                     .values(grundpreis_euro_monat=0.0))
    await db.commit()
    mit = await _anlage(db, wp=True, monate=(4,), mit_pv=True)
    assert (await db.execute(select(SP.grundpreis_euro_monat).where(
        SP.anlage_id == mit.id, SP.verwendung == "waermepumpe"))).scalar_one() == GP_WP
    a = (await get_aktueller_monat(anlage_id=ohne.id, jahr=JAHR, monat=4, db=db)).model_dump()
    b = (await get_aktueller_monat(anlage_id=mit.id, jahr=JAHR, monat=4, db=db)).model_dump()
    assert b["netzbezug_kosten_euro"] - a["netzbezug_kosten_euro"] == pytest.approx(GP_WP)
    assert a["ergebnis_euro"] is not None and a["netto_ertrag_euro"] is not None
    assert b["ergebnis_euro"] - a["ergebnis_euro"] == pytest.approx(-GP_WP)
    assert b["ergebnis_vor_betriebskosten_euro"] - a["ergebnis_vor_betriebskosten_euro"] == pytest.approx(-GP_WP)
    gleich = {"netto_ertrag_euro", "ev_ersparnis_euro", "wp_ersparnis_euro", "emob_ersparnis_euro",
              "einspeise_erloes_euro", "netzbezug_arbeitspreis_kosten_euro", "betriebskosten_anteilig_euro"}
    for k in gleich:
        assert a[k] == b[k], k
    # `aktualisiert_um` (Uhr) und `feld_quellen` (trägt die Investitions-IDs der zwei Anlagen) sind keine Geldgrößen.
    erwartet_anders = {"anlage_id", "anlage_name", "aktualisiert_um", "feld_quellen", "netzbezug_kosten_euro", "grundgebuehr_euro", "grundgebuehr_aufteilung",
                       "ergebnis_euro", "ergebnis_vor_betriebskosten_euro", "ergebnis_herleitung"}
    sonst = sorted(k for k in a if a[k] != b[k] and k not in erwartet_anders)
    assert sonst == [], sonst


# ── Vorjahr, Jahr, Übersicht, Tabelle, Monatsdetail ─────────────────────────

@pytest.mark.asyncio
async def test_vorjahresmonat_folgt_derselben_regel(db):
    anlage = await _anlage(db, wp=True, monate=(4,), jahre=(JAHR - 1, JAHR))
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=4, db=db)
    assert res.vorjahr["netzbezug_kosten_euro"] == pytest.approx(_arbeitspreis() + GP_ALLGEMEIN + GP_WP)


@pytest.mark.asyncio
async def test_jahr_uebersicht_und_tabelle_sind_die_summe_der_monate(db):
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    # WP-Tarif nur bis 30.06. ⇒ Januar–Juni mit, Juli–Dezember ohne WP-Grundpreis (die Aufteilung des Jahres muss
    # die Monate ohne Aufteilung als «allgemein» mitzählen).
    anlage = await _anlage(db, wp=True, wp_bis=date(JAHR, 6, 30), mit_pv=True)
    monate = [await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=m, db=db) for m in range(1, 13)]
    grund_soll = 12 * GP_ALLGEMEIN + 6 * GP_WP
    assert sum(d.grundgebuehr_euro for d in monate) == pytest.approx(grund_soll)
    kosten_soll = 12 * _arbeitspreis() + grund_soll
    assert sum(d.netzbezug_kosten_euro for d in monate) == pytest.approx(kosten_soll)

    jahr = await get_cockpit_jahr(anlage_id=anlage.id, jahr=JAHR, db=db)
    kopf = jahr["kopf"]
    assert kopf["netzbezug_kosten_euro"] == pytest.approx(kosten_soll)
    assert kopf["grundgebuehr_euro"] == pytest.approx(grund_soll)
    assert kopf["grundgebuehr_aufteilung"] == pytest.approx({"allgemein": 12 * GP_ALLGEMEIN, "waermepumpe": 6 * GP_WP})
    assert list(kopf["grundgebuehr_aufteilung"]) == ["allgemein", "waermepumpe"]

    uebersicht = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=JAHR, db=db)
    assert uebersicht.netzbezug_kosten_euro == pytest.approx(kosten_soll)

    reihe = [z if isinstance(z, dict) else z.model_dump()
             for z in await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=JAHR, db=db)]
    assert sum(z["netzbezug_kosten_euro"] for z in reihe) == pytest.approx(kosten_soll)
    assert {z["monat"]: z["netzbezug_kosten_euro"] for z in reihe}[3] == pytest.approx(_arbeitspreis() + GP_ALLGEMEIN + GP_WP)


@pytest.mark.asyncio
async def test_komponenten_zeitreihe_traegt_die_summe(db):
    """*Komponenten*-Zeitreihe (`cockpit/komponenten.py`) liest den Grundpreis aus den Tarif-Fakten."""
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe

    anlage = await _anlage(db, wp=True, wallbox=True, monate=(4,))
    sp = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Sp", anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add(sp)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=JAHR, monat=4,
                                  verbrauch_daten={"ladung_kwh": 100, "entladung_kwh": 90}))
    await db.commit()
    resp = await get_komponenten_zeitreihe(anlage_id=anlage.id, jahr=JAHR, db=db)
    m = next(x for x in resp.monatswerte if (x.jahr, x.monat) == (JAHR, 4))
    assert m.netzbezug_kosten_euro == pytest.approx(_arbeitspreis() + GP_ALLGEMEIN + GP_WP + GP_WB)


@pytest.mark.asyncio
async def test_jahr_ohne_komponenten_tarif_hat_keine_aufteilung(db):
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr

    anlage = await _anlage(db, monate=(1, 2, 3))
    kopf = (await get_cockpit_jahr(anlage_id=anlage.id, jahr=JAHR, db=db))["kopf"]
    assert kopf["grundgebuehr_euro"] == pytest.approx(3 * GP_ALLGEMEIN)
    assert kopf["grundgebuehr_aufteilung"] is None


@pytest.mark.asyncio
async def test_monatsdetail_kennzahlen_tragen_die_summe(db):
    """``GET /monatsdaten/{id}`` (``berechne_monatskennzahlen``) — dieselbe Bildungsstelle."""
    from backend.api.routes.monatsdaten import get_monatsdaten
    from sqlalchemy import select

    anlage = await _anlage(db, wp=True, wallbox=True, monate=(5,))
    md_id = (await db.execute(select(Monatsdaten.id).where(Monatsdaten.anlage_id == anlage.id))).scalar_one()
    res = await get_monatsdaten(md_id, db=db)
    k = res.kennzahlen if hasattr(res, "kennzahlen") else res["kennzahlen"]
    kosten = k.netzbezug_kosten_euro if hasattr(k, "netzbezug_kosten_euro") else k["netzbezug_kosten_euro"]
    assert kosten == pytest.approx(_arbeitspreis() + GP_ALLGEMEIN + GP_WP + GP_WB)
