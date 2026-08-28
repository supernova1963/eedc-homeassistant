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

import logging
from datetime import datetime, timedelta
from typing import Optional

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


# ── Auf welchem Weg eine Menge entstanden ist ────────────────────────────────
#
# ⭐ **Warum eine Menge ihren Weg mitführt (N-341).** Beide Wege liefern eine
# Zahl in kWh, aber sie sind nicht gleich genau: Die Randdifferenz ist exakt —
# sie liest zwei Zählerstände. Die Reihensumme trägt einen **systematischen
# Abschlag**, weil zwischen der letzten Abtastung vor dem Rücksprung und dem
# Rücksprung selbst noch verbraucht wird und dieser Rest in keinem Stand mehr
# auftaucht. **Gemessen am 28.08.2026** an einer stündlich abgetasteten Reihe
# über 14 Tage mit realistischem Haushaltsprofil: **−3,1 %**, und der Abschlag
# geht *immer* in dieselbe Richtung.
#
# Ein Verbraucher, der die Zahl nur anzeigt, darf den Weg ignorieren. Wer sie
# dem Anwender zum **Übernehmen** anbietet, muss ihn nennen — sonst sieht eine
# Zahl mit bekanntem Abschlag aus wie eine exakte Messung, und das ist die
# Klasse, gegen die dieser ganze Pfad gebaut ist (ADR-002/P4).
WEG_RANDDIFFERENZ: str = "randdifferenz"
WEG_REIHENSUMME: str = "reihensumme"


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
    zwischenstaende = await _staende_im_fenster(db, anlage_id, sensor_key, von, bis)
    if not zwischenstaende:
        return False
    folge = [startstand, *zwischenstaende, endstand]
    return any(
        b < a - toleranz_kwh for a, b in zip(folge, folge[1:])
    )


async def _staende_im_fenster(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
) -> list[float]:
    """Die Zwischenstände eines Zählers im Fenster, in zeitlicher Reihenfolge.

    **Die eine Abfrage für beide Fragen an die Reihe** — *ist der Zähler
    gefallen?* ({@link zaehler_faellt_im_fenster}) und *wie viel ist
    zusammengekommen?* ({@link menge_aus_reihe}). Sie zweimal hinzuschreiben
    wäre die F-56-Klasse; und die beiden Antworten dürfen nie
    auseinanderlaufen, sonst summiert die eine Funktion über eine Reihe, in der
    die andere keinen Rücksprung gesehen hat.

    Beide Ränder sind **exklusiv** — sie kommen als Zählerstände von den
    Aufrufern, aus der Self-Healing-Kaskade und nicht aus dieser Tabelle.
    """
    return list((await db.execute(
        select(SensorSnapshot.wert_kwh)
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
    )).scalars().all())


async def menge_aus_reihe(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
    startstand: float,
    endstand: float,
) -> Optional[float]:
    """Menge eines **zurückgesetzten** Zählers aus seiner ganzen Standreihe.

    **Wofür sie da ist (N-341).** Ist ein Zähler im Fenster zurückgesprungen,
    ist die Randdifferenz ``s1 − s0`` keine Menge — das stellt
    {@link zaehler_faellt_im_fenster} fest. Bis zum 28.08.2026 endete die
    Auskunft dort: **keine Zahl**. Für einen „…heute"-Zähler heißt das über
    einen ganzen Monat, dass eedc gar nichts sagen kann, obwohl jede einzelne
    Stunde mitgeschrieben wurde. `MQTT_INBOUND.md` verspricht dem Anwender das
    Gegenteil (*„Ein täglich oder monatlich zurückgesetzter Zähler funktioniert
    ebenfalls"*), und die Reihe trägt die Antwort tatsächlich.

    **Die Rechnung.** Über die Reihe laufen und die Zuwächse addieren. Fällt der
    Stand, ist das der Rücksprung: Dann ist der **neue Stand selbst** der
    Zuwachs seit dem Rücksprung — der Zähler hat bei 0 neu begonnen und steht
    schon wieder dort.

    ⚠ **Die Grenze gehört zur Auskunft, nicht ins Kleingedruckte.** Was zwischen
    der letzten Abtastung vor dem Rücksprung und dem Rücksprung selbst
    verbraucht wird, steht in keinem Stand und fehlt deshalb. Bei stündlicher
    Abtastung sind das **rund 3 %**, gemessen am 28.08.2026 über 14 Tage mit
    realistischem Haushaltsprofil (140,2 gegen 144,8 kWh), und der Abschlag geht
    **immer** in dieselbe Richtung. Deshalb trägt das Ergebnis
    {@link WEG_REIHENSUMME}: Wer die Zahl zum Übernehmen anbietet, sagt es dazu.

    ⛔ **Sie ersetzt die Randdifferenz NICHT.** Ohne Rücksprung ist die
    Randdifferenz exakt und obendrein unempfindlich gegen Lücken in der Reihe —
    ein fehlender Stundenstand kostet sie nichts, die Summe dagegen läuft dann
    über die Lücke hinweg. Diese Funktion wird nur gerufen, **wenn** ein
    Rücksprung festgestellt wurde.

    Args:
        von: Fensteranfang — **exklusiv**, wie bei
            {@link zaehler_faellt_im_fenster}. Der Rand selbst ist
            ``startstand``.
        bis: Fensterende (exklusiv, s. ``von``); der Rand ist ``endstand``.
        startstand: Stand am Fensteranfang, aus der Self-Healing-Kaskade.
        endstand: Stand am Fensterende, ebendaher.

    Returns:
        Die Menge in kWh, oder ``None``, wenn zwischen den Rändern **kein**
        Stand liegt. Dann gibt es nichts zu summieren, was die Randdifferenz
        nicht schon wüsste — und eine Zahl aus zwei Ständen, von denen einer
        hinter einem Rücksprung liegt, wäre genau die falsche Auskunft.
    """
    zwischenstaende = await _staende_im_fenster(db, anlage_id, sensor_key, von, bis)
    if not zwischenstaende:
        return None

    summe = 0.0
    vorher = startstand
    for stand in list(zwischenstaende) + [endstand]:
        d = stand - vorher
        if d >= -TAGESRESET_TOLERANZ_KWH:
            summe += max(0.0, d)
        else:
            # Rücksprung: der Zähler hat neu begonnen, sein jetziger Stand ist
            # der Zuwachs seither.
            summe += max(0.0, stand)
        vorher = stand
    return round(summe, 3)


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
            wert = ha_svc.get_value_at(
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


async def delta_mit_weg(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: str,
    von: datetime,
    bis: datetime,
    quellen_energy: Optional[dict] = None,
) -> tuple[Optional[float], Optional[str]]:
    """Menge eines kumulativen Zählers über ein Zeitfenster — **plus ihr Weg**.

    **Der eine Ort für die Fenster-Regel.** Ein Rücksprung hinterlässt zwei
    Spuren, und beide werden hier geprüft — dieselben zwei wie im Tagesfenster
    (`snapshot/aggregator._tageswert_aus_raendern`):

    1. **Randdifferenz negativ** — der Rücksprung liegt zwischen den Rändern
       und ist an ihnen selbst ablesbar.
    2. **Monotonie der Zwischenstände verletzt**
       ({@link zaehler_faellt_im_fenster}) — ein Zwischenstand liegt über dem
       End- oder unter dem Startstand.

    ⛔ **Weg 2 fehlte hier bis zum 28.08.2026, und das war N-341 (P0).** Der
    Tages-Pfad hatte ihn seit dem 26.08. und begründete in seinem Docstring
    wörtlich, warum er nötig ist: *„Werden beide Ränder eines
    Tagesreset-Zählers vor dem Reset abgetastet, ist d positiv, plausibel und
    still falsch."* **Über einen Monat ist genau das der Normalfall** — der
    Monatspfad wurde einen Tag später ohne Weg 2 geschrieben. Nachgestellt und
    gemessen: ein „…heute"-Zähler ergab **5,6 kWh statt 140,0**, und
    `aktueller_monat.py` zeigte diese Zahl in *Cockpit → Monat* an.

    ⭐ **Ein erkannter Rücksprung endet nicht in „keine Zahl".** Die Reihe ist
    mitgeschrieben, also wird sie summiert ({@link menge_aus_reihe}). Nur wenn
    zwischen den Rändern gar kein Stand liegt, gibt es keine Auskunft.

    Returns:
        ``(menge_kwh, weg)`` mit ``weg`` aus {@link WEG_RANDDIFFERENZ} /
        {@link WEG_REIHENSUMME}, oder ``(None, None)``, wenn keine Aussage
        möglich ist. **Der Weg ist keine Zierde:** die Reihensumme trägt einen
        systematischen Abschlag von rund 3 %, die Randdifferenz nicht.
    """
    snap_von = await get_snapshot(
        db, anlage_id, sensor_key, sensor_id, von, quellen_energy=quellen_energy
    )
    snap_bis = await get_snapshot(
        db, anlage_id, sensor_key, sensor_id, bis, quellen_energy=quellen_energy
    )
    if snap_von is None or snap_bis is None:
        return None, None

    async def _aus_der_reihe(grund: str) -> tuple[Optional[float], Optional[str]]:
        menge = await menge_aus_reihe(
            db, anlage_id, sensor_key, von, bis, snap_von, snap_bis
        )
        if menge is None:
            logger.info(
                f"Zähler-Rücksprung ({grund}) für anlage={anlage_id} "
                f"key={sensor_key} ({von} → {bis}) und keine Zwischenstände "
                f"— keine Aussage"
            )
            return None, None
        logger.info(
            f"Zähler-Rücksprung ({grund}) für anlage={anlage_id} "
            f"key={sensor_key} ({von} → {bis}) → aus der Standreihe summiert: "
            f"{menge:.3f} kWh"
        )
        return menge, WEG_REIHENSUMME

    d = snap_bis - snap_von
    if d < -TAGESRESET_TOLERANZ_KWH:
        return await _aus_der_reihe("negative Randdifferenz")
    if await zaehler_faellt_im_fenster(
        db, anlage_id, sensor_key, von, bis, snap_von, snap_bis
    ):
        return await _aus_der_reihe("Monotonie verletzt")
    return max(0.0, round(d, 3)), WEG_RANDDIFFERENZ


async def delta(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: str,
    von: datetime,
    bis: datetime,
    quellen_energy: Optional[dict] = None,
) -> Optional[float]:
    """Nur die Menge — für Aufrufer, die den Weg nicht brauchen.

    ⚠ **Kein zweiter Rechenweg**: ein Durchreicher auf
    {@link delta_mit_weg}. Dieselbe Bauform wie
    `aggregator._tagesdetail_boundary_diff`, und aus demselben Grund — eine
    Regel, die an zwei Stellen nachgebaut wird, driftet (F-56).
    """
    menge, _weg = await delta_mit_weg(
        db, anlage_id, sensor_key, sensor_id, von, bis,
        quellen_energy=quellen_energy,
    )
    return menge


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
