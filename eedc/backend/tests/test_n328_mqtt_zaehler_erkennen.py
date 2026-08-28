"""N-328/N-328b — eine MQTT-Quelle IST ein Zähler (Discussion #396, gruaGit).

**Der gemeldete Fall.** gruaGit publiziert die PV-Ladung seiner go-e-Wallbox per
MQTT — 1286,62 kWh laufen über das Feld. Der Daten-Checker meldete trotzdem
*„Offen: go-e Charger, Ladung PV"* und behauptete dazu, die Werte blieben „in
Cockpit → Tag auf —". Die Meldung war falsch **und** nicht abstellbar: Der
Beheben-Knopf führte in ein Formular ohne dieses Feld.

**Zwei Wirkungen, eine Ursache.** `_has_zaehler` (Checker) und vier Schleifen des
Snapshot-Aggregators fragten „`strategie == "sensor"`?", also *„hat das Feld
einen HA-Sensor?"*. Ein Feld auf MQTT-Inbound trägt gar keinen
`sensor_mapping`-Eintrag — `datenquellen.py` räumt ihn ausdrücklich weg.
Schlimmer noch: `datenquellen_mapping_sync._inv_eintrag` legt den
Investitions-Teilbaum **nur bei einer HA-Wahl** an, das Gerät war für die
Aufzählung also gar nicht vorhanden.

⭐ **Die Anlage wird über den ECHTEN Weg hergestellt**, nicht per direkt
gesetztem Feld (Lehre aus W-5): `sensor_mapping` entsteht durch die
B8-1-Materialisierung, die Zählerstände durch den echten Snapshot-Writer aus
`MqttEnergySnapshot`-Zeilen. Wer die Zustände von Hand hinschreibt, prüft seine
eigene Annahme.

⛔ **Die Gegenrichtung ist Pflicht, und sie ist der Grund für die halbe
Bauform.** Der erste Entwurf ließ einen `quellen`-Eintrag als Zähler gelten. Die
B8-1-Materialisierung stempelt aber `mqtt_inbound_standard` auf **jedes**
unzugeordnete Feld, ohne MQTT je zu prüfen — der Fix hätte den Checker auf jeder
Bestandsanlage verstummen lassen. `test_stempel_ohne_werte_*` hält das fest.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.daten_checker import DatenChecker
from backend.services.migrations.migrate_datenquellen_materialisieren import (
    materialisiere_datenquellen,
)
from backend.services.snapshot.aggregator import (
    get_komponenten_tageskwh,
    get_tagesdetail_kwh,
)
from backend.services.snapshot.source import SnapshotSource
from backend.services.snapshot.writer import snapshot_anlage
from backend.tests import factories as f


@pytest.fixture(autouse=True)
def _mqtt_fenster_offen(monkeypatch):
    """Das **gleitende** Fenster des Checkers gegen den **festen** Messtag.

    ⛔ **Warum es diese Fixture gibt — der Fehler, den sie behebt, ist am
    28.08.2026 eingetreten.** `DatenChecker.check_anlage` fragt nach
    MQTT-Zaehlerstaenden der letzten `MQTT_AKTIV_TAGE` = 7 Tage und bildet das
    Fenster selbst aus `datetime.now()`; ein Datum nimmt er nicht entgegen (und
    soll es auch nicht — die Proben rufen ihn bewusst wie die Produktion).

    Am Bau-Tag (27.08.) war `TAG` genau sieben Tage alt und lag knapp im
    Fenster: alles gruen. Einen Tag spaeter war er acht Tage alt, und drei
    Proben meldeten rot, **ohne dass sich eine Zeile Produktcode geaendert
    hatte.** Ein fester Messtag gegen ein gleitendes Fenster ist eine Wette auf
    den Tag der Entstehung — sie ist nach 24 Stunden verloren gegangen.

    ⭐ **Der Ausweg ist nicht `date.today()` in der Fixture** (das verbietet der
    Uhr-Waechter zu Recht: es macht die Probe von Uhr UND Zone abhaengig), und
    auch keine gestellte Uhr (`freezegun` ist verworfen, Entscheid 23.08.).
    Stattdessen wird die **Groesse geweitet, die den Konflikt erzeugt**: Das
    Fenster deckt jeden Kalendertag ab, der feste Messtag bleibt fest.

    ⚠ **Was dadurch NICHT mehr geprueft wird:** dass es das Fenster ueberhaupt
    gibt (ein Topic, das seit Wochen schweigt, soll gemeldet werden). Das ist
    auch nicht Gegenstand dieser Datei — sie prueft, ob eine MQTT-Quelle als
    Zaehler **erkannt** wird. Wer das Fenster selbst pruefen will, braucht eine
    eigene Probe mit zwei Staenden verschiedenen Alters.
    """
    import backend.services.daten_checker as dc
    monkeypatch.setattr(dc, "MQTT_AKTIV_TAGE", 36_500, raising=True)

#: Der Messtag der nachgestellten Anlage — **fest**, wie der Uhr-Waechter es
#: verlangt (`test_konformitaet_echte_uhr_in_tests.py`): die Suite laeuft in
#: drei Zeitzonen, und ein fester Wert ist in allen dreien derselbe.
TAG = date(2026, 8, 20)


# ─────────────────────────────────────────────────────────────────────────
# Die nachgestellte Anlage: Standalone, alles per MQTT
# ─────────────────────────────────────────────────────────────────────────

async def _mqtt_anlage(db, *, mit_werten: bool = True):
    """Basis + WP + Wallbox, ausschließlich per MQTT gespeist.

    Args:
        mit_werten: False ⇒ dieselbe Anlage, dieselben Stempel, aber **keine
            einzige MQTT-Nachricht**. Das ist die Bestandsanlage, die der
            erste Fix-Entwurf blind gemacht hätte.
    """
    anlage = await f.anlage(db, anlagenname="Standalone")
    wp = await f.investition(db, anlage.id, "waermepumpe", bezeichnung="WP")
    wb = await f.investition(db, anlage.id, "wallbox", bezeichnung="go-e Charger")
    await db.commit()

    # (1) Echter Weg zur `quellen`-Ablage: die B8-1-Materialisierung. Sie
    #     stempelt konservativ Inbound auf jedes unzugeordnete Feld.
    await materialisiere_datenquellen(db)
    await db.commit()
    await db.refresh(anlage)

    if mit_werten:
        # (2) Echter Weg zu den Zählerständen: MqttEnergySnapshot-Zeilen, wie
        #     `mqtt_energy_history_service.snapshot_energy_cache` sie schreibt.
        #     Anfangs- und Endstand des Tagesfensters, dazu die Stunde davor,
        #     damit der Writer beide Ränder findet.
        staende = {
            "einspeisung_kwh": (1000.0, 1012.0),
            "netzbezug_kwh": (2000.0, 2008.0),
            f"inv/{wp.id}/stromverbrauch_kwh": (500.0, 507.0),
            f"inv/{wb.id}/ladung_kwh": (300.0, 318.0),
            f"inv/{wb.id}/ladung_pv_kwh": (1286.62, 1298.62),
        }
        for key, (start, ende) in staende.items():
            for ts, wert in (
                (datetime.combine(TAG, datetime.min.time()), start),
                (datetime.combine(TAG, datetime.min.time()) + timedelta(days=1), ende),
            ):
                db.add(MqttEnergySnapshot(
                    anlage_id=anlage.id, timestamp=ts, energy_key=key, value_kwh=wert,
                ))
        await db.commit()

        # (3) Echter Weg zu den SensorSnapshots: der Produktions-Writer.
        for ts in (
            datetime.combine(TAG, datetime.min.time()),
            datetime.combine(TAG, datetime.min.time()) + timedelta(days=1),
        ):
            await snapshot_anlage(db, anlage, zeitpunkt=ts)
        await db.commit()

    return anlage, {str(wp.id): wp, str(wb.id): wb}


# ─────────────────────────────────────────────────────────────────────────
# Vorbedingung: Der Aufbau ist wirklich MQTT-only
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aufbau_hat_keinen_einzigen_ha_sensor(db):
    """Kein `felder`-Eintrag, kein Investitions-Teilbaum — genau der Zustand,
    in dem die alte Bauform das Gerät gar nicht erst aufzählte."""
    anlage, _ = await _mqtt_anlage(db)
    mapping = anlage.sensor_mapping or {}

    assert not (mapping.get("investitionen") or {}), (
        "Die nachgestellte Anlage hätte einen Investitions-Teilbaum — dann prüft "
        "der Test nicht den gemeldeten Fall, sondern eine HA-Anlage."
    )
    quellen = mapping.get("quellen") or {}
    assert quellen, "B8-1 hat nichts materialisiert — der Aufbau greift nicht"
    assert all(
        e.get("quelle") == "mqtt_inbound_standard" for e in quellen.values()
    ), "Erwartet: ausschließlich Inbound-Stempel"

    # Und die Snapshots sind wirklich über den MQTT-Zweig entstanden.
    quellen_der_snaps = {
        s.quelle for s in (await db.execute(
            __import__("sqlalchemy").select(SensorSnapshot).where(
                SensorSnapshot.anlage_id == anlage.id
            )
        )).scalars().all()
    }
    assert quellen_der_snaps == {SnapshotSource.MQTT_INBOUND}, (
        f"Snapshots kamen nicht aus MQTT: {quellen_der_snaps}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Hälfte 1 — die drei Falschmeldungen sind weg (N-328)
# ─────────────────────────────────────────────────────────────────────────

async def _checker_meldungen(db, anlage_id) -> list:
    """Über den ECHTEN Einstieg, nicht über `_check_energieprofil_abdeckung`.

    ⛔ Absichtlich: `mqtt_zaehler` ist ein Parameter mit Default `None`. Wer die
    Methode direkt ruft, prüft den Fix an einem Aufrufer, den es in der
    Produktion nicht gibt — und ein vergessenes Durchreichen in
    `daten_checker/__init__.py` bliebe unbemerkt.
    """
    return (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse


@pytest.mark.asyncio
async def test_checker_meldet_keine_fehlenden_basis_zaehler(db):
    anlage, _ = await _mqtt_anlage(db)
    meldungen = [e.meldung for e in await _checker_meldungen(db, anlage.id)]
    assert not [m for m in meldungen if "Kein Basis-Zähler" in m], (
        f"Basis-Zähler laufen per MQTT, werden aber vermisst: {meldungen}"
    )


#: Der WORTLAUT der Komponenten-Meldung. Ein erster Entwurf dieser Datei suchte
#: „ohne Zuordnung" — eine Zeichenkette, die der Checker nie ausgibt. Die Probe
#: war damit **immer grün** und fiel erst in der Gegenprobe auf, als sie als
#: einzige nicht rot wurde. *Ein Prüfer muss aufs richtige Objekt zeigen.*
_KOMPONENTEN_MELDUNG = "ohne vollständige kWh-Zähler-Abdeckung"


@pytest.mark.asyncio
async def test_checker_meldet_keine_komponente_ohne_abdeckung(db):
    anlage, _ = await _mqtt_anlage(db)
    meldungen = [e.meldung for e in await _checker_meldungen(db, anlage.id)]
    assert not [m for m in meldungen if _KOMPONENTEN_MELDUNG in m], (
        f"WP und Wallbox messen per MQTT: {meldungen}"
    )


@pytest.mark.asyncio
async def test_checker_meldet_keinen_offenen_zusatz_zaehler(db):
    """Die Meldung, die gruaGit gemeldet hat — wörtlich „Ladung PV"."""
    anlage, _ = await _mqtt_anlage(db)
    ergebnisse = await _checker_meldungen(db, anlage.id)
    offen = [
        e for e in ergebnisse
        if "ohne Zusatz-Zähler" in e.meldung
        and "Ladung PV" in (e.details or "")
    ]
    assert not offen, (
        "Der Melder-Fall steht unverändert: "
        + "; ".join(e.details or "" for e in offen)
    )


# ─────────────────────────────────────────────────────────────────────────
# Hälfte 2 — die Tageswerte kommen an (N-328b)
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tagesdetail_liefert_die_pv_ladung(db):
    """Genau der Wert, dessen Fehlen der Checker fälschlich vorhersagte."""
    anlage, invs = await _mqtt_anlage(db)
    detail = await get_tagesdetail_kwh(db, anlage, invs, TAG)

    assert detail.werte.get("emob_ladung_pv_kwh") == pytest.approx(12.0), (
        f"PV-Ladung fehlt in Cockpit → Tag: {detail.werte}"
    )


@pytest.mark.asyncio
async def test_tagesdetail_nennt_nicht_mehr_kein_zaehler_zugeordnet(db):
    """W-18 mitgeprüft: Der Grund darf einem MQTT-Anwender nicht raten, einen
    Sensor zuzuordnen — er hat einen Zähler, nur eben keinen HA-Sensor."""
    anlage, invs = await _mqtt_anlage(db)
    detail = await get_tagesdetail_kwh(db, anlage, invs, TAG)

    assert "emob_ladung_pv_kwh" not in detail.grund_je_feld, (
        "Ein Wert und ein Grund zugleich wäre ein Widerspruch auf der Fläche"
    )
    # Die WP hat keinen Wärmemengenzähler — dort ist „nicht zugeordnet" richtig.
    from backend.core.tageswert_grund import GRUND_NICHT_ZUGEORDNET
    assert detail.grund_je_feld.get("wp_heizung_kwh") == GRUND_NICHT_ZUGEORDNET


@pytest.mark.asyncio
async def test_komponenten_tageskwh_fuellt_basis_und_geraete(db):
    """Die Hauptzahl über den Detailzeilen — `get_komponenten_tageskwh`."""
    anlage, invs = await _mqtt_anlage(db)
    kwh = await get_komponenten_tageskwh(db, anlage, invs, TAG)

    wp_id, wb_id = sorted(invs.keys(), key=int)
    assert kwh.get("einspeisung") == pytest.approx(12.0), kwh
    assert kwh.get("netzbezug") == pytest.approx(8.0), kwh
    assert kwh.get(f"waermepumpe_{wp_id}") == pytest.approx(7.0), kwh
    assert kwh.get(f"wallbox_{wb_id}") == pytest.approx(18.0), kwh


# ─────────────────────────────────────────────────────────────────────────
# Die Gegenrichtung — der Stempel allein ist KEIN Zähler
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stempel_ohne_werte_meldet_weiterhin(db):
    """Dieselbe Anlage, dieselben 31 Inbound-Stempel, keine MQTT-Nachricht.

    ⭐ Ohne diese Probe wäre der verworfene Entwurf („ein `quellen`-Eintrag
    genügt") durch jede andere Prüfung dieser Datei gelaufen — und hätte den
    Daten-Checker auf jeder Bestandsanlage stillgelegt.
    """
    anlage, _ = await _mqtt_anlage(db, mit_werten=False)
    meldungen = [e.meldung for e in await _checker_meldungen(db, anlage.id)]

    assert [m for m in meldungen if "Kein Basis-Zähler" in m], (
        f"Ohne jeden Messwert muss die Basis-Warnung stehen bleiben: {meldungen}"
    )
    assert [m for m in meldungen if _KOMPONENTEN_MELDUNG in m], (
        f"… und die Komponenten-Warnung ebenso: {meldungen}"
    )
    assert [m for m in meldungen if "ohne Zusatz-Zähler" in m], (
        f"… und der Zusatz-Zähler-Hinweis ebenso: {meldungen}"
    )


@pytest.mark.asyncio
async def test_stempel_ohne_werte_liefert_keine_tageswerte(db):
    """Und die Gegenprobe auf der Aggregator-Seite: keine erfundenen Nullen."""
    anlage, invs = await _mqtt_anlage(db, mit_werten=False)

    detail = await get_tagesdetail_kwh(db, anlage, invs, TAG)
    assert detail.werte == {}, f"Werte ohne Messung: {detail.werte}"
    assert await get_komponenten_tageskwh(db, anlage, invs, TAG) == {}
