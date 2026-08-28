"""F-66 — ein MQTT-Energy-Topic trägt einen ZÄHLERSTAND, keine Monatsmenge.

Gemeldet von **gruaGit** (Discussion #396, 27.08.2026), Docker-Standalone ohne
Home Assistant, alle Werte per MQTT. Der Monatsabschluss stellte in **elf**
Feldern den Lebenszählerstand neben den Monatswert und meldete „weicht ab":

    Einspeisung   552,75 kWh gespeichert · „Sensor meldet 6675,3"
    Netzbezug      28,09 kWh gespeichert · „Sensor meldet 6424,8"
    PV Fronius    915,5  kWh gespeichert · „Sensor meldet 37158,6"
    Gefahrene km  1001   km  gespeichert · „Sensor meldet 13272"   ← Tachostand

Daneben stand „Sensorwert übernehmen" — ein Klick hätte den Lebensstand als
Monatsmenge gespeichert.

⭐ **Der Absender hat alles richtig gemacht.** Die Topic-Registry verlangt genau
das: *„Zählerstand der ins Netz eingespeisten Energie"*, *„Kumulierter kWh-
Zählerstand"*. Die Leser haben ihn als Menge gedeutet.

⛔ **Die Klasse war schon einmal halb behandelt.** Bis zur Dirk-PN vom
2026-06-01 hieß das Label „… Monat (kWh)" und wurde als irreführend berichtigt
— **der Wortlaut, nicht die Leser**. Zweieinhalb Monate später meldete gruaGit
die Folge. Diese Datei hält deshalb die *Rechnung* fest, nicht die Beschriftung.

Zwei Leser waren betroffen, und der zweite wog schwerer als der gemeldete:
  * `monatsabschluss/views.py` — ein **Vorschlag** (sichtbar, falsch, gefährlich)
  * `aktueller_monat.py` — ein **`update` in der Prioritätskette**: im laufenden
    Monat verdrängte der Stand den gespeicherten Wert. Ohne HA — der Normalfall
    dieser Aufstellung — gewann er gegen alles.

Schwesterdateien: test_mqtt_compute_deltas_pv_aggregation.py (der TAGES-Pfad
derselben Reihe, `_compute_deltas`) und
test_aktueller_monat_datenquellen_prioritaet.py (die Kette, in die das Ergebnis
hier einläuft — dort steht, WER gewinnt, hier WAS geliefert wird).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services import mqtt_inbound_service as mqtt_mod
from backend.services.mqtt_energy_history_service import mqtt_monats_deltas

# gruaGits Zahlen, damit die Probe beim Namen nennt, was sie prüft.
STAND_ANFANG = 6122.55
STAND_JETZT = 6675.30
MENGE_IM_MONAT = round(STAND_JETZT - STAND_ANFANG, 1)  # 552,8 kWh

# ⛔ **Kein `datetime.now()` in dieser Datei.** Eine Probe, die die Prozessuhr
# liest, wettet auf die Stunde ihres Laufs (N-167), und die Suite fährt in drei
# Zeitzonen. Der Wächter `test_konformitaet_echte_uhr_in_tests.py` hat den
# ersten Entwurf dieser Datei genau dafür rot gemeldet — zu Recht: Der Fall
# „laufender Monat, aber noch keine volle Stunde vergangen" hätte sie in der
# ersten Stunde jedes Monatsersten kippen lassen.
# Möglich ist der feste Wert, weil beide Prüflinge Monat UND Messzeitpunkt als
# Argument nehmen. Der Wächter hat damit eine Naht erzwungen, die der Prüfling
# ohnehin haben sollte.
FESTER_MONAT = (2025, 3)
MESSZEITPUNKT = datetime(2025, 3, 20, 14, 0)


async def _anlage_mit_monatswert(db: AsyncSession, jahr: int, monat: int) -> int:
    anlage = Anlage(anlagenname="Standalone MQTT", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=jahr, monat=monat,
        einspeisung_kwh=552.75, netzbezug_kwh=28.09,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Fronius",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=10000.0,
    ))
    await db.commit()
    return anlage.id


def _stelle_mqtt_cache(anlage_id: int, werte: dict[str, float]) -> None:
    """Setzt die Singleton-Instanz mit einem gefüllten Energy-Cache.

    ⚠ Bewusst über `on_message` statt durch Setzen von `_energy`: eine Probe,
    die sich ihren Zustand am Produktivweg vorbei herstellt, schützt am Ende die
    Falschaussage ([[feedback_probe_unerreichbarer_zustand]]). So durchläuft der
    Wert dieselbe Topic-Zerlegung wie im Betrieb.
    """
    svc = mqtt_mod.MqttInboundService("localhost", 1883)
    for key, wert in werte.items():
        if key.startswith("inv/"):
            _, inv_id, feld = key.split("/", 2)
            topic = f"eedc/{anlage_id}/energy/inv/{inv_id}/{feld}"
        else:
            topic = f"eedc/{anlage_id}/energy/{key}"
        svc.cache.on_message(topic, str(wert))
    mqtt_mod._mqtt_inbound_service = svc


@pytest.fixture(autouse=True)
def _mqtt_singleton_zuruecksetzen():
    vorher = mqtt_mod._mqtt_inbound_service
    yield
    mqtt_mod._mqtt_inbound_service = vorher


async def _snapshot(db: AsyncSession, anlage_id: int, key: str,
                    zeitpunkt: datetime, wert: float) -> None:
    db.add(SensorSnapshot(
        anlage_id=anlage_id, sensor_key=key, zeitpunkt=zeitpunkt,
        wert_kwh=wert, quelle="mqtt_inbound",
    ))
    await db.commit()


# ---------------------------------------------------------------------------
# Der Kern: Stand → Menge
# ---------------------------------------------------------------------------

async def test_monatsmenge_ist_die_differenz_nicht_der_stand(db: AsyncSession):
    """Aus 6122,55 → 6675,30 wird 552,8 kWh — nicht 6675,3."""
    jahr, monat = FESTER_MONAT
    jetzt = MESSZEITPUNKT
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    await _snapshot(db, anlage_id, "basis:einspeisung",
                    datetime(jahr, monat, 1), STAND_ANFANG)
    await _snapshot(db, anlage_id, "basis:einspeisung",
                    jetzt.replace(minute=0, second=0, microsecond=0), STAND_JETZT)

    mengen = await mqtt_monats_deltas(
        db, anlage_id, jahr, monat, ["einspeisung_kwh"], bis=jetzt,
    )

    assert mengen["einspeisung_kwh"] == MENGE_IM_MONAT
    # Die eigentliche Behauptung — der Lebensstand darf nie herauskommen.
    assert mengen["einspeisung_kwh"] != STAND_JETZT


async def test_ohne_standreihe_gibt_es_KEINE_aussage(db: AsyncSession):
    """Fehlt ein Rand, fehlt das Feld — statt den Stand roh durchzureichen.

    Das ist der Fall des abgeschlossenen Monats, dessen Anfangsstand nicht mehr
    vorliegt. Ein Feld ohne Vorschlag ist ehrlich; ein Feld mit einem Stand
    darin sieht aus wie eine Messung und ist ein Datenverlust.
    """
    jahr, monat = FESTER_MONAT
    jetzt = MESSZEITPUNKT
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    # NUR der aktuelle Stand, kein Monatsanfang.
    await _snapshot(db, anlage_id, "basis:einspeisung",
                    jetzt.replace(minute=0, second=0, microsecond=0), STAND_JETZT)

    mengen = await mqtt_monats_deltas(
        db, anlage_id, jahr, monat, ["einspeisung_kwh"], bis=jetzt,
    )

    assert "einspeisung_kwh" not in mengen


async def test_tachostand_erzeugt_keine_monatskilometer(db: AsyncSession):
    """`km_gefahren` hat keine Zählerreihe ⇒ keine Aussage.

    gruaGits Bild zeigte „Sensor meldet 13272" neben 1001 gefahrenen Kilometern.
    13272 ist ein Tachostand — und das Feld lädt sogar dazu ein („kumulativer
    km-Zähler", `field_definitions`). Ohne Reihe kann eedc daraus keine
    Monatsmenge bilden und behauptet deshalb keine.
    """
    jahr, monat = FESTER_MONAT
    jetzt = MESSZEITPUNKT
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    mengen = await mqtt_monats_deltas(
        db, anlage_id, jahr, monat, ["inv/9/km_gefahren"], bis=jetzt,
    )

    assert mengen == {}


async def test_zaehlerreset_liefert_keine_negative_menge(db: AsyncSession):
    """Springt der Zähler zurück, gibt es keine Aussage statt einer falschen."""
    jahr, monat = FESTER_MONAT
    jetzt = MESSZEITPUNKT
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    await _snapshot(db, anlage_id, "basis:einspeisung",
                    datetime(jahr, monat, 1), STAND_JETZT)
    await _snapshot(db, anlage_id, "basis:einspeisung",
                    jetzt.replace(minute=0, second=0, microsecond=0), 12.0)

    mengen = await mqtt_monats_deltas(
        db, anlage_id, jahr, monat, ["einspeisung_kwh"], bis=jetzt,
    )

    assert "einspeisung_kwh" not in mengen


# ---------------------------------------------------------------------------
# Der zweite Leser: die Prioritätskette von Cockpit → Monat
# ---------------------------------------------------------------------------

async def test_prioritaetskette_bekommt_die_menge_nicht_den_stand(db: AsyncSession):
    """`_collect_mqtt_inbound_data` liefert die Monatsmenge.

    Diese Stelle ist die schwerere: ihr Ergebnis geht per
    `resolved.update(mqtt_energy)` in die Anzeige. Vor dem 27.08. stand hier
    der Lebensstand und verdrängte den gespeicherten Monatswert.
    """
    from backend.api.routes import aktueller_monat as am
    from sqlalchemy import select

    jahr, monat = FESTER_MONAT
    jetzt = MESSZEITPUNKT
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    await _snapshot(db, anlage_id, "basis:einspeisung",
                    datetime(jahr, monat, 1), STAND_ANFANG)
    await _snapshot(db, anlage_id, "basis:einspeisung",
                    jetzt.replace(minute=0, second=0, microsecond=0), STAND_JETZT)
    _stelle_mqtt_cache(anlage_id, {"einspeisung_kwh": STAND_JETZT})

    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )).scalar_one()
    investitionen = list((await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all())

    resolved = await am._collect_mqtt_inbound_data(
        db, anlage, investitionen, jahr, monat, bis=jetzt,
    )

    wert, info = resolved["einspeisung_kwh"]
    assert wert == MENGE_IM_MONAT
    assert wert != STAND_JETZT
    assert info.quelle == "mqtt_inbound"


async def test_ohne_reihe_verdraengt_nichts_den_gespeicherten_wert(db: AsyncSession):
    """Ohne Standreihe bleibt das Feld leer — der gespeicherte Wert überlebt.

    Der Gegenbeweis zur Stelle darüber: Es genügt nicht, dass die Menge richtig
    ist, wenn sie vorliegt. Liegt sie NICHT vor, darf nichts geliefert werden,
    sonst überschreibt `merge_datenquellen` weiterhin einen guten Wert.
    """
    from backend.api.routes import aktueller_monat as am
    from sqlalchemy import select

    jahr, monat = FESTER_MONAT
    jetzt = MESSZEITPUNKT
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)
    _stelle_mqtt_cache(anlage_id, {"einspeisung_kwh": STAND_JETZT})

    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )).scalar_one()

    resolved = await am._collect_mqtt_inbound_data(
        db, anlage, [], jahr, monat, bis=jetzt,
    )

    assert resolved == {}


async def test_abgeschlossener_monat_fragt_den_cache_gar_nicht_erst(db: AsyncSession):
    """Ende zu Ende: Ein vergangener Monat behält seinen gespeicherten Wert.

    `get_aktueller_monat` sammelt MQTT nur für den laufenden Monat — der Cache
    kennt ohnehin nur das Jetzt. Diese Probe hält fest, dass durch die ganze
    Route hindurch **nichts** aus dem Cache in einen abgeschlossenen Monat
    sickert: gespeichert sind 552,75, im Cache steht 6675,3.

    ⚠ Sie prüft bewusst den ABGESCHLOSSENEN Monat und nicht den laufenden. Für
    den laufenden müsste sie die Prozessuhr lesen und wettete damit auf die
    Stunde ihres Laufs (N-167) — genau in der ersten Stunde eines Monatsersten
    gäbe es noch keine volle Stunde zu messen. Was die Route im laufenden Monat
    liefert, steht eine Probe weiter oben am Sammler, und WER in der Kette
    gewinnt, steht in `test_aktueller_monat_datenquellen_prioritaet.py`.
    """
    from backend.api.routes import aktueller_monat as am

    jahr, monat = FESTER_MONAT
    jetzt = MESSZEITPUNKT
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    await _snapshot(db, anlage_id, "basis:einspeisung",
                    datetime(jahr, monat, 1), STAND_ANFANG)
    await _snapshot(db, anlage_id, "basis:einspeisung",
                    jetzt.replace(minute=0, second=0, microsecond=0), STAND_JETZT)
    _stelle_mqtt_cache(anlage_id, {"einspeisung_kwh": STAND_JETZT})

    res = await am.get_aktueller_monat(
        anlage_id=anlage_id, jahr=jahr, monat=monat, db=db,
    )

    assert res.einspeisung_kwh == 552.75
    assert res.einspeisung_kwh != STAND_JETZT


# ---------------------------------------------------------------------------
# Der Monatsbezug — die zweite Hälfte des Fehlers
# ---------------------------------------------------------------------------

async def test_ein_vergangener_monat_bekommt_seine_eigene_menge(db: AsyncSession):
    """Der Cache kennt nur das Jetzt; die Menge muss aus dem MONAT kommen.

    Vor dem 27.08. schlug der Monatsabschluss für jeden geöffneten Monat
    denselben aktuellen Stand vor — ein Vorschlag, der die Frage nicht gehört
    hat, die er beantwortet.
    """
    # Ein fest gewählter, abgeschlossener Monat — unabhängig von der Uhr.
    jahr, monat = 2025, 3
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    await _snapshot(db, anlage_id, "basis:einspeisung",
                    datetime(2025, 3, 1), 1000.0)
    await _snapshot(db, anlage_id, "basis:einspeisung",
                    datetime(2025, 4, 1), 1120.0)
    # Ein viel späterer, viel höherer Stand darf die Antwort nicht verändern.
    await _snapshot(db, anlage_id, "basis:einspeisung",
                    datetime(2025, 8, 1), 5000.0)

    mengen = await mqtt_monats_deltas(db, anlage_id, jahr, monat, ["einspeisung_kwh"])

    assert mengen["einspeisung_kwh"] == 120.0


async def test_grenze_liegt_auf_dem_monatswechsel(db: AsyncSession):
    """Dezember rechnet gegen den 1. Januar des Folgejahres, nicht gegen Monat 13."""
    jahr, monat = 2025, 12
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    await _snapshot(db, anlage_id, "basis:netzbezug",
                    datetime(2025, 12, 1), 300.0)
    await _snapshot(db, anlage_id, "basis:netzbezug",
                    datetime(2026, 1, 1), 345.5)

    mengen = await mqtt_monats_deltas(db, anlage_id, jahr, monat, ["netzbezug_kwh"])

    assert mengen["netzbezug_kwh"] == 45.5


async def test_investitionsfeld_wird_ebenso_differenziert(db: AsyncSession):
    """Nicht nur die Basis — auch `inv/{id}/{feld}` (gruaGits Fronius, 37158,6)."""
    jahr, monat = 2025, 3
    anlage_id = await _anlage_mit_monatswert(db, jahr, monat)

    await _snapshot(db, anlage_id, "inv:7:ladung_kwh", datetime(2025, 3, 1), 4473.9)
    await _snapshot(db, anlage_id, "inv:7:ladung_kwh", datetime(2025, 4, 1), 4700.3)

    mengen = await mqtt_monats_deltas(db, anlage_id, jahr, monat, ["inv/7/ladung_kwh"])

    assert mengen["inv/7/ladung_kwh"] == 226.4  # der Wert aus seinem Screenshot
