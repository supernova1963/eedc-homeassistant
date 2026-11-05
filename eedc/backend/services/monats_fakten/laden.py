"""Monats-Fakten — der Orchestrator `lade_monats_fakten` (ein Query-Satz, danach reine Faltung) und die Ergänzung
des Modus-Splits für Monate ohne Abschluss (#263 K-2).
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.api.routes.strompreise import lade_tarife_je_stichtag
from backend.services.strompreis_aggregator import PreisMessung, lade_preis_aggregate_je_monat
from backend.core.berechnungen import (
    ModusStromZeile,
    abdeckung_ueber_geraete,
    abgetretene_bkw_ids,
    funktionsfremd_abzug_kwh,
    hat_gemessene_betriebsart,
)
from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD
from backend.core.field_definitions import get_wp_strom_kwh, nenner_ist_feine_summe
from backend.models.investition import Investition
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_je_monat
from backend.services.energie_profil.modus_split_monat import lade_modus_split_mit_kanaelen
from backend.services.energie_profil.monats_aus_tagen import TagesMonatsSumme
from backend.services.pv_monatswerte import (
    BkwAnteile,
    lade_pv_je_monat,
    pv_summe_je_monat,
    pv_teilsumme_je_monat,
)
from backend.services.monats_fakten.bau import _baue_fakt
from backend.services.monats_fakten.fakten import MonatsFakt, MonatsSchluessel
from backend.services.monats_fakten.roh import NETZFELDER, _RohMonat, _ein_jahr, _im_fenster, _lade_imd, _lade_monatsdaten, netzfeld_ist_erfasst


# ═══════════════════════════════════════════════════════════════════════════
# Der Ladepfad
# ═══════════════════════════════════════════════════════════════════════════


async def lade_monats_fakten(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
    tarif_cache: Optional[dict[date, dict]] = None,
    preis_messung: Optional[PreisMessung] = None,
    inkl_nur_tageswerte: bool = False,
) -> list[MonatsFakt]:
    """Baut die Monats-Fakten einer Anlage — ein Query-Satz, danach reine Faltung.

    Args:
        db: Session.
        anlage_id: Anlage.
        von: frühester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.
        bis: spätester Monat ``(jahr, monat)``, **inklusive**. ``None`` = offen.
        preis_messung: die **gemessenen** Monats-Ø dieser Anlage, einmal je
            Anfrage geladen (``strompreis_aggregator.lade_preis_aggregate_je_monat``).
            Dieselbe Bauform wie ``tarif_cache``: Wer danach ``baue_finanz_zeile``
            ruft, reicht **dasselbe** Objekt weiter. Ohne sie fragt Stufe 2 der
            Preis-Kaskade je Monat **einzeln** — an einer Anlage mit 39 Monaten
            waren das 117 Abfragen über die Stundentabelle (gemessen 15.09.2026).
            Wird sie nicht übergeben, legt die Schicht sie selbst an.
        tarif_cache: derselbe Cache, den der Aufrufer an ``baue_finanz_zeile``
            weiterreicht. Ohne ihn löst der Tarif-Stichtag **zweimal** je Monat
            auf — einmal hier, einmal im Finanz-Zeilen-Builder (Risiko 2 des
            Konzepts, „Ladezeit"). Wer keine Finanz-Zeile baut, lässt ihn weg.
        inkl_nur_tageswerte: nimmt Monate mit auf, deren einzige Spur die lokale
            **Tagesebene** ist, und füllt damit die Lücken der übrigen Monate
            (Fund **N-121**, Default **aus**). Gedacht für **Zeitreihen** — der
            laufende Monat hat nie einen Monatsabschluss und fehlte deshalb im
            Jahres-Verlauf immer. Für Datensatz-Listen (*Auswertungen → Tabelle*)
            bleibt es aus: dort wäre so ein Monat eine Zeile, die man weder
            bearbeiten noch löschen kann. Kostet **keine** HA-Abfrage (die
            Tagesebene liegt lokal, s. ``energie_profil/monats_aus_tagen.py``).

    Returns:
        Nach ``(jahr, monat)`` aufsteigend sortierte Liste. Enthalten ist jeder
        Monat, für den es eine Zählerzeile, eine sichtbare IMD-Zeile oder eine
        aufgelöste PV gibt — Monate ohne jede Spur fehlen. Ein Monat **ohne**
        Zählerzeile ist enthalten (``meta.hat_zaehlerzeile is False``), damit eine
        Sicht die Lücke ausweisen kann, statt sie zu übersehen.

    Die Investitionen werden **ohne** ``aktiv``-Filter geladen (#123: historische
    Kennzahlen dürfen später deaktivierte Komponenten nicht rückwirkend
    ausblenden); die Sichtbarkeit entscheidet je Monat ``ist_aktiv_im_monat`` —
    das deckt alle drei Achsen ab (``aktiv``-Override, Anschaffung, Stilllegung).

    Form (RF-61, Bauform RF-1): eine Aufrufliste über den Kontext ``_LadeKontext``. ``_lade_satz`` ist der Lader der
    Schicht — der Query-Satz (Investitionen ungefiltert, IMD-Zeilen, Monatszeilen, PV über P7, negative Preise,
    Zuordnungsmonate der Wallboxen) wortgleich und in derselben Reihenfolge. Danach falten die Phasen auf dem geladenen
    Satz: ``_roh_je_monat`` (Zeitfilter je Zeile, Abtretung je Monat über ``_sichtbare_investitionen`` →
    ``_abgetretene_bkw_im_monat``), ``_modus_split_ohne_abschluss`` (E4d, F-52), ``_tagesebene`` (N-121/N-141),
    ``_kanal_gruppen`` (E4c), ``_zuordnungsmonate_nicht_gemessen`` (F10), ``_verluste_summen`` (E4b), ``_kandidaten``,
    ``_tarife_und_preise`` (P8, #412, E4f), ``_laufender_monat_emob`` (N-555), ``_netzladung_tage`` (#427),
    ``_baue_fakten`` und ``_mit_netzanteil_preisen`` (F6). Was eine Phase nachlädt, lädt sie unter derselben Bedingung
    und an derselben Stelle der Folge wie vorher.
    """
    ctx = await _lade_satz(
        db, anlage_id, von=von, bis=bis, tarif_cache=tarif_cache, preis_messung=preis_messung,
        inkl_nur_tageswerte=inkl_nur_tageswerte,
    )
    _roh_je_monat(ctx)
    await _modus_split_ohne_abschluss(ctx)
    await _tagesebene(ctx)
    await _kanal_gruppen(ctx)
    # N-770/N-771 F10 (Entscheid Gernot 31.10.2026): im Zuordnungsmonat des Felds «Netzbezug zum WP-/Wallbox-Tarif»
    # (sein Kanal beginnt im Monat) ist der Monatswert eine Teilmenge ⇒ der Monat gilt als nicht gemessen.
    await _zuordnungsmonate_nicht_gemessen(db, anlage_id, ctx.roh, ctx.investitionen)
    await _verluste_summen(ctx)
    ctx.kandidaten = _kandidaten(ctx)
    await _tarife_und_preise(ctx)
    await _laufender_monat_emob(ctx)
    await _netzladung_tage(ctx)
    fakten = await _baue_fakten(ctx)
    # N-770/N-771 F6: HT/NT über N bzw. (Netzbezug − N) — nur in Monaten, die den Netzbezug zum Komponenten-Tarif messen
    # (sonst derselbe Fakt, keine Abfrage).
    return await _mit_netzanteil_preisen(db, anlage_id, fakten, ctx.tarif_cache)


@dataclass
class _LadeKontext:
    """Der geladene Satz einer Anfrage und was die Phasen von ``lade_monats_fakten`` daraus falten (RF-61).

    Die Felder bis ``wb_zuordnung`` setzt ``_lade_satz`` (der Lader); die übrigen füllen die Phasen in ihrer Reihenfolge.
    Die Caches (``tarif_cache``, ``preis_messung``) sind die Objekte des Aufrufers, wenn er sie mitbringt — sie werden an
    Ort und Stelle ergänzt, nie ersetzt (der Aufrufer reicht sie an ``baue_finanz_zeile`` weiter).
    """

    db: AsyncSession
    anlage_id: int
    von: Optional[MonatsSchluessel]
    bis: Optional[MonatsSchluessel]
    inkl_nur_tageswerte: bool
    tarif_cache: Optional[dict[date, dict]]
    preis_messung: Optional[PreisMessung]
    investitionen: list[Investition]
    inv_by_id: dict[int, Investition]
    imd_rows: list
    monatsdaten_by_ym: dict
    pv_je_modul: dict
    bkw_anteile: BkwAnteile
    pv_summen: dict
    pv_teilsummen: dict
    neg_preis_je_monat: Optional[dict]
    wb_zuordnung: dict
    #: N-266/N-386: je Monat die abgetretenen Balkonkraftwerke (``_abgetretene_bkw_im_monat``).
    abgetretene_cache: dict[MonatsSchluessel, frozenset] = field(default_factory=dict)
    # Roh-Faltung je Monat aus den sichtbaren IMD-Zeilen.
    roh: dict[MonatsSchluessel, _RohMonat] = field(default_factory=dict)
    #: (jahr, monat) → {investition_id_als_string: (hat_gespeicherten_split,
    #: gepflegter_wp_strom_kwh)} — die Buchführung für den Modus-Lesepfad (F-52).
    #: Sie entsteht **in diesem Durchlauf**, damit der Lesepfad je *Gerät*
    #: entscheiden kann, statt je Monat: eine Anlage mit zwei Wärmepumpen kann
    #: für die eine einen Abschluss haben und für die andere nicht.
    wp_je_monat: dict[MonatsSchluessel, dict[str, tuple[bool, float]]] = field(default_factory=dict)
    #: (jahr, monat) → {investition_id_als_string: „der Nenner dieser Zeile ist
    #: die feine Summe"} — dieselbe Buchführung, andere Frage (N-462).
    wp_nenner_fein: dict[MonatsSchluessel, dict[str, bool]] = field(default_factory=dict)
    nur_fuer_ladeanteil: bool = False
    wp_kanal: dict = field(default_factory=dict)
    wp_gruppen: dict[MonatsSchluessel, set[str]] = field(default_factory=dict)
    tages_summen: dict[MonatsSchluessel, TagesMonatsSumme] = field(default_factory=dict)
    emob_kanal: dict[MonatsSchluessel, object] = field(default_factory=dict)
    kanal_gruppen: dict[MonatsSchluessel, set[str]] = field(default_factory=dict)
    verluste_summen: dict[MonatsSchluessel, TagesMonatsSumme] = field(default_factory=dict)
    kandidaten: set = field(default_factory=set)
    zeittarif_cache: dict = field(default_factory=dict)
    preis_cache: dict = field(default_factory=dict)
    laufend: Optional[MonatsSchluessel] = None
    laufend_quellen: frozenset = frozenset()
    bloecke: dict = field(default_factory=dict)
    netzladung_tage: dict = field(default_factory=dict)

    @property
    def mit_tagesebene(self) -> bool:
        """Wird die Tagesebene geladen? Mit dem Flag (N-121) oder allein für den Ladeanteil (N-141 Weg c)."""
        return self.inkl_nur_tageswerte or self.nur_fuer_ladeanteil

    def offen(self, m: MonatsSchluessel) -> bool:
        """Darf die Schicht einen Monat ohne bisherige Spur führen? Nur mit dem Flag (N-121) — oder er hat eine
        Zählerzeile."""
        return self.inkl_nur_tageswerte or m in self.monatsdaten_by_ym


async def _lade_satz(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[MonatsSchluessel],
    bis: Optional[MonatsSchluessel],
    tarif_cache: Optional[dict[date, dict]],
    preis_messung: Optional[PreisMessung],
    inkl_nur_tageswerte: bool,
) -> _LadeKontext:
    """Der Query-Satz der Schicht (RF-61, Phase von ``lade_monats_fakten``): Investitionen ungefiltert, IMD-Zeilen,
    Monatszeilen, PV über die Read-time-SoT (P7), negative Preise je Monat, Zuordnungsmonate der Wallboxen (N-771) —
    in dieser Reihenfolge und wortgleich wie vor dem Schnitt. Er rechnet nichts außer den Nachschlage-Tabellen."""
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = list(inv_result.scalars().all())
    inv_by_id = {i.id: i for i in investitionen}

    imd_rows = await _lade_imd(db, [i.id for i in investitionen], von, bis)
    md_rows = await _lade_monatsdaten(db, anlage_id, von, bis)
    monatsdaten_by_ym = {(m.jahr, m.monat): m for m in md_rows}

    # PV über den Read-time-SoT (P7): gemessene Modulwerte + Lücken aus dem
    # Anlagen-Aggregat. NIE die Rohspalte direkt — sie ist entweder eine
    # Teilsumme oder sie überschreibt Messungen.
    #
    # N-611: der Anlagenwert steht für ALLE PV-Quellen. Das Balkonkraftwerk geht
    # hier nicht in die Modul-Auflösung (es kommt in `bau.py` als `bkw_erzeugung`
    # dazu), sein eigener Wert mindert aber den Anlagenwert, bevor der Rest die
    # Modul-Lücken füllt — sonst stünde es zweimal in `pv_kwh`. Dafür reicht die
    # Schicht ihre Investitionen UNGEFILTERT durch; Zeitfilter und Abtretung
    # entscheidet `lade_pv_je_monat` je Monat (ADR-002/P11, N-386, #123).
    #
    # N-621: ein Balkonkraftwerk OHNE eigenen Wert bekommt in einem Monat mit
    # gespeichertem Anlagenwert seinen kWp-Anteil am Rest — dieselbe Auflösung
    # wie die Modul-Lücken, nur getrennt zurückgegeben (`bkw_anteile`), damit
    # `pv_je_modul` bei den Modulen bleibt (F-10). Er geht in `bau.py` als
    # `bkw_aus_anlagenwert_kwh` in `pv_kwh` und verdrängt im selben Monat den
    # Rest-Eigenverbrauch (P9, unten in der Faltung) und den BKW-Tageswert.
    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    bkw_anteile: BkwAnteile = {}
    pv_je_modul = await lade_pv_je_monat(
        db, anlage_id, pv_module, jahr=_ein_jahr(von, bis), investitionen=investitionen,
        bkw_anteile=bkw_anteile,
    )
    pv_summen = pv_summe_je_monat(pv_je_modul)
    # N-626: die Anzeige-Summe eines Monats mit Modul-Lücke ohne Anlagenwert (die vorhandenen Werte);
    # `bau.py` nimmt sie erst nach der vollständigen Summe und dem Tageswert.
    pv_teilsummen = pv_teilsumme_je_monat(pv_je_modul)

    neg_preis_je_monat = await get_neg_preis_einspeisung_je_monat(db, anlage_id)

    # N-771 Rest 1 (E6): der Zuordnungsmonat des Felds je Wallbox (eine Abfrage nur, wenn eine Wallbox-Zeile das Feld
    # trägt) — dort ist das Feld auch an der E-Mob-Zeile nicht die Netzladung (`reader.netzladung_des_zaehlers`).
    _wb_zuordnung = await _wallbox_zuordnungsmonate(db, anlage_id, imd_rows, inv_by_id)
    return _LadeKontext(
        db=db, anlage_id=anlage_id, von=von, bis=bis, inkl_nur_tageswerte=inkl_nur_tageswerte,
        tarif_cache=tarif_cache, preis_messung=preis_messung,
        investitionen=investitionen, inv_by_id=inv_by_id, imd_rows=imd_rows, monatsdaten_by_ym=monatsdaten_by_ym,
        pv_je_modul=pv_je_modul, bkw_anteile=bkw_anteile, pv_summen=pv_summen, pv_teilsummen=pv_teilsummen,
        neg_preis_je_monat=neg_preis_je_monat, wb_zuordnung=_wb_zuordnung,
    )


def _sichtbare_investitionen(ctx: _LadeKontext, jahr: int, monat: int) -> list[Investition]:
    """Der Zeitfilter (aktiv · Anschaffung · Stilllegung, #123) eines Monats über die ungefiltert geladenen
    Investitionen — die Menge, auf die der Selektor danach läuft (RF-61, Phase von ``lade_monats_fakten``)."""
    return [i for i in ctx.investitionen if i.ist_aktiv_im_monat(jahr, monat)]


def _abgetretene_bkw_im_monat(ctx: _LadeKontext, jahr: int, monat: int) -> frozenset:
    """Welche BKW haben in DIESEM Monat abgetreten? (Zeitfilter → Selektor; RF-61, Phase von ``lade_monats_fakten``)"""
    # N-266: Balkonkraftwerke, unter denen `pv-module` hängen. Ihre Erzeugung
    # steckt seit E4 in `pv_je_modul` (der BKW-Monatswert füllt dort die Lücken
    # seiner Kinder) und darf deshalb nicht zusätzlich als `bkw_erzeugung`
    # gezählt werden. Ohne Modul-Kinder ist die Menge leer und alles bleibt
    # bitgleich zu vorher.
    #
    # ⛔ **Je MONAT, nicht einmal für die Anlage** (N-386, ADR-002/P11 nennt die
    # Reihenfolge Zeitfilter → Selektor ausdrücklich als Teil der Regel). Bis
    # 2026-09-04 stand hier ein einziger Aufruf über die ganze Menge: Wer seinem
    # bestehenden Balkonkraftwerk Module zuordnete, verlor dessen Erzeugung
    # damit **rückwirkend** in jedem Monat davor — in dem das BKW der einzige
    # Erzeuger war und die Module noch gar nicht existierten. Unauffällig, weil
    # alle Sichten denselben zu kleinen Wert nannten.
    schluessel = (jahr, monat)
    if schluessel not in ctx.abgetretene_cache:
        ctx.abgetretene_cache[schluessel] = abgetretene_bkw_ids(_sichtbare_investitionen(ctx, jahr, monat))
    return ctx.abgetretene_cache[schluessel]


def _roh_je_monat(ctx: _LadeKontext) -> None:
    """Roh-Faltung je Monat aus den sichtbaren IMD-Zeilen (RF-61, Phase von ``lade_monats_fakten``) samt der
    Buchführung je Wärmepumpe für den Modus-Lesepfad (F-52, #263) und die Stufe des Nenners (N-462)."""
    for imd in ctx.imd_rows:
        inv = ctx.inv_by_id.get(imd.investition_id)
        # #153/#155/#236/#308: vor Anschaffung / nach Stilllegung / deaktiviert
        # zählt nichts — der EINE Ort, an dem dieser Filter gilt.
        if inv is None or not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
            continue
        daten = _daten_mit_auskunft(imd, inv, ctx.wb_zuordnung)
        ctx.roh.setdefault((imd.jahr, imd.monat), _RohMonat()).falte(
            inv, daten,
            abgetretene_bkw=_abgetretene_bkw_im_monat(ctx, imd.jahr, imd.monat),
            bkw_mit_anlagenanteil=frozenset(ctx.bkw_anteile.get((imd.jahr, imd.monat), {})),
            source_provenance=imd.source_provenance,
        )
        if inv.typ == "waermepumpe":
            # #263 — eine **gemessene** Betriebsart-Aufteilung wirkt hier wie
            # ein gelaufener Monatsabschluss: der aus dem Betriebsmodus
            # gerechnete Split wird für dieses Gerät NICHT zusätzlich
            # angewandt, sonst stünde dieselbe Menge zweimal in der Zeile.
            # Dieselbe Weiche, kein zweiter Mechanismus (ADR-002/P8).
            ctx.wp_je_monat.setdefault((imd.jahr, imd.monat), {})[str(inv.id)] = (
                float(daten.get(MODUS_ABDECKUNG_FELD) or 0) > 0
                or hat_gemessene_betriebsart(daten),
                get_wp_strom_kwh(daten, inv.parameter),
            )
            # N-462: Welche **Stufe** trägt der Strom dieser Zeile (K3)? Der
            # Nachtrag-Block unten sieht die Zeile nicht mehr, braucht die
            # Antwort aber für SOLL-§9-E7/Option A.
            ctx.wp_nenner_fein.setdefault((imd.jahr, imd.monat), {})[str(inv.id)] = (
                nenner_ist_feine_summe(daten, inv.parameter)
            )


async def _modus_split_ohne_abschluss(ctx: _LadeKontext) -> None:
    """Die WP-Gruppe aus den Kanälen (E4d) und der Modus-Split für Monate ohne Abschluss (F-52) — RF-61, Phase von
    ``lade_monats_fakten``. Davor die Vorprüfung N-141 (``nur_fuer_ladeanteil``) auf den gefalteten Zeilen; die E4d-
    Faltung steht vor dem Split, weil der Split ihre Buchführung (``wp_je_monat``) als «gespeichert» liest."""
    # ── Modus-Split für Monate ohne Abschluss (F-52) ─────────────────────────
    #
    # **Der zweite Aufrufer, den `modus_split_monat.py` im eigenen Modul-Kopf
    # beschreibt.** Er fehlte: die drei Modus-Felder stehen nur in der
    # IMD-Zeile, und dorthin schreibt allein der von Hand gestartete
    # Monatsabschluss. Der *laufende* Monat hat nie einen — wer den
    # Betriebsmodus heute zuordnet, sah bis hierher in **allen vier** Sichten
    # nichts (Komponenten-Hub, Cockpit Monat, Cockpit Jahr, HA-Sensoren), und
    # zwar bis zum nächsten Abschluss. Gemeldet von kingcap1 (#263).
    #
    # **Gespeichert schlägt gerechnet** — dieselbe Reihenfolge wie beim
    # Schreibpfad (ADR-002/P8: ein Wert trägt den Stichtag seines Monats). Wo
    # ein Abschluss gelaufen ist, gilt sein Ergebnis, auch wenn die Tagesebene
    # inzwischen etwas anderes hergäbe.
    #
    # ⚠ **Die Invariante gilt hier genauso**, und sie ist der Grund, warum
    # dieser Block nicht einfach addiert: Beim Abschluss *verworfene* Splits
    # (Σ Teilmengen > Gesamt) hinterlassen keine Spur — ohne erneute Prüfung
    # kämen sie über diesen Weg zurück und die Invariante wäre umgangen.
    #
    # **Kosten:** eine `SELECT DISTINCT datum … WHERE betriebsmodus_je_wp IS NOT
    # NULL`. Eine Anlage ohne Modus-Zuordnung bricht dort ab und lädt nichts
    # (`modus_split_monat.py`, Modul-Kopf) — deshalb genügt als Vorbedingung,
    # dass es überhaupt eine Wärmepumpe gibt.
    #
    # ── HA-Bauform E4d: die WP-Gruppe aus den Kanälen (Bauplan §6 U4, §8a; Lesart 1) ──────────────────────────────
    # Je Monat EINE Quellenwahl der WP-Gruppe (`kanal/wp_leser.py`). Deckt sie den Monat und trägt der Monat KEINE
    # WP-Zeile (gespeichert schlägt gerechnet, P8 — die Gruppe als Ganzes, wie E-Mob/Sonstiges in E4c), faltet die
    # Schicht je Gerät die Kanal-Zeile in der Form einer Abschluss-Zeile ein (Strom, Wärme je Feld, Betriebsart-Strom,
    # Kälte, Strom je Betriebsart, Abdeckung); neue Monate nur mit dem Flag (N-121), geladen nur wo die Tagesebene
    # ohnehin geladen wird (dieselbe Bedingung wie E4c). Der Modus-Split der übrigen Monate ohne Abschluss kommt für
    # gedeckte Monate aus dem Kanal, sonst unverändert aus der Tagesebene (`_ergaenze_modus_split_ohne_abschluss`).
    ctx.nur_fuer_ladeanteil = not ctx.inkl_nur_tageswerte and any(
        m.emob_ladung_ohne_pv_anteil for m in ctx.roh.values()
    )
    if not any(i.typ == "waermepumpe" for i in ctx.investitionen):
        return
    from backend.services.kanal.wp_leser import wp_monate

    ctx.wp_kanal = await wp_monate(ctx.db, ctx.anlage_id, von=ctx.von, bis=ctx.bis)
    if ctx.mit_tagesebene:
        ctx.wp_gruppen = _falte_wp_kanal(
            ctx.roh, ctx.wp_kanal, ctx.inv_by_id, ctx.wp_je_monat, ctx.wp_nenner_fein,
            offen=ctx.offen,
        )
    await _ergaenze_modus_split_ohne_abschluss(
        ctx.db, ctx.anlage_id, ctx.roh, ctx.wp_je_monat, ctx.inv_by_id,
        wp_nenner_fein=ctx.wp_nenner_fein, von=ctx.von, bis=ctx.bis, wp_kanal=ctx.wp_kanal,
    )


async def _tagesebene(ctx: _LadeKontext) -> None:
    """Die lokale Tagesebene (N-121 nur mit dem Flag, N-141 Weg c für den Ladeanteil) — RF-61, Phase von
    ``lade_monats_fakten``. Ohne beide Gründe wird sie nicht geladen."""
    # Die lokale Tagesebene als **zusätzliche** Grundgesamtheit (N-121). Ohne
    # das Flag wird sie nicht einmal geladen — die Kosten trägt nur, wer sie
    # bestellt.
    #
    # ⚠ Seit N-141 Weg (c) gibt es einen **zweiten** Grund, sie zu laden, und er
    # hat nichts mit der Grundgesamtheit zu tun: der PV-Anteil der Heimladung
    # ist nirgends gemessen und wird aus der Tagesebene abgeleitet. Ohne dieses
    # Nachladen sähen nur die Aufrufer MIT dem Flag (Speicher-Potential,
    # Auswertungen → Tabelle und Cockpit → Jahr über `monatsdaten.py`; Cockpit →
    # Monat ruft seit C1a OHNE das Flag) einen PV-Anteil, während Komponenten-Hub,
    # CO₂-Bilanz und E-Auto-Ersparnis weiter 0 % behaupten — zwei Zahlen für dieselbe Größe,
    # die Klasse hinter #331 und F-15. Deshalb **bedingt**: nur wenn ein Monat
    # überhaupt Heimladung ohne gepflegten PV-Anteil trägt. Eine Anlage ohne
    # Wallbox und ohne E-Auto zahlt dafür nichts (Entscheid Gernot 2026-08-08).
    if not ctx.mit_tagesebene:
        return
    # ⭐ Wird die Tagesebene NUR für den Ladeanteil gebraucht, genügen die
    # Tageszusammenfassungen — die Quote steht dort. Die **Stunden**ebene
    # braucht nur, wer unten wirklich auf sie zurückfällt, und das sind
    # genau zwei Stellen in `_baue_fakt`: der Zähler-Fallback (`monatsdaten
    # is None` — seit N-736 auch ein Netzfeld, das die Zeile nicht erfasst,
    # `bau._zaehler_fakten`) und der Speicher-Fallback (keine `speicher`-Zeile
    # im Monat). PV, BKW und die Quote kommen aus der Tageszusammenfassung.
    #
    # ⛔ Die Bedingung ist aus `_baue_fakt` abgeleitet, nicht aus einer
    # Beispielanlage: an der produktiven Anlage wäre die Menge leer, und
    # eine Regel, die nur dort stimmt, hätte jedem mit Zähler- oder
    # Speicherlücke still die Rückfallwerte genommen.
    stunden_nur_fuer = None
    if not ctx.inkl_nur_tageswerte:
        im_fenster = [
            k for k in (set(ctx.monatsdaten_by_ym) | set(ctx.roh))
            if _im_fenster(k, ctx.von, ctx.bis)
        ]
        stunden_nur_fuer = {
            k for k in im_fenster
            if k not in ctx.monatsdaten_by_ym
            or not all(netzfeld_ist_erfasst(ctx.monatsdaten_by_ym[k], feld) for feld in NETZFELDER)
            or "speicher" not in ctx.roh.get(k, _RohMonat()).typen_mit_zeile
        }
    # HA-Bauform E4a-2 (Umschaltstelle 1): je Monat EINE Quellenwahl der Bilanz-Gruppe — Monate, deren
    # Kanäle voll decken, aus den Kanälen (Weg 2, `services/kanal/bilanz_leser.py`), die übrigen unverändert
    # aus der Tagesebene (Lesart 1); die E-Mob-Aufteilung bleibt aus der Tagesebene (D2).
    from backend.services.kanal.bilanz_leser import lade_monats_summen

    ctx.tages_summen = await lade_monats_summen(
        ctx.db, ctx.anlage_id, von=ctx.von, bis=ctx.bis, stunden_nur_fuer=stunden_nur_fuer,
    )


async def _kanal_gruppen(ctx: _LadeKontext) -> None:
    """E-Mob- und Sonstiges-Gruppe aus den Kanälen (E4c) und die Marken der WP-Gruppe (E4d) je Monat — RF-61, Phase
    von ``lade_monats_fakten``."""
    # ── HA-Bauform E4c: E-Mob- und Sonstiges-Gruppe aus den Kanälen (Bauplan §6 U5/U6, §7 E-c) ──────────────────────
    # Je Monat und Gruppe EINE Quellenwahl, getrennt von der Bilanz-Gruppe (`kanal/geraete_leser.py`). Deckt eine Gruppe
    # den Monat und trägt der Monat für sie KEINE Zeile (gespeichert schlägt gerechnet, P8 — feldgruppen-weise wie der
    # Tageswert-Rückfall in `bau.py`), faltet die Schicht je Gerät die Zeile `{feld: Δ}` des Kanals ein — in denselben
    # `_RohMonat.falte` wie eine Monatszeile: Wallbox-Regel, Pool, Rest und Dienstwagen-Filter entscheiden danach die
    # Faltung und die eine Funktion (`entscheide_emob_heimladung`) zur Lesezeit (P10), genau wie im abgeschlossenen Monat.
    # Die Sonstiges-ERZEUGER gehören zur Bilanz-Gruppe und kommen aus deren Kanal-Monat (`sonstige_erzeuger_je_inv`).
    # Die E-Mob-Aufteilung (der PV-Anteil) eines gedeckten Monats kommt aus dem abgeleiteten Kanal — mit UND ohne
    # Abschluss (N-631: „eine Aufteilung für Monat mit und ohne Abschluss"). Geladen wird nur, wo die Tagesebene
    # ohnehin geladen ist (dieselbe Bedingung, N-121: ohne Flag öffnet die Schicht keinen neuen Monat).
    if ctx.mit_tagesebene and any(
        i.typ in ("e-auto", "wallbox", "sonstiges") for i in ctx.investitionen
    ):
        from backend.services.kanal.geraete_leser import geraete_monate

        geraete = await geraete_monate(ctx.db, ctx.anlage_id, von=ctx.von, bis=ctx.bis)
        ctx.emob_kanal, ctx.kanal_gruppen = _falte_kanal_gruppen(
            ctx.roh, geraete, ctx.tages_summen, ctx.inv_by_id,
            offen=ctx.offen,
        )
    elif ctx.tages_summen:
        # Ohne E-Mob-/Sonstiges-Geräte bleibt nur der Erzeuger hinter dem Zähler aus dem Kanal-Monat der Bilanz.
        _, ctx.kanal_gruppen = _falte_kanal_gruppen(
            ctx.roh, {}, ctx.tages_summen, ctx.inv_by_id,
            offen=ctx.offen,
        )

    for m, marken in ctx.wp_gruppen.items():
        ctx.kanal_gruppen.setdefault(m, set()).update(marken)


async def _verluste_summen(ctx: _LadeKontext) -> None:
    """Die Kanal-Monate der Wandlungsverluste (E4b, N-588) — RF-61, Phase von ``lade_monats_fakten``."""
    # HA-Bauform E4b (Entscheid B-1): die Wandlungsverluste (samt Messpunkt-Vertrag, N-588) kommen aus dem Kanal-Monat — auch für
    # abgeschlossene Monate, deren Mengen aus der Zählerzeile stammen. Wurde die Tagesebene oben geladen, trägt sie die
    # Kanal-Monate schon (`lade_monats_summen`); sonst EIN zusätzlicher `kanal_monate`-Aufruf, und nur, wenn die Anlage
    # einen Anlagenzähler-Kanal hat (ohne ihn ist der Wert ohnehin `None`). ⚑ Laufzeit: Vormerkung E4f „Monatsreihe je
    # Anfrage einmal laden".
    ctx.verluste_summen = ctx.tages_summen
    from backend.services.kanal.bilanz_leser import hat_anlagenzaehler_kanal, kanal_monate

    if not ctx.tages_summen and await hat_anlagenzaehler_kanal(ctx.db, ctx.anlage_id):

        ctx.verluste_summen = await kanal_monate(ctx.db, ctx.anlage_id, von=ctx.von, bis=ctx.bis)


def _kandidaten(ctx: _LadeKontext) -> set:
    """Die Grundgesamtheit der Monate (RF-61, Phase von ``lade_monats_fakten``) — vor dem Fenster-Schnitt."""
    return (
        set(ctx.monatsdaten_by_ym)
        | set(ctx.pv_summen)
        | set(ctx.pv_je_modul)
        | set(ctx.bkw_anteile)
        | set(ctx.roh)
        # ⚠ Nur mit dem Flag erweitert die Tagesebene die Grundgesamtheit. Wurde
        # sie allein für den Ladeanteil geholt, darf sie KEINE zusätzlichen
        # Monate aufmachen — sonst tauchten in jeder Sicht plötzlich Monate auf,
        # die nur eine Tagesspur haben. Das ist genau die Wirkung, die N-121
        # hinter das Flag gestellt hat.
        | (set(ctx.tages_summen) if ctx.inkl_nur_tageswerte else set())
    )


async def _tarife_und_preise(ctx: _LadeKontext) -> None:
    """Die Caches der Anfrage, die gemessenen Monats-Ø (#412), die Tarife aller Stichtage (P8) und die Vormerkung des
    Netzbezugs je Stunde für Zeitfenster-Tarife (E4f) — RF-61, Phase von ``lade_monats_fakten``."""
    if ctx.tarif_cache is None:
        ctx.tarif_cache = {}
    # N-267: eigener Cache je Aufruf — begruendet im Block ueber `_komponenten_preis`.
    ctx.zeittarif_cache = {}
    # #412: dieselbe Bauform für die volle Preis-Kaskade. Sie fragt je Monat
    # die Stundenpreise ab; über ein Jahr wären das sonst zwölf Abfragen pro
    # Leser, und Cockpit → Jahr hat mehrere.
    ctx.preis_cache = {}
    von, bis = ctx.von, ctx.bis
    if ctx.preis_messung is None:
        # EINE gruppierte Abfrage für die ganze Anfrage. Der Aufrufer darf sie
        # mitbringen (und reicht dann dasselbe Objekt an `baue_finanz_zeile`
        # weiter) — sonst entsteht sie hier, mit demselben Fenster wie die
        # Fakten selbst.
        ctx.preis_messung = await lade_preis_aggregate_je_monat(
            ctx.db, ctx.anlage_id,
            von=date(von[0], von[1], 1) if von else None,
            bis=(
                date(bis[0] + (bis[1] == 12), (bis[1] % 12) + 1, 1)
                if bis else None
            ),
        )
    # ⭐ Die Tarife aller Stichtage in EINER Abfrage vorladen (statt einer je
    # Monat plus Nachladen der Zeitfenster). `_lade_tarif` und `baue_finanz_zeile`
    # finden danach alles im Cache — an ihrem Code ändert sich nichts. P8 bleibt:
    # jeder Monat bekommt den Tarif seines eigenen Stichtags.
    _offene_stichtage = [
        date(k[0], k[1], 1)
        for k in sorted(kk for kk in ctx.kandidaten if _im_fenster(kk, von, bis))
        if date(k[0], k[1], 1) not in ctx.tarif_cache
    ]
    if _offene_stichtage:
        ctx.tarif_cache.update(
            await lade_tarife_je_stichtag(ctx.db, ctx.anlage_id, _offene_stichtage)
        )
    # HA-Bauform E4f (Auftrag Punkt 3b): die Monate, in denen ein Zeitfenster-Tarif (HT/NT) gilt, brauchen den
    # Netzbezug je Stunde als Gewicht — im Lade-Kontext der Anfrage holt der erste Abruf alle in EINER Anweisung.
    from backend.core.berechnungen.zeittarif import hat_zeitfenster
    from backend.services.kanal.preis_leser import netzbezug_vormerken

    netzbezug_vormerken(ctx.db, ctx.anlage_id, [
        k for k in ctx.kandidaten if _im_fenster(k, von, bis)
        and any(hat_zeitfenster(t) for t in (ctx.tarif_cache.get(date(k[0], k[1], 1)) or {}).values())
    ])


async def _laufender_monat_emob(ctx: _LadeKontext) -> None:
    """N-555: die Heimlade-Quellen des laufenden Monats (Regel 1) und die Ladeblöcke je Auto (Stufe 3) — RF-61, Phase
    von ``lade_monats_fakten``."""
    # N-555 (Konzept Regel 1): der LAUFENDE Monat fragt zusätzlich, ob einem
    # Heimlade-Feld eine Quelle zugeordnet ist — sonst stünde in Übersicht, Hubs und
    # Jahresbericht für einen Monat, dessen Wallbox misst und noch nichts geladen hat,
    # der Fahrverbrauch als Schätzung, während *Cockpit → Monat* 0 zeigt (gemessen in
    # der Wirkungsmessung: 1.544 gegen 0 kWh). Eine Abfrage, nur wenn der laufende
    # Monat gebaut wird und E-Mobilität in Betrieb ist.
    from backend.services.emob_heimlade_quellen import (
        lade_emob_heimlade_quellen,
        laufender_monat,
    )

    ctx.laufend = laufender_monat()
    if ctx.laufend in ctx.kandidaten and _im_fenster(ctx.laufend, ctx.von, ctx.bis):
        from backend.models.anlage import Anlage as _Anlage

        _anlage = await ctx.db.get(_Anlage, ctx.anlage_id)
        if _anlage is not None:
            ctx.laufend_quellen = await lade_emob_heimlade_quellen(
                ctx.db, _anlage, ctx.investitionen, *ctx.laufend,
            )

    # N-555 Stufe 3 (Konzept 7.2 Regel 9 Punkt 3, Anhang D): die Ladeblöcke je Auto — lokal,
    # eine Abfrage, nur mit E-Auto UND Wallbox. Der Leser prüft die Tages-Bedingung W-C
    # (jeder Tag des Monats mit Regelmarke); ohne sie rechnet der Monat nach Stufe 2.
    if any(i.typ == "e-auto" for i in ctx.investitionen) and any(
        i.typ == "wallbox" for i in ctx.investitionen
    ):
        from backend.services.energie_profil.monats_aus_tagen import emob_je_auto_monate

        ctx.bloecke = await emob_je_auto_monate(
            ctx.db, ctx.anlage_id, ctx.investitionen,
            [k for k in ctx.kandidaten if _im_fenster(k, ctx.von, ctx.bis)],
        )


async def _netzladung_tage(ctx: _LadeKontext) -> None:
    """Die Speicher-Netzladung im Tageswert-Rückfall (#427) — RF-61, Phase von ``lade_monats_fakten``."""
    # Entscheid Gernot 13.10.2026 (#427): die Speicher-Netzladung im Tageswert-Rückfall — dieselbe Regel wie Ladung/
    # Entladung in `bau._baue_fakt` (Monat ohne Speicher-Zeile, Tage mit Speicherwert), Menge und Preis aus der einen
    # Rechenstelle `netzladung_tage.netzladung_aus_tagen`, die auch *Cockpit → Monat* ruft. Geladen nur für genau diese
    # Monate — ohne Tagesebene (kein Flag, kein Ladeanteil) gibt es keinen Rückfall und keine Abfrage.
    _nl_monate = [
        k for k in ctx.kandidaten
        if _im_fenster(k, ctx.von, ctx.bis)
        and (s := ctx.tages_summen.get(k)) is not None
        and "speicher" not in ctx.roh.get(k, _RohMonat()).typen_mit_zeile
        and (s.speicher_ladung_kwh > 0 or s.speicher_entladung_kwh > 0)
        and any(i.typ == "speicher" and i.ist_aktiv_im_monat(*k) for i in ctx.investitionen)
    ]
    if not _nl_monate:
        return
    from datetime import datetime as _dt

    from backend.models.anlage import Anlage as _Anlage
    from backend.services.kanal.bilanz_leser import uhr as _uhr
    from backend.services.monats_fakten.netzladung_tage import netzladung_aus_tagen

    _nl_anlage = await ctx.db.get(_Anlage, ctx.anlage_id)
    # Die Uhr der Schicht ist die der Kanal-Leser (eine Stelle, Proben stellen sie dort).
    _heute = _dt.fromtimestamp(_uhr()).date()
    for k in _nl_monate:
        _nl = await netzladung_aus_tagen(
            ctx.db, _nl_anlage,
            [i for i in ctx.investitionen if i.typ == "speicher" and i.ist_aktiv_im_monat(*k)],
            k[0], k[1], _heute,
        )
        if _nl is not None:
            ctx.netzladung_tage[k] = _nl


async def _baue_fakten(ctx: _LadeKontext) -> list[MonatsFakt]:
    """Je Monat im Fenster, aufsteigend, der kanonische ``MonatsFakt`` (``bau._baue_fakt``) — RF-61, Phase von
    ``lade_monats_fakten``."""
    fakten: list[MonatsFakt] = []
    for schluessel in sorted(k for k in ctx.kandidaten if _im_fenster(k, ctx.von, ctx.bis)):
        fakten.append(
            await _baue_fakt(
                ctx.db,
                ctx.anlage_id,
                schluessel,
                ctx.roh.get(schluessel, _RohMonat()),
                monatsdaten=ctx.monatsdaten_by_ym.get(schluessel),
                pv_modul_summe=ctx.pv_summen.get(schluessel),
                pv_modul_teilsumme=ctx.pv_teilsummen.get(schluessel),
                pv_je_modul=ctx.pv_je_modul.get(schluessel, {}),
                bkw_aus_anlagenwert=ctx.bkw_anteile.get(schluessel, {}),
                investitionen=ctx.investitionen,
                neg_preis_kwh=(ctx.neg_preis_je_monat or {}).get(schluessel),
                tarif_cache=ctx.tarif_cache,
                zeittarif_cache=ctx.zeittarif_cache,
                tages_summe=ctx.tages_summen.get(schluessel),
                netzladung_tage=ctx.netzladung_tage.get(schluessel),
                preis_cache=ctx.preis_cache,
                preis_messung=ctx.preis_messung,
                heimlade_quellen=ctx.laufend_quellen if schluessel == ctx.laufend else frozenset(),
                bloecke=ctx.bloecke.get(schluessel),
                verluste_summe=ctx.verluste_summen.get(schluessel),
                emob_kanal=ctx.emob_kanal.get(schluessel),
                kanal_gruppen=frozenset(ctx.kanal_gruppen.get(schluessel, ())),
            )
        )
    return fakten


async def _mit_netzanteil_preisen(db: AsyncSession, anlage_id: int, fakten: list, tarif_cache: dict) -> list:
    """N-770/N-771 F6 je Fakt (``tarif.mit_netzanteil_preisen``) — eigene Phase (Komplexitäts-Wächter)."""
    from backend.services.monats_fakten.tarif import mit_netzanteil_preisen

    return [await mit_netzanteil_preisen(db, anlage_id, f, tarif_cache.get(date(f.jahr, f.monat, 1)) or {})
            for f in fakten]


def _falte_kanal_gruppen(roh, geraete, tages_summen, inv_by_id, *, offen):
    """HA-Bauform E4c: die Zeilen der E-Mob- und Sonstiges-Gruppe aus den Kanälen in die Rohmonate falten.

    ``geraete``: ``kanal/geraete_leser.geraete_monate`` je Monat. ``offen(m)``: darf die Schicht diesen Monat führen,
    auch wenn er bisher keine Spur hat (nur mit ``inkl_nur_tageswerte``, N-121)? Ein Monat, der schon eine Spur hat
    (Zeile, Zählerzeile), ist immer offen.

    Je Monat und Gruppe: deckt die Gruppe (Wahl ``kanal``) und trägt der Monat für sie keine Zeile (P8, gespeichert
    schlägt gerechnet — die Gruppe als Ganzes: E-Mob = alle Wallboxen und E-Autos, auch dienstliche; Sonstiges = alle
    Sonstiges-Geräte), werden ihre Zeilen gefaltet. Das ist das heutige feldgruppen-weise Füllen der Monats-Fakten
    (``bau.py``: der Tageswert füllt eine Gruppe nur, wenn der Monat für ihren Typ keine Zeile trägt), auf die zwei
    Gruppen angewandt (Annahme 1, abgenommen vom Master 06.10.2026). Die Sonstiges-Erzeuger kommen aus dem Kanal-Monat der BILANZ-Gruppe
    (``TagesMonatsSumme.sonstige_erzeuger_je_inv`` — leer, wo die Bilanz-Gruppe den Bestand liest).

    Returns: ``(emob_kanal, gruppen)`` — je Monat mit gedeckter E-Mob-Gruppe ihr Ergebnis (der Anteil gilt auch für
    Monate MIT Zeile, N-631), je Monat die Marken der gefalteten Gruppen (``TAGESWERT_EMOB``/``TAGESWERT_SONSTIGES``).
    """
    from backend.services.kanal.geraete_leser import herkunft_der_zeile
    from backend.services.monats_fakten.fakten import TAGESWERT_EMOB, TAGESWERT_SONSTIGES

    vorher = set(roh)
    emob_kanal: dict = {}
    gruppen: dict[MonatsSchluessel, set[str]] = {}

    def _falte(m, inv_id, zeile) -> bool:
        inv = inv_by_id.get(int(inv_id))
        if inv is None or not inv.ist_aktiv_im_monat(*m) or not zeile:
            return False
        roh.setdefault(m, _RohMonat()).falte(inv, zeile, source_provenance=herkunft_der_zeile(zeile))
        return True

    monate = set(geraete) | {m for m, s in tages_summen.items() if getattr(s, "sonstige_erzeuger_je_inv", None)}
    for m in sorted(monate):
        if not (offen(m) or m in vorher):
            continue
        r = roh.get(m)
        zeile_emob = r is not None and bool(r.eauto_ladedaten or r.wallbox_ladedaten or r.dienstlich_je_inv)
        zeile_sonst = r is not None and "sonstiges" in r.typen_mit_zeile
        g = geraete.get(m)
        if g is not None and g.emob.kanal:
            emob_kanal[m] = g.emob
            if not zeile_emob and any([_falte(m, i, z) for i, z in sorted(g.emob.zeilen.items())]):
                gruppen.setdefault(m, set()).add(TAGESWERT_EMOB)
        if zeile_sonst:
            continue
        gefaltet = []
        if g is not None and g.sonstiges.kanal:
            gefaltet += [_falte(m, i, z) for i, z in sorted(g.sonstiges.zeilen.items())]
        summe = tages_summen.get(m)
        for inv_id, kwh in sorted((getattr(summe, "sonstige_erzeuger_je_inv", None) or {}).items()):
            gefaltet.append(_falte(m, inv_id, {"erzeugung_kwh": kwh}))
        if any(gefaltet):
            gruppen.setdefault(m, set()).add(TAGESWERT_SONSTIGES)
    return emob_kanal, gruppen

async def _wallbox_zuordnungsmonate(db: AsyncSession, anlage_id: int, imd_rows, inv_by_id) -> dict:
    """N-771 Rest 1 (E6): ``wallbox_id → Zuordnungsmonat`` des Felds aus den geladenen Zeilen
    (``kanal/netzanteil_leser.zuordnungsmonate_der_wallboxen`` — ohne Wallbox-Zeile mit Feld keine Abfrage)."""
    from backend.services.kanal.netzanteil_leser import zuordnungsmonate_der_wallboxen

    return await zuordnungsmonate_der_wallboxen(db, anlage_id, [
        (imd.investition_id, imd.verbrauch_daten) for imd in imd_rows
        if getattr(inv_by_id.get(imd.investition_id), "typ", None) == "wallbox"
    ])


def _daten_mit_auskunft(imd, inv, wb_zuordnung: dict) -> dict:
    """Die Zeile einer IMD, wie die Faltung sie liest — an einer Wallbox im Zuordnungsmonat ihres Felds mit der Auskunft
    (``netzanteil_leser.mit_zuordnungsauskunft``, N-771 Rest 1); sonst ``verbrauch_daten`` selbst."""
    daten = imd.verbrauch_daten or {}
    if not wb_zuordnung or inv.typ != "wallbox":
        return daten
    from backend.services.kanal.netzanteil_leser import mit_zuordnungsauskunft

    return mit_zuordnungsauskunft(daten, inv.id, (imd.jahr, imd.monat), wb_zuordnung)


async def _zuordnungsmonate_nicht_gemessen(db: AsyncSession, anlage_id: int, roh: dict, investitionen) -> None:
    """N-770/N-771 F10 (Bauplan §2c, Entscheid Gernot 31.10.2026): der **Zuordnungsmonat** des Felds «Netzbezug zum
    WP-/Wallbox-Tarif» — der Kalendermonat, in dem sein Kanal beginnt (``kanal/netzanteil_leser.beginn_je_geraet``; dort
    hat der Kanal keinen Stand vor dem Monatsbeginn, ``lesen.py`` Regel (a)) — gilt als **nicht gemessen**: der Monatswert
    der Abschluss-Zeile ist eine Teilmenge, und ein zu kleines N machte den PV-Anteil P = S − N zu groß. Dieselbe Regel
    wie bei jedem neu zugeordneten Zähler (Handbuch Einstellungen §7.2). Ein Monat OHNE Kanal (Hand, CSV, vor dem Kanal)
    bleibt mit seinem Monatswert gemessen (E2-Wirkung).

    ⚑ **Benannte Grenze — der Handwert im Zuordnungsmonat:** Gernot 31.10.: «ein von Hand eingetragener Monatswert im
    Zuordnungsmonat gilt (Herkunft der Abschluss-Zeile prüfen); ist das nicht billig, als Grenze benennen». Die Herkunft
    unterscheidet ihn nicht: der Monatsabschluss stempelt JEDES gesendete Feld ``manual:form``
    (``monatsabschluss/wizard.py``, ``write_json_subkey_with_provenance(..., source="manual:form")``) — den getippten Wert
    und den übernommenen HA-Statistik-Vorschlag (die Teilmenge) gleich. Deshalb gilt der Zuordnungsmonat ohne Ausnahme
    als nicht gemessen.

    Abfrage nur, wenn eine Monatszeile das Feld überhaupt trägt (sonst bitgleich, keine SQL-Anweisung mehr)."""
    if not any(r.wp_netz_eigener_tarif_gemessen or r.wallbox_netz_eigener_tarif_gemessen for r in roh.values()):
        return
    from backend.services.kanal.netzanteil_leser import beginn_je_geraet, monat_der_stunde

    typ_je_inv = {i.id: i.typ for i in investitionen if i.typ in ("waermepumpe", "wallbox")}
    for inv_id, ts in (await beginn_je_geraet(db, anlage_id, typ_je_inv)).items():
        r = roh.get(monat_der_stunde(ts))
        if r is None:
            continue
        if typ_je_inv[inv_id] == "waermepumpe":
            r.wp_netz_eigener_tarif_luecke = True
        else:
            r.wallbox_netz_eigener_tarif_luecke = True


def _falte_wp_kanal(roh, wp_kanal, inv_by_id, wp_je_monat, wp_nenner_fein, *, offen) -> dict[MonatsSchluessel, set[str]]:
    """HA-Bauform E4d: die Zeilen der WP-Gruppe aus den Kanälen in die Rohmonate falten.

    ``wp_kanal``: ``kanal/wp_leser.wp_monate`` je Monat. ``offen(m)``: darf die Schicht diesen Monat führen, auch wenn
    er bisher keine Spur hat (nur mit ``inkl_nur_tageswerte``, N-121)? Je Monat mit Wahl ``kanal`` und OHNE WP-Zeile
    (P8, die Gruppe als Ganzes) je Gerät die Kanal-Zeile in der Form, die der Abschluss schriebe
    (``bau.wp_kanal_zeile``: Herkunft ``kanal``, abgeleitete Heizwärme wie beim Abschluss) — durch denselben
    ``_RohMonat.falte`` wie eine Monatszeile. Die Buchführung für den Modus-Split (``wp_je_monat``) und die Stufe des
    Nenners (``wp_nenner_fein``, N-462) entstehen aus derselben Zeile, wie im IMD-Durchlauf.

    Returns: je Monat die Marke ``TAGESWERT_WP``, wo gefaltet wurde.
    """
    from backend.services.monats_fakten.bau import wp_kanal_zeile
    from backend.services.monats_fakten.fakten import TAGESWERT_WP

    vorher = set(roh)
    gruppen: dict[MonatsSchluessel, set[str]] = {}
    for m, z in sorted(wp_kanal.items()):
        if not z.kanal or not (offen(m) or m in vorher):
            continue
        r = roh.get(m)
        if r is not None and "waermepumpe" in r.typen_mit_zeile:
            continue
        for inv_id, zeile in sorted(z.zeilen.items()):
            inv = inv_by_id.get(int(inv_id))
            if inv is None or not inv.ist_aktiv_im_monat(*m) or not zeile:
                continue
            daten, herkunft = wp_kanal_zeile(inv, zeile)
            roh.setdefault(m, _RohMonat()).falte(inv, daten, source_provenance=herkunft)
            wp_je_monat.setdefault(m, {})[str(inv.id)] = (
                float(daten.get(MODUS_ABDECKUNG_FELD) or 0) > 0 or hat_gemessene_betriebsart(daten),
                get_wp_strom_kwh(daten, inv.parameter),
            )
            wp_nenner_fein.setdefault(m, {})[str(inv.id)] = nenner_ist_feine_summe(daten, inv.parameter)
            gruppen.setdefault(m, set()).add(TAGESWERT_WP)
    return gruppen


async def _ergaenze_modus_split_ohne_abschluss(
    db: AsyncSession,
    anlage_id: int,
    roh: dict[MonatsSchluessel, _RohMonat],
    wp_je_monat: dict[MonatsSchluessel, dict[str, tuple[bool, float]]],
    inv_by_id: dict[int, Investition],
    *,
    wp_nenner_fein: dict[MonatsSchluessel, dict[str, bool]],
    von: Optional[MonatsSchluessel],
    bis: Optional[MonatsSchluessel],
    wp_kanal: Optional[dict] = None,
) -> None:
    """Trägt den Modus-Split der Tagesebene nach, wo kein Abschluss ihn hält (F-52).

    Ändert ``roh`` an Ort und Stelle. **Die Regeln stehen nicht hier** — sie
    liegen in ``lade_modus_split_ohne_abschluss``, weil der HA-Export dieselben
    braucht und seine IMD-Zeilen je Investition faltet (P10-Restschuld). Ein
    Nachbau daneben wäre die Drift-Klasse, an der F-52 selbst entstanden ist.

    ⚠ **Es entsteht hier ein neuer Monat**, wo bisher keine Gerätespur lag —
    und das ist gewollt: ein Monat mit Modus-Spur *hat* eine, sie steht nur in
    Stundenzeilen statt in einer Monatszeile. Das ist nicht die N-121-Falle
    (dort ging es um Monate mit reiner Tagesspur ohne jeden Gerätebezug).
    """
    # HA-Bauform E4d (Lesart 1): Monate, deren WP-Gruppe die Kanäle decken, je Gerät aus dem abgeleiteten Kanal oder —
    # ohne ihn (V-1) — aus den Stundenzeilen; die übrigen unverändert aus der Tagesebene. Die eine Weiche mit dem
    # HA-Export (N-727): `lade_modus_split_mit_kanaelen`.
    angewandt = await lade_modus_split_mit_kanaelen(
        db, anlage_id, wp_kanal=wp_kanal, inv_by_id=inv_by_id, gespeichert=wp_je_monat, von=von, bis=bis,
    )
    for schluessel, je_inv in sorted(angewandt.items()):
        for inv_id, split in je_inv.items():
            r = roh.setdefault(schluessel, _RohMonat())
            r.wp_modus_strom_heizen += split.heizen_kwh
            r.wp_modus_strom_kuehlen += split.kuehlen_kwh
            # N-609: der nachgetragene Kühlanteil gehört auch zur Zeile SEINES Geräts — sonst rechnete die
            # Gerätezeile mit vollem Strom, die Anlagensumme ohne Kühlstrom (gemessen 115 gegen 124 €).
            r.wp_je_geraet.setdefault(int(inv_id), [0.0, 0.0, 0.0])[2] += split.kuehlen_kwh
            r.wp_modus_strom_warmwasser += split.warmwasser_kwh
            # ⭐ **SOLL-§9-E7/Option A — auch hier, und hier ist es immer der
            # abgeleitete Zweig.** `lade_modus_split_ohne_abschluss` trägt
            # genau die Monate nach, für die es *keinen* Abschluss und damit
            # keine gemessene Betriebsart-Zeile gibt: Dieser Split ist per
            # Konstruktion eine **Verteilung** des Gesamtstroms. Bei getrennter
            # Strommessung verteilt er `strom_heizen + strom_warmwasser` und
            # darf diesen Nenner deshalb nicht kürzen.
            #
            # ⛔ **Die Regel wird GERUFEN, nicht nachgebaut** (F-56). Der
            # Umweg über eine `ModusStromZeile` sieht nach Umstand aus und ist
            # der Kern: So gilt hier **dieselbe** Definition von
            # „funktionsfremd" und **dieselbe** Abzugsbedingung wie im
            # IMD-Zweig. Ein `if hat_split: 0 else kuehlen_kwh` daneben wäre
            # die zweite Codestelle, an der F-56 schon einmal entstanden ist.
            #
            # ⚠ `gemessen=False` ist keine Annahme, sondern die Definition
            # dieses Pfads: `lade_modus_split_ohne_abschluss` trägt genau die
            # Monate nach, für die es keine gemessene Betriebsart-Zeile gibt.
            # Lüften/Entfeuchten bleiben 0 — der abgeleitete Weg kann sie
            # nicht (E4/D11).
            #
            # ⚠ **`int(inv_id)`** — `angewandt` ist nach Investitions-ID als
            # **Zeichenkette** gekeyt, `inv_by_id` nach `int`. Ohne die
            # Umwandlung liefe der Nachschlag still ins Leere und der Abzug
            # würde für JEDE Anlage gezogen.
            _inv_nach = inv_by_id.get(int(inv_id))
            r.wp_modus_strom_funktionsfremd_abzug += funktionsfremd_abzug_kwh(
                ModusStromZeile(
                    heizen_kwh=split.heizen_kwh,
                    kuehlen_kwh=split.kuehlen_kwh,
                    warmwasser_kwh=split.warmwasser_kwh,
                    gemessen=False,
                    abdeckung_h=split.abdeckung_h,
                ),
                # ⛔ **N-462: die STUFE dieser Zeile, nicht das Kennzeichen.**
                # `lade_modus_split_ohne_abschluss` nimmt als Bezug den
                # *gepflegten* Strom der Monatszeile, sobald es einen gibt —
                # also genau die Menge, die `get_wp_strom_kwh` gewählt hat. Ist
                # das der Gesamtzähler (feine Achse unvollständig, K3), steckt
                # der Kühlstrom darin und muss abgezogen werden.
                # Ein Monat **ohne** jede Zeile hat auch keinen Gesamtzähler,
                # auf den er zurückfallen könnte — dort bleibt es beim
                # Kennzeichen, und das heißt „feine Summe".
                hat_split=wp_nenner_fein.get(schluessel, {}).get(
                    inv_id,
                    bool((getattr(_inv_nach, "parameter", None) or {})
                         .get("getrennte_strommessung")),
                ),
            )
            # W-17: Stunden werden ueber GERAETE nicht addiert (SoT-Helfer).
            # Die Schleife laeuft ueber `je_inv` — jeder Durchlauf ist ein
            # weiteres Geraet DESSELBEN Monats. Mengen ja, Zeitraum nein.
            r.wp_modus_abdeckung_h = abdeckung_ueber_geraete(
                r.wp_modus_abdeckung_h, split.abdeckung_h,
            )
            r.wp_modus_strom_bezug += split.bezug_kwh
