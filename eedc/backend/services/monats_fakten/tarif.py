"""Monats-Fakten — der Monatstarif je Stichtag (ADR-002/P8) samt Komponenten-Spezialtarif und Flex-Ø (KONZEPT-FLEX-TARIFE).
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping, Optional
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
from backend.core.berechnungen.netzbezug_kosten import berechne_netzbezug_kosten, klemme_netzanteil
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


#: Die Verwendungen, deren Tarif einen Grundpreis zur Stromrechnung beiträgt — in der Reihenfolge des Ausweises (N-769).
GRUNDPREIS_VERWENDUNGEN: tuple[str, ...] = ("allgemein", "waermepumpe", "wallbox")
#: Anwenderwort je Verwendung — wie die Tarifliste (`StrompreiseTeile.tsx::verwendungLabel` → `lib/tarifHinweise.ts`).
VERWENDUNG_LABEL: dict[str, str] = {"allgemein": "Standard", "waermepumpe": "Wärmepumpe", "wallbox": "Wallbox"}


@dataclass(frozen=True)
class GrundpreisDesMonats:
    """Der Grundpreis eines Monats: die Summe und — nur wenn ein eigener Komponenten-Tarif beiträgt — je Verwendung."""

    summe_euro: float
    #: ``{verwendung: €}`` der Tarife mit Grundpreis > 0, Reihenfolge ``GRUNDPREIS_VERWENDUNGEN``; ``None``, solange nur
    #: der allgemeine Tarif beiträgt (dann ist die Summe sein Grundpreis, und eine Aufteilung sagte nichts Neues).
    aufteilung: Optional[dict[str, float]] = None


def grundpreis_des_monats(tarife: Mapping[str, object]) -> GrundpreisDesMonats:
    """Der Grundpreis der Stromrechnung eines Monats aus den zum Stichtag gültigen Tarifen (N-769, 30.10.2026).

    ``tarife`` ist das Dict von ``lade_tarife_fuer_anlage``/``tarife_zum_stichtag`` (``allgemein``, ``waermepumpe``,
    ``wallbox``; ohne eigenen Datensatz zeigt die Verwendung auf DENSELBEN allgemeinen Datensatz). Die Stromrechnung
    trägt die Grundpreise ALLER im Monat gültigen Tarife: den allgemeinen und je Verwendung den eines EIGENEN Datensatzes —
    nicht den Rückfall auf den allgemeinen (sonst doppelt; dieselbe Identitätsprobe wie ``_wp_tarif is not allgemein``
    unten). Bis dahin las jede Sicht nur ``allgemein.grundpreis_euro_monat``: der Grundpreis eines zweiten Zählers mit
    eigenem WP-/Wallbox-Tarif ging in keine Zahl ein (gemessen r28, Januar 2025, WP-Tarif 10 €/Monat: Stromrechnung 126,17
    statt 136,17 €). Der Komponenten-Grundpreis steht NUR hier (Stromrechnung), nicht zusätzlich in WP-Kosten, WP- oder
    E-Mob-Ersparnis — sonst stünde er im Ergebnis doppelt (Vorentscheid 30.10.2026, Muster N-606).

    Die EINE Bildungsstelle: die Tarif-Fakten (``TarifFakten.grundpreis_euro_monat``), *Cockpit → Monat* (samt Vorjahr
    und Jahr) und ``GET /monatsdaten/{id}`` lesen den Grundpreis hier.
    """
    allgemein = tarife.get("allgemein")
    posten: dict[str, float] = {}
    for verwendung in GRUNDPREIS_VERWENDUNGEN:
        tarif = tarife.get(verwendung)
        if tarif is None or (verwendung != "allgemein" and tarif is allgemein):
            continue
        betrag = tarif.grundpreis_euro_monat
        if betrag is not None and betrag > 0:
            posten[verwendung] = betrag
    return GrundpreisDesMonats(
        summe_euro=sum(posten.values(), 0.0),
        aufteilung=posten if any(v != "allgemein" for v in posten) else None,
    )


#: Die Verwendungen, die einen eigenen Komponenten-Tarif haben können (N-770/N-771).
KOMPONENTEN_VERWENDUNGEN: tuple[str, ...] = ("waermepumpe", "wallbox")


def eigene_tarif_verwendungen(tarife: Mapping[str, object]) -> frozenset[str]:
    """Die Verwendungen mit EIGENEM Tarif-Datensatz (nicht dem Rückfall auf den allgemeinen) — dieselbe Identitätsprobe
    wie ``grundpreis_des_monats``. Leser: Sichtbarkeit des Felds «Netzbezug zum WP-/Wallbox-Tarif» (F1) in Datenquellen
    und Monatsabschluss."""
    allgemein = tarife.get("allgemein")
    return frozenset(
        v for v in KOMPONENTEN_VERWENDUNGEN if tarife.get(v) is not None and tarife.get(v) is not allgemein
    )


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
        # N-769: Σ der Grundpreise aller gültigen Tarife (allgemein + eigener WP-/Wallbox-Tarif) — die eine Bildungsstelle.
        grundpreis_euro_monat=grundpreis_des_monats(tarife).summe_euro,
        wp_preis_cent=wp_preis_cent,
        wallbox_preis_cent=wallbox_cent,
        # N-770/N-771: eigener Datensatz der Verwendung (dieselbe Identitätsprobe wie der Grundpreis, N-769).
        wp_eigener_tarif="waermepumpe" in eigene_tarif_verwendungen(tarife),
        wallbox_eigener_tarif="wallbox" in eigene_tarif_verwendungen(tarife),
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


@dataclass(frozen=True)
class NetzanteilZumTarif:
    """Ein Teil des Netzbezugs, den der Versorger zu einem eigenen Komponenten-Tarif abrechnet (N-770/N-771)."""

    #: ``waermepumpe`` · ``wallbox``
    verwendung: str
    #: die angesetzte Menge (geklemmt, F7)
    kwh: float
    #: Arbeitspreis des Komponenten-Tarifs (``wp_preis_cent`` bzw. ``wallbox_preis_effektiv_cent`` der Tarif-Fakten)
    cent: float
    #: die gemessene Menge vor der Klemme
    gemessen_kwh: float

    @property
    def geklemmt(self) -> bool:
        return self.kwh != self.gemessen_kwh

    @property
    def euro(self) -> float:
        return self.kwh * self.cent / 100


@dataclass(frozen=True)
class KomponentenAnteile:
    """Die gemessenen Anteile zum Komponenten-Tarif eines Monats — die EINE Bildungsstelle für Stromrechnung und
    Eigenverbrauchs-Ersparnis (N-770/N-771, Bauplan §1)."""

    #: Netzbezug zum WP- bzw. Wallbox-Tarif (Stromrechnung): ``(Netzbezug − Σ N) × Haushalt + Σ N × Komponenten-Tarif``
    netz: tuple[NetzanteilZumTarif, ...] = ()
    #: PV-Anteil der Wärmepumpe P = S − N_wp (Eigenverbrauchs-Ersparnis: P zum WP-Tarif, der Rest zum Haushaltspreis);
    #: ``None`` ohne WP-Anteil.
    wp_pv_kwh: Optional[float] = None
    wp_cent: Optional[float] = None

    def stromrechnung_anteile(self) -> tuple[tuple[float, float], ...]:
        """``(kWh, ct)`` je Anteil — die Eingabe des Layers ``berechne_netzbezug_kosten``."""
        return tuple((a.kwh, a.cent) for a in self.netz)

    def als_dict(self) -> list[dict]:
        """Antwortfeld ``netzbezug_anteile`` (Cockpit, Herleitung): je Anteil Menge, Preis, Betrag, Klemme."""
        return [
            {"verwendung": a.verwendung, "kwh": a.kwh, "cent": a.cent, "euro": a.euro,
             "gemessen_kwh": a.gemessen_kwh, "geklemmt": a.geklemmt}
            for a in self.netz
        ]


def komponenten_anteile(
    netzbezug_kwh: Optional[float],
    tarif: TarifFakten,
    *,
    wp_strom_kwh: float = 0.0,
    wp_netz_eigener_tarif_kwh: Optional[float] = None,
    wallbox_ladung_kwh: float = 0.0,
    wallbox_netz_eigener_tarif_kwh: Optional[float] = None,
) -> Optional[KomponentenAnteile]:
    """Die gemessenen Anteile zum Komponenten-Tarif eines Monats (N-770/N-771, 30.10.2026, Bauplan §1/F7/F8).

    Je Verwendung nur, wenn ein EIGENER Tarif gilt (``tarif.wp_eigener_tarif`` bzw. ``wallbox_eigener_tarif``) UND der
    Netzbezug zum Komponenten-Tarif gemessen ist (``None`` = nicht gemessen, F3). Ohne beides ``None`` — die
    Stromrechnung bleibt ``Netzbezug × Haushaltspreis`` (bitgleich wie bis dahin), die Ersparnis ebenso.

    - **Wärmepumpe:** N_wp auf ``[0, min(S, Netzbezug)]`` geklemmt (F7), Preis ``tarif.wp_preis_cent``; P = S − N_wp
      (PV-Anteil der WP) — die Eigenverbrauchs-Ersparnis bewertet ihn zum WP-Tarif (N-767 exakt statt Grenze).
    - **Wallbox:** N_wb auf ``[0, min(Ladung aller Wallboxen, Netzbezug − N_wp)]`` geklemmt, Preis
      ``tarif.wallbox_preis_effektiv_cent`` (derselbe, zu dem die E-Mob-Ersparnis die Netzladung bewertet). Die
      E-Mob-Ersparnis bleibt unverändert (F8).
    """
    if netzbezug_kwh is None:
        return None
    netz: list[NetzanteilZumTarif] = []
    wp_pv: Optional[float] = None
    wp_cent: Optional[float] = None
    rest = netzbezug_kwh
    if tarif.wp_eigener_tarif and wp_netz_eigener_tarif_kwh is not None:
        n_wp = klemme_netzanteil(wp_netz_eigener_tarif_kwh, wp_strom_kwh, rest)
        netz.append(NetzanteilZumTarif("waermepumpe", n_wp, tarif.wp_preis_cent, wp_netz_eigener_tarif_kwh))
        rest -= n_wp
        wp_pv = max(0.0, wp_strom_kwh - n_wp)
        wp_cent = tarif.wp_preis_cent
    if tarif.wallbox_eigener_tarif and wallbox_netz_eigener_tarif_kwh is not None:
        n_wb = klemme_netzanteil(wallbox_netz_eigener_tarif_kwh, wallbox_ladung_kwh, rest)
        netz.append(NetzanteilZumTarif(
            "wallbox", n_wb, tarif.wallbox_preis_effektiv_cent, wallbox_netz_eigener_tarif_kwh,
        ))
    if not netz:
        return None
    return KomponentenAnteile(netz=tuple(netz), wp_pv_kwh=wp_pv, wp_cent=wp_cent)


def komponenten_anteile_des_fakts(fakt, netzbezug_kwh: Optional[float] = None) -> Optional[KomponentenAnteile]:
    """``komponenten_anteile`` aus einem ``MonatsFakt`` (Mengen der Fakten, Tarif des Fakts); ``netzbezug_kwh`` überschreibt
    den Zählerwert, wo die Sicht einen anderen trägt (Cockpit → Monat)."""
    if fakt is None:
        return None
    return komponenten_anteile(
        fakt.zaehler.netzbezug_kwh if netzbezug_kwh is None else netzbezug_kwh,
        fakt.tarif,
        wp_strom_kwh=fakt.wp.strom_kwh,
        wp_netz_eigener_tarif_kwh=fakt.wp.netz_eigener_tarif_kwh,
        wallbox_ladung_kwh=fakt.emob.wallbox_ladung_alle_kwh,
        wallbox_netz_eigener_tarif_kwh=fakt.emob.wallbox_netz_eigener_tarif_kwh,
    )


def stromrechnung_euro(
    netzbezug_kwh: float,
    preis_cent: float,
    grundpreis_euro: float = 0.0,
    anteile: Optional[KomponentenAnteile] = None,
) -> float:
    """Die Stromrechnung eines Monats — die EINE Stelle, an der jede Sicht sie bildet (N-770 E2: bis dahin fünf
    Aufrufe der Layer-Formel mit zwei Preisquellen). ``preis_cent`` ist der Haushaltspreis (Tarif-Fakten
    ``netzbezug_preis_cent``), ``grundpreis_euro`` die Σ der Grundpreise (N-769), ``anteile`` die gemessenen Anteile
    zum Komponenten-Tarif. Mit ``grundpreis_euro = 0`` der reine Arbeitspreis-Anteil (Ø-Preis-Kachel)."""
    return berechne_netzbezug_kosten(
        netzbezug_kwh, preis_cent, grundpreis_euro,
        anteile.stromrechnung_anteile() if anteile is not None else (),
    )


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
