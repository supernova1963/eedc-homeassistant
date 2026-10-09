"""Zweite Abnahme-Matrix — Netz · Speicher · Wärmepumpe · E-Mobilität · Sonstiges · Preis.

Baustein (Formen, Seed, Schreibwege, Messfunktionen): ``achsen_matrix.py``. Vorbild und Bauform:
``test_pv_achse_matrix.py`` (Zellen, ``BEKANNT``/``SOLL_UNKLAR``, Messung je Lauf einmal).

**Was eine Zelle ist.** Form (M01–M10) × Größe × Weg × Invariante. Größe ist eine der sechs Achsen
(``netz`` · ``speicher`` · ``wp`` · ``emob`` · ``sonstiges`` · ``preis``) — nur die, die die Form trägt.
Weg wie in der PV-Matrix: ``HA``/``SA`` (Datenstand: Tag + laufender Monat), ``S1``/``S2``/``S3``
(Schreibweg des abgeschlossenen Monats). Jede Zelle prüft alle Sichten ihrer Invariante für alle
Mengen der Größe; was sie zählt, steht in ``KATALOG`` und ``bewerte``.

**Die Invarianten** (Auftrag, je Größe): I1 eine Zahl je Menge in allen Monats-Sichten (Referenz:
abgeschlossen die Monats-Fakten, laufend Cockpit → Monat) · I2 Zeitebenen (Σ Tage = laufender Monat;
vor = nach dem Abschluss) · I3 Soll der Form aus den gesäten Raten · I4 je Gerät (Σ Geräte = Summe;
ein Gerät mit Zähler trägt seinen Messwert) · I5 Folgekennzahlen (Eigenverbrauch, Autarkie,
Gesamtverbrauch, Arbeitszahl, Wirkungsgrad/Vollzyklen, Stromkosten folgen den Mengen derselben Sicht;
gemessene 0 bleibt 0) · I6 nichts verschwindet.

**Drei Arten nicht-grüner Sichten**, alle benannt, keine still ausgelassen:

* ``ROT`` — rot gegen HEAD, ``xfail(strict=True, raises=BekannterMangel)`` mit genau diesen Sichten.
  Ursachen: ``N-586`` · ``N-585-REST`` · ``OHNE-ABSCHLUSS`` · ``KANDIDAT-<Kurzname>`` (nur gezeigt);
  ``SAMMELIMPORT`` kommt auf diesen Achsen nicht vor (gemessen: keine Sicht ist nur auf S2 rot).
  ``OHNE-ABSCHLUSS`` ist der Ausgangszustand des Auftrags — eine Größe, die im Monat ohne Abschluss nicht aus
  der Tagesebene gefüllt wird, kein Mangel dieser Matrix; als benannte Erwartung geführt, damit ein Umbau, der
  sie füllt, die Markierung zwingend entfernt.
* ``SOLL_UNKLAR`` — die Regel legt das Soll nicht fest (u. a. alles, was K1–K5 für Wärme/Klima nicht
  hergeben: diese Fachfragen entscheidet der Master). Gemessen und gezeigt, nicht bewertet.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx
from backend.tests.matrix_haltewerte import ACHSEN_HALTEWERTE

# ── Messung je Lauf einmal (Bauform der PV-Matrix) ──────────────────────────

_MESSUNGEN: dict[tuple[str, str], am.Messung] = {}


@pytest.fixture(scope="session")
def _matrix_ordner(tmp_path_factory) -> Optional[Path]:
    if not os.environ.get("PYTEST_XDIST_WORKER") or fcntl is None:
        return None
    ordner = tmp_path_factory.getbasetemp().parent / "achsen-matrix"
    ordner.mkdir(exist_ok=True)
    return ordner


async def _miss(fid: str, teil: str) -> am.Messung:
    m = am.Messung(am.MATRIX_FORMEN[fid])
    if teil == "HA":
        await am.messe_ha(m.form, m)
    else:
        await am.messe_sa(m.form, m)
    return m


def _json(m: am.Messung) -> dict:
    return json.loads(json.dumps({"tage": m.tage, "laufend": m.laufend, "vor": m.vor, "nach": m.nach,
                                  "nutzlast": m.nutzlast, "ids": m.ids}, default=str))


async def _messung(fid: str, teil: str, ordner: Optional[Path]) -> am.Messung:
    schluessel = (fid, teil)
    if schluessel in _MESSUNGEN:
        return _MESSUNGEN[schluessel]
    if ordner is None:
        d = _json(await _miss(fid, teil))
    else:
        datei = ordner / f"{fid}-{teil}.json"
        with open(ordner / f"{fid}-{teil}.lock", "w") as sperre:
            fcntl.flock(sperre, fcntl.LOCK_EX)
            try:
                if not datei.exists():
                    datei.write_text(json.dumps(_json(await _miss(fid, teil))), encoding="utf-8")
                d = json.loads(datei.read_text(encoding="utf-8"))
            finally:
                fcntl.flock(sperre, fcntl.LOCK_UN)
    # Jede Zelle bewertet dieselben Bytes (JSON-Rundreise auch ohne xdist).
    m = am.Messung(am.MATRIX_FORMEN[fid], d["tage"], d["laufend"], d["vor"], d["nach"], d["nutzlast"], d["ids"])
    _MESSUNGEN[schluessel] = m
    return m


def _teil(weg: str) -> str:
    return "HA" if weg in ("HA", "S1", "S2") else "SA"


# ── Soll aus den gesäten Raten ──────────────────────────────────────────────

UNKLAR = object()


def _verworfen(form: am.Form, tage, weg: str) -> list:
    """Stunden, die die Regel verwirft — seit HA-Bauform E4a-2 keine mehr (N-586, Soll umgedreht, Bauplan §7: „Tag =
    Monat = HA; der Sprung steht in beiden"). Bis dahin verwarf die Tagesregel die Sprung-Stunde (Spannen-Deckel);
    die Kanal-Leser nehmen den Spiegel wie das HA-Energie-Dashboard, ohne Deckel (R-5, HA-Teil)."""
    return []


def _sprung_kwh(form, sensor: str, tage, weg: str) -> float:
    """N-586 (E4a-2): der Zählersprung, den HAs ``sum`` in diesen Tagen trägt — er steht im Soll (Tag = Monat = HA).
    Nur mit HA-Statistik (die Standalone-Stände und die Handeingabe tragen ihn nicht)."""
    if sensor not in form.sprung or weg in ("SA", "S3"):
        return 0.0
    return am.SPRUNG_KWH * sum(1 for t in am.SPRUNG_ZEITEN if t.date() in tage)


def _einsp(form, tage, weg="HA") -> float:
    v = am.menge(form.einsp, tage) + _sprung_kwh(form, "sensor.einsp", tage, weg)
    return round(v, 6)


def _netz(form, tage, weg="HA") -> float:
    return am.menge(form.netz, tage)


def _pv(form, tage, weg="HA") -> float:
    # N-586 (E4a-2): der Sprung des Anlagenzählers geht nach W2-R2 als Rest an die Geräte ohne Zähler.
    s = mx.soll_monat(form.pvform, tuple(tage)).summe + _sprung_kwh(form, "sensor.pv_gesamt", tage, weg)
    return round(s, 6)


def _feld(form, typ: str, feld: str, tage, *, name: Optional[str] = None) -> float:
    return round(sum(am.menge(g.felder[feld], tage) for g in form.typ(typ)
                     if feld in g.felder and (name is None or g.name == name)), 6)


def _sonst(form, richtung: str, tage) -> float:
    s = 0.0
    for g in form.typ("sonstiges"):
        kat = (g.parameter or {}).get("kategorie")
        if richtung == "erzeugung" and kat == "erzeuger" and form.w2:
            # Weg 2 (W2-E): die Ersatzgruppe nimmt je Zeitraum den ersten Zähler mit Deckung — A deckt jeden Tag (am
            # Lückentag mit seinem Δ, wie HA) — und sein Δ über die Tagesfenster.
            s += am.w2_menge(g.felder["erzeugung_kwh"], g.ohne.get("erzeugung_kwh"), tuple(tage))
        elif richtung == "erzeugung" and kat == "erzeuger":
            s += am.menge(g.felder["erzeugung_kwh"], tage)
        elif richtung == "verbrauch" and kat != "erzeuger":
            # Either-Or: der erste Name mit Daten — der neue (`verbrauch_sonstig_kwh`) vor dem alten.
            f = "verbrauch_sonstig_kwh" if "verbrauch_sonstig_kwh" in g.felder else "verbrauch_kwh"
            s += am.menge(g.felder[f], tage)
    return round(s, 6)


def ev_regel(hz: float, einsp: float, ladung: float, entladung: float) -> float:
    """``berechne_verbrauchs_kennzahlen`` (BERECHNUNGEN §3.1): EV = Direkt + Entladung."""
    direkt = max(0.0, hz - einsp - ladung) if hz > 0 else 0.0
    return max(0.0, direkt + entladung)


#: HA-Bauform E4a-2, Weg 2 (Bauplan §6b, „laufend-Teiltag"): das Monats-Δ der Kanäle reicht bis zum letzten
#: geschriebenen Stand. Um 00:30 (Matrix-Uhr) ist das die Zeile 03.07. 23:00 — die erste Stunde des Tagesfensters
#: 04.07., den die Σ der Tage noch nicht zählt. Gilt für die Monats-Fakten (`fakten_tw`), nicht für Cockpit → Monat
#: (HA-Weg Kalendermonat, ab 1. 00:00 — die zweite Monatsgrenze, E3-Nachtrag 2).
TEILTAG_STUNDEN = (datetime(2026, 7, 3, 23),)


def _stunde(fn, stunden) -> float:
    return sum(fn(t) for t in stunden)


def _pv_stunden(pvform, stunden) -> float:
    """PV einzelner Stunden nach W2: Σ Geräte = max(Anlagenzähler, Σ gemessene Geräte) (R1–R3; die PV-Seiten der
    Achsen-Formen haben keine Modul-Kinder)."""
    reihen = mx._reihen(pvform)
    gesamt = reihen.get("sensor.pv_gesamt")
    gem = [reihen[g.sensor_id][0] for g in pvform.geraete if g.zaehler]
    return sum(max(gesamt[0](t) if gesamt else 0.0, sum(f(t) for f in gem)) for t in stunden)


def bilanz_soll(form, tage, weg="HA", *, extra_stunden=()) -> dict:
    """Die Bilanz mit den Mengen der Regel: hinter dem Zähler = PV + Sonstiges-Erzeuger; Speicher = alle
    Speicher (auch der am Balkonkraftwerk). Ein einzelner Tag mit verworfener Stunde nennt EV und Autarkie
    nicht (Tagesregel R7, ``tagesbilanz.py:160-164``). ``extra_stunden``: Stunden über die Tage hinaus (Teiltag des
    laufenden Monats aus den Kanälen, E4a-2) — ihre Mengen aus denselben Raten."""
    pv_h = _pv_stunden(form.pvform, extra_stunden)
    hz = _pv(form, tage, weg) + pv_h + _sonst(form, "erzeugung", tage) + sum(
        _stunde(g.felder["erzeugung_kwh"], extra_stunden) for g in form.typ("sonstiges")
        if (g.parameter or {}).get("kategorie") == "erzeuger" and "erzeugung_kwh" in g.felder)
    e = _einsp(form, tage, weg) + _stunde(form.einsp, extra_stunden)
    n = _netz(form, tage, weg) + _stunde(form.netz, extra_stunden)
    lad = _feld(form, "speicher", "ladung_kwh", tage) + sum(
        _stunde(g.felder["ladung_kwh"], extra_stunden) for g in form.typ("speicher") if "ladung_kwh" in g.felder)
    entl = _feld(form, "speicher", "entladung_kwh", tage) + sum(
        _stunde(g.felder["entladung_kwh"], extra_stunden) for g in form.typ("speicher") if "entladung_kwh" in g.felder)
    ev = ev_regel(hz, e, lad, entl)
    gv = ev + n
    out = {"pv": round(_pv(form, tage, weg) + pv_h, 6), "einsp": round(e, 6), "netz": round(n, 6), "ev": round(ev, 6),
           "gv": round(gv, 6),
           "autarkie": round(100.0 * ev / gv, 4) if gv else None}
    if len(tage) == 1 and _verworfen(form, tage, weg):
        out["ev"] = out["autarkie"] = None
    return out


def _preis_soll(form, weg: str) -> Any:
    """Kaskade gepflegt → gemessen → Zeitfenster → Stamm (``aufgeloester_monatspreis``). Gemessen gibt es
    nur mit Preissensor in HA; der Bezug fließt nur in 25-ct-Stunden (``am.preis_flex``)."""
    ha = weg in ("HA", "S1", "S2")
    if form.gepflegt_cent is not None and weg in ("S1", "S3"):
        return form.gepflegt_cent
    if form.preis is not None and ha:
        return 25.0
    return am.STAMM_CENT


# ── Katalog: welche Sicht welche Menge führt ────────────────────────────────


@dataclass(frozen=True)
class Menge:
    """Eine Menge einer Größe. ``pfade`` je Sicht (``/`` trennt), ``tag`` je Tageszeile, ``soll(form,
    tage, weg)`` (``UNKLAR`` = die Regel legt es nicht fest). ``geraet``: Menge je Gerät (I4)."""

    name: str
    pfade: dict
    soll: Callable
    tag: Optional[Callable] = None
    geraet: bool = False
    #: Die Form führt diese Menge nur, wenn ``nur(form)`` (ein Zähler sie trägt) — sonst ist sie keine Zelle.
    nur: Optional[Callable] = None
    #: Eine abgeleitete Aufteilung (PV-/Netz-Anteil): „keine Angabe" und 0 sind dieselbe Aussage.
    null_gleich_none: bool = False
    #: Nur I1 (eine Zahl in allen Sichten): das Soll ist eine Layer-Formel, die die Matrix nicht nachbildet.
    nur_i1: bool = False


def _p(d: Any, pfad: str) -> Any:
    for teil in pfad.split("/"):
        if not isinstance(d, dict):
            return None
        d = d.get(teil)
    return d


#: Sichten des abgeschlossenen Monats (nach dem Abschluss) und ihre Wurzel in ``Messung.nach[weg]``.
NACH = ("cockpit_monat", "fakten", "uebersicht", "cockpit_jahr", "tabelle", "zeitreihe", "dashboards",
        "ha_export", "community", "pdf_monat", "pdf_kopf", "preis")
#: Sichten des laufenden Monats / des abgeschlossenen vor dem Abschluss.
LAUFEND = ("cockpit_monat", "cockpit_jahr", "jahr_verlauf", "fakten_tw")
VOR = ("cockpit_monat", "jahr_verlauf", "fakten_tw")


def _wurzeln(m: am.Messung, weg: str, ebene: str) -> dict:
    if ebene == "laufend":
        L = m.laufend[weg]
        return {"cockpit_monat": L["monat"], "cockpit_jahr": L["jahr"], "jahr_verlauf": L["verlauf"],
                "fakten_tw": L["fakten_tw"]}
    if ebene == "vor":
        V = m.vor[weg]
        return {"cockpit_monat": V["monat"], "jahr_verlauf": V["verlauf"], "fakten_tw": V["fakten_tw"]}
    N = m.nach[weg]
    return {"cockpit_monat": N["monat"], "fakten": N["fakten"], "uebersicht": N["uebersicht"],
            "cockpit_jahr": N["jahr"], "tabelle": N["tabelle"], "zeitreihe": N["zeitreihe"],
            "dashboards": N["dashboards"], "ha_export": N["ha_export"], "community": (N["community"] or {}).get("monat"),
            "pdf_monat": (N["pdf"] or {}).get("juni"), "pdf_kopf": (N["pdf"] or {}).get("kopf"), "preis": N["preis"]}


def _alle(pfad: str, *, fakten: Optional[str] = None, ohne: tuple = ()) -> dict:
    """Ein Feldname, der in Cockpit → Monat/Jahr, Jahr-Verlauf, Tabelle, Übersicht und Zeitreihe gleich
    heißt; ``fakten`` = Pfad in den Monats-Fakten (gilt auch für ``fakten_tw``)."""
    out = {s: pfad for s in ("cockpit_monat", "cockpit_jahr", "jahr_verlauf", "tabelle", "uebersicht", "zeitreihe")
           if s not in ohne}
    if fakten:
        out["fakten"] = out["fakten_tw"] = fakten
    return out


def _hat_feld(typ: str, *felder: str, wert: Optional[Callable] = None):
    """Prädikat: ein Gerät dieses Typs hat einen der Zähler (und ``wert(g)`` gilt)."""
    return lambda form: any(any(f in g.felder for f in felder) and (wert is None or wert(g))
                            for g in form.typ(typ))


def _hat_typ(typ: str):
    return lambda form: bool(form.typ(typ))


#: Mengen der Netz-Gruppe → Schlüssel von ``bilanz_soll``.
_BIL_SCHLUESSEL = {"pv": "pv", "einspeisung": "einsp", "netzbezug": "netz", "eigenverbrauch": "ev",
                   "gesamtverbrauch": "gv", "autarkie": "autarkie"}


def _bil(schluessel):
    return lambda form, tage, weg: bilanz_soll(form, tage, weg)[schluessel]


KATALOG: dict[str, list[Menge]] = {
    "netz": [
        Menge("pv", {**_alle("pv_erzeugung_kwh", fakten="erzeugung/pv_kwh", ohne=("zeitreihe",)),
                     "ha_export": "anlage/pv_erzeugung_gesamt_kwh", "community": "ertrag_kwh",
                     "pdf_monat": "pv_erzeugung_kwh"},
              _bil("pv"), tag=lambda d: None if _p(d, "tw/erzeugung") is None
              else round((_p(d, "tw/pv_anlage") or 0.0) + (_p(d, "tw/bkw") or 0.0), 4)),
        Menge("einspeisung", {**_alle("einspeisung_kwh", fakten="zaehler/einspeisung_kwh", ohne=("zeitreihe",)),
                              "ha_export": "anlage/einspeisung_gesamt_kwh", "community": "einspeisung_kwh",
                              "pdf_monat": "einspeisung_kwh"},
              _bil("einsp"), tag=lambda d: _p(d, "tw/einspeisung")),
        Menge("netzbezug", {**_alle("netzbezug_kwh", fakten="zaehler/netzbezug_kwh", ohne=("zeitreihe",)),
                            "ha_export": "anlage/netzbezug_gesamt_kwh", "community": "netzbezug_kwh",
                            "pdf_monat": "netzbezug_kwh"},
              _bil("netz"), tag=lambda d: _p(d, "tw/netzbezug")),
        Menge("eigenverbrauch", {**_alle("eigenverbrauch_kwh", fakten="kennzahlen/eigenverbrauch_kwh",
                                         ohne=("zeitreihe",)),
                                 "ha_export": "anlage/eigenverbrauch_gesamt_kwh", "community": "eigenverbrauch_kwh",
                                 "pdf_monat": "eigenverbrauch_kwh"},
              _bil("ev"), tag=lambda d: _p(d, "tw/eigenverbrauch")),
        Menge("gesamtverbrauch", {**_alle("gesamtverbrauch_kwh", fakten="kennzahlen/gesamtverbrauch_kwh",
                                          ohne=("zeitreihe",)),
                                  "ha_export": "anlage/gesamtverbrauch_kwh", "pdf_kopf": "kpis.gesamtverbrauch_kwh"},
              _bil("gv"), tag=lambda d: _p(d, "tw/gesamtverbrauch")),
        Menge("autarkie", {**_alle("autarkie_prozent", fakten="kennzahlen/autarkie_prozent", ohne=("zeitreihe",)),
                           "ha_export": "anlage/autarkie_prozent", "community": "autarkie_prozent",
                           "pdf_monat": "autarkie_prozent"},
              _bil("autarkie"), tag=lambda d: _p(d, "tw/autarkie")),
    ],
    "speicher": [
        Menge("ladung", {**_alle("speicher_ladung_kwh", fakten="speicher/ladung_kwh"),
                         "community": "speicher_ladung_kwh", "pdf_kopf": "speicher.ladung_kwh"},
              lambda f, t, w: _feld(f, "speicher", "ladung_kwh", t), tag=lambda d: _p(d, "tw/speicher_ladung")),
        Menge("entladung", {**_alle("speicher_entladung_kwh", fakten="speicher/entladung_kwh"),
                            "community": "speicher_entladung_kwh", "pdf_kopf": "speicher.entladung_kwh"},
              lambda f, t, w: _feld(f, "speicher", "entladung_kwh", t), tag=lambda d: _p(d, "tw/speicher_entladung")),
        Menge("netzladung", {"cockpit_monat": "speicher_ladung_netz_kwh", "cockpit_jahr": "speicher_ladung_netz_kwh",
                             "jahr_verlauf": "speicher_netzladung_kwh", "tabelle": "speicher_netzladung_kwh",
                             "fakten": "speicher/netzladung_kwh", "fakten_tw": "speicher/netzladung_kwh",
                             "zeitreihe": "speicher_arbitrage_kwh", "community": "speicher_ladung_netz_kwh"},
              lambda f, t, w: _feld(f, "speicher", "ladung_netz_kwh", t), nur=_hat_feld("speicher", "ladung_netz_kwh")),
        Menge("ladung", {"dashboards": "speicher/{g}/juni/ladung_kwh",
                         "dashboard_summe": "speicher/{g}/zusammenfassung/gesamt_ladung_kwh"},
              lambda f, t, w, g=None: _feld(f, "speicher", "ladung_kwh", t, name=g), geraet=True),
        Menge("entladung", {"dashboards": "speicher/{g}/juni/entladung_kwh",
                            "dashboard_summe": "speicher/{g}/zusammenfassung/gesamt_entladung_kwh"},
              lambda f, t, w, g=None: _feld(f, "speicher", "entladung_kwh", t, name=g), geraet=True),
    ],
    "wp": [
        Menge("strom", {**_alle("wp_strom_kwh", fakten="wp/strom_kwh"), "community": "wp_stromverbrauch_kwh",
                        "pdf_kopf": "waermepumpe.strom_kwh"},
              lambda f, t, w: _wp_soll(f, "strom", t), tag=lambda d: _p(d, "tw/wp_strom")),
        Menge("waerme", {**_alle("wp_waerme_kwh", fakten="wp/waerme_kwh", ohne=("tabelle", "jahr_verlauf")),
                         "pdf_kopf": "waermepumpe.waerme_kwh"},
              lambda f, t, w: _wp_soll(f, "waerme", t)),
        Menge("heizung", {**_alle("wp_heizung_kwh", fakten="wp/heizung_kwh"), "community": "wp_heizwaerme_kwh",
                          "pdf_kopf": "waermepumpe.heizung_kwh"},
              lambda f, t, w: _wp_soll(f, "heizung", t),
              nur=_hat_feld("waermepumpe", "heizenergie_kwh", "waerme_kwh", "betriebsart_nutzenergie_heizen_kwh")),
        Menge("warmwasser", {**_alle("wp_warmwasser_kwh", fakten="wp/warmwasser_kwh"),
                             "community": "wp_warmwasser_kwh", "pdf_kopf": "waermepumpe.warmwasser_kwh"},
              lambda f, t, w: _wp_soll(f, "warmwasser", t), nur=_hat_feld("waermepumpe", "warmwasser_kwh", "waerme_kwh")),
        Menge("strom_heizen", _alle("wp_strom_heizen_kwh", fakten="wp/strom_heizen_kwh"),
              lambda f, t, w: _wp_soll(f, "strom_heizen", t), nur=_hat_feld("waermepumpe", "strom_heizen_kwh")),
        Menge("strom_warmwasser", _alle("wp_strom_warmwasser_kwh", fakten="wp/strom_warmwasser_kwh"),
              lambda f, t, w: _wp_soll(f, "strom_warmwasser", t), nur=_hat_feld("waermepumpe", "strom_warmwasser_kwh")),
        Menge("modus_heizen", _alle("wp_modus_strom_heizen_kwh", fakten="wp/modus_strom_heizen_kwh",
                                    ohne=("tabelle", "jahr_verlauf")),
              lambda f, t, w: _wp_soll(f, "modus_heizen", t),
              nur=lambda f: _hat_feld("waermepumpe", "betriebsart_strom_heizen_kwh")(f) or any(g.live for g in f.typ("waermepumpe"))),
        Menge("modus_kuehlen", {**_alle("wp_modus_strom_kuehlen_kwh", fakten="wp/modus_strom_kuehlen_kwh",
                                        ohne=("tabelle", "jahr_verlauf")), "community": "wp_strom_kuehlen_kwh"},
              lambda f, t, w: _wp_soll(f, "modus_kuehlen", t), nur=_hat_feld("waermepumpe", "betriebsart_strom_kuehlen_kwh")),
        Menge("modus_warmwasser", _alle("wp_modus_strom_warmwasser_kwh", fakten="wp/modus_strom_warmwasser_kwh",
                                        ohne=("tabelle", "jahr_verlauf")),
              lambda f, t, w: _wp_soll(f, "modus_warmwasser", t), nur=lambda f: any(g.live for g in f.typ("waermepumpe"))),
        Menge("kaelte", {"cockpit_monat": "wp_kaelte_kwh", "cockpit_jahr": "wp_kaelte_kwh",
                         "uebersicht": "wp_kaelte_kwh"},
              lambda f, t, w: _wp_soll(f, "kaelte", t), nur=_hat_feld("waermepumpe", "betriebsart_nutzenergie_kuehlen_kwh")),
        Menge("strom", {"cockpit_monat": "wp_geraete/{g}/strom_kwh", "fakten": "wp_je_geraet/{g}/strom_kwh",
                        "dashboards": "waermepumpe/{g}/zusammenfassung/gesamt_stromverbrauch_kwh"},
              lambda f, t, w, g=None: _wp_soll(f, "strom", t, name=g), geraet=True,
              tag=lambda d, g=None: _p(d, f"keys/waermepumpe:{g}")),
        Menge("waerme", {"cockpit_monat": "wp_geraete/{g}/waerme_kwh", "fakten": "wp_je_geraet/{g}/waerme_kwh",
                         "dashboards": "waermepumpe/{g}/zusammenfassung/gesamt_waerme_kwh"},
              lambda f, t, w, g=None: _wp_soll(f, "waerme", t, name=g), geraet=True),
    ],
    "emob": [
        # E4c: `fakten_tw` fehlte — die Sicht „vor dem Abschluss" (`fakten:tageswert=gespeichert`) las immer None.
        Menge("wallbox", {"tabelle": "wallbox_ladung_kwh", "jahr_verlauf": "wallbox_ladung_kwh",
                          "fakten": "emob_wallbox_summe/ladung_kwh", "fakten_tw": "emob_wallbox_summe/ladung_kwh",
                          "community": "wallbox_ladung_kwh"},
              lambda f, t, w: _feld(f, "wallbox", "ladung_kwh", t), nur=_hat_typ("wallbox"),
              tag=lambda d: sum(v for k, v in (d.get("keys") or {}).items() if k.startswith("wallbox:") and v)
              or None),
        Menge("heimladung", {**_alle("emob_ladung_kwh", fakten="emob/ladung_kwh", ohne=("tabelle", "jahr_verlauf")),
                             "pdf_kopf": "emob.ladung_kwh"},
              lambda f, t, w: _emob_soll(f, "ladung", t)),
        Menge("heim_pv", {"cockpit_monat": "emob_ladung_pv_kwh", "cockpit_jahr": "emob_ladung_pv_kwh",
                          "zeitreihe": "emob_ladung_pv_kwh", "fakten": "emob/ladung_pv_kwh",
                          "fakten_tw": "emob/ladung_pv_kwh", "pdf_kopf": "emob.ladung_pv_kwh"},
              lambda f, t, w: _emob_soll(f, "pv", t), null_gleich_none=True),
        Menge("heim_netz", {"cockpit_monat": "emob_ladung_netz_kwh", "cockpit_jahr": "emob_ladung_netz_kwh",
                            "zeitreihe": "emob_ladung_netz_kwh", "fakten": "emob/ladung_netz_kwh",
                            "fakten_tw": "emob/ladung_netz_kwh", "pdf_kopf": "emob.ladung_netz_kwh"},
              lambda f, t, w: _emob_soll(f, "netz", t), null_gleich_none=True),
        Menge("ladung", {"dashboards": "e-auto/{g}/zusammenfassung/gesamt_ladung_kwh",
                         "dashboard_summe": "e-auto/{g}/juni/ladung_kwh"},
              lambda f, t, w, g=None: _emob_soll(f, "ladung", t, name=g), geraet=True, nur=_hat_typ("e-auto")),
        Menge("ladung_pv", {"dashboards": "e-auto/{g}/zusammenfassung/ladung_pv_kwh",
                            "fakten": "emob_je_auto/{g}/pv_kwh"},
              lambda f, t, w, g=None: _emob_soll(f, "pv", t, name=g), geraet=True, nur=_hat_typ("e-auto")),
    ] + [
        Menge("dienst_pv", {"fakten": "emob/dienstlich_ladung_pv_kwh", "fakten_tw": "emob/dienstlich_ladung_pv_kwh"},
              lambda f, t, w: _dienst_soll(f, "pv", t),
              nur=lambda f: any((g.parameter or {}).get("ist_dienstlich") for g in f.typ("e-auto"))),
        Menge("dienst_netz", {"fakten": "emob/dienstlich_ladung_netz_kwh", "fakten_tw": "emob/dienstlich_ladung_netz_kwh"},
              lambda f, t, w: _dienst_soll(f, "netz", t),
              nur=lambda f: any((g.parameter or {}).get("ist_dienstlich") for g in f.typ("e-auto"))),
    ],
    "sonstiges": [
        Menge("erzeugung", {**_alle("sonstiges_erzeugung_kwh", fakten="sonstiges/erzeugung_kwh",
                                    ohne=("tabelle", "jahr_verlauf")),
                            "tabelle": "sonstige_erzeugung_kwh", "jahr_verlauf": "sonstige_erzeugung_kwh"},
              lambda f, t, w: _sonst(f, "erzeugung", t), tag=lambda d: _p(d, "tw/sonstiges_erzeugung"),
              nur=_hat_feld("sonstiges", "erzeugung_kwh")),
        Menge("verbrauch", {**_alle("sonstiges_verbrauch_kwh", fakten="sonstiges/verbrauch_kwh",
                                    ohne=("tabelle", "jahr_verlauf")),
                            "tabelle": "sonstige_verbrauch_kwh", "jahr_verlauf": "sonstige_verbrauch_kwh",
                            "community": "sonstiges_verbrauch_kwh"},
              lambda f, t, w: _sonst(f, "verbrauch", t), tag=lambda d: _p(d, "tw/sonstiges_verbrauch"),
              # E4c (W2-E-KATALOG): ein Verbrauchsfeld eines ERZEUGERS ist der Ersatz seiner Erzeugung
              # (`sonstiges_feld_reihenfolge("erzeuger")`, `_categorize_counter` → erzeugung_sonstiges), kein Verbrauch.
              nur=_hat_feld("sonstiges", "verbrauch_sonstig_kwh", "verbrauch_kwh",
                            wert=lambda g: (g.parameter or {}).get("kategorie") != "erzeuger")),
        Menge("hinter_zaehler", {"fakten": "erzeugung/hinter_zaehler_kwh", "fakten_tw": "erzeugung/hinter_zaehler_kwh",
                                 "tabelle": "erzeugung_hinter_zaehler_kwh",
                                 "jahr_verlauf": "erzeugung_hinter_zaehler_kwh"},
              lambda f, t, w: round(_pv(f, t, w) + _sonst(f, "erzeugung", t), 6), nur=_hat_feld("sonstiges", "erzeugung_kwh")),
        Menge("geraet", {"cockpit_monat": "sonstiges_geraete/{g}/{richtung}_kwh",
                         "fakten": "sonstiges_je_geraet/{g}/{richtung}_kwh"},
              lambda f, t, w, g=None: _sonst_geraet(f, g, t), geraet=True,
              tag=lambda d, g=None: _p(d, f"keys/sonstige:{g}")),
    ],
    "preis": [
        Menge("preis_effektiv", {"cockpit_monat": "netzbezug_preis_effektiv_cent",
                                 "cockpit_jahr": "netzbezug_preis_effektiv_cent",
                                 "jahr_verlauf": "netzbezug_preis_cent", "tabelle": "netzbezug_preis_cent",
                                 "fakten": "tarif/netzbezug_preis_cent", "fakten_tw": "tarif/netzbezug_preis_cent",
                                 "preis": "lookup/allgemein/6"},
              lambda f, t, w: _preis_soll(f, w), tag=None),
        Menge("netto_ertrag", {**_alle("netto_ertrag_euro", ohne=("zeitreihe",)), "ha_export": "anlage/netto_ertrag_euro",
                               "pdf_monat": "netto_ertrag_euro", "pdf_kopf": "kpis.netto_ertrag_euro"},
              lambda f, t, w: UNKLAR, nur_i1=True),
        Menge("kosten", {**_alle("netzbezug_kosten_euro"), },
              lambda f, t, w: round(_netz(f, t, w) * _preis_soll(f, w) / 100.0, 6),
              tag=lambda d: _p(d, "tw/netzbezug_kosten")),
    ],
}


def _wp_soll(form, menge: str, tage, *, name: Optional[str] = None, stunden=None) -> Any:
    """Wärmepumpe nach K1–K5 (``docs/KONZEPT-WAERME-KLIMA.md`` §3). Was die Kanon-Regeln NICHT festlegen
    (Aufteilung nach dem Etikett bei Gesamtstrom; Wärme-Aufteilung ohne getrennte Wärmezähler), ist
    ``UNKLAR`` — Fachfrage des Masters. ``stunden`` (HA-Bauform E4d): dieselben Mengen über einzelne Stunden statt
    über Tage — der Teiltag des laufenden Monats der Monats-Fakten (``TEILTAG_STUNDEN``)."""
    out = 0.0
    for g in form.typ("waermepumpe"):
        if name is not None and g.name != name:
            continue
        f = g.felder
        hat = lambda k: k in f  # noqa: E731
        if stunden is not None:
            m = lambda k: _stunde(f[k], stunden) if k in f else 0.0  # noqa: E731
        else:
            m = lambda k: am.menge(f[k], tage) if k in f else 0.0  # noqa: E731
        ba_strom = sum(m(k) for k in f if k.startswith("betriebsart_strom_"))
        if menge == "strom":       # K1 Gesamtzähler · K3 Regel 3 Summanden · Regel 4 Betriebsart-Zähler
            v = m("stromverbrauch_kwh") if hat("stromverbrauch_kwh") else (
                m("strom_heizen_kwh") + m("strom_warmwasser_kwh") if hat("strom_heizen_kwh") else ba_strom)
        elif menge == "waerme":    # K1 auf der Wärmeseite: Gesamtwert, sonst Σ des Gemessenen (Heizwärme)
            v = m("waerme_kwh") if hat("waerme_kwh") else (
                m("heizenergie_kwh") + m("warmwasser_kwh") + m("betriebsart_nutzenergie_heizen_kwh"))
        elif menge == "heizung":
            if hat("waerme_kwh") and not hat("heizenergie_kwh"):
                return UNKLAR      # Gesamtwärme ohne Heiz-/WW-Zähler: die Aufteilung gibt K1–K5 nicht her
            v = m("heizenergie_kwh") + m("betriebsart_nutzenergie_heizen_kwh")
        elif menge == "warmwasser":
            if hat("waerme_kwh") and not hat("warmwasser_kwh"):
                return UNKLAR
            v = m("warmwasser_kwh")
        elif menge == "strom_heizen":
            v = m("strom_heizen_kwh")
        elif menge == "strom_warmwasser":
            v = m("strom_warmwasser_kwh")
        elif menge in ("modus_heizen", "modus_kuehlen", "modus_warmwasser"):
            if g.live:
                return UNKLAR      # Aufteilung nach dem Etikett: K1–K5 legen sie nicht fest (W1)
            v = m({"modus_heizen": "betriebsart_strom_heizen_kwh",
                   "modus_kuehlen": "betriebsart_strom_kuehlen_kwh"}.get(menge, "-"))
        elif menge == "kaelte":
            v = m("betriebsart_nutzenergie_kuehlen_kwh")
        else:
            raise KeyError(menge)
        out += v
    return round(out, 6)


def _emob_soll(form, menge: str, tage, *, name: Optional[str] = None) -> float:
    """Heimladung (BERECHNUNGEN Regel 2/3): Σ der privaten Autos; ohne Fahrzeug ist die Wallbox das private
    Auto. Die Ladestunden der Wallbox-Formen liegen in Sonnenstunden ohne Netzbezug ⇒ PV-Anteil 100 %."""
    autos = [g for g in form.typ("e-auto") if not (g.parameter or {}).get("ist_dienstlich")]
    if name is not None:
        autos = [g for g in form.typ("e-auto") if g.name == name]
    wb = _feld(form, "wallbox", "ladung_kwh", tage)
    if not form.typ("e-auto"):
        return {"ladung": wb, "pv": wb, "netz": 0.0}[menge]
    s = {"ladung": 0.0, "pv": 0.0, "netz": 0.0}
    for g in autos:
        f = g.felder
        if "ladung_pv_kwh" in f or "ladung_netz_kwh" in f:
            pv = am.menge(f.get("ladung_pv_kwh", am.null), tage)
            nz = am.menge(f.get("ladung_netz_kwh", am.null), tage)
        else:
            gesamt = am.menge(f["ladung_kwh"], tage)
            pv, nz = gesamt, 0.0           # an der Wallbox in Sonnenstunden ohne Bezug geladen
        s["ladung"] += pv + nz
        s["pv"] += pv
        s["netz"] += nz
    return round(s[menge], 6)


def _dienst_soll(form, menge: str, tage) -> float:
    """Dienstliche Ladung (BERECHNUNGEN „Der Dienstwagen"): mit eigener Messung ist sie seine Ladung."""
    s = 0.0
    for g in form.typ("e-auto"):
        if (g.parameter or {}).get("ist_dienstlich"):
            s += am.menge(g.felder.get(f"ladung_{menge}_kwh", am.null), tage)
    return round(s, 6)


def _sonst_teiltag(form, menge: str, stunden) -> float:
    """E4c: die Mengen der Sonstiges-Gruppe in den Teiltag-Stunden (``TEILTAG_STUNDEN``) aus denselben Raten — der
    laufende Monat der Monats-Fakten reicht bis zum letzten geschriebenen Stand (wie die Bilanz-Gruppe, E4a-2)."""
    erz = sum(_stunde(g.felder["erzeugung_kwh"], stunden) for g in form.typ("sonstiges")
              if (g.parameter or {}).get("kategorie") == "erzeuger" and "erzeugung_kwh" in g.felder)
    if menge == "erzeugung":
        return erz
    if menge == "hinter_zaehler":
        return erz + _pv_stunden(form.pvform, stunden)
    if menge == "verbrauch":
        out = 0.0
        for g in form.typ("sonstiges"):
            if (g.parameter or {}).get("kategorie") == "erzeuger":
                continue
            f = "verbrauch_sonstig_kwh" if "verbrauch_sonstig_kwh" in g.felder else "verbrauch_kwh"
            out += _stunde(g.felder[f], stunden) if f in g.felder else 0.0
        return out
    return 0.0


def _sonst_geraet(form, name, tage) -> float:
    g = form.geraet(name)
    kat = (g.parameter or {}).get("kategorie")
    if kat == "erzeuger":
        return am.menge(g.felder["erzeugung_kwh"], tage)
    f = "verbrauch_sonstig_kwh" if "verbrauch_sonstig_kwh" in g.felder else "verbrauch_kwh"
    return am.menge(g.felder[f], tage)


# ── Bewertung ───────────────────────────────────────────────────────────────


@dataclass
class Zelle:
    sicht: str
    ist: Any
    soll: Any
    status: str  # "ok" | "rot"
    notiz: str = ""


def _tol(soll) -> float:
    return max(0.05, 0.001 * abs(soll or 0.0))


_TOL_TAGE = 0.6


def _gleich(ist, soll, tol=None) -> bool:
    if isinstance(soll, str) or isinstance(ist, str):
        return ist == soll
    if ist is None or soll is None:
        return ist is None and soll is None
    return abs(float(ist) - float(soll)) <= (tol if tol is not None else _tol(soll))


def _z(sicht, ist, soll, *, tol=None, notiz="") -> Zelle:
    return Zelle(sicht, ist, soll, "ok" if _gleich(ist, soll, tol) else "rot", notiz)


def _geraete(form, groesse: str) -> list:
    typ = {"speicher": "speicher", "wp": "waermepumpe", "emob": "e-auto", "sonstiges": "sonstiges"}[groesse]
    return form.typ(typ)


def _pfad_fuer(menge: Menge, sicht: str, g=None) -> Optional[str]:
    p = menge.pfade.get(sicht)
    if p is None:
        return None
    if g is not None:
        richtung = "erzeugung" if (g.parameter or {}).get("kategorie") == "erzeuger" else "verbrauch"
        p = p.replace("{g}", g.name).replace("{richtung}", richtung)
    return p


def _wert(wurzeln: dict, menge: Menge, sicht: str, g=None) -> Any:
    p = _pfad_fuer(menge, sicht, g)
    if p is None:
        return None
    wurzel = wurzeln.get("dashboards" if sicht == "dashboard_summe" else sicht)
    v = _p(wurzel, p)
    if menge.null_gleich_none and v is None:
        return 0.0
    return v


def _fuehrt(wurzeln: dict, sicht: str) -> bool:
    """Eine Sicht ohne jede Zeile (Komponenten-Zeitreihe einer Anlage ohne Komponenten) führt nichts."""
    w = wurzeln.get("dashboards" if sicht == "dashboard_summe" else sicht)
    return isinstance(w, dict) and bool(w)


def _sichten(menge: Menge, ebene: str, wurzeln: Optional[dict] = None) -> list[str]:
    erlaubt = {"laufend": LAUFEND, "vor": VOR, "nach": NACH + ("dashboard_summe",)}[ebene]
    return [s for s in menge.pfade if s in erlaubt and (wurzeln is None or _fuehrt(wurzeln, s))]


def _mengen(groesse: str, *, geraet: bool, form: Optional[am.Form] = None) -> list[Menge]:
    return [q for q in KATALOG[groesse] if q.geraet == geraet and (form is None or q.nur is None or q.nur(form))]


def _ist_null_soll(soll) -> bool:
    return soll is not UNKLAR and soll is not None and abs(float(soll)) < 1e-9


def _soll_fuer(form, menge: Menge, tage, weg, g=None):
    s = menge.soll(form, tage, weg, g.name) if g is not None else menge.soll(form, tage, weg)
    return s


def _folge_netz(sicht: str, d: dict) -> list[Zelle]:
    """I5 Netz mit den Mengen DERSELBEN Sicht: EV = Regel(hinter dem Zähler, Einspeisung, Ladung, Entladung),
    Gesamtverbrauch = EV + Netzbezug, Autarkie = EV / Gesamtverbrauch. ``d`` trägt, was die Sicht führt
    (fehlende Erzeuger-/Speichermengen zählen 0 — die Sicht führt sie dann nicht)."""
    e, n, ev = d.get("einsp"), d.get("netz"), d.get("ev")
    if e is None or n is None or d.get("hz") is None:
        return []
    ev_soll = ev_regel(d["hz"], e, d.get("lad") or 0.0, d.get("entl") or 0.0)
    out = [_z(f"{sicht}:ev", ev, ev_soll)]
    basis = ev if ev is not None else ev_soll
    if "gv" in d:
        out.append(_z(f"{sicht}:gv", d.get("gv"), basis + n))
    if "autarkie" in d:
        out.append(_z(f"{sicht}:autarkie", d.get("autarkie"), 100.0 * basis / (basis + n) if (basis + n) else None,
                      tol=0.15))
    return out


def _sigma_zelle(sicht: str, monat, werte: list) -> Zelle:
    """Monat gegen Σ der Tage. Nennt ein Tag die Größe nicht (abgeleitete Größe, Tagesregel R7 bei einer
    verworfenen Stunde), ist die Σ unvollständig — dann wird gezeigt, nicht bewertet."""
    if all(v is None for v in werte):
        return _z(sicht, monat, None, tol=_TOL_TAGE)
    sigma = round(sum(v or 0.0 for v in werte), 4)
    if any(v is None for v in werte):
        return Zelle(sicht, monat, sigma, "unklar", f"Σ unvollständig: {sum(v is None for v in werte)} Tage ohne Wert")
    return _z(sicht, monat, sigma, tol=_TOL_TAGE)


def bewerte(fid: str, groesse: str, weg: str, inv: str, m: am.Messung) -> list[Zelle]:  # noqa: C901
    if groesse in HUB_GROESSEN:
        return _bewerte_hub(fid, groesse, weg, inv, m) or [Zelle("nicht_pruefbar", None, None, "nicht_pruefbar",
                                                                 NICHT_PRUEFBAR_GRUND.get((groesse, inv), "—"))]
    form = am.MATRIX_FORMEN[fid]
    z: list[Zelle] = []
    juni, juli = am.TAGE_JUNI, am.TAGE_JULI
    datenstand = weg in ("HA", "SA")
    tage_monat = juli if datenstand else juni
    w_tage = m.tage[_teil(weg)]

    if datenstand:
        wurzeln = _wurzeln(m, weg, "laufend")
        ebene = "laufend"
        ref_sicht = "cockpit_monat"
    else:
        wurzeln = _wurzeln(m, weg, "nach")
        ebene = "nach"
        ref_sicht = "fakten"

    mengen = _mengen(groesse, geraet=False, form=form)

    def ref_von(q):
        return ref_sicht if ref_sicht in q.pfade else "cockpit_monat"

    if inv == "I1":
        for q in mengen:
            sichten = _sichten(q, ebene, wurzeln)
            r = ref_von(q)
            if r not in sichten:
                continue
            ref = _wert(wurzeln, q, r)
            for s in sichten:
                if s != r:
                    z.append(_z(f"{q.name}:{s}", _wert(wurzeln, q, s), ref, notiz=f"Referenz {r}"))
    elif inv == "I2":
        for q in mengen:
            if q.nur_i1:
                continue
            if datenstand:
                if q.tag is not None and q.name != "autarkie":     # eine Quote summiert sich nicht
                    werte = [q.tag(w_tage[t.isoformat()]) for t in juli]
                    for s in ("cockpit_monat", "jahr_verlauf", "fakten_tw"):
                        if s in q.pfade:
                            z.append(_sigma_zelle(f"{q.name}:{s}=Σtage", _wert(wurzeln, q, s), werte))
            else:
                vor = _wurzeln(m, weg, "vor")
                # Der Preis vor dem Abschluss kennt keinen gepflegten Monats-Ø (er entsteht erst im Abschluss):
                # sein Soll vor dem Abschluss ist die Kaskade ohne Stufe 1.
                preis_vor = groesse == "preis" and form.gepflegt_cent is not None and weg in ("S1", "S3")
                for s, nach_s in (("cockpit_monat", "cockpit_monat"), ("jahr_verlauf", "tabelle")):
                    if s in q.pfade and nach_s in q.pfade:
                        soll = _wert(wurzeln, q, nach_s)
                        notiz = ""
                        if preis_vor:
                            soll = _soll_vor_abschluss(form, q, weg)
                            notiz = "Soll: Kaskade ohne gepflegten Ø"
                        z.append(_z(f"{q.name}:{s}:vor=nach", _wert(vor, q, s), soll, tol=_TOL_TAGE, notiz=notiz))
                if "fakten" in q.pfade:
                    soll = _soll_vor_abschluss(form, q, weg) if preis_vor else _wert(wurzeln, q, "fakten")
                    z.append(_z(f"{q.name}:fakten:tageswert=gespeichert", _wert(vor, q, "fakten_tw"), soll,
                                tol=_TOL_TAGE))
                if q.tag is not None and q.name != "autarkie":
                    werte = [q.tag(w_tage[t.isoformat()]) for t in juni]
                    monat = _soll_vor_abschluss(form, q, weg) if preis_vor else _wert(wurzeln, q, ref_von(q))
                    z.append(_sigma_zelle(f"{q.name}:Σtage_juni={ref_von(q)}", monat, werte))
        if groesse == "emob" and datenstand:
            # Heimladung des laufenden Monats = Σ der Tage: Wallbox-Keys, ohne Wallbox die privaten Autos.
            priv = [g.name for g in form.typ("e-auto") if not (g.parameter or {}).get("ist_dienstlich")]
            werte = []
            for t in juli:
                k = w_tage[t.isoformat()]["keys"]
                if form.typ("wallbox"):
                    werte.append(sum(v for kk, v in k.items() if kk.startswith("wallbox:") and v is not None))
                else:
                    werte.append(sum(k.get(f"eauto:{n}") or 0.0 for n in priv))
            kat = {q.name: q for q in KATALOG["emob"]}
            z.append(_sigma_zelle("heimladung:cockpit_monat=Σtage", _wert(wurzeln, kat["heimladung"], "cockpit_monat"),
                                  werte))
    elif inv == "I3":
        for q in mengen:
            if q.nur_i1:
                continue
            soll = _soll_fuer(form, q, tage_monat, weg)
            sichten = ["cockpit_monat", "fakten_tw"] if datenstand else ["cockpit_monat", "fakten"]
            for s in sichten:
                if s not in q.pfade:
                    continue
                soll_s = soll
                if groesse == "netz" and weg == "HA" and s == "fakten_tw" and q.name in _BIL_SCHLUESSEL:
                    # E4a-2 (Weg 2, §6b): die Monats-Fakten des laufenden Monats aus den Kanälen tragen den Teiltag.
                    soll_s = bilanz_soll(form, tage_monat, weg, extra_stunden=TEILTAG_STUNDEN)[_BIL_SCHLUESSEL[q.name]]
                elif groesse == "sonstiges" and weg == "HA" and s == "fakten_tw" and soll is not UNKLAR:
                    # E4c: die Sonstiges-Gruppe des laufenden Monats aus den Kanälen trägt denselben Teiltag.
                    soll_s = round(soll + _sonst_teiltag(form, q.name, TEILTAG_STUNDEN), 6)
                elif groesse == "wp" and weg == "HA" and s == "fakten_tw" and soll is not UNKLAR:
                    # E4d: die WP-Gruppe des laufenden Monats aus den Kanälen trägt denselben Teiltag.
                    soll_s = round(soll + _wp_soll(form, q.name, (), stunden=TEILTAG_STUNDEN), 6)
                z.append(Zelle(f"{q.name}:{s}", _wert(wurzeln, q, s), "unklar", "unklar")
                         if soll is UNKLAR else _z(f"{q.name}:{s}", _wert(wurzeln, q, s), soll_s))
            if datenstand and q.tag is not None and soll is not UNKLAR:
                abw = []
                for t in juni + juli:
                    s_tag = _soll_fuer(form, q, (t,), weg)
                    ist = q.tag(w_tage[t.isoformat()])
                    if not _gleich(ist, s_tag):
                        abw.append((t.isoformat(), ist, s_tag))
                z.append(_tage_zelle(f"{q.name}:tag", abw))
        if groesse == "preis" and not datenstand and form.preis is not None and weg in ("S1", "S2"):
            agg = _p(wurzeln["preis"], "6")
            z.append(_z("preis_aggregat:gewichtet", _p(agg, "gewichtet_cent"), 25.0))
            z.append(_z("preis_aggregat:arithmetisch", _p(agg, "arithmetisch_cent"), round(700 / 24, 2)))
    elif inv == "I4":
        z += _bewerte_geraete(form, groesse, weg, m, wurzeln, datenstand)
    elif inv == "I5":
        z += _bewerte_folge(form, groesse, weg, m, wurzeln, datenstand)
    elif inv == "I6":
        for q in mengen:
            if q.nur_i1:
                continue
            werte = {s: _wert(wurzeln, q, s) for s in _sichten(q, ebene, wurzeln)}
            if q.tag is not None and datenstand:
                werte["tag"] = q.tag(w_tage[juli[0].isoformat()])
            if any(isinstance(v, (int, float)) and not isinstance(v, bool) and v for v in werte.values()):
                for s, v in werte.items():
                    z.append(Zelle(f"{q.name}:{s}", v, "> 0", "ok" if v else "rot"))
    if not z:
        z.append(Zelle("nicht_pruefbar", None, None, "nicht_pruefbar", NICHT_PRUEFBAR_GRUND.get(
            (groesse, inv), "keine Menge dieser Größe führt in dieser Zelle einen Wert")))
    return z


def _tage_zelle(sicht: str, abw: list) -> Zelle:
    if not abw:
        return Zelle(sicht, "alle Tage", "Soll", "ok", "33 Tage")
    t, ist, soll = abw[0]
    return Zelle(sicht, ist, soll, "rot", f"{len(abw)} von 33 Tagen, erster {t}")


def _soll_vor_abschluss(form, q: Menge, weg: str):
    """Preis-Soll vor dem Abschluss: die Kaskade ohne den gepflegten Ø (HA: gemessen, ohne HA: Stamm)."""
    preis = 25.0 if (form.preis is not None and weg in ("S1", "S2")) else am.STAMM_CENT
    if q.name == "preis_effektiv":
        return preis
    if q.name == "kosten":
        return round(_netz(form, am.TAGE_JUNI, weg) * preis / 100.0, 2)
    return None


#: Warum eine Zelle nichts zu prüfen hat (Lieferung Punkt 3: „nicht prüfbar" mit Grund).
NICHT_PRUEFBAR_GRUND: dict[tuple[str, str], str] = {
    ("emob", "I5"): "ohne HA nennt der laufende Monat keine Lademenge (ohne Abschluss nicht geführt) — keine "
                    "Folgekennzahl, die man an ihr messen könnte",
    ("wp", "I6"): "alle Mengen der Form sind 0 (Monat ohne Betrieb) — „nichts verschwindet“ hat keinen Wert",
    ("emob", "I6"): "ohne HA führt keine Sicht des laufenden Monats die Lademenge (ohne Abschluss nicht geführt), "
                    "die Tagesebene trägt sie je Auto (`eauto_<id>`, I4)",
    ("sonstiges", "I5"): "im laufenden Monat führt keine Sicht Sonstiges (ohne Abschluss nicht geführt) — die "
                         "Folgekennzahl (Erzeugung hinter dem Zähler) gibt es dort nicht",
    ("hub_sonstiges", "I5"): "der Hub eines Sonstiges-Erzeugers nennt keine Folgekennzahl aus einer gemessenen Menge "
                             "(Eigenverbrauch/Einspeisung je Gerät nicht gemessen, „je Gerät nicht gemessen“ im Kopf)",
}


def _bewerte_geraete(form, groesse, weg, m, wurzeln, datenstand) -> list[Zelle]:  # noqa: C901
    """I4: je Gerät der Messwert, Σ Geräte = Summe der Sicht."""
    z: list[Zelle] = []
    juni, juli = am.TAGE_JUNI, am.TAGE_JULI
    tage_monat = juli if datenstand else juni
    w_tage = m.tage[_teil(weg)]
    geraete = _geraete(form, groesse)
    for q in _mengen(groesse, geraet=True, form=form):
        for g in geraete:
            soll = _soll_fuer(form, q, tage_monat, weg, g)
            dienst = groesse == "emob" and (g.parameter or {}).get("ist_dienstlich")
            for s in _sichten(q, "laufend" if datenstand else "nach", wurzeln):
                # Die Monats-Fakten führen je Auto nur die privaten (Regel 3, `EmobFakten.je_auto`).
                z.append(_z(f"{q.name}:{s}:{g.name}", _wert(wurzeln, q, s, g),
                            None if (dienst and s == "fakten") else soll))
            if datenstand and q.tag is not None:
                abw = []
                for t in juni + juli:
                    s_tag = _soll_fuer(form, q, (t,), weg, g)
                    ist = q.tag(w_tage[t.isoformat()], g.name)
                    if not _gleich(ist, s_tag):
                        abw.append((t.isoformat(), ist, s_tag))
                z.append(_tage_zelle(f"{q.name}:tag:{g.name}", abw))
    if groesse == "wp":
        for s, pfad, summe in (("cockpit_monat", "wp_geraete/{g}/strom_kwh", "wp_strom_kwh"),
                               ("fakten", "wp_je_geraet/{g}/strom_kwh", "wp/strom_kwh")):
            if datenstand and s == "fakten":
                continue
            w = wurzeln[s]
            teile = [_p(w, pfad.replace("{g}", g.name)) for g in geraete]
            z.append(_z(f"Σgeraete=summe:{s}", None if all(t is None for t in teile)
                        else round(sum(t or 0.0 for t in teile), 4), _p(w, summe)))
    if groesse == "speicher" and not datenstand:
        d = wurzeln["dashboards"]
        teile = [_p(d, f"speicher/{g.name}/juni/ladung_kwh") for g in geraete]
        z.append(_z("Σgeraete=summe:ladung", round(sum(t or 0.0 for t in teile), 4),
                    _p(wurzeln["fakten"], "speicher/ladung_kwh")))
    if groesse == "speicher" and datenstand:
        for g in geraete:
            abw = []
            for t in juni + juli:
                soll = round(am.menge(g.felder["entladung_kwh"], (t,)) - am.menge(g.felder["ladung_kwh"], (t,)), 4)
                ist = _p(w_tage[t.isoformat()], f"keys/batterie:{g.name}")
                if not _gleich(ist, soll):
                    abw.append((t.isoformat(), ist, soll))
            z.append(_tage_zelle(f"tag:batterie_netto:{g.name}", abw))
    if groesse == "emob":
        for g in form.typ("wallbox"):
            if datenstand:
                abw = []
                for t in juni + juli:
                    soll = am.menge(g.felder["ladung_kwh"], (t,))
                    ist = _p(w_tage[t.isoformat()], f"keys/wallbox:{g.name}")
                    if not _gleich(ist, soll):
                        abw.append((t.isoformat(), ist, soll))
                z.append(_tage_zelle(f"tag:wallbox:{g.name}", abw))
            else:
                z.append(_z(f"wallbox:dashboards:{g.name}", _p(wurzeln["dashboards"], f"wallbox/{g.name}/juni/ladung_kwh"),
                            am.menge(g.felder["ladung_kwh"], juni)))
        if datenstand:
            # Tag: je Auto ein Key mit seiner Ladung — außer neben einer Wallbox mit Ladezähler (Wallbox-Regel,
            # `komponenten_beitraege.wallbox_deckt_ladung_ab`): dann trägt die Wallbox, das Auto keinen Key.
            for g in form.typ("e-auto"):
                abw = []
                for t in juni + juli:
                    soll = None if form.typ("wallbox") else round(sum(am.menge(fn, (t,)) for fn in g.felder.values()), 4)
                    ist = _p(w_tage[t.isoformat()], f"keys/eauto:{g.name}")
                    if not _gleich(ist, soll):
                        abw.append((t.isoformat(), ist, soll))
                z.append(_tage_zelle(f"tag:eauto:{g.name}", abw))
    return z


def _bewerte_folge(form, groesse, weg, m, wurzeln, datenstand) -> list[Zelle]:  # noqa: C901
    z: list[Zelle] = []
    tage = am.TAGE_JULI if datenstand else am.TAGE_JUNI
    w_tage = m.tage[_teil(weg)]
    # Gemessene 0 bleibt 0 (Auftrag I5): jede Menge mit Soll 0 ist in jeder Sicht 0, nicht None.
    for q in _mengen(groesse, geraet=False, form=form):
        soll = _soll_fuer(form, q, tage, weg)
        if not _ist_null_soll(soll) or not any(g for g in _geraete_oder_basis(form, groesse)):
            continue
        if q.name in ("netzladung", "strom_heizen", "strom_warmwasser", "modus_heizen", "modus_kuehlen",
                      "modus_warmwasser", "kaelte", "heim_netz", "heizung", "warmwasser", "erzeugung",
                      "verbrauch") and not _gemessen_null(form, groesse, q.name):
            continue   # eine 0, die niemand misst, ist keine gemessene 0
        for s in _sichten(q, "laufend" if datenstand else "nach"):
            v = _wert(wurzeln, q, s)
            z.append(Zelle(f"null:{q.name}:{s}", v, 0.0, "ok" if v is not None and abs(float(v)) < 1e-9 else "rot",
                           "gemessene 0 bleibt 0"))
    if groesse == "netz":
        kat = {q.name: q for q in KATALOG["netz"]}
        sp = {q.name: q for q in KATALOG["speicher"] if not q.geraet}
        so = {q.name: q for q in KATALOG["sonstiges"] if not q.geraet}
        sichten = ("cockpit_monat", "cockpit_jahr", "jahr_verlauf", "fakten_tw") if datenstand else \
                  ("cockpit_monat", "fakten", "uebersicht", "cockpit_jahr", "tabelle")
        for s in sichten:
            d = {k: _wert(wurzeln, kat[n], s) for k, n in (("einsp", "einspeisung"), ("netz", "netzbezug"),
                                                          ("ev", "eigenverbrauch"), ("gv", "gesamtverbrauch"),
                                                          ("autarkie", "autarkie"))}
            pv = _wert(wurzeln, kat["pv"], s)
            erz = _wert(wurzeln, so["erzeugung"], s)
            d["hz"] = None if pv is None else pv + (erz or 0.0)
            if s in ("fakten", "fakten_tw"):
                d["hz"] = _p(wurzeln[s], "erzeugung/hinter_zaehler_kwh")
            d["lad"] = _wert(wurzeln, sp["ladung"], s)
            d["entl"] = _wert(wurzeln, sp["entladung"], s)
            z += _folge_netz(s, d)
        if datenstand:
            # Der Tag: Eigenverbrauch und Gesamtverbrauch aus den Mengen desselben Tages.
            abw = []
            for t in am.TAGE_JUNI + am.TAGE_JULI:
                tw = w_tage[t.isoformat()]["tw"]
                d = {"einsp": tw.get("einspeisung"), "netz": tw.get("netzbezug"), "ev": tw.get("eigenverbrauch"),
                     "gv": tw.get("gesamtverbrauch"), "hz": tw.get("erzeugung"),
                     "lad": tw.get("speicher_ladung"), "entl": tw.get("speicher_entladung")}
                if tw.get("eigenverbrauch") is None and _verworfen(form, (t,), weg):
                    continue   # Tagesregel R7: ein Tag mit verworfener Stunde nennt keinen EV
                rot = [x for x in _folge_netz("tag", d) if x.status == "rot"]
                if rot:
                    abw.append((t.isoformat(), rot[0]))
            z.append(Zelle("tag:folge", abw[0][1].ist if abw else "EV/GV je Tag",
                           abw[0][1].soll if abw else "folgen den Mengen", "rot" if abw else "ok",
                           f"{len(abw)} von 33 Tagen, erster {abw[0][0]}: {abw[0][1].sicht}" if abw else "33 Tage"))
    elif groesse == "speicher":
        kap = sum((g.parameter or {}).get("kapazitaet_kwh", 0.0) for g in form.typ("speicher"))
        paare = (("cockpit_monat", "speicher_ladung_kwh", "speicher_entladung_kwh", "speicher_wirkungsgrad_prozent",
                  "speicher_vollzyklen"),
                 ("cockpit_jahr", "speicher_ladung_kwh", "speicher_entladung_kwh", "speicher_wirkungsgrad_prozent",
                  "speicher_vollzyklen"))
        if not datenstand:
            paare += (("uebersicht", "speicher_ladung_kwh", "speicher_entladung_kwh", "speicher_effizienz_prozent",
                       "speicher_vollzyklen"),)
        for s, l, e, eta, vz in paare:
            d = wurzeln[s] or {}
            lv, ev = d.get(l), d.get(e)
            if lv:
                z.append(_z(f"{s}:wirkungsgrad", d.get(eta), round(100.0 * (ev or 0.0) / lv, 1), tol=0.15))
            if kap:
                z.append(_z(f"{s}:vollzyklen", d.get(vz), round((ev or 0.0) / kap, 1), tol=0.06))
        if not datenstand:
            ha = wurzeln["ha_export"]
            fk = wurzeln["fakten"]
            lv, ev = _p(fk, "speicher/ladung_kwh"), _p(fk, "speicher/entladung_kwh")
            if kap:
                z.append(_z("ha_export:vollzyklen", _p(ha, "anlage/speicher_zyklen"), round((ev or 0) / kap, 2), tol=0.06))
                z.append(_z("pdf_kopf:vollzyklen", _p(wurzeln["pdf_kopf"], "speicher.vollzyklen"), round((ev or 0) / kap, 2),
                            tol=0.06))
            if lv:
                z.append(_z("ha_export:wirkungsgrad", _p(ha, "anlage/speicher_effizienz_prozent"), 100.0 * ev / lv, tol=0.15))
            nl = _feld(form, "speicher", "ladung_netz_kwh", tage)
            if nl:
                kosten = _p(wurzeln["cockpit_monat"], "speicher_ladung_netz_kosten_euro")
                z.append(_z("cockpit_monat:netzladung_kosten", kosten, round(nl * _preis_soll(form, weg) / 100.0, 2)))
        else:
            abw = []
            for t in am.TAGE_JUNI + am.TAGE_JULI:
                tw = w_tage[t.isoformat()]["tw"]
                lv, ev = tw.get("speicher_ladung"), tw.get("speicher_entladung")
                if lv and not _gleich(tw.get("speicher_effizienz"), round(100 * (ev or 0) / lv, 1), tol=0.15):
                    abw.append((t.isoformat(), tw.get("speicher_effizienz"), round(100 * (ev or 0) / lv, 1)))
            z.append(Zelle("tag:wirkungsgrad", abw[0][1] if abw else "je Tag", abw[0][2] if abw else "Entl./Ladung",
                           "rot" if abw else "ok", f"{len(abw)} Tage" if abw else "33 Tage"))
    elif groesse == "wp":
        for s, w_, st_, jz in (("cockpit_monat", "wp_waerme_kwh", "wp_strom_kwh", "wp_jaz"),
                               ("uebersicht", "wp_waerme_kwh", "wp_strom_kwh", "wp_cop")):
            if datenstand and s == "uebersicht":
                continue
            d = wurzeln[s] or {}
            nenner = d.get("wp_jaz_nenner_kwh") if d.get("wp_jaz_nenner_kwh") is not None else d.get(st_)
            zaehler = d.get("wp_jaz_zaehler_kwh") if d.get("wp_jaz_zaehler_kwh") is not None else d.get(w_)
            if nenner:
                z.append(_z(f"{s}:jaz=zaehler/nenner", d.get(jz), round((zaehler or 0) / nenner, 2), tol=0.02))
        for g in form.typ("waermepumpe"):
            d = _p(wurzeln["cockpit_monat"], f"wp_geraete/{g.name}") or {}
            if d.get("strom_kwh"):
                z.append(_z(f"cockpit_monat:jaz:{g.name}", d.get("jaz"), round((d.get("waerme_kwh") or 0) / d["strom_kwh"], 2),
                            tol=0.02))
    elif groesse == "emob":
        for s in (("cockpit_monat", "fakten") if not datenstand else ("cockpit_monat",)):
            d = wurzeln[s] or {}
            kat = {q.name: q for q in KATALOG["emob"] if not q.geraet}
            lad, pv, nz = (_wert(wurzeln, kat[n], s) for n in ("heimladung", "heim_pv", "heim_netz"))
            if lad:
                z.append(_z(f"{s}:pv+netz=ladung", round((pv or 0) + (nz or 0), 4), lad))
    elif groesse == "sonstiges":
        if not datenstand:
            fk = wurzeln["fakten"]
            z.append(_z("fakten:hinter_zaehler=pv+erzeugung", _p(fk, "erzeugung/hinter_zaehler_kwh"),
                        round((_p(fk, "erzeugung/pv_kwh") or 0) + (_p(fk, "sonstiges/erzeugung_kwh") or 0), 4)))
            # PV-Kennzahlen ohne Sonstiges-Erzeuger: die PV-Erzeugung der Sichten ist die PV allein.
            for sicht, pfad in (("cockpit_monat", "pv_erzeugung_kwh"), ("uebersicht", "pv_erzeugung_kwh"),
                                ("tabelle", "pv_erzeugung_kwh")):
                z.append(_z(f"{sicht}:pv_ohne_sonstiges", _p(wurzeln[sicht], pfad), _p(fk, "erzeugung/pv_kwh")))
    elif groesse == "preis":
        if not datenstand:
            # Aussichten → bisherige Erträge = Netto-Ertrag + WP- + E-Mob-Ersparnis der Übersicht (gemessen an
            # Formen ohne und mit Geräte-Ersparnis; die Speicher-Ersparnis steckt im Eigenverbrauch).
            u = wurzeln["uebersicht"]
            teile = [u.get("netto_ertrag_euro"), u.get("wp_ersparnis_euro"), u.get("emob_ersparnis_euro")]
            z.append(_z("aussichten:bisherige=netto+wp+emob", _p(m.nach[weg]["aussichten"], "bisherige_ertraege_euro"),
                        round(sum(t or 0.0 for t in teile), 2), tol=0.02))
        for s in ("cockpit_monat",) + (("cockpit_jahr",) if datenstand else ("cockpit_jahr",)):
            d = wurzeln[s] or {}
            if d.get("netzbezug_kwh") is not None and d.get("netzbezug_preis_effektiv_cent") is not None:
                z.append(_z(f"{s}:kosten=menge×preis", d.get("netzbezug_kosten_euro"),
                            round(d["netzbezug_kwh"] * d["netzbezug_preis_effektiv_cent"] / 100.0, 2), tol=0.02))
    return z


def _geraete_oder_basis(form, groesse):
    return [True] if groesse in ("netz", "preis") else _geraete(form, groesse)


def _gemessen_null(form, groesse, name) -> bool:
    """Gibt es einen zugeordneten Zähler, dessen Monatsmenge 0 ist und der diese Menge trägt?"""
    if groesse == "wp":
        return any(all(am.menge(fn, am.TAGE_JUNI) == 0 for fn in g.felder.values()) for g in form.typ("waermepumpe"))
    return False


# ── Sicht „Hub-Verlauf" (Vorhaben nach 4.1.3, Vorbild `bkw_hub:*` der PV-Matrix, N-638) ─────────────────────────
#
# Komponenten → <Typ> → Verlauf/Vergleich: die Monatsreihe, die der Frontend-Leser aus `monatsdaten[].verbrauch_daten`
# liest (Nachbildung in `achsen_matrix.miss_hub`, Schlüssel und Fundstelle dort je Serie zitiert), gegen die Kopfzahlen
# derselben Antwort (I4: Σ Verlauf = Kopf), gegen die Monats-Fakten und die Lesetür auf derselben Zeile (I1: eine Zahl)
# und ihre Folgekennzahlen (I5). **Eigene Zellen** (Größe `hub_<typ>`), nicht in den bestehenden: eine rote Hub-Sicht
# macht so keine bisher grüne Zelle rot. Nur nach dem Abschluss (S1 · S2 · S3) — vor dem Abschluss und im laufenden
# Monat trägt der Hub keine Monatszeile (gemessen, Bericht `opus-berichte/HUB-VERLAUF-MATRIX.md`).

#: Hub-Größe → Investitionstypen, deren Hub sie misst.
HUB_GROESSEN: dict[str, tuple[str, ...]] = {
    "hub_speicher": ("speicher",), "hub_wp": ("waermepumpe",), "hub_sonstiges": ("sonstiges",),
    "hub_emob": ("e-auto", "wallbox"),
}
HUB_WEGE = ("S1", "S2", "S3")
HUB_INVARIANTEN = ("I1", "I4", "I5")
#: Kopfzahlen der Komponenten-Routen runden auf 0,1 — Σ der ungerundeten Reihe liegt höchstens 0,05 daneben.
_TOL_KOPF = 0.051


def _hub_geraete(form: am.Form, hub: dict, typ: str, z: list):
    """Je Gerät dieses Typs der Hub-Eintrag; fehlt er, ist das eine rote Sicht (die Route nennt das Gerät nicht)."""
    for g in form.typ(typ):
        d = (hub.get(typ) or {}).get(g.name)
        if d is None:
            z.append(Zelle(f"eintrag:{typ}:{g.name}", None, "Eintrag je Gerät", "rot", "die Route nennt das Gerät nicht"))
            continue
        yield g, d["kopf"], d["summe"], d["juni"] or {}, d


def _bewerte_hub(fid: str, groesse: str, weg: str, inv: str, m: am.Messung) -> list[Zelle]:  # noqa: C901 — eine Tafel
    from backend.core.berechnungen import vollzyklen as berechne_vollzyklen

    form = am.MATRIX_FORMEN[fid]
    hub = m.nach[weg].get("hub") or {}
    fk = hub.get("fakten") or {}
    z: list[Zelle] = []
    if groesse == "hub_speicher":
        juni_teile = []
        for g, k, s, j, _d in _hub_geraete(form, hub, "speicher", z):
            juni_teile.append(j)
            # Der Netz-Stapel im Verlauf steht nur bei `arbitrage_faehig` und Netzladung (SpeicherVerlaufCharts.tsx:74);
            # die Jahresbilanz zeigt ihn immer, sobald ein Monat Netzladung trägt (SpeicherJahresbilanz.tsx:72-73).
            verlauf_netz = bool(k.get("arbitrage_faehig")) and (k.get("arbitrage_kwh") or 0) > 0
            if inv == "I4":
                z += [_z(f"ladung:Σreihe=kopf:{g.name}", s["ladung"], k.get("gesamt_ladung_kwh"), tol=_TOL_KOPF),
                      _z(f"entladung:Σreihe=kopf:{g.name}", s["entladung"], k.get("gesamt_entladung_kwh"), tol=_TOL_KOPF),
                      _z(f"netzladung_jahresbilanz:Σreihe=kopf:{g.name}", s["jb_netz"], k.get("arbitrage_kwh"),
                         tol=_TOL_KOPF, notiz="Kopf `arbitrage_kwh` (Lesetür)"),
                      _z(f"zyklen:Σreihe=kopf:{g.name}", s["zyklen"], k.get("vollzyklen"), tol=_TOL_KOPF,
                         notiz="Kopf `vollzyklen` = Entladung ÷ Kapazität")]
                if verlauf_netz:
                    z.append(_z(f"netzladung_verlauf:Σreihe=kopf:{g.name}", s["arbitrage"], k.get("arbitrage_kwh"),
                                tol=_TOL_KOPF))
            elif inv == "I1":
                z.append(_z(f"netzladung_jahresbilanz:juni=tuer:{g.name}", j.get("jb_netz"), j.get("tuer_netzladung"),
                            notiz="Lesetür `get_speicher_netzladung_kwh` derselben Zeile"))
                if verlauf_netz:
                    z.append(_z(f"netzladung_verlauf:juni=tuer:{g.name}", j.get("arbitrage"), j.get("tuer_netzladung")))
            elif inv == "I5":
                kap = k.get("kapazitaet_kwh")
                z.append(_z(f"zyklen:juni=vollzyklen(entladung):{g.name}", j.get("zyklen"), j.get("tuer_zyklen"),
                            tol=0.01, notiz="`berechne_vollzyklen` auf der Entladung derselben Zeile"))
                if j:
                    lad = j.get("ladung") or 0.0
                    z.append(_z(f"pv_ladung_jahresbilanz:juni=ladung−netzladung:{g.name}", max(0.0, lad - (j.get("jb_netz") or 0)),
                                max(0.0, lad - (j.get("tuer_netzladung") or 0))))
                if kap:
                    vz = berechne_vollzyklen(k.get("gesamt_entladung_kwh") or 0.0, kap)
                    z.append(_z(f"vollzyklen:kopf=vollzyklen(kopf_entladung):{g.name}", k.get("vollzyklen"),
                                round(vz or 0.0, 1), tol=0.06))
        if inv == "I1":
            for menge, leser, fakt in (("ladung", "ladung", "ladung_kwh"), ("entladung", "entladung", "entladung_kwh"),
                                       ("netzladung_jahresbilanz", "jb_netz", "netzladung_kwh")):
                z.append(_z(f"{menge}:Σgeraete_juni=fakten", round(sum(t.get(leser) or 0.0 for t in juni_teile), 4),
                            _p(fk, f"speicher/{fakt}")))
    elif groesse == "hub_wp":
        heiz, ww = [], []
        for g, k, s, j, d in _hub_geraete(form, hub, "waermepumpe", z):
            hat_ww = d.get("hat_ww")
            heiz.append(j.get("heizung") or 0.0)
            ww.append(j.get("warmwasser") or 0.0)
            if inv == "I4":
                z += [_z(f"strom:Σreihe=kopf:{g.name}", s["strom"], k.get("gesamt_stromverbrauch_kwh"), tol=_TOL_KOPF),
                      _z(f"heizung:Σreihe=kopf:{g.name}", s["heizung"], k.get("gesamt_heizenergie_kwh"), tol=_TOL_KOPF),
                      # Σ der gezeichneten Flächen (Nachbildung `waerme`): mit Warmwasser-Achse Heizung + Warmwasser,
                      # ohne sie die EINE Fläche „Wärme" = Wärme gesamt (N-643, S2).
                      _z(f"waerme:Σreihe=kopf:{g.name}", s["waerme"],
                         k.get("gesamt_waerme_kwh"), tol=_TOL_KOPF,
                         notiz="ohne Warmwasser-Achse trägt die Fläche „Wärme“ die Wärme gesamt (WaermepumpeCharts.tsx)")]
                if hat_ww:
                    z.append(_z(f"warmwasser:Σreihe=kopf:{g.name}", s["warmwasser"], k.get("gesamt_warmwasser_kwh"),
                                tol=_TOL_KOPF))
            elif inv == "I1":
                z += [_z(f"strom:juni=fakten:{g.name}", j.get("strom"), _p(fk, f"wp_je_geraet/{g.name}/strom_kwh")),
                      _z(f"waerme:juni=fakten:{g.name}", j.get("waerme") if j else None,
                         _p(fk, f"wp_je_geraet/{g.name}/waerme_kwh")),
                      _z(f"heizung:juni=tuer:{g.name}", j.get("heizung"), j.get("tuer_heizung") or 0.0 if j else None,
                         notiz="Lesetür `heizwaerme_kwh` derselben Zeile"),
                      _z(f"aussicht_strom:juni=tuer:{g.name}", j.get("aussicht_strom"), j.get("tuer_strom"),
                         notiz="Zeilen-Leser der Aussicht; HEIZ_MONATE nicht nachgebildet"),
                      _z(f"aussicht_waerme:juni=tuer:{g.name}", j.get("aussicht_waerme"), j.get("tuer_waerme"),
                         notiz="Zeilen-Leser der Aussicht; HEIZ_MONATE nicht nachgebildet")]
                if hat_ww:
                    z.append(_z(f"warmwasser:juni=tuer:{g.name}", j.get("warmwasser"), j.get("tuer_warmwasser")))
            elif inv == "I5":
                nenner = s.get("jaz_nenner")
                z.append(_z(f"jaz:kopf=Σzaehler/Σnenner:{g.name}", k.get("durchschnitt_cop"),
                            round(s["jaz_zaehler"] / nenner, 2) if nenner else None, tol=0.02))
        if inv == "I1":
            z += [_z("heizung:Σgeraete_juni=fakten", round(sum(heiz), 4), _p(fk, "wp/heizung_kwh")),
                  _z("warmwasser:Σgeraete_juni=fakten", round(sum(ww), 4), _p(fk, "wp/warmwasser_kwh"))]
    elif groesse == "hub_sonstiges":
        for g, k, s, j, _d in _hub_geraete(form, hub, "sonstiges", z):
            if (g.parameter or {}).get("kategorie") == "erzeuger":
                if inv == "I4":
                    z.append(_z(f"erzeugung:Σreihe=kopf:{g.name}", s["erzeugung"], k.get("gesamt_erzeugung_kwh"),
                                tol=_TOL_KOPF))
                elif inv == "I1":
                    z.append(_z(f"erzeugung:juni=fakten:{g.name}", j.get("erzeugung"),
                                _p(fk, f"sonstiges_je_geraet/{g.name}/erzeugung_kwh")))
                continue
            if inv == "I4":
                z += [_z(f"verbrauch_vergleich:Σreihe=kopf:{g.name}", s["vergleich_verbrauch"],
                         k.get("gesamt_verbrauch_kwh"), tol=_TOL_KOPF, notiz="Vergleich: Σ `verbrauch_kwh` je Jahr"),
                      # N-645 (Fachentscheid Master 09.10.2026): der Verlauf stapelt PV · Netz · „nicht aufgeteilt" —
                      # Soll „Verlauf = Kopf" (vorher Soll unklar, `_U_HUB_SONST_BEZUG`, Haltewert 0).
                      _z(f"verbrauch_verlauf:Σreihe=kopf:{g.name}",
                         round(s["bezug_pv"] + s["bezug_netz"] + s["nicht_aufgeteilt"], 4),
                         k.get("gesamt_verbrauch_kwh"), tol=_TOL_KOPF,
                         notiz="Verlauf: PV + Netz + nicht aufgeteilt gestapelt"),
                      _z(f"bezug_pv:Σreihe=kopf:{g.name}", s["bezug_pv"], k.get("bezug_pv_kwh"), tol=_TOL_KOPF),
                      _z(f"bezug_netz:Σreihe=kopf:{g.name}", s["bezug_netz"], k.get("bezug_netz_kwh"), tol=_TOL_KOPF)]
            elif inv == "I1":
                z += [_z(f"verbrauch_vergleich:juni=fakten:{g.name}", j.get("vergleich_verbrauch"),
                         _p(fk, f"sonstiges_je_geraet/{g.name}/verbrauch_kwh")),
                      _z(f"verbrauch_vergleich:juni=tuer:{g.name}", j.get("vergleich_verbrauch"), j.get("tuer_verbrauch"),
                         notiz="Lesetür `get_sonstiges_verbrauch_kwh` derselben Zeile")]
            elif inv == "I5":
                v = k.get("gesamt_verbrauch_kwh") or 0.0
                z.append(_z(f"pv_anteil:kopf=bezug_pv/verbrauch:{g.name}", k.get("pv_anteil_prozent"),
                            round(100.0 * (k.get("bezug_pv_kwh") or 0.0) / v, 1) if v else 0.0, tol=0.06))
    elif groesse == "hub_emob":
        dienst_juni = {"pv": 0.0, "netz": 0.0}
        for g, k, s, j, _d in _hub_geraete(form, hub, "e-auto", z):
            dienst = bool((g.parameter or {}).get("ist_dienstlich"))
            if inv == "I4":
                z += [_z(f"ladung_pv:Σreihe=kopf:{g.name}", s["pv"], k.get("ladung_pv_kwh"), tol=_TOL_KOPF),
                      _z(f"ladung_netz:Σreihe=kopf:{g.name}", s["netz"], k.get("ladung_netz_kwh"), tol=_TOL_KOPF),
                      _z(f"ladung_extern:Σreihe=kopf:{g.name}", s["extern"], k.get("ladung_extern_kwh"), tol=_TOL_KOPF),
                      _z(f"ladung:Σreihe=kopf:{g.name}", round(s["pv"] + s["netz"] + s["extern"], 4),
                         k.get("gesamt_ladung_kwh"), tol=_TOL_KOPF)]
            elif inv == "I1":
                if dienst:
                    dienst_juni["pv"] += j.get("pv") or 0.0
                    dienst_juni["netz"] += j.get("netz") or 0.0
                else:
                    z += [_z(f"ladung_pv:juni=fakten:{g.name}", j.get("pv"), _p(fk, f"emob_je_auto/{g.name}/pv_kwh")),
                          _z(f"ladung_netz:juni=fakten:{g.name}", j.get("netz"), _p(fk, f"emob_je_auto/{g.name}/netz_kwh"))]
            elif inv == "I5":
                heim = (k.get("ladung_pv_kwh") or 0.0) + (k.get("ladung_netz_kwh") or 0.0)
                z.append(_z(f"pv_anteil:kopf=pv/(pv+netz):{g.name}", k.get("pv_anteil_heim_prozent"),
                            round(100.0 * (k.get("ladung_pv_kwh") or 0.0) / heim, 1) if heim else 0.0, tol=0.06))
        if inv == "I1" and any((g.parameter or {}).get("ist_dienstlich") for g in form.typ("e-auto")):
            z += [_z("dienst_pv:Σdienst_juni=fakten", round(dienst_juni["pv"], 4), _p(fk, "emob/dienstlich_ladung_pv_kwh")),
                  _z("dienst_netz:Σdienst_juni=fakten", round(dienst_juni["netz"], 4),
                     _p(fk, "emob/dienstlich_ladung_netz_kwh"))]
        wb_juni = []
        for g, k, s, j, _d in _hub_geraete(form, hub, "wallbox", z):
            wb_juni.append(j.get("heim") or 0.0)
            if inv == "I4":
                z.append(_z(f"heimladung:Σreihe=kopf:{g.name}", s["heim"], k.get("gesamt_heim_ladung_kwh"), tol=_TOL_KOPF))
            elif inv == "I5":
                z.append(_z(f"heimladung:kopf=pv+netz:{g.name}", k.get("gesamt_heim_ladung_kwh"),
                            round((k.get("ladung_pv_kwh") or 0.0) + (k.get("ladung_netz_kwh") or 0.0), 4), tol=_TOL_KOPF))
        if inv == "I1" and form.typ("wallbox"):
            z.append(_z("heimladung:Σwallbox_juni=fakten", round(sum(wb_juni), 4),
                        _p(fk, "emob_wallbox_summe/ladung_kwh")))
    return z


# ── Register: rote Zellen, ohne Abschluss nicht geführt, Soll unklar ───────


class BekannterMangel(AssertionError):
    """Die Zelle ist rot, und zwar genau mit den Sichten, die ``BEKANNT`` für sie nennt."""


@dataclass(frozen=True)
class Ursache:
    zuordnung: str
    grund: str


#: Die Ursachen der roten Zellen gegen HEAD ``66a37ac4`` (v4.1.2) — gemessen 05.10.2026, Bericht
#: ``~/.claude/plans/opus-berichte/ACHSEN-MATRIX-2.md``. Kandidaten werden nur gezeigt, nichts ist gebaut.
URSACHE: dict[str, Ursache] = {
    "N-586": Ursache(
        "HA-Bauform S1+S2 (Pflicht)",
        "Zählersprung (N3, 250 kWh in der ersten Ertragsstunde nach der Nacht, je auf Einspeisung und PV-Gesamt"
        "zähler): die Tagesregel verwirft die Stunde (Spannen-Deckel ab dem Anker), der Monat übernimmt den Sprung "
        "(`ha_statistics_service.get_sensor_monatswert`, Nullstunden ab der letzten Änderung). Cockpit → Monat "
        "(laufend) nennt 304/268 statt Σ Tage 51/17; „Aus HA laden“ und Sammelimport schreiben 790/430 statt "
        "537/179 in den Juni",
    ),
    "TEILTAG-ZWEI-MONATSGRENZEN": Ursache(
        "HA-Bauform S4 (R-3 „Kalendertag\")",
        "Laufender Monat zwischen 00:05 und etwa 01:09 (Matrix-Uhr 00:30): die Monats-Fakten und der Jahr-Verlauf "
        "rechnen den Monat aus den Kanälen über das Tagesfenster-Monatsfenster (ab Vortag 23:00) bis zum letzten "
        "geschriebenen Stand und tragen damit schon die erste Stunde des neuen Tagesfensters (Netzbezug 0,4 kWh); "
        "Cockpit → Monat nimmt den HA-Weg über den Kalendermonat (ab 1. 00:00) ohne diese Stunde. Zwei "
        "Monatsgrenzen (Bauplan E3-Nachtrag 2); sie fallen erst mit R-3 „Kalendertag\" in S4 zusammen. Entscheid "
        "Master 06.10.2026: bleibt bis dahin, benannt. Kosten folgen dem Netzbezug. Seit E4d dieselbe Stunde für die "
        "Wärmepumpe (Strom, Wärme und Funktionsmengen; 0,3 kWh Strom in M05)",
    ),
    "N-585-REST": Ursache(
        "HA-Bauform S1+S2 (Pflicht) — seit HA-Bauform E4d geheilt (Bauplan §8a); keine Zelle mehr",
        "Wärmepumpe ohne Betrieb (W5, Strom 0 und Wärme 0 gemessen): Cockpit → Monat/Jahr, Community und PDF nennen "
        "keine 0, sondern nichts; der Tag nennt `wp_strom` nicht, obwohl die Tageszeile `waermepumpe_<id> = 0` "
        "trägt. Monats-Fakten, Übersicht, Dashboard nennen 0 (Halteprobe `test_n585_gemessene_null.py`)",
    ),
    "OHNE-ABSCHLUSS": Ursache(
        "Ausgangszustand (Auftrag): ohne Abschluss nicht geführt — seit HA-Bauform E4c für E-Mobilität und Sonstiges, "
        "seit E4d für die Wärmepumpe mit HA (Kanäle, Wege HA/S1/S2) geheilt; es bleiben Speicher-Netzladung und die "
        "Wege ohne Kanäle (SA/S3, Lesart 1 — dort auch die Wärmepumpe: Monats-Fakten und Jahr-Verlauf ohne Abschluss "
        "ohne WP-Mengen, Cockpit → Monat aus der Tagesebene ohne Betriebsart-Strom, Kälte und Heiz-Nutzenergie des "
        "Klimageräts)",
        "Größen, die im Monat ohne Abschluss nicht aus der Tagesebene gefüllt werden: Wärmepumpen-Mengen und "
        "-Achsen, Sonstiges, E-Mob-Lademenge, Speicher-Netzladung (Monats-Fakten mit Tageswerten und "
        "Jahr-Verlauf nennen 0/nichts; Sonstiges und Netzladung auch Cockpit → Monat; E-Mob ohne HA auch Cockpit "
        "→ Monat). Folge in der Form mit Sonstiges-Erzeuger (M10): Eigenverbrauch, Gesamtverbrauch, Autarkie "
        "und Erzeugung hinter dem Zähler des Monats ohne Abschluss rechnen ohne das BHKW. Cockpit → Monat nennt "
        "daneben für WP-Strom/-Wärme und (mit HA) die Lademenge den Wert der Tagesebene",
    ),
    "KANDIDAT-EMOB-LAUFEND-NETZ": Ursache(
        "KANDIDAT (nur gezeigt) — N-631, seit HA-Bauform E4c geheilt (eine Aufteilung aus dem abgeleiteten Kanal für "
        "den Monat mit und ohne Abschluss); keine Zelle mehr",
        "Wallbox-Ladung im Monat ohne Abschluss (HA-Weg von Cockpit → Monat): die ganze Lademenge steht als "
        "Netz-Ladung (9,0 / 90,0 kWh), PV 0 — obwohl die Ladestunden ohne Netzbezug in der Sonne liegen; nach dem "
        "Abschluss nennen alle Sichten 100 % PV. Gilt für die laufende (Juli) und die abgeschlossene Zeit vor dem "
        "Abschluss (Juni)",
    ),
    "KANDIDAT-WP-ACHSEN-OHNE-ABSCHLUSS": Ursache(
        "KANDIDAT (nur gezeigt) — N-630, seit HA-Bauform E4d geheilt (die WP-Gruppe aus den Kanälen); keine Zelle mehr",
        "Cockpit → Monat ohne Abschluss führt die feinen WP-Achsen unvollständig: laufend fehlen Betriebsart-Ströme, "
        "Kälte und die Heiz-Nutzenergie des Klimageräts (Heizwärme 54 statt 59,4, ohne HA auch die Wärme 64,8 statt "
        "70,2); im vergangenen Monat vor dem Abschluss (HA-Weg) fehlen Heiz-/Warmwasser-Strom und -Wärme, "
        "Betriebsart-Ströme und Kälte ganz, während Strom- und Wärmemenge da sind",
    ),
}

#: ``Ursache → {(Form, Größe, Weg, Invariante): rote Sichten}`` — gemessen, nicht hergeleitet (erzeugt aus der
#: Messung, Klassifikation siehe Bericht).
ROT: dict[str, dict[tuple[str, str, str, str], tuple[str, ...]]] = {
    # N-586: seit HA-Bauform E4a-2 geheilt (Soll umgedreht „Tag = Monat = HA", Bauplan §7; Markierungen entfernt
    # vom Master nach §6a, 06.10.2026) — keine Zelle mehr.
    'N-586': {},
    'TEILTAG-ZWEI-MONATSGRENZEN': {
        ('M01', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M03', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M04', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M05', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M06', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M07', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M08', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M09', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf',
            'netzbezug:fakten_tw', 'netzbezug:jahr_verlauf',
        ),
        ('M01', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M03', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M04', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M05', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M06', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M07', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M08', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M07', 'sonstiges', 'HA', 'I1'): ('verbrauch:fakten_tw', 'verbrauch:jahr_verlauf'),
        ('M09', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf',),
        ('M10', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'eigenverbrauch:fakten_tw', 'eigenverbrauch:jahr_verlauf',
            'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf', 'netzbezug:fakten_tw',
            'netzbezug:jahr_verlauf',
        ),
        ('M10', 'netz', 'HA', 'I2'): ('gesamtverbrauch:fakten_tw=Σtage', 'gesamtverbrauch:jahr_verlauf=Σtage'),
        ('M10', 'sonstiges', 'HA', 'I1'): ('erzeugung:fakten_tw', 'erzeugung:jahr_verlauf'),
        ('M10', 'preis', 'HA', 'I1'): ('kosten:jahr_verlauf', 'netto_ertrag:jahr_verlauf'),
        ('M05', 'wp', 'HA', 'I1'): ('strom:fakten_tw', 'strom:jahr_verlauf', 'waerme:fakten_tw'),
        ('M06', 'wp', 'HA', 'I1'): (
            'heizung:fakten_tw', 'heizung:jahr_verlauf', 'strom:fakten_tw', 'strom:jahr_verlauf',
            'strom_heizen:fakten_tw', 'strom_heizen:jahr_verlauf', 'waerme:fakten_tw', 'warmwasser:fakten_tw',
            'warmwasser:jahr_verlauf',
        ),
    },
    # N-585-REST: seit HA-Bauform E4d geheilt (Bauplan §8a: eine gemessene 0 ist erfasst; Strom 0 und Wärme 0 = Stufe 3,
    # Mengen 0, Ersparnis 0 €) — keine Zelle mehr. Die Sichten der Wege ohne Kanäle, die die 0 vor dem Abschluss nicht
    # kennen (Jahr-Verlauf aus den Monats-Fakten, Lesart 1), stehen unter OHNE-ABSCHLUSS.
    'N-585-REST': {
    },
    'OHNE-ABSCHLUSS': {
        ('M02', 'emob', 'S3', 'I2'): (
            'heim_pv:fakten:tageswert=gespeichert', 'heimladung:fakten:tageswert=gespeichert',
            'wallbox:fakten:tageswert=gespeichert', 'wallbox:jahr_verlauf:vor=nach',
        ),
        ('M02', 'emob', 'SA', 'I1'): ('heimladung:fakten_tw',),
        ('M04', 'speicher', 'HA', 'I1'): ('netzladung:fakten_tw', 'netzladung:jahr_verlauf',),
        ('M04', 'speicher', 'HA', 'I3'): ('netzladung:cockpit_monat', 'netzladung:fakten_tw',),
        ('M04', 'speicher', 'S1', 'I2'): (
            'netzladung:cockpit_monat:vor=nach', 'netzladung:fakten:tageswert=gespeichert',
            'netzladung:jahr_verlauf:vor=nach',
        ),
        ('M04', 'speicher', 'S2', 'I2'): (
            'netzladung:cockpit_monat:vor=nach', 'netzladung:fakten:tageswert=gespeichert',
            'netzladung:jahr_verlauf:vor=nach',
        ),
        ('M04', 'speicher', 'S3', 'I2'): (
            'netzladung:fakten:tageswert=gespeichert', 'netzladung:jahr_verlauf:vor=nach',
        ),
        ('M04', 'speicher', 'SA', 'I1'): ('netzladung:fakten_tw', 'netzladung:jahr_verlauf',),
        ('M04', 'speicher', 'SA', 'I3'): ('netzladung:cockpit_monat', 'netzladung:fakten_tw',),
        ('M05', 'wp', 'S3', 'I2'): (
            'strom:fakten:tageswert=gespeichert', 'strom:jahr_verlauf:vor=nach',
            'waerme:fakten:tageswert=gespeichert',
        ),
        ('M05', 'wp', 'SA', 'I1'): ('strom:fakten_tw', 'strom:jahr_verlauf', 'waerme:fakten_tw',),
        ('M05', 'wp', 'SA', 'I2'): ('strom:fakten_tw=Σtage', 'strom:jahr_verlauf=Σtage',),
        ('M05', 'wp', 'SA', 'I3'): ('strom:fakten_tw', 'waerme:fakten_tw',),
        ('M05', 'wp', 'SA', 'I6'): ('strom:fakten_tw', 'strom:jahr_verlauf', 'waerme:fakten_tw',),
        ('M06', 'wp', 'S3', 'I2'): (
            'heizung:fakten:tageswert=gespeichert', 'heizung:jahr_verlauf:vor=nach',
            'modus_heizen:fakten:tageswert=gespeichert', 'modus_kuehlen:fakten:tageswert=gespeichert',
            'strom:fakten:tageswert=gespeichert', 'strom:jahr_verlauf:vor=nach',
            'strom_heizen:fakten:tageswert=gespeichert', 'strom_heizen:jahr_verlauf:vor=nach',
            'strom_warmwasser:fakten:tageswert=gespeichert', 'strom_warmwasser:jahr_verlauf:vor=nach',
            'waerme:fakten:tageswert=gespeichert', 'warmwasser:fakten:tageswert=gespeichert',
            'warmwasser:jahr_verlauf:vor=nach',
        ),
        ('M06', 'wp', 'SA', 'I1'): (
            'heizung:fakten_tw', 'heizung:jahr_verlauf', 'modus_heizen:fakten_tw', 'modus_kuehlen:fakten_tw',
            'strom:fakten_tw', 'strom:jahr_verlauf', 'strom_heizen:fakten_tw', 'strom_heizen:jahr_verlauf',
            'strom_warmwasser:fakten_tw', 'strom_warmwasser:jahr_verlauf', 'waerme:fakten_tw',
            'warmwasser:fakten_tw', 'warmwasser:jahr_verlauf',
        ),
        ('M06', 'wp', 'SA', 'I2'): ('strom:fakten_tw=Σtage', 'strom:jahr_verlauf=Σtage',),
        ('M06', 'wp', 'SA', 'I6'): (
            'heizung:fakten_tw', 'heizung:jahr_verlauf', 'strom:fakten_tw', 'strom:jahr_verlauf',
            'strom_heizen:fakten_tw', 'strom_heizen:jahr_verlauf', 'strom_warmwasser:fakten_tw',
            'strom_warmwasser:jahr_verlauf', 'waerme:fakten_tw', 'warmwasser:fakten_tw', 'warmwasser:jahr_verlauf',
        ),
        ('M07', 'sonstiges', 'S3', 'I2'): (
            'verbrauch:fakten:tageswert=gespeichert', 'verbrauch:jahr_verlauf:vor=nach',
        ),
        ('M07', 'sonstiges', 'SA', 'I1'): ('verbrauch:fakten_tw',),
        ('M07', 'sonstiges', 'SA', 'I2'): (
            'verbrauch:cockpit_monat=Σtage', 'verbrauch:fakten_tw=Σtage', 'verbrauch:jahr_verlauf=Σtage',
        ),
        ('M07', 'sonstiges', 'SA', 'I3'): ('verbrauch:cockpit_monat', 'verbrauch:fakten_tw',),
        ('M07', 'sonstiges', 'SA', 'I4'): ('geraet:cockpit_monat:Pool',),
        ('M07', 'sonstiges', 'SA', 'I6'): (
            'verbrauch:cockpit_jahr', 'verbrauch:cockpit_monat', 'verbrauch:fakten_tw', 'verbrauch:jahr_verlauf',
        ),
        ('M08', 'emob', 'S3', 'I2'): ('wallbox:fakten:tageswert=gespeichert', 'wallbox:jahr_verlauf:vor=nach',),
        ('M08', 'emob', 'SA', 'I1'): ('heimladung:fakten_tw',),
        ('M09', 'emob', 'S3', 'I2'): (
            'dienst_netz:fakten:tageswert=gespeichert', 'dienst_pv:fakten:tageswert=gespeichert',
            'heim_netz:fakten:tageswert=gespeichert', 'heim_pv:fakten:tageswert=gespeichert',
            'heimladung:fakten:tageswert=gespeichert',
        ),
        ('M09', 'emob', 'SA', 'I1'): ('heimladung:fakten_tw',),
        ('M09', 'emob', 'SA', 'I2'): ('heimladung:cockpit_monat=Σtage',),
        ('M10', 'netz', 'S3', 'I2'): (
            'autarkie:fakten:tageswert=gespeichert', 'autarkie:jahr_verlauf:vor=nach',
            'eigenverbrauch:fakten:tageswert=gespeichert', 'eigenverbrauch:jahr_verlauf:vor=nach',
            'gesamtverbrauch:fakten:tageswert=gespeichert', 'gesamtverbrauch:jahr_verlauf:vor=nach',
        ),
        ('M10', 'netz', 'SA', 'I2'): (
            'eigenverbrauch:cockpit_monat=Σtage', 'eigenverbrauch:fakten_tw=Σtage',
            'eigenverbrauch:jahr_verlauf=Σtage', 'gesamtverbrauch:cockpit_monat=Σtage',
            'gesamtverbrauch:fakten_tw=Σtage', 'gesamtverbrauch:jahr_verlauf=Σtage',
        ),
        ('M10', 'netz', 'SA', 'I3'): (
            'autarkie:cockpit_monat', 'autarkie:fakten_tw', 'eigenverbrauch:cockpit_monat',
            'eigenverbrauch:fakten_tw', 'gesamtverbrauch:cockpit_monat', 'gesamtverbrauch:fakten_tw',
        ),
        ('M10', 'sonstiges', 'S3', 'I2'): (
            'erzeugung:fakten:tageswert=gespeichert', 'erzeugung:jahr_verlauf:vor=nach',
            'hinter_zaehler:fakten:tageswert=gespeichert', 'hinter_zaehler:jahr_verlauf:vor=nach',
            'verbrauch:fakten:tageswert=gespeichert', 'verbrauch:jahr_verlauf:vor=nach',
        ),
        ('M10', 'sonstiges', 'SA', 'I1'): ('erzeugung:fakten_tw', 'verbrauch:fakten_tw',),
        ('M10', 'sonstiges', 'SA', 'I2'): (
            'erzeugung:cockpit_monat=Σtage', 'erzeugung:fakten_tw=Σtage', 'erzeugung:jahr_verlauf=Σtage',
            'verbrauch:cockpit_monat=Σtage', 'verbrauch:fakten_tw=Σtage', 'verbrauch:jahr_verlauf=Σtage',
        ),
        ('M10', 'sonstiges', 'SA', 'I3'): (
            'erzeugung:cockpit_monat', 'erzeugung:fakten_tw', 'hinter_zaehler:fakten_tw', 'verbrauch:cockpit_monat',
            'verbrauch:fakten_tw',
        ),
        ('M10', 'sonstiges', 'SA', 'I4'): ('geraet:cockpit_monat:BHKW', 'geraet:cockpit_monat:Sauna',),
        ('M10', 'sonstiges', 'SA', 'I6'): (
            'erzeugung:cockpit_jahr', 'erzeugung:cockpit_monat', 'erzeugung:fakten_tw', 'erzeugung:jahr_verlauf',
            'verbrauch:cockpit_jahr', 'verbrauch:cockpit_monat', 'verbrauch:fakten_tw', 'verbrauch:jahr_verlauf',
        ),
        ('M02', 'emob', 'SA', 'I2'): (
            'heimladung:cockpit_monat=Σtage', 'wallbox:fakten_tw=Σtage', 'wallbox:jahr_verlauf=Σtage',
        ),
        ('M02', 'emob', 'SA', 'I3'): (
            'heim_pv:cockpit_monat', 'heim_pv:fakten_tw', 'heimladung:cockpit_monat', 'heimladung:fakten_tw',
            'wallbox:fakten_tw',
        ),
        ('M02', 'emob', 'SA', 'I6'): ('wallbox:fakten_tw', 'wallbox:jahr_verlauf'),
        ('M08', 'emob', 'SA', 'I2'): (
            'heimladung:cockpit_monat=Σtage', 'wallbox:fakten_tw=Σtage', 'wallbox:jahr_verlauf=Σtage',
        ),
        ('M08', 'emob', 'SA', 'I3'): (
            'heim_pv:cockpit_monat', 'heim_pv:fakten_tw', 'heimladung:cockpit_monat', 'heimladung:fakten_tw',
            'wallbox:fakten_tw',
        ),
        ('M08', 'emob', 'SA', 'I6'): ('wallbox:fakten_tw', 'wallbox:jahr_verlauf'),
        ('M09', 'emob', 'SA', 'I3'): (
            'dienst_netz:fakten_tw', 'dienst_pv:fakten_tw', 'heim_netz:cockpit_monat', 'heim_netz:fakten_tw',
            'heim_pv:cockpit_monat', 'heim_pv:fakten_tw', 'heimladung:cockpit_monat', 'heimladung:fakten_tw',
        ),
        ('M06', 'wp', 'SA', 'I3'): (
            'heizung:cockpit_monat', 'heizung:fakten_tw', 'kaelte:cockpit_monat', 'modus_heizen:cockpit_monat',
            'modus_heizen:fakten_tw', 'modus_kuehlen:cockpit_monat', 'modus_kuehlen:fakten_tw', 'strom:fakten_tw',
            'strom_heizen:fakten_tw', 'strom_warmwasser:fakten_tw', 'waerme:cockpit_monat', 'waerme:fakten_tw',
            'warmwasser:fakten_tw',
        ),
        ('M06', 'wp', 'SA', 'I4'): ('waerme:cockpit_monat:Klima',),
        ('M07', 'wp', 'SA', 'I1'): ('strom:jahr_verlauf',),
        ('M07', 'wp', 'SA', 'I2'): ('strom:jahr_verlauf=Σtage',),
        ('M07', 'wp', 'SA', 'I5'): ('null:strom:jahr_verlauf',),
        ('M07', 'wp', 'S3', 'I2'): ('strom:jahr_verlauf:vor=nach',),
    },
    'KANDIDAT-EMOB-LAUFEND-NETZ': {
    },
    # KANDIDAT-WP-ACHSEN-OHNE-ABSCHLUSS (N-630): seit HA-Bauform E4d geheilt (die WP-Gruppe aus den Kanälen in Monats-Fakten
    # und Cockpit → Monat) — keine Zelle mehr; die Sichten ohne Kanäle (SA) stehen unter OHNE-ABSCHLUSS (Lesart 1).
    'KANDIDAT-WP-ACHSEN-OHNE-ABSCHLUSS': {
    },
    # E4E-DIENSTLICHE-LADEKOSTEN (N-633): seit HA-Bauform E4e geheilt (Cockpit → Monat ohne Monats-Fakt zieht die
    # dienstlichen Ladekosten wie die Fakten ab: Mengen der einen Entscheidung, Tarif und Bewertung der Schicht) — keine
    # Zelle mehr. Die Teiltag-Sicht `kosten:jahr_verlauf` derselben Zelle bleibt unter TEILTAG-ZWEI-MONATSGRENZEN.
    'E4E-DIENSTLICHE-LADEKOSTEN': {
    },
}


#: **Soll unklar je Menge** — ``(Form, Größe, Menge) → Grund``: alle Zellen dieser Menge werden gemessen und
#: gezeigt, nicht bewertet (Fachfragen Wärme/Klima entscheidet der Master).
_U_W1 = ("W1 (Gesamtstrom + Gesamtwärme, Betriebsart nur als Etikett) — entschieden (Master, 06.10.2026, Bauplan §8a "
         "„Etikett“): der Betriebsmodus teilt den STROM je Stunde auf, die Wärme nicht (ein Wärmezähler ohne "
         "Funktionstrennung bleibt Gesamtwärme, Kennzahl nur gesamt). Soll Strom je Betriebsart: ohne Abschluss aus dem "
         "abgeleiteten Kanal, nach dem Abschluss derselbe Wert über den Kanal-Split (HA-Bauform E4d, H-1) — Juni "
         "Heizen 198 · Warmwasser 18 (Abdeckung 720 h). Die Zellen bleiben gemessen mit Haltewert; Heizwärme: "
         "Monats-Fakten 0, Cockpit → Monat keine, Community die ganze Wärme als Heizwärme (Community-Zuordnung: "
         "Haltewert/Beobachtung, §8a)")
_U_W5_SPLIT = ("W5 (nur Gesamtstrom und Gesamtwärme, beide 0): ohne Heiz-/Warmwasser-Zähler legt K1–K5 keine "
               "Aufteilung fest — ob sie 0 oder „keine Angabe“ heißt, ist eine Fachfrage")
_U_KLIMA_JAZ = ("Arbeitszahl eines Klimageräts mit Heiz- UND Kühlbetrieb: ob die Geräte-Zahl Kälte einrechnet oder "
                "nur die Heizseite nennt, legen K1–K5 nicht fest (gemessen 3,0 = Heizen 54/18 = Kühlen 108/36)")
SOLL_UNKLAR_MENGE: dict[tuple[str, str, str], str] = {
    ("M05", "wp", "heizung"): _U_W1, ("M05", "wp", "warmwasser"): _U_W1,
    ("M05", "wp", "modus_heizen"): _U_W1, ("M05", "wp", "modus_warmwasser"): _U_W1,
    ("M07", "wp", "heizung"): _U_W5_SPLIT, ("M07", "wp", "warmwasser"): _U_W5_SPLIT,
}

#: ``(Form, Größe, Weg, Invariante, Sicht) → Grund``: die Regel legt das Soll dieser Sicht nicht fest.
SOLL_UNKLAR: dict[tuple[str, str, str, str, str], str] = {}

#: Wie ``test_pv_achse_matrix._U_SA_VOR``: ohne HA hat ein vergangener Monat vor dem Abschluss in Cockpit →
#: Monat keine Werte (N-472), Cockpit → Jahr → Verlauf zeigt ihn aus den Tageswerten (N-121) — nicht entschieden.
_U_SA_VOR = (
    "Cockpit → Monat sammelt die Tagesebene NUR im laufenden Monat (aktueller_monat/__init__.py, N-472); ohne HA "
    "hat ein vergangener Monat vor dem Abschluss dort keine Werte, Cockpit → Jahr → Verlauf zeigt ihn aus den "
    "Tageswerten (N-121) — ob „nichts verschwindet“ hier gilt, ist nicht entschieden (wie in der PV-Matrix)."
)


def _zerlege(sicht: str) -> tuple[str, str, str]:
    """``(menge, sicht, art)`` einer Zellen-Sicht; ``art`` ∈ monat · tage · vor · tw · null."""
    teile = sicht.split(":")
    art = "monat"
    if teile[0] == "null":
        teile, art = teile[1:], "null"
    menge = teile[0]
    s = teile[1] if len(teile) > 1 else ""
    if s.endswith("=Σtage"):
        s, art = s[: -len("=Σtage")], "tage"
    if len(teile) > 2 and teile[2] == "vor=nach":
        art = "vor"
    if s == "fakten" and len(teile) > 2 and teile[2] == "tageswert=gespeichert":
        s, art = "fakten_tw", "vor"
    return menge, s, art


def _soll_unklar(fid, groesse, weg, inv, sicht: str) -> Optional[str]:
    k = (fid, groesse, weg, inv, sicht)
    if k in SOLL_UNKLAR:
        return SOLL_UNKLAR[k]
    menge, s, art = _zerlege(sicht)
    if (fid, groesse, menge) in SOLL_UNKLAR_MENGE:
        return SOLL_UNKLAR_MENGE[(fid, groesse, menge)]
    if weg == "S3" and art == "vor" and s == "cockpit_monat":
        return _U_SA_VOR
    if fid == "M06" and groesse == "wp" and sicht.startswith("cockpit_monat:jaz:Klima"):
        return _U_KLIMA_JAZ
    return None


#: HA-Bauform E4a-2 — die neue Form W2-E (Entweder-oder, Markierung bei NEUEN Formen, Freigabe Master 06.10.2026):
#: gemessen 06.10.2026 nach dem Umschalten, Klassifikation im Bericht ``opus-berichte/HA-BAUFORM-E4A2.md``.
URSACHE.update({
    "W2-E-KATALOG": Ursache(
        "Katalog der Achsen-Matrix — seit HA-Bauform E4c berichtigt (die Menge „verbrauch“ nur bei einem Gerät, das "
        "kein Erzeuger ist); keine Zelle mehr",
        "Der Katalog liest das zweite Feld der Ersatzgruppe eines Sonstiges-Erzeugers (`verbrauch_sonstig_kwh`) als "
        "Verbrauch und erwartet 0; im Erzeuger ist es der Ersatz der Erzeugung (`sonstiges_feld_reihenfolge"
        "('erzeuger')`), die Sichten führen keinen Verbrauch",
    ),
    "W2-BESTAND-SPEICHER": Ursache(
        "HA-Bauform S3/S5 (gespeicherte Tageszeilen)",
        "Die Tageszeile schreibt weiter `aggregate_day` (Bestandspfad, Ersatzgruppe am Ausfalltag B mit 6,24); der "
        "Kanal ersetzt sie nur beim Lesen der Bilanz-Gruppe. Die Sicht liest den gespeicherten Schlüssel roh",
    ),
    "W2-SA-BESTAND": Ursache(
        "Lesart 1 (Bauplan §3b) — Standalone ohne Kanäle",
        "Der Standalone-Datenstand hat keine Kanäle: die Tage rechnet der Bestand (Ersatzgruppe am Ausfalltag B mit "
        "6,24 statt Weg 2 A 0 / 12,0)",
    ),
})
URSACHE["E4E-DIENSTLICHE-LADEKOSTEN"] = Ursache(
    "HA-Bauform E4e (Preis und Kosten) — seit E4e geheilt (Cockpit → Monat ohne Monats-Fakt rechnet den Posten wie die "
    "Monats-Fakten, 10,44 € in beiden); keine Zelle mehr",
    "Seit E4c führen die Monats-Fakten des laufenden Monats den Dienstwagen aus den Kanälen und ziehen seine "
    "dienstlichen Ladekosten ab (Jahr-Verlauf 10,44 €); Cockpit → Monat ohne Monats-Fakt liest die dienstlichen "
    "Ladekosten nur aus dem Fakt (`aktueller_monat/finanzen.py`) und zieht sie im Monat ohne Abschluss nicht ab "
    "(12,24 €). Nach dem Abschluss nennen beide dasselbe. Geld — nicht Teil von E4c",
)
_ROT_W2: dict[str, dict[tuple[str, str, str, str], tuple[str, ...]]] = {
    'OHNE-ABSCHLUSS': {
        ('W2-E', 'netz', 'S3', 'I2'): ('autarkie:fakten:tageswert=gespeichert', 'autarkie:jahr_verlauf:vor=nach', 'eigenverbrauch:fakten:tageswert=gespeichert', 'eigenverbrauch:jahr_verlauf:vor=nach', 'eigenverbrauch:Σtage_juni=fakten', 'gesamtverbrauch:fakten:tageswert=gespeichert', 'gesamtverbrauch:jahr_verlauf:vor=nach', 'gesamtverbrauch:Σtage_juni=fakten'),
        ('W2-E', 'netz', 'SA', 'I2'): ('eigenverbrauch:cockpit_monat=Σtage', 'eigenverbrauch:fakten_tw=Σtage', 'eigenverbrauch:jahr_verlauf=Σtage', 'gesamtverbrauch:cockpit_monat=Σtage', 'gesamtverbrauch:fakten_tw=Σtage', 'gesamtverbrauch:jahr_verlauf=Σtage'),
        ('W2-E', 'netz', 'SA', 'I3'): ('autarkie:cockpit_monat', 'autarkie:fakten_tw', 'eigenverbrauch:cockpit_monat', 'eigenverbrauch:fakten_tw', 'gesamtverbrauch:cockpit_monat', 'gesamtverbrauch:fakten_tw'),
        ('W2-E', 'sonstiges', 'SA', 'I4'): ('geraet:cockpit_monat:BHKW',),
        ('W2-E', 'sonstiges', 'SA', 'I6'): ('erzeugung:cockpit_jahr', 'erzeugung:cockpit_monat', 'erzeugung:fakten_tw', 'erzeugung:jahr_verlauf'),
        ('W2-E', 'sonstiges', 'SA', 'I1'): ('erzeugung:fakten_tw',),
        ('W2-E', 'sonstiges', 'SA', 'I2'): (
            'erzeugung:cockpit_monat=Σtage', 'erzeugung:fakten_tw=Σtage', 'erzeugung:jahr_verlauf=Σtage',
        ),
        ('W2-E', 'sonstiges', 'SA', 'I3'): (
            'erzeugung:cockpit_monat', 'erzeugung:fakten_tw', 'hinter_zaehler:fakten_tw',
        ),
        ('W2-E', 'sonstiges', 'S3', 'I2'): (
            'erzeugung:fakten:tageswert=gespeichert', 'erzeugung:jahr_verlauf:vor=nach',
            'erzeugung:Σtage_juni=fakten', 'hinter_zaehler:fakten:tageswert=gespeichert',
            'hinter_zaehler:jahr_verlauf:vor=nach',
        ),
    },
    'W2-BESTAND-SPEICHER': {
        ('W2-E', 'sonstiges', 'HA', 'I4'): ('geraet:tag:BHKW',),
    },
    'W2-E-KATALOG': {
    },
    'W2-SA-BESTAND': {
        ('W2-E', 'netz', 'SA', 'I3'): ('autarkie:tag', 'eigenverbrauch:tag', 'gesamtverbrauch:tag'),
        ('W2-E', 'sonstiges', 'SA', 'I4'): ('geraet:tag:BHKW',),
        ('W2-E', 'sonstiges', 'SA', 'I3'): ('erzeugung:tag',),
    },
    'TEILTAG-ZWEI-MONATSGRENZEN': {
        ('W2-E', 'netz', 'HA', 'I1'): (
            'autarkie:fakten_tw', 'autarkie:jahr_verlauf', 'eigenverbrauch:fakten_tw', 'eigenverbrauch:jahr_verlauf',
            'gesamtverbrauch:fakten_tw', 'gesamtverbrauch:jahr_verlauf', 'netzbezug:fakten_tw',
            'netzbezug:jahr_verlauf',
        ),
        ('W2-E', 'netz', 'HA', 'I2'): ('gesamtverbrauch:fakten_tw=Σtage', 'gesamtverbrauch:jahr_verlauf=Σtage'),
        ('W2-E', 'sonstiges', 'HA', 'I1'): ('erzeugung:fakten_tw', 'erzeugung:jahr_verlauf'),
    },
}
for _u, _zellen in _ROT_W2.items():
    ROT.setdefault(_u, {}).update(_zellen)


#: Sicht „Hub-Verlauf" (Vorhaben nach 4.1.3) — gemessen 08.10.2026 gegen HEAD `beef97cf`, Bericht
#: ``~/.claude/plans/opus-berichte/HUB-VERLAUF-MATRIX.md``. ⭐ **Bau N-641 … N-645 (09.10.2026, Bericht
#: ``opus-berichte/HUB-VERLAUF-BAU.md``):** die Verläufe lesen die bewertete ``monatsreihe`` der Route — 39 der 45 Zellen
#: sind mit dem Bau geheilt, die übrigen sechs (M05, W1, Sicht ``waerme:*``) mit der Richter-Korrektur: die Sicht liest
#: die gezeichnete Wärme (Nachbildung ``waerme``) statt Heizung + Warmwasser der Zeile. Das Register ist leer.
_ROT_HUB: dict[str, dict[tuple[str, str, str, str], tuple[str, ...]]] = {}
for _u, _zellen in _ROT_HUB.items():
    ROT.setdefault(_u, {}).update(_zellen)


def _baue_bekannt() -> dict:
    sichten: dict = {}
    kennungen: dict = {}
    for kennung, zellen in ROT.items():
        for zelle, rote in zellen.items():
            sichten.setdefault(zelle, set()).update(rote)
            kennungen.setdefault(zelle, []).append(kennung)
    return {zelle: (frozenset(sichten[zelle]), " + ".join(kennungen[zelle]),
                    " ‖ ".join(f"{k}: {URSACHE[k].grund}" for k in kennungen[zelle])) for zelle in sichten}


BEKANNT = _baue_bekannt()

WEGE = ("HA", "S1", "S2", "SA", "S3")
INVARIANTEN = ("I1", "I2", "I3", "I4", "I5", "I6")


def _hat_zelle(form: am.Form, groesse: str, inv: str) -> bool:
    if inv == "I4" and groesse in ("netz", "preis"):
        return False
    return True


def _zellen():
    for fid, form in am.MATRIX_FORMEN.items():
        for groesse in form.groessen:
            for weg in WEGE:
                for inv in INVARIANTEN:
                    if _hat_zelle(form, groesse, inv):
                        yield fid, groesse, weg, inv
    # Sicht „Hub-Verlauf": eigene Zellen je Typ, den die Form trägt (nach den bestehenden, deren IDs bleiben).
    for fid, form in am.MATRIX_FORMEN.items():
        for groesse, typen in HUB_GROESSEN.items():
            if any(form.typ(t) for t in typen):
                for weg in HUB_WEGE:
                    for inv in HUB_INVARIANTEN:
                        yield fid, groesse, weg, inv


def _zellen_params():
    for fid, groesse, weg, inv in _zellen():
        b = BEKANNT.get((fid, groesse, weg, inv))
        marks = ()
        if b is not None:
            marks = (pytest.mark.xfail(strict=True, raises=BekannterMangel, reason=f"{b[1]}: {b[2]}"),)
        yield pytest.param(fid, groesse, weg, inv, marks=marks, id=f"{fid}-{groesse}-{weg}-{inv}")


def _rot(fid, groesse, weg, inv, zellen: list[Zelle]) -> dict[str, Zelle]:
    return {x.sicht: x for x in zellen
            if x.status == "rot" and not _soll_unklar(fid, groesse, weg, inv, x.sicht)}


def _bericht(zellen) -> str:
    return "\n".join(f"  {x.sicht}: ist {x.ist} · soll {x.soll} {('· ' + x.notiz) if x.notiz else ''}"
                     for x in zellen.values())


@pytest.mark.parametrize("fid,groesse,weg,inv", list(_zellen_params()))
async def test_zelle(fid, groesse, weg, inv, _matrix_ordner):
    m = await _messung(fid, _teil(weg), _matrix_ordner)
    zellen = bewerte(fid, groesse, weg, inv, m)
    assert zellen, "Eine Zelle ohne Prüfung misst nichts."
    rot = _rot(fid, groesse, weg, inv, zellen)
    b = BEKANNT.get((fid, groesse, weg, inv))
    erwartet = b[0] if b else frozenset()
    if set(rot) != set(erwartet):
        raise AssertionError(
            f"{fid} {groesse} {weg} {inv}: rote Sichten weichen vom Register ab.\n"
            f" neu rot: {sorted(set(rot) - erwartet)}\n geheilt (Markierung entfernen): {sorted(erwartet - set(rot))}\n"
            + _bericht(rot))
    if rot:
        raise BekannterMangel(f"{b[1]} — {b[2]}\n" + _bericht(rot))


async def test_jede_regel_trifft_noch(_matrix_ordner):
    """Jeder „Soll unklar"-Eintrag (``SOLL_UNKLAR``, ``SOLL_UNKLAR_MENGE``) trifft noch eine gemessene Sicht —
    ein Eintrag, der nichts mehr trifft, ist tot und gehört entfernt."""
    getroffen: set = set()
    for fid, groesse, weg, inv in _zellen():
        m = await _messung(fid, _teil(weg), _matrix_ordner)
        for x in bewerte(fid, groesse, weg, inv, m):
            k = (fid, groesse, weg, inv, x.sicht)
            menge, s, _art = _zerlege(x.sicht)
            if k in SOLL_UNKLAR:
                getroffen.add(("su", k))
            if (fid, groesse, menge) in SOLL_UNKLAR_MENGE:
                getroffen.add(("sum", (fid, groesse, menge)))
    tot = ([("su", k) for k in SOLL_UNKLAR if ("su", k) not in getroffen]
           + [("sum", k) for k in SOLL_UNKLAR_MENGE if ("sum", k) not in getroffen])
    assert not tot, tot


def _haltewert_gleich(ist, gehalten) -> bool:
    if ist is None or gehalten is None:
        return ist is None and gehalten is None
    return abs(float(ist) - float(gehalten)) <= 1e-6


@pytest.mark.parametrize("schluessel", sorted(ACHSEN_HALTEWERTE), ids=lambda s: "-".join(s))
async def test_soll_unklar_haltewert(schluessel, _matrix_ordner):
    """Haltewert (HA-Bauform E0): eine „Soll unklar"-Sicht misst, was am 05.10.2026 gemessen wurde
    (``matrix_haltewerte.ACHSEN_HALTEWERTE``) — der Umbau ändert sie nicht still. Kein Soll, ein Festwert."""
    fid, groesse, weg, inv, sicht = schluessel
    assert _soll_unklar(fid, groesse, weg, inv, sicht), f"{schluessel}: nicht mehr „Soll unklar“ — Haltewert entfernen"
    m = await _messung(fid, _teil(weg), _matrix_ordner)
    zellen = {x.sicht: x for x in bewerte(fid, groesse, weg, inv, m)}
    assert sicht in zellen, f"{schluessel} misst nichts mehr"
    ist = zellen[sicht].ist
    assert _haltewert_gleich(ist, ACHSEN_HALTEWERTE[schluessel]), (
        f"{schluessel}: gemessen {ist}, festgehalten {ACHSEN_HALTEWERTE[schluessel]}")


async def test_jede_soll_unklar_sicht_hat_haltewert(_matrix_ordner):
    """Jede gemessene „Soll unklar"-Sicht hat einen Haltewert — eine neue (andere Messung, neue Regel) ohne
    Eintrag ist rot, damit sie nicht ungehalten durch den Umbau läuft."""
    ohne = []
    for fid, groesse, weg, inv in _zellen():
        m = await _messung(fid, _teil(weg), _matrix_ordner)
        for x in bewerte(fid, groesse, weg, inv, m):
            k = (fid, groesse, weg, inv, x.sicht)
            if _soll_unklar(*k) and k not in ACHSEN_HALTEWERTE:
                ohne.append(k)
    assert not ohne, ohne


def test_hub_leser_nachbildung_steht_im_quelltext():
    """Sicht „Hub-Verlauf": die Nachbildung der Frontend-Leser (`achsen_matrix.miss_hub`) liest dieselben Schlüssel wie
    die Komponente — jeder nachgebildete Ausdruck steht wörtlich in seiner Datei (`achsen_matrix.HUB_LESER_QUELLTEXT`).
    Wird ein Leser geändert, ist diese Probe rot, bis die Nachbildung (und ggf. das Register) mitgezogen ist."""
    wurzel = Path(__file__).resolve().parents[2] / "frontend" / "src"
    fehlt = [(datei, ausdruck) for datei, ausdruecke in am.HUB_LESER_QUELLTEXT.items()
             for ausdruck in ausdruecke if ausdruck not in (wurzel / datei).read_text(encoding="utf-8")]
    assert not fehlt, fehlt


def test_register_zeigt_nur_auf_bestehende_zellen():
    zellen = set(_zellen())
    assert set(BEKANNT) <= zellen
    assert {k[:4] for k in SOLL_UNKLAR} <= zellen


def test_jede_auspraegung_steht_in_einer_form():
    """Auftrag: jede Ausprägung (N1 … T3) steht in mindestens einer Form."""
    soll = {"N1", "N2", "N3", "P1", "P2", "P3", "P4", "W1", "W2", "W3", "W4", "W5", "E1", "E2", "E3", "E4",
            "S1", "S2", "S3", "T1", "T2", "T3"}
    ist = {a for f in am.FORMEN.values() for a in f.ausp}
    assert soll <= ist, sorted(soll - ist)
