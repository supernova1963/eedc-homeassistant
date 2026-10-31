"""N-770 / N-771 Etappe E6 (Auftrag ``auftrag-n770-e6-2026-10-31.md``) — Wallbox-Reste und gemeinsamer Zähler WP + Wallbox.

* **Rest 1 (N-771):** im **Zuordnungsmonat** des Felds «Netzbezug zum Wallbox-Tarif» (sein Kanal beginnt im Monat, F10)
  gilt das Feld auch an der Wallbox-Zeile nicht — es greift die bisherige Regel (evcc-Wert bzw. Gesamt − PV, danach die
  Tagesquote). Je Gerät; die Auskunft kennt ``kanal/netzanteil_leser`` und reist an der Zeile
  (``reader.ZeileImZuordnungsmonat``) bis ``reader.netzladung_des_zaehlers``.
* **Rest 2 (N-771):** im laufenden Monat ohne Abschluss bekommt die Wallbox ihren Anteil zum Wallbox-Tarif aus den
  Kanal-Zeilen der E-Mob-Gruppe (``finanzen.komponenten_anteile_des_monats``), Klemme wie im Monat.
* **F12 (F12a = A):** Tarif-Verwendung ``waermepumpe_wallbox`` — ``waermepumpe`` und ``wallbox`` zeigen auf denselben
  Datensatz; das Feld an der WP trägt N_g; Stromrechnung (Netzbezug − N_g) × H + N_g × W_g + Grundpreise (W_g einmal);
  N_wb = Netzladung der Wallbox-Zeilen nach bisheriger Regel auf [0, min(L_wb, N_g)], N_wp = N_g − N_wb auf [0, S_wp],
  P_wp = S_wp − N_wp zum Tarif W_g. Tag: Stunden-N_g aus dem WP-Kanal, die EV-Ersparnis des Tages teilt nicht (benannte
  Grenze analog F9, Auftrag §3.4).

Sprengsätze (im Bericht gefahren, zurückgesetzt): S-R1 ``mit_zuordnungsauskunft`` gibt die Zeile unverändert zurück ⇒
Rest-1-Proben rot; S-R2 ``_wallbox_aus_kanal`` liefert ``None`` ⇒ Rest-2-Proben rot; S-F12 ``komponenten_tarif_gemeinsam``
liefert ``False`` ⇒ F12-Proben rot.

Schwesterdateien: test_n771_f11_wallbox_netzladung.py (F11), test_n770_e3_tag_stunde.py (Tag/Stunde, F10),
test_n770_netzbezug_komponenten_tarif.py (Monat E1–E2), test_n767_wp_eigener_tarif.py (Daten-Checker),
test_n769_grundpreis_komponenten_tarif.py (Grundpreis).
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.strompreise import tarife_zum_stichtag
from backend.core.field_definitions.reader import (
    ZeileImZuordnungsmonat,
    get_emob_pv_netz_kwh,
    kopie_der_zeile,
    misst_netz_zaehler,
    netzladung_des_zaehlers,
)
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.daten_checker import DatenChecker
from backend.services.energie_profil.tage_werte import baue_tage_werte
from backend.services.monats_fakten import TarifFakten, komponenten_anteile, lade_monats_fakten
from backend.services.monats_fakten.tarif import (
    eigene_tarif_verwendungen,
    grundpreis_des_monats,
    komponenten_tarif_gemeinsam,
    tarif_verwendungen_der_flaeche,
)

FELD = "netzbezug_eigener_tarif_kwh"
J = 2025


def _fakt(fakten, j, m):
    return next(f for f in fakten if (f.jahr, f.monat) == (j, m))


async def _kanal(db, anlage_id: int, inv_id: int, ab: datetime, bis: datetime, je_stunde: float = 0.1) -> None:
    """Kanal des Felds ``inv:<id>:netzbezug_eigener_tarif_kwh`` von ``ab`` (erste Zeile) bis ``bis`` (stündlich)."""
    k = Kanal(anlage_id=anlage_id, key=f"inv:{inv_id}:{FELD}", einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(ab.timestamp()), familie="spiegel", offset=0.0))
    summe, t = 0.0, ab
    while t < bis:
        summe += je_stunde
        db.add(KanalStatistik(kanal_id=k.id, start_ts=int(t.timestamp()), sum=summe, familie="spiegel"))
        t += timedelta(hours=1)


# ── Rest 1 — Zeile ─────────────────────────────────────────────────────────────


def test_zeile_im_zuordnungsmonat_traegt_die_bisherige_regel():
    zeile = {"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0, "ladung_netz_kwh": 50.0, FELD: 30.0}
    assert netzladung_des_zaehlers(zeile) == (170.0, 30.0)
    z = ZeileImZuordnungsmonat(zeile)
    assert z == zeile and netzladung_des_zaehlers(z) is None and not misst_netz_zaehler(z)
    assert get_emob_pv_netz_kwh(z) == (150.0, 50.0)                       # evcc-Wert
    assert get_emob_pv_netz_kwh(ZeileImZuordnungsmonat({"ladung_kwh": 200.0, FELD: 30.0})) == (0.0, 200.0)  # Gesamt − PV
    assert netzladung_des_zaehlers(zeile, zuordnungsmonat=True) is None    # die Auskunft als Parameter
    assert netzladung_des_zaehlers(z, zuordnungsmonat=False) == (170.0, 30.0)
    kopie = kopie_der_zeile(z)
    kopie["ladung_pv_kwh"] = 1.0
    assert isinstance(kopie, ZeileImZuordnungsmonat) and z["ladung_pv_kwh"] == 150.0


async def _wb_anlage(db, *, evcc: bool, kanal_ab: datetime | None, auto_eigen: bool = False) -> Anlage:
    """Wallbox-Tarif 20 ct; Wallbox Jan/Feb 2025 je 200 kWh (evcc 150/50 oder ohne Aufteilung), Feld 30 (Jan, Teilwert)
    und 120 (Feb); Kanal des Felds ab ``kanal_ab`` ⇒ Zuordnungsmonat Jan, Feb voll gedeckt."""
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="N-771 E6 Rest 1", leistung_kwp=10.0)
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
    for m, n in ((1, 30.0), (2, 120.0)):
        wb_daten = {"ladung_kwh": 200.0, FELD: n}
        if evcc:
            wb_daten |= {"ladung_pv_kwh": 150.0, "ladung_netz_kwh": 50.0}
        auto_daten = {"km_gefahren": 1000.0}
        if auto_eigen:
            auto_daten |= {"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0, "ladung_netz_kwh": 50.0}
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=J, monat=m, verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=J, monat=m, verbrauch_daten=wb_daten))
        db.add(InvestitionMonatsdaten(investition_id=auto.id, jahr=J, monat=m, verbrauch_daten=auto_daten))
        md = Monatsdaten(anlage_id=anlage.id, jahr=J, monat=m, netzbezug_kwh=400.0, einspeisung_kwh=100.0)
        db.add(md)
        await db.flush()
        seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    if kanal_ab is not None:
        await _kanal(db, anlage.id, wb.id, kanal_ab, datetime(J, 3, 1, 1))
    await db.commit()
    return anlage


@pytest.mark.parametrize("evcc, netz_jan", [(True, 50.0), (False, 200.0)], ids=["mit_evcc", "ohne_evcc"])
async def test_zuordnungsmonat_netzladung_nach_bisheriger_regel(db, evcc, netz_jan):
    """Zuordnungsmonat Jan: Netzladung nach bisheriger Regel (evcc 50 bzw. Gesamt − PV = 200), nicht der Teilwert 30;
    erster voller Monat Feb: N_wb = 120 (F11)."""
    anlage = await _wb_anlage(db, evcc=evcc, kanal_ab=datetime(J, 1, 15))
    fakten = await lade_monats_fakten(db, anlage.id)
    jan, feb = _fakt(fakten, J, 1), _fakt(fakten, J, 2)
    assert jan.emob.ladung_netz_kwh == pytest.approx(netz_jan)
    assert jan.emob.ladung_pv_kwh == pytest.approx(200.0 - netz_jan)
    assert jan.emob.wallbox_netz_eigener_tarif_kwh is None                 # F10 (Stromrechnung) wie bisher
    assert (feb.emob.ladung_pv_kwh, feb.emob.ladung_netz_kwh) == pytest.approx((80.0, 120.0))
    assert feb.emob.wallbox_netz_eigener_tarif_kwh == pytest.approx(120.0)


async def test_monat_ohne_kanal_traegt_n_wb(db):
    """Monat ohne Kanal (Hand/CSV): der Monatswert gilt (E2-Wirkung), N_wb ist die Netzladung."""
    anlage = await _wb_anlage(db, evcc=True, kanal_ab=None)
    jan = _fakt(await lade_monats_fakten(db, anlage.id), J, 1)
    assert (jan.emob.ladung_pv_kwh, jan.emob.ladung_netz_kwh) == pytest.approx((170.0, 30.0))
    assert jan.emob.wallbox_netz_eigener_tarif_kwh == pytest.approx(30.0)


async def test_cockpit_zuordnungsmonat_ohne_zaehler_herkunft(db):
    """Cockpit → Monat (T-Konto, emob_kontext): im Zuordnungsmonat keine «Zähler des Versorgers»-Herleitung und die
    E-Mob-Ersparnis wie ohne Feld; im Folgemonat mit."""
    anlage = await _wb_anlage(db, evcc=True, kanal_ab=datetime(J, 1, 15))
    jan = await get_aktueller_monat(anlage.id, J, 1, db)
    feb = await get_aktueller_monat(anlage.id, J, 2, db)
    ohne = await _wb_anlage(db, evcc=True, kanal_ab=None)
    jan_ohne_kanal = await get_aktueller_monat(ohne.id, J, 1, db)
    auto_jan = next(d for d in jan.investitionen_financials if d.typ == "e-auto")
    auto_feb = next(d for d in feb.investitionen_financials if d.typ == "e-auto")
    assert "Zähler des Versorgers" not in (auto_jan.berechnung or "")
    assert "Zähler des Versorgers" in (auto_feb.berechnung or "")
    # Jan: Netzladung 50 (evcc) statt 30 (Teilwert) ⇒ 20 kWh wandern von der PV-Ladung (Preis der EV-Ersparnis, 30 ct)
    # zur Netzladung (Wallbox-Tarif 20 ct): Heimladekosten 2,00 € niedriger, E-Mob-Ersparnis 2,00 € höher (N-672).
    assert jan.emob_ersparnis_euro - jan_ohne_kanal.emob_ersparnis_euro == pytest.approx(20 * (0.30 - 0.20), abs=0.011)


async def test_auto_mit_eigener_messung_unveraendert(db):
    mit = await _wb_anlage(db, evcc=True, kanal_ab=datetime(J, 1, 15), auto_eigen=True)
    ohne = await _wb_anlage(db, evcc=True, kanal_ab=None, auto_eigen=True)
    a = _fakt(await lade_monats_fakten(db, mit.id), J, 1)
    b = _fakt(await lade_monats_fakten(db, ohne.id), J, 1)
    assert (a.emob.ladung_pv_kwh, a.emob.ladung_netz_kwh) == (b.emob.ladung_pv_kwh, b.emob.ladung_netz_kwh)


@pytest.mark.parametrize("monat, feld, netz", [(1, 30.0, 50.0), (2, 120.0, 120.0)], ids=["zuordnungsmonat", "voll"])
async def test_laufender_monat_wallbox_zeile_im_zuordnungsmonat(db, monat, feld, netz):
    """Nachtrag Master-Nachmessung (Bindestelle ``aggregation._mit_auskunft``): der **laufende** Monat ist der
    Zuordnungsmonat des Felds (Kanal ab 15.01.), kein Auto misst selbst ⇒ die Netzladung der Wallbox-Zeile folgt der
    bisherigen Regel (evcc 50), nicht dem Teilwert 30; im voll gedeckten Monat gilt das Feld (120). Gefahren über
    ``wallbox_zuordnung_des_monats`` → ``emob_heimladung_pool`` mit den Werten aus den Quellen (``resolved``)."""
    from backend.api.routes.aktueller_monat.aggregation import emob_heimladung_pool, wallbox_zuordnung_des_monats
    from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo

    anlage = await _wb_anlage(db, evcc=True, kanal_ab=datetime(J, 1, 15))
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()
    wb = next(i for i in invs if i.typ == "wallbox")
    live = DatenquelleInfo(quelle="ha_statistics", konfidenz=92)
    resolved = {f"inv_{wb.id}_ladung_kwh": (200.0, live), f"inv_{wb.id}_ladung_pv_kwh": (150.0, live),
                f"inv_{wb.id}_ladung_netz_kwh": (50.0, live), f"inv_{wb.id}_{FELD}": (feld, live)}
    zuordnung = await wallbox_zuordnung_des_monats(db, anlage.id, invs, resolved, J, monat, ist_aktueller_monat=True)
    assert zuordnung == {wb.id: (J, 1)}
    out = emob_heimladung_pool(direct_fields=set(), investitionen=invs, jahr=J, monat=monat, resolved=resolved,
                               ist_aktueller_monat=True, wallbox_zuordnung=zuordnung)
    pool = out["emob_entscheid"].pool
    assert (pool.ladung_kwh, pool.pv_kwh, pool.netz_kwh) == pytest.approx((200.0, 200.0 - netz, netz))


def test_tagesquote_an_der_zeile_im_zuordnungsmonat():
    """Nachtrag Master-Nachmessung (Bindestelle ``emob_ladeanteil.reichere_ladezeilen_an``): Zeile im Zuordnungsmonat
    ohne Aufteilung (200 kWh, Feld 30) bekommt die Tagesquote 0,4 ⇒ PV 80 / Netz 120; die Kopie behält die Auskunft,
    die Netzladung ist die Quote, nicht das Feld (sonst 170 / 30)."""
    from backend.services.emob_ladeanteil import reichere_ladezeilen_an

    zeile = ZeileImZuordnungsmonat({"ladung_kwh": 200.0, FELD: 30.0})
    _ea, (neu,), abgeleitet = reichere_ladezeilen_an(eauto_daten=[], wallbox_daten=[zeile], quote=0.4)
    assert abgeleitet and neu is not zeile and "ladung_pv_kwh" not in zeile           # Kopie, Original unberührt
    assert isinstance(neu, ZeileImZuordnungsmonat) and not misst_netz_zaehler(neu)
    assert (neu["ladung_pv_kwh"], neu["ladung_netz_kwh"]) == pytest.approx((80.0, 120.0))
    assert get_emob_pv_netz_kwh(neu) == pytest.approx((80.0, 120.0))


# ── Rest 2 — laufender Monat ──────────────────────────────────────────────────


async def test_laufender_monat_wallbox_anteil_aus_kanal_zeilen(db):
    """Ohne Fakt: N_wb und Ladung aus den Kanal-Zeilen der E-Mob-Gruppe ⇒ Anteil = Monatsformel auf den Teilmonat;
    ohne Kanal-Zeilen wie bisher (kein Anteil); WP und Wallbox zusammen ⇒ zweite Klemme (Netzbezug − N_wp)."""
    from backend.api.routes.aktueller_monat.finanzen import komponenten_anteile_des_monats
    from backend.services.monats_fakten.fakten_wp import WpFakten

    anlage = await _wb_anlage(db, evcc=False, kanal_ab=None)
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()
    wb = next(i for i in invs if i.typ == "wallbox")
    zeilen = {wb.id: {"ladung_kwh": 200.0, FELD: 120.0}}
    a = await komponenten_anteile_des_monats(db, anlage.id, J, 3, None, None, 400.0,
                                             emob_kanal=(zeilen, None), investitionen=invs)
    assert a is not None and len(a.netz) == 1
    assert (a.netz[0].verwendung, a.netz[0].kwh, a.netz[0].cent) == ("wallbox", pytest.approx(120.0), pytest.approx(20.0))
    assert await komponenten_anteile_des_monats(db, anlage.id, J, 3, None, None, 400.0,
                                                emob_kanal=({}, None), investitionen=invs) is None
    # Mit WP-Anteil (eigener WP-Tarif fehlt hier ⇒ nur Wallbox): zweite Klemme über den Netzbezug selbst.
    b = await komponenten_anteile_des_monats(db, anlage.id, J, 3, None, WpFakten(strom_kwh=260.0), 100.0,
                                             emob_kanal=(zeilen, None), investitionen=invs)
    assert b.netz[0].kwh == pytest.approx(100.0) and b.netz[0].geklemmt


async def test_laufender_monat_wp_und_wallbox_zweite_klemme(db):
    from backend.api.routes.aktueller_monat.finanzen import komponenten_anteile_des_monats
    from backend.services.monats_fakten.fakten_wp import WpFakten

    anlage = await _wb_anlage(db, evcc=False, kanal_ab=None)
    db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=0.0))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1))
    db.add(wp)
    await db.commit()
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()
    wb = next(i for i in invs if i.typ == "wallbox")
    a = await komponenten_anteile_des_monats(
        db, anlage.id, J, 3, None, WpFakten(strom_kwh=260.0, netz_eigener_tarif_kwh=250.0), 300.0,
        emob_kanal=({wb.id: {"ladung_kwh": 200.0, FELD: 120.0}}, None), investitionen=invs)
    je = {x.verwendung: x for x in a.netz}
    assert je["waermepumpe"].kwh == pytest.approx(250.0)
    assert je["wallbox"].kwh == pytest.approx(50.0) and je["wallbox"].geklemmt      # min(120, 200, 300 − 250)


# ── F12 — gemeinsamer Zähler ──────────────────────────────────────────────────


def _sp(verwendung: str, cent: float, grund: float, ab=date(2025, 1, 1)) -> Strompreis:
    return Strompreis(anlage_id=1, verwendung=verwendung, gueltig_ab=ab, netzbezug_arbeitspreis_cent_kwh=cent,
                      einspeiseverguetung_cent_kwh=0.0, grundpreis_euro_monat=grund)


def test_tarif_aufloesung_gemeinsam_und_vorrang():
    allg, gz, wp, wb = _sp("allgemein", 30, 14), _sp("waermepumpe_wallbox", 22, 10), _sp("waermepumpe", 21, 5), _sp(
        "wallbox", 20, 8)
    t = tarife_zum_stichtag([allg, gz], date(2025, 6, 1))
    assert t["waermepumpe"] is gz and t["wallbox"] is gz and t["allgemein"] is allg and set(t) == {
        "allgemein", "waermepumpe", "wallbox"}
    assert komponenten_tarif_gemeinsam(t)
    assert eigene_tarif_verwendungen(t) == {"waermepumpe"}
    assert tarif_verwendungen_der_flaeche(t) == {"waermepumpe", "waermepumpe_wallbox"}
    g = grundpreis_des_monats(t)
    assert g.summe_euro == pytest.approx(24.0) and g.aufteilung == {"allgemein": 14.0, "waermepumpe_wallbox": 10.0}
    # Eigener WP-Tarif hat Vorrang für seine Verwendung — dann kein gemeinsamer Tarif mehr.
    t2 = tarife_zum_stichtag([wp, allg, gz], date(2025, 6, 1))
    assert t2["waermepumpe"] is wp and t2["wallbox"] is gz and not komponenten_tarif_gemeinsam(t2)
    t3 = tarife_zum_stichtag([wb, allg, gz], date(2025, 6, 1))
    assert t3["wallbox"] is wb and t3["waermepumpe"] is gz and not komponenten_tarif_gemeinsam(t3)
    # Ohne gemeinsamen Datensatz bitgleich: Rückfall auf den allgemeinen.
    t4 = tarife_zum_stichtag([allg], date(2025, 6, 1))
    assert t4["waermepumpe"] is allg and t4["wallbox"] is allg and not komponenten_tarif_gemeinsam(t4)


def _tf(**kw) -> TarifFakten:
    return TarifFakten(netzbezug_preis_cent=30.0, wp_preis_cent=22.0, wallbox_preis_cent=22.0,
                       wallbox_preis_effektiv_cent=22.0, wp_eigener_tarif=True, komponenten_tarif_gemeinsam=True, **kw)


def test_formel_f12a_a():
    """N_g 250 (S 300 + L 200, Netzbezug 400), N_wb nach Regel 100 ⇒ N_wp 150, P_wp 150 zu W_g; Stromrechnung mit N_g."""
    a = komponenten_anteile(400.0, _tf(), wp_strom_kwh=300.0, wp_netz_eigener_tarif_kwh=250.0,
                            wallbox_ladung_kwh=200.0, wallbox_netzladung_kwh=100.0)
    (teil,) = a.netz
    assert (teil.verwendung, teil.kwh, teil.cent) == ("waermepumpe_wallbox", 250.0, 22.0)
    assert (a.gemeinsam_wallbox_kwh, a.gemeinsam_wp_kwh, a.wp_pv_kwh, a.wp_cent) == (100.0, 150.0, 150.0, 22.0)
    from backend.services.monats_fakten.tarif import stromrechnung_euro

    assert stromrechnung_euro(400.0, 30.0, 24.0, a) == pytest.approx(150 * 0.30 + 250 * 0.22 + 24.0)
    # Σ P_wp + PV_wb = S_wp + L_wb − N_g, solange nichts klemmt.
    assert a.wp_pv_kwh + (200.0 - a.gemeinsam_wallbox_kwh) == pytest.approx(300.0 + 200.0 - 250.0)


def test_formel_klemmen():
    # N_g > S_wp + L_wb (und > Netzbezug): auf min(500, 450) geklemmt.
    a = komponenten_anteile(450.0, _tf(), wp_strom_kwh=300.0, wp_netz_eigener_tarif_kwh=600.0,
                            wallbox_ladung_kwh=200.0, wallbox_netzladung_kwh=100.0)
    assert a.netz[0].kwh == 450.0 and a.netz[0].geklemmt
    # N_wb nach Regel > N_g: N_wb auf min(L_wb, N_g), N_wp = Rest.
    b = komponenten_anteile(400.0, _tf(), wp_strom_kwh=300.0, wp_netz_eigener_tarif_kwh=150.0,
                            wallbox_ladung_kwh=200.0, wallbox_netzladung_kwh=180.0)
    assert (b.gemeinsam_wallbox_kwh, b.gemeinsam_wp_kwh, b.gemeinsam_wallbox_regel_kwh) == (150.0, 0.0, 180.0)
    # Ohne Feld an der WP: kein Anteil (bitgleich zu heute).
    assert komponenten_anteile(400.0, _tf(), wp_strom_kwh=300.0, wallbox_ladung_kwh=200.0) is None


async def _gz_anlage(db, *, feld_an_wallbox: bool = False, eigener_wp: bool = False) -> Anlage:
    """Gemeinsamer Tarif 22 ct / 10 €, Haushalt 30 ct / 14 €; Juni 2025: Netzbezug 400, WP S 300 mit Feld N_g 250,
    Wallbox 200 kWh (evcc 120 PV / 80 Netz), PV 600, Einspeisung 100 (EV 500)."""
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="N-770 E6 F12", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=14.0))
    db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe_wallbox", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=0.0, grundpreis_euro_monat=10.0))
    if eigener_wp:
        db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2024, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=21.0, einspeiseverguetung_cent_kwh=0.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1),
                     parameter={"effizienz_modus": "gesamt_jaz", "jaz": 3.5, "wp_art": "luft_wasser"})
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Garage", anschaffungsdatum=date(2024, 1, 1))
    db.add_all([pv, wp, wb])
    await db.flush()
    wb_daten = {"ladung_kwh": 200.0, "ladung_pv_kwh": 120.0, "ladung_netz_kwh": 80.0}
    if feld_an_wallbox:
        wb_daten[FELD] = 77.0
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=J, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=J, monat=6,
                                  verbrauch_daten={"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1050.0, FELD: 250.0}))
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=J, monat=6, verbrauch_daten=wb_daten))
    md = Monatsdaten(anlage_id=anlage.id, jahr=J, monat=6, netzbezug_kwh=400.0, einspeisung_kwh=100.0)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.strompreise)).where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_cockpit_monat_gemeinsamer_zaehler(db):
    """Stromrechnung (400 − 250) × 30 + 250 × 22 + 14 + 10; Anteil «waermepumpe_wallbox»; Grundpreis einmal;
    EV-Ersparnis mit P_wp = 300 − (250 − 80) = 130 zu 22 ct."""
    anlage = await _gz_anlage(db)
    m = await get_aktueller_monat(anlage.id, J, 6, db)
    assert m.netzbezug_kosten_euro == pytest.approx(150 * 0.30 + 250 * 0.22 + 24.0, abs=0.005)
    assert m.grundgebuehr_aufteilung == {"allgemein": 14.0, "waermepumpe_wallbox": 10.0}
    (teil,) = m.netzbezug_anteile
    assert teil["verwendung"] == "waermepumpe_wallbox" and teil["kwh"] == pytest.approx(250.0)
    assert m.ev_ersparnis_wp_tarif_kwh == pytest.approx(130.0)
    assert m.ev_ersparnis_wp_tarif_cent == pytest.approx(22.0)


async def test_feld_an_der_wallbox_zaehlt_nicht_in_der_stromrechnung(db):
    mit = await get_aktueller_monat((await _gz_anlage(db, feld_an_wallbox=True)).id, J, 6, db)
    ohne = await get_aktueller_monat((await _gz_anlage(db)).id, J, 6, db)
    assert mit.netzbezug_kosten_euro == pytest.approx(ohne.netzbezug_kosten_euro, abs=1e-9)
    assert [a["verwendung"] for a in mit.netzbezug_anteile] == ["waermepumpe_wallbox"]


async def test_checker_gemeinsamer_zaehler(db):
    heute = date(2025, 7, 15)
    meld = await DatenChecker(db)._check_wp_eigener_tarif(await _gz_anlage(db, feld_an_wallbox=True), heute=heute)
    texte = [x.meldung for x in meld]
    assert any("Tage teilen die Ersparnis nicht (06/2025)" in t for t in texte)
    assert any("zählt unter dem gemeinsamen Tarif nicht" in t for t in texte)
    vorrang = await DatenChecker(db)._check_wp_eigener_tarif(await _gz_anlage(db, eigener_wp=True), heute=heute)
    assert any("hat Vorrang vor dem gemeinsamen Tarif" in x.meldung for x in vorrang)


# ── F12 — Tag (Auftrag §3.4) ──────────────────────────────────────────────────

M_TAG = 6
TAGE = calendar.monthrange(J, M_TAG)[1]


def _n(h: int) -> float:
    return 0.5 if 1 <= h <= 21 else 0.0


def _wp(h: int) -> float:
    return 0.8 if 1 <= h <= 21 else 0.0


def _pv(h: int) -> float:
    return 2.0 if 10 <= h <= 14 else 0.0


async def _gz_tag_anlage(db) -> Anlage:
    """Wie ``test_n770_e3_tag_stunde`` (Juni 2025, Netzbezug 1 kWh je Stunde, S 504, N_g 315 aus dem Kanal an der WP),
    dazu eine Wallbox 100 kWh (evcc 60 PV / 40 Netz) — gemeinsamer Tarif 22 ct, Haushalt 30 ct, kein Zeitfenster."""
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="N-770 E6 F12 Tag", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=14.0))
    db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe_wallbox", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=0.0, grundpreis_euro_monat=10.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1),
                     parameter={"effizienz_modus": "gesamt_jaz", "jaz": 3.5})
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Garage", anschaffungsdatum=date(2024, 1, 1))
    db.add_all([pv, wp, wb])
    await db.flush()
    s_monat = sum(_wp(h) for h in range(24)) * TAGE
    n_monat = sum(_n(h) for h in range(24)) * TAGE
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=J, monat=M_TAG, verbrauch_daten={
        "stromverbrauch_kwh": s_monat, "heizenergie_kwh": s_monat * 3.5, FELD: n_monat}))
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=J, monat=M_TAG, verbrauch_daten={
        "ladung_kwh": 100.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 40.0}))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=J, monat=M_TAG,
                                  verbrauch_daten={"pv_erzeugung_kwh": sum(_pv(h) for h in range(24)) * TAGE}))
    md = Monatsdaten(anlage_id=anlage.id, jahr=J, monat=M_TAG, netzbezug_kwh=24.0 * TAGE, einspeisung_kwh=0.0)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    for tag in [date(J, M_TAG, 1) + timedelta(days=i) for i in range(TAGE)]:
        for s in range(24):
            h = (s - 1) % 24
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=s, pv_kw=_pv(h), einspeisung_kw=0.0,
                                      netzbezug_kw=1.0, verbrauch_kw=1.0 + _pv(h), waermepumpe_kw=_wp(h)))
    k = Kanal(anlage_id=anlage.id, key=f"inv:{wp.id}:{FELD}", einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    t0 = datetime(J, 5, 31)
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(t0.timestamp()), familie="spiegel", offset=0.0))
    summe, t = 0.0, t0
    while t < datetime(J, M_TAG + 1, 1, 1):
        summe += _n(t.hour)
        db.add(KanalStatistik(kanal_id=k.id, start_ts=int(t.timestamp()), sum=summe, familie="spiegel"))
        t += timedelta(hours=1)
    await db.commit()
    return anlage


async def test_tag_stromrechnung_je_stunde_ev_teilt_nicht(db):
    """Σ Tage Stromrechnung = Monat ((720 − 315) × 30 + 315 × 22); die EV-Ersparnis des Tages teilt nicht (ohne
    Stundenwerte der Wallbox), der Monat bewertet P_wp = 504 − (315 − 40) = 229 kWh zu 22 ct — Σ Tage EV liegt um
    P_wp × (30 − 22) ct höher (benannte Grenze analog F9)."""
    anlage = await _gz_tag_anlage(db)
    monat = await get_aktueller_monat(anlage.id, J, M_TAG, db)
    tage = await baue_tage_werte(db, anlage, date(J, M_TAG, 1), date(J, M_TAG, TAGE))
    soll = (720 - 315) * 0.30 + 315 * 0.22
    assert monat.netzbezug_arbeitspreis_kosten_euro == pytest.approx(soll, abs=0.01)
    assert sum(t.netzbezug_kosten for t in tage) == pytest.approx(soll, abs=1e-6)
    assert monat.ev_ersparnis_wp_tarif_kwh == pytest.approx(229.0)
    assert sum(t.ev_ersparnis for t in tage) - monat.ev_ersparnis_euro == pytest.approx(229 * (0.30 - 0.22), abs=0.02)


def test_label_des_felds_unter_gemeinsamem_tarif():
    from backend.core.field_definitions.auswahl import TARIF_LABEL_GEMEINSAM, tarif_label

    feld = {"feld": FELD, "tarif_verwendung": "waermepumpe"}
    assert tarif_label(feld, {"waermepumpe", "waermepumpe_wallbox"}) == TARIF_LABEL_GEMEINSAM
    assert tarif_label(feld, {"waermepumpe"}) is None
    assert tarif_label({"feld": FELD, "tarif_verwendung": "wallbox"}, {"waermepumpe", "waermepumpe_wallbox"}) is None
