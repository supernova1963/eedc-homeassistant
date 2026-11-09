"""P-433-2b K4 «E-Auto-Fahrt heute, Kopfzahl PV-Anteil, Preset-Wahl» — Backend-Proben (Bauplan K4 Fassung 1a §1–§5).

Was hier gesichert wird, und warum jede Gruppe existiert:

1. **Katalog O7** (K4-3, Halt H2): ``km_gefahren``/``ladevorgaenge`` tragen Spiegel/Mitschrift (Katalog-Korrektur), und der
   Spiegel folgt der ``counter_map`` — ein km-Zähler mit ``quellen``-Wahl HA wird gespiegelt, eine Zuordnung nur über
   ``felder`` nicht (vorbestehende Grenze). Die übrigen Zuweisungen bleiben (Sprengsatz S7 über den Kanal-Dump).
2. **Layer** (K4-4, Halt H1): ``pv_anteil_prozent`` (bis Päckchen Z1b ``pv_anteil_gemessen_prozent``) — Quote zweier gemessener Mengen, ``None`` ohne Aussage;
   dieselbe Zahl wie ``ist_pv_ladeanteil_prozent`` auf denselben Mengen.
3. **Fahrt heute** (K4-2): Σ Zuwachs der Kanal-Stunden; die erste Kanalzeile (Tachostand) zählt 0 (S4).
4. **Tag-Detail** ``emob_heute`` (K4-4/K4-5): Kopfzahl nur gemessen (S3), nur mit beiden Mengen, nur ``pv ≤ ladung``,
   nie aus dem Live-Pfad (S1); E-Auto unter deckender Wallbox ohne ``ladung_kwh``.
5. **Kilometerstand live** (K4-1): HA vor MQTT, ``quellen``-Wahl, nie aus dem Monatsfeld (S6); Builder/Schema/Demo.
6. **Preset** (K4-7/K4-8): ``typen`` am Preset, Apply ersetzt je ``ziel_key`` (S5) und setzt die Quelle Gateway.

Die Uhr steht fest (``zeitpunkt``/``datum``) — keine Probe liest die echte Uhr.
Schwesterdateien: test_p433_2b_k1_emob.py, test_p433_2b_k3_mitschrift.py, test_kanal_feld_deckung.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.core.berechnungen.pv_anteil_ladung import pv_anteil_prozent
from backend.models.kanal import ART_STAND, FAMILIE_MITSCHRIFT, FAMILIE_SPIEGEL
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
# Am Dateikopf, damit die Tabelle im Schema der `db`-Fixture steht, auch wenn eine Probe einzeln läuft.
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services import betriebsmodus_live as bml
from backend.services import mqtt_inbound_service as mis
from backend.services.kanal import katalog as kat
from backend.tests import factories

TAG = date(2026, 6, 10)
M0 = datetime(2026, 6, 10, 0)


@pytest.fixture(autouse=True)
def _ohne_takt_und_singleton(monkeypatch):
    bml.cache_leeren()
    monkeypatch.setattr(mis, "_mqtt_inbound_service", None)
    yield
    bml.cache_leeren()


async def _anlage_emob(db, *, sensor_mapping: dict | None = None, mit_wallbox: bool = True):
    a = await factories.anlage(db, anlagenname="Test", sensor_mapping={})
    wb = (await factories.investition(db, a.id, "wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1))
          if mit_wallbox else None)
    auto = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1))
    a.sensor_mapping = sensor_mapping or {}
    await db.commit()
    return a, wb, auto


# ═══ 1 · Katalog O7 (K4-3, H2) ════════════════════════════════════════════════

def test_o7_spiegel_oder_mitschrift_mit_grundtext():
    o7 = [z for z in kat.zuweisungen() if z.feld in ("km_gefahren", "ladevorgaenge")]
    assert {(z.liste, z.typ) for z in o7} == {
        (kat.L_INV, "e-auto"), (kat.L_INV, "wallbox"), (kat.L_MQTT_STAND, None)}
    for z in o7:
        if z.liste == kat.L_MQTT_STAND:
            # Die typlose Liste beschreibt den MQTT-EINGANG (``snapshot/keys.py``) — sie bleibt «nur Mitschrift».
            assert (z.art, z.familien) == (ART_STAND, (FAMILIE_MITSCHRIFT,)), z
            continue
        assert (z.art, z.familien, z.e1_schreiber) == (ART_STAND, (FAMILIE_SPIEGEL, FAMILIE_MITSCHRIFT), True), z
        assert z.grund == "O7: Spiegel bei HA-Entität, sonst MQTT-Mitschrift"
    assert kat.zaehler_art("inv:3:km_gefahren", "e-auto") == ART_STAND
    assert kat.zaehler_art("inv:5:ladevorgaenge", "wallbox") == ART_STAND


def test_katalog_bestand_ausser_o7_unveraendert():
    """S7: die Katalog-Korrektur fasst nur O7 an — die Zähler der Fahrt und der Ladung behalten Art und Familien,
    der Tachostand der Handeingabe (``km_stand``) bleibt O5 ohne Kanal."""
    from backend.models.kanal import ART_SUM

    je = {(z.liste, z.typ, z.feld): z for z in kat.zuweisungen()}
    for typ, feld in (("e-auto", "verbrauch_kwh"), ("wallbox", "ladung_kwh"), ("wallbox", "ladung_pv_kwh"),
                      ("e-auto", "ladung_kwh")):
        z = je[(kat.L_INV, typ, feld)]
        assert (z.art, z.familien, z.e1_schreiber) == (ART_SUM, (FAMILIE_SPIEGEL, FAMILIE_MITSCHRIFT), True), z
    km = je[(kat.L_INV, "e-auto", "km_stand")]
    assert (km.art, km.ausnahme) == (None, kat.AUSNAHME_ABSCHLUSS)


def test_spiegel_folgt_der_counter_map_quellen_ha_ja_felder_allein_nein():
    """Bestand (H2): ``_build_counter_map`` nimmt einen km-Zähler nur mit ``quellen``-Wahl HA auf (Read-Through
    «ERGÄNZEN») — eine Zuordnung nur über ``felder`` bleibt draußen (benannte Grenze, vorbestehend)."""
    from backend.services.snapshot.writer import _build_counter_map

    felder = {"investitionen": {"3": {"felder": {"km_gefahren": {"strategie": "sensor", "sensor_id": "sensor.km"}}}}}
    assert _build_counter_map(SimpleNamespace(sensor_mapping=felder)) == {}
    mit_quellen = {**felder, "quellen": {"inv_energy_3_km_gefahren": {"quelle": "ha_connector",
                                                                      "entity_id": "sensor.km"}}}
    assert _build_counter_map(SimpleNamespace(sensor_mapping=mit_quellen)) == {"inv:3:km_gefahren": "sensor.km"}


# ═══ 2 · Layer (K4-4, H1) ═════════════════════════════════════════════════════

@pytest.mark.parametrize("pv, ladung, soll", [
    (9.8, 14.7, 67), (0.0, 5.0, 0), (5.0, 5.0, 100), (None, 5.0, None), (1.0, None, None),
    (1.0, 0.0, None), (1.0, -2.0, None), (6.0, 5.0, None), (-0.5, 5.0, None),
])
def test_pv_anteil_gemessen_prozent(pv, ladung, soll):
    assert pv_anteil_prozent(pv, ladung, stellen=0, nur_gemessen=True) == soll


async def test_pv_anteil_gemessen_gleich_ist_pv_ladeanteil_auf_denselben_mengen(db, monkeypatch):
    """Die neue Layer-Funktion und die bestehende Monats-Quote (``ist_pv_ladeanteil_prozent``, ungerundet) sagen auf
    denselben Mengen dieselbe Zahl — die Konsolidierung ist ein eigenes Päckchen, die Formel ist schon dieselbe."""
    from backend.services.monats_fakten import ableitungen

    for pv, ladung in ((9.8, 14.7), (123.4, 180.0), (0.0, 12.0), (40.0, 40.0)):
        fakten = [SimpleNamespace(emob=SimpleNamespace(ladung_kwh=ladung * 0.4, ladung_pv_kwh=pv * 0.4)),
                  SimpleNamespace(emob=SimpleNamespace(ladung_kwh=ladung * 0.6, ladung_pv_kwh=pv * 0.6))]

        async def _fakten(_db, _aid, *, von=None, bis=None, _f=fakten):
            return _f
        monkeypatch.setattr(ableitungen, "lade_monats_fakten", _fakten)
        ist = await ableitungen.ist_pv_ladeanteil_prozent(db, 1)
        assert pv_anteil_prozent(pv, ladung, stellen=0, nur_gemessen=True) == round(ist), (pv, ladung, ist)


# ═══ 3 · Fahrt heute (K4-2) ═══════════════════════════════════════════════════

async def _mqtt_staende(db, anlage_id: int, key: str, staende: dict[datetime, float]) -> None:
    for ts, wert in staende.items():
        db.add(MqttEnergySnapshot(anlage_id=anlage_id, timestamp=ts, energy_key=key, value_kwh=wert))
    await db.commit()


async def _stundenlauf(db, anlage, von: datetime, bis: datetime) -> None:
    from backend.services.kanal.schreiber import schreibe_eigene_summe

    zp = von
    while zp <= bis:
        await schreibe_eigene_summe(db, anlage, zp)
        await db.commit()
        zp += timedelta(hours=1)


async def _fahrt_saat(db, a, auto):
    """km-Stand 23 000 ab 05:00, +12 km in der Stunde 07, +30 km in der Stunde 16; Fahrverbrauch +2,0 / +5,5 kWh.
    Mitschrift (MQTT) stündlich von 06:05 bis 23:05."""
    km, kwh = {}, {}
    for h in range(5, 23):
        for m in (0, 30):
            t = M0 + timedelta(hours=h, minutes=m)
            km[t] = 23000.0 + (12.0 if h >= 8 else 0.0) + (30.0 if h >= 17 else 0.0)
            kwh[t] = 5000.0 + (2.0 if h >= 8 else 0.0) + (5.5 if h >= 17 else 0.0)
    await _mqtt_staende(db, a.id, f"inv/{auto.id}/km_gefahren", km)
    await _mqtt_staende(db, a.id, f"inv/{auto.id}/verbrauch_kwh", kwh)
    await _stundenlauf(db, a, M0 + timedelta(hours=6, minutes=5), M0 + timedelta(hours=23, minutes=5))


async def test_fahrt_je_tag_summe_der_zuwaechse_erste_zeile_zaehlt_null(db):
    from backend.services.energie_profil.kanal_stunden import fahrt_je_tag

    a, _wb, auto = await _anlage_emob(db)
    await _fahrt_saat(db, a, auto)
    invs = {str(auto.id): auto}
    out = await fahrt_je_tag(db, a, invs, TAG)
    # Die erste Kanalzeile trägt den Tachostand 23 000 (kein Vorstand) — sie zählt 0, nicht 23 000 (S4).
    assert out == {str(auto.id): {"km": pytest.approx(42.0), "verbrauch_kwh": pytest.approx(7.5)}}


async def test_fahrt_je_tag_ohne_kanal_keine_aussage(db):
    from backend.services.energie_profil.kanal_stunden import fahrt_je_tag

    a, _wb, auto = await _anlage_emob(db)
    assert await fahrt_je_tag(db, a, {str(auto.id): auto}, TAG) == {}


# ═══ 4 · Tag-Detail emob_heute (K4-4/K4-5) ════════════════════════════════════

def _detail(pv_je_inv: dict | None = None, grund: dict | None = None):
    return SimpleNamespace(werte_je_inv={"emob_ladung_pv_kwh": pv_je_inv} if pv_je_inv is not None else {},
                           grund_je_feld=grund or {})


async def _tz(db, anlage_id: int, komponenten: dict) -> None:
    db.add(TagesZusammenfassung(anlage_id=anlage_id, datum=TAG, komponenten_kwh=komponenten))
    await db.commit()


async def _heute(db, a, detail):
    from backend.api.routes.energie_profil.tag import _mit_emob_heute
    from backend.models.investition import Investition

    invs = {str(i.id): i for i in (await db.execute(
        select(Investition).where(Investition.anlage_id == a.id))).scalars().all()}
    return {z.investition_id: z for z in await _mit_emob_heute(db, a, invs, TAG, detail)}


async def test_kopfzahl_nur_mit_beiden_gemessenen_mengen(db):
    a, wb, _auto = await _anlage_emob(db)
    await _tz(db, a.id, {f"wallbox_{wb.id}": 14.7})
    z = (await _heute(db, a, _detail({str(wb.id): 9.8})))[wb.id]
    assert (z.typ, z.ladung_kwh, z.ladung_pv_kwh, z.pv_anteil_prozent) == ("wallbox", 14.7, 9.8, 67)


async def test_kopfzahl_ohne_wallbox_kwh_fehlt(db):
    a, wb, _auto = await _anlage_emob(db)
    z = (await _heute(db, a, _detail({str(wb.id): 9.8})))[wb.id]
    assert (z.ladung_kwh, z.ladung_pv_kwh, z.pv_anteil_prozent) == (None, 9.8, None)


async def test_kopfzahl_nur_gemessen_geschaetzter_pv_zaehler_traegt_keine(db):
    """S3: trägt ``grund_je_feld`` einen Grund für ``emob_ladung_pv_kwh``, ist der PV-Wert keine Messung — keine
    PV-Ladung in der Zeile, keine Kopfzahl."""
    a, wb, _auto = await _anlage_emob(db)
    await _tz(db, a.id, {f"wallbox_{wb.id}": 14.7})
    z = (await _heute(db, a, _detail({str(wb.id): 9.8}, {"emob_ladung_pv_kwh": "teilweise"})))[wb.id]
    assert (z.ladung_kwh, z.ladung_pv_kwh, z.pv_anteil_prozent) == (14.7, None, None)


async def test_kopfzahl_pv_groesser_ladung_keine(db):
    a, wb, _auto = await _anlage_emob(db)
    await _tz(db, a.id, {f"wallbox_{wb.id}": 8.0})
    z = (await _heute(db, a, _detail({str(wb.id): 9.8})))[wb.id]
    assert (z.ladung_kwh, z.ladung_pv_kwh, z.pv_anteil_prozent) == (8.0, 9.8, None)


async def test_kopfzahl_nie_aus_dem_live_pfad(db, monkeypatch):
    """S1 (Ü5): der Live-Tageswert (``heute_kwh_pro_komponente``) ist kein Eingang — ohne Tageswert der Wallbox im
    Tag-Detail gibt es keine Ladung und keine Kopfzahl, auch wenn der Live-Pfad eine Zahl hätte."""
    from backend.services import live_history_service

    async def _live(*_a, **_k):
        return {"wallbox_1": 14.7, "wallbox_2": 14.7}
    monkeypatch.setattr(live_history_service, "get_tages_kwh", _live)
    monkeypatch.setattr(live_history_service, "safe_get_tages_kwh", _live)
    a, wb, _auto = await _anlage_emob(db)
    z = (await _heute(db, a, _detail({str(wb.id): 9.8})))[wb.id]
    assert (z.ladung_kwh, z.pv_anteil_prozent) == (None, None)


async def test_eauto_unter_deckender_wallbox_ohne_ladung(db):
    a, wb, auto = await _anlage_emob(db)
    await _tz(db, a.id, {f"wallbox_{wb.id}": 14.7, f"eauto_{auto.id}": 14.7})
    zeilen = await _heute(db, a, _detail())
    assert auto.id not in zeilen          # ohne Fahrt und ohne eigene Ladung keine Zeile
    assert zeilen[wb.id].ladung_kwh == 14.7


async def test_eauto_ohne_wallbox_traegt_ladung_und_fahrt(db):
    a, _wb, auto = await _anlage_emob(db, mit_wallbox=False)
    await _tz(db, a.id, {f"eauto_{auto.id}": 6.25})
    await _fahrt_saat(db, a, auto)
    z = (await _heute(db, a, _detail()))[auto.id]
    assert (z.typ, z.ladung_kwh, z.km, z.fahrverbrauch_kwh, z.pv_anteil_prozent) == ("e-auto", 6.2, 42.0, 7.5, None)


async def test_ladung_heute_aus_dem_leistungspfad_als_betrag(db):
    """K4-N1 (Lab-Fund 28.10.): der Leistungspfad schreibt die Senke negativ in ``komponenten_kwh`` — die Wallbox-Zeile
    trägt den Betrag, die Kopfzahl kommt (vorher −14,7 kWh und keine Kopfzahl). Positive Tageszeile: Probe oben (14,7)."""
    a, wb, _auto = await _anlage_emob(db)
    await _tz(db, a.id, {f"wallbox_{wb.id}": -14.7})
    z = (await _heute(db, a, _detail({str(wb.id): 9.8})))[wb.id]
    assert (z.ladung_kwh, z.ladung_pv_kwh, z.pv_anteil_prozent) == (14.7, 9.8, 67)


async def test_eauto_ladung_aus_dem_leistungspfad_als_betrag(db):
    """K4-N1: E-Auto ohne deckende Wallbox mit negativer Tageszeile (Leistungspfad) trägt den Betrag."""
    a, _wb, auto = await _anlage_emob(db, mit_wallbox=False)
    await _tz(db, a.id, {f"eauto_{auto.id}": -6.2})
    z = (await _heute(db, a, _detail()))[auto.id]
    assert z.ladung_kwh == 6.2


async def test_tag_detail_traegt_emob_heute(db):
    from backend.api.routes.energie_profil.views import get_tag_detail

    a, wb, auto = await _anlage_emob(db)
    await _tz(db, a.id, {f"wallbox_{wb.id}": 14.7})
    await _fahrt_saat(db, a, auto)
    t = await get_tag_detail(a.id, TAG, db)
    zeilen = {z.investition_id: z for z in t.emob_heute}
    assert zeilen[wb.id].ladung_kwh == 14.7 and zeilen[wb.id].pv_anteil_prozent is None
    assert (zeilen[auto.id].km, zeilen[auto.id].fahrverbrauch_kwh, zeilen[auto.id].ladung_kwh) == (42.0, 7.5, None)


async def test_tag_detail_ohne_emob_leer(db):
    a = await factories.anlage(db, anlagenname="Leer", sensor_mapping={})
    from backend.api.routes.energie_profil.views import get_tag_detail

    t = await get_tag_detail(a.id, TAG, db)
    assert t.emob_heute == [] and t.model_dump()["emob_heute"] == []


# ═══ 5 · Kilometerstand live (K4-1, K4-9) ═════════════════════════════════════

class _FakeHa:
    def __init__(self, staende: dict, verfuegbar: bool = True):
        self._s = staende
        self.is_available = verfuegbar
        self.gefragt: list = []

    async def get_sensor_states_batch(self, entity_ids):
        self.gefragt.append(sorted(entity_ids))
        return {e: self._s.get(e) for e in entity_ids}

    async def get_zustand_states_batch(self, entity_ids):
        return {}


def _mqtt(monkeypatch, energie: dict):
    cache = SimpleNamespace(get_energy_data=lambda _aid: dict(energie), get_all_live_inv=lambda _aid: {})
    monkeypatch.setattr(mis, "_mqtt_inbound_service", SimpleNamespace(cache=cache))


def _km_mapping(auto_id: int, *, felder: bool = True, quelle: str | None = None) -> dict:
    m: dict = {"investitionen": {}}
    if felder:
        m["investitionen"][str(auto_id)] = {"felder": {"km_gefahren": {"strategie": "sensor",
                                                                      "sensor_id": "sensor.km"}}}
    if quelle is not None:
        eintrag = {"quelle": quelle}
        if quelle.startswith("ha_"):
            eintrag["entity_id"] = "sensor.km"
        m["quellen"] = {f"inv_energy_{auto_id}_km_gefahren": eintrag}
    return m


async def _staende(db, a):
    return await bml.lade_staende_live(db, a)


async def test_km_stand_aus_ha_vor_mqtt(db, monkeypatch):
    a, _wb, auto = await _anlage_emob(db)
    a.sensor_mapping = _km_mapping(auto.id)
    await db.commit()
    fake = _FakeHa({"sensor.km": (23037.4, "km")})
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: fake)
    _mqtt(monkeypatch, {f"inv/{auto.id}/km_gefahren": 99.0})
    assert await _staende(db, a) == {auto.id: 23037.4}
    assert fake.gefragt == [["sensor.km"]]


async def test_km_stand_aus_mqtt_ohne_ha_entitaet(db, monkeypatch):
    a, _wb, auto = await _anlage_emob(db)
    _mqtt(monkeypatch, {f"inv/{auto.id}/km_gefahren": 61420.0})
    assert await _staende(db, a) == {auto.id: 61420.0}


@pytest.mark.parametrize("quelle, soll", [("mqtt_inbound_standard", 50.0), ("keine", None), ("ha_connector", 7.0)])
async def test_km_stand_quellen_wahl_entscheidet(db, monkeypatch, quelle, soll):
    a, _wb, auto = await _anlage_emob(db)
    a.sensor_mapping = _km_mapping(auto.id, quelle=quelle)
    await db.commit()
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service",
                        lambda: _FakeHa({"sensor.km": (7.0, "km")}))
    _mqtt(monkeypatch, {f"inv/{auto.id}/km_gefahren": 50.0})
    assert (await _staende(db, a)).get(auto.id) == soll


async def test_ohne_sensor_kein_kilometerstand(db, monkeypatch):
    """S6: ein Kilometerstand kommt nur vom zugeordneten Zähler — die Handeingabe ``km_stand`` in den Monatsdaten und
    ein HA-Ausfall machen keinen."""
    a, _wb, auto = await _anlage_emob(db)
    await factories.imd(db, auto.id, 2026, 6, verbrauch_daten={"km_stand": 23000.0, "km_gefahren": 800.0})
    await db.commit()
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: _FakeHa({}))
    _mqtt(monkeypatch, {})
    assert await _staende(db, a) == {}
    a.sensor_mapping = _km_mapping(auto.id)
    await db.commit()
    bml.cache_leeren()
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service",
                        lambda: _FakeHa({"sensor.km": (5.0, "km")}, verfuegbar=False))
    assert await _staende(db, a) == {}


async def test_km_stand_im_takt_ein_abruf(db, monkeypatch):
    a, _wb, auto = await _anlage_emob(db)
    a.sensor_mapping = _km_mapping(auto.id)
    await db.commit()
    fake = _FakeHa({"sensor.km": (100.0, "km")})
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: fake)
    await _staende(db, a)
    await _staende(db, a)
    assert fake.gefragt == [["sensor.km"]]


def test_builder_km_stand_nur_mit_wert_an_jedem_fahrzeug():
    from backend.services.live_komponenten_builder import build_komponenten

    anlage = factories.mach_anlage(id=1, anlagenname="T", sensor_mapping={})
    wb = factories.mach_investition("wallbox", id=6, anlage_id=1, bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1))
    au = factories.mach_investition("e-auto", id=4, anlage_id=1, bezeichnung="ID.4", anschaffungsdatum=date(2024, 1, 1))
    zo = factories.mach_investition("e-auto", id=12, anlage_id=1, bezeichnung="Zoe", anschaffungsdatum=date(2024, 1, 1))
    invs = {"6": wb, "4": au, "12": zo}
    werte = {"6": {"leistung_w": 3700.0}, "4": {"soc": 62.0}, "12": {"soc": 40.0}}
    ohne = build_komponenten(anlage, {}, werte, invs, {})
    mit = build_komponenten(anlage, {}, werte, invs, {}, stand_map={4: 23037.4})
    (wb_ohne,) = [k for k in ohne["komponenten"] if k["key"] == "wallbox_6"]
    (wb_mit,) = [k for k in mit["komponenten"] if k["key"] == "wallbox_6"]
    assert all("km_stand" not in f for f in wb_ohne["fahrzeuge"])
    assert {f["investition_id"]: f.get("km_stand") for f in wb_mit["fahrzeuge"]} == {4: 23037.0, 12: None}
    # ohne Wallbox: fahrzeuge_ohne_wallbox
    nur_autos = build_komponenten(anlage, {}, {"4": {"soc": 62.0}}, {"4": au}, {}, stand_map={4: 99.6})
    assert [f["km_stand"] for f in nur_autos["fahrzeuge_ohne_wallbox"]] == [100.0]


def test_schema_und_demo_tragen_km_stand():
    from backend.api.routes.live_dashboard import LiveFahrzeug

    assert LiveFahrzeug(investition_id=1, label="x").km_stand is None
    assert LiveFahrzeug(investition_id=1, label="x", km_stand=23037.0).km_stand == 23037.0
    from backend.api.routes.live_dashboard import _generate_demo_data

    demo = _generate_demo_data(1, "Demo")
    km = {f["label"]: f.get("km_stand") for k in demo["komponenten"] for f in (k.get("fahrzeuge") or ())}
    assert km == {"VW ID.4": 23037.0, "Renault Zoe": 61420.0}


# ═══ 6 · Preset (K4-7/K4-8) ═══════════════════════════════════════════════════

def test_preset_typen_im_backend_und_in_der_antwort():
    import asyncio

    from backend.api.routes.mqtt_presets import get_presets
    from backend.services.mqtt_presets import list_presets

    je_id = {p.id: p for p in list_presets()}
    assert je_id["evcc_ladepunkt"].typen == ("wallbox",) and je_id["go_echarger"].typen == ("wallbox",)
    assert je_id["sonnen_mqtt"].typen == ("speicher",)
    # Ein Geräte-Preset trägt Typen, ein Anlagen-Preset keine.
    for p in list_presets():
        assert bool(p.typen) == p.erfordert_investition, p.id
    antwort = {p.id: p for p in asyncio.run(get_presets())}
    assert antwort["evcc_ladepunkt"].typen == ["wallbox"] and antwort["opendtu"].typen == []


async def _apply(db, anlage_id: int, inv_id: int):
    from backend.api.routes.mqtt_presets import ApplyPresetRequest, apply_preset

    return await apply_preset(ApplyPresetRequest(preset_id="evcc_ladepunkt", anlage_id=anlage_id, variablen={},
                                                 investition_id=inv_id), db)


async def test_apply_ersetzt_eine_zeile_je_ziel_key(db):
    """S5: zweimal anwenden ⇒ je ``ziel_key`` genau eine aktive Zeile; die zweite Antwort nennt die ersetzten."""
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping

    a, wb, _auto = await _anlage_emob(db)
    r1 = await _apply(db, a.id, wb.id)
    r2 = await _apply(db, a.id, wb.id)
    assert (r1.erstellt, r1.ersetzt) == (11, 0)
    assert (r2.erstellt, r2.ersetzt) == (11, 11)
    zeilen = (await db.execute(select(MqttGatewayMapping).where(MqttGatewayMapping.anlage_id == a.id))).scalars().all()
    ziel = [z.ziel_key for z in zeilen]
    assert len(ziel) == 11 and len(set(ziel)) == 11


async def test_apply_setzt_die_quelle_gateway_je_feld(db):
    from backend.models.anlage import Anlage
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping

    a, wb, _auto = await _anlage_emob(db)
    r = await _apply(db, a.id, wb.id)
    await db.refresh(a)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    quellen = anlage.sensor_mapping.get("quellen") or {}
    zeilen = {z.ziel_key: z.id for z in (await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.anlage_id == a.id))).scalars().all()}
    erwartet_live = {f"inv_live_{wb.id}_{f}": f"live/inv/{wb.id}/{f}" for f in (
        "leistung_w", "sitzung_kwh", "sitzung_dauer_s", "restzeit_min", "phasen_aktiv", "lademodus",
        "evcc_verbunden", "evcc_laedt", "evcc_freigegeben", "fahrzeug_am_ladepunkt")}
    for fid, zk in erwartet_live.items():
        assert quellen.get(fid) == {"quelle": "mqtt_gateway", "mapping_id": zeilen[zk]}, fid
    # Die Zählerstand-Zeile landet am Energie-Feld der Wallbox.
    assert quellen.get(f"inv_energy_{wb.id}_ladung_kwh") == {
        "quelle": "mqtt_gateway", "mapping_id": zeilen[f"energy/inv/{wb.id}/ladung_kwh"]}
    assert (r.quelle_gesetzt, r.ohne_feld) == (11, [])


async def test_apply_zeile_ohne_feld_bleibt_ohne_quelle(db, monkeypatch):
    """Eine Zeile, deren ``ziel_key`` kein Feld der Fläche ist: Zeile da, Quelle unverändert, in ``ohne_feld``."""
    from backend.api.routes import datenquellen
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping

    a, wb, _auto = await _anlage_emob(db)
    orig = datenquellen.build_expected_topics

    async def _ohne_ladung(db_, anlage, investitionen=None):
        return [e for e in await orig(db_, anlage, investitionen=investitionen)
                if not (e["topic"].endswith("/ladung_kwh") and "/energy/inv/" in e["topic"])]
    monkeypatch.setattr(datenquellen, "build_expected_topics", _ohne_ladung)
    r = await _apply(db, a.id, wb.id)
    assert r.ohne_feld == [f"energy/inv/{wb.id}/ladung_kwh"] and r.quelle_gesetzt == 10
    assert (await db.execute(select(MqttGatewayMapping).where(
        MqttGatewayMapping.ziel_key == f"energy/inv/{wb.id}/ladung_kwh"))).scalar_one_or_none() is not None


async def test_apply_ersetzt_auch_die_picker_zeile_mit_namensteil(db):
    """Der Picker schreibt ``live/inv/{id}_{name}/…`` (Standard-Topic-Suffix), das Preset ``live/inv/{id}/…`` — dasselbe
    Feld, also wird die Picker-Zeile ersetzt, nicht verdoppelt."""
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping

    a, wb, _auto = await _anlage_emob(db)
    db.add(MqttGatewayMapping(anlage_id=a.id, quell_topic="alt/topic", ziel_key=f"live/inv/{wb.id}_WB/leistung_w",
                              payload_typ="plain", faktor=1.0, offset=0.0, invertieren=False, aktiv=True))
    await db.commit()
    r = await _apply(db, a.id, wb.id)
    assert r.ersetzt == 1
    topics = [z.quell_topic for z in (await db.execute(select(MqttGatewayMapping).where(
        MqttGatewayMapping.anlage_id == a.id))).scalars().all()]
    assert "alt/topic" not in topics and len(topics) == 11


def test_ziel_key_ohne_namen():
    from backend.services.datenquellen_resolver import ziel_key_ohne_namen

    assert ziel_key_ohne_namen("live/inv/4_SMA_eCharger_22/leistung_w") == "live/inv/4/leistung_w"
    assert ziel_key_ohne_namen("energy/inv/4_SMA/ladung_kwh") == "energy/inv/4/ladung_kwh"
    assert ziel_key_ohne_namen("live/inv/4/leistung_w") == "live/inv/4/leistung_w"
    assert ziel_key_ohne_namen("live/netzbezug_w") == "live/netzbezug_w"
