"""Modus-Split je Monat und Gerät aus der lokalen Tagesebene (#263 K-2, S3).

**Ein Lader, zwei Aufrufer** — das ist der Zweck dieser Datei, nicht ihre
Nebenwirkung:

* **Schreiben:** ``monatsabschluss_aggregator`` persistiert die zwei Teilmengen
  und die Abdeckung beim Monatsabschluss (Entscheid E-A/E-I).
* **Lesen:** der **laufende** Monat hat nie einen Abschluss und damit nie eine
  gespeicherte Aufteilung. Einen automatischen Monatsabschluss gibt es in eedc
  nicht — ``monats_aus_tagen.py`` sagt das im eigenen Modul-Kopf.

Beides über **dieselbe** Faltung. Zwei Faltungen derselben Quelle sind die
Drift-Klasse, gegen die dieses Projekt seit zehn Vorfällen arbeitet
([[feedback_aggregations_drift]]); genau hier wäre sie fast entstanden, weil
der Schreibpfad für sich genommen vollständig ausgesehen hätte.

**Warum die Tagesebene die richtige Quelle ist** — dieselbe Begründung wie bei
``monats_aus_tagen.py``: sie liegt lokal, wird von den ohnehin laufenden Jobs
geschrieben und kostet **null** zusätzliche Home-Assistant-Abfragen.

**Grenze (Konzept §5.1):** Der Split entsteht nur, wo Tageszeilen entstehen —
also bei zugeordneten Datenquellen. Wer seine Klimaanlage über den
Monatsabschluss, den HA-Statistik-Import oder CSV pflegt, bekommt **nie** eine
Aufteilung. Das ist keine Lücke, die später zuwächst, sondern die Bauform.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    ModusSplit,
    ModusStunde,
    falte_modus_split_tag,
    summiere_modus_split,
    teilmengen_passen,
    waermepumpe_kwh_je_investition,
)
from backend.core.betriebsmodus import HEIZEN, KUEHLEN
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

#: ``(jahr, monat)`` — dieselbe Achse wie die Monats-Fakten-Schicht.
MonatsSchluessel = tuple[int, int]

#: ``(jahr, monat)`` → ``{investition_id_als_string: ModusSplit}``.
SplitJeMonat = dict[MonatsSchluessel, dict[str, ModusSplit]]


@dataclass(frozen=True)
class _TagesEingang:
    """Die Stundenzeilen **eines** Tages, schon nach Gerät sortiert."""

    stunden_je_inv: dict[str, list[ModusStunde]]


def _monatsgrenzen(
    von: Optional[MonatsSchluessel], bis: Optional[MonatsSchluessel]
) -> tuple[Optional[date], Optional[date]]:
    """``(jahr, monat)``-Fenster → Datumsgrenzen (``ab`` inklusive, ``vor`` exklusiv)."""
    erster = date(von[0], von[1], 1) if von else None
    if bis is None:
        return erster, None
    jahr, monat = (bis[0] + 1, 1) if bis[1] == 12 else (bis[0], bis[1] + 1)
    return erster, date(jahr, monat, 1)


async def _lade_tages_eingaenge(
    db: AsyncSession, anlage_id: int, ab, vor,
) -> tuple[dict[date, "_TagesEingang"], dict[date, dict[str, float]]]:
    """Stundenzeilen + Tages-Zählersummen laden — der Teil, den Monat und Tag teilen.

    **Warum extrahiert** (#263/T2): Die Tagesansicht braucht dieselben Eingänge
    wie die Monatssicht, nur ohne die Zusammenfassung am Ende. Sie ein zweites
    Mal zu laden hieße, die Auswahlregeln („Tage über die Modus-Spur, Stunden
    vollständig") zweimal zu pflegen — und der Modul-Kopf sagt, warum das nicht
    geht: *eine Regel, die an zwei Stellen nachgebaut wird, driftet.*

    Returns:
        ``(je_tag, zaehler_je_tag)`` — leer, wenn die Anlage keine Modus-Spur hat.
    """
    # ⚠ **Zwei Schritte, und der Grund dafür ist gemessen.** Der erste Entwurf
    # filterte direkt auf `betriebsmodus_je_wp IS NOT NULL` — das hält die
    # Menge klein, hat aber die Stunden **ohne** Modus-Spur auch aus dem
    # **Nenner der Normierung** entfernt. Folge an einer eigenen Instanz
    # gemessen (20 Tage, 2 Standby-Stunden je Tag ohne Signal): die erfassten
    # Stunden wurden auf die volle Tagesmenge hochgerechnet, `Σ Teilmengen`
    # traf exakt den Gesamtwert und „nicht aufgeteilt" wurde 0 — statt der
    # 4,3 kWh, die das Gerät ohne Beobachtung verbraucht hat. Genau die
    # Extrapolation, die Entscheid E-H ausschließt.
    #
    # Deshalb: **Tage** über die Modus-Spur auswählen, **Stunden** aber
    # vollständig laden. Eine Anlage ohne Modus-Sensor lädt weiterhin nichts.
    tage_query = select(TagesEnergieProfil.datum).where(
        TagesEnergieProfil.anlage_id == anlage_id,
        TagesEnergieProfil.betriebsmodus_je_wp.is_not(None),
    ).distinct()
    tep_query = select(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage_id,
    )
    tz_query = select(
        TagesZusammenfassung.datum, TagesZusammenfassung.komponenten_kwh
    ).where(TagesZusammenfassung.anlage_id == anlage_id)
    if ab is not None:
        tage_query = tage_query.where(TagesEnergieProfil.datum >= ab)
        tep_query = tep_query.where(TagesEnergieProfil.datum >= ab)
        tz_query = tz_query.where(TagesZusammenfassung.datum >= ab)
    if vor is not None:
        tage_query = tage_query.where(TagesEnergieProfil.datum < vor)
        tep_query = tep_query.where(TagesEnergieProfil.datum < vor)
        tz_query = tz_query.where(TagesZusammenfassung.datum < vor)

    tage = {d for (d,) in (await db.execute(tage_query)).all()}
    if not tage:
        return {}, {}
    tep_query = tep_query.where(TagesEnergieProfil.datum.in_(tage))

    tep_result = await db.execute(tep_query)
    # Erst je Tag sammeln, welche Geräte überhaupt eine Modus-Spur haben —
    # nur für sie entstehen Stunden-Einträge (auch leere).
    zeilen_je_tag: dict[date, list] = defaultdict(list)
    geraete_je_tag: dict[date, set[str]] = defaultdict(set)
    for row in tep_result.scalars().all():
        zeilen_je_tag[row.datum].append(row)
        for inv_id in (row.betriebsmodus_je_wp or {}):
            geraete_je_tag[row.datum].add(str(inv_id))

    je_tag: dict[date, _TagesEingang] = {}
    for datum, zeilen in zeilen_je_tag.items():
        geraete = geraete_je_tag.get(datum)
        if not geraete:
            continue
        eingang = _TagesEingang(stunden_je_inv=defaultdict(list))
        for row in zeilen:
            modi = row.betriebsmodus_je_wp or {}
            # ⚠ Vorzeichen: `komponenten` führt die WP negativ (Leistungspfad).
            # Der Helfer liefert Beträge — das ist die eine Stelle, an der die
            # zwei Vorzeichen-Welten zusammenkommen.
            mengen = waermepumpe_kwh_je_investition(row.komponenten)
            for inv_id in geraete:
                # `modi.get(...)` ist hier bewusst None-tolerant: eine Stunde
                # ohne Eintrag ist „nicht hingesehen" und trägt zu keiner
                # Teilmenge bei — ihre **Menge** gehört aber in den Nenner der
                # Normierung, sonst entsteht die Hochrechnung von oben.
                eingang.stunden_je_inv[inv_id].append(
                    ModusStunde(kwh=mengen.get(inv_id), modus=modi.get(inv_id))
                )
        je_tag[datum] = eingang

    if not je_tag:
        return {}, {}

    tz_result = await db.execute(tz_query)
    zaehler_je_tag: dict[date, dict[str, float]] = {}
    for datum, komponenten_kwh in tz_result.all():
        if datum in je_tag and komponenten_kwh:
            zaehler_je_tag[datum] = waermepumpe_kwh_je_investition(komponenten_kwh)

    return je_tag, zaehler_je_tag


async def lade_modus_split_je_monat(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
) -> SplitJeMonat:
    """Faltet die Stundenzeilen je Monat und Wärmepumpe.

    Args:
        db: Session.
        anlage_id: Anlage.
        von: frühester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.
        bis: spätester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.

    Returns:
        Je Monat und Gerät ein ``ModusSplit``. Geräte ohne **eine einzige**
        Stunde mit Modus-Signal erscheinen **nicht** — Abwesenheit heißt hier
        „keine Aussage", nicht „null" (ADR-002/P4).

    Zwei Queries, danach reine Rechnung. Die Tages-Normierung braucht die
    zweite (``TagesZusammenfassung.komponenten_kwh``); fehlt sie für einen Tag
    oder ein Gerät, gilt für diesen Tag die Roh-Summe des Leistungspfads
    (``core/berechnungen/modus_split.py``, Modul-Kopf Punkt 3).
    """
    ab, vor = _monatsgrenzen(von, bis)
    je_tag, zaehler_je_tag = await _lade_tages_eingaenge(db, anlage_id, ab, vor)
    if not je_tag:
        return {}

    # Tagesweise falten (die Normierung ist tagesweise — s. `summiere_modus_split`),
    # danach je Monat aufsummieren.
    splits_je_monat: dict[MonatsSchluessel, dict[str, list[ModusSplit]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for datum, eingang in je_tag.items():
        zaehler = zaehler_je_tag.get(datum, {})
        schluessel = (datum.year, datum.month)
        for inv_id, stunden in eingang.stunden_je_inv.items():
            splits_je_monat[schluessel][inv_id].append(
                falte_modus_split_tag(stunden, tages_kwh=zaehler.get(inv_id))
            )

    ergebnis: SplitJeMonat = {}
    for schluessel, je_inv in splits_je_monat.items():
        zusammengefasst = {
            inv_id: summiere_modus_split(tage) for inv_id, tage in je_inv.items()
        }
        # Geräte ohne jede erfasste Stunde fallen heraus (P4: keine Aussage
        # statt einer 0, die wie eine Messung aussieht).
        gefiltert = {i: s for i, s in zusammengefasst.items() if not s.ist_leer}
        if gefiltert:
            ergebnis[schluessel] = gefiltert
    return ergebnis


async def lade_modus_split_tag(
    db: AsyncSession, anlage_id: int, datum: date,
) -> dict[str, ModusSplit]:
    """Der Modus-Split **eines Tages**, je Wärmepumpe (#263/T2).

    **Warum es das gibt** (gemeldet von OB73-gif, 2026-08-20): Die Aufteilung
    Heizen/Kühlen gab es nur je Monat — *„Die Übersicht am Ende (wie beim
    Monat) … fehlt hier auch."* Die Rechnung selbst ist ohnehin **tagesweise**
    (`falte_modus_split_tag`, die Normierung braucht die Tages-Zählersumme);
    die Monatssicht summiert sie nur hinterher auf. Diese Funktion bleibt eine
    Ebene früher stehen — **derselbe Ladepfad, dieselbe Faltung, kein zweiter
    Rechenweg.**

    ⚠ **Kein Vorrang gegenüber einem Abschluss.** Der Monatsabschluss
    persistiert seine Teilmengen (`auto:monatsabschluss`) — auf Tagesebene gibt
    es dazu kein Gegenstück, weil es keine Tages-Zeile gibt, die etwas anderes
    behaupten könnte. Was hier steht, ist immer die frisch gefaltete Stunde.

    Returns:
        ``{investitions_id_str: ModusSplit}`` — Geräte ohne **eine einzige**
        erfasste Stunde erscheinen **nicht** (P4: keine Aussage statt einer 0).
    """
    je_tag, zaehler_je_tag = await _lade_tages_eingaenge(
        db, anlage_id, datum, datum + timedelta(days=1),
    )
    eingang = je_tag.get(datum)
    if eingang is None:
        return {}
    zaehler = zaehler_je_tag.get(datum, {})
    splits = {
        inv_id: falte_modus_split_tag(stunden, tages_kwh=zaehler.get(inv_id))
        for inv_id, stunden in eingang.stunden_je_inv.items()
    }
    return {i: s for i, s in splits.items() if not s.ist_leer}


async def lade_modus_split_monat(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> dict[str, ModusSplit]:
    """Bequemer Einzelmonat — sonst identisch zu {@link lade_modus_split_je_monat}."""
    alle = await lade_modus_split_je_monat(
        db, anlage_id, von=(jahr, monat), bis=(jahr, monat)
    )
    return alle.get((jahr, monat), {})


@dataclass(frozen=True)
class AngewandterSplit:
    """Ein Modus-Split, der die Vorrang- und Invariantenprüfung bestanden hat.

    ``bezug_kwh`` ist der Gesamtwert, gegen den geprüft wurde — und aus dem die
    Zeile „nicht aufgeteilt" entsteht (``bezug − heizen − kuehlen``).
    """

    heizen_kwh: float
    kuehlen_kwh: float
    abdeckung_h: float
    bezug_kwh: float


async def lade_modus_split_ohne_abschluss(
    db: AsyncSession,
    anlage_id: int,
    *,
    inv_by_id: dict,
    gespeichert: dict[MonatsSchluessel, dict[str, tuple[bool, float]]],
    von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
) -> dict[MonatsSchluessel, dict[str, AngewandterSplit]]:
    """Der **zweite Aufrufer** aus dem Modul-Kopf — für Monate ohne Abschluss (F-52).

    **Warum das eine Funktion ist und keine zwei.** Sie hat selbst zwei
    Aufrufer: die Monats-Fakten-Schicht (Komponenten-Hub, Cockpit Monat/Jahr)
    und den HA-Export, der seine IMD-Zeilen **je Investition** faltet und
    deshalb nicht über die Monats-Fakten geht (bekannte P10-Restschuld). Beide
    brauchen dieselben zwei Regeln — und genau daran ist S3 gescheitert: eine
    Regel, die an zwei Stellen nachgebaut wird, driftet.

    Args:
        inv_by_id: die in Frage kommenden Investitionen, nach ID. Nur für sie
            wird etwas geliefert — der HA-Export übergibt genau eine.
        gespeichert: ``(jahr, monat) → {inv_id_str: (hat_gespeicherten_split,
            gepflegter_wp_strom_kwh)}``. Der Aufrufer baut sie beim Falten
            seiner IMD-Zeilen; diese Funktion liest **keine** Monatszeilen, um
            keine dritte Quelle für denselben Wert zu öffnen.

    Returns:
        Nur Monat/Gerät-Paare, für die tatsächlich etwas anzuwenden ist.

    Die zwei Regeln:

    * **Gespeichert schlägt gerechnet** (ADR-002/P8) — wo ein Abschluss lief,
      gilt sein Ergebnis; ein fertiger Monat wird nicht rückwirkend
      umgeschrieben.
    * **Die Teilmengen-Invariante gilt hier genauso.** Beim Abschluss
      *verworfene* Splits hinterlassen keine Spur (``_entferne_split``); ohne
      erneute Prüfung kämen sie über diesen Weg zurück.
    """
    splits = await lade_modus_split_je_monat(db, anlage_id, von=von, bis=bis)
    if not splits:
        return {}

    ergebnis: dict[MonatsSchluessel, dict[str, AngewandterSplit]] = {}
    for schluessel, je_inv in splits.items():
        for inv_id_str, split in je_inv.items():
            inv = inv_by_id.get(int(inv_id_str))
            # Dieselben drei Achsen wie im Schreibpfad (#153/#155/#236/#308).
            if inv is None or not inv.ist_aktiv_im_monat(*schluessel):
                continue
            hat_gespeicherten, gepflegter_strom = gespeichert.get(
                schluessel, {}
            ).get(inv_id_str, (False, 0.0))
            if hat_gespeicherten:
                continue
            bezug = gepflegter_strom if gepflegter_strom > 0 else split.bezug_kwh
            if not teilmengen_passen(split, bezug):
                continue
            ergebnis.setdefault(schluessel, {})[inv_id_str] = AngewandterSplit(
                heizen_kwh=split.teilmenge_kwh(HEIZEN),
                kuehlen_kwh=split.teilmenge_kwh(KUEHLEN),
                abdeckung_h=split.abdeckung_h,
                bezug_kwh=float(bezug or 0.0),
            )
    return ergebnis
