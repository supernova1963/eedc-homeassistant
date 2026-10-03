"""Cockpit → Jahr: welche Monate gehören dazu, und ihre zwölf Antworten — Aufbereitung für die Jahresroute.

Paket „Ergebnisgrößen Monat/Jahr in den Layer" (03.10.2026, Vorlage B3, Entscheid E3). Bis dahin lud der Browser die
Monatsantworten eines Jahres (6er-Pool) und faltete sie selbst (``v4/JahrAggregat.tsx``). D3 („kein neuer Endpoint",
24.06.2026) ist damit zurückgenommen — mit derselben Begründung, die D3 trug: „ein Jahr ist die Summe seiner Monate,
kein zweiter Code-Pfad". Der Browser-Fold WAR der zweite Code-Pfad, außerhalb jedes Backend-Wächters (ADR-001-Nachtrag).

Hier steht die **Aufbereitung** (welche Monate, in welcher Reihenfolge geladen); die Faltung selbst ist Layer
(``core/berechnungen/ergebnis.py::falte_zeitraum``). Die Monatsauswahl ist 1:1 die des Clients:

* ``zu_ladende_monate`` — Intervall vom ersten Datenmonat der Anlage bis zum laufenden Monat bzw. Dezember, plus jede
  erfasste Zeile (N-65: ein Monat ohne Abschluss fehlte sonst ganz in der Jahreszahl).
* ``monat_hat_daten`` — nur Monate mit gemessenen MENGEN; ein Monat vor der Inbetriebnahme antwortet mit Stammdaten
  (SOLL, Tarif) und darf das SOLL nicht aufblähen.
* ``abgeschlossene_monate`` — die Grundgesamtheit des Vergleichs: ohne den laufenden Monat (N-37, P-12).

``heute`` ist ``date.today()`` in der **Prozesszone** — kein Zonen-Pin (Entscheid Gernot 24.08.2026, CLAUDE.md).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.berechnungen.ergebnis import MONAT_KURZ, _js_round, falte_zeitraum, jahr_vergleich_aus, mittel_jahre

logger = logging.getLogger(__name__)

#: Die gemessenen Mengen einer Monatsantwort — wie ``MENGEN_FELDER`` im Client bis 03.10.2026.
MENGEN_FELDER: tuple[str, ...] = (
    "pv_erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh", "eigenverbrauch_kwh",
    "direktverbrauch_kwh", "gesamtverbrauch_kwh",
    "speicher_ladung_kwh", "speicher_entladung_kwh",
    "wp_strom_kwh", "wp_waerme_kwh",
    "emob_ladung_kwh", "emob_km",
    "bkw_erzeugung_kwh", "sonstiges_erzeugung_kwh", "sonstiges_verbrauch_kwh", "abgabe_dritte_kwh",
)


def monat_hat_daten(m: Mapping[str, Any]) -> bool:
    return any(m.get(k) is not None for k in MENGEN_FELDER)


def zu_ladende_monate(zeilen: Sequence[Mapping[str, Any]], jahr: int, heute: date) -> list[int]:
    menge = {r["monat"] for r in zeilen if r["jahr"] == jahr}
    if zeilen and jahr <= heute.year:
        erstes_jahr = min(r["jahr"] for r in zeilen)
        if jahr >= erstes_jahr:
            von = (
                min(r["monat"] for r in zeilen if r["jahr"] == erstes_jahr)
                if jahr == erstes_jahr else 1
            )
            bis = heute.month if jahr == heute.year else 12
            menge.update(range(von, bis + 1))
    return sorted(menge)


def abgeschlossene_monate(monate: Iterable[int], jahr: int, heute: date) -> list[int]:
    monate = list(monate)
    if jahr != heute.year:
        return monate
    return [m for m in monate if m < heute.month]


def runde_rand(d: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Die Rundung der Jahresfaltung am Antwortrand (G8: der Layer rundet nicht — Nachmessung 03.10.2026).

    Bis dahin rundete ``falte_zeitraum`` zwei Felder selbst (``sonstiges_geraete.*`` auf Cent bzw. Zehntel-kWh,
    ``grundlast_anteil_prozent`` auf eine Stelle) — Port der Client-Rundung aus ``JahrAggregat.tsx`` für die
    P6-Bitgleichheit. Dieselbe Rundung (``_js_round``, JS-``Math.round``) steht jetzt hier, also bleibt die Antwort
    der Route bitgleich (P6 nachgefahren), und die Faltung liefert ungerundete Floats wie die Leiter.
    """
    if d is None:
        return d
    for g in d.get("sonstiges_geraete") or []:
        for k, v in list(g.items()):
            if isinstance(v, float):
                g[k] = _js_round(v * 100) / 100
    if d.get("grundlast_anteil_prozent") is not None:
        d["grundlast_anteil_prozent"] = _js_round(d["grundlast_anteil_prozent"] * 10) / 10
    return d


#: Die Quellen einer Monatsantwort (``quellen``) in Anwenderwörtern — für den E11-Hinweis.
_QUELLEN_WORTE: tuple[tuple[str, str], ...] = (
    ("ha_statistics", "Home Assistant"), ("mqtt_inbound", "MQTT"), ("connector", "einem Connector"),
    ("tagesebene", "den Tageswerten"),
)


def _monate_text(monate: Sequence[int]) -> str:
    return ", ".join(MONAT_KURZ[m] for m in monate if 1 <= m <= 12)


def hinweis_ohne_abschluss(
    zeilen: Sequence[Mapping[str, Any]], antworten: Sequence[Mapping[str, Any]], jahr: int, abgeschlossen: Sequence[int],
) -> Optional[str]:
    """E11 (Entscheid Gernot 03.10.2026, N-584): der Satz für abgeschlossene Monate OHNE Monatsabschluss.

    Cockpit → Jahr behält solche Monate mit ihren Werten aus Home Assistant (bzw. MQTT, Connector, Tageswerten — N-65),
    Übersicht, PDF und HA-Sensor rechnen nur mit abgeschlossenen Monaten. Die Zeile sagt, welche Monate das sind und
    woher ihre Werte kommen (ADR-002/P4: beschriften, nicht unterdrücken). Der laufende Monat zählt NICHT mit — er hat
    naturgemäß noch keinen Abschluss und trägt seine Kennzeichnung über das Kennzahlen-Fenster.
    ``None`` heißt: jeder abgeschlossene Monat hat seinen Abschluss.
    """
    mit_abschluss = {r["monat"] for r in zeilen if r["jahr"] == jahr and r.get("id") is not None}
    ohne = [m for m in abgeschlossen if m not in mit_abschluss]
    if not ohne:
        return None
    quellen: list[str] = []
    for d in antworten:
        if d["monat"] in ohne:
            for schluessel, wort in _QUELLEN_WORTE:
                if (d.get("quellen") or {}).get(schluessel) and wort not in quellen:
                    quellen.append(wort)
    herkunft = f", Werte aus {' und '.join(quellen)}" if quellen else ""
    anzahl = f"{len(ohne)} Monat" if len(ohne) == 1 else f"{len(ohne)} Monate"
    pronomen = "ihn" if len(ohne) == 1 else "sie"
    return (f"{anzahl} ohne Monatsabschluss ({_monate_text(ohne)}){herkunft} — "
            f"Übersicht und Jahresbericht zählen {pronomen} nicht mit.")


async def baue_jahr(db: AsyncSession, anlage_id: int, jahr: int, *, heute: Optional[date] = None) -> dict[str, Any]:
    """Die Jahresantwort: zwölf Monatsantworten (in derselben Sitzung, sequenziell), Kopf, Vergleich, Vorjahr, Ø-Jahr."""
    from backend.api.routes.aktueller_monat import _berechne_monat
    from backend.api.routes.aktueller_monat.kontext import lade_monats_kontext
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.core.exceptions import not_found
    from backend.models.anlage import Anlage

    heute = heute or date.today()
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage_id)
    )).scalar_one_or_none()
    if anlage is None:
        raise not_found("Anlage")

    zeilen = [
        z.model_dump() for z in await list_monatsdaten_aggregiert(
            anlage_id, jahr=None, inkl_ohne_zaehlerzeile=True, inkl_nur_tageswerte=True, db=db,
        )
    ]
    kontext = await lade_monats_kontext(db, anlage, jahr)
    antworten: list[dict[str, Any]] = []
    fehlgeschlagen: list[int] = []
    for m in zu_ladende_monate(zeilen, jahr, heute):
        try:
            # N-610: das Jahr braucht keinen Vorjahresmonat je Monat (sein Vergleich läuft über `jahr_vergleich_aus`).
            antwort = await _berechne_monat(anlage_id, jahr, m, db, kontext=kontext, ohne_vorjahr=True)
        except Exception:
            # Ein Monat kippt das Jahr nicht (wie der Client bis 03.10.2026) — aber er fehlt nicht STILL (ADR-002/P4,
            # Nachmessung 03.10.): er steht unten in `hinweise` und in `fehlende_posten` des Kopfs.
            logger.exception("Jahresroute: Monat %s/%s nicht berechenbar", m, jahr)
            fehlgeschlagen.append(m)
            continue
        d = antwort.model_dump()
        if monat_hat_daten(d):
            antworten.append(d)
    try:
        kennzahlen = (await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=jahr, db=db)).model_dump()
    except Exception:  # pragma: no cover - ohne Kennzahlen bleibt der Zustand vor B4 (wie der Client)
        logger.exception("Jahresroute: Übersicht %s nicht ladbar", jahr)
        kennzahlen = None

    monate_nr = [d["monat"] for d in antworten]
    vergleichs_monate = abgeschlossene_monate(monate_nr, jahr, heute)
    kopf = runde_rand(falte_zeitraum(antworten, jahr, kennzahlen))
    vergleich = (
        None if vergleichs_monate == monate_nr
        else runde_rand(falte_zeitraum([d for d in antworten if d["monat"] in vergleichs_monate], jahr))
    )
    # E11 und P4: was die Kopfzahl enthält und was ihr fehlt, steht in der Antwort selbst.
    zusatz: list[str] = []
    satz = hinweis_ohne_abschluss(zeilen, antworten, jahr, vergleichs_monate)
    if satz:
        zusatz.append(satz)
    if fehlgeschlagen:
        einer = len(fehlgeschlagen) == 1
        zusatz.append(
            f"{_monate_text(fehlgeschlagen)} {jahr} "
            + ("konnte nicht berechnet werden und fehlt" if einer else "konnten nicht berechnet werden und fehlen")
            + " in den Summen des Jahres."
        )
        # G2 (Nachmessung C5, 03.10.2026): ein Monat der Grundgesamtheit fehlt — dann gibt es, wie bei einer fehlenden
        # Stromrechnung, kein Ergebnis vor Betriebskosten und kein Jahresergebnis (Stufe 2/3 `None`, Grund in
        # `fehlende_posten`). Stufe 1 bleibt die Summe der berechneten Monate und trägt den Hinweis oben (wie G2).
        for teil in (kopf, vergleich):
            if teil is None:
                continue
            teil["fehlende_posten"] = [
                *(teil.get("fehlende_posten") or []), *(f"Monat {MONAT_KURZ[m]} {jahr}" for m in fehlgeschlagen),
            ]
            teil["ergebnis_vor_betriebskosten_euro"] = None
            teil["ergebnis_euro"] = None
            herl = teil.get("ergebnis_herleitung")
            if isinstance(herl, dict):
                for stufe in ("vor_betriebskosten", "ergebnis"):
                    if isinstance(herl.get(stufe), dict):
                        herl[stufe]["ergebnis_euro"] = None
    if zusatz:
        kopf["hinweise"] = [*(kopf.get("hinweise") or []), *zusatz]
    vj = jahr_vergleich_aus(zeilen, jahr - 1, vergleichs_monate)
    andere = sorted({z["jahr"] for z in zeilen} - {jahr})
    oe = mittel_jahre([jahr_vergleich_aus(zeilen, j, vergleichs_monate) for j in andere], vergleichs_monate)
    return {
        "jahr": jahr,
        "monate": antworten,
        "kopf": kopf,
        "vergleich": vergleich,
        "monate_nr": monate_nr,
        "vergleichs_monate": vergleichs_monate,
        "vorjahr": vj if vj["monate"] else None,
        "oe_jahr": oe,
    }
