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
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    ModusSplit,
    ModusStunde,
    falte_modus_split_tag,
    summiere_modus_split,
    waermepumpe_kwh_je_investition,
)
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
        return {}
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
        return {}

    tz_result = await db.execute(tz_query)
    zaehler_je_tag: dict[date, dict[str, float]] = {}
    for datum, komponenten_kwh in tz_result.all():
        if datum in je_tag and komponenten_kwh:
            zaehler_je_tag[datum] = waermepumpe_kwh_je_investition(komponenten_kwh)

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


async def lade_modus_split_monat(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> dict[str, ModusSplit]:
    """Bequemer Einzelmonat — sonst identisch zu {@link lade_modus_split_je_monat}."""
    alle = await lade_modus_split_je_monat(
        db, anlage_id, von=(jahr, monat), bis=(jahr, monat)
    )
    return alle.get((jahr, monat), {})
