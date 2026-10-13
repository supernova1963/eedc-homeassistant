"""Speicher-Netzladung eines Monats aus den Tagen — die EINE Rechenstelle (#427 Punkt 2, Entscheid Gernot 13.10.2026).

Bis zum 13.10.2026 stand der Bereichs-Leser-Pfad in der Route *Cockpit → Monat* (`aktueller_monat/komponenten.py`) und
galt nur im laufenden Monat; die Monats-Fakten ließen die Netzladung im Tageswert-Rückfall aus (N-121-Lesart: „eine
Preis-Aussage, und die trägt die Tagesebene nicht"). Seit #427 trägt der Tag Menge **und** Preis — deshalb steht beides
hier, und zwei Leser rufen dieselbe Funktion:

* der Tageswert-Rückfall der Monats-Fakten (`laden.py` → `bau._baue_fakt`, jeder Monat ohne Speicher-Zeile mit Tagen,
  dieselbe Regel wie Ladung/Entladung),
* *Cockpit → Monat* für jeden Monat ohne Speicher-Zeile. Die Route hat für genau diese Monate keinen Fakt (ihr Kontext
  lädt ohne ``inkl_nur_tageswerte``, Ladung/Entladung kommen dort aus der Vier-Quellen-Auflösung) — sie ruft deshalb
  diese Funktion statt einer eigenen Zweitschrift (Entscheid Master 13.10.2026, Option A).
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass(frozen=True)
class NetzladungTage:
    """Netzladung eines Monats als Σ der abgelaufenen Tage, mit dem Preis der Tage.

    ``preis_summe_cent_kwh``/``gewicht_kwh`` in der Form von `SpeicherFakten.netzladung_preis_*` (Summe und Gewicht
    getrennt): der TEP-gewichtete Ladepreis (`berechne_effektiver_ladepreis`, derselbe Helfer wie *Cockpit → Tag*).
    Ohne belastbaren Stundenpreis (kein dynamischer Tarif, Standalone) bleiben beide 0 — dann greift bei jedem Leser
    die Kette auf den Bezugspreis (`berechne_netzladung_kosten`), wie am Tag.
    """

    kwh: float
    preis_summe_cent_kwh: float = 0.0
    gewicht_kwh: float = 0.0


def _fenster(jahr: int, monat: int, heute: date) -> Optional[tuple[date, date]]:
    """``[1., min(Monatsende, gestern)]`` — der heutige Tag hat seinen rechten Rand noch nicht."""
    von = date(jahr, monat, 1)
    bis = min(date(jahr, monat, monthrange(jahr, monat)[1]), heute - timedelta(days=1))
    return None if bis < von else (von, bis)


async def speicher_netzladung_aus_tagen(db, anlage, speicher_invs, jahr: int, monat: int, heute: date) -> Optional[float]:
    """Die Netzladung des Speichers im Monat als Σ der abgelaufenen Tage — dieselbe Boundary-Differenz wie
    *Cockpit → Tag* (`get_tagesdetail_kwh`), über den Bereichs-Leser in EINER Standreihe je Zähler.

    * **Feldmenge und Fenster aus den geteilten Tabellen**: `aggregator.TAGESDETAIL_AUSGABE` (`speicher/ladung_netz_kwh`
      → `speicher_ladung_netz_kwh`) und `boundary_range.TAGESFENSTER_JE_TYP["speicher"]` (rückwärts: je Tag
      [Vortag 23:00, 23:00) — derselbe Tag wie die Speicher-Ladung der Tagesbilanz).
    * **Nur abgelaufene Tage** (bis gestern): der heutige Tag hat seinen rechten Rand noch nicht.
    * **Ein Tag mit Rücksprung oder ohne Rand fehlt** (Bereichs-Leser) — keine 0 als Platzhalter. Ohne zugeordneten
      Netzlade-Zähler oder ohne einen einzigen Tageswert: ``None``. Eine gemessene 0 bleibt 0.
    * Kein neuer Tagesschlüssel, kein Nachfüllen alter Tage; eine Speicher-Zeile ersetzt den Wert (P8, gespeichert
      schlägt gerechnet — das Tor steht beim Aufrufer).
    """
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld
    from backend.services.snapshot.boundary_range import TAGESFENSTER_JE_TYP

    if anlage is None or not speicher_invs:
        return None
    fenster = _fenster(jahr, monat, heute)
    if fenster is None:
        return None
    von, bis = fenster
    felder = {k: v for k, v in TAGESDETAIL_AUSGABE.items() if k == ("speicher", "ladung_netz_kwh")}
    ausgabe_key = felder[("speicher", "ladung_netz_kwh")]
    tage = [von + timedelta(days=i) for i in range((bis - von).days + 1)]
    rueckwaerts = frozenset(tage) if TAGESFENSTER_JE_TYP.get("speicher") == "rueckwaerts" else frozenset()
    je_tag = await lade_tageswerte_je_feld(
        db, anlage, {str(i.id): i for i in speicher_invs}, von, bis, felder, rueckwaerts_tage=rueckwaerts,
    )
    werte = [w[ausgabe_key] for w in je_tag.values() if ausgabe_key in w]
    return sum(werte) if werte else None


async def netzladung_aus_tagen(db, anlage, speicher_invs, jahr: int, monat: int, heute: date) -> Optional[NetzladungTage]:
    """Menge (`speicher_netzladung_aus_tagen`) und Preis der Tage für den Tageswert-Rückfall der Monats-Fakten.

    Der Preis über dasselbe Fenster wie die Menge und denselben Helfer wie der Tag (`berechne_effektiver_ladepreis`,
    TEP-gewichtet, nur bei dynamischem Tarif ein Wert); übernommen wird er nur, wenn er > 0 ist — dieselbe Schwelle wie
    die Kette in `berechne_netzladung_kosten`.
    """
    kwh = await speicher_netzladung_aus_tagen(db, anlage, speicher_invs, jahr, monat, heute)
    if kwh is None:
        return None
    if kwh <= 0:
        return NetzladungTage(kwh=kwh)
    from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis

    von, bis = _fenster(jahr, monat, heute)
    eff = await berechne_effektiver_ladepreis(db, anlage_id=anlage.id, von=von, bis=bis)
    preis = eff.effektiver_ladepreis_cent
    if preis is None or preis <= 0:
        return NetzladungTage(kwh=kwh)
    return NetzladungTage(kwh=kwh, preis_summe_cent_kwh=kwh * preis, gewicht_kwh=kwh)
