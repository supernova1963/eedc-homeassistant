"""DB-Aggregate für die §51-bereinigte Erlös-Berechnung.

Brückenmodul zwischen `TagesZusammenfassung.einspeisung_neg_preis_kwh`
(Tages-Aggregat) und den Erlös-Read-Sites (Monatsdaten-basiert, in
aussichten.py, cockpit/uebersicht.py, ha_export.py, aktueller_monat.py,
cockpit/komponenten.py, investitionen/dashboards.py).

Liefert die §51-Aggregate pro Anlage × Monat bzw. × Jahr. Der reine
Berechnungs-Schritt (Erlös-Reduzierung × Vergütung) lebt im
Berechnungs-Layer: `core.berechnungen.einspeise_erloes_euro`.

Konvention:
- Rückgabe `None` wenn die Anlage **nicht** dem §51 EEG unterliegt
  (`Anlage.unterliegt_eeg_51` = False, Default) — der Abzug gilt rechtlich nur
  für Neuanlagen ab Solarpaket I und ist ein bewusst manueller Schalter. Dies
  ist der **einzige Gate** für den §51-Abzug; alle Read-Sites gehen über diesen
  Service, daher genügt die Prüfung an dieser Stelle (kein Per-Site-Patch).
  Wer seine Tages-Zeilen schon geladen hat, nimmt `neg_preis_einspeisung_tageswert`
  — dieselbe Prüfung ohne zweiten Query. Genau dieser Weg fehlte bis 2026-08-03,
  und der Satz oben stimmte deshalb nicht: der Tagespfad las die Spalte roh.
- Rückgabe `None` wenn keine `TagesZusammenfassung`-Zeilen mit
  `einspeisung_neg_preis_kwh IS NOT NULL` existieren — das signalisiert
  Read-Sites: „Anwender hat keine Strompreis-Mitschrift / keinen
  Börsenpreis-Sensor"; alte Berechnung greift unverändert.
- Rückgabe `0.0` wenn die Anlage §51 unterliegt und Tages-Aggregate vorhanden
  sind, aber im Zeitraum keine Negativpreis-Einspeisung stattfand — eine echte
  0, kein Daten-Fehlen.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesZusammenfassung


async def _unterliegt_eeg_51(db: AsyncSession, anlage_id: int) -> bool:
    """True wenn die Anlage dem §51-EEG-Negativpreis-Abzug unterliegt.

    Manueller Schalter pro Anlage (Default False). Gate für den gesamten
    §51-Abzug — siehe Modul-Docstring.
    """
    stmt = select(Anlage.unterliegt_eeg_51).where(Anlage.id == anlage_id)
    return bool(await db.scalar(stmt))


def neg_preis_einspeisung_tageswert(
    anlage: Anlage,
    roh_kwh: Optional[float],
) -> Optional[float]:
    """Dasselbe Gate für einen **bereits geladenen** Tages-Rohwert.

    Die Tages-Sichten haben ihre ``TagesZusammenfassung``-Zeilen schon in der
    Hand (und die ``Anlage`` dazu) — für sie wäre ein eigener Query nur eine
    zweite Rundreise für eine Auskunft, die schon vorliegt. Sie sollen deshalb
    **nicht** an diesem Service vorbeigehen: bis 2026-08-03 lasen
    ``services/energie_profil/tage_werte.py`` und
    ``api/routes/energie_profil/views.py`` die Spalte roh, und der Tages-Erlös
    wurde dadurch auch bei Anlagen gekürzt, die dem §51 **nicht** unterliegen
    (Rainer-Meldung 2026-08-02: 45 kWh Einspeisung, 1,86 € statt ~3,7 €).
    Der Rohwert selbst wird bewusst **immer** geschrieben
    (``energie_profil/aggregator.py``) — er ist eine Messung; erst seine
    *Verwendung* als Vergütungsabzug hängt am Schalter.

    Args:
        anlage: die bereits geladene Anlage (kein Query).
        roh_kwh: ``TagesZusammenfassung.einspeisung_neg_preis_kwh`` des Tages.

    Returns:
        ``roh_kwh`` wenn die Anlage dem §51 unterliegt, sonst ``None`` — die
        Erlös-Formel lässt den Abzug dann weg, und die Ausweis-Spalte zeigt
        nichts an, genau wie die Monatstabelle (``monatsdaten.py``).
    """
    if not anlage.unterliegt_eeg_51:
        return None
    return roh_kwh


async def get_neg_preis_einspeisung_monat(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
    monat: int,
) -> Optional[float]:
    """Σ `einspeisung_neg_preis_kwh` über die Tage eines Monats.

    Returns:
        Summe in kWh wenn die Anlage §51 unterliegt und mindestens ein Tag im
        Monat einen nicht-NULL-Wert hat; sonst `None` (Anlage ohne §51-Flag oder
        Anwender ohne Tages-Aggregate / Strompreis-Sensor).
    """
    if not await _unterliegt_eeg_51(db, anlage_id):
        return None
    stmt = (
        select(
            func.sum(TagesZusammenfassung.einspeisung_neg_preis_kwh),
            func.count(TagesZusammenfassung.einspeisung_neg_preis_kwh),
        )
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .where(extract("year", TagesZusammenfassung.datum) == jahr)
        .where(extract("month", TagesZusammenfassung.datum) == monat)
    )
    result = await db.execute(stmt)
    summe, anzahl = result.one()
    if not anzahl:
        return None
    return float(summe or 0.0)


async def get_neg_preis_einspeisung_jahr(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
) -> Optional[float]:
    """Σ `einspeisung_neg_preis_kwh` über alle Tage eines Jahres.

    Returns:
        Wie `get_neg_preis_einspeisung_monat`, aber Jahres-Aggregat. `None`
        wenn die Anlage §51 nicht unterliegt oder das Jahr keine Tages-Aggregate
        mit Strompreis-Mitschrift hat.
    """
    if not await _unterliegt_eeg_51(db, anlage_id):
        return None
    stmt = (
        select(
            func.sum(TagesZusammenfassung.einspeisung_neg_preis_kwh),
            func.count(TagesZusammenfassung.einspeisung_neg_preis_kwh),
        )
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .where(extract("year", TagesZusammenfassung.datum) == jahr)
    )
    result = await db.execute(stmt)
    summe, anzahl = result.one()
    if not anzahl:
        return None
    return float(summe or 0.0)


async def get_neg_preis_einspeisung_je_monat(
    db: AsyncSession,
    anlage_id: int,
) -> Optional[dict[tuple[int, int], float]]:
    """Alle Monats-Aggregate auf einmal — dieselbe Aussage, EIN Query.

    Gegenstück zu `get_neg_preis_einspeisung_monat` für Aufrufer, die eine ganze
    Historie aufbereiten (`services/monats_fakten.py`): pro Monat einzeln zu
    fragen wären N Rundreisen für dieselbe Gruppierung.

    Returns:
        `None` wenn die Anlage **nicht** dem §51 unterliegt — identisches Gate,
        damit beide Wege dieselbe Antwort geben. Sonst ein Dict
        `{(jahr, monat): kWh}`; ein Monat **ohne** Tages-Aggregate mit
        Strompreis-Mitschrift **fehlt** im Dict (der Aufrufer liest ihn als
        `None`, nicht als 0 — eine 0 wäre dort eine Aussage, die niemand belegen
        kann).
    """
    if not await _unterliegt_eeg_51(db, anlage_id):
        return None
    jahr_spalte = extract("year", TagesZusammenfassung.datum).label("jahr")
    monat_spalte = extract("month", TagesZusammenfassung.datum).label("monat")
    stmt = (
        select(
            jahr_spalte,
            monat_spalte,
            func.sum(TagesZusammenfassung.einspeisung_neg_preis_kwh),
            func.count(TagesZusammenfassung.einspeisung_neg_preis_kwh),
        )
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .group_by(jahr_spalte, monat_spalte)
    )
    result = await db.execute(stmt)
    return {
        (int(j), int(m)): float(summe or 0.0)
        for j, m, summe, anzahl in result.all()
        if anzahl
    }
