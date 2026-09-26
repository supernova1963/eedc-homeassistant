"""Monats-Summen aus der **lokalen** Tagesebene — reines Lesen (Fund N-121).

**Warum es das gibt.** Die Monats-Fakten-Schicht kennt einen Monat nur, wenn er
eine DB-Spur hat: eine ``Monatsdaten``-Zeile (entsteht erst beim Monatsabschluss)
oder eine ``InvestitionMonatsdaten``-Zeile. Einen automatischen Monatsabschluss
gibt es nicht — der Monatswechsel-Job (``scheduler.py::monthly_snapshot_job``)
setzt nur einen Log-Zeitstempel. Damit fehlt dem *laufenden* Monat die Spur
**immer**, und dem Vormonat so lange, bis jemand den Abschluss macht. In
*Cockpit → Jahr* stand deshalb eine Kopfzahl über acht Monate über einem Verlauf
mit sechs Balken (an Gernots Anlage gemessen: Juli — der ertragsstärkste Monat
des Jahres — und August fehlten).

**Warum die Tagesebene die richtige Quelle ist.** Sie liegt **lokal** und wird
von den ohnehin laufenden Snapshot-Jobs geschrieben. Ein Lesepfad darauf kostet
**null zusätzliche Home-Assistant-Abfragen** — das ist die Auflage, unter der
diese Erweiterung entschieden wurde (Entscheid Gernot 2026-08-03, direkt nach der
mit **L-1** gewonnenen HA-Entlastung: „Monatsfakten erweitern, aber Achtung gerade
erst HA DB Last reduziert").

**Warum das kein zweiter Tag→Monat-Falter ist** ([[feedback_aggregations_drift]],
Präzedenz ``komponenten_beitraege`` v3.33). Zwei Faltungen derselben Quelle sind
die Drift-Klasse, gegen die dieses Projekt seit zehn Vorfällen arbeitet. Hier
entsteht keine:

- ``rollup_month`` (nebenan) ist **kein** Konkurrent: es faltet fünf *andere*
  Felder (Überschuss, Defizit, Vollzyklen, Performance Ratio, Peak-Netzbezug) und
  **schreibt** sie in ``Monatsdaten``. Die Energiemengen fasst es gar nicht an.
- Die Faltung selbst kommt aus dem Berechnungs-Layer: ``bilanz_aus_stundenrows``
  (ADR-001) — derselbe Helfer, den die Tages-Tabelle benutzt, hier nur über die
  Stunden eines ganzen Monats statt eines Tages. Σ über Stunden ist assoziativ,
  die additive Symmetrie zum Tag bleibt damit per Konstruktion erhalten.
- Der PV/BKW-Split kommt aus ``summe_pv_anlage_kwh``/``summe_bkw_kwh`` auf
  ``TagesZusammenfassung.komponenten_kwh`` — dieselben Helfer und dieselbe
  Whitelist wie in der Tages-Tabelle.

**Gemessen, nicht angenommen** (Anlage 1, 2026-08-03, v4.0.8): über sechs Monate,
für die es *beide* Quellen gibt, weicht die Tages-Σ maximal **0,8 kWh** von der
DB-Zeile ab (0,05 %). Für Juli und August — die Monate ohne DB-Spur — trifft sie
die HA-Statistics-Kaskade der Kachel auf allen vier Größen: PV 1843,2 gegen
1843,25 · Einspeisung 1343,9 gegen 1343,91 · Netzbezug 10,3 gegen 10,31.
Das „Σ Tage ≠ Monat"-Risiko (dokumentiert für CO₂-Tageswerte und den Flex-Ø)
greift für **diese** Größen also nicht.

**Grenze.** Tageszeilen entstehen nur, wo Datenquellen zugeordnet sind
(``aggregate_day`` liest ``anlage.sensor_mapping``; das deckt HA-Sensor **und**
MQTT ab). Wer rein manuell pflegt, hat keine — dort füllt sich aber auch die
Kachel nicht, es gibt also keine Diskrepanz zu heilen. Ein Monat mit Zuordnung,
aber ohne je gelaufene Aggregation (Add-on war aus, kein Vollbackfill) bleibt
weiterhin unsichtbar; sein Reparaturweg ist der Vollbackfill aus LTS.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    bilanz_aus_stundenrows,
    monatsbilanz_aus_tagen,
    summe_bkw_kwh,
    summe_pv_anlage_kwh,
)
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

#: ``(jahr, monat)`` — dieselbe Achse wie die Monats-Fakten-Schicht.
MonatsSchluessel = tuple[int, int]


@dataclass(frozen=True)
class TagesMonatsSumme:
    """Die Monatsgrößen, die die Tagesebene **belegen kann** — mehr nicht.

    Bewusst schmal: Euro-Positionen, E-Mobilität, Wärmemengen und die
    §51-Mitschrift haben auf Tagesebene entweder keine Entsprechung oder eine
    mit anderer Semantik. Wer sie hier ergänzt, muss den Vergleich gegen die
    DB-Quelle genauso messen wie oben für PV/Zähler/Speicher geschehen.

    ``tage``/``stunden`` sind die Belegdichte — ein Monat mit drei Tageszeilen
    (laufender Monat) ist eine *vollständige* Aussage über diese drei Tage, aber
    keine über den Monat. Wer eine Hochrechnung daraus macht, macht sie selbst.
    """

    einspeisung_kwh: float = 0.0
    netzbezug_kwh: float = 0.0
    pv_module_kwh: float = 0.0
    bkw_kwh: float = 0.0
    speicher_ladung_kwh: float = 0.0
    speicher_entladung_kwh: float = 0.0
    #: Abgeleiteter PV-/Netz-Anteil der Heimladung (N-141 Weg c). ⚠ **Das ist
    #: die einzige E-Mob-Größe hier, und sie ist mit Bedacht keine Ladungs-
    #: MENGE**, sondern eine Aufteilung: die Menge bleibt Sache der
    #: Monatszeile. Die Auflage aus dem Klassen-Docstring ist erfüllt — die
    #: Regel wurde am 2026-08-08 gegen evcc als externe Referenz vermessen
    #: (963 kWh, −3,2 pp), nachzulesen in `KONZEPT-WALLBOX-EAUTO.md` Phase 5.
    emob_ladung_pv_abgeleitet_kwh: float = 0.0
    emob_ladung_netz_abgeleitet_kwh: float = 0.0
    tage: int = 0
    stunden: int = 0
    #: Erster und letzter Tag **mit Spur** (N-472). ⭐ Sie machen aus der
    #: Belegdichte oben eine *ausweisbare* Abdeckung: Wer diese Summe als
    #: Monatswert zeigt, kann daneben schreiben, ab wann sie misst — und genau
    #: das verlangt P4, wenn die Tagesebene erst mitten im Monat beginnt (ein
    #: später eingerichtetes Add-on, ein Vollbackfill, der nicht zurückreicht).
    #:
    #: ⚠ **Sie beschreiben die Ränder, nicht die Lückenlosigkeit dazwischen.**
    #: Ein Loch in der Mitte (Add-on war drei Tage aus) sieht man ihnen nicht
    #: an; dafür ist der Daten-Checker zuständig, der fehlende Tage meldet.
    erster_tag: Optional[date] = None
    letzter_tag: Optional[date] = None

    @property
    def pv_kwh(self) -> float:
        """Module + Balkonkraftwerk — die PV-Achse der Monats-Fakten."""
        return self.pv_module_kwh + self.bkw_kwh

    @property
    def abgeleiteter_pv_anteil(self) -> Optional[float]:
        """Anteil der Heimladung, der aus eigener Sonne kam — 0…1.

        **Ein Anteil, keine Kilowattstunde.** Wer die abgeleiteten kWh direkt
        in die Monatszeile schriebe, zerbräche die Trias
        ``ladung_kwh == ladung_pv_kwh + ladung_netz_kwh``: die Tagesebene und
        die Monatszeile müssen nicht dieselbe Ladungsmenge kennen (Tagesspur
        unvollständig, Monat aus einer anderen Quelle gepflegt). Mit dem Anteil
        auf die kanonische Monatsladung angewandt bleibt sie exakt geschlossen
        — genau der Fehler, der bei #262 einen PV-Anteil > 100 % erzeugt hat.

        ``None`` heißt „keine Aussage" (keine Ladung in der Tagesspur).
        """
        gesamt = self.emob_ladung_pv_abgeleitet_kwh + self.emob_ladung_netz_abgeleitet_kwh
        if gesamt <= 0:
            return None
        return self.emob_ladung_pv_abgeleitet_kwh / gesamt


def _monatsgrenzen(
    von: Optional[MonatsSchluessel], bis: Optional[MonatsSchluessel]
) -> tuple[Optional[date], Optional[date]]:
    """``(jahr, monat)``-Fenster → Datumsgrenzen, beide inklusive."""
    erster = date(von[0], von[1], 1) if von else None
    if bis is None:
        return erster, None
    jahr, monat = (bis[0] + 1, 1) if bis[1] == 12 else (bis[0], bis[1] + 1)
    # Letzter Tag des `bis`-Monats = Tag vor dem Ersten des Folgemonats.
    letzter = date(jahr, monat, 1)
    return erster, letzter


async def lade_monats_summen_aus_tagen(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
    stunden_nur_fuer: Optional[set[MonatsSchluessel]] = None,
) -> dict[MonatsSchluessel, TagesMonatsSumme]:
    """Faltet die lokale Tagesebene je Monat — zwei Queries, danach reine Summe.

    ⚠ **Die Stundenzeilen kommen als Spalten-Tupel, nicht als ORM-Objekte.**
    Die Faltung (``bilanz_aus_stundenrows``) liest genau sechs Felder; ein
    Entity-Load baut daneben je Zeile ein ``TagesEnergieProfil``-Objekt **und
    deserialisiert dessen JSON-Spalten** (``komponenten``,
    ``source_provenance``, ``soc_je_speicher``, ``betriebsmodus_je_wp``).
    An der produktiven Anlage waren das 17.366 Objekte und 35.861
    ``json.loads`` je Anfrage — der Posten, der den Event-Loop für rund 0,7 s
    blockierte und parallele Seitenabrufe gegenseitig ausbremste (gemessen
    15.09.2026). Ein Spalten-Tupel trägt dieselben Attributnamen; die Faltung
    merkt den Unterschied nicht.

    Args:
        db: Session.
        anlage_id: Anlage.
        von: frühester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.
        bis: spätester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.
        stunden_nur_fuer: Monate, für die die **Stundenebene** überhaupt
            gebraucht wird. ``None`` (Default) = alle im Fenster, wie bisher.
            Eine **leere** Menge heißt: keine — dann entfällt die Stunden-Query
            ganz. Die Tageszusammenfassungen werden **immer** vollständig
            geladen; aus ihnen kommen PV, BKW und die Ladeanteils-Quote.

            ⛔ Wer die Menge setzt, muss wissen, was er aufgibt: ``stunden``,
            ``tage``, ``erster_tag`` und ``letzter_tag`` beschreiben dann nur
            noch die geladene Teilmenge. Im Fakten-Pfad liest sie heute
            niemand (baumweit geprüft); wer sie braucht, ruft ohne die Menge.

    Returns:
        Je Monat mit mindestens einer Tages-Spur eine ``TagesMonatsSumme``.
        Monate ohne jede Tageszeile fehlen — wie in der Monats-Fakten-Schicht
        ist Abwesenheit hier „keine Aussage", nicht „null".
    """
    ab, vor = _monatsgrenzen(von, bis)

    # Nur die Felder, die `bilanz_aus_stundenrows` liest — plus `datum` für die
    # Zuordnung zum Monat. Die Row-Objekte tragen dieselben Attributnamen.
    tep_query = select(
        TagesEnergieProfil.datum,
        TagesEnergieProfil.pv_kw,
        TagesEnergieProfil.verbrauch_kw,
        TagesEnergieProfil.einspeisung_kw,
        TagesEnergieProfil.netzbezug_kw,
        TagesEnergieProfil.batterie_kw,
        TagesEnergieProfil.waermepumpe_kw,
    ).where(
        TagesEnergieProfil.anlage_id == anlage_id
    )
    tz_query = select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id
    )
    if ab is not None:
        tep_query = tep_query.where(TagesEnergieProfil.datum >= ab)
        tz_query = tz_query.where(TagesZusammenfassung.datum >= ab)
    if vor is not None:
        tep_query = tep_query.where(TagesEnergieProfil.datum < vor)
        tz_query = tz_query.where(TagesZusammenfassung.datum < vor)

    if stunden_nur_fuer is not None:
        # Je gewünschtem Monat ein Datumsfenster — dieselbe Bauform wie oben,
        # damit der Index `ix_tep_anlage_datum` greift (kein `extract`).
        fenster = [
            and_(
                TagesEnergieProfil.datum >= date(jahr, monat, 1),
                TagesEnergieProfil.datum < date(
                    jahr + (monat == 12), (monat % 12) + 1, 1
                ),
            )
            for jahr, monat in sorted(stunden_nur_fuer)
        ]
        tep_query = tep_query.where(or_(*fenster)) if fenster else None

    # Stundenzeilen je Monat sammeln — die Faltung macht danach der Layer-Helfer
    # über den ganzen Monatsblock (Σ über Stunden ist assoziativ, s. Modul-Kopf).
    stunden_je_monat: dict[MonatsSchluessel, list] = defaultdict(list)
    tage_je_monat: dict[MonatsSchluessel, set[date]] = defaultdict(set)
    if tep_query is not None:
        tep_result = await db.execute(tep_query)
        for row in tep_result.all():
            schluessel = (row.datum.year, row.datum.month)
            stunden_je_monat[schluessel].append(row)
            tage_je_monat[schluessel].add(row.datum)

    tz_result = await db.execute(tz_query)
    verworfen_je_tag: dict[date, Optional[dict]] = {}
    pv_je_monat: dict[MonatsSchluessel, float] = defaultdict(float)
    bkw_je_monat: dict[MonatsSchluessel, float] = defaultdict(float)
    lade_pv_je_monat: dict[MonatsSchluessel, float] = defaultdict(float)
    lade_netz_je_monat: dict[MonatsSchluessel, float] = defaultdict(float)
    for tz in tz_result.scalars().all():
        schluessel = (tz.datum.year, tz.datum.month)
        pv_je_monat[schluessel] += summe_pv_anlage_kwh(tz.komponenten_kwh)
        bkw_je_monat[schluessel] += summe_bkw_kwh(tz.komponenten_kwh)
        # `or 0.0` ist hier korrekt und NICHT die `is not None`-Falle: eine
        # Tageszeile ohne Ableitung trägt None, und None trägt zur Summe
        # nichts bei. Ob der Monat überhaupt eine Aussage hat, entscheidet
        # danach `abgeleiteter_pv_anteil` an der Gesamtsumme — nicht dieses
        # Feld je Tag.
        lade_pv_je_monat[schluessel] += tz.emob_ladung_pv_abgeleitet_kwh or 0.0
        lade_netz_je_monat[schluessel] += tz.emob_ladung_netz_abgeleitet_kwh or 0.0
        tage_je_monat[schluessel].add(tz.datum)
        verworfen_je_tag[tz.datum] = tz.verworfen

    summen: dict[MonatsSchluessel, TagesMonatsSumme] = {}
    for schluessel in sorted(set(stunden_je_monat) | set(pv_je_monat) | set(bkw_je_monat)):
        stunden = stunden_je_monat.get(schluessel, [])
        # ⭐ Zählerlücken wie HA (R8): der Monat faltet TAGESbilanzen — jeder
        # Tag nach seiner Regelmarke. Für die Mengen dieser Summe ist das
        # bitgleich zur Σ über die Stunden (Σ ist assoziativ); es ist dieselbe
        # Faltung wie im Monats-Endpunkt, damit keine zweite entsteht.
        stunden_je_tag: dict[date, list] = defaultdict(list)
        for row in stunden:
            stunden_je_tag[row.datum].append(row)
        bilanz = monatsbilanz_aus_tagen(
            bilanz_aus_stundenrows(rows, verworfen=verworfen_je_tag.get(tag))
            for tag, rows in sorted(stunden_je_tag.items())
        )
        tage = tage_je_monat.get(schluessel, set())
        summen[schluessel] = TagesMonatsSumme(
            einspeisung_kwh=bilanz.einspeisung_kwh,
            netzbezug_kwh=bilanz.netzbezug_kwh,
            pv_module_kwh=pv_je_monat.get(schluessel, 0.0),
            bkw_kwh=bkw_je_monat.get(schluessel, 0.0),
            speicher_ladung_kwh=bilanz.speicher_ladung_kwh,
            speicher_entladung_kwh=bilanz.speicher_entladung_kwh,
            emob_ladung_pv_abgeleitet_kwh=lade_pv_je_monat.get(schluessel, 0.0),
            emob_ladung_netz_abgeleitet_kwh=lade_netz_je_monat.get(schluessel, 0.0),
            tage=len(tage),
            stunden=len(stunden),
            erster_tag=min(tage) if tage else None,
            letzter_tag=max(tage) if tage else None,
        )
    return summen
