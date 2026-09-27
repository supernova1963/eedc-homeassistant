"""Komponenten-Dashboards — die Basis: gewichtete Monatspreise (Netzbezug/Einspeisung je Verwendung, P8) und das
Monatsdaten-Antwortmodell, das alle Dashboards mitliefern.
"""
# Reiner Umzug aus `api/routes/investitionen/dashboards.py` (18.09.2026, Vorlage 6 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `dashboards.py` haengt den Router an der
# bisherigen Stelle ein und exportiert die Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from typing import Optional, Any, NamedTuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import date
from backend.models.monatsdaten import Monatsdaten
from backend.services.strompreis_aggregator import aufgeloester_monatspreis
from backend.api.routes.strompreise import (
    resolve_einspeiseverguetung_cent,
    resolve_strompreis_for_komponente,
)


class GewichtetePreise(NamedTuple):
    """Mengengewichtete Ø-Tarife einer Periode, beide Preisseiten (ct/kWh).

    ``bezug_lookup`` trägt zusätzlich die **ungemittelten** Monatspreise, aus
    denen der Ø entstanden ist. Er geht an
    ``berechne_eauto_ersparnis_periode`` weiter, damit die Preisachse dort
    aufgelöst wird und nicht hier — sonst gäbe es die Mittelung an zwei Orten
    (F-18/N-181). Zwei getrennte Query-Schleifen über dieselben Monate wären
    der Preis dafür gewesen; so bleibt es bei einer.
    """
    bezug_cent: float
    einspeise_cent: float
    bezug_lookup: dict[tuple[int, int], float] = {}

async def _gewichtete_monatspreise(
    db: AsyncSession,
    anlage_id: int,
    verwendung: str,
    gewichte: dict[tuple[int, int], float],
    fallback_bezug: float,
    fallback_einspeise: float,
) -> GewichtetePreise:
    """Mengengewichtete Ø der Tarife, die in den Monaten der Periode galten.

    ADR-002/P8 für die Komponenten-Dashboards. Sie summieren Energien über die
    ganze Lebensdauer und bewerten sie EINMAL — mit dem heutigen Tarif hätte
    jede Preiserhöhung die komplette Historie rückwirkend neu bewertet.

    Warum ein gewichteter Ø statt einer strengen Monatsmultiplikation: Bei
    aktivem Wallbox-Pool (#262) ersetzt `attribute_emob_pool_by_km` die
    Monatswerte durch EINEN nach km verteilten Gesamtwert — eine
    Monatsaufteilung der Netzladung existiert dort nicht. Der Ø wird deshalb
    mit derselben Größe gewichtet, nach der auch attribuiert wird. Für Anlagen
    ohne Tarifwechsel ist das Ergebnis identisch zum bisherigen Wert.

    **Warum BEIDE Preisseiten aus einer Schleife kommen:** die Funktion hieß
    bis v4.0.7 `_gewichteter_monatspreis` und lieferte nur den Bezugspreis —
    die Einspeisevergütung daneben blieb der HEUTE gültige Wert. In jedem
    Spread (`bezug − einspeise` bei V2H und Speicher) standen damit zwei
    Summanden aus verschiedenen Zeitpunkten. Zwei getrennte Aufrufe wären
    zudem eine zweite Query-Schleife über dieselben Monate.

    Die Vergütung trägt bewusst dieselben Gewichte wie der Bezugspreis, auch
    wo die bewertete Menge eine andere ist (V2H-Entladung statt Netzladung):
    eine eigene Gewichtung wäre nur mit einer Monatsaufteilung der
    V2H-Energie ehrlich, und die existiert im Pool-Fall gerade nicht. Die
    Näherung ist damit dieselbe, die der Bezugspreis hier seit v4.0.5 macht.

    Args:
        gewichte: ``{(jahr, monat): menge}`` — Netzladung bzw. km je Monat.
        fallback_bezug: Bezugspreis ohne Gewichte (ct/kWh).
        fallback_einspeise: Einspeisevergütung ohne Gewichte (ct/kWh).
    """
    summe_gewicht = sum(g for g in gewichte.values() if g and g > 0)
    if summe_gewicht <= 0:
        return GewichtetePreise(fallback_bezug, fallback_einspeise, {})

    # ⭐ **#412 (11.09.2026): auch hier gilt die volle Preis-Kaskade.** Bis dahin
    # las diese Schleife allein den Tarif — der **abgerechnete** Monats-Ø aus
    # dem Monatsabschluss kam nie an, obwohl Cockpit → Übersicht und die
    # Aussichten ihn für dieselbe E-Mob-Ersparnis längst nahmen. Dieselbe
    # Größe, zwei Zahlen, je nachdem welche Sicht der Anwender öffnet — die
    # F-18-Klasse, eine Ebene tiefer: Der bestehende Wächter prüft, **dass**
    # ein Lookup übergeben wird, nicht **welcher**.
    #
    # ⚠ Der Layer sagt es ausdrücklich: *„Der Flex-Ø gilt für den ganzen
    # Zähler — auch für die Wallbox"* (`monats_fakten._lade_tarif`).
    md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    md_je_monat = {(m.jahr, m.monat): m for m in md_result.scalars().all()}

    # Dieselbe Bauform wie in `monats_strompreis_lookup`: Tarife und gemessene
    # Monats-Ø einmal fuer alle Monate, danach rechnet die Schleife nur noch.
    from backend.api.routes.strompreise import lade_tarife_je_stichtag
    from backend.services.strompreis_aggregator import lade_preis_aggregate_je_monat

    _monate = [(j, m) for (j, m), g in gewichte.items() if g and g > 0]
    _tarife_je_stichtag = await lade_tarife_je_stichtag(
        db, anlage_id, [date(j, m, 1) for j, m in _monate]
    )
    _messung = await lade_preis_aggregate_je_monat(db, anlage_id)

    gewichteter_bezug = 0.0
    gewichtete_einspeisung = 0.0
    bezug_lookup: dict[tuple[int, int], float] = {}
    preis_cache: dict = {}
    for (jahr, monat), gewicht in gewichte.items():
        if not gewicht or gewicht <= 0:
            continue
        m_tarife = _tarife_je_stichtag[date(jahr, monat, 1)]
        m_bezug = resolve_strompreis_for_komponente(
            m_tarife, verwendung, fallback=fallback_bezug
        )
        # Die Kaskade schlägt den Komponenten-Tarif, wo sie etwas Besseres
        # weiß — genau wie `wallbox_preis_effektiv_cent` in den Monats-Fakten.
        # ⚠ `stammpreis_override`: Der Komponenten-Tarif bleibt Stufe 4, er geht
        # nicht verloren; nur ein gepflegter oder gemessener Ø schlägt ihn.
        m_bezug = (await aufgeloester_monatspreis(
            db, anlage_id, jahr, monat, md_je_monat.get((jahr, monat)),
            m_tarife.get("allgemein"),
            stammpreis_override=m_bezug, cache=preis_cache, messung=_messung,
        )).cent
        bezug_lookup[(jahr, monat)] = m_bezug
        gewichteter_bezug += m_bezug * gewicht
        gewichtete_einspeisung += resolve_einspeiseverguetung_cent(
            m_tarife, fallback=fallback_einspeise
        ) * gewicht
    return GewichtetePreise(
        gewichteter_bezug / summe_gewicht,
        gewichtete_einspeisung / summe_gewicht,
        bezug_lookup,
    )

class InvestitionMonatsdatenResponse(BaseModel):
    """Monatsdaten für eine Investition."""
    #: ``None`` nur für eine Zeile, die nicht gespeichert ist: der E-Auto-Hub zeigt einen
    #: Monat, in dem das Auto Rest der Wallbox bekommt, aber keine eigene Monatszeile hat
    #: (N-564, ``verbrauch_daten.ladung_aus_rest``). Jede gespeicherte Zeile trägt ihre ID.
    id: Optional[int] = None
    investition_id: int
    jahr: int
    monat: int
    verbrauch_daten: dict[str, Any]
    einsparung_monat_euro: Optional[float]
    co2_einsparung_kg: Optional[float]

    class Config:
        from_attributes = True
