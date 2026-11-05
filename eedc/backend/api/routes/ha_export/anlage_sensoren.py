"""HA-Export — die Anlagen-Sensoren: `calculate_anlage_sensors` (Energie, Finanzen, CO₂, Prognose, Preis, Grundlast je
Anlage aus den Monats-Fakten, ADR-002/P10).

Seit Vorlage 8b (18.09.2026) ist der Rechner ein Orchestrator: Kopf (Monatsdaten, Frühausstieg, heutiger Tarif,
Investitionen) und `return` stehen hier, die neun Phasen liegen byte-identisch in `anlage_energie.py` (Monatsfakten und
Energie, Finanz-Aggregat, Investitionen und USt), `anlage_komponenten.py` (historische Komponenten, Alternativkosten und
CO₂, Ertrag und Amortisation, Speicher-KPIs) und `anlage_sensorwerte.py` (Sensorwerte, Prognose und Preis; dort auch
`grundlast_sensorwert`, hier re-exportiert). Schnittstelle je Phase: Schlüsselwort-Parameter hinein, Rückgabe-Dict heraus;
Gate ist der Golden Master `plans/skript-golden-master-ha-export.py`.

RF-75 (5.11.2026): auch der Kopf ist eine Phase — `_anlage_eingaenge` (Kontext `_AnlageEingaenge`, Frühausstieg ohne
Monatsdaten), das `_out`-Entpacken je Phase läuft über `_entpacke` in die Werte-Tafel des Orchestrators, die S3b-Eingänge
(Bezugspreise, Speicher-Wirkungsgrade) über `_s3b_eingaenge`. Die Vorlage-8b-Phasen sind unverändert.
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from dataclasses import dataclass
from collections import defaultdict
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    FinanzMonatsZeile,
    berechne_dienstliche_ladekosten,
    berechne_finanz_aggregat,
    berechne_wp_alternativkosten_ersparnis,
    berechne_spez_ertrag_annualisiert,
    berechne_verbrauchs_kennzahlen,
    erzeugung_hinter_zaehler_kwh,
    imd_typ_beitrag,
    monatsgewichte_aus_pvgis,
    relevante_kosten_aus_investitionen,
    speicher_wirkungsgrad,
    vollzyklen as berechne_vollzyklen,
)
from backend.services.prognose_auswahl import lade_aktive_prognose
from datetime import date, datetime
from backend.services.strompreis_aggregator import (
    lade_preis_aggregate_je_monat,
    aufgeloester_monatspreis,
)
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen.kapitalrechnung import (
    ErsparnisPosten,
    annahme_dauer_text,
    erklaerung_jahres_ersparnis,
    jahres_ersparnis_euro,
    kapitaleinsatz_euro,
)
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.core.berechnungen.investitions_jahresertrag import (
    BEZEICHNUNG_ERTRAGSFELD,
    jahresertrag_posten,
)
from backend.models.investition import ERTRAGSFELD_TYPEN, Investition, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_jetzt

import logging

logger = logging.getLogger(__name__)
from backend.services.ha_sensors_export import (
    SensorValue,
    ANLAGE_SENSOREN,
    INVESTITION_SENSOREN,
    SPEICHER_SENSOREN,
    LETZTER_IMPORT_SENSOREN,
    PROGNOSE_SENSOREN,
    PREIS_SENSOREN,
)
from backend.services.ha_export_prognose import berechne_prognose_export
from backend.services.ha_export_preis import berechne_preis_export
from backend.core.investition_parameter import PARAM_E_AUTO, PARAM_E_AUTO_DEFAULTS, ist_dienstlich
from backend.core.calculations import berechne_co2_bilanz
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    ust_eigenverbrauch_fuer_anlage,
)
# Vorlage 8b: die Phasen des Anlagen-Rechners (Bauform wie `aussichten/finanz_*.py`, ohne Lazy-Import —
# die Phasenmodule brauchen nichts aus diesem Modul, ein Zyklus entsteht nicht).
from backend.api.routes.ha_export.anlage_energie import (
    monatsfakten_und_energie,
    finanz_aggregat,
    investitionen_und_ust,
)
from backend.api.routes.ha_export.anlage_komponenten import (
    historische_komponenten,
    alternativkosten_und_co2,
    ertrag_und_amortisation,
    speicher_kpis,
)
from backend.api.routes.ha_export.anlage_sensorwerte import sensorwerte_erstellen, prognose_und_preis_sensoren
from backend.api.routes.ha_export.anlage_steuerung import steuerungs_sensoren
from backend.api.routes.ha_export.anlage_preise_speicher import preise_speicher_sensoren
from backend.services.ha_export_fenster import baue_fenster_kontext


# Vorlage 8b: `grundlast_sensorwert` ist in anlage_sensorwerte.py umgezogen (die Sensorwerte-Phase ruft es); hier nur der Re-Export
# fuer die Fassade und die Tests.
from backend.api.routes.ha_export.anlage_sensorwerte import grundlast_sensorwert  # noqa: F401 — Re-Export


@dataclass
class _AnlageEingaenge:
    """Kopf des Anlagen-Rechners (RF-75, 5.11.2026): was `_anlage_eingaenge` lädt und alle Phasen danach lesen.

    ``tarife`` ist das Ergebnis von ``lade_tarife_fuer_anlage`` (N-200, Schlüssel je Verwendung), ``strompreis`` dessen
    ``"allgemein"``-Eintrag; ``investitionen`` die heute aktiven, ``alle_investitionen`` alle der Anlage (USt-Satz je Jahr).
    """
    monatsdaten: list
    tarife: dict
    strompreis: object
    investitionen: list
    alle_investitionen: list


async def _anlage_eingaenge(db: AsyncSession, anlage: Anlage) -> Optional[_AnlageEingaenge]:
    """Kopf-Phase (RF-75): Monatsdaten, heutiger Tarif aus dem SoT, Investitionen — in dieser Reihenfolge (SQL-Folge).

    ``None`` = Frühausstieg: ohne eine einzige Monatszeile liefert der Rechner keinen Sensor (``[]``) und lädt weder
    Tarif noch Investitionen.
    """
    # Monatsdaten laden (für Zählerwerte: einspeisung, netzbezug)
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )
    monatsdaten = result.scalars().all()

    if not monatsdaten:
        return None

    # N-200: Der Tarif kommt aus dem SoT, nicht aus einer Handquery. Die alte
    # Form (`order_by(gueltig_ab.desc()).limit(1)`) verlor ZWEI Filter, die
    # `lade_tarife_fuer_anlage` mitbringt:
    #
    #   * `gueltig_bis` — ein ausgelaufener Tarif galt weiter als „aktuellster";
    #   * `verwendung`  — ist der zuletzt angelegte Tarif ein WP- oder
    #     Wallbox-Spezialtarif, wurde er hier als ALLGEMEINER Netzbezugspreis
    #     gelesen. Genau die Fallunterscheidung, die der SoT trifft.
    #
    # Dazu faellt ein `gueltig_ab` in der Zukunft nicht mehr auf heute durch.
    # Dieselbe Umstellung, die D5 fuer den Daten-Checker gefahren hat.
    # Das Ergebnis wird unten als `_tarife` weiterbenutzt (WP-/Wallbox-Zweig) —
    # der zweite Ladevorgang von damals entfaellt damit.
    _tarife = await lade_tarife_fuer_anlage(db, anlage.id)
    strompreis = _tarife["allgemein"]

    # Investitionen laden für ROI-Berechnung
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage.id)
        .where(aktiv_jetzt())
    )
    investitionen = result.scalars().all()
    # Alle Investitionen der Anlage (ohne Heute-Filter) — der USt-Satz eines Jahres zählt, was IN DIESEM JAHR aktiv war
    # (`services/ust_satz.py`, G1, 03.10.2026); eine 2025 stillgelegte Komponente fehlt in `investitionen`.
    alle_investitionen = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id)
    )).scalars().all()
    return _AnlageEingaenge(
        monatsdaten=monatsdaten,
        tarife=_tarife,
        strompreis=strompreis,
        investitionen=investitionen,
        alle_investitionen=alle_investitionen,
    )


def _entpacke(w: dict, _out: dict, *namen: str) -> None:
    """Das `_out`-Entpacken der Vorlage 8b (RF-75): je Name ``if "x" in _out: x = _out["x"]`` — nur die genannten
    Namen, in dieser Reihenfolge, nach ``w`` (die Werte-Tafel des Orchestrators). Ein Name, den die Phase nicht
    gebunden hat, bleibt ungebunden (vorher ``UnboundLocalError`` beim Lesen, jetzt ``KeyError``)."""
    for k in namen:
        if k in _out:
            w[k] = _out[k]


async def _s3b_eingaenge(db: AsyncSession, anlage: Anlage, preis, monatsdaten, heute: date):
    """S3b-Phase (RF-75): Bezugspreis-Reihen und Speicher-Wirkungsgrade — die Eingänge, die ZWEI Phasen brauchen,
    einmal geholt. Rückgabe ``(bezugspreise, speicher_eta)``; ``bezugspreise`` ist ``None``, wenn die Beschaffung scheitert."""
    # ── S3b: die Eingänge, die ZWEI Phasen brauchen — einmal geholt ─────────
    #
    # ⭐ **Warum hier und nicht in der Phase, die sie ausgibt.** Die
    # Bezugspreis-Reihen speisen den Fenster-Kontext (also P2/P4/P5/P7/P8/P9),
    # die Wirkungsgrade speisen P3 in `steuerungs_sensoren` — **beide** also
    # eine Phase, die VOR der Preis-und-Speicher-Phase läuft. Stünde die
    # Beschaffung dort, bräuchte P3 sie vor ihrer Entstehung.
    #
    # ⛔ **Und der Geräte-Rechner kann es auch nicht liefern:**
    # `calculate_investition_sensors` läuft **nach** dem Anlagen-Rechner
    # (`sensoren.py:49/103`), und `/sensors/{id}` wie `/yaml/{id}` rufen nur
    # diesen hier. Eine anlagenweite Größe aus einer Geräte-Schleife zu holen,
    # erreicht die Hälfte der Sichten nie.
    from backend.api.routes.ha_export.anlage_preise_speicher import lade_speicher_wirkungsgrade
    from backend.services.ha_export_bezugspreis import lade_bezugspreise

    try:
        _bezugspreise = await lade_bezugspreise(
            db, anlage, preis, monatsdaten, heute=heute,
        )
    except Exception as e:      # Preise sind eine Zugabe — der Export bleibt grün
        logger.warning(
            "HA-Export Bezugspreise fehlgeschlagen (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        _bezugspreise = None
    _speicher_eta = await lade_speicher_wirkungsgrade(db, anlage, heute=heute)
    return _bezugspreise, _speicher_eta


async def calculate_anlage_sensors(
    db: AsyncSession,
    anlage: Anlage,
    *,
    skip_jitter: bool = False,
    kontext_out: Optional[dict] = None,
    jetzt: Optional[datetime] = None,
) -> list[SensorValue]:
    """
    Berechnet alle Sensor-Werte für eine Anlage.

    WICHTIG: PV-Erzeugung kommt aus InvestitionMonatsdaten (pro PV-Modul),
    NICHT aus Monatsdaten.pv_erzeugung_kwh (Legacy-Feld!).
    Einspeisung/Netzbezug kommen aus Monatsdaten (Zählerwerte).

    ``skip_jitter`` (N-531): ``True`` auf den On-Demand-Wegen (REST-Sichten, Publish-Knopf) — der
    Prognose-Kanon würfelt sonst vor jedem Open-Meteo-Abruf bis zu 30 s Wartezeit (s. `berechne_prognose_export`).

    ``kontext_out`` (S3, 21.09.2026) ist ein **Ausgabe-Dict**: wer es mitgibt, bekommt darin den
    ``FensterKontext`` dieser Anlage zurück (Schlüssel ``fenster``) und reicht ihn an
    ``calculate_investition_sensors`` weiter.

    ⭐ **Warum ein Ausgabe-Parameter und kein zweiter Rückgabewert:** Die Signatur
    ``-> list[SensorValue]`` hat fünf Aufrufer, von denen drei den Kontext nicht brauchen (YAML-Snippet,
    Abwahl-Sicht, Anlagen-Einzelsicht). Ein Tupel hätte alle fünf geändert, damit zwei etwas bekommen.
    Der Kontext ist **eine Rechnung je Publish-Lauf** — Preisreihe, Überschussreihe und Kostenprofil
    entstehen einmal, nicht einmal je Gerät; eine Anlage mit zwei Wärmepumpen und drei sonstigen
    Verbrauchern riefe sonst fünfmal dieselbe Rechnung.

    ``jetzt`` ist die Uhr der Steuerungs- und Plan-Sensoren — ein **Parameter** und kein
    ``datetime.now()`` in der Phase selbst (dasselbe Muster wie ``grundlast_sensorwert``). Ohne
    Angabe liest der Orchestrator die Prozessuhr; eine Probe setzt sie fest und muss damit nicht
    auf die Stunde ihres Laufs wetten (N-167: vier von 24 Stunden rot ohne Code-Änderung).

    **Form (RF-75, 5.11.2026):** reiner Orchestrator — Kopf-Phase `_anlage_eingaenge` (Kontext
    `_AnlageEingaenge`, Frühausstieg ohne Monatsdaten), dann die Vorlage-8b-Phasen in fester Reihenfolge
    («Reihenfolge ist Vertrag»), jede Rückgabe per `_entpacke` in die Werte-Tafel ``w``, dann
    `prognose_und_preis_sensoren`, die Uhr, die S3b-Phase `_s3b_eingaenge`, der Fenster-Kontext, `steuerungs_sensoren`
    und `preise_speicher_sensoren`.
    """
    e = await _anlage_eingaenge(db, anlage)
    if e is None:
        return []
    monatsdaten = e.monatsdaten
    _tarife = e.tarife
    strompreis = e.strompreis
    investitionen = e.investitionen
    alle_investitionen = e.alle_investitionen
    w: dict = {}

    # ── monatsfakten_und_energie (Vorlage 8b: Phase in anlage_energie.py, Schnittstelle 4 ein / 15 aus) ──
    _out = await monatsfakten_und_energie(
        anlage=anlage,
        db=db,
        investitionen=investitionen,
        monatsdaten=monatsdaten,
    )
    _entpacke(w, _out, "_preis_messung", "_tarif_cache", "autarkie", "batterie_entladung", "batterie_ladung",
              "direktverbrauch", "eigenverbrauch", "eigenverbrauch_ohne_verluste", "einspeisung", "erzeugung_bilanz",
              "ev_quote", "fakten", "gesamtverbrauch", "netzbezug", "pv_erzeugung", "spez_ertrag")
    # ── finanz_aggregat (Vorlage 8b: Phase in anlage_energie.py, Schnittstelle 6 ein / 6 aus) ──
    _out = await finanz_aggregat(
        _preis_messung=w["_preis_messung"],
        _tarif_cache=w["_tarif_cache"],
        anlage=anlage,
        db=db,
        fakten=w["fakten"],
        strompreis=strompreis,
    )
    _entpacke(w, _out, "bkw_ersparnis", "einspeise_erloes", "erzeuger_erloes", "ev_ersparnis", "ev_wandlungsverluste")
    w["ev_preis_lookup"] = _out.get("ev_preis_lookup", {})
    _entpacke(w, _out, "sonstige_ausgaben_gesamt", "sonstige_ertraege_gesamt", "sonstige_netto_gesamt")
    # ── investitionen_und_ust (Vorlage 8b: Phase in anlage_energie.py, Schnittstelle 5 ein / 5 aus) ──
    _out = investitionen_und_ust(
        anlage=anlage,
        fakten=w["fakten"],
        investitionen=investitionen,
        monatsdaten=monatsdaten,
        alle_investitionen=alle_investitionen,
        einspeise_erloes=w["einspeise_erloes"],
        ev_ersparnis=w["ev_ersparnis"],
        bkw_ersparnis=w["bkw_ersparnis"],
        erzeuger_erloes=w["erzeuger_erloes"],
        sonstige_netto_gesamt=w["sonstige_netto_gesamt"],
    )
    _entpacke(w, _out, "betriebskosten_ges", "investition_gesamt", "jahres_ertraege_ges", "netto_ertrag",
              "netto_herleitung", "relevante_kosten")
    # ── historische_komponenten (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 6 ein / 10 aus) ──
    _out = await historische_komponenten(
        _tarife=_tarife,
        anlage=anlage,
        db=db,
        investitionen=investitionen,
        monatsdaten=monatsdaten,
        strompreis=strompreis,
    )
    _entpacke(w, _out, "e_autos", "emob_ctx", "historische_inv_daten", "inv_by_id_export", "md_by_periode")
    w["netzbezug_preis_cent"] = _out.get("netzbezug_preis_cent")
    _entpacke(w, _out, "waermepumpen", "wallbox_netzbezug_preis_cent", "wallbox_preis_by_periode",
              "wp_netzbezug_preis_cent", "wp_preis_by_periode")
    # ── alternativkosten_und_co2 (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 11 ein / 5 aus) ──
    _out = alternativkosten_und_co2(
        e_autos=w["e_autos"],
        eigenverbrauch_ohne_verluste=w["eigenverbrauch_ohne_verluste"],
        emob_ctx=w["emob_ctx"],
        ev_preis_lookup=w["ev_preis_lookup"],
        historische_inv_daten=w["historische_inv_daten"],
        inv_by_id_export=w["inv_by_id_export"],
        md_by_periode=w["md_by_periode"],
        netzbezug_preis_cent=w["netzbezug_preis_cent"],
        waermepumpen=w["waermepumpen"],
        wallbox_netzbezug_preis_cent=w["wallbox_netzbezug_preis_cent"],
        wallbox_preis_by_periode=w["wallbox_preis_by_periode"],
        wp_netzbezug_preis_cent=w["wp_netzbezug_preis_cent"],
        wp_preis_by_periode=w["wp_preis_by_periode"],
    )
    _entpacke(w, _out, "bisherige_eauto_ersparnis", "bisherige_wp_ersparnis", "co2_ersparnis", "emob_posten", "wp_posten")
    # ── ertrag_und_amortisation (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 11 ein / 5 aus) ──
    _out = ertrag_und_amortisation(
        betriebskosten_ges=w["betriebskosten_ges"],
        bisherige_eauto_ersparnis=w["bisherige_eauto_ersparnis"],
        bisherige_wp_ersparnis=w["bisherige_wp_ersparnis"],
        emob_posten=w["emob_posten"],
        jahres_ertraege_ges=w["jahres_ertraege_ges"],
        monatsdaten=monatsdaten,
        netto_ertrag=w["netto_ertrag"],
        relevante_kosten=w["relevante_kosten"],
        sonstige_ausgaben_gesamt=w["sonstige_ausgaben_gesamt"],
        sonstige_ertraege_gesamt=w["sonstige_ertraege_gesamt"],
        wp_posten=w["wp_posten"],
    )
    _entpacke(w, _out, "amortisation_jahre", "ersparnis_posten", "jahres_ersparnis", "kapitaleinsatz", "roi_prozent")
    # ── speicher_kpis (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 3 ein / 3 aus) ──
    _out = speicher_kpis(
        batterie_entladung=w["batterie_entladung"],
        batterie_ladung=w["batterie_ladung"],
        investitionen=investitionen,
    )
    _entpacke(w, _out, "speicher_effizienz", "speicher_kapazitaet", "speicher_zyklen")
    # ── sensorwerte_erstellen (Vorlage 8b: Phase in anlage_sensorwerte.py, Schnittstelle 36 ein / 1 aus) ──
    _out = await sensorwerte_erstellen(
        amortisation_jahre=w["amortisation_jahre"],
        anlage=anlage,
        autarkie=w["autarkie"],
        batterie_entladung=w["batterie_entladung"],
        batterie_ladung=w["batterie_ladung"],
        betriebskosten_ges=w["betriebskosten_ges"],
        co2_ersparnis=w["co2_ersparnis"],
        db=db,
        direktverbrauch=w["direktverbrauch"],
        eigenverbrauch=w["eigenverbrauch"],
        einspeise_erloes=w["einspeise_erloes"],
        einspeisung=w["einspeisung"],
        ersparnis_posten=w["ersparnis_posten"],
        erzeugung_bilanz=w["erzeugung_bilanz"],
        ev_ersparnis=w["ev_ersparnis"],
        ev_quote=w["ev_quote"],
        gesamtverbrauch=w["gesamtverbrauch"],
        investition_gesamt=w["investition_gesamt"],
        investitionen=investitionen,
        jahres_ersparnis=w["jahres_ersparnis"],
        jahres_ertraege_ges=w["jahres_ertraege_ges"],
        kapitaleinsatz=w["kapitaleinsatz"],
        monatsdaten=monatsdaten,
        netto_ertrag=w["netto_ertrag"],
        netto_herleitung=w["netto_herleitung"],
        netzbezug=w["netzbezug"],
        pv_erzeugung=w["pv_erzeugung"],
        relevante_kosten=w["relevante_kosten"],
        roi_prozent=w["roi_prozent"],
        sonstige_ausgaben_gesamt=w["sonstige_ausgaben_gesamt"],
        sonstige_ertraege_gesamt=w["sonstige_ertraege_gesamt"],
        sonstige_netto_gesamt=w["sonstige_netto_gesamt"],
        speicher_effizienz=w["speicher_effizienz"],
        speicher_kapazitaet=w["speicher_kapazitaet"],
        speicher_zyklen=w["speicher_zyklen"],
        spez_ertrag=w["spez_ertrag"],
        strompreis=strompreis,
        ev_wandlungsverluste=w["ev_wandlungsverluste"],
    )
    _entpacke(w, _out, "sensor_values")
    sensor_values = w["sensor_values"]
    # ── prognose_und_preis_sensoren (Vorlage 8b: Phase in anlage_sensorwerte.py, Schnittstelle 3 ein / 2 aus) ──
    _out = await prognose_und_preis_sensoren(anlage=anlage, db=db, sensor_values=sensor_values, skip_jitter=skip_jitter)

    # ── steuerungs_sensoren (S2/S3: Phase in anlage_steuerung.py) ───────────
    #
    # Die Uhr wird HIER gelesen und als Parameter weitergegeben (N-167-Muster,
    # wie `grundlast_sensorwert`): eine Phase, die selbst `date.today()` ruft,
    # zwingt jede Probe, auf die Stunde ihres Laufs zu wetten.
    _jetzt = jetzt or datetime.now()

    # ── S3b: die Eingänge, die ZWEI Phasen brauchen — einmal geholt (Phase `_s3b_eingaenge`, Begründung dort) ──
    _heute = _jetzt.date()
    _bezugspreise, _speicher_eta = await _s3b_eingaenge(db, anlage, _out.get("preis"), monatsdaten, _heute)

    _fenster_ctx = baue_fenster_kontext(
        _out.get("prognose"), _out.get("preis"), _bezugspreise, jetzt=_jetzt,
    )
    await steuerungs_sensoren(
        anlage=anlage,
        db=db,
        sensor_values=sensor_values,
        prognose=_out.get("prognose"),
        preis=_out.get("preis"),
        fenster_ctx=_fenster_ctx,
        heute=_heute,
        jetzt_stunde=_jetzt.hour,
        speicher_eta=_speicher_eta,
    )
    await preise_speicher_sensoren(
        anlage=anlage,
        sensor_values=sensor_values,
        prognose=_out.get("prognose"),
        preis=_out.get("preis"),
        fenster_ctx=_fenster_ctx,
        bezugspreise=_bezugspreise,
        speicher_eta=_speicher_eta,
        heute=_heute,
        jetzt_stunde=_jetzt.hour,
    )
    if kontext_out is not None:
        kontext_out["fenster"] = _fenster_ctx
    return sensor_values
