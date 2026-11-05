"""Tageswerte kumulativer Zähler über einen **Bereich** — eine Reihe statt N Abfragen.

**Warum es diesen Leser gibt** (10.09.2026, Konzept Wärme/Klima §8,
Bauschnitt 4). Der Wärme/Klima-Verlauf in *Cockpit → Monat* braucht die
gemessene Wärme **je Tag** über einen ganzen Monat. Der bestehende Weg dorthin
ist ``get_tagesdetail_kwh`` — und der ist pro Tag teuer:

* zwei ``get_snapshot``-Abfragen je Feld (die beiden Tagesränder),
* dazu die Standreihe für die Monotonie-Prüfung,

also **drei** Datenbankabfragen je Feld und Tag. Für einen Monat mit einer
Wärmepumpe und zwei Wärmefeldern sind das ~186 Abfragen für **eine** Linie in
einem Diagramm. Dieser Leser lädt stattdessen **eine** Standreihe je Feld über
das ganze Fenster und wertet lokal aus.

⭐ **Die Regel selbst wird geteilt, nicht kopiert.** Die Tagesreset-Behandlung
steht in ``reader.tageswert_aus_reihe``, die Feldmenge in
``aggregator.TAGESDETAIL_AUSGABE``. Beides ist **wegen dieses Lesers** dorthin
gezogen worden: Ohne das hätte er die Regel ein drittes Mal und die Feldliste
ein zweites Mal getragen — und **Bauschnitt 6** (Kälte je Tag) müsste danach an
zwei Stellen gebaut werden.

⚠ **Die Ränder überlappen, und das ist der eigentliche Gewinn:** Das Ende von
Tag N ist der Anfang von Tag N+1. Für 31 Tage braucht es 32 Randstände je Feld,
nicht 62.

## Self-Healing — heilen ja, aber nur die Lücken

``get_snapshot`` hat eine dreistufige Kaskade: lokale Snapshot-Tabelle → HA
Langzeitstatistik → MQTT-Backup; was sie findet, **schreibt sie zurück**. Dieser
Leser deckt Stufe 1 selbst ab und ruft die Kaskade nur für die Ränder, die lokal
fehlen.

⛔ **Warum nicht ganz darauf verzichten** — das war der erste Entwurf und er war
falsch begründet („bis zu 62 HA-Abrufe je Aufruf"): Der geheilte Wert wird
**upsertet**, es ist also ein Einmal-Preis, kein Dauerzustand. Und es gibt
Lagen, in denen lokale Stände systematisch fehlen — allen voran der **Monat, in
dem der Anwender den Zähler zugeordnet hat**: Snapshots entstehen erst ab der
Zuordnung, die Monatswerte davor kommen aus der HA-Langzeitstatistik. Ohne
Heilung bräche die Linie ausgerechnet dort, wo der Verlauf zum ersten Mal
geöffnet wird — und Cockpit → Tag zeigte daneben einen Wert. Das ist die
S1-Verletzung (*dieselbe Größe, überall derselbe Wert*), also die v4.0.1-Klasse.

⚠ **Und die Heilung läuft über ``asyncio.to_thread``.** ``get_value_at`` ist
synchrones SQLAlchemy gegen die Recorder-Datenbank; direkt im ``async def``
gerufen hält es den Event-Loop an. Der Snapshot-**Writer** hat diese Lehre seit
Langem und schreibt sie in seinen eigenen Kommentar (*„hielt den Event-Loop von
eedc an — je Zähler, je Lauf"*); der Reader hat sie nicht, und über einen ganzen
Monat wöge das schwerer als über einen Tag.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.betriebsart_gemessen import (
    geraetefeld_oder_innengeraete,
)
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.snapshot.keys import (
    extract_quellen_energy,
    feld_hat_zaehler,
    innengeraet_felder,
    zaehler_feld_kandidaten,
)
from backend.services.snapshot.reader import (
    get_snapshot,
    letzter_stand_vor,
    mqtt_zaehler_keys,
    tageswert_aus_reihe,
)

logger = logging.getLogger(__name__)

#: Toleranz beim Zuordnen eines Snapshots zu einer Tagesgrenze (Minuten) —
#: dieselbe wie in ``get_snapshot``. Stundenzeilen liegen exakt auf :00, die
#: Toleranz deckt Latenz-Jitter ab.
RAND_TOLERANZ_MINUTEN = 5


def _tagesgrenzen(von: date, bis: date) -> list[datetime]:
    """Die Randzeitpunkte für ``[von, bis]`` — ein Rand mehr als Tage.

    ``bis`` ist **einschließlich**; der letzte Rand ist deshalb der Beginn des
    Folgetags.
    """
    tage = (bis - von).days + 1
    return [
        datetime.combine(von, time.min) + timedelta(days=i) for i in range(tage + 1)
    ]


def _naechster_stand(
    reihe: list[tuple[datetime, float]], ziel: datetime,
) -> Optional[float]:
    """Der Stand, der ``ziel`` am nächsten liegt — innerhalb der Toleranz.

    Dieselbe Auswahl, die ``get_snapshot`` in SQL trifft (``ORDER BY
    abs(zeitpunkt − ziel) LIMIT 1``), nur lokal auf der geladenen Reihe.
    """
    grenze = timedelta(minutes=RAND_TOLERANZ_MINUTEN)
    bester: Optional[tuple[timedelta, float]] = None
    for ts, wert in reihe:
        abstand = abs(ts - ziel)
        if abstand > grenze:
            continue
        if bester is None or abstand < bester[0]:
            bester = (abstand, wert)
    return bester[1] if bester else None


async def lade_tageswerte_je_feld(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    von: date,
    bis: date,
    felder: dict[tuple[str, str], str],
    *,
    rueckwaerts_tage: frozenset[date] | set[date] = frozenset(),
) -> dict[date, dict[str, float]]:
    """Tages-kWh je Ausgabe-Key über ``[von, bis]`` — die Σ über die Geräte.

    Die dünne Hülle über {@link lade_tageswerte_je_geraet}. Wer eine Regel
    anwendet, die **am Gerät** hängt — D1 („Gesamtwert vor Summanden") ist eine
    solche —, ruft die Kernfunktion; hier ist die Auflösung schon vorbei
    (N-391b).
    """
    je_geraet = await lade_tageswerte_je_geraet(
        db, anlage, investitionen_by_id, von, bis, felder,
        rueckwaerts_tage=rueckwaerts_tage,
    )
    return {
        tag: {key: sum(je_inv.values()) for key, je_inv in keys.items()}
        for tag, keys in je_geraet.items()
    }


@dataclass
class _BereichKontext:
    """Die geteilten Eingänge von ``lade_tageswerte_je_geraet`` (RF-57): Anlage und Sitzung, die Zuordnungen
    (``investitionen``-Map, Energie-Quellen, MQTT-Zähler), die Fenster je Tag mit ihren Randzeitpunkten und das Ergebnis
    ``{datum: {ausgabe_key: {inv_id: kWh}}}``, in das die Felder auffalten."""

    db: AsyncSession
    anlage: Any
    investitionen_map: dict
    quellen_energy: dict
    mqtt_keys: set
    fenster_je_tag: dict[date, tuple[datetime, datetime]]
    grenzen: list[datetime]
    ergebnis: dict[date, dict[str, dict[str, float]]] = field(default_factory=dict)


async def lade_tageswerte_je_geraet(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    von: date,
    bis: date,
    felder: dict[tuple[str, str], str],
    *,
    rueckwaerts_tage: frozenset[date] | set[date] = frozenset(),
) -> dict[date, dict[str, dict[str, float]]]:
    """Tages-kWh je Ausgabe-Key **und Gerät** über ``[von, bis]``.

    ⭐ **Warum die Geräte-Ebene der Kern ist und die Summe die Hülle** (N-391b,
    14.09.2026): ``get_tagesdetail_kwh`` liefert beides seit Bauschnitt 6
    (``werte`` und ``werte_je_inv``) — dieser Leser lieferte nur die Summe, und
    der Monatsverlauf konnte D1 deshalb gar nicht je Gerät anwenden. Bei zwei
    verschieden zählenden Wärmepumpen verschluckte der Gesamtwert der einen die
    Aufteilung der anderen, und die Monatssäule nannte eine andere Wärme als der
    Monat daneben. Die Summe ist aus den Geräte-Zahlen jederzeit zu bilden, die
    Geräte-Zahlen aus der Summe nie.

    Args:
        felder: Ausschnitt aus ``aggregator.TAGESDETAIL_AUSGABE``,
            ``(typ, mapping-feld) → ausgabe_key``. Der Aufrufer wählt die
            Teilmenge, die er braucht; die **Namen** kommen aus der einen
            Tabelle.
        rueckwaerts_tage: Tage, deren Wert im Fenster [Vortag 23:00, 23:00)
            gelesen wird statt [00:00, 24:00) — **N-435**. Das sind die Tage,
            deren Tageszeile ihren Wärmepumpen-Strom aus den HA-LTS-Slots trägt
            (``tageszeile_ist_rueckwaerts``). Ohne das nennte die Monatssäule
            eine andere Wärme als *Cockpit → Tag* für denselben Tag, sobald die
            Tagessicht im Fenster ihrer Tageszeile rechnet. Der Aufrufer reicht
            nur Felder herein, deren Gegenstück in diesem Fenster steht.

    Returns:
        ``{datum: {ausgabe_key: {inv_id: kwh}}}``. Ein Tag ohne verwertbaren
        Wert fehlt — ebenso ein Tag, dessen Zähler zurückgesprungen ist.
        **Keine 0 als Platzhalter** (ADR-002/P4: keine Aussage statt einer
        Zahl, die wie eine Messung aussieht).

    Form (RF-57, Bauform RF-1): der Orchestrator läuft über Geräte und Felder — ``_tagesfenster`` (Fenster je Tag,
    N-435, und die Randzeitpunkte) · ``_geraete_aufloesung`` (Gerät überspringen: ``None``, E-Auto mit Parent;
    Zähler-Kandidaten) · ``_tageswerte_des_feldes`` (Gerätefeld und Innengerät-Kopien mit Zähler, je Zähler EINE Reihe
    und die Ränder mit Heilung) · ``_randstaende`` (ein Tag eines Zählers: Lückenanker R1, Rücksprung ⇒ kein Tag) ·
    ``_auffalten`` (Gerätefeld ODER Innengeräte, Akkumulation je Gerät). Geteilte Eingänge: ``_BereichKontext``.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    quellen_energy = extract_quellen_energy(anlage)
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)
    fenster_je_tag, grenzen = _tagesfenster(von, bis, rueckwaerts_tage)
    ctx = _BereichKontext(db=db, anlage=anlage, investitionen_map=investitionen_map, quellen_energy=quellen_energy,
                          mqtt_keys=mqtt_keys, fenster_je_tag=fenster_je_tag, grenzen=grenzen)

    for inv_id_str, inv in investitionen_by_id.items():
        geraet = _geraete_aufloesung(ctx, inv_id_str, inv)
        if geraet is None:
            continue
        typ, geraet_felder, kandidaten = geraet
        for (t, feld), ausgabe_key in felder.items():
            if t != typ:
                continue
            je_tag_je_key = await _tageswerte_des_feldes(ctx, inv_id_str, geraet_felder, kandidaten, feld)
            _auffalten(ctx, je_tag_je_key, feld, ausgabe_key, inv_id_str)

    return ctx.ergebnis


def _tagesfenster(
    von: date, bis: date, rueckwaerts_tage: frozenset[date] | set[date],
) -> tuple[dict[date, tuple[datetime, datetime]], list[datetime]]:
    """Je Tag sein Fenster und die sortierten Randzeitpunkte aller Fenster (RF-57).

    ``[00:00, 24:00)``, an den ``rueckwaerts_tage`` (N-435) ``[Vortag 23:00, 23:00)``; die Ränder sind die Menge der
    Fenster-Enden — benachbarte Tage mit gleichem Fenster teilen ihren Rand.
    """
    # Je Tag sein Fenster: [00:00, 24:00) oder — N-435 — [Vortag 23:00, 23:00).
    # Die Randzeitpunkte aller Tage bilden EINE sortierte Menge; benachbarte
    # Tage mit gleichem Fenster teilen weiterhin ihren gemeinsamen Rand.
    fenster_je_tag: dict[date, tuple[datetime, datetime]] = {}
    for tages_beginn in _tagesgrenzen(von, bis)[:-1]:
        tag = tages_beginn.date()
        start = (
            tages_beginn - timedelta(hours=1)
            if tag in rueckwaerts_tage
            else tages_beginn
        )
        fenster_je_tag[tag] = (start, start + timedelta(days=1))
    grenzen = sorted({ts for paar in fenster_je_tag.values() for ts in paar})
    return fenster_je_tag, grenzen


def _geraete_aufloesung(ctx: _BereichKontext, inv_id_str, inv) -> Optional[tuple[Any, dict, set[str]]]:
    """Das Gerät für den Leser (RF-57): ``None`` überspringt (kein Gerät; E-Auto mit Parent — die Wallbox misst die
    Ladung), sonst ``(typ, Gerätefelder der Zuordnung, Zähler-Kandidaten)`` — die Kandidaten aus beiden Ablagen
    (``felder`` und MQTT, N-328b), aus denen ``_tageswerte_des_feldes`` die Innengerät-Kopien auflöst."""
    if inv is None:
        return None
    typ = getattr(inv, "typ", None)
    # E-Auto mit parent (die Wallbox misst die Ladung) → sonst Doppelzählung;
    # dieselbe Regel wie in `get_tagesdetail_kwh`.
    if typ == "e-auto" and getattr(inv, "parent_investition_id", None) is not None:
        return None
    inv_data = ctx.investitionen_map.get(str(inv_id_str))
    geraet_felder = (inv_data or {}).get("felder", {}) or {}
    kandidaten = zaehler_feld_kandidaten(inv_id_str, geraet_felder, ctx.mqtt_keys)
    return typ, geraet_felder, kandidaten


async def _tageswerte_des_feldes(
    ctx: _BereichKontext, inv_id_str, geraet_felder: dict, kandidaten: set[str], feld: str,
) -> dict[str, dict[date, float]]:
    """Ein Feld eines Geräts (RF-57): ``{feld-key: {tag: kWh}}`` über das Gerätefeld und seine Innengerät-Kopien mit
    Zähler — je Zähler EINE Standreihe über alle Fenster (``_reihe_ueber_bereich``), die Ränder lokal bzw. über die
    Heilungs-Kaskade (``_raender_mit_heilung``), je Tag ``_randstaende``."""
    # Bauschnitt 6: Gerätefeld UND Innengerät-Kopien — dieselbe Menge wie
    # `get_tagesdetail_kwh`, dieselbe Auflösung danach. Die Tabelle ist
    # geteilt; ein Aufrufer, der die Kälte hereinreicht, bekäme sonst
    # still die Antwort ohne Innengeräte.
    je_tag_je_key: dict[str, dict[date, float]] = {}
    for k in (feld, *innengeraet_felder(feld, kandidaten)):
        cfg = geraet_felder.get(k)
        sensor_key = f"inv:{inv_id_str}:{k}"
        if not feld_hat_zaehler(cfg, sensor_key, ctx.quellen_energy, ctx.mqtt_keys):
            continue
        sensor_id = cfg.get("sensor_id") if isinstance(cfg, dict) else None

        reihe = await _reihe_ueber_bereich(
            ctx.db, ctx.anlage.id, sensor_key, ctx.grenzen[0], ctx.grenzen[-1],
        )
        staende = await _raender_mit_heilung(
            ctx.db, ctx.anlage, sensor_key, sensor_id, ctx.quellen_energy, ctx.grenzen, reihe,
        )
        stand_am = dict(zip(ctx.grenzen, staende))

        for tag, fenster in ctx.fenster_je_tag.items():
            wert = await _randstaende(ctx, sensor_key, sensor_id, reihe, stand_am, tag, fenster)
            if wert is not None:
                je_tag_je_key.setdefault(k, {})[tag] = wert
    return je_tag_je_key


async def _randstaende(
    ctx: _BereichKontext,
    sensor_key: str,
    sensor_id: Optional[str],
    reihe: list[tuple[datetime, float]],
    stand_am: dict[datetime, Optional[float]],
    tag: date,
    fenster: tuple[datetime, datetime],
) -> Optional[float]:
    """Ein Tag eines Zählers (RF-57): Randstand-Differenz über das Fenster samt Zwischenständen
    (``tageswert_aus_reihe``); fehlt der Anfangsstand, trägt der Lückenanker R1 (letzter Stand davor, aus der Reihe
    oder beliebig weit zurück) — ``None`` ohne Anfangs- oder Endstand und bei Rücksprung (kein Tag)."""
    tages_start, tages_ende = fenster
    s0, s1 = stand_am[tages_start], stand_am[tages_ende]
    anker_ts = tages_start
    if s0 is None and s1 is not None:
        # ⭐ Zählerlücken wie HA (R1): fehlt der Stand am
        # Tagesbeginn, trägt der letzte Stand davor — zuerst aus
        # der geladenen Reihe, sonst beliebig weit zurück. Die
        # Energie einer Lücke über Mitternacht gehört zu diesem
        # Tag (wie im HA-Dashboard, wie Cockpit → Tag).
        vorher = [(ts, w) for ts, w in reihe if ts < tages_start]
        if vorher:
            anker_ts, s0 = vorher[-1]
        else:
            anker = await letzter_stand_vor(
                ctx.db, ctx.anlage.id, sensor_key, tages_start,
                sensor_id=sensor_id, quellen_energy=ctx.quellen_energy,
            )
            if anker is not None:
                anker_ts, s0 = anker
    if s0 is None or s1 is None:
        return None
    zwischen = [
        w for ts, w in reihe if anker_ts < ts < tages_ende
    ]
    wert = tageswert_aus_reihe(s0, s1, zwischen)
    if wert is None:
        logger.debug(
            "Zähler-Rücksprung im Tagesfenster für anlage=%s key=%s "
            "(%s) — keine Tagesaussage",
            ctx.anlage.id, sensor_key, tag,
        )
    return wert


def _auffalten(
    ctx: _BereichKontext, je_tag_je_key: dict[str, dict[date, float]], feld: str, ausgabe_key: str, inv_id_str,
) -> None:
    """Die Tageswerte eines Feldes in das Ergebnis (RF-57): je Tag Gerätefeld ODER Σ Innengeräte, nie addiert
    (``geraetefeld_oder_innengeraete``); ein Gerät läuft über mehrere ``(typ, feld)``-Paare in denselben Ausgabe-Key
    und wird dort aufaddiert."""
    for tag in ctx.fenster_je_tag:
        wert = geraetefeld_oder_innengeraete(
            {k: w[tag] for k, w in je_tag_je_key.items() if tag in w}, feld,
        )
        if wert is None:
            continue
        # Dieselbe Akkumulation wie in `get_tagesdetail_kwh`: EIN Gerät
        # kann über mehrere (typ, feld)-Paare in denselben Ausgabe-Key
        # laufen, mehrere Geräte ohnehin.
        geraete = ctx.ergebnis.setdefault(tag, {}).setdefault(ausgabe_key, {})
        geraete[str(inv_id_str)] = geraete.get(str(inv_id_str), 0.0) + wert


async def _reihe_ueber_bereich(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    von: datetime,
    bis: datetime,
) -> list[tuple[datetime, float]]:
    """**Die eine Abfrage** — alle Stände des Fensters, zeitlich sortiert.

    Die Ränder sind mit erfasst (im Unterschied zu ``reader.reihe_im_fenster``,
    das sie exklusiv hält): Hier **sind** sie Teil derselben Reihe, weil jeder
    innere Rand zugleich Ende des einen und Anfang des nächsten Tages ist.
    """
    rand = timedelta(minutes=RAND_TOLERANZ_MINUTEN)
    result = await db.execute(
        select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh)
        .where(and_(
            SensorSnapshot.anlage_id == anlage_id,
            SensorSnapshot.sensor_key == sensor_key,
            SensorSnapshot.zeitpunkt >= von - rand,
            SensorSnapshot.zeitpunkt <= bis + rand,
        ))
        .order_by(SensorSnapshot.zeitpunkt)
    )
    return [(ts, wert) for ts, wert in result.all() if wert is not None]


async def _raender_mit_heilung(
    db: AsyncSession,
    anlage,
    sensor_key: str,
    sensor_id: Optional[str],
    quellen_energy: dict,
    grenzen: list[datetime],
    reihe: list[tuple[datetime, float]],
) -> list[Optional[float]]:
    """Je Tagesgrenze ein Stand — lokal, sonst über die Heilungs-Kaskade.

    ⚠ **Die Kaskade wird nur für die LÜCKEN gerufen.** Ein vollständig
    mitgeschriebener Monat kostet damit genau eine Abfrage (die Reihe oben);
    ein Monat aus der Zeit vor der Zuordnung kostet so viel wie früher, heilt
    sich dabei aber und ist beim nächsten Mal lokal da.
    """
    staende: list[Optional[float]] = [
        _naechster_stand(reihe, ziel) for ziel in grenzen
    ]
    for i, wert in enumerate(staende):
        if wert is not None:
            continue
        # `get_snapshot` fragt zuerst dieselbe Tabelle noch einmal — das ist
        # eine Abfrage zu viel, aber die Kaskade dahinter (HA-Langzeitstatistik,
        # MQTT-Backup, Rückschreiben) gibt es nur hier, und sie an dieser Stelle
        # nachzubauen wäre die F-56-Klasse.
        staende[i] = await get_snapshot(
            db, anlage.id, sensor_key, sensor_id, grenzen[i],
            quellen_energy=quellen_energy,
        )
    return staende
