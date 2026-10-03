"""Vorlade-Kontext von *Cockpit → Monat*: Monats-Fakten J−1…J und die USt-Sätze beider Jahre.

Paket „Ergebnisgrößen Monat/Jahr" (03.10.2026, Vorlage B2/B3, Gegenprüfung G3/G5). Der USt-Anteil eines Monats ist
``EV_Monat × Satz des Jahres`` (E1) — den Satz kennt nur, wer die abgeschlossenen Monate des Jahres kennt, und das
Vorjahr braucht den Satz **seines** Jahres (G5). Statt zweier Einzelmonate (Monat, Vorjahresmonat) lädt die Route
deshalb **einen** Fakten-Bereich ``(jahr−1, 1)…(jahr, 12)``.

Die Jahresroute (``api/routes/cockpit/jahr.py``) lädt den Kontext **einmal** und reicht ihn an alle zwölf
Monatsaufrufe durch (``_berechne_monat(…, kontext=…)``) — sonst lüde jeder Monat dieselben 24 Monate erneut.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from backend.services.monats_fakten import MonatsFakt, lade_monats_fakten
from backend.services.ust_satz import UstSatz, ust_satz_des_jahres


@dataclass
class MonatsKontext:
    jahr: int
    fakten: dict[tuple[int, int], MonatsFakt]
    ust_satz: Optional[UstSatz]
    ust_satz_vj: Optional[UstSatz]
    #: Tarif-Stichtage, die die Schicht beim Laden aufgelöst hat — der Vorjahrespfad liest daraus.
    tarif_cache: dict[date, dict] = field(default_factory=dict)


async def lade_monats_kontext(db, anlage, jahr: int) -> MonatsKontext:
    """Fakten J−1…J und die Sätze von J und J−1 (``anlage.investitionen`` muss geladen sein)."""
    tarif_cache: dict[date, dict] = {}
    fakten = await lade_monats_fakten(
        db, anlage.id, von=(jahr - 1, 1), bis=(jahr, 12), tarif_cache=tarif_cache,
    )
    investitionen = list(anlage.investitionen)
    return MonatsKontext(
        jahr=jahr,
        fakten={f.schluessel: f for f in fakten},
        ust_satz=ust_satz_des_jahres(anlage, investitionen, fakten, jahr),
        ust_satz_vj=ust_satz_des_jahres(anlage, investitionen, fakten, jahr - 1),
        tarif_cache=tarif_cache,
    )
