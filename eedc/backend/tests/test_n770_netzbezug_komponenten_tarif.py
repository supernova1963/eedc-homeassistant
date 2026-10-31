"""N-770 / N-771 — Netzbezug zum Komponenten-Tarif als Messgröße (Bauplan `bauplan-n770-wp-tarif-netzbezug.md`, E1–E2).

Je Monat: WP-Strom **S** = PV-Anteil **P** + Netzanteil **N**; Haushaltstarif **H**, WP-Tarif **W**. Bis dahin rechnete
die Stromrechnung den ganzen Netzbezug zu H (zu hoch um N·(H−W), N-770) und die Eigenverbrauchs-Ersparnis den ganzen
Eigenverbrauch zu H (zu hoch um P·(H−W), N-767). Mit dem optionalen Feld «Netzbezug zum WP-Tarif» (``netzbezug_eigener_
tarif_kwh``) und eigenem WP-Tarif: Stromrechnung = (Netzbezug − N) × H + N × W + Grundpreise; EV-Ersparnis =
(EV − P) × H + P × W mit P = S − N. Dieselbe Bauform an der Wallbox (F8, N-771): «Netzbezug zum Wallbox-Tarif» in der
Stromrechnung; die E-Mob-Ersparnis bleibt unverändert. Ohne eigenen Tarif oder ohne Feld bleibt alles bitgleich.

Zahlenbeispiel Bauplan §1 (Januar 2025 der Kopie r28): S = 426,7 kWh, N = 256 kWh, Netzbezug 373,9 kWh, H = 30 ct,
W = 22 ct, Grundpreise 14 + 10 € ⇒ Stromrechnung 115,69 € (statt 136,17 €).

Sprengsätze (im Bericht gefahren): ``komponenten_anteile`` gibt immer ``None`` zurück (N ignoriert) ⇒ rot;
``bewerte_eigenverbrauch`` ignoriert den WP-Anteil (P nicht zu W) ⇒ die EV-Proben rot.

Schwesterdateien: test_n770_e3_tag_stunde.py (Tag/Stunde, E3), test_n770_e4_prognose_roi.py,
test_n771_f11_wallbox_netzladung.py, test_n767_wp_eigener_tarif.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.core.berechnungen import berechne_netzbezug_kosten, bewerte_eigenverbrauch, klemme_netzanteil
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401 — Tabelle für die Datenquellen-Route
from backend.services.monats_fakten import (
    TarifFakten,
    komponenten_anteile,
    lade_monats_fakten,
)

JAHR = 2025
NETZ = 373.9
H = 30.0
W_WP = 22.0
W_WB = 20.0
GP_ALLG = 14.0
GP_WP = 10.0
GP_WB = 8.0
PV = 400.0
EINSP = 50.0
EV = PV - EINSP          # kein Speicher: Eigenverbrauch = PV − Einspeisung
S = 426.7
N = 256.0
P = S - N                # 170,7


async def _anlage(db: AsyncSession, *, wp_tarif: bool = True, wb_tarif: bool = False, wp: tuple = ((S, N),),
                  wallbox: tuple = (), monate=(1,), jahre=(JAHR,), netzbezug: float = NETZ) -> Anlage:
    """Anlage mit PV, Netzbezug und je ``wp``-Eintrag einer Wärmepumpe ``(Strom, N oder None)``, je ``wallbox``-Eintrag
    einer Wallbox ``(Ladung, N oder None)``."""
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="N-770", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=H, einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=GP_ALLG))
    if wp_tarif:
        db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2024, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=W_WP, einspeiseverguetung_cent_kwh=0.0,
                          grundpreis_euro_monat=GP_WP))
    if wb_tarif:
        db.add(Strompreis(anlage_id=anlage.id, verwendung="wallbox", gueltig_ab=date(2024, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=W_WB, einspeiseverguetung_cent_kwh=0.0,
                          grundpreis_euro_monat=GP_WB))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    geraete = []
    for i, (strom, n) in enumerate(wp):
        inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung=f"WP{i}", anschaffungsdatum=date(2024, 1, 1),
                          parameter={"effizienz_modus": "gesamt_jaz", "jaz": 3.5})
        db.add(inv)
        geraete.append((inv, {"stromverbrauch_kwh": strom, "heizenergie_kwh": strom * 3.5}, n))
    for i, (ladung, n) in enumerate(wallbox):
        inv = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung=f"WB{i}", anschaffungsdatum=date(2024, 1, 1))
        db.add(inv)
        geraete.append((inv, {"ladung_kwh": ladung}, n))
    await db.flush()
    for j in jahre:
        for m in monate:
            db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m, verbrauch_daten={"pv_erzeugung_kwh": PV}))
            for inv, daten, n in geraete:
                vd = dict(daten)
                if n is not None:
                    vd["netzbezug_eigener_tarif_kwh"] = n
                db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=j, monat=m, verbrauch_daten=vd))
            md = Monatsdaten(anlage_id=anlage.id, jahr=j, monat=m, netzbezug_kwh=netzbezug, einspeisung_kwh=EINSP)
            db.add(md)
            await db.flush()
            seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    return anlage


def _soll_stromrechnung(n_wp: float = 0.0, n_wb: float = 0.0, grund: float = GP_ALLG + GP_WP, netz: float = NETZ) -> float:
    return (netz - n_wp - n_wb) * H / 100 + n_wp * W_WP / 100 + n_wb * W_WB / 100 + grund


def _soll_ev(p: float = 0.0) -> float:
    return (EV - p) * H / 100 + p * W_WP / 100


# ── Layer ───────────────────────────────────────────────────────────────────

def test_layer_ohne_anteile_bitgleich_mit_anteilen_zwei_preise():
    for kwh, cent, gp in [(373.9, 30.0, 24.0), (0.1, 33.3, 0.0), (1234.56, 27.77, 13.5)]:
        assert berechne_netzbezug_kosten(kwh, cent, gp) == kwh * cent / 100 + gp
        assert berechne_netzbezug_kosten(kwh, cent, gp, ()) == kwh * cent / 100 + gp
    assert berechne_netzbezug_kosten(NETZ, H, 24.0, [(N, W_WP)]) == pytest.approx(115.69, abs=1e-9)
    assert berechne_netzbezug_kosten(NETZ, H, 0.0, [(N, W_WP), (50.0, W_WB)]) == pytest.approx(
        (NETZ - N - 50) * 0.3 + N * 0.22 + 50 * 0.2)


def test_klemme_netzanteil():
    assert klemme_netzanteil(256.0, 426.7, 373.9) == 256.0
    assert klemme_netzanteil(500.0, 426.7, 600.0) == 426.7      # N > S
    assert klemme_netzanteil(256.0, 426.7, 100.0) == 100.0      # N > Netzbezug
    assert klemme_netzanteil(-5.0, 426.7, 373.9) == 0.0


def test_bewerte_eigenverbrauch():
    assert bewerte_eigenverbrauch(EV, H).euro == EV * H / 100
    assert bewerte_eigenverbrauch(EV, H, None, W_WP).euro == EV * H / 100
    b = bewerte_eigenverbrauch(EV, H, P, W_WP)
    assert b.euro == pytest.approx(_soll_ev(P)) and b.wp_tarif_kwh == pytest.approx(P)
    # P über dem Eigenverbrauch wird auf ihn begrenzt.
    b = bewerte_eigenverbrauch(100.0, H, 170.7, W_WP)
    assert b.euro == pytest.approx(100 * W_WP / 100) and b.wp_tarif_kwh == 100.0


# ── Die Bildungsstelle in den Tarif-Fakten ──────────────────────────────────

def test_komponenten_anteile_nur_mit_eigenem_tarif_und_messung():
    mit_wp = TarifFakten(netzbezug_preis_cent=H, wp_preis_cent=W_WP, wp_eigener_tarif=True,
                         wallbox_preis_effektiv_cent=W_WB, wallbox_eigener_tarif=True)
    ohne = TarifFakten(netzbezug_preis_cent=H, wp_preis_cent=H)
    assert komponenten_anteile(NETZ, ohne, wp_strom_kwh=S, wp_netz_eigener_tarif_kwh=N) is None
    assert komponenten_anteile(NETZ, mit_wp, wp_strom_kwh=S, wp_netz_eigener_tarif_kwh=None) is None
    assert komponenten_anteile(None, mit_wp, wp_strom_kwh=S, wp_netz_eigener_tarif_kwh=N) is None
    a = komponenten_anteile(NETZ, mit_wp, wp_strom_kwh=S, wp_netz_eigener_tarif_kwh=N)
    assert [(x.verwendung, x.kwh, x.cent, x.geklemmt) for x in a.netz] == [("waermepumpe", N, W_WP, False)]
    assert a.wp_pv_kwh == pytest.approx(P) and a.wp_cent == W_WP
    # F7: N > Netzbezug ⇒ auf den Netzbezug geklemmt, P = S − Netzbezug; die Wallbox bekommt den Rest (0).
    a = komponenten_anteile(100.0, mit_wp, wp_strom_kwh=S, wp_netz_eigener_tarif_kwh=N,
                            wallbox_ladung_kwh=80.0, wallbox_netz_eigener_tarif_kwh=40.0)
    assert [(x.verwendung, x.kwh, x.geklemmt) for x in a.netz] == [("waermepumpe", 100.0, True), ("wallbox", 0.0, True)]
    assert a.wp_pv_kwh == pytest.approx(S - 100.0)
    # F7: N > S ⇒ auf S geklemmt, P = 0.
    a = komponenten_anteile(NETZ, mit_wp, wp_strom_kwh=200.0, wp_netz_eigener_tarif_kwh=250.0)
    assert a.netz[0].kwh == 200.0 and a.netz[0].geklemmt and a.wp_pv_kwh == 0.0
    # Wallbox allein: kein WP-Anteil an der Ersparnis.
    a = komponenten_anteile(NETZ, mit_wp, wallbox_ladung_kwh=200.0, wallbox_netz_eigener_tarif_kwh=120.0)
    assert [(x.verwendung, x.kwh, x.cent) for x in a.netz] == [("wallbox", 120.0, W_WB)]
    assert a.wp_pv_kwh is None


@pytest.mark.asyncio
@pytest.mark.parametrize("wp, soll", [
    (((S, N),), N),
    (((S, None),), None),
    (((300.0, 200.0), (126.7, 56.0)), 256.0),
    (((300.0, 200.0), (126.7, None)), None),      # F3: ein Gerät mit Strom > 0 ohne Feld ⇒ nicht gemessen
    (((300.0, 200.0), (0.0, None)), 200.0),       # … ein stillstehendes Gerät ohne Feld stört nicht
])
async def test_fakten_tragen_n_je_typ_f3(db, wp, soll):
    anlage = await _anlage(db, wp=wp)
    f = (await lade_monats_fakten(db, anlage.id, von=(JAHR, 1), bis=(JAHR, 1)))[0]
    assert f.wp.netz_eigener_tarif_kwh == (pytest.approx(soll) if soll is not None else None)
    assert f.tarif.wp_eigener_tarif is True and f.tarif.wallbox_eigener_tarif is False


@pytest.mark.asyncio
async def test_fakten_wallbox_f3(db):
    anlage = await _anlage(db, wp=(), wallbox=((200.0, 120.0), (50.0, None)), wb_tarif=True)
    f = (await lade_monats_fakten(db, anlage.id, von=(JAHR, 1), bis=(JAHR, 1)))[0]
    assert f.emob.wallbox_netz_eigener_tarif_kwh is None and f.emob.wallbox_ladung_alle_kwh == pytest.approx(250.0)
    anlage = await _anlage(db, wp=(), wallbox=((200.0, 120.0),), wb_tarif=True)
    f = (await lade_monats_fakten(db, anlage.id, von=(JAHR, 1), bis=(JAHR, 1)))[0]
    assert f.emob.wallbox_netz_eigener_tarif_kwh == pytest.approx(120.0)


# ── Cockpit → Monat ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monat_zahlenbeispiel_bauplan(db):
    anlage = await _anlage(db)
    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=1, db=db)
    assert r.netzbezug_kosten_euro == pytest.approx(115.69, abs=0.005)
    assert r.netzbezug_kosten_euro == pytest.approx(_soll_stromrechnung(N), abs=0.005)
    assert r.netzbezug_arbeitspreis_kosten_euro == pytest.approx(_soll_stromrechnung(N, grund=0.0), abs=0.005)
    assert r.ev_ersparnis_euro == pytest.approx(_soll_ev(P), abs=0.005)
    assert r.netzbezug_anteile == [{"verwendung": "waermepumpe", "kwh": N, "cent": W_WP, "euro": 56.32,
                                    "gemessen_kwh": N, "geklemmt": False}]
    assert r.ev_ersparnis_wp_tarif_kwh == pytest.approx(P) and r.ev_ersparnis_wp_tarif_cent == W_WP


@pytest.mark.asyncio
async def test_monat_ohne_feld_und_ohne_eigenen_tarif_bitgleich(db):
    """Ohne Feld = wie bisher; ein Feld ohne eigenen WP-Tarif ändert nichts (H = W, Bauplan §1)."""
    weg = {"anlage_id", "anlage_name", "aktualisiert_um", "investitionen_financials", "komponenten_geraete", "quellen",
           "feld_quellen", "wp_geraete"}
    ohne_feld = (await get_aktueller_monat(anlage_id=(await _anlage(db, wp=((S, None),))).id, jahr=JAHR, monat=1, db=db))
    assert ohne_feld.netzbezug_kosten_euro == pytest.approx(_soll_stromrechnung(), abs=0.005)
    assert ohne_feld.ev_ersparnis_euro == pytest.approx(_soll_ev(), abs=0.005)
    assert ohne_feld.netzbezug_anteile is None and ohne_feld.ev_ersparnis_wp_tarif_kwh is None
    a = (await get_aktueller_monat(anlage_id=(await _anlage(db, wp_tarif=False, wp=((S, None),))).id,
                                   jahr=JAHR, monat=1, db=db)).model_dump()
    b = (await get_aktueller_monat(anlage_id=(await _anlage(db, wp_tarif=False)).id, jahr=JAHR, monat=1, db=db)).model_dump()
    assert {k: v for k, v in a.items() if k not in weg} == {k: v for k, v in b.items() if k not in weg}


@pytest.mark.asyncio
async def test_monat_klemme_herleitung_sagt_es(db):
    anlage = await _anlage(db, netzbezug=100.0)
    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=1, db=db)
    assert r.netzbezug_anteile[0]["kwh"] == 100.0 and r.netzbezug_anteile[0]["geklemmt"] is True
    assert r.netzbezug_anteile[0]["gemessen_kwh"] == N
    assert r.netzbezug_kosten_euro == pytest.approx(_soll_stromrechnung(100.0, netz=100.0), abs=0.005)
    assert r.ev_ersparnis_wp_tarif_kwh == pytest.approx(S - 100.0)


@pytest.mark.asyncio
async def test_monat_wallbox_stromrechnung_ohne_e_auto_emob_gleich(db):
    """Ohne E-Auto keine E-Mob-Ersparnis; die Netzladung aus dem Feld (F11, E4) prüft ``test_n771_f11_…``."""
    mit = await get_aktueller_monat(anlage_id=(await _anlage(db, wp=(), wallbox=((200.0, 120.0),), wb_tarif=True,
                                                             wp_tarif=False)).id, jahr=JAHR, monat=1, db=db)
    ohne = await get_aktueller_monat(anlage_id=(await _anlage(db, wp=(), wallbox=((200.0, None),), wb_tarif=True,
                                                              wp_tarif=False)).id, jahr=JAHR, monat=1, db=db)
    grund = GP_ALLG + GP_WB
    assert mit.netzbezug_kosten_euro == pytest.approx(_soll_stromrechnung(n_wb=120.0, grund=grund), abs=0.005)
    assert ohne.netzbezug_kosten_euro == pytest.approx(_soll_stromrechnung(grund=grund), abs=0.005)
    assert mit.emob_ersparnis_euro == ohne.emob_ersparnis_euro
    assert mit.ev_ersparnis_euro == ohne.ev_ersparnis_euro
    assert mit.ev_ersparnis_wp_tarif_kwh is None


@pytest.mark.asyncio
async def test_monat_wp_kosten_und_wp_ersparnis_unveraendert(db):
    """P9: die WP-Kosten bleiben S × W — nur Stromrechnung und EV-Ersparnis tragen die Anteile."""
    mit = await get_aktueller_monat(anlage_id=(await _anlage(db)).id, jahr=JAHR, monat=1, db=db)
    ohne = await get_aktueller_monat(anlage_id=(await _anlage(db, wp=((S, None),))).id, jahr=JAHR, monat=1, db=db)
    assert mit.wp_ersparnis_euro == ohne.wp_ersparnis_euro
    assert mit.emob_ersparnis_euro == ohne.emob_ersparnis_euro
    # Ergebnis: + N·(H−W) Stromrechnung, − P·(H−W) Ersparnis.
    assert mit.ergebnis_euro - ohne.ergebnis_euro == pytest.approx((N - P) * (H - W_WP) / 100, abs=0.02)


# ── Vorjahr, Jahr, Übersicht, Tabelle, Komponenten, Monatsdetail ────────────

@pytest.mark.asyncio
async def test_vorjahresmonat_folgt_derselben_regel(db):
    anlage = await _anlage(db, jahre=(JAHR - 1, JAHR))
    r = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=1, db=db)
    assert r.vorjahr["netzbezug_kosten_euro"] == pytest.approx(_soll_stromrechnung(N), abs=0.005)
    assert r.vorjahr["ev_ersparnis_euro"] == pytest.approx(_soll_ev(P), abs=0.005)


@pytest.mark.asyncio
async def test_jahr_uebersicht_tabelle_komponenten_monatsdetail_sind_dieselbe_zahl(db):
    from sqlalchemy import select
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import get_monatsdaten, list_monatsdaten_aggregiert

    anlage = await _anlage(db, monate=(1, 2, 3))
    monate = [await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=m, db=db) for m in (1, 2, 3)]
    kosten = sum(d.netzbezug_kosten_euro for d in monate)
    ev = sum(d.ev_ersparnis_euro for d in monate)
    assert kosten == pytest.approx(3 * _soll_stromrechnung(N), abs=0.02)
    assert ev == pytest.approx(3 * _soll_ev(P), abs=0.02)

    kopf = (await get_cockpit_jahr(anlage_id=anlage.id, jahr=JAHR, db=db))["kopf"]
    assert kopf["netzbezug_kosten_euro"] == pytest.approx(kosten, abs=0.02)
    assert kopf["ev_ersparnis_euro"] == pytest.approx(ev, abs=0.02)
    assert kopf["netzbezug_anteile"][0]["kwh"] == pytest.approx(3 * N)
    assert kopf["netzbezug_anteile"][0]["cent"] == pytest.approx(W_WP)
    assert kopf["ev_ersparnis_wp_tarif_kwh"] == pytest.approx(3 * P)

    ue = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=JAHR, db=db)
    assert ue.netzbezug_kosten_euro == pytest.approx(kosten, abs=0.02)
    assert ue.ev_ersparnis_euro == pytest.approx(ev, abs=0.02)

    reihe = [z if isinstance(z, dict) else z.model_dump()
             for z in await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=JAHR, db=db)]
    assert sum(z["netzbezug_kosten_euro"] for z in reihe) == pytest.approx(kosten, abs=0.02)

    zr = await get_komponenten_zeitreihe(anlage_id=anlage.id, jahr=JAHR, db=db)
    jan = next(x for x in zr.monatswerte if (x.jahr, x.monat) == (JAHR, 1))
    assert jan.netzbezug_kosten_euro == pytest.approx(_soll_stromrechnung(N), abs=0.005)

    md_id = (await db.execute(select(Monatsdaten.id).where(
        Monatsdaten.anlage_id == anlage.id, Monatsdaten.monat == 1))).scalar_one()
    k = (await get_monatsdaten(md_id, db=db)).kennzahlen
    assert k.netzbezug_kosten_euro == pytest.approx(_soll_stromrechnung(N), abs=0.005)
    assert k.eigenverbrauch_ersparnis_euro == pytest.approx(_soll_ev(P), abs=0.005)


# ── E1: Sichtbarkeit (F1) und Registry ─────────────────────────────────────

def test_feld_im_monatsabschluss_nur_mit_eigenem_tarif():
    from backend.core.field_definitions import get_felder_fuer_investition

    def hat(typ, eigene, belegt=None):
        return "netzbezug_eigener_tarif_kwh" in {
            f["feld"] for f in get_felder_fuer_investition(typ, {}, eigene_tarife=eigene, belegte_felder=belegt)}

    for typ, verw in (("waermepumpe", "waermepumpe"), ("wallbox", "wallbox")):
        assert hat(typ, None)                     # Import/CSV: kein Filter
        assert hat(typ, {verw})
        assert not hat(typ, set())
        assert hat(typ, set(), {"netzbezug_eigener_tarif_kwh"})   # R1: mit Beleg sichtbar


def test_registry_teilmenge_ohne_bilanzbeitrag_und_ohne_mengenart():
    from backend.core.field_definitions.karten import _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG, wp_menge
    from backend.services.snapshot.keys import KUMULATIVE_ZAEHLER_FELDER

    assert ("waermepumpe", "netzbezug_eigener_tarif_kwh") in _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG
    assert ("wallbox", "netzbezug_eigener_tarif_kwh") in _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG
    assert wp_menge("netzbezug_eigener_tarif_kwh") is None
    # MQTT-Inbound/Snapshot über die abgeleitete Zählerliste — ohne Sonderzeile.
    assert "netzbezug_eigener_tarif_kwh" in KUMULATIVE_ZAEHLER_FELDER["waermepumpe"]
    assert "netzbezug_eigener_tarif_kwh" in KUMULATIVE_ZAEHLER_FELDER["wallbox"]


@pytest.mark.asyncio
@pytest.mark.parametrize("typ, tarif", [("waermepumpe", False), ("waermepumpe", True), ("wallbox", False), ("wallbox", True)])
async def test_datenquellen_feld_erste_reihe_nur_mit_eigenem_tarif(db, typ, tarif):
    """F1: mit eigenem Tarif in der ersten Reihe (WP: Block «Gerät gesamt»), sonst «Weitere Größen erfassen»."""
    from backend.api.routes.datenquellen import get_datenquellen_felder

    if typ == "waermepumpe":
        anlage = await _anlage(db, wp_tarif=tarif)
    else:
        anlage = await _anlage(db, wp_tarif=False, wb_tarif=tarif, wp=(), wallbox=((200.0, None),))
    res = await get_datenquellen_felder(anlage.id, db=db)
    gruppen = res["gruppen"] if isinstance(res, dict) else res.gruppen
    felder = [f for g in gruppen if g["typ"] == typ for f in g["felder"]]
    feld = next(f for f in felder if f["feld"] == "netzbezug_eigener_tarif_kwh")
    assert feld["erweitert"] is (not tarif)
    if typ == "waermepumpe":
        assert feld["betriebsart"] == "geraet" and feld["menge"] is None
