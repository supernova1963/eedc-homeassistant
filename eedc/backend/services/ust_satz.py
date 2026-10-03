"""USt auf den Eigenverbrauch — der EINE Eingang des Satzes (Gegenprüfung G1, Entscheid E9, Register N-601).

**Warum es diesen Service gibt.** Die Formel steht seit N-129/N-130 im Layer (``core/berechnungen/ust_eigenverbrauch``),
aber **welche Mengen und welche Investitionen in den Satz eingehen**, wählte jede Sicht selbst — sieben
``UstJahresanteil(``-Bildungsstellen, drei Lesarten. Gemessen am 03.10.2026 (Fixture: drei Monate Regelbesteuerung,
eine Wallbox ``aktiv=False`` mit 1 000 € / 600 €): **Übersicht 20,21 € · Monatsreihe 35,96 € · Monatsroute 18,90 €**
für dasselbe Jahr. Ohne die inaktive Wallbox nannten alle drei 18,90 €.

**Die eine Regel (Aufbereitung, deshalb hier und nicht im Layer — ADR-001 „Aufbereitung ≠ Formel"):**

* **Investitionen:** ``ist_aktiv_im_zeitraum(1.1.–31.12. des Jahres)`` für Bemessungsgrundlage **und**
  Betriebskosten. Das ist Gernots Regel vom 05.06.2026 (``models/investition.py::ist_aktiv_im_zeitraum``):
  ``aktiv=False`` ist „wie gelöscht", auch historisch; eine im Jahr gelaufene und später stillgelegte Komponente zählt
  in diesem Jahr. Bis hierhin nahm die Übersicht für die Bemessung **alle** Investitionen („KEIN aktiv-Filter",
  Issue #123 — eine Regel für Mengen, nicht für Kosten) und für die Betriebskosten die **heute** aktiven; die
  Monatsreihe nahm alle für beides.
* **Monate (Grundgesamtheit des Jahres):** die Monats-Fakten des Kalenderjahres mit **Zählerzeile** und **aktivem
  Erzeuger** (``meta.hat_zaehlerzeile and meta.erzeuger_aktiv``) — die abgeschlossenen Monate, in denen die Anlage lief;
  dieselbe Menge, über die die Übersicht ihre Finanz-Zeilen bildet. ``monate`` ist ihre Anzahl (Anteiligkeit N-130).
* **Eigenverbrauch:** Σ der **Monats**-Eigenverbräuche (``fakt.kennzahlen.eigenverbrauch_kwh`` — dieselben Eingänge
  wie die Finanz-Zeile, ``finanz_zeile_eingabe``). Nur so gilt Σ der Monatsanteile = Jahreswert; die Perioden-EV
  (Summen erst addiert, dann einmal geklemmt), die Übersicht und HA-Export bisher übergaben, weicht in Monaten mit
  Einspeisung > PV davon ab.
* **PV:** Σ ``erzeugung.pv_kwh`` derselben Monate.

**Rückfall (§3.4 der Vorlage):** Hat das Jahr noch keinen solchen Monat (Januar des laufenden Jahres), gilt der Satz
des Vorjahres — sofern dessen Fakten mitgegeben sind. Gibt es auch dort keinen, ist der Satz **nicht ermittelbar**
(``euro_je_kwh is None``) und die Herleitung sagt es (ADR-002/P4). Ein Jahr ohne PV-Erzeugung hat den Satz 0.

**Im laufenden Jahr wandert der Satz** mit jedem Abschluss (Jan–Jun → Jan–Jul) und mit ihm der USt-Anteil eines schon
abgeschlossenen Monats um Cent-Beträge — die Natur einer Jahressteuer; die Herleitung nennt die Grundlage.
Abgeschlossene Jahre sind stabil.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Sequence

from backend.core.berechnungen.ergebnis import MONAT_KURZ, ust_satz_euro_je_kwh
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    berechne_ust_eigenverbrauch,
)
from backend.core.zahlenformat import fmt_zahl


def ist_regelbesteuert(anlage) -> bool:
    """Gilt die USt auf den Eigenverbrauch für diese Anlage? (``anlage`` nur per ``getattr``.)"""
    return (getattr(anlage, "steuerliche_behandlung", None) or "keine_ust") == "regelbesteuerung"


def ust_satz_prozent(anlage) -> float:
    satz = getattr(anlage, "ust_satz_prozent", None)
    return satz if satz is not None else 19.0


def investitionen_im_jahr(investitionen: Iterable, jahr: int) -> list:
    """Die Investitionen, deren Kosten in den Satz des Jahres eingehen (Regel 05.06.2026)."""
    start, ende = date(jahr, 1, 1), date(jahr, 12, 31)
    return [i for i in investitionen if i.ist_aktiv_im_zeitraum(start, ende)]


def grundgesamtheit(fakten: Iterable, jahr: int) -> list:
    """Die abgeschlossenen Monate des Jahres, in denen die Anlage lief (Zählerzeile + aktiver Erzeuger)."""
    return [
        f for f in fakten
        if f.jahr == jahr and f.meta.hat_zaehlerzeile and f.meta.erzeuger_aktiv
    ]


def ust_jahresanteil(fakten: Iterable, jahr: int) -> UstJahresanteil:
    """EV, PV und Monatszahl des Jahres — der Eingang der Jahresformel (G1)."""
    g = grundgesamtheit(fakten, jahr)
    ev = 0.0
    pv = 0.0
    for f in g:
        ev += f.kennzahlen.eigenverbrauch_kwh
        pv += f.erzeugung.pv_kwh
    return UstJahresanteil(jahr=jahr, eigenverbrauch_kwh=ev, pv_kwh=pv, monate=len(g))


def kosten_des_jahres(investitionen: Iterable, jahr: int) -> tuple[float, float]:
    """(Bemessungsgrundlage, Betriebskosten/Jahr) über die im Jahr aktiven Investitionen."""
    invs = investitionen_im_jahr(investitionen, jahr)
    return (
        bemessungsgrundlage_aus_investitionen(invs),
        sum((i.betriebskosten_jahr or 0) for i in invs),
    )


@dataclass(frozen=True)
class UstSatz:
    """Der Satz eines Jahres samt Grundlage — für Monatsanteil und Herleitung."""

    jahr: int
    #: Das Jahr, dessen Abschlüsse den Satz tragen (``jahr - 1`` im Rückfall).
    grundlage_jahr: int
    anteil: Optional[UstJahresanteil]
    monate_grundlage: tuple[int, ...]
    bemessungsgrundlage_euro: float
    betriebskosten_jahr_euro: float
    ust_satz_prozent: float
    #: USt je kWh Eigenverbrauch (€/kWh); ``None`` = nicht ermittelbar (P4).
    euro_je_kwh: Optional[float]

    @property
    def selbstkosten_euro_je_kwh(self) -> Optional[float]:
        if self.euro_je_kwh is None or self.ust_satz_prozent <= 0:
            return None
        return self.euro_je_kwh * 100 / self.ust_satz_prozent

    def herleitung(self, eigenverbrauch_kwh: Optional[float] = None) -> str:
        """Ein Satz, der Satz und Grundlage nennt (Anzeige-Text, Backend-SoT)."""
        if self.euro_je_kwh is None:
            return (
                f"USt auf den Eigenverbrauch nicht ermittelbar: {self.jahr} und {self.jahr - 1} haben keinen "
                "abgeschlossenen Monat mit PV-Erzeugung, aus dem sich die Selbstkosten je kWh bilden ließen."
            )
        monate = _monatsbereich(self.monate_grundlage)
        grundlage = f"Grundlage {monate} {self.grundlage_jahr}" if monate else f"Grundlage {self.grundlage_jahr}"
        if self.grundlage_jahr != self.jahr:
            grundlage += f" (für {self.jahr} gibt es noch keinen Abschluss)"
        selbst = self.selbstkosten_euro_je_kwh
        satz = (
            f"Selbstkosten {fmt_zahl((selbst or 0) * 100, 2)} ct/kWh × {fmt_zahl(self.ust_satz_prozent, 0)} % "
            f"= {fmt_zahl(self.euro_je_kwh * 100, 3)} ct je kWh Eigenverbrauch"
        )
        ev = f"{fmt_zahl(eigenverbrauch_kwh, 1)} kWh Eigenverbrauch × " if eigenverbrauch_kwh is not None else ""
        return f"{ev}{satz} ({grundlage})"


def _monatsbereich(monate: Sequence[int]) -> str:
    if not monate:
        return ""
    teile: list[str] = []
    start = vorher = monate[0]
    for m in list(monate[1:]) + [None]:
        if m is not None and m == vorher + 1:
            vorher = m
            continue
        teile.append(MONAT_KURZ[start] if start == vorher else f"{MONAT_KURZ[start]}–{MONAT_KURZ[vorher]}")
        if m is not None:
            start = vorher = m
    return ", ".join(teile)


def ust_satz_des_jahres(anlage, investitionen: Iterable, fakten: Sequence, jahr: int) -> Optional[UstSatz]:
    """Der Satz des Jahres — ``None``, wenn die Anlage keine Regelbesteuerung hat (dann gibt es keine USt).

    Rückfall auf das Vorjahr, wenn ``jahr`` keinen Grundgesamtheits-Monat hat und die Vorjahres-Fakten mitgegeben sind.
    """
    if not ist_regelbesteuert(anlage):
        return None
    investitionen = list(investitionen)
    prozent = ust_satz_prozent(anlage)
    for grund_jahr in (jahr, jahr - 1):
        g = grundgesamtheit(fakten, grund_jahr)
        if not g:
            continue
        anteil = ust_jahresanteil(g, grund_jahr)
        bemessung, bk = kosten_des_jahres(investitionen, grund_jahr)
        return UstSatz(
            jahr=jahr, grundlage_jahr=grund_jahr, anteil=anteil,
            monate_grundlage=tuple(sorted(f.monat for f in g)),
            bemessungsgrundlage_euro=bemessung, betriebskosten_jahr_euro=bk,
            ust_satz_prozent=prozent,
            euro_je_kwh=ust_satz_euro_je_kwh(
                anteil, bemessungsgrundlage_euro=bemessung, betriebskosten_jahr_euro=bk, ust_satz_prozent=prozent,
            ),
        )
    return UstSatz(
        jahr=jahr, grundlage_jahr=jahr, anteil=None, monate_grundlage=(),
        bemessungsgrundlage_euro=0.0, betriebskosten_jahr_euro=0.0, ust_satz_prozent=prozent, euro_je_kwh=None,
    )


def ust_eigenverbrauch_zeitraum(anlage, investitionen: Iterable, fakten: Sequence) -> float:
    """USt über alle Kalenderjahre der gegebenen Fakten (Übersicht, PDF, HA-Export, Monatsreihe, ROI, Rückblick).

    Je Jahr ``berechne_ust_eigenverbrauch`` mit dem Eingang oben — Σ der Monatsanteile desselben Jahres ist (bis auf
    die Rundung je Monat) genau dieser Wert. 0 ohne Regelbesteuerung.
    """
    if not ist_regelbesteuert(anlage):
        return 0.0
    investitionen = list(investitionen)
    prozent = ust_satz_prozent(anlage)
    jahre = sorted({f.jahr for f in fakten})
    summe = 0.0
    for jahr in jahre:
        anteil = ust_jahresanteil(fakten, jahr)
        if anteil.monate == 0:
            continue
        bemessung, bk = kosten_des_jahres(investitionen, jahr)
        summe += berechne_ust_eigenverbrauch(
            [anteil], bemessungsgrundlage_euro=bemessung, betriebskosten_jahr_euro=bk, ust_satz_prozent=prozent,
        )
    return summe


def ust_hochrechnung(anlage, investitionen: Iterable, jahr: int, eigenverbrauch_kwh: float, pv_kwh: float) -> float:
    """USt für eine auf zwölf Monate HOCHGERECHNETE Jahresmenge (ROI-Dashboard, Aussichten-Prognose).

    Die Mengen sind kein Zeitraum-Aggregat (N-130 greift nicht ⇒ ein Anteil mit ``monate=12``); die Investitionsmenge
    folgt derselben Regel wie überall (im Kalenderjahr ``jahr`` aktiv, für Bemessung UND Betriebskosten). 0 ohne
    Regelbesteuerung.
    """
    if not ist_regelbesteuert(anlage):
        return 0.0
    bemessung, bk = kosten_des_jahres(investitionen, jahr)
    return berechne_ust_eigenverbrauch(
        [UstJahresanteil(jahr=jahr, eigenverbrauch_kwh=eigenverbrauch_kwh, pv_kwh=pv_kwh, monate=12)],
        bemessungsgrundlage_euro=bemessung, betriebskosten_jahr_euro=bk, ust_satz_prozent=ust_satz_prozent(anlage),
    )
