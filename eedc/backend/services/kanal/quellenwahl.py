"""Quellenwahl je Zeitraum — Kanäle oder Bestand (HA-Bauform E3, Auftrag Punkt 3; Bauplan §3b, Entscheid Gernot 06.10.).

Je Tag und je Monat gibt es EINE Quellenwahl für alle Eingänge einer Größe: ``kanal`` nur, wenn JEDER benötigte
Kanal den Zeitraum voll deckt (Regel in ``lesen.py``); sonst ``bestand`` — der heutige Leser rechnet den ganzen
Zeitraum unverändert aus den bisherigen Stunden- und Tageszeilen. Kein Wert halb aus der einen, halb aus der anderen
Quelle. Ein zugeordnetes Feld ohne Kanal (Sensor ohne HA-Statistik, Entscheid „keine Mittelwert-Mitschrift")
zählt als „deckt nicht".

**Reine Auskunft:** die Wahl ruft weder den alten Leser noch ändert sie etwas. **Stand E3: von niemandem benutzt**
(Umhängen ist E4).

Schwesterdateien: ``lesen.py``, ``monatsraster.py``, ``fenster.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_MEAN
from backend.services.kanal.lesen import (
    GRUND_KEIN_KANAL,
    Mittel,
    Zeitraum,
    kanaele_laden,
    mittel_stapel,
    zeitraum_stapel,
)

QUELLE_KANAL = "kanal"
QUELLE_BESTAND = "bestand"
#: Eine Wahl ohne einen einzigen benannten Eingang hat nichts zu prüfen — sie bleibt beim Bestand (heute unverändert).
GRUND_KEINE_EINGAENGE = "keine_eingaenge"


@dataclass(frozen=True)
class Quellenwahl:
    #: ``kanal`` oder ``bestand``.
    quelle: str
    #: Je Kanal, der NICHT voll deckt, der Grund (``kein_kanal``, ``beginnt_nach_von``, ``endet_vor_bis``,
    #: ``feiner_als_spanne``, ``keine_zeile``). Leer bei ``kanal``.
    gruende: dict[str, str] = field(default_factory=dict)
    #: Die Lese-Ergebnisse, auf denen die Wahl beruht (je vorhandenem Kanal).
    ergebnisse: dict[str, Union[Zeitraum, Mittel]] = field(default_factory=dict)


def waehle_quelle(
    ergebnisse: Mapping[str, Optional[Union[Zeitraum, Mittel]]], benoetigte: Iterable[str],
) -> Quellenwahl:
    """Die eine Regel als reine Funktion: ``kanal`` nur, wenn jeder benötigte Schlüssel ein voll deckendes Ergebnis
    hat; ein fehlendes Ergebnis heißt ``kein_kanal``. Dieselbe Funktion wählt je Monat im Monatsraster."""
    benoetigte = list(dict.fromkeys(benoetigte))
    if not benoetigte:
        return Quellenwahl(QUELLE_BESTAND, {"": GRUND_KEINE_EINGAENGE}, {})
    gruende: dict[str, str] = {}
    for key in benoetigte:
        erg = ergebnisse.get(key)
        if erg is None:
            gruende[key] = GRUND_KEIN_KANAL
        elif not erg.voll:
            gruende[key] = erg.grund or "nicht_voll"
    vorhanden = {k: v for k, v in ergebnisse.items() if v is not None and k in benoetigte}
    return Quellenwahl(QUELLE_BESTAND if gruende else QUELLE_KANAL, gruende, vorhanden)


async def quellenwahl(
    db: AsyncSession, anlage_id: int, von: int, bis: int, benoetigte_kanaele: Iterable[str],
    *, jetzt: Optional[int] = None,
) -> Quellenwahl:
    """Kanal oder Bestand für ``[von, bis)`` und die benannten Kanal-Schlüssel, mit Grund je nicht deckendem Kanal.

    Kosten: eine Anweisung für die Kanäle, je zwei für die Mengen-/Stand- und die Mittelwert-Kanäle — unabhängig von
    der Länge des Zeitraums und der Zahl der Kanäle.
    """
    benoetigte = list(dict.fromkeys(benoetigte_kanaele))
    kanaele = await kanaele_laden(db, anlage_id, benoetigte)
    mengen = [k for k in kanaele.values() if k.art != ART_MEAN]
    mittelwerte = [k for k in kanaele.values() if k.art == ART_MEAN]
    ergebnisse: dict[str, Union[Zeitraum, Mittel]] = {}
    if mengen:
        ergebnisse.update(await zeitraum_stapel(db, mengen, von, bis, jetzt=jetzt))
    if mittelwerte:
        ergebnisse.update(await mittel_stapel(db, mittelwerte, von, bis, jetzt=jetzt))
    return waehle_quelle(ergebnisse, benoetigte)
