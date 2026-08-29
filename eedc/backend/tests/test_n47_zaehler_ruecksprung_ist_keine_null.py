"""N-47 — ein Zähler-Rücksprung im Verbrauchsprofil ergibt keine Aussage, keine 0.

``_stunden_zuwaechse`` bildete den Stundenzuwachs bis zum 29.08.2026 als
``max(0.0, v_end - v_start)`` mit dem Kommentar „Counter-Reset → als 0 werten".
Damit wurde aus *unbekannt* eine **gemessene Null**: Die Stunde lieferte eine
vollwertige Stichprobe von 0 kW, die in den Slot-Mittelwert einging und das
Profil dauerhaft nach unten zog.

**Warum das in genau diesem Modul falsch ist**, steht in seinem eigenen
Docstring: *„Alle drei Quellen zählen eine unvollständige Stunde nicht mit"*
(N-45/N-46). Ein ausgelassener Slot ist behandelt — ``_build_profil_result``
nimmt ihn nicht auf, und ``live_wetter.py::_berechne_verbrauchsprofil`` setzt
seine Standard-Grundlast ein (ADR-002/P4). Eine 0 ist dagegen unbehandelbar:
Sie sieht wie eine Messung aus.

⚠ **Und nicht hochgerechnet — das ist eine Entscheidung, keine Auslassung.**
Der Nachbar ``mqtt_energy_history_service._compute_deltas`` behandelt einen
Rücksprung mit ``delta = end_val``. Hier bewusst nicht: Gernots Entscheid vom
28.08.2026 lautet „ein Zähler mit Reset wird abgelehnt, nicht hochgerechnet"
(Kasten in ``services/snapshot/reader.py``). Für ein **Profil** wiegt das
doppelt — es ist ein Mittelwert über viele Tage, eine hochgerechnete Stunde
verzerrt jede künftige Prognose desselben Slots.

**Zwei Sorten Probe, und die zweite ist die eigentliche:**
  1. **Die Regel** — ``_stunden_zuwaechse`` liefert bei einem Rücksprung ``None``.
  2. **Die Naht** — der MQTT-Pfad lässt den betroffenen Slot wirklich aus dem
     Profil fallen, statt ihn mit 0 zu füllen. Eine Regel-Probe allein bliebe
     grün, wenn ``_profil_from_mqtt`` das ``None`` irgendwo in eine 0 umdeutete.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
import backend.services.live_verbrauchsprofil_service as svc

pytestmark = pytest.mark.asyncio

TAGE = 7
#: Uhrzeit, zu der der Zähler auf 0 zurückspringt.
RUECKSPRUNG_STUNDE = 10
#: ⭐ **Betroffen ist die Stunde DAVOR, und das hat die Naht-Probe berichtigt.**
#: Der Rücksprung liegt auf der Grenze 10:00. Das Intervall ``[09:00, 10:00)``
#: liest dort seinen END-Stand (0.0) gegen einen Start von 99.0 ⇒ Rücksprung.
#: Das Intervall ``[10:00, 11:00)`` liest ihn als START-Stand und misst von dort
#: einen sauberen Zuwachs — es merkt gar nichts. Backward-Konvention (Slot ``h``
#: = Intervall ``[h-1, h)``) ⇒ betroffen ist Slot 10, nicht Slot 11.
#: ⚠ Die erste Fassung dieser Datei prüfte Slot 11 und wäre an einer korrekten
#: 1.0 gescheitert — die **Regel**-Proben waren dabei grün. Ein Prüfer, der neben
#: der Fundstelle misst, misst nichts.
RUECKSPRUNG_SLOT = RUECKSPRUNG_STUNDE
#: Der Nachbar-Slot, der seinen vollen Betrag behalten muss.
NACHBAR_SLOT = RUECKSPRUNG_STUNDE + 1


#: ⭐ **Fester Bezugszeitpunkt statt der Prozessuhr** — ein Mittwoch, 12:00.
#: Der Wächter ``test_konformitaet_echte_uhr_in_tests.py`` hat die erste Fassung
#: dieser Datei gemeldet, und er hatte recht: Eine Probe, die ``datetime.now()``
#: liest, wettet auf die Stunde ihres Laufs (N-167). Hier wiegt das doppelt — die
#: Fixture schreibt sieben Tage à 24 Stunden und unterscheidet Werktag/Wochenende;
#: je nach Laufzeitpunkt lägen andere Wochentage im Fenster, und die Suite fährt
#: in drei Zeitzonen. ⛔ **Bewusst KEIN Baseline-Eintrag:** der Wächter lässt ihn
#: zu, wenn es „wirklich nicht geht" — hier geht es, es braucht nur eine gestellte
#: Modul-Uhr. Gemessen: Das Fenster trägt damit **5 Werktage und 2 Wochenendtage**,
#: also beide Hälften über der Schwelle von ``_build_profil_result``.
JETZT = datetime(2026, 5, 13, 12, 0)


class _GestellteUhr(datetime):
    """``datetime`` mit festem ``now()`` — alles andere unverändert geerbt.

    Wird per ``monkeypatch`` in das Service-Modul gesetzt. Erben statt Nachbauen
    ist Absicht: ``_fenster_start`` ruft ``datetime.combine``, und eine
    handgeschriebene Attrappe müsste jede solche Stelle mitpflegen.
    """

    @classmethod
    def now(cls, tz=None):  # noqa: D102 — Signatur der Basisklasse
        return JETZT


def _erster_tag() -> date:
    """Erster Tag des Profil-Fensters (dieselbe Rechnung wie der Service)."""
    return (JETZT - timedelta(days=TAGE)).date()


def _intervalle() -> list[datetime]:
    start = datetime.combine(_erster_tag(), time()) - timedelta(hours=1)
    return [start + timedelta(hours=i) for i in range(TAGE * 24)]


def _werktage_im_fenster() -> list[date]:
    return [
        t
        for t in (_erster_tag() + timedelta(days=i) for i in range(TAGE))
        if t.weekday() < 5
    ]


# ─── 1. Die Regel ──────────────────────────────────────────────────────────


def _reihe(*staende: float) -> dict[str, tuple[list[datetime], list[float]]]:
    """Eine Zählerreihe mit Ständen auf beiden Stundengrenzen."""
    h_start = datetime(2026, 5, 4, 10, 0)
    zeiten = [h_start, h_start + timedelta(hours=1)]
    return {"netzbezug_kwh": (zeiten, list(staende))}


def test_ein_rueckspringender_zaehler_liefert_keine_stichprobe():
    """Der Kern: ``None`` statt 0.0 — die Stunde ist unvollständig."""
    h_start = datetime(2026, 5, 4, 10, 0)
    h_end = h_start + timedelta(hours=1)

    assert svc._stunden_zuwaechse(_reihe(500.0, 3.0), h_start, h_end) is None


def test_ein_normaler_zuwachs_bleibt_unveraendert():
    """Gegenanker: der gute Fall darf sich nicht mitverändert haben."""
    h_start = datetime(2026, 5, 4, 10, 0)
    h_end = h_start + timedelta(hours=1)

    assert svc._stunden_zuwaechse(_reihe(100.0, 101.5), h_start, h_end) == {
        "netzbezug_kwh": 1.5
    }


def test_eine_echte_null_bleibt_eine_null():
    """Gegenanker, und er ist der wichtigere: **gemessene** 0 ist keine Lücke.

    Ein ruhendes Gerät liefert zwei gleiche Stände. Das ist eine Aussage („in
    dieser Stunde nichts verbraucht") und muss als Stichprobe erhalten bleiben —
    sonst hätte der Fix die Regel „gemessene 0 wird nicht Nichts" gebrochen,
    also genau die Gegenrichtung des Fundes (KONZEPT-UNVOLLSTAENDIGE-WERTE §3).
    """
    h_start = datetime(2026, 5, 4, 10, 0)
    h_end = h_start + timedelta(hours=1)

    assert svc._stunden_zuwaechse(_reihe(100.0, 100.0), h_start, h_end) == {
        "netzbezug_kwh": 0.0
    }


def test_ein_fehlender_randstand_bleibt_unvollstaendig():
    """Gegenanker: der N-45-Fall darf durch den Fix nicht verschwinden."""
    h_start = datetime(2026, 5, 4, 10, 0)
    h_end = h_start + timedelta(hours=1)
    # Nur ein Stand, und der liegt weit vor der Startgrenze ⇒ kein Randwert.
    zeiten = [h_start - timedelta(hours=5)]
    reihen = {"netzbezug_kwh": (zeiten, [100.0])}

    assert svc._stunden_zuwaechse(reihen, h_start, h_end) is None


def test_ein_rueckspringender_zaehler_sperrt_die_ganze_stunde():
    """Mehrere Zähler: einer springt zurück ⇒ die Stunde liefert gar nichts.

    Sonst entstünde eine Bilanz aus einem gemessenen und einem geratenen
    Summanden — die Klasse von N-92 („eine Differenz erbt die Lücke jedes
    Summanden").
    """
    h_start = datetime(2026, 5, 4, 10, 0)
    h_end = h_start + timedelta(hours=1)
    zeiten = [h_start, h_end]
    reihen = {
        "netzbezug_kwh": (zeiten, [100.0, 101.0]),   # sauber
        "pv_gesamt_kwh": (zeiten, [900.0, 4.0]),     # Rücksprung
    }

    assert svc._stunden_zuwaechse(reihen, h_start, h_end) is None


# ─── 2. Die Naht ───────────────────────────────────────────────────────────


async def _anlage(db: AsyncSession) -> Anlage:
    anlage = Anlage(
        anlagenname="N-47 Rücksprung",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()
    return anlage


async def _schreibe_snapshots(
    db: AsyncSession, anlage_id: int, *, mit_ruecksprung: bool
) -> None:
    """Kumulativer Netzbezugs-Zähler, 1 kWh je Stunde, alle 5 Minuten abgelegt.

    ``mit_ruecksprung`` setzt den Zähler an jedem Werktag auf der Grenze 10:00
    auf 0 zurück und lässt ihn von dort weiterlaufen — die Bauform eines
    Geräteneustarts. Betroffen ist damit das Intervall ``[09:00, 10:00)``, das
    diese Grenze als END-Stand liest (⇒ Slot 10).
    """
    stand = 100.0
    for beginn in _intervalle():
        springt = (
            mit_ruecksprung
            and beginn.hour == RUECKSPRUNG_STUNDE
            and beginn.date() in _werktage_im_fenster()
        )
        if springt:
            stand = 0.0
        for minute in range(0, 60, 5):
            db.add(
                MqttEnergySnapshot(
                    anlage_id=anlage_id,
                    timestamp=beginn + timedelta(minutes=minute),
                    energy_key="netzbezug_kwh",
                    value_kwh=stand,
                )
            )
        stand += 1.0
    db.add(
        MqttEnergySnapshot(
            anlage_id=anlage_id,
            timestamp=_intervalle()[-1] + timedelta(hours=1),
            energy_key="netzbezug_kwh",
            value_kwh=stand,
        )
    )
    await db.flush()


@pytest_asyncio.fixture
def mqtt_session(monkeypatch, db: AsyncSession):
    """Test-DB unterschieben **und** die Uhr des Service-Moduls stellen.

    ``_profil_from_mqtt`` öffnet eine eigene Session und bestimmt sein
    Sieben-Tage-Fenster über ``datetime.now()`` (``:548``). Beides wird hier
    gestellt, damit die Probe weder von der Laufzeit-DB noch von der Stunde ihres
    Laufs abhängt.
    """

    @asynccontextmanager
    async def _fake_get_session():
        yield db

    monkeypatch.setattr("backend.core.database.get_session", _fake_get_session)
    monkeypatch.setattr(svc, "datetime", _GestellteUhr)
    return db


async def test_naht_der_ruecksprung_slot_faellt_aus_dem_profil(
    db: AsyncSession, mqtt_session
):
    """Die eigentliche Probe: der betroffene Slot steht **gar nicht** im Profil.

    Vorher stand er dort mit **0.0** — als Messung ununterscheidbar von einer
    Stunde ohne Verbrauch. Der Konsument konnte die Lücke deshalb nicht erkennen
    und seine Standard-Grundlast nicht einsetzen (ADR-002/P4).
    """
    anlage = await _anlage(db)
    await _schreibe_snapshots(db, anlage.id, mit_ruecksprung=True)

    profil = await svc._profil_from_mqtt(anlage.id)

    assert profil is not None
    werktag = profil["werktag"]
    assert RUECKSPRUNG_SLOT not in werktag, (
        f"Slot {RUECKSPRUNG_SLOT} steht mit {werktag.get(RUECKSPRUNG_SLOT)} im Profil — "
        "ein Rücksprung darf keine Stichprobe erzeugen"
    )
    # Gegenanker: die übrigen Slots sind unberührt und tragen ihren vollen Wert.
    assert werktag, "das Profil ist ganz leer — der Fix hat zu viel gesperrt"
    assert werktag.get(NACHBAR_SLOT) == pytest.approx(1.0), (
        "der Nachbar-Slot muss seinen vollen Betrag behalten — der Nachholzuwachs "
        "darf nicht in die Stunde nach dem Rücksprung rutschen"
    )


async def test_naht_ohne_ruecksprung_ist_der_slot_da(db: AsyncSession, mqtt_session):
    """Gegenanker zur Naht: ohne Rücksprung steht der Slot ganz normal drin.

    Ohne ihn wäre die Probe darüber auch dann grün, wenn ``_profil_from_mqtt``
    diesen Slot aus einem ganz anderen Grund nie liefert.
    """
    anlage = await _anlage(db)
    await _schreibe_snapshots(db, anlage.id, mit_ruecksprung=False)

    profil = await svc._profil_from_mqtt(anlage.id)

    assert profil is not None
    assert profil["werktag"].get(RUECKSPRUNG_SLOT) == pytest.approx(1.0)
