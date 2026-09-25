"""Heimlade-Quellen im laufenden Monat — N-555, Konzept Heimladung/Fahrverbrauch, Regel 1.

*„Laufender Monat, Tag und Stunde fragen zusätzlich, ob eine Quelle zugeordnet ist"* — ein
HA-Sensor, oder über MQTT sind Zählerstände angekommen (Connector-Wallboxen kommen auf demselben
MQTT-Weg an); eine Quelle „keine" zählt nicht. Das ist die Antwort von
``snapshot.keys.feld_hat_zaehler``, die eedc für „hat dieses Feld einen Zähler" überall benutzt.

**Warum ein eigenes Modul:** Zwei Schichten fragen dasselbe — *Cockpit → Monat*
(``api/routes/aktueller_monat/aggregation.py``, Live-Werte) und die Monats-Fakten
(``services/monats_fakten/laden.py``) für den laufenden Monat aller Zeitraum-Sichten
(Übersicht, Hubs, Jahresbericht). Stünde die Frage nur in der Route, entschiede der laufende
Monat in der Übersicht anders als im Cockpit — gemessen am 25.09.2026 in der Wirkungsmessung:
Übersicht 1.544 kWh (Schätzung aus dem Fahrverbrauch), Cockpit → Monat 0 kWh.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.field_definitions import HEIMLADE_FELDER
from backend.core.investition_parameter import ist_dienstlich


def laufender_monat() -> tuple[int, int]:
    """``(jahr, monat)`` des laufenden Kalendermonats — die EINE Stelle, an der die
    Heimladung die Uhr fragt (Proben stellen sie hier, statt die echte Uhr zu lesen)."""
    heute = date.today()
    return (heute.year, heute.month)


async def lade_emob_heimlade_quellen(
    db: AsyncSession, anlage, investitionen: Iterable, jahr: int, monat: int,
) -> frozenset:
    """Die Heimlade-Felder privater Geräte in Betrieb, denen eine Quelle zugeordnet ist.

    Returns:
        ``frozenset({(inv_id, feld), …})`` — leer ohne private E-Autos/Wallboxen in Betrieb
        (dann fällt auch keine Abfrage an).
    """
    from backend.services.snapshot.keys import extract_quellen_energy, feld_hat_zaehler
    from backend.services.snapshot.reader import mqtt_zaehler_keys

    kandidaten = [
        inv for inv in investitionen
        if inv.typ in HEIMLADE_FELDER
        and not ist_dienstlich(inv)
        and inv.ist_aktiv_im_monat(jahr, monat)
    ]
    if not kandidaten:
        return frozenset()
    mapping = (anlage.sensor_mapping or {}).get("investitionen") or {}
    quellen_energy = extract_quellen_energy(anlage)
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)
    treffer = set()
    for inv in kandidaten:
        felder = (mapping.get(str(inv.id)) or {}).get("felder") or {}
        for feld in HEIMLADE_FELDER[inv.typ]:
            if feld_hat_zaehler(
                felder.get(feld), f"inv:{inv.id}:{feld}", quellen_energy, mqtt_keys,
            ):
                treffer.add((inv.id, feld))
    return frozenset(treffer)


async def laufende_heimlade_quellen(
    db: AsyncSession, anlage_id: int, investitionen: Iterable,
) -> dict[tuple[int, int], frozenset]:
    """``{(jahr, monat): quellen}`` für den **laufenden** Monat — Eingang für
    ``eauto_wirtschaftlichkeit.build_emob_pool_ctx(quellen_je_monat=…)``.

    Für die Sichten, die ``InvestitionMonatsdaten`` selbst laden (E-Auto-/Wallbox-Hub,
    Aussichten, HA-Export, T-Konto): ihr laufender Monat entscheidet damit wie der der
    Monats-Fakten und wie *Cockpit → Monat*. Leer, wenn es nichts zu fragen gibt.
    """
    from backend.models.anlage import Anlage

    investitionen = list(investitionen)
    if not any(i.typ in HEIMLADE_FELDER and not ist_dienstlich(i) for i in investitionen):
        return {}
    laufend = laufender_monat()
    anlage = await db.get(Anlage, anlage_id)
    if anlage is None:
        return {}
    quellen = await lade_emob_heimlade_quellen(db, anlage, investitionen, *laufend)
    return {laufend: quellen} if quellen else {}
