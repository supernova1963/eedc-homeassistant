"""Monats-Fakten — der Monatstarif je Stichtag (ADR-002/P8) samt Komponenten-Spezialtarif und Flex-Ø (KONZEPT-FLEX-TARIFE).
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    lade_tarife_je_stichtag,
    resolve_tarif_for_komponente,
    resolve_einspeise_preis_cent,
)
from backend.services.strompreis_aggregator import (
    PreisMessung,
    aufgeloester_monatspreis,
    lade_preis_aggregate_je_monat,
    wirksamer_arbeitspreis_cent,
)
from backend.core.berechnungen.dienstliche_ladekosten import (
    DienstlicheLadungZeile,
    berechne_dienstliche_ladekosten,
)
from backend.core.wirtschaftlichkeit_defaults import EINSPEISEVERGUETUNG_DEFAULT_CENT
from backend.models.monatsdaten import Monatsdaten
from backend.services.monats_fakten.fakten import MonatsSchluessel, TarifFakten


# ⛔ Der Zeittarif-Cache reist NICHT im `tarif_cache` mit — erster Entwurf am
# 2026-08-29, von `test_geteilter_tarif_cache_laedt_jeden_stichtag_einmal`
# kassiert, und zu Recht: `tarif_cache` ist `dict[date, dict]`, ein
# String-Schluessel darin macht ihn heterogen und schon ein `sorted()` bricht ab.
#
# Stattdessen haelt jede Bildungsstelle ihren EIGENEN Cache je Aufruf. Damit kann
# derselbe Monat zweimal an der Stundentabelle landen — einmal aus
# `lade_monats_fakten`, einmal aus `baue_finanz_zeile`. Das ist bewusst in Kauf
# genommen:
#   · Es ist eine **Performance**-Frage, keine Drift-Frage. Die Warnung der Probe
#     („zwei Aufloesungen aus zwei Caches sind eine Drift-Gelegenheit") gilt der
#     TARIF-Aufloesung — welche Zeile gilt —, und die bleibt geteilt. Der Preis
#     entsteht daraus rein und deterministisch: dieselbe Tarifzeile und dieselben
#     unveraenderlichen Stundenzeilen ergeben denselben Wert.
#   · Und sie faellt nur bei Anlagen MIT Zeitfenstern an: ohne Fenster fragt
#     `wirksamer_arbeitspreis_cent` die Datenbank gar nicht erst.
# Wer das aendern will, gibt den Cache als eigenen Parameter durch — nicht als
# Fremdschluessel in einem fremden Dict.


async def _komponenten_preis(
    db: AsyncSession,
    anlage_id: int,
    schluessel: MonatsSchluessel,
    tarife: dict,
    komponente: str,
    stammpreis: float,
    zeittarif_cache: dict,
) -> float:
    """Komponenten-Tarif ueber die SoT-Kaskade, mit Zeitfenstern (N-267).

    ⚠ **Gewichtet wird mit dem Netzbezug des HAUSES, auch beim Waermepumpen-
    oder Wallbox-Tarif** — und das ist eine Festlegung, keine Nachlaessigkeit:
    eedc misst je Geraet den **Verbrauch**, nicht den **Netzbezug**. Wieviel
    einer Geraetestunde aus dem Netz kam und wieviel aus der PV, ist ohne eine
    Zuteilungsannahme nicht bekannt — eine zweite Gewichtungsbasis waere also
    keine groessere Genauigkeit, sondern eine erfundene. Wer einen
    Zeittarif-Waermepumpentarif genauer abrechnen will, traegt den Monats-Ø ein;
    dieses Feld schlaegt den Wert hier ohnehin.
    """
    tarif = resolve_tarif_for_komponente(tarife, komponente)
    if tarif is None:
        return stammpreis
    return await wirksamer_arbeitspreis_cent(
        db, anlage_id, schluessel[0], schluessel[1], tarif, cache=zeittarif_cache
    )

async def _lade_tarif(
    db: AsyncSession,
    anlage_id: int,
    schluessel: MonatsSchluessel,
    monatsdaten: Optional[Monatsdaten],
    cache: dict[date, dict],
    zeittarif_cache: dict,
    preis_cache: Optional[dict] = None,
    preis_messung: Optional[PreisMessung] = None,
) -> TarifFakten:
    """Tarif zum Monatsersten (P8) — ein Cache-Eintrag je Stichtag pro Anfrage."""
    stichtag = date(schluessel[0], schluessel[1], 1)
    if stichtag not in cache:
        cache[stichtag] = await lade_tarife_fuer_anlage(db, anlage_id, target_date=stichtag)
    tarife = cache[stichtag]

    allgemein = tarife.get("allgemein")
    # N-267: Traegt der Tarif Zeitfenster (HT/NT), ist der Stammpreis des Monats
    # der ueber den GEMESSENEN Netzbezug gewichtete Arbeitspreis statt der
    # Spalte. Ohne Fenster liefert der Helfer die Spalte unveraendert zurueck —
    # dieselbe Bauform wie `aufgeloester_strompreis_cent` auf der E-Mob-Achse
    # (F-18): eine Anlage ohne den neuen Fall bewegt keine Zahl.
    stammpreis = await wirksamer_arbeitspreis_cent(
        db, anlage_id, schluessel[0], schluessel[1], allgemein, cache=zeittarif_cache
    )
    # Komponenten-Tarif über die SoT-Kaskade (Komponente → allgemein → Default)
    # statt handschriftlich: ein Spezialtarif-Datensatz OHNE Arbeitspreis fiel
    # in der Handschrift auf `None` durch, statt auf den allgemeinen Tarif.
    wallbox_cent = await _komponenten_preis(
        db, anlage_id, schluessel, tarife, "wallbox", stammpreis, cache
    )
    # ⭐ **Die ganze Kaskade** (#412, 11.09.2026): gepflegt → gemessen →
    # Zeitfenster → Stamm. Bis dahin fehlte die **Messung** zwischen den beiden
    # äußeren Stufen — ein dynamischer Tarif rechnete ohne Monatsabschluss mit
    # dem Stammpreis, obwohl die Stundenpreise mitgeschrieben werden.
    # ⚠ `stammpreis` bleibt daneben stehen: er ist der Bezugspunkt der
    # Komponenten-Kaskade (`_komponenten_preis`) und eine eigene Aussage.
    preis = await aufgeloester_monatspreis(
        db, anlage_id, schluessel[0], schluessel[1], monatsdaten, allgemein,
        cache=preis_cache, messung=preis_messung,
    )
    # N-663 (10.10.2026): Ohne EIGENEN Wärmepumpen-Tarif hängt die WP am Hauszähler — ihr Preis ist dann der
    # des Hauszählers, mit der ganzen Kaskade (gepflegt → gemessen → Zeitfenster → Stamm), also `preis.cent`.
    # Bis dahin stand hier immer `_komponenten_preis(…, "waermepumpe", …)`; der fällt ohne WP-Tarif auf den
    # Stammpreis zurück und übersprang den gepflegten bzw. gemessenen Monats-Ø (gemessen: Tarif 30 ct, Monats-Ø
    # 24 ct ⇒ WP 30, Wallbox 24). Dieselbe Regel wie *Cockpit → Monat* ohne Gerätezeile
    # (`aktueller_monat/waerme.py`: „Ohne eigenen WP-Tarif gilt der allgemeine Bezugspreis — bei flexiblem Tarif
    # also der Monatsdurchschnitt"). MIT eigenem WP-Tarif bleibt es bei dessen Kaskade (KONZEPT-FLEX-TARIFE P-6:
    # eine separat belieferte WP hat ihre eigene) — unverändert.
    _wp_tarif = resolve_tarif_for_komponente(tarife, "waermepumpe")
    if _wp_tarif is not None and _wp_tarif is not allgemein:
        wp_preis_cent = await _komponenten_preis(
            db, anlage_id, schluessel, tarife, "waermepumpe", stammpreis, cache
        )
    else:
        wp_preis_cent = preis.cent
    return TarifFakten(
        netzbezug_preis_cent=preis.cent,
        netzbezug_preis_herkunft=preis.herkunft,
        netzbezug_stammpreis_cent=stammpreis,
        # #392: der Monatswert der variablen Vergütung schlägt den Stammwert —
        # dieselbe zweite P8-Form wie beim Netzbezug eine Zeile darüber.
        einspeiseverguetung_cent=resolve_einspeise_preis_cent(
            monatsdaten,
            allgemein.einspeiseverguetung_cent_kwh
            if allgemein
            else EINSPEISEVERGUETUNG_DEFAULT_CENT,
        ),
        grundpreis_euro_monat=(allgemein.grundpreis_euro_monat or 0.0) if allgemein else 0.0,
        wp_preis_cent=wp_preis_cent,
        wallbox_preis_cent=wallbox_cent,
        # Der Flex-Ø gilt für den ganzen Zähler — auch für die Wallbox.
        # #412: dieselbe Kaskade wie beim Netzbezug eine Zeile darüber — sonst
        # trüge DASSELBE `TarifFakten`-Objekt zwei verschiedene Auflösungen
        # (`netzbezug_preis_cent` mit Messung, die Wallbox ohne).
        # `stammpreis_override`: der Wallbox-Tarif bleibt Stufe 4.
        # ⭐ N-717 (12.10.2026): die Kaskade läuft über den Tarif DERSELBEN
        # Verwendung (`resolve_tarif_for_komponente(…, "wallbox")` — ohne eigenen
        # Wallbox-Tarif der Allgemeintarif). Bis dahin stand hier `allgemein`:
        # Stufe 3 prüfte dessen HT/NT-Fenster und ersetzte den Wallbox-Tarif durch
        # ihren Ø (gemessen 26,667 statt 25 ct ⇒ E-Auto-Ersparnis 760,00 statt
        # 772,00 € in Cockpit, Hubs, HA-Anlagensensoren und Aussichten). N-433:
        # der Komponenten-Tarif ist Stufe 4 und geht nicht verloren; gepflegt
        # (Stufe 1) und gemessen (Stufe 2) gelten dem ganzen Zähler und schlagen
        # ihn weiter. Die zweite Kaskade `strompreise.monats_strompreis_lookup`
        # (sie übergab schon den Wallbox-Tarif) ist damit entfallen.
        wallbox_preis_effektiv_cent=(await aufgeloester_monatspreis(
            db, anlage_id, schluessel[0], schluessel[1], monatsdaten,
            resolve_tarif_for_komponente(tarife, "wallbox"),
            stammpreis_override=wallbox_cent, messung=preis_messung,
        )).cent,
        kraftstoffpreis_euro=monatsdaten.kraftstoffpreis_euro if monatsdaten else None,
        gaspreis_cent_kwh=monatsdaten.gaspreis_cent_kwh if monatsdaten else None,
    )


async def tarif_des_monats(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, monatsdaten: Optional[Monatsdaten] = None,
) -> TarifFakten:
    """Der Monatstarif, wie die Monats-Fakten ihn bilden (``_lade_tarif``: Stichtag P8, die ganze Kaskade, Wallbox-Preis
    mit Flex-Ø) — für eine Sicht, die einen Monat OHNE Fakt rechnet (HA-Bauform E4e: Cockpit → Monat ohne Abschluss,
    dienstliche Ladekosten). Eigene Caches je Aufruf; dieselbe Auflösung wie die Schicht, keine zweite."""
    return await _lade_tarif(db, anlage_id, (jahr, monat), monatsdaten, {}, {})


async def tarife_der_monate(
    db: AsyncSession, anlage_id: int, monate: Iterable[MonatsSchluessel],
) -> dict[MonatsSchluessel, TarifFakten]:
    """Der Monatstarif VIELER Monate, wie die Monats-Fakten ihn bilden — je Monat ``_lade_tarif`` (``tarif_des_monats``),
    mit den geteilten Ladern von ``lade_monats_fakten``: Tarife aller Stichtage in einer Abfrage
    (``lade_tarife_je_stichtag``), die gemessenen Monats-Ø in einer (``lade_preis_aggregate_je_monat``), die
    Monatszeilen in einer.

    N-712/N-713 (12.10.2026, Entscheid Gernot: Kanon ist der Monatspreis der Monats-Fakten): Hubs, HA-Export und
    Aussichten lesen ihren Monatspreis HIER, statt ihn je Sicht aus Tarif und Ersatzpreis zusammenzusetzen. Bis dahin
    setzte jede Sicht für Monate vor dem ersten Tarif den HEUTIGEN Tarif ein (Fall C: E-Auto-Hub 666,00 statt 675,00 €)
    und nahm ohne eigenen WP-Tarif den Stammpreis statt der N-663-Kaskade (gepflegter Monats-Ø 24 ct: WP-Hub 346,67
    statt 490,67 €). Die Sicht wählt das Feld ihrer Verwendung: ``netzbezug_preis_cent`` (Hauszähler),
    ``wp_preis_cent``, ``wallbox_preis_effektiv_cent``. Keine eigene Kaskade — dieselbe Auflösung wie die Schicht."""
    _monate = sorted(set(monate))
    if not _monate:
        return {}
    md_je_monat = {
        (m.jahr, m.monat): m
        for m in (await db.execute(
            select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
        )).scalars().all()
    }
    tarif_cache: dict[date, dict] = await lade_tarife_je_stichtag(
        db, anlage_id, [date(j, m, 1) for j, m in _monate]
    )
    letzter = _monate[-1]
    messung = await lade_preis_aggregate_je_monat(
        db, anlage_id,
        von=date(_monate[0][0], _monate[0][1], 1),
        bis=date(letzter[0] + (letzter[1] == 12), (letzter[1] % 12) + 1, 1),
    )
    zeittarif_cache: dict = {}
    preis_cache: dict = {}
    return {
        k: await _lade_tarif(
            db, anlage_id, k, md_je_monat.get(k), tarif_cache, zeittarif_cache,
            preis_cache=preis_cache, preis_messung=messung,
        )
        for k in _monate
    }


def dienstliche_ladekosten_euro(pv_kwh: float, netz_kwh: float, tarif: TarifFakten) -> float:
    """Der Posten „Dienstliche Ladekosten" eines Monats (N-633) aus den Mengen und dem Monatstarif — die EINE
    Bewertung, die ``bau.py`` für den Fakt und Cockpit → Monat ohne Fakt rufen (Layer-Formel
    ``berechne_dienstliche_ladekosten``: PV-Anteil zum Netzbezugspreis, Netzanteil zum effektiven Wallbox-Preis)."""
    return berechne_dienstliche_ladekosten([
        DienstlicheLadungZeile(
            ladung_pv_kwh=pv_kwh,
            ladung_netz_kwh=netz_kwh,
            netzbezug_preis_cent=tarif.netzbezug_preis_cent,
            wallbox_preis_cent=tarif.wallbox_preis_effektiv_cent,
        ),
    ]).gesamt_euro
