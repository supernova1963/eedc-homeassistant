"""Speicher-Wirkungsgrad aus Lade-/Entlademengen und ΔSoC (ADR-001).

Single Source of Truth für die Frage *„welcher η gilt für diesen Zeitraum, und
worauf beruht er?"*. Die Formel ist die Energieerhaltung:

    ladung × η = entladung + ΔSoC_energie   ⇒   η = (entladung + ΔSoC) / ladung

**Warum die Funktion einen Grund mitliefert und nicht nur eine Zahl.** Ein
Zeitraum ist kein geschlossenes System: Wer am Morgen mit vollem Speicher
beginnt und am Abend leer endet, entnimmt mehr, als er im selben Fenster
geladen hat — der rohe Quotient steht dann über 100 %, ohne dass am Speicher
etwas kaputt wäre. Über einen Monat mittelt sich das aus, über **einen Tag**
nicht. Genau das hat Knallfrosch am 15.08.2026 gemeldet (Forum T89667 #163,
„ein η > 100 % wäre zwar nett aber eher falsch"), und rapahl hat im selben
Faden die richtige Erklärung gegeben (#164) — sie stand nur nirgends in eedc.

Drei Fälle, drei Antworten:

- **ΔSoC bekannt** → korrigierter Wert, ``quelle="soc_korrigiert"``.
- **ΔSoC unbekannt, roher Quotient ≤ 100 %** → der rohe Wert mit
  ``quelle="roh-unkorrigiert"``. Er trägt den Übertrag über die
  Zeitraumgrenze, ist aber physikalisch möglich und für Anlagen ohne
  SoC-Sensor die einzige Aussage, die es gibt (P4: sagen, was man weiß, **und**
  wie sicher).
- **ΔSoC unbekannt, roher Quotient > 100 %** → **kein** Wert,
  ``quelle="nicht-ermittelbar"``. Über 100 % kann kein Speicher, und ohne
  Ladestand lässt sich nicht sagen, wie viel davon Übertrag war.

Die ``quelle``-Werte sind das Vokabular, das der Client bereits kennt
(``v4/KomponentenSektionen.tsx::wirkungsgradHinweis``) — jeder Fall hat dort
seinen Satz. Ein Wert ohne Satz ist der Zustand, der zu #163 geführt hat.

DB-frei und ohne Zeitbegriff: Tag, Monat und Jahr rufen dieselbe Formel, sie
unterscheiden sich nur darin, woher ΔSoC kommt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Unterhalb dieser Lademenge ist der Quotient Messrauschen, kein Wirkungsgrad
# (Bestandsschwelle aus ``core/berechnungen/tagesbilanz.py``).
MINDEST_LADUNG_KWH = 0.1


@dataclass(frozen=True)
class SpeicherWirkungsgrad:
    """Wirkungsgrad in Prozent (oder ``None``) **plus** die Herkunft der Aussage."""

    prozent: Optional[float]
    quelle: str


def speicher_wirkungsgrad(
    ladung_kwh: Optional[float],
    entladung_kwh: Optional[float],
    delta_soc_kwh: Optional[float] = None,
    *,
    mindest_ladung_kwh: float = MINDEST_LADUNG_KWH,
) -> SpeicherWirkungsgrad:
    """η für einen Zeitraum — mit ΔSoC-Korrektur, wenn der Ladestand vorliegt.

    ``delta_soc_kwh`` ist die Energie, die am Ende **mehr** im Speicher steht
    als am Anfang (negativ, wenn der Speicher leerer geworden ist). ``None``
    heißt „nicht gemessen" und ist nicht dasselbe wie ``0.0``: 0 behauptet
    einen unveränderten Ladestand, ``None`` behauptet nichts.

    Der korrigierte Wert wird auf 0…100 % geklemmt — bei Messfehlern oder
    Restdrift kann der Quotient auch mit ΔSoC kurz über 1,0 schießen.
    """
    lad = ladung_kwh or 0.0
    entl = entladung_kwh or 0.0
    if lad <= mindest_ladung_kwh:
        return SpeicherWirkungsgrad(None, "keine-ladung")

    if delta_soc_kwh is not None:
        eta = (entl + delta_soc_kwh) / lad
        return SpeicherWirkungsgrad(max(0.0, min(1.0, eta)) * 100, "soc_korrigiert")

    roh = entl / lad * 100
    if roh <= 100.0:
        return SpeicherWirkungsgrad(roh, "roh-unkorrigiert")
    return SpeicherWirkungsgrad(None, "nicht-ermittelbar")


def delta_soc_kwh(
    soc_prozent_werte: list[Optional[float]],
    nutzbare_kapazitaet_kwh: Optional[float],
) -> Optional[float]:
    """ΔSoC in kWh aus einer **zeitlich geordneten** Reihe von SoC-Messwerten.

    Genommen werden der **erste und der letzte gemessene** Stand, nicht 0 und
    23 Uhr: Eine Lücke am Zeitraumrand darf keinen Ladestand von 0 % vortäuschen
    (gleiche Regel wie ``v4/TagKomponenten.tsx::socTagWerte`` und
    ``services/speicher_wirtschaftlichkeit._lese_soc_am_periodenrand``).

    ``None`` — also „keine Korrektur möglich" — bei weniger als zwei Messwerten
    oder ohne nutzbare Kapazität; aus einem einzelnen Stand folgt keine
    Differenz.
    """
    werte = [v for v in soc_prozent_werte if v is not None]
    if len(werte) < 2 or not nutzbare_kapazitaet_kwh or nutzbare_kapazitaet_kwh <= 0:
        return None
    return (werte[-1] - werte[0]) / 100.0 * nutzbare_kapazitaet_kwh
