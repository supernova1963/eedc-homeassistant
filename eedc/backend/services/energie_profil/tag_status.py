"""Warum ist die Tagessicht leer — und was hilft? Eine Antwort, aus dem Backend.

Cockpit/Tag zeigte bis v4.0.9 für einen Tag ohne Daten **einen Satz ohne Grund
und ohne Weg**: „Für diesen Tag liegen keine Daten vor. Wähle einen Tag mit
Messwerten." Das trifft die Lage seit v4.0.2/4 nicht mehr — leere Sichten
erklären sich, und der Reparatur-Knopf steht daneben, **wo er wirkt**.

**Warum ein eigener, tagesbezogener Weg?** Der Daten-Checker beschreibt die
**Anlage** (`daten_checker.datenquelle`): letzte `TagesZusammenfassung`
überhaupt, Lücken über die letzten 90 Tage, ein voller Lauf kostet an einer
echten Box ~2,5 s. Zu einem konkret **gewählten** Tag sagt er nichts — an
Winterborn meldete er „keine reparierbaren Tages-Lücken", während die Sicht
für den 2024-10-15 leer bleibt (Tageszeilen beginnen erst am 2024-10-31).
Das eine für das andere auszugeben wäre eine falsche Auskunft, keine
Erklärung. Deshalb dieselbe Logik in Tages-Granularität — **kein zweiter
Erfassungsweg und keine Client-eigene Ableitung** (Gernot 2026-08-06:
„zweite Wahrheit ist nicht gut").

**Grund immer, Handlung nur wo sie wirkt.** Liegt der Tag vor der
Inbetriebnahme, hat HA für ihn selbst nichts, oder fehlt dem Tages-Lauf die
Leistungs-Zuordnung, dann gibt es nichts nachzuaggregieren; ein Knopf, der
dann trotzdem dasteht, verspricht eine Wirkung, die es nicht gibt (dieselbe
Linie wie #368/P-8, nur von der anderen Seite). In diesen Lagen bleibt
``aktion`` leer und der Text sagt die Absage offen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.aggregations_quelle import (
    ermittle_aggregations_quelle,
)

logger = logging.getLogger(__name__)

# Ab dieser Tages-kWh gilt ein HA-Wert als „da wäre etwas zu holen". Gleiche
# Schwelle wie der Lücken-Check des Daten-Checkers (`_check_leere_tage_trotz_
# zaehler`) — eine zweite Schwelle daneben hieße: zwei Sichten, zwei Aussagen.
SCHWELLE_KWH = 1.0

LINK_DATENQUELLEN = "/einstellungen/datenquellen"


@dataclass(frozen=True)
class TagStatus:
    """Der Grund für einen Tag ohne Daten, plus — wo sie wirkt — eine Handlung."""

    lage: str
    meldung: str
    details: Optional[str] = None
    link: Optional[str] = None
    aktion_kind: Optional[str] = None
    aktion_label: Optional[str] = None


async def baue_tag_status(db: AsyncSession, anlage: Anlage, datum: date) -> TagStatus:
    """Beurteilt **genau diesen Tag** dieser Anlage.

    Reihenfolge der Prüfungen = Reihenfolge der Gewissheit: was ohne jede
    externe Abfrage feststeht, wird zuerst beantwortet. Der HA-LTS-Read läuft
    zuletzt und nur dann, wenn er die Antwort noch ändern kann — er ist das
    einzige Mittel, „Lücke, nachholbar" von „HA hat für den Tag selbst nichts"
    zu unterscheiden.
    """
    heute = date.today()

    if await _hat_tagesdaten(db, anlage.id, datum):
        return TagStatus(
            lage="daten_vorhanden",
            meldung="Für diesen Tag liegen Werte vor.",
        )

    if datum > heute:
        return TagStatus(
            lage="zukunft",
            meldung="Dieser Tag liegt in der Zukunft.",
            details="Werte entstehen erst, wenn der Tag läuft.",
        )

    if datum == heute:
        return TagStatus(
            lage="laeuft_noch",
            meldung="Der Tag läuft noch — die ersten Werte fehlen.",
            details=(
                "Die Tagesaggregation läuft stündlich; kurz nach Mitternacht "
                "ist deshalb noch nichts da. Bleibt es den ganzen Tag dabei, "
                "sieh unter Einstellungen → Datenquellen nach, ob die "
                "kWh-Zähler zugeordnet sind."
            ),
            link=LINK_DATENQUELLEN,
        )

    if anlage.installationsdatum and datum < anlage.installationsdatum:
        return TagStatus(
            lage="vor_inbetriebnahme",
            meldung=(
                f"Vor der Inbetriebnahme am "
                f"{anlage.installationsdatum.isoformat()} — für diesen Tag gibt "
                f"es keine Messwerte."
            ),
            details=(
                "eedc wertet erst ab dem Inbetriebnahme-Datum der Anlage aus. "
                "Ist das Datum falsch, lässt es sich unter Einstellungen → "
                "Stammdaten korrigieren."
            ),
            link="/einstellungen/stammdaten",
        )

    invs_by_id, erwartete_keys = await _erwartete_keys(db, anlage, datum)
    if not erwartete_keys:
        return TagStatus(
            lage="keine_zuordnung",
            meldung="Für diesen Tag war kein kWh-Zähler zugeordnet.",
            details=(
                "Ohne zugeordnete Zähler entstehen keine Tageswerte — auch "
                "rückwirkend nicht. Unter Einstellungen → Datenquellen die "
                "kWh-Zeilen belegen (nicht nur die Watt-Zeilen); ab dann füllt "
                "sich die Tagessicht."
            ),
            link=LINK_DATENQUELLEN,
        )

    quelle = await ermittle_aggregations_quelle(db, anlage, datum)

    ha_kwh = await _ha_tageswerte(anlage, invs_by_id, datum, erwartete_keys)
    if ha_kwh is None:
        return TagStatus(
            lage="keine_ha_statistik",
            meldung="Keine Tageswerte — und keine Home-Assistant-Statistik zum Nachholen.",
            details=(
                "eedc erreicht die HA-Langzeitstatistik gerade nicht. Im "
                "Standalone-Betrieb ohne Home Assistant entstehen Tageswerte "
                "nur aus den eigenen 5-Minuten-Snapshots — also ab dem Tag der "
                "Einrichtung vorwärts, nicht rückwirkend. Besteht eine "
                "HA-Verbindung, lässt sie sich unter Einstellungen → "
                "Datenquellen prüfen."
            ),
            link=LINK_DATENQUELLEN,
        )

    if not ha_kwh:
        return TagStatus(
            lage="ha_ohne_werte",
            meldung="Auch Home Assistant hat für diesen Tag nichts aufgezeichnet.",
            details=(
                "eedc reicht nur so weit zurück wie Home Assistant selbst. "
                "Liegt der Tag vor der HA-Einrichtung oder außerhalb der "
                "Aufbewahrung des Recorders, ist die Lücke keine Fehlfunktion "
                "— sie lässt sich nicht mehr füllen. Erfasste Monatswerte "
                "bleiben davon unberührt; Cockpit → Monat zeigt sie weiter."
            ),
        )

    gefunden = ", ".join(f"{k} {v:.1f} kWh" for k, v in sorted(ha_kwh.items())[:4])
    if not quelle.vorhanden:
        return TagStatus(
            lage="luecke_ohne_reparaturweg",
            meldung="Home Assistant hat Werte für diesen Tag, eedc kann sie aber nicht holen.",
            details=(
                f"In der HA-Langzeitstatistik stehen für diesen Tag: {gefunden}. "
                f"Nachrechnen ist hier trotzdem nicht möglich: der Tages-Lauf "
                f"braucht zusätzlich eine Leistungs-Zuordnung (W), und dieser "
                f"Anlage ist keine zugeordnet. Der Zählerstand allein genügt "
                f"ihm nicht. Deshalb steht hier bewusst kein Knopf — er würde "
                f"durchlaufen und nichts schreiben. Zuerst unter Einstellungen "
                f"→ Datenquellen einen Leistungssensor zuordnen (z. B. "
                f"„Netz-Leistung“), danach lässt sich der Tag nachrechnen."
            ),
            link=LINK_DATENQUELLEN,
        )

    return TagStatus(
        lage="luecke_reparierbar",
        meldung="Dieser Tag wurde nie aggregiert — Home Assistant hat die Werte noch.",
        details=(
            f"In der HA-Langzeitstatistik stehen für diesen Tag: {gefunden}. "
            f"„Tag nachrechnen“ holt Tages- und Stundenwerte nach — nicht die "
            f"Monatswerte. Für abgeschlossene Monate anschließend Einstellungen "
            f"→ Integration → Statistik-Import."
        ),
        aktion_kind="reaggregate_day",
        aktion_label="Tag nachrechnen",
    )


async def _hat_tagesdaten(db: AsyncSession, anlage_id: int, datum: date) -> bool:
    """Dieselbe Bedingung, unter der ``baue_tage_werte`` eine Zeile ausgibt:
    stündliche TEP-Rows **oder** eine Tageszusammenfassung."""
    tep = await db.execute(
        select(TagesEnergieProfil.id).where(and_(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == datum,
        )).limit(1)
    )
    if tep.scalar_one_or_none() is not None:
        return True
    tz = await db.execute(
        select(TagesZusammenfassung.id).where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum == datum,
        )).limit(1)
    )
    return tz.scalar_one_or_none() is not None


async def _erwartete_keys(
    db: AsyncSession, anlage: Anlage, datum: date,
) -> tuple[dict, set[str]]:
    """Was verspricht die Zuordnung für **diesen** Tag? (SoT-Helper, tagesgenau)"""
    from backend.services.snapshot.komponenten_beitraege import (
        erwartete_komponenten_keys,
    )

    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id)
    )
    invs_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}
    keys = set(erwartete_komponenten_keys(anlage.sensor_mapping or {}, invs_by_id, datum))
    return invs_by_id, keys


async def _ha_tageswerte(
    anlage: Anlage,
    invs_by_id: dict,
    datum: date,
    erwartete_keys: set[str],
) -> Optional[dict[str, float]]:
    """Was hat HA für diesen Tag? ``None`` = **nicht gefragt/nicht erreichbar**.

    Die Unterscheidung ist der Kern: ein fehlgeschlagener Read darf nicht als
    „HA hat nichts" durchgehen — das war die B0/N-93-Klasse (aus einer Lücke
    wird still eine 0). Deshalb ``None`` statt ``{}``.
    """
    from backend.services.ha_statistics_service import get_ha_statistics_service
    from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts
    from backend.services.snapshot.komponenten_beitraege import komponenten_key_label

    if not get_ha_statistics_service().is_available:
        return None
    try:
        roh = await get_komponenten_tageskwh_lts(anlage, invs_by_id, datum)
    except Exception as e:  # Netzfehler ≠ „HA hat nichts"
        logger.debug(
            f"Tag-Status Anlage {anlage.id} {datum}: HA-LTS-Read fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )
        return None

    def _label(key: str) -> str:
        _praefix, _, inv_id = key.rpartition("_")
        return komponenten_key_label(key, invs_by_id.get(inv_id))

    return {
        _label(k): float(v) for k in sorted(erwartete_keys)
        if isinstance((v := roh.get(k)), (int, float)) and v >= SCHWELLE_KWH
    }
