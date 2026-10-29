"""Tabellen-Spalten E-Mobilität und Wärme/Klima (*Auswertungen → Tabellen*, Auftrag 28.10.2026) — Backend-Proben.

Was hier gesichert wird, und warum:

1. **Bereich = Einzeltag** (Entscheid Master 28.10., Option A): ``fahrt_der_tage``/``zustand_wechsel_der_tage`` lesen
   EINEN Stunden-Stapel über das Fenster und müssen für jeden Tag dasselbe liefern wie ``fahrt_je_tag``/
   ``zustand_wechsel_je_tag`` (dieselbe Σ-Regel, dasselbe Raster). Drei Tage Mitschrift, die erste Zeile ohne Vorstand.
2. **Tages-Tabelle**: ``tage-werte`` trägt die Summen über die privaten Geräte (ein Dienstwagen zählt nicht), ``None``
   an Tagen ohne Wert; WP-Starts/Betriebszeit (ganze Minuten) mit der Tagessumme von *Cockpit → Monat*.
3. **Monats-Tabelle**: die neuen Felder der Zeile — Mengen «nur mit Wert» wie *Cockpit → Monat*, kWh/100 km aus dem
   Layer, Betriebsart-Strom nur mit Aufteilung, Zusatzheizung nur gemessen, Arbeitszahl je Funktion.

Die Uhr steht fest (``zeitpunkt``/``datum``) — keine Probe liest die echte Uhr.
Schwesterdateien: test_p433_2b_k4_fahrt_pvanteil.py (Fahrt heute), test_p433_2b_k3_mitschrift.py (Wechsel).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services import mqtt_inbound_service as mis
from backend.tests import factories

D1, D2, D3 = date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)
M0 = datetime(2026, 6, 9, 0)


@pytest.fixture(autouse=True)
def _ohne_singleton(monkeypatch):
    monkeypatch.setattr(mis, "_mqtt_inbound_service", None)


async def _anlage(db, *, dienstwagen: bool = False):
    a = await factories.anlage(db, anlagenname="Test", sensor_mapping={})
    wb = await factories.investition(db, a.id, "wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1))
    auto = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1))
    dw = (await factories.investition(db, a.id, "e-auto", bezeichnung="Dienst", anschaffungsdatum=date(2024, 1, 1),
                                      parameter={"ist_dienstlich": True})
          if dienstwagen else None)
    await db.commit()
    return a, wb, auto, dw


async def _saat(db, a, wb, autos):
    """Drei Tage Mitschrift: je Auto km-Stand und Fahrverbrauch (Zuwachs 10 km / 1,5 kWh in Stunde 7 und 30 km /
    5,0 kWh in Stunde 17 jedes Tages, ab 05:00 des ersten Tages), an der Wallbox Übergänge nach «lädt» um 09:24 (alle
    Tage) und 20:24 (nur am zweiten). Danach der Stundenlauf beider Schreiber von 06:05 des ersten bis 23:05 des
    dritten Tages."""
    from backend.services.kanal.schreiber import schreibe_eigene_summe, schreibe_zustands_mitschrift_mqtt

    for auto in autos:
        km = kwh = 0.0
        for h in range(5, 72):
            t = M0 + timedelta(hours=h)
            if h % 24 in (8, 18):
                km += 10.0 if h % 24 == 8 else 30.0
                kwh += 1.5 if h % 24 == 8 else 5.0
            for m in (0, 30):
                db.add(MqttEnergySnapshot(anlage_id=a.id, timestamp=t + timedelta(minutes=m),
                                          energy_key=f"inv/{auto.id}/km_gefahren", value_kwh=23000.0 + km))
                db.add(MqttEnergySnapshot(anlage_id=a.id, timestamp=t + timedelta(minutes=m),
                                          energy_key=f"inv/{auto.id}/verbrauch_kwh", value_kwh=5000.0 + kwh))
    # Die Mitschrift schreibt eine Stunde nur mit Zustands-Anteilen (5-Minuten-Snapshots, K3) — Wechsel allein nicht.
    for h in range(5, 72):
        for m in range(5, 65, 5):
            ts = int((M0 + timedelta(hours=h, minutes=m)).timestamp()) - 1
            db.add(MqttLiveSnapshot(anlage_id=a.id, timestamp=datetime.fromtimestamp(ts),
                                    component_key=f"inv:{wb.id}:ladezustand:verbunden", value_w=1.0, ts_unix=ts))
    for tag_nr, stunden in ((0, (9,)), (1, (9, 20)), (2, (9,))):
        for h in stunden:
            ts = int((M0 + timedelta(days=tag_nr, hours=h, minutes=24)).timestamp())
            db.add(MqttLiveSnapshot(anlage_id=a.id, timestamp=datetime.fromtimestamp(ts),
                                    component_key=f"inv:{wb.id}:ladezustand:wechsel_laedt", value_w=1.0, ts_unix=ts))
    await db.commit()
    zp = M0 + timedelta(hours=6, minutes=5)
    while zp <= M0 + timedelta(days=2, hours=23, minutes=5):
        await schreibe_eigene_summe(db, a, zp)
        await schreibe_zustands_mitschrift_mqtt(db, a, zp)
        await db.commit()
        zp += timedelta(hours=1)


async def _invs(db, a):
    from sqlalchemy import select

    from backend.models.investition import Investition

    return {str(i.id): i for i in (await db.execute(
        select(Investition).where(Investition.anlage_id == a.id))).scalars().all()}


# ═══ 1 · Bereich = Einzeltag ═══════════════════════════════════════════════════

async def test_fahrt_und_wechsel_bereich_gleich_einzeltag_an_jedem_tag(db):
    from backend.services.energie_profil import kanal_stunden as ks

    a, wb, auto, _ = await _anlage(db)
    await _saat(db, a, wb, [auto])
    invs = await _invs(db, a)
    fahrt = await ks.fahrt_der_tage(db, a, invs, D1 - timedelta(days=1), D3 + timedelta(days=1))
    wechsel = await ks.zustand_wechsel_der_tage(db, a, invs, D1 - timedelta(days=1), D3 + timedelta(days=1),
                                                typ="wallbox", feld="ladezustand", wert="laedt")
    for tag in (D1 - timedelta(days=1), D1, D2, D3, D3 + timedelta(days=1)):
        assert fahrt.get(tag, {}) == await ks.fahrt_je_tag(db, a, invs, tag), tag
        assert wechsel.get(tag, {}) == await ks.zustand_wechsel_je_tag(
            db, a, invs, tag, typ="wallbox", feld="ladezustand", wert="laedt"), tag
    # Nicht leer: am zweiten Tag zwei Fahrten (40 km, 6,5 kWh) und zwei Ladevorgänge.
    assert fahrt[D2][str(auto.id)] == {"km": pytest.approx(40.0), "verbrauch_kwh": pytest.approx(6.5)}
    assert wechsel[D2] == {str(wb.id): 2}


async def test_bereich_ohne_kanal_keine_aussage(db):
    from backend.services.energie_profil import kanal_stunden as ks

    a, _wb, _auto, _ = await _anlage(db)
    invs = await _invs(db, a)
    assert await ks.fahrt_der_tage(db, a, invs, D1, D3) == {}
    assert await ks.zustand_wechsel_der_tage(db, a, invs, D1, D3, typ="wallbox", feld="ladezustand",
                                             wert="laedt") == {}


# ═══ 2 · Tages-Tabelle ═════════════════════════════════════════════════════════

async def test_tage_werte_summen_ueber_private_geraete_dienstwagen_zaehlt_nicht(db):
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    a, wb, auto, dw = await _anlage(db, dienstwagen=True)
    await _saat(db, a, wb, [auto, dw])
    for tag, kwh in ((D1, -7.25), (D2, 11.5)):   # Leistungspfad negativ, Zählerpfad positiv (K4-N1: Betrag)
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=tag, komponenten_kwh={f"wallbox_{wb.id}": kwh}))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D3, komponenten_kwh={}))
    await db.commit()
    zeilen = {z.datum: z for z in await baue_tage_werte(db, a, D1, D3)}
    assert zeilen[D2].eauto_km == pytest.approx(40.0), "nur das private Auto, der Dienstwagen fehlt"
    assert zeilen[D2].eauto_fahrverbrauch == pytest.approx(6.5)
    assert zeilen[D2].ladevorgaenge == 2
    assert zeilen[D2].wallbox_ladung == pytest.approx(11.5)
    assert zeilen[D1].wallbox_ladung == pytest.approx(7.25)
    assert zeilen[D3].wallbox_ladung is None, "ohne Wallbox-Schlüssel kein Wert — keine 0"
    assert zeilen[D2].wp_starts is None and zeilen[D2].wp_betriebszeit_min is None


async def test_tage_werte_wp_starts_und_betriebszeit_in_ganzen_minuten(db):
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    a = await factories.anlage(db, anlagenname="WP", sensor_mapping={})
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1))
    alt = await factories.investition(db, a.id, "waermepumpe", bezeichnung="Alt", anschaffungsdatum=date(2020, 1, 1),
                                      stilllegungsdatum=date(2025, 1, 1))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D1, komponenten_kwh={}, komponenten_starts={
        "wp_starts_anzahl": {str(wp.id): 7, str(alt.id): 99}, "wp_betriebsstunden": {str(wp.id): 3.26}}))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D2, komponenten_kwh={}, komponenten_starts={
        "wp_starts_anzahl": {str(wp.id): 0}, "wp_betriebsstunden": {}}))
    await db.commit()
    zeilen = {z.datum: z for z in await baue_tage_werte(db, a, D1, D2)}
    assert zeilen[D1].wp_starts == 7, "die stillgelegte Wärmepumpe zählt nicht (Cockpit → Monat)"
    assert zeilen[D1].wp_betriebszeit_min == 196, "3,26 h = 195,6 min ⇒ ganze Minuten"
    # Dieselbe Tagessumme wie Cockpit → Monat: ein Tag ohne Wert > 0 hat keinen Tageswert.
    assert zeilen[D2].wp_starts is None and zeilen[D2].wp_betriebszeit_min is None


def test_wp_zaehler_tagessumme_nur_aktive_und_positive():
    from backend.services.energie_profil.tage_werte_zusatz import wp_zaehler_tagessumme

    komp = {"wp_starts_anzahl": {"1": 4, "2": 3, "3": -1, "4": "x"}}
    assert wp_zaehler_tagessumme(komp, "wp_starts_anzahl", {"1", "3", "4"}) == 4.0
    assert wp_zaehler_tagessumme(None, "wp_starts_anzahl", {"1"}) == 0.0


# ═══ 3 · Monats-Tabelle ════════════════════════════════════════════════════════

def _fakt(**emob):
    basis = dict(fahrverbrauch_kwh=0.0, ladung_kwh=0.0, extern_kwh=0.0, extern_euro=0.0, km=0.0,
                 v2h_entladung_kwh=0.0, ladevorgaenge=0.0)
    return SimpleNamespace(emob=SimpleNamespace(**{**basis, **emob}))


def test_monat_emob_nur_mit_wert_und_verbrauch_aus_dem_layer():
    from backend.api.routes.monatsdaten_aggregiert import _zeile_emob_zusatz

    z = _zeile_emob_zusatz(_fakt(fahrverbrauch_kwh=180.0, ladung_kwh=250.0, extern_kwh=20.0, extern_euro=11.4,
                                 km=1000.0, v2h_entladung_kwh=12.0, ladevorgaenge=9.0), {"e-auto", "wallbox"})
    assert z == dict(eauto_fahrverbrauch_kwh=180.0, eauto_verbrauch_kwh_100km=18.0, eauto_v2h_entladung_kwh=12.0,
                     emob_ladung_extern_kwh=20.0, emob_ladung_extern_euro=11.4, emob_ladevorgaenge=9.0)
    # Ohne gemessenen Fahrverbrauch die Näherung aus Heim + Extern (N-557), Mengen 0 ⇒ «—» wie Cockpit → Monat.
    z = _zeile_emob_zusatz(_fakt(ladung_kwh=250.0, extern_kwh=20.0, km=1500.0), {"e-auto"})
    assert z["eauto_verbrauch_kwh_100km"] == pytest.approx(18.0)
    assert z["eauto_fahrverbrauch_kwh"] is None and z["eauto_v2h_entladung_kwh"] is None
    assert z["emob_ladevorgaenge"] is None
    # Ohne E-Auto/Wallbox im Monat: alles leer; ohne km keine Quote.
    assert set(_zeile_emob_zusatz(_fakt(fahrverbrauch_kwh=5.0), set()).values()) == {None}
    assert _zeile_emob_zusatz(_fakt(ladung_kwh=50.0), {"e-auto"})["eauto_verbrauch_kwh_100km"] is None


def _wp(**felder):
    basis = dict(hat_modus_split=False, modus_strom_kuehlen_kwh=0.0, modus_strom_lueften_kwh=0.0,
                 modus_strom_entfeuchten_kwh=0.0, modus_nicht_aufgeteilt_kwh=0.0, nutzenergie_kuehlen_kwh=0.0,
                 heizstab_kwh=None)
    return SimpleNamespace(wp=SimpleNamespace(**{**basis, **felder}))


def test_monat_wp_betriebsart_nur_mit_aufteilung_heizstab_nur_gemessen():
    from backend.api.routes.monatsdaten_aggregiert import _zeile_wp_zusatz

    z = _zeile_wp_zusatz(_wp(hat_modus_split=True, modus_strom_kuehlen_kwh=31.04, modus_strom_lueften_kwh=0.0,
                             modus_strom_entfeuchten_kwh=2.0, modus_nicht_aufgeteilt_kwh=9.0,
                             nutzenergie_kuehlen_kwh=95.0, heizstab_kwh=0.0), {"waermepumpe"}, (4.2, 3.1, 3.06))
    assert z == dict(wp_strom_kuehlen_kwh=31.0, wp_strom_lueften_kwh=0.0, wp_strom_entfeuchten_kwh=2.0,
                     wp_strom_nicht_aufgeteilt_kwh=9.0, wp_kaelte_kwh=95.0, wp_heizstab_kwh=0.0,
                     wp_jaz_heizen=4.2, wp_jaz_warmwasser=3.1, wp_jaz_kuehlen=3.06)
    ohne = _zeile_wp_zusatz(_wp(modus_strom_kuehlen_kwh=31.0), {"waermepumpe"}, (None, None, None))
    assert ohne["wp_strom_kuehlen_kwh"] is None, "ohne Aufteilung keine Teilmenge"
    assert ohne["wp_heizstab_kwh"] is None and ohne["wp_kaelte_kwh"] is None
    assert _zeile_wp_zusatz(_wp(), set(), (None, None, None)) == {}


async def test_monatsroute_traegt_die_neuen_felder(db):
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    a = await factories.anlage(db, anlagenname="Test", sensor_mapping={})
    auto = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1))
    await factories.monatsdaten(db, a.id, 2026, 5, einspeisung_kwh=100.0, netzbezug_kwh=50.0)
    await factories.imd(db, auto.id, 2026, 5, verbrauch_daten={
        "km_gefahren": 1000.0, "verbrauch_kwh": 170.0, "ladung_kwh": 200.0, "v2h_entladung_kwh": 8.0})
    [z] = await list_monatsdaten_aggregiert(a.id, jahr=None, db=db)
    assert z.eauto_fahrverbrauch_kwh == pytest.approx(170.0)
    assert z.eauto_verbrauch_kwh_100km == pytest.approx(17.0)
    assert z.eauto_v2h_entladung_kwh == pytest.approx(8.0)
    assert z.wp_jaz_heizen is None and z.wp_strom_kuehlen_kwh is None


# ── Wärmepumpen-Tagesreihe (Auftrag 29.10.2026, ``?mit_waerme=true``) ──────────────────────────────────────────────

_WAERME_PAARE = {  # Tabellen-Spalte → Feld der Route `waerme-verlauf` (Cockpit → Monat)
    "wp_waerme": "wp_waerme_kwh", "wp_kaelte": "wp_kaelte_kwh",
    "wp_strom_kuehlen": "wp_modus_strom_kuehlen_kwh", "wp_strom_lueften": "wp_modus_strom_lueften_kwh",
    "wp_strom_entfeuchten": "wp_modus_strom_entfeuchten_kwh",
    "wp_strom_nicht_aufgeteilt": "wp_modus_nicht_aufgeteilt_kwh",
}


async def _wp_klima_zwei_tage(db):
    """Ein Klimagerät (luft_luft) an zwei Tagen: Kühlstrom 6 / 4 kWh (Betriebsart-Zähler ⇒ Aufteilung), Kälte 18 / 9,
    Wärme (gemeinsamer Wärmemengenzähler) 5 / 0 — und Bezug 30 / 20 kWh in der Tageszeile. Am zweiten Tag ist die Wärme
    0 (der Leser sagt dann «keine Aussage»), Kälte und Aufteilung bleiben."""
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.energie_profil._provenance_helpers import seed_tz_provenance

    a = await factories.anlage(db, anlagenname="Klima", sensor_mapping={})
    inv = await factories.investition(db, a.id, "waermepumpe", bezeichnung="Klima", anschaffungsdatum=date(2024, 1, 1),
                                      parameter={"wp_art": "luft_luft"})
    t0 = datetime.combine(D1, datetime.min.time())
    felder = {}
    for feld, je_tag in (("betriebsart_strom_kuehlen_kwh", (6.0, 4.0)),
                         ("betriebsart_nutzenergie_kuehlen_kwh", (18.0, 9.0)),
                         ("waerme_kwh", (5.0, 0.0))):
        felder[feld] = {"strategie": "sensor", "sensor_id": f"sensor.{inv.id}_{feld}"}
        stand = 100.0
        for n, kwh in enumerate((0.0, *je_tag)):
            stand += kwh
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=f"inv:{inv.id}:{feld}", zeitpunkt=t0 + timedelta(days=n),
                                  wert_kwh=stand, quelle="ha_statistics"))
    a.sensor_mapping = {"investitionen": {str(inv.id): {"felder": felder}}}
    for tag, bezug in ((D1, 30.0), (D2, 20.0)):
        tz = TagesZusammenfassung(anlage_id=a.id, datum=tag, komponenten_kwh={f"waermepumpe_{inv.id}": bezug})
        seed_tz_provenance(tz, writer="test", source="auto:monatsabschluss")
        db.add(tz)
    await db.commit()
    return a


async def test_tage_werte_waerme_nur_auf_anfrage_und_gleich_dem_cockpit_monat(db):
    """Ohne ``mit_waerme`` bleiben die sechs Felder ``None`` (Cockpit → Monat ruft die Route so); mit ihm trägt jeder
    Tag genau die Werte der Route ``waerme-verlauf`` für denselben Tag — derselbe Leser, dieselbe Rundung, «nur mit
    Aufteilung» und «keine 0 als Platzhalter» wie dort. Die übrigen Spalten bleiben mit und ohne Parameter gleich."""
    from backend.api.routes.energie_profil.waerme import get_waerme_verlauf
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    a = await _wp_klima_zwei_tage(db)
    ohne = {z.datum: z for z in await baue_tage_werte(db, a, D1, D2)}
    assert set(ohne) == {D1, D2}
    assert all(getattr(z, f) is None for z in ohne.values() for f in _WAERME_PAARE), "ohne Parameter keine WP-Reihe"

    mit = {z.datum: z for z in await baue_tage_werte(db, a, D1, D2, mit_waerme=True)}
    cockpit = {z.datum: z for z in await get_waerme_verlauf(a.id, von=D1, bis=D2, db=db)}
    assert set(cockpit) == {D1, D2}
    for tag in (D1, D2):
        for spalte, feld in _WAERME_PAARE.items():
            assert getattr(mit[tag], spalte) == getattr(cockpit[tag], feld), (tag, spalte)
    # Die Probe trägt Werte (sonst bewiese die Gleichheit nichts): Kühlstrom gemessen, der Rest nicht aufgeteilt.
    assert mit[D1].wp_strom_kuehlen == pytest.approx(6.0)
    assert mit[D1].wp_strom_nicht_aufgeteilt == pytest.approx(24.0)
    assert mit[D1].wp_kaelte == pytest.approx(18.0) and mit[D1].wp_waerme == pytest.approx(5.0)
    assert mit[D2].wp_kaelte == pytest.approx(9.0)
    assert mit[D2].wp_waerme is None, "Wärme 0 ⇒ keine Aussage wie im Verlauf, keine 0 als Platzhalter"
    for tag in (D1, D2):
        assert ohne[tag].model_dump(exclude=set(_WAERME_PAARE)) == mit[tag].model_dump(exclude=set(_WAERME_PAARE))


async def test_route_tage_werte_positional_mit_db_und_parameter_aus(db):
    """Die Route bleibt positional mit ``db`` an vierter Stelle rufbar (vier Bestandsproben tun das), und ohne den
    Parameter ist er ``False`` — kein wahres ``Query``-Objekt als Default."""
    from backend.api.routes.energie_profil.tage import get_tage_werte

    a = await _wp_klima_zwei_tage(db)
    ohne = await get_tage_werte(a.id, D1, D2, db)
    assert ohne and all(z.wp_kaelte is None for z in ohne)
    mit = {z.datum: z for z in await get_tage_werte(a.id, D1, D2, db, mit_waerme=True)}
    assert mit[D1].wp_kaelte == pytest.approx(18.0)


# ── Zusatzheizung je Tag (Auftrag 29.10.2026, Option (b) des Halts H1) ──────────────────────────────────────────────

D0, D4 = date(2026, 6, 8), date(2026, 6, 12)


async def _wp_heizstab_vier_tage(db):
    """Eine Wärmepumpe mit Heizstab-Zähler, stündliche Stände von D0 00:00 bis D4 00:00: je Stunde +0,1 kWh, in der
    Stunde D1 23:00–24:00 aber +5,0 kWh, und an D3 kein Zuwachs (gemessene 0). Die Tageszeilen von D1 und D2 kommen aus
    der HA-Langzeitstatistik (Rückwärts-Fenster [Vortag 23:00, 23:00)), D3 aus dem Snapshot-Pfad (Kalendertag) — der
    Sprung zählt damit zu D2, nicht zu D1. D4 hat keine Tageszeile."""
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.energie_profil._provenance_helpers import seed_tz_provenance
    from backend.services.snapshot.boundary_range import TZ_QUELLE_LTS

    a = await factories.anlage(db, anlagenname="Heizstab", sensor_mapping={})
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1))
    feld = "heizstab_strom_kwh"
    a.sensor_mapping = {"investitionen": {str(wp.id): {"felder": {
        feld: {"strategie": "sensor", "sensor_id": f"sensor.{wp.id}_{feld}"}}}}}
    t0 = datetime.combine(D0, datetime.min.time())
    stand = 500.0
    for h in range(4 * 24 + 1):
        ts = t0 + timedelta(hours=h)
        db.add(SensorSnapshot(anlage_id=a.id, sensor_key=f"inv:{wp.id}:{feld}", zeitpunkt=ts, wert_kwh=stand,
                              quelle="ha_statistics"))
        if ts.date() != D3:
            stand += 5.0 if ts == datetime.combine(D1, datetime.min.time()) + timedelta(hours=23) else 0.1
    for tag, lts in ((D1, True), (D2, True), (D3, False)):
        tz = TagesZusammenfassung(anlage_id=a.id, datum=tag, komponenten_kwh={f"waermepumpe_{wp.id}": 10.0})
        seed_tz_provenance(tz, writer="test", source=TZ_QUELLE_LTS if lts else "auto:monatsabschluss")
        db.add(tz)
    await db.commit()
    return a


async def test_zusatzheizung_je_tag_gleich_cockpit_tag_und_bereich_gleich_einzeltag(db):
    """Je Tag mit ``mit_waerme`` dieselbe Zusatzheizung wie *Cockpit → Tag* (``tag-detail.wp_heizstab_kwh``) — auch am
    Rückwärts-Tag; derselbe Wert, ob der Tag allein oder im Bereich gelesen wird; ohne Parameter ``None``; eine gemessene
    0 bleibt 0 (wie im Tag), ein Tag ohne Stände trägt nichts. Die sechs Geschwister-Felder bleiben ``None`` (kein
    Verlauf an diesen Tagen ohne Wärme/Aufteilung)."""
    from backend.api.routes.energie_profil.views import get_tag_detail
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    a = await _wp_heizstab_vier_tage(db)
    bereich = {z.datum: z for z in await baue_tage_werte(db, a, D1, D3, mit_waerme=True)}
    assert set(bereich) == {D1, D2, D3}
    for tag in (D1, D2, D3):
        cockpit = (await get_tag_detail(a.id, tag, db)).wp_heizstab_kwh
        [einzel] = await baue_tage_werte(db, a, tag, tag, mit_waerme=True)
        assert bereich[tag].wp_heizstab == cockpit == einzel.wp_heizstab, tag
    # Fenster: D1 rückwärts [D0 23:00, D1 23:00) = 24 × 0,1; D2 rückwärts trägt den Sprung der Stunde D1 23–24.
    assert bereich[D1].wp_heizstab == pytest.approx(2.4)
    assert bereich[D2].wp_heizstab == pytest.approx(7.3)
    assert bereich[D3].wp_heizstab == 0.0, "gemessene 0 bleibt 0 — wie Cockpit → Tag"
    ohne = {z.datum: z for z in await baue_tage_werte(db, a, D1, D3)}
    assert all(z.wp_heizstab is None for z in ohne.values()), "ohne Parameter keine Zusatzheizung"
    assert all(getattr(bereich[t], f) is None for t in (D1, D2, D3) for f in _WAERME_PAARE)


async def test_zusatzheizung_ohne_zaehler_keine_aussage(db):
    """Ohne Heizstab-Zähler trägt kein Tag eine Zusatzheizung — keine 0 als Platzhalter (wie Cockpit → Tag)."""
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    a = await _wp_klima_zwei_tage(db)
    assert all(z.wp_heizstab is None for z in await baue_tage_werte(db, a, D1, D2, mit_waerme=True))
