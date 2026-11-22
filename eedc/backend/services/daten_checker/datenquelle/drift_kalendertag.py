"""Daten-Checker «Abweichung zu Home Assistant» (``drift_komponente``) — der Vergleichswert an Kanal-Tagen (Fund-Päckchen E,
N-815).

An einem Tag, an dem eedc einen Wert als Kalendertag zeigt (Wahl ``kanal`` seiner Gruppe an diesem Tag — Bilanz für
Einspeisung und Netzbezug, E-Mobilität, Wärmepumpe, Sonstiges), vergleicht die zweite Achse gegen den **Kalendertag von
Home Assistant**; an einem Bestandstag der Gruppe bleibt der Vergleich, wie er war (beide Seiten im Bestands-Fenster
``[Vortag 23:00, 23:00)``). Den Kalendertag setzt ``slot_konvention.kalendertag_aus_fenster`` aus Stunden zusammen, die
Home Assistant führt: ``Fenster(D) − Stunde [D−1 23:00, D 00:00) + Stunde [D 23:00, D+1 00:00)`` — die Randstunden aus dem
LTS-Read von D und D+1 (``lts_aggregator.KomponentenTag.erste_stunde``). Ist eine Randstunde nicht bekannt (HA führt sie
nicht, obwohl die Statistik davor läuft; D+1 nicht lesbar), wird das Gerät an diesem Tag **nicht verglichen** — kein
Ersatzwert, kein Rückfall auf das Fenster.

Lesen: die Wahl je Tag und Gruppe (``kanal_gruppen_der_tage``, nur an einer Anlage mit HA-Spiegel — ohne Spiegel gibt es
keinen Kanal-Tag mit HA-Werten), die Bilanz-Ziele der Tage (nur bei einem ``sonstige_``-Schlüssel: ein Erzeuger hinter dem
Zähler gehört zur Bilanz) und je Kanal-Tag, dessen Folgetag die Schleife nicht liest, EIN LTS-Read dieses Folgetags (seine
Randstunde Slot 0 ist 23–24 Uhr des Kanal-Tags; Entscheid Master H-E2 (a)): im Normalbetrieb einmal je Lauf — für gestern den
Tag von heute —, dazu je Lücke der Tageszeilen einer; jeder Folgetag höchstens einmal.

Die PV-Achse (``drift_tag``) bleibt beim Fenster: PV erzeugt zwischen 23 und 24 Uhr nichts, was die Schwelle (≥ 2 kWh UND
≥ 5 %) erreicht (Produktiv-Kopie: höchster Wert 0,0 kWh in 739 Nächten; ein Balkonkraftwerk mit Speicher speist höchstens
0,8 kWh je Stunde).

Schwesterdateien: ``quellen.py`` (die Prüfung, ``_DriftKontext``), ``drift_zeilen.py`` (die Zeilen).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.services.daten_checker.datenquelle.quellen import _DriftKontext

logger = logging.getLogger(__name__)


def gruppe_des_schluessels(schluessel: str, bilanz_ziele: frozenset[str] | set[str]) -> str:
    """Die Gruppe, deren Tageswahl den ``komponenten_kwh``-Schlüssel trägt: dieselbe Zuordnung wie der Text der Zeile
    (``kanal_stunden.gruppen_der_schluessel``); ein ``sonstige_``-Schlüssel unter den Bilanz-Zielen des Tages (Erzeuger
    hinter dem Zähler) kommt aus der Bilanz-Komposition (``komponenten_der_tage``, ``_ohne_bilanz``)."""
    from backend.services.energie_profil.kanal_stunden import GRUPPE_BILANZ, gruppen_der_schluessel

    if schluessel in bilanz_ziele:
        return GRUPPE_BILANZ
    return gruppen_der_schluessel([schluessel])[-1]


async def lade_kalendertag(db, ctx: "_DriftKontext") -> None:
    """Füllt ``ctx.hat_spiegel``, ``ctx.kanal_gruppen``, ``ctx.bilanz_ziele`` und ``ctx.ha_folgetag`` (``{Folgetag: Read}``
    je Kanal-Tag, dessen Folgetag keine Tageszeile im Prüffenster hat — im Normalbetrieb nur heute) — einmal je Lauf, vor der
    zweiten Achse."""
    from backend.services.kanal.konsistenz import spiegel_quellen_anzahl

    if not ctx.ha_komp_je_tag:
        return
    ctx.hat_spiegel = await spiegel_quellen_anzahl(db, ctx.anlage.id) > 0
    if not ctx.hat_spiegel:
        return
    from backend.services.energie_profil.kanal_stunden import kanal_gruppen_der_tage

    tage = sorted(ctx.ha_komp_je_tag)
    ctx.kanal_gruppen = await kanal_gruppen_der_tage(db, ctx.anlage.id, tage[0], tage[-1])
    kanal_tage = [d for d in tage if ctx.kanal_gruppen.get(d)]
    if any(k.startswith("sonstige_") for d in kanal_tage for k in ctx.ha_komp_je_tag[d]):
        from backend.services.kanal.bilanz_leser import bilanz_ziele

        ctx.bilanz_ziele = await bilanz_ziele(db, ctx.anlage.id, kanal_tage)
    # H-E2 (a): je Kanal-Tag, dessen Folgetag die Schleife nicht liest (gestern ⇒ heute; ein Tag ohne Tageszeile danach), EIN
    # Read des Folgetags — im Normalbetrieb einer je Lauf; die Menge der Folgetage liest jeden höchstens einmal.
    gelesen = {tz.datum for tz in ctx.tz_list}
    for folgetag in sorted({d + timedelta(days=1) for d in kanal_tage} - gelesen):
        ctx.ha_folgetag[folgetag] = await _lts_folgetag(ctx, folgetag)


async def _lts_folgetag(ctx: "_DriftKontext", tag: date) -> Optional[dict]:
    """Der LTS-Read des Tages nach dem letzten geprüften (heute) — nur seine Randstunde Slot 0 wird gelesen."""
    from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts

    invs_by_id = {str(inv.id): inv for inv in ctx.alle_invs if inv.ist_aktiv_an(tag)}
    try:
        return await get_komponenten_tageskwh_lts(ctx.anlage, invs_by_id, tag, **ctx.wechsel_kw)
    except Exception as e:  # noqa: BLE001 — wie die Achse 1: nicht gelesen ist kein Wert (#311)
        logger.debug(f"Drift-Check Anlage {ctx.anlage.id} {tag}: HA-LTS-Read fehlgeschlagen: {type(e).__name__}: {e}")
        return None


def vergleichswert(ctx: "_DriftKontext", datum: date, schluessel: str, fenster_kwh: float) -> Optional[float]:
    """Der HA-Wert, gegen den die zweite Achse ``schluessel`` am ``datum`` vergleicht: am Bestandstag seiner Gruppe das
    Fenster (wie bisher), am Kanal-Tag der HA-Kalendertag (``kalendertag_aus_fenster``) — ``None``: nicht vergleichen."""
    from backend.core.berechnungen.slot_konvention import kalendertag_aus_fenster

    gruppe = gruppe_des_schluessels(schluessel, ctx.bilanz_ziele.get(datum, frozenset()))
    if gruppe not in ctx.kanal_gruppen.get(datum, ()):
        return fenster_kwh
    folgetag = datum + timedelta(days=1)
    folge = ctx.ha_komp_je_tag[folgetag] if folgetag in ctx.ha_komp_je_tag else ctx.ha_folgetag.get(folgetag)
    vor = getattr(ctx.ha_komp_je_tag.get(datum), "erste_stunde", {}).get(schluessel)
    nach = getattr(folge, "erste_stunde", {}).get(schluessel) if folge is not None else None
    return kalendertag_aus_fenster(fenster_kwh, vor, nach)
