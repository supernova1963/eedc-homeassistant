"""Zusatzspalten der Tages-Tabelle (*Auswertungen → Tabellen*, Auftrag «Tabellen-Spalten» 28.10.2026).

Je Tag eines Fensters die Spalten E-Mobilität und Wärmepumpen-Zähler, die die Tagesansicht schon zeigt — **gebündelt**
über das Fenster gelesen (kein Aufruf je Tag), mit denselben Lesern und Regeln wie die Einzeltag-Sicht:

* **Wallbox-Ladung** — ``komponenten_der_tage`` (die eine Mischung, E-Mob-Gruppe) wie ``emob_heute`` im Tag-Detail
  (``tag.py::_emob_heute_wallbox``), als Betrag (K4-N1: der Leistungspfad trägt das Vorzeichen der Senke).
* **E-Auto km / Fahrverbrauch** — ``kanal_stunden.fahrt_der_tage`` (Bereichs-Variante von ``fahrt_je_tag``).
* **Ladevorgänge** — ``kanal_stunden.zustand_wechsel_der_tage`` (Bereichs-Variante von ``zustand_wechsel_je_tag``,
  Übergänge nach «lädt» an der Wallbox, ``zustands_kanon.WECHSEL_FELDER``).
* **WP-Starts / Betriebszeit** — ``TagesZusammenfassung.komponenten_starts`` mit der Tagessumme von *Cockpit → Monat*
  (``wp_zaehler_tagessumme``: aktive Wärmepumpen des Monats, nur Werte > 0); die Betriebszeit in ganzen Minuten
  (Style-Guide C3: Dauern nie dezimal).
* **WP-Wärme, Kälte, Strom Heizbetrieb/Warmwasserbetrieb/Kühlen/Lüften/Entfeuchten/nicht aufgeteilt** (Auftrag
  29.10.2026, Heiz-/Warmwasserbetrieb seit 3.11.2026, nur auf Anfrage
  ``mit_waerme``) — die Tagesreihe von *Cockpit → Monat* (``waerme_verlauf.lade_waerme_verlauf``), EIN Aufruf über das
  Fenster, Werte und Rundung wie die Route ``waerme-verlauf``. Teuer (je Tag die Betriebsart-Zähler); der Client fragt
  nur, wenn eine dieser Spalten eingeblendet ist. Ebenso die **Zusatzheizung** (``waerme_verlauf.lade_heizstab_je_tag``,
  derselbe Bereichs-Leser und dasselbe Fenster, Werte wie *Cockpit → Tag*).

Summiert wird über die **privaten** Geräte (``ist_dienstlich`` nein) — dieselbe Menge wie die Monatsspalte mit demselben
Schlüssel (Monats-Fakten «ohne Dienstwagen», private Wallboxen). Ein Tag ohne Wert trägt ``None`` (keine 0).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.investition import Investition


def wp_zaehler_tagessumme(komp: Optional[dict], feld: str, inv_ids: set[str]) -> float:
    """Summe eines Zähler-Felds (``wp_starts_anzahl``/``wp_betriebsstunden``) über die gegebenen Wärmepumpen an einem
    Tag — nur Zahlen > 0 (Issue #169/#238). Die eine Stelle für *Cockpit → Monat* (``aktueller_monat/waerme.py``) und
    die Tages-Tabelle; bis 28.10.2026 stand sie als Hilfsfunktion in der Monatsroute."""
    feld_map = (komp or {}).get(feld) or {}
    tag_sum = 0.0
    for inv_id_str, wert in feld_map.items():
        if inv_id_str in inv_ids and isinstance(wert, (int, float)) and wert > 0:
            tag_sum += float(wert)
    return tag_sum


def _summe(werte: list[float], stellen: int) -> Optional[float]:
    return round(sum(werte), stellen) if werte else None


def _wp_zaehler(tz_pro_tag: Mapping[date, Any], invs: list) -> dict[date, dict]:
    """Starts und Betriebszeit je Tag aus der Tageszeile — Tagessumme wie *Cockpit → Monat*, ``None`` ohne Wert > 0."""
    wps = [i for i in invs if i.typ == "waermepumpe"]
    out: dict[date, dict] = {}
    if not wps:
        return out
    for tag, tz in tz_pro_tag.items():
        komp = getattr(tz, "komponenten_starts", None)
        if not komp:
            continue
        ids = {str(i.id) for i in wps if i.ist_aktiv_im_monat(tag.year, tag.month)}
        starts = wp_zaehler_tagessumme(komp, "wp_starts_anzahl", ids)
        stunden = wp_zaehler_tagessumme(komp, "wp_betriebsstunden", ids)
        out[tag] = {
            "wp_starts": int(starts) if starts > 0 else None,
            "wp_betriebszeit_min": int(round(stunden * 60)) if stunden > 0 else None,
        }
    return out


async def _emob(db: AsyncSession, anlage, invs: list, von: date, bis: date) -> dict[date, dict]:
    """Wallbox-Ladung, E-Auto km/Fahrverbrauch und Ladevorgänge je Tag über die privaten, am Tag aktiven Geräte."""
    from backend.core import zustands_kanon as zk
    from backend.core.investition_parameter import ist_dienstlich
    from backend.services.energie_profil.kanal_stunden import (
        GRUPPE_EMOB, fahrt_der_tage, komponenten_der_tage, zustand_wechsel_der_tage,
    )

    privat = {str(i.id): i for i in invs if i.typ in ("wallbox", "e-auto") and not ist_dienstlich(i)}
    if not privat:
        return {}
    wallboxen = [i for i, inv in privat.items() if inv.typ == "wallbox"]
    autos = [i for i, inv in privat.items() if inv.typ == "e-auto"]
    komp = await komponenten_der_tage(db, anlage.id, von, bis, gruppen=(GRUPPE_EMOB,)) if wallboxen else {}
    fahrt = await fahrt_der_tage(db, anlage, privat, von, bis) if autos else {}
    wechsel_feld = zk.LADEZUSTAND
    wechsel = await zustand_wechsel_der_tage(
        db, anlage, privat, von, bis, typ="wallbox", feld=wechsel_feld,
        wert=zk.WECHSEL_FELDER[("wallbox", wechsel_feld)],
    ) if wallboxen else {}

    out: dict[date, dict] = {}
    for tag in sorted(set(komp) | set(fahrt) | set(wechsel)):
        aktiv_wb = [i for i in wallboxen if privat[i].ist_aktiv_an(tag)]
        aktiv_auto = [i for i in autos if privat[i].ist_aktiv_an(tag)]
        k = komp.get(tag) or {}
        f = fahrt.get(tag) or {}
        w = wechsel.get(tag) or {}
        out[tag] = {
            # Betrag wie `tag.py::_betrag` (K4-N1): Zählerpfad positiv, Leistungspfad negativ im selben JSON.
            "wallbox_ladung": _summe([abs(k[f"wallbox_{i}"]) for i in aktiv_wb
                                      if k.get(f"wallbox_{i}") is not None], 3),
            "eauto_km": _summe([f[i]["km"] for i in aktiv_auto if "km" in f.get(i, {})], 1),
            "eauto_fahrverbrauch": _summe([f[i]["verbrauch_kwh"] for i in aktiv_auto
                                           if "verbrauch_kwh" in f.get(i, {})], 3),
            "ladevorgaenge": _summe([float(w[i]) for i in aktiv_wb if i in w], 0),
        }
    return out


#: Betriebsart-Strom des Tagesstapels → Spalte; Wert nur mit Aufteilung (``hat_split``), sonst ``None``.
#: Heizbetrieb/Warmwasserbetrieb (Zusage #446, 3.11.2026) heißen bewusst anders als die Monatsspalten
#: ``wp_strom_heizen``/``wp_strom_warmwasser``: dort die getrennten Zähler (Summanden des Gesamtstroms), hier die
#: Teilmenge aus den Betriebsart-Stunden — Namen wie die HA-Export-Sensoren «Strom Heiz-/Warmwasserbetrieb».
_STAPEL_SPALTEN = {
    "wp_strom_heizbetrieb": "heizen_kwh",
    "wp_strom_warmwasserbetrieb": "warmwasser_kwh",
    "wp_strom_kuehlen": "kuehlen_kwh",
    "wp_strom_lueften": "lueften_kwh",
    "wp_strom_entfeuchten": "entfeuchten_kwh",
    "wp_strom_nicht_aufgeteilt": "nicht_aufgeteilt_kwh",
}


async def _waerme(db: AsyncSession, anlage, invs: list, von: date, bis: date) -> dict[date, dict]:
    """WP-Wärme, Kälte und Betriebsart-Strom je Tag aus der Tagesreihe von *Cockpit → Monat* — derselbe Leser mit
    derselben Investitions-Menge wie ``get_waerme_verlauf``, EIN Aufruf über ``[von, bis]``. Rundung und «nur mit
    Aufteilung» wie dort (Alles-oder-nichts je Tag); ein Tag ohne Zeile im Verlauf trägt nichts.

    Dazu die **Zusatzheizung** (Auftrag 29.10.2026, Option (b) des Halts H1): ``lade_heizstab_je_tag`` — derselbe
    Bereichs-Leser und dasselbe Fenster wie die Wärme des Verlaufs, Σ über die Geräte, auf zwei Stellen wie *Cockpit →
    Tag* (``waerme_klima_block.ohne_zusatzheizung_felder``); ein Tag ohne Heizstab-Zähler trägt nichts."""
    from backend.services.energie_profil.waerme_verlauf import lade_heizstab_je_tag, lade_waerme_verlauf

    by_id = {str(i.id): i for i in invs}
    zeilen = await lade_waerme_verlauf(db, anlage, by_id, von, bis)
    out: dict[date, dict] = {}
    for z in zeilen:
        werte = {"wp_waerme": z.waerme_kwh, "wp_kaelte": z.kaelte_kwh}
        for spalte, feld in _STAPEL_SPALTEN.items():
            werte[spalte] = round(getattr(z.stapel, feld), 2) if z.stapel.hat_split else None
        out[z.datum] = werte
    for tag, kwh in (await lade_heizstab_je_tag(db, anlage, by_id, von, bis)).items():
        out.setdefault(tag, {})["wp_heizstab"] = round(kwh, 2)
    return out


async def lade_tabellen_zusatz(db: AsyncSession, anlage, tz_pro_tag: Mapping[date, Any], von: date,
                               bis: date, *, mit_waerme: bool = False) -> dict[date, dict]:
    """``{datum: {spalte: wert}}`` der Zusatzspalten für ``[von, bis]`` — eine Abfrage der Investitionen, je Größe ein
    Bereichs-Leser. Ohne Wallbox/E-Auto bzw. Wärmepumpe keine weitere Abfrage; die Wärmepumpen-Tagesreihe nur mit
    ``mit_waerme`` (ohne ihn bleibt die Antwort wie vor dem 29.10.2026)."""
    invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all())
    out: dict[date, dict] = defaultdict(dict)
    for tag, werte in _wp_zaehler(tz_pro_tag, invs).items():
        out[tag].update(werte)
    if any(i.typ in ("wallbox", "e-auto") for i in invs):
        for tag, werte in (await _emob(db, anlage, invs, von, bis)).items():
            out[tag].update(werte)
    if mit_waerme:
        for tag, werte in (await _waerme(db, anlage, invs, von, bis)).items():
            out[tag].update(werte)
    return dict(out)
