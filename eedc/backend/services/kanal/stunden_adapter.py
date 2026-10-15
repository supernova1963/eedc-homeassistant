"""Adapter des Kanal-Stundentags — die 24 Stunden in der Datenform der Stundenzeile ``TagesEnergieProfil``
(HA-Bauform S3, Etappe E-S3-1; Bauplan §4 S3-R5/S3-R6; Vorbild ``bilanz_adapter.py``: Adapter in der Datenform des
heutigen Lesers, nichts umgeschaltet).

**Stand E-S3-1: von KEINER Sicht gelesen.** Die Zeilen tragen die Felder, die ``bilanz_aus_stundenrows``,
``stundenbilanz.py`` und ``serien.get_stundenwerte`` heute aus der Stundenzeile lesen: ``pv_kw``, ``verbrauch_kw``,
``einspeisung_kw``, ``netzbezug_kw``, ``batterie_kw``, ``waermepumpe_kw``, ``wallbox_kw``, ``ueberschuss_kw``,
``defizit_kw``, ``komponenten``, ``spannen`` — **nur aus den Gruppen mit Wahl ``kanal``** (``KanalStunden.felder``
nennt sie). Die Felder, die nach S3-R6 aus der Stundenzeile bleiben (SoC, SoC je Speicher, Preise, Wetter,
Zählwerke), trägt der Adapter NICHT; der Aufrufer (E-S3-2) mischt sie aus der Stundenzeile.

**Rechnung je Stunde — nur Layer-Funktionen, keine eigene Formel** (wie ``snapshot/tages_tabelle._stundenwerte``):

* Mengen aus der Komposition der Stunde (``stunden_leser``, W2 je Stunde): ``pv_kw`` = PV + Erzeuger hinter dem
  Zähler, ``einspeisung_kw``, ``netzbezug_kw``; ``batterie_kw`` über ``stundenbilanz.berechne_batterie_netto_kwh`` und
  ``energie.batterie_kw_spalte`` (Entladung positiv).
* ``verbrauch_kw`` über ``stundenbilanz.stunden_verbrauch_kwh``, nur wenn die Spannen passen
  (``spannen.verbrauch_spannen_passen``, R6).
* ``ueberschuss_kw``/``defizit_kw`` über ``tagesbilanz.bilanz_aus_stundenrows`` auf der einen Stunde (S3-R5 — dieselbe
  Formel wie die Tagessumme), nur mit PV und Verbrauch (wie ``aggregator.verrechne_stunde``).
* ``waermepumpe_kw`` = Σ der Zähler der Kategorie ``verbrauch_wp``; ``wallbox_kw`` = Σ ``ladung_wallbox`` +
  ``verbrauch_eauto`` (die Zähler des Tagespfads, ``bilanz_adapter.zaehler_eintraege``) — je Stunde mit Zeile.
* ``komponenten`` = je Ziel-Schlüssel (``komponenten_kwh``-Form, Vorzeichen der Beitragsschicht) der Wert der Stunde:
  die Komposition der Bilanz-Gruppe und die Geräte-Zähler. ⚑ HALT H-1 im Bericht E-S3-1: ``TagesEnergieProfil.
  komponenten`` ist heute der **Leistungspfad** (Stundenmittel der Leistungssensoren, eigene Schlüssel und Vorzeichen) —
  dieser Adapter liefert die Zählerform; welche Form E-S3-2 zeigt, entscheidet der Master.
* ``spannen`` = je Achse die größte Spanne (in Stunden, nur > 1) der Kanäle, die die Stunde tragen (Form der Spalte).

``gerundet=True`` rundet wie ``aggregate_day`` beim Schreiben (``aggregator.rund``, drei Stellen); der Wächter
„Σ Stunden ≡ Tag" liest die ungerundeten Stunden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Optional, Sequence

from backend.core.berechnungen.energie import batterie_kw_spalte
from backend.core.berechnungen.spannen import achse_der_kategorie, verbrauch_spannen_passen
from backend.core.berechnungen.stundenbilanz import berechne_batterie_netto_kwh, stunden_verbrauch_kwh
from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows
from backend.services.kanal.stunden_leser import (
    GRUPPE_BILANZ,
    GRUPPE_EMOB,
    GRUPPE_SONSTIGES,
    GRUPPE_WP,
    SLOTS,
    GruppenStunden,
    KanalStundentag,
)

_STUNDE = 3600

#: Die Felder der Stundenzeile je Gruppe.
FELDER_BILANZ = ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "ueberschuss_kw",
                 "defizit_kw")
FELDER_JE_GRUPPE: dict[str, tuple[str, ...]] = {
    GRUPPE_BILANZ: FELDER_BILANZ, GRUPPE_WP: ("waermepumpe_kw",), GRUPPE_EMOB: ("wallbox_kw",),
    GRUPPE_SONSTIGES: (),
}
#: Alle Felder einer Zeile (die Stundenfelder der Spalte, ohne SoC/Preis/Wetter/Zählwerke — S3-R6).
FELDER = (*FELDER_BILANZ, "waermepumpe_kw", "wallbox_kw", "komponenten", "spannen")

_KATEGORIE_FELD = {"verbrauch_wp": "waermepumpe_kw", "ladung_wallbox": "wallbox_kw", "verbrauch_eauto": "wallbox_kw"}


@dataclass(frozen=True)
class KanalStunden:
    """Die 24 Zeilen eines Kanal-Stundentags in der Form der Stundenzeile."""

    datum: date
    zeilen: tuple[SimpleNamespace, ...]
    #: Die Felder, die aus den Kanälen kommen (Gruppen mit Wahl ``kanal``); ``komponenten``/``spannen`` tragen dann
    #: nur deren Anteile. Fehlt ein Feld hier, steht es in jeder Zeile auf ``None`` — der Aufrufer nimmt die
    #: Stundenzeile.
    felder: frozenset[str]
    klemm_stunden: tuple[int, ...]


def _rund(wert, gerundet: bool):
    if not gerundet or wert is None:
        return wert
    from backend.services.energie_profil.aggregator import rund

    return rund(wert, 3)


def _spannen_der_stunde(gruppen: Sequence[GruppenStunden], h: int) -> dict[str, int]:
    """Je Achse die größte Spanne (in Stunden) der Kanäle mit Zeile in der Stunde — wie ``tages_tabelle``: nur > 1."""
    out: dict[str, int] = {}
    for gs in gruppen:
        for e in gs.eintraege:
            s = gs.spannen.get(e.schluessel)
            achse = achse_der_kategorie(e.kategorie)
            if s is None or s[h] is None or achse is None:
                continue
            n = round(s[h] / _STUNDE)
            if n > 1:
                out[achse] = max(out.get(achse, 1), n)
    return out


def _bilanz_der_stunde(tag: KanalStundentag, h: int, spannen: dict[str, int]) -> dict:
    """Die Bilanz-Felder einer Stunde aus ihrer Komposition (Layer-Funktionen, S3-R5)."""
    k = tag.bilanz.kompositionen[h] if tag.bilanz is not None else None
    if k is None:
        return {f: None for f in FELDER_BILANZ}
    kat = k.kat_summe
    pv = k.bilanz.erzeugung_kwh if k.bilanz.pv_erfasst else None
    einsp = kat.get("einspeisung")
    netz = kat.get("netzbezug")
    ladung = -kat["ladung_batterie"] if "ladung_batterie" in kat else None
    netto = berechne_batterie_netto_kwh(ladung_kwh=ladung, entladung_kwh=kat.get("entladung_batterie"))
    verbrauch = (stunden_verbrauch_kwh(pv_kwh=pv, netzbezug_kwh=netz, einspeisung_kwh=einsp,
                                       batterie_netto_kwh=netto)
                 if verbrauch_spannen_passen(spannen, batterie_da=netto is not None) else None)
    ueberschuss = defizit = None
    if pv is not None and verbrauch is not None:
        b = bilanz_aus_stundenrows([SimpleNamespace(pv_kw=pv, verbrauch_kw=verbrauch, einspeisung_kw=None,
                                                    netzbezug_kw=None, batterie_kw=None, waermepumpe_kw=None)])
        ueberschuss, defizit = b.ueberschuss_kwh, b.defizit_kwh
    return {"pv_kw": pv, "verbrauch_kw": verbrauch, "einspeisung_kw": einsp, "netzbezug_kw": netz,
            "batterie_kw": batterie_kw_spalte(netto), "ueberschuss_kw": ueberschuss, "defizit_kw": defizit}


def _geraete_der_stunde(gruppen: Sequence[GruppenStunden], h: int, komponenten: dict) -> dict:
    """``waermepumpe_kw``/``wallbox_kw`` der Stunde und die Geräte-Schlüssel in ``komponenten``."""
    felder: dict[str, Optional[float]] = {}
    for gs in gruppen:
        for e in gs.eintraege:
            wert = gs.mengen[e.schluessel][h]
            if wert is None:
                continue
            wert = e.vorzeichen * wert
            komponenten[e.target_key] = komponenten.get(e.target_key, 0.0) + wert
            feld = _KATEGORIE_FELD.get(e.kategorie)
            if feld is not None:
                felder[feld] = (felder.get(feld) or 0.0) + wert
    return felder


def stunden_aus_kanaelen(tag: KanalStundentag, *, gerundet: bool = True) -> KanalStunden:
    """Die 24 Zeilen eines Kanal-Stundentags (``stunden_leser.kanal_stundentag``) in der Form der Stundenzeile."""
    felder = {f for g in tag.gruppen for f in FELDER_JE_GRUPPE.get(g, ())}
    if tag.gruppen:
        felder |= {"komponenten", "spannen"}
    alle = list(tag.gruppen.values())
    geraete = [gs for g, gs in tag.gruppen.items() if g != GRUPPE_BILANZ]
    zeilen = []
    for h in range(SLOTS):
        spannen = _spannen_der_stunde(alle, h)
        werte = _bilanz_der_stunde(tag, h, spannen)
        k = tag.bilanz.kompositionen[h] if tag.bilanz is not None else None
        komponenten: dict[str, float] = dict(k.komponenten) if k is not None else {}
        werte.update(_geraete_der_stunde(geraete, h, komponenten))
        zeile = {f: _rund(werte.get(f), gerundet) for f in FELDER if f not in ("komponenten", "spannen")}
        zeilen.append(SimpleNamespace(
            stunde=h, **zeile, spannen=spannen or None,
            komponenten={kk: _rund(v, gerundet) for kk, v in komponenten.items()} or None,
        ))
    return KanalStunden(tag.datum, tuple(zeilen), frozenset(felder), tag.klemm_stunden)


__all__ = ["FELDER", "FELDER_BILANZ", "FELDER_JE_GRUPPE", "KanalStunden", "stunden_aus_kanaelen"]
