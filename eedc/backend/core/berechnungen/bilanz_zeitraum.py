"""Die Bilanz-Gruppe eines Zeitraums aus Zeitraum-Differenzen — Weg 2 (HA-Bauform E4a-2, Bauplan §6b).

**Eine Funktion für jeden Zeitraum** (Tag, Monat, Jahr über das Monatsraster): Eingang ist je Feld-Kanal der
Bilanz-Gruppe (Netz, PV/Balkonkraftwerk samt Anlagenzähler, Speicher Ladung/Entladung, Erzeuger hinter dem Zähler)
das Δ über den Zeitraum — ``None``, wenn sein Kanal den Zeitraum nicht voll deckt —, dazu die Stammdaten der
PV-Träger. Ausgang: der Wert je Gerät (``komponenten``-Schlüssel wie ``TagesZusammenfassung.komponenten_kwh``), die
Marke ``kwp_anteil``, die Summen je Kategorie, die PV-Summe der Bilanz (W2-R3: Σ Geräte), die Wandlungsverluste (nur geführt)
und die Bilanz selbst (``tagesbilanz.bilanz_aus_stundenrows`` — dieselbe Layer-Funktion wie am Tag des Bestands).

Die fünf Regeln (abgenommen von Gernot 06.10.2026):

* **W2-R1/R2/R3/R5** stehen in ``pv_verteilung.loese_pv_zeitraum_auf`` (die Monatsregel P7 auf jeden Zeitraum).
* **W2-R4 Entweder-oder** — je Zeitraum der erste Kanal der Gruppe mit voller Deckung. Gruppenbildung wie heute
  (``fallback_gruppe`` der Beitragsschicht); die Wahl trifft der Aufrufer mit der EINEN Funktion dafür,
  ``services/snapshot/komponenten_beitraege.resolve_either_or_eintraege`` mit dem Prädikat „Δ ist nicht ``None``" —
  hier kommen nur noch die gewählten Eingänge an (``Eingang``).

**Die Bilanz** entsteht über zwei Eingangszeilen an ``bilanz_aus_stundenrows`` (Regel R7, ``verworfen={}``): die
Mengen sind die Σ des Zeitraums; Ladung und Entladung stehen in getrennten Zeilen, damit das Zeilenvorzeichen
(``batterie_kw``) sie nicht verrechnet. Stundengepaarte Größen (Direktverbrauch, Überschuss, Defizit) sind hier 0 —
sie sind keine Zeitraum-Differenz und bleiben bis S3 aus den Stundenzeilen (Entscheid D4). Kein Deckel, kein
Rücksprung-Verwurf: der Spiegel trägt, was HA trägt (R-5, HA-Teil).

ADR-001: keine Session, kein Sensor, keine Zuordnung — nur Zahlen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional, Sequence

from backend.core.berechnungen.pv_verteilung import PvTraeger, PvZeitraum, loese_pv_zeitraum_auf
from backend.core.berechnungen.tagesbilanz import TagesBilanz, bilanz_aus_stundenrows

#: Marke eines kWp-Anteils (``services/provenance.ABGELEITET_KWP_ANTEIL`` — hier als Wert, der Layer importiert
#: keine Services; Gleichheit hält ``test_bilanz_zeitraum.py``).
KWP_ANTEIL = "kwp_anteil"
#: Präfix der Schlüssel je PV-Typ (wie ``snapshot/komponenten_beitraege._TYP_KEY_PREFIX``).
PV_SCHLUESSEL_PRAEFIX: dict[str, str] = {"pv-module": "pv_", "balkonkraftwerk": "bkw_"}


@dataclass(frozen=True)
class Eingang:
    """Ein Feld-Kanal der Bilanz-Gruppe im Zeitraum, nach der Entweder-oder-Wahl.

    ``kategorie`` wie die Beitragsschicht (``pv``, ``einspeisung``, ``netzbezug``, ``ladung_batterie``,
    ``entladung_batterie``, ``erzeugung_sonstiges``); ``ziel`` der ``komponenten``-Schlüssel, ``vorzeichen`` ±1.
    PV: ``pv_inv_id`` = das Gerät, ``None`` = der Anlagenzähler. ``delta`` = Δ bei voller Deckung, sonst ``None``.
    """

    kategorie: str
    ziel: str
    vorzeichen: int
    delta: Optional[float]
    pv_inv_id: Optional[int] = None


@dataclass
class BilanzZeitraum:
    """Ergebnis von ``komponiere_bilanz_zeitraum`` (Werte ungerundet; die Rundung ist Sache des Lesers)."""

    komponenten: dict[str, float]
    marken: dict[str, str]
    kat_summe: dict[str, float]
    pv: Optional[PvZeitraum]
    bilanz: TagesBilanz
    #: Die Einträge mit Wert (Diagnose).
    mit_wert: list = field(default_factory=list)


def komponiere_bilanz_zeitraum(
    eingaenge: Sequence[Eingang], traeger: Sequence[PvTraeger],
) -> Optional[BilanzZeitraum]:
    """W2 auf den Δ EINES Zeitraums. ``traeger``: die im Zeitraum aktiven PV-Erzeuger. ``None``, wenn kein Eingang
    einen Wert hat (keine Aussage — wie ein Tag ohne Tageszeile)."""
    mit = [e for e in eingaenge if e.delta is not None]
    if not mit:
        return None
    komponenten: dict[str, float] = {}
    kat_summe: dict[str, float] = {}

    def _nimm(kat: str, ziel: str, wert: float) -> None:
        kat_summe[kat] = kat_summe.get(kat, 0.0) + wert
        komponenten[ziel] = komponenten.get(ziel, 0.0) + wert

    anlagenzaehler: Optional[float] = None
    eigen: dict[int, float] = {}
    for e in mit:
        if e.kategorie == "pv":
            if e.pv_inv_id is None:
                anlagenzaehler = (anlagenzaehler or 0.0) + e.delta
            else:
                eigen[e.pv_inv_id] = eigen.get(e.pv_inv_id, 0.0) + e.delta
            continue
        _nimm(e.kategorie, e.ziel, e.vorzeichen * e.delta)

    marken: dict[str, str] = {}
    pv: Optional[PvZeitraum] = None
    if eigen or anlagenzaehler is not None:
        pv = loese_pv_zeitraum_auf(traeger=list(traeger), eigen=eigen, anlagenzaehler_kwh=anlagenzaehler)
        typ_je_id = {t.inv_id: t.typ for t in traeger}
        for inv_id, wert in pv.werte.items():
            praefix = PV_SCHLUESSEL_PRAEFIX.get(typ_je_id.get(inv_id))
            if praefix is None:
                continue
            komponenten[f"{praefix}{inv_id}"] = komponenten.get(f"{praefix}{inv_id}", 0.0) + wert
            if inv_id in pv.verteilt:
                marken[f"{praefix}{inv_id}"] = KWP_ANTEIL
        if pv.bilanz_kwh is not None:
            kat_summe["pv"] = pv.bilanz_kwh

    pv_total = None
    if "pv" in kat_summe or "erzeugung_sonstiges" in kat_summe:
        pv_total = kat_summe.get("pv", 0.0) + kat_summe.get("erzeugung_sonstiges", 0.0)
    ladung = -kat_summe["ladung_batterie"] if "ladung_batterie" in kat_summe else None
    entladung = kat_summe.get("entladung_batterie")
    zeilen = [SimpleNamespace(
        pv_kw=pv_total, verbrauch_kw=None, einspeisung_kw=kat_summe.get("einspeisung"),
        netzbezug_kw=kat_summe.get("netzbezug"), batterie_kw=entladung, waermepumpe_kw=None,
    )]
    if ladung is not None:
        zeilen.append(SimpleNamespace(pv_kw=None, verbrauch_kw=None, einspeisung_kw=None, netzbezug_kw=None,
                                      batterie_kw=-ladung, waermepumpe_kw=None))
    return BilanzZeitraum(komponenten, marken, kat_summe, pv, bilanz_aus_stundenrows(zeilen, verworfen={}), mit)


__all__ = ["BilanzZeitraum", "Eingang", "KWP_ANTEIL", "PV_SCHLUESSEL_PRAEFIX", "komponiere_bilanz_zeitraum"]
