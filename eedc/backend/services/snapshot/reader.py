"""
Snapshot-Reader.

Single-Snapshot-Read mit Self-Healing-Kaskade (DB → HA Statistics → MQTT-
Energy-Snapshot), Delta-Berechnung über Zeit-Range, sowie Lifetime-Counter-
Read aus drei Quellen (HA-State → HA-Statistics → jüngster Snapshot).

Reader greift auf `writer._upsert_snapshot` zurück, um neu geholte Werte
aus dem Self-Healing zu persistieren — die einseitige Abhängigkeit
reader → writer ist explizit gewollt (writer importiert nichts aus reader).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.ha_statistics_service import get_ha_statistics_service

from backend.services.snapshot.keys import (
    KUMULATIVE_COUNTER_FELDER,
    QUELLE_KEINE_ENERGY,
    _mqtt_key_to_sensor_key,
    _sensor_key_to_mqtt_key,
    extract_quellen_energy,
    ist_stand_sensor_key,
    resolve_energy_snapshot_eid,
)
from backend.services.snapshot.source import SnapshotSource
from backend.services.snapshot.writer import _upsert_snapshot

logger = logging.getLogger(__name__)


#: Toleranz, unterhalb derer ein Rücksprung als Messrauschen gilt (kWh).
TAGESRESET_TOLERANZ_KWH = 0.01


# ── ⛔ Ein Zähler mit Tages-Reset wird abgelehnt, nicht hochgerechnet ────────
#
# **Entscheid Gernot, 28.08.2026 — nicht neu aufrollen.** Beim Bau von N-341
# stand hier zwischenzeitlich eine Reihensumme: Der Rücksprung wurde erkannt und
# die Menge aus allen mitgeschriebenen Ständen aufaddiert statt aus zwei Rändern
# gebildet. **Sie hat funktioniert** — gemessen 140,2 kWh gegen 144,8 wahre,
# also 3,1 % Abschlag, gegenüber 5,6 kWh vorher. Sie ist trotzdem wieder
# entfernt worden, und der Grund ist kein technischer:
#
# > *„Es geht weniger um die Unterstützung des Zählers mit Tages-Reset, als um
# > Datenqualitätssicherung. Ich möchte die Einschränkung bestehen lassen —
# > auch wenn sie mit diesem Bau theoretisch aufhebbar wäre."*
#
# **Das Produkt sagt dasselbe an vier Stellen**, bevor überhaupt ein Wert
# entsteht: Der Daten-Checker rät beim Anlegen eines Helfers ausdrücklich zu
# *Zurücksetzen „nie" (ohne Zyklus)* (`daten_checker/sensoren.py`). Ein
# Monatswert mit systematischem Abschlag, den der Anwender per Knopfdruck in
# seinen Abschluss übernimmt und der dort dauerhaft wie eine Messung aussieht,
# widerspricht dieser Empfehlung — und `soll-waerme-klima.md` §3.1 hält
# denselben Satz für den Tages-Pfad fest: *„Ein Zähler mit Tages-Reset wird
# erkannt und abgelehnt, statt still falsche Werte zu erzeugen."*
#
# ⭐ **Was aus dem Bau bleibt, ist die Erkennung** — und die ist der eigentliche
# Gewinn: Vorher lieferte ein zurückgesetzter Zähler im laufenden Monat eine
# *falsche* Zahl (5,6 statt 140 kWh), und `aktueller_monat.py` zeigte sie an.
# Jetzt liefert er **keine**, und das ist die richtige Auskunft.


#: Fenster, in dem ein MQTT-Topic als „aktiv" gilt (Daten-Checker, Stundenpfad).
MQTT_AKTIV_TAGE = 7


async def mqtt_zaehler_keys(
    db: AsyncSession,
    anlage_id: int,
    seit: Optional[datetime] = None,
) -> set[str]:
    """sensor_keys, für die MQTT-Zählerstände angekommen sind — EINE Abfrage.

    Der positive Beleg hinter `keys.feld_hat_zaehler` Weg 2: nicht „ist ein
    Eintrag hinterlegt", sondern „ist je ein Wert angekommen". Ein
    `SELECT DISTINCT` je Aufruf, kein Zugriff je Feld.

    ⚑ **Nicht neu, sondern eingesammelt.** Genau diese Abfrage stand bis zum
    27.08. inline in `aggregator.get_hourly_kwh_by_category` — der Grund, warum
    der Energiefluss einer MQTT-Anlage gefüllt war, während Tagesansicht und
    Daten-Checker leer blieben bzw. falsch meldeten (N-328/N-328b). Sie steht
    jetzt einmal im Baum; der Stundenpfad ruft sie.

    Args:
        seit: Untergrenze des Zeitfensters.
            * `datetime` → nur **aktive** Topics. Der Daten-Checker und der
              Stundenpfad fragen so (`MQTT_AKTIV_TAGE`): ein Topic, das seit
              Wochen schweigt, ist eine echte Lücke und soll gemeldet werden.
            * ``None`` → **jede** Historie. So fragen die Tages-/Stunden-
              Erhebungen: ein Tag im Frühjahr darf nicht daran scheitern, dass
              das Topic heute stumm ist. Ob für den *angefragten* Tag Werte
              vorliegen, entscheidet danach der Boundary-Diff — und genau das
              ist der Unterschied, den W-18 dem Anwender als Grund nennt.

    ⚠ **Grenze, ehrlich benannt: `mqtt_energy_snapshots` hat 31 Tage Retention**
    (`mqtt_energy_history_service.cleanup_old_snapshots`, Scheduler). Ein Topic,
    das seit **mehr als** 31 Tagen schweigt, taucht auch mit `seit=None` nicht
    mehr auf — seine `SensorSnapshot`-Zeilen bleiben zwar erhalten, werden für
    weit zurückliegende Tage aber nicht mehr aufgezählt. Für jede laufende
    Installation ist das folgenlos (die Keys werden alle 5 Minuten neu
    geschrieben); betroffen wäre nur, wer ein Gerät abgeschaltet hat und danach
    einen alten Tag nachschlägt.

    ⛔ **Warum nicht über `sensor_snapshots` aufgezählt wird**, obwohl diese
    Tabelle keine Retention hat: Sie trägt HA- und MQTT-Zeilen gemeinsam. Sie zu
    befragen hieße, jedem Feld mit *historischen* Ständen wieder einen Zähler
    zuzusprechen — auch dem, dessen Zuordnung der Anwender bewusst entfernt hat.
    Die Frage hier lautet „liefert MQTT dieses Feld?", nicht „gab es hier je
    einen Wert?".

    Returns:
        Menge der `sensor_key`s (`basis:<feld>` / `inv:<id>:<feld>`). Leer,
        wenn nichts per MQTT ankommt.
    """
    bedingungen = [MqttEnergySnapshot.anlage_id == anlage_id]
    if seit is not None:
        bedingungen.append(MqttEnergySnapshot.timestamp >= seit)
    result = await db.execute(
        select(MqttEnergySnapshot.energy_key).where(and_(*bedingungen)).distinct()
    )
    keys: set[str] = set()
    for (mqtt_key,) in result.all():
        sk = _mqtt_key_to_sensor_key(mqtt_key)
        if sk:
            keys.add(sk)
    return keys


async def zaehler_faellt_im_fenster(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
    startstand: float,
    endstand: float,
    toleranz_kwh: float = TAGESRESET_TOLERANZ_KWH,
) -> bool:
    """Ist der Zählerstand innerhalb des Fensters **gefallen**? (SOLL §3.1)

    Ein kumulativer Zähler kann nicht fallen. Seine Reihe ist monoton steigend,
    also gilt für **jeden** Zwischenstand ``s0 ≤ v ≤ s1``. Wird eine der beiden
    Schranken verletzt, ist der Zähler im Fenster zurückgesetzt worden — dann
    ist die Randdifferenz ``s1 − s0`` keine Menge, sondern die Differenz zweier
    unzusammenhängender Zählerläufe.

    ⛔ **Bis zum 28.08.2026 wurden nur die beiden Schranken ``min``/``max``
    gegen die Ränder gehalten — und das ist keine Monotonie-Prüfung, sondern
    eine Extremwert-Prüfung.** Sie ist blind, sobald der Startstand zufällig
    das Minimum und der Endstand das Maximum der Reihe ist: Dann liegt kein
    Zwischenstand außerhalb, obwohl die Reihe vierzehnmal auf null gefallen
    ist. **Gemessen** an einem „…heute"-Zähler über 14 Tage, Fenster vom
    01. 00:00 bis zum 14. 23:00: ``min = start = 0,021``,
    ``max = ende = 10,019`` ⇒ Extremwert-Prüfung **False**, echte
    Monotonie-Prüfung **True**. Real trifft das *Cockpit → Monat*, wenn der
    Anwender es am Monatsletzten spät abends aufruft.

    ⭐ **Jetzt wird die Folge selbst geprüft** — ein einziger fallender Schritt
    genügt, und die Ränder sind ihr erstes und letztes Glied. Damit stimmt die
    Funktion mit ihrem eigenen Namen überein. Der Fall, der die alte Fassung
    überhaupt zur zweiten Schranke brachte, ist darin enthalten: Werden **beide
    Ränder vor** dem Reset abgetastet (s0 = gestriger Tagesstand, s1 =
    heutiger), ist die Randdifferenz positiv und plausibel — der Sturz dazwischen
    steht trotzdem in der Folge.

    ⭐ **Warum diese Prüfung überhaupt nötig ist, obwohl HA sie schon macht.**
    Über HA kommt der Wert aus der Spalte ``sum`` — HAs **reset-bereinigter**
    Lebenszeit-Stand. Ein ``utility_meter`` mit ``daily``-Zyklus erreicht eedc
    deshalb längst monoton (gemessen 26.08.; die Regel steht seit #131/v3.23.8
    und F-58 fest). **Der MQTT-/Standalone-Pfad hat diese Spalte nicht:**
    ``MqttEnergySnapshot.value_kwh`` speichert den rohen publizierten Wert.
    Publiziert eine App einen „…heute"-Zähler, landet er ungefiltert hier.

    Die Prüfung ist deshalb bewusst **quellen-agnostisch** formuliert — sie
    fragt die Zählerreihe selbst, nicht ihre Herkunft. Eine Prüfung, die nur den
    MQTT-Pfad kennt, wäre die nächste Drift-Quelle (F-56-Klasse).

    ⚠ **Was sie NICHT kann:** Liegt im Fenster außer den beiden Rändern kein
    Snapshot, gibt es nichts zu vergleichen — sie meldet dann ``False``. Das ist
    kein Freibrief, sondern die ehrliche Auskunft „nicht feststellbar"; ohne
    Zwischenstände ist ein Tagesreset-Zähler von einem ruhenden Gerät nicht
    unterscheidbar.

    Args:
        von: Fensteranfang — die Snapshot-Abfrage ist **exklusiv**; der Rand
            selbst kommt als ``startstand`` und ist das erste Glied der Folge.
        bis: Fensterende (exklusiv, s. ``von``); der Rand ist ``endstand``.
        startstand: der Stand am Fensteranfang (``s0``).
        endstand: der Stand am Fensterende (``s1``).
    """
    zwischenstaende = [w for _ts, w in await reihe_im_fenster(
        db, anlage_id, sensor_key, von, bis
    )]
    if not zwischenstaende:
        return False
    folge = [startstand, *zwischenstaende, endstand]
    return any(
        _ist_ruecksprung(a, b, toleranz_kwh) for a, b in zip(folge, folge[1:])
    )


def _ist_ruecksprung(vorher: float, nachher: float, toleranz_kwh: float) -> bool:
    """Ist der Zähler von ``vorher`` auf ``nachher`` gefallen?

    **Die Regel selbst, an einer Stelle** — sie beantwortet zwei verschiedene
    Fragen ({@link zaehler_faellt_im_fenster}: *„irgendwo im Fenster?"*,
    {@link finde_zaehler_ruecksprunge}: *„wo genau, und wie oft?"*), und die
    dürfen nie auseinanderlaufen.

    Gleichstand ist kein Rücksprung: ein Zähler, der still steht, steht still.
    Die Toleranz deckt Messrauschen ab.

    ⚑ **Das kWh-Gegenstück zu `zaehlerstaende.finde_reihen_brueche`**, das
    dieselbe Frage für Gas-, Wasser- und Ölzähler beantwortet. Getrennt, weil
    die Reihen in verschiedenen Tabellen mit verschiedenen Punkt-Typen liegen —
    wer eine der beiden ändert, sieht hier, dass es die andere gibt.
    """
    return nachher < vorher - toleranz_kwh


def tageswert_aus_reihe(
    s0: float,
    s1: float,
    zwischenstaende: Sequence[float],
    toleranz_kwh: float = TAGESRESET_TOLERANZ_KWH,
) -> Optional[float]:
    """Die Menge eines kumulativen Zaehlers ueber ein Fenster — **die Regel selbst**.

    **Warum es sie als reine Funktion gibt.** Sie stand bis zum 10.09.2026
    **zweimal** im Baum, und beide Stellen behaupteten im eigenen Docstring, der
    eine Ort zu sein: ``delta`` („Der eine Ort fuer die Fenster-Regel") und
    ``snapshot/aggregator._tageswert_aus_raendern`` („Der eine Ort fuer die
    Tagesfenster-Regel"). Sie waren inhaltlich gleich und **formal schon
    auseinander**: hier die Konstante ``TAGESRESET_TOLERANZ_KWH``, dort das
    Literal ``-0.01``. Genau die F-56-Form, vor der beide Docstrings warnen —
    und an diesem Feld ist die Regel schon einmal gedriftet (N-341: Weg 2 fehlte
    im Monatspfad einen Tag laenger als im Tagespfad, gemessen 5,6 statt
    140,0 kWh).

    Den dritten Aufrufer brachte der Waerme/Klima-Verlauf: Ein Bereichs-Leser
    ueber einen ganzen Monat kann nicht je Tag drei Datenbankabfragen stellen,
    er laedt **eine** Standreihe und wendet die Regel lokal an. Ohne diese
    Funktion haette er sie ein **drittes** Mal hingeschrieben.

    **Ein Ruecksprung hinterlaesst zwei Spuren, und beide sind hier geprueft:**

    1. **Randdifferenz negativ** — der Ruecksprung liegt zwischen den Raendern
       und ist an ihnen selbst ablesbar.
    2. **Monotonie der Folge verletzt** — irgendwo in der Reihe faellt der
       Stand. Dieser Weg laeuft **immer**, nicht nur bei verdaechtig kleinem
       Delta: Werden **beide** Raender eines Tagesreset-Zaehlers vor dem Reset
       abgetastet, ist die Randdifferenz positiv, plausibel und still falsch.

    ⚠ **Ohne Zwischenstaende gilt nur Weg 1** — dieselbe Grenze, die
    {@link zaehler_faellt_im_fenster} mit ihrem fruehen ``False`` zieht: ohne
    Reihe ist ein Tagesreset-Zaehler von einem ruhenden Geraet nicht zu
    unterscheiden. Das ist keine Nachlaessigkeit, sondern die ehrliche Auskunft.

    ⛔ **Ein erkannter Ruecksprung endet in ``None``, nicht in einer
    hochgerechneten Menge** (Entscheid Gernot, 28.08.2026, s. Kanon-Kasten oben).

    Args:
        s0: Stand am Fensteranfang.
        s1: Stand am Fensterende.
        zwischenstaende: die Staende **zwischen** den Raendern, in zeitlicher
            Reihenfolge. Leer ⇒ nur Weg 1.

    Returns:
        Menge in kWh (>= 0), oder ``None`` — „keine Aussage", nie „null"
        (ADR-002/P4). Der Aufrufer protokolliert; diese Funktion ist stumm,
        damit sie rein bleibt.
    """
    d = s1 - s0
    if d < -toleranz_kwh:
        return None
    if zwischenstaende:
        folge = [s0, *zwischenstaende, s1]
        if any(
            _ist_ruecksprung(a, b, toleranz_kwh) for a, b in zip(folge, folge[1:])
        ):
            return None
    return max(0.0, d)


async def finde_zaehler_ruecksprunge(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
    toleranz_kwh: float = TAGESRESET_TOLERANZ_KWH,
) -> list[tuple[datetime, float, float]]:
    """**Wo** die Standreihe fällt — paarweise, mit Zeitpunkt und beiden Ständen.

    {@link zaehler_faellt_im_fenster} beantwortet *„ist hier überhaupt etwas
    passiert?"* und genügt der Aggregation, die danach ohnehin nichts liefert.
    Der Daten-Checker muss es dem **Anwender erzählen** — dafür braucht er den
    Zeitpunkt und die beiden Stände, sonst steht dort eine Behauptung ohne
    Beleg.

    ⚠ **Ohne Randstände.** Diese Frage stellt niemand über ein Auswertungs-
    fenster, sondern über die aufgezeichnete Reihe selbst; die Ränder kämen aus
    der Self-Healing-Kaskade und gehören einer anderen Frage an.

    Returns:
        ``[(zeitpunkt_des_falls, stand_vorher, stand_nachher), …]`` in
        zeitlicher Reihenfolge; leer, wenn die Reihe monoton ist.
    """
    reihe = await reihe_im_fenster(db, anlage_id, sensor_key, von, bis)
    return [
        (ts_b, a, b)
        for (_ts_a, a), (ts_b, b) in zip(reihe, reihe[1:])
        if _ist_ruecksprung(a, b, toleranz_kwh)
    ]


async def reihe_im_fenster(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
) -> list[tuple[datetime, float]]:
    """Die Standreihe eines Zählers im Fenster, in zeitlicher Reihenfolge.

    **Warum die Folge und nicht ``MIN``/``MAX``:** {@link
    zaehler_faellt_im_fenster} hieß Monotonie-Prüfung und verglich bis zum
    28.08.2026 nur die Extrema gegen die Ränder — das ist blind, sobald der
    Startstand zufällig das Minimum und der Endstand das Maximum ist. Die
    Begründung samt Messung steht dort.

    Beide Ränder sind **exklusiv** — sie kommen als Zählerstände vom Aufrufer,
    aus der Self-Healing-Kaskade und nicht aus dieser Tabelle.

    ⚑ **Öffentlich seit dem 10.09.2026**, weil sie einen zweiten Leser bekommen
    hat: `snapshot/aggregator` holt die Reihe jetzt selbst, statt die
    Reset-Prüfung als zweite Fassung mitzuschleppen (s.
    {@link tageswert_aus_reihe}).
    """
    return [
        (ts, wert) for ts, wert in (await db.execute(
            select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh)
            .where(
                and_(
                    SensorSnapshot.anlage_id == anlage_id,
                    SensorSnapshot.sensor_key == sensor_key,
                    SensorSnapshot.zeitpunkt > von,
                    SensorSnapshot.zeitpunkt < bis,
                    SensorSnapshot.wert_kwh.isnot(None),
                )
            )
            .order_by(SensorSnapshot.zeitpunkt)
        )).all()
    ]


async def _get_mqtt_snapshot_at(
    db: AsyncSession,
    anlage_id: int,
    mqtt_key: str,
    zeitpunkt: datetime,
    toleranz_minuten: int = 10,
) -> Optional[float]:
    """
    Liest den zeitlich nächstgelegenen MqttEnergySnapshot um zeitpunkt
    (±toleranz_minuten).

    Wird als MQTT-Fallback genutzt wenn HA Statistics nicht verfügbar ist
    (Standalone/Docker-Modus ohne HA-Integration).

    Standard ±10 min (vorher ±30): MQTT-Publisher liefern Zählerstände
    typischerweise alle 1–5 min. Ein Fenster > 10 min bedeutet fast immer,
    dass der Zielzeitpunkt gar keine frische Publikation hatte — in dem Fall
    ist None + Interpolation in der aufrufenden Schicht (Issue #145) besser
    als ein weit entfernter Wert, der Stunden-Deltas verzerrt.

    Kandidaten werden nach absolutem Zeitabstand sortiert (nearest first),
    nicht nach Timestamp-Reihenfolge — damit der zeitlich passendste Wert
    gewählt wird, nicht zufällig der früheste im Fenster.
    """
    von = zeitpunkt - timedelta(minutes=toleranz_minuten)
    bis = zeitpunkt + timedelta(minutes=toleranz_minuten)
    abstand = func.abs(
        func.julianday(MqttEnergySnapshot.timestamp) - func.julianday(zeitpunkt)
    )
    result = await db.execute(
        select(MqttEnergySnapshot.value_kwh, MqttEnergySnapshot.timestamp).where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.energy_key == mqtt_key,
                MqttEnergySnapshot.timestamp >= von,
                MqttEnergySnapshot.timestamp <= bis,
            )
        ).order_by(abstand.asc()).limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def get_snapshot(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: Optional[str],
    zeitpunkt: datetime,
    toleranz_minuten: int = 5,
    ha_toleranz_minuten: int = 10,
    quellen_energy: Optional[dict] = None,
) -> Optional[float]:
    """
    Holt den kumulativen Zählerstand zu einem bestimmten Zeitpunkt.

    Self-Healing-Reihenfolge:
      1. DB-Lookup in sensor_snapshots (±toleranz_minuten)
      2. HA Statistics via sensor_id (nur wenn sensor_id gesetzt)
      3. MqttEnergySnapshot-Fallback (Standalone-Modus, Issue #135 Blocker 2)

    Args:
        db: Async Session
        anlage_id: Anlagen-ID
        sensor_key: Stabiler Schlüssel (z.B. "inv:4:pv_erzeugung_kwh")
        sensor_id: HA Entity-ID des kumulativen Zählers; None bei MQTT-only
        zeitpunkt: Zielzeitpunkt (typisch: Stundenanfang, 00:00, 01:00 ...)
        toleranz_minuten: Max. zeitliche Abweichung bei DB-Lookup
        ha_toleranz_minuten: Max. zeitliche Abweichung bei HA-Statistics-Fallback.
            Standard 10 min: HA Statistics speichert stündliche Snapshots mit
            start_ts exakt auf der Stunde; eine Abweichung über 10 min bedeutet
            fast immer, dass der Zielzeitpunkt in HA gar keinen Eintrag hat —
            ein nearest-Lookup würde den Nachbar-Wert liefern und zu
            Stunde-Null-mit-Folge-Spike-Artefakten führen (Issue #145).
        quellen_energy: Datenquellen-V4-C2b-Read-Through-Map
            (`extract_quellen_energy(anlage)`). None/leer → heutiges Verhalten
            bitgleich. Mit Eintrag für `sensor_key`: HA → Self-Heal gegen die
            zugeordnete Entity; MQTT → HA-Self-Heal aus (Wert kommt via
            sensor_key aus MQTT-Backup); keine → sofort None (kein Wert, strikt
            kein Fallback — Monatsabschluss manuell, §2d).

    Returns:
        Zählerstand in kWh oder None (kein Datenpunkt verfügbar).
    """
    if quellen_energy:
        sensor_id, behalten = resolve_energy_snapshot_eid(
            quellen_energy, sensor_key, sensor_id
        )
        if not behalten:
            return None  # „keine"-Zuordnung → kein Wert (auch kein DB-Altbestand)

    von = zeitpunkt - timedelta(minutes=toleranz_minuten)
    bis = zeitpunkt + timedelta(minutes=toleranz_minuten)

    abstand = func.abs(
        func.julianday(SensorSnapshot.zeitpunkt) - func.julianday(zeitpunkt)
    )
    result = await db.execute(
        select(SensorSnapshot.wert_kwh).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt >= von,
                SensorSnapshot.zeitpunkt <= bis,
            )
        ).order_by(abstand.asc()).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    # Self-Healing via HA Statistics (wenn HA-Sensor-ID bekannt)
    wert: Optional[float] = None
    quelle: Optional[str] = None
    if sensor_id:
        ha_svc = get_ha_statistics_service()
        if ha_svc.is_available:
            # F-58: Auch der Self-Healing-Read muss die richtige Spalte
            # nehmen — sonst repariert er eine Lücke mit der falschen Größe.
            # ⚠ **`get_value_at` ist synchrones SQLAlchemy gegen die
            # Recorder-Datenbank.** Direkt im `async def` gerufen hielt es den
            # Event-Loop von eedc an — je Zähler, je Rand. Der Snapshot-**Writer**
            # zieht diese Lehre seit Langem und begründet sie in seinem eigenen
            # Kommentar; der Reader tat es bis zum 10.09.2026 nicht. Aufgefallen
            # beim Bereichs-Leser des Wärme/Klima-Verlaufs, der über einen ganzen
            # Monat viele Ränder heilt statt zwei — die Blockade gab es aber schon
            # vorher, bei jedem Aufruf von *Cockpit → Tag* mit einer Lücke.
            # ⛔ `als_stand` MUSS als Schlüsselwort übergeben werden: der vierte
            # positionelle Parameter von `get_value_at` heißt `short_term`. Ein
            # positionelles Argument landete dort und läse still die falsche
            # Spalte — genau die F-58-Klasse, die diese Zeile bewacht.
            wert = await asyncio.to_thread(
                ha_svc.get_value_at,
                sensor_id, zeitpunkt, ha_toleranz_minuten,
                als_stand=ist_stand_sensor_key(sensor_key),
            )
            if wert is not None:
                quelle = SnapshotSource.HA_STATISTICS

    # Fallback: MQTT-Energy-Snapshot (Standalone/Docker-Modus)
    if wert is None:
        mqtt_key = _sensor_key_to_mqtt_key(sensor_key)
        if mqtt_key:
            wert = await _get_mqtt_snapshot_at(db, anlage_id, mqtt_key, zeitpunkt)
            if wert is not None:
                # Self-Healing-Read über MQTT-Backup, wenn HA nichts lieferte —
                # konzeptionell die `live_fallback`-Quelle (siehe source.py).
                quelle = SnapshotSource.LIVE_FALLBACK

    if wert is None:
        logger.debug(
            f"Kein Wert für anlage={anlage_id} key={sensor_key} @ {zeitpunkt} "
            f"(weder HA Statistics noch MQTT-Snapshot)"
        )
        return None

    # Upsert in DB (idempotent bei parallelen Anfragen dank UniqueConstraint)
    assert quelle is not None  # eine der beiden Quellen muss gegriffen haben
    await _upsert_snapshot(db, anlage_id, sensor_key, zeitpunkt, wert, quelle=quelle)
    return wert


async def delta(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: str,
    von: datetime,
    bis: datetime,
    quellen_energy: Optional[dict] = None,
) -> Optional[float]:
    """Menge eines kumulativen Zählers über ein Zeitfenster, oder ``None``.

    **Der eine Ort für die Fenster-Regel.** Ein Rücksprung hinterlässt zwei
    Spuren, und beide werden hier geprüft — dieselben zwei wie im Tagesfenster
    (`snapshot/aggregator._tageswert_aus_raendern`):

    1. **Randdifferenz negativ** — der Rücksprung liegt zwischen den Rändern
       und ist an ihnen selbst ablesbar.
    2. **Monotonie der Folge verletzt**
       ({@link zaehler_faellt_im_fenster}) — irgendwo in der Reihe fällt der
       Stand.

    ⛔ **Weg 2 fehlte hier bis zum 28.08.2026, und das war N-341 (P0).** Der
    Tages-Pfad hatte ihn seit dem 26.08. und begründete in seinem Docstring
    wörtlich, warum er nötig ist: *„Werden beide Ränder eines
    Tagesreset-Zählers vor dem Reset abgetastet, ist d positiv, plausibel und
    still falsch."* **Über einen Monat ist genau das der Normalfall** — der
    Monatspfad wurde einen Tag später ohne Weg 2 geschrieben. Nachgestellt und
    gemessen: ein „…heute"-Zähler ergab **5,6 kWh statt 140,0**, und
    `aktueller_monat.py` zeigte diese Zahl in *Cockpit → Monat* an, ohne dass
    der Anwender etwas anklicken musste.

    ⛔ **Ein erkannter Rücksprung endet in ``None``, nicht in einer
    hochgerechneten Menge.** Die Reihe ließe sich summieren — das war gebaut
    und ist am 28.08.2026 bewusst wieder entfernt worden. Die Begründung steht
    oben beim Kanon-Kasten; sie ist eine Entscheidung über **Datenqualität**,
    keine über Machbarkeit, und sie ist nicht neu aufzurollen.

    Returns:
        Menge in kWh (≥ 0), oder ``None``, wenn ein Rand fehlt oder der Zähler
        im Fenster zurückgesprungen ist. ``None`` heißt „keine Aussage" — nie
        „null" (ADR-002/P4).
    """
    snap_von = await get_snapshot(
        db, anlage_id, sensor_key, sensor_id, von, quellen_energy=quellen_energy
    )
    snap_bis = await get_snapshot(
        db, anlage_id, sensor_key, sensor_id, bis, quellen_energy=quellen_energy
    )
    if snap_von is None or snap_bis is None:
        return None

    # Die Regel selbst steht in {@link tageswert_aus_reihe} — hier wird nur
    # geladen und protokolliert. Bis 10.09.2026 stand sie hier ausgeschrieben,
    # ein zweites Mal in `snapshot/aggregator._tageswert_aus_raendern`, und die
    # beiden waren formal schon auseinander (Konstante gegen Literal).
    zwischenstaende = [w for _ts, w in await reihe_im_fenster(
        db, anlage_id, sensor_key, von, bis
    )]
    wert = tageswert_aus_reihe(snap_von, snap_bis, zwischenstaende)
    if wert is None:
        logger.info(
            f"Zähler-Rücksprung im Fenster für anlage={anlage_id} "
            f"key={sensor_key} ({von} → {bis}): "
            f"{snap_von:.3f} → {snap_bis:.3f} über {len(zwischenstaende)} "
            f"Zwischenstände — keine Aussage"
        )
        return None
    return round(wert, 3)


# ── Der Rückfall auf den ersten Stand im Fenster (N-472) ─────────────────────


@dataclass(frozen=True)
class MengeSeit:
    """Eine Menge **mit** dem Zeitpunkt, ab dem sie wirklich gemessen ist.

    ``seit`` ist der linke Rand, der die Menge trägt — im Regelfall der
    angefragte Fensteranfang, im Rückfall der **erste Stand im Fenster**.
    ``ab_fenster_beginn`` unterscheidet die beiden Fälle, damit ein Aufrufer
    die Einschränkung ausweisen kann, statt sie zu verschweigen (ADR-002/P4).
    """

    menge_kwh: float
    seit: datetime
    bis: datetime
    ab_fenster_beginn: bool


async def erster_stand_im_fenster(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
) -> Optional[datetime]:
    """Der Zeitpunkt des **frühesten** mitgeschriebenen Standes im Fenster.

    Beide Ränder inklusive; ``None`` heißt „in diesem Fenster steht kein
    Stand". Gesucht wird in derselben Reihenfolge, in der {@link get_snapshot}
    liest: zuerst die lokale ``sensor_snapshots``-Reihe, dann — für die
    MQTT-only-Aufstellung, in der es weder HA-Entity noch geheilten Snapshot
    gibt — die 5-Minuten-Reihe ``mqtt_energy_snapshots``.

    ⚠ **Es kommt der Zeitpunkt zurück, nicht der Wert.** Der Wert wird
    anschließend über ``get_snapshot`` geholt, damit die Self-Healing-Kaskade
    und der C2b-Read-Through (``quellen_energy``) auch für den Rückfall-Rand
    gelten — ein hier gelesener Rohwert würde beide umgehen.
    """
    ts = (await db.execute(
        select(func.min(SensorSnapshot.zeitpunkt)).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt >= von,
                SensorSnapshot.zeitpunkt <= bis,
                SensorSnapshot.wert_kwh.isnot(None),
            )
        )
    )).scalar_one_or_none()
    if ts is not None:
        return ts

    mqtt_key = _sensor_key_to_mqtt_key(sensor_key)
    if not mqtt_key:
        return None
    return (await db.execute(
        select(func.min(MqttEnergySnapshot.timestamp)).where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.energy_key == mqtt_key,
                MqttEnergySnapshot.timestamp >= von,
                MqttEnergySnapshot.timestamp <= bis,
                MqttEnergySnapshot.value_kwh.isnot(None),
            )
        )
    )).scalar_one_or_none()


async def letzter_stand_im_fenster(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
) -> Optional[datetime]:
    """Der Zeitpunkt des **spätesten** mitgeschriebenen Standes im Fenster.

    Die Gegenrichtung zu {@link erster_stand_im_fenster}, mit derselben
    Suchreihenfolge und derselben Zusage: Es kommt der **Zeitpunkt** zurück,
    nicht der Wert — der Wert wird anschließend über ``get_snapshot`` geholt,
    damit Self-Healing und C2b-Read-Through auch für diesen Rand gelten.

    ⭐ **Wofür sie gebraucht wird (R-4b, N-491):** der **laufende Tag**. Sein
    rechter Rand liegt in der Zukunft; ohne ihn gibt es heute keinen einzigen
    Tageswert je Gerät, obwohl seit Mitternacht Stände mitgeschrieben werden.
    Der Monat hat dieselbe Frage seit N-472 auf der linken Seite beantwortet.
    """
    ts = (await db.execute(
        select(func.max(SensorSnapshot.zeitpunkt)).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt >= von,
                SensorSnapshot.zeitpunkt <= bis,
                SensorSnapshot.wert_kwh.isnot(None),
            )
        )
    )).scalar_one_or_none()
    if ts is not None:
        return ts

    mqtt_key = _sensor_key_to_mqtt_key(sensor_key)
    if not mqtt_key:
        return None
    return (await db.execute(
        select(func.max(MqttEnergySnapshot.timestamp)).where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.energy_key == mqtt_key,
                MqttEnergySnapshot.timestamp >= von,
                MqttEnergySnapshot.timestamp <= bis,
                MqttEnergySnapshot.value_kwh.isnot(None),
            )
        )
    )).scalar_one_or_none()


async def letzter_stand_vor(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    zeitpunkt: datetime,
    *,
    sensor_id: Optional[str] = None,
    quellen_energy: Optional[dict] = None,
) -> Optional[tuple[datetime, float]]:
    """Der letzte mitgeschriebene Stand **vor** ``zeitpunkt`` — Zeitpunkt **und** Wert.

    ⭐ **Zählerlücken wie HA, T3 (Vorlage Fassung 7).** Der Snapshot-/MQTT-Pfad
    (Standalone) bekommt dieselbe Regel wie der HA-Pfad: fehlt der Stand am
    Fensterbeginn (Vortag 23:00), trägt der **letzte vorhandene Stand davor**,
    beliebig weit zurück. Der erste belegte Slot des Tages ist dann ein
    **Bündel** mit Spanne aus den Zeitstempeln — nicht linear aufgefüllt
    (E1/Ü6: eine interpolierte Stunde ist eine Aussage ohne Messung; über den
    Fensterrand hinweg würde sie Vortagsenergie für die Leser unsichtbar machen).

    Gesucht wird in derselben Reihenfolge wie {@link erster_stand_im_fenster}:
    erst ``sensor_snapshots``, dann ``mqtt_energy_snapshots``. Der **Wert** kommt
    danach über {@link get_snapshot} am gefundenen Zeitpunkt — Self-Healing und
    C2b-Read-Through gelten damit auch für den Anker. Eine „keine"-Zuordnung
    liefert ``None``.

    Returns:
        ``(zeitpunkt, stand_kwh)`` oder ``None`` (kein Stand vor dem Zeitpunkt —
        die Reihe beginnt im Fenster; wie im HA-Pfad kein Anker).
    """
    if quellen_energy:
        _eid, behalten = resolve_energy_snapshot_eid(quellen_energy, sensor_key, sensor_id)
        if not behalten:
            return None
    ts = (await db.execute(
        select(func.max(SensorSnapshot.zeitpunkt)).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt < zeitpunkt,
                SensorSnapshot.wert_kwh.isnot(None),
            )
        )
    )).scalar_one_or_none()
    if ts is None:
        mqtt_key = _sensor_key_to_mqtt_key(sensor_key)
        if mqtt_key:
            ts = (await db.execute(
                select(func.max(MqttEnergySnapshot.timestamp)).where(
                    and_(
                        MqttEnergySnapshot.anlage_id == anlage_id,
                        MqttEnergySnapshot.energy_key == mqtt_key,
                        MqttEnergySnapshot.timestamp < zeitpunkt,
                        MqttEnergySnapshot.value_kwh.isnot(None),
                    )
                )
            )).scalar_one_or_none()
    if ts is None:
        return None
    wert = await get_snapshot(
        db, anlage_id, sensor_key, sensor_id, ts, quellen_energy=quellen_energy,
    )
    if wert is None:
        return None
    return ts, wert


async def delta_mit_rand(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: Optional[str],
    von: datetime,
    bis: datetime,
    quellen_energy: Optional[dict] = None,
    rueckfall_erster_stand: bool = False,
) -> Optional[MengeSeit]:
    """{@link delta} — und, auf Wunsch, der Rückfall auf den ersten Stand (N-472).

    Ohne ``rueckfall_erster_stand`` ist das Ergebnis **bitgleich** zu ``delta``,
    nur um ``seit``/``bis`` ergänzt. Mit dem Schalter gilt zusätzlich:

    > Fehlt der Stand am Fensteranfang, ist der linke Rand der **erste Stand im
    > Fenster**; die Menge gilt dann seit diesem Zeitpunkt und sagt das.

    ⛔ **Der Rückfall greift ausschließlich beim fehlenden LINKEN Rand.** Die
    beiden anderen ``None``-Ursachen behalten ihre Antwort:

    * **fehlender rechter Rand** — dann gibt es keinen zweiten Punkt, zwischen
      dem gemessen werden könnte; ein näherrückender linker Rand hilft nicht.
    * **Zählerrücksprung im Fenster** (N-341) — das ``None`` ist dort eine
      *Entscheidung über Datenqualität*, kein fehlender Punkt. Ein Rückfall
      würde sie aushebeln und aus einer abgelehnten Zahl eine kleinere,
      ebenso falsche machen. Deshalb wird der linke Rand ausdrücklich
      **nachgefragt**, bevor der Rückfall greift: ist er da, war es der
      Rücksprung oder der rechte Rand.

    ⚠ **Der Schalter ist Absicht und steht nicht auf ``True``.** Der zweite
    Leser der Monatsmengen ist der Monatsabschluss-Vorschlag — dort wäre eine
    Menge „seit dem 14." ein Wert, der als **Monatsmenge** gespeichert würde,
    und das ist genau der Datenverlust, gegen den F-66 gebaut ist. Nur die
    Anzeige des laufenden Monats darf einen Teilzeitraum zeigen, weil sie ihn
    beschriften kann.
    """
    wert = await delta(
        db, anlage_id, sensor_key, sensor_id, von, bis,
        quellen_energy=quellen_energy,
    )
    if wert is not None:
        return MengeSeit(menge_kwh=wert, seit=von, bis=bis, ab_fenster_beginn=True)
    if not rueckfall_erster_stand:
        return None

    linker_rand = await get_snapshot(
        db, anlage_id, sensor_key, sensor_id, von, quellen_energy=quellen_energy
    )
    if linker_rand is not None:
        # Der Rand steht — das `None` kam vom rechten Rand oder vom Rücksprung.
        return None

    seit = await erster_stand_im_fenster(db, anlage_id, sensor_key, von, bis)
    if seit is None or seit >= bis:
        return None

    wert = await delta(
        db, anlage_id, sensor_key, sensor_id, seit, bis,
        quellen_energy=quellen_energy,
    )
    if wert is None:
        return None
    return MengeSeit(menge_kwh=wert, seit=seit, bis=bis, ab_fenster_beginn=False)


async def get_counter_lifetime(
    db: AsyncSession,
    anlage,
    inv,
    feld: str,
) -> Optional[float]:
    """
    Liefert den aktuellen Lebensdauer-Stand eines kumulativen Counter-Sensors
    direkt aus der Hersteller-Quelle (z.B. WP-Kompressor-Starts oder
    WP-Betriebsstunden).

    Read-Kaskade: HA-Live-State → HA-Statistics → jüngster SensorSnapshot.
    Keine Berechnung, keine Eichung, keine Drift-Möglichkeit — der Sensor
    selbst ist die Wahrheit. Vergleich gegen EEDC-erfasste Tagesinkremente
    erfolgt im Daten-Checker, nicht im Read-Pfad.

    ⛔ **Die ersten beiden Stufen brauchen eine HA-Entity, die dritte nicht** —
    bis zum 27.08. brach die Funktion trotzdem sofort ab, wenn keine da war
    (`strategie != "sensor"` → `return None`). Wer seine Kompressor-Starts per
    MQTT publiziert, sah die Lebensdauer-Kachel im WP-Dashboard deshalb leer,
    obwohl seine Snapshots geschrieben wurden. Dieselbe Klasse wie N-328b, nur
    auf der Live-Fläche statt in der Tagesansicht. Jetzt werden die HA-Stufen
    **übersprungen** statt die ganze Kaskade abzubrechen; ein ausdrückliches
    „keine" bleibt eine Absage (§2d).

    Returns:
        Aktueller Counter-Stand als Float (Stunden- und Anzahl-Counter
        sind syntaktisch gleich), oder None wenn weder Live-Read noch
        Snapshot ermittelbar. Konsument entscheidet, ob int-Cast für die
        Anzeige sinnvoll ist (Starts: int, Betriebsstunden: 1 Nachkommastelle).
    """
    if feld not in KUMULATIVE_COUNTER_FELDER.get(inv.typ, ()):
        return None

    sensor_mapping = anlage.sensor_mapping or {}
    sensor_key = f"inv:{inv.id}:{feld}"
    inv_data = (sensor_mapping.get("investitionen", {}) or {}).get(str(inv.id))
    config = (inv_data.get("felder", {}) or {}).get(feld) \
        if isinstance(inv_data, dict) else None
    # `mqtt_zaehler_keys` bleibt hier bewusst ungefragt: Stufe 3 liest ohnehin
    # den SensorSnapshot zu diesem `sensor_key` — eine Vorab-Abfrage „gibt es
    # MQTT-Werte?" wäre eine zweite Abfrage für dieselbe Auskunft. Es bleibt
    # allein das Veto aus `feld_hat_zaehler` Regel 3 zu ziehen.
    quelle = (extract_quellen_energy(anlage).get(sensor_key) or (None, None))[0]
    if quelle == QUELLE_KEINE_ENERGY:
        return None  # ausdrückliche Absage des Anwenders (§2d)
    entity_id = config.get("sensor_id") if isinstance(config, dict) else None

    wert: Optional[float] = None
    if entity_id:
        try:
            from backend.services.ha_state_service import get_ha_state_service
            ha_state = get_ha_state_service()
            if ha_state.is_available:
                wert = await ha_state.get_sensor_state(entity_id)
        except Exception as e:
            logger.debug(
                f"lifetime {feld} inv={inv.id}: ha_state Fehler: {type(e).__name__}: {e}"
            )

        if wert is None:
            ha_svc = get_ha_statistics_service()
            if ha_svc.is_available:
                wert = ha_svc.get_value_at(
                    entity_id, datetime.now(), toleranz_minuten=120,
                    als_stand=ist_stand_sensor_key(sensor_key),
                )

    if wert is None:
        result = await db.execute(
            select(SensorSnapshot.wert_kwh).where(
                and_(
                    SensorSnapshot.anlage_id == anlage.id,
                    SensorSnapshot.sensor_key == sensor_key,
                )
            ).order_by(SensorSnapshot.zeitpunkt.desc()).limit(1)
        )
        wert = result.scalar_one_or_none()

    if wert is None:
        return None
    return float(wert)
