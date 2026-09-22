"""HA-Export — die Anlagen-Sensoren: `calculate_anlage_sensors` (Energie, Finanzen, CO₂, Prognose, Preis, Grundlast je
Anlage aus den Monats-Fakten, ADR-002/P10).

Seit Vorlage 8b (18.09.2026) ist der Rechner ein Orchestrator: Kopf (Monatsdaten, Frühausstieg, heutiger Tarif,
Investitionen) und `return` stehen hier, die neun Phasen liegen byte-identisch in `anlage_energie.py` (Monatsfakten und
Energie, Finanz-Aggregat, Investitionen und USt), `anlage_komponenten.py` (historische Komponenten, Alternativkosten und
CO₂, Ertrag und Amortisation, Speicher-KPIs) und `anlage_sensorwerte.py` (Sensorwerte, Prognose und Preis; dort auch
`grundlast_sensorwert`, hier re-exportiert). Schnittstelle je Phase: Schlüsselwort-Parameter hinein, Rückgabe-Dict heraus;
Gate ist der Golden Master `plans/skript-golden-master-ha-export.py`.
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
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
from backend.core.field_definitions import get_emob_pv_netz_kwh
from backend.core.berechnungen.kapitalrechnung import (
    ErsparnisPosten,
    annahme_dauer_text,
    erklaerung_jahres_ersparnis,
    jahres_ersparnis_euro,
    kapitaleinsatz_euro,
)
from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis_periode,
    eigener_verbrauch_l_100km,
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
from backend.api.routes.ha_export.emob import _build_emob_pool_ctx, _emob_month_share, _reichere_emob_imd_an
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
    """
    # Monatsdaten laden (für Zählerwerte: einspeisung, netzbezug)
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )
    monatsdaten = result.scalars().all()

    if not monatsdaten:
        return []

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

    # ── monatsfakten_und_energie (Vorlage 8b: Phase in anlage_energie.py, Schnittstelle 4 ein / 15 aus) ──
    _out = await monatsfakten_und_energie(
        anlage=anlage,
        db=db,
        investitionen=investitionen,
        monatsdaten=monatsdaten,
    )
    if "_preis_messung" in _out: _preis_messung = _out["_preis_messung"]
    if "_tarif_cache" in _out: _tarif_cache = _out["_tarif_cache"]
    if "autarkie" in _out: autarkie = _out["autarkie"]
    if "batterie_entladung" in _out: batterie_entladung = _out["batterie_entladung"]
    if "batterie_ladung" in _out: batterie_ladung = _out["batterie_ladung"]
    if "direktverbrauch" in _out: direktverbrauch = _out["direktverbrauch"]
    if "eigenverbrauch" in _out: eigenverbrauch = _out["eigenverbrauch"]
    if "einspeisung" in _out: einspeisung = _out["einspeisung"]
    if "erzeugung_bilanz" in _out: erzeugung_bilanz = _out["erzeugung_bilanz"]
    if "ev_quote" in _out: ev_quote = _out["ev_quote"]
    if "fakten" in _out: fakten = _out["fakten"]
    if "gesamtverbrauch" in _out: gesamtverbrauch = _out["gesamtverbrauch"]
    if "netzbezug" in _out: netzbezug = _out["netzbezug"]
    if "pv_erzeugung" in _out: pv_erzeugung = _out["pv_erzeugung"]
    if "spez_ertrag" in _out: spez_ertrag = _out["spez_ertrag"]
    # ── finanz_aggregat (Vorlage 8b: Phase in anlage_energie.py, Schnittstelle 6 ein / 6 aus) ──
    _out = await finanz_aggregat(
        _preis_messung=_preis_messung,
        _tarif_cache=_tarif_cache,
        anlage=anlage,
        db=db,
        fakten=fakten,
        strompreis=strompreis,
    )
    if "einspeise_erloes" in _out: einspeise_erloes = _out["einspeise_erloes"]
    if "ev_ersparnis" in _out: ev_ersparnis = _out["ev_ersparnis"]
    if "netto_ertrag" in _out: netto_ertrag = _out["netto_ertrag"]
    if "sonstige_ausgaben_gesamt" in _out: sonstige_ausgaben_gesamt = _out["sonstige_ausgaben_gesamt"]
    if "sonstige_ertraege_gesamt" in _out: sonstige_ertraege_gesamt = _out["sonstige_ertraege_gesamt"]
    if "sonstige_netto_gesamt" in _out: sonstige_netto_gesamt = _out["sonstige_netto_gesamt"]
    # ── investitionen_und_ust (Vorlage 8b: Phase in anlage_energie.py, Schnittstelle 5 ein / 5 aus) ──
    _out = investitionen_und_ust(
        anlage=anlage,
        fakten=fakten,
        investitionen=investitionen,
        monatsdaten=monatsdaten,
        netto_ertrag=netto_ertrag,
    )
    if "betriebskosten_ges" in _out: betriebskosten_ges = _out["betriebskosten_ges"]
    if "investition_gesamt" in _out: investition_gesamt = _out["investition_gesamt"]
    if "jahres_ertraege_ges" in _out: jahres_ertraege_ges = _out["jahres_ertraege_ges"]
    if "netto_ertrag" in _out: netto_ertrag = _out["netto_ertrag"]
    if "relevante_kosten" in _out: relevante_kosten = _out["relevante_kosten"]
    # ── historische_komponenten (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 6 ein / 10 aus) ──
    _out = await historische_komponenten(
        _tarife=_tarife,
        anlage=anlage,
        db=db,
        investitionen=investitionen,
        monatsdaten=monatsdaten,
        strompreis=strompreis,
    )
    if "e_autos" in _out: e_autos = _out["e_autos"]
    if "emob_ctx" in _out: emob_ctx = _out["emob_ctx"]
    if "historische_inv_daten" in _out: historische_inv_daten = _out["historische_inv_daten"]
    if "inv_by_id_export" in _out: inv_by_id_export = _out["inv_by_id_export"]
    if "md_by_periode" in _out: md_by_periode = _out["md_by_periode"]
    if "waermepumpen" in _out: waermepumpen = _out["waermepumpen"]
    if "wallbox_netzbezug_preis_cent" in _out: wallbox_netzbezug_preis_cent = _out["wallbox_netzbezug_preis_cent"]
    if "wallbox_preis_by_periode" in _out: wallbox_preis_by_periode = _out["wallbox_preis_by_periode"]
    if "wp_netzbezug_preis_cent" in _out: wp_netzbezug_preis_cent = _out["wp_netzbezug_preis_cent"]
    if "wp_preis_by_periode" in _out: wp_preis_by_periode = _out["wp_preis_by_periode"]
    # ── alternativkosten_und_co2 (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 11 ein / 5 aus) ──
    _out = alternativkosten_und_co2(
        e_autos=e_autos,
        eigenverbrauch=eigenverbrauch,
        emob_ctx=emob_ctx,
        historische_inv_daten=historische_inv_daten,
        inv_by_id_export=inv_by_id_export,
        md_by_periode=md_by_periode,
        waermepumpen=waermepumpen,
        wallbox_netzbezug_preis_cent=wallbox_netzbezug_preis_cent,
        wallbox_preis_by_periode=wallbox_preis_by_periode,
        wp_netzbezug_preis_cent=wp_netzbezug_preis_cent,
        wp_preis_by_periode=wp_preis_by_periode,
    )
    if "bisherige_eauto_ersparnis" in _out: bisherige_eauto_ersparnis = _out["bisherige_eauto_ersparnis"]
    if "bisherige_wp_ersparnis" in _out: bisherige_wp_ersparnis = _out["bisherige_wp_ersparnis"]
    if "co2_ersparnis" in _out: co2_ersparnis = _out["co2_ersparnis"]
    if "emob_posten" in _out: emob_posten = _out["emob_posten"]
    if "wp_posten" in _out: wp_posten = _out["wp_posten"]
    # ── ertrag_und_amortisation (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 11 ein / 5 aus) ──
    _out = ertrag_und_amortisation(
        betriebskosten_ges=betriebskosten_ges,
        bisherige_eauto_ersparnis=bisherige_eauto_ersparnis,
        bisherige_wp_ersparnis=bisherige_wp_ersparnis,
        emob_posten=emob_posten,
        jahres_ertraege_ges=jahres_ertraege_ges,
        monatsdaten=monatsdaten,
        netto_ertrag=netto_ertrag,
        relevante_kosten=relevante_kosten,
        sonstige_ausgaben_gesamt=sonstige_ausgaben_gesamt,
        sonstige_ertraege_gesamt=sonstige_ertraege_gesamt,
        wp_posten=wp_posten,
    )
    if "amortisation_jahre" in _out: amortisation_jahre = _out["amortisation_jahre"]
    if "ersparnis_posten" in _out: ersparnis_posten = _out["ersparnis_posten"]
    if "jahres_ersparnis" in _out: jahres_ersparnis = _out["jahres_ersparnis"]
    if "kapitaleinsatz" in _out: kapitaleinsatz = _out["kapitaleinsatz"]
    if "roi_prozent" in _out: roi_prozent = _out["roi_prozent"]
    # ── speicher_kpis (Vorlage 8b: Phase in anlage_komponenten.py, Schnittstelle 3 ein / 3 aus) ──
    _out = speicher_kpis(
        batterie_entladung=batterie_entladung,
        batterie_ladung=batterie_ladung,
        investitionen=investitionen,
    )
    if "speicher_effizienz" in _out: speicher_effizienz = _out["speicher_effizienz"]
    if "speicher_kapazitaet" in _out: speicher_kapazitaet = _out["speicher_kapazitaet"]
    if "speicher_zyklen" in _out: speicher_zyklen = _out["speicher_zyklen"]
    # ── sensorwerte_erstellen (Vorlage 8b: Phase in anlage_sensorwerte.py, Schnittstelle 36 ein / 1 aus) ──
    _out = await sensorwerte_erstellen(
        amortisation_jahre=amortisation_jahre,
        anlage=anlage,
        autarkie=autarkie,
        batterie_entladung=batterie_entladung,
        batterie_ladung=batterie_ladung,
        betriebskosten_ges=betriebskosten_ges,
        co2_ersparnis=co2_ersparnis,
        db=db,
        direktverbrauch=direktverbrauch,
        eigenverbrauch=eigenverbrauch,
        einspeise_erloes=einspeise_erloes,
        einspeisung=einspeisung,
        ersparnis_posten=ersparnis_posten,
        erzeugung_bilanz=erzeugung_bilanz,
        ev_ersparnis=ev_ersparnis,
        ev_quote=ev_quote,
        gesamtverbrauch=gesamtverbrauch,
        investition_gesamt=investition_gesamt,
        investitionen=investitionen,
        jahres_ersparnis=jahres_ersparnis,
        jahres_ertraege_ges=jahres_ertraege_ges,
        kapitaleinsatz=kapitaleinsatz,
        monatsdaten=monatsdaten,
        netto_ertrag=netto_ertrag,
        netzbezug=netzbezug,
        pv_erzeugung=pv_erzeugung,
        relevante_kosten=relevante_kosten,
        roi_prozent=roi_prozent,
        sonstige_ausgaben_gesamt=sonstige_ausgaben_gesamt,
        sonstige_ertraege_gesamt=sonstige_ertraege_gesamt,
        sonstige_netto_gesamt=sonstige_netto_gesamt,
        speicher_effizienz=speicher_effizienz,
        speicher_kapazitaet=speicher_kapazitaet,
        speicher_zyklen=speicher_zyklen,
        spez_ertrag=spez_ertrag,
        strompreis=strompreis,
    )
    if "sensor_values" in _out: sensor_values = _out["sensor_values"]
    # ── prognose_und_preis_sensoren (Vorlage 8b: Phase in anlage_sensorwerte.py, Schnittstelle 3 ein / 2 aus) ──
    _out = await prognose_und_preis_sensoren(anlage=anlage, db=db, sensor_values=sensor_values, skip_jitter=skip_jitter)

    # ── steuerungs_sensoren (S2/S3: Phase in anlage_steuerung.py) ───────────
    #
    # Die Uhr wird HIER gelesen und als Parameter weitergegeben (N-167-Muster,
    # wie `grundlast_sensorwert`): eine Phase, die selbst `date.today()` ruft,
    # zwingt jede Probe, auf die Stunde ihres Laufs zu wetten.
    _jetzt = jetzt or datetime.now()

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

    _heute = _jetzt.date()
    try:
        _bezugspreise = await lade_bezugspreise(
            db, anlage, _out.get("preis"), monatsdaten, heute=_heute,
        )
    except Exception as e:      # Preise sind eine Zugabe — der Export bleibt grün
        logger.warning(
            "HA-Export Bezugspreise fehlgeschlagen (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        _bezugspreise = None
    _speicher_eta = await lade_speicher_wirkungsgrade(db, anlage, heute=_heute)

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
