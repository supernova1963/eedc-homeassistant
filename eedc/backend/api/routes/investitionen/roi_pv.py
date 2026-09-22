"""ROI-Dashboard — die PV-Seite: PV-Einsparung aus den Monats-Fakten (P7/P10) mit Hochrechnung, Speicher-IST-Aggregate
(Etappe B/C, #264), die F-37-Kuerzung des PV-Topfs um den Speicher-Anteil, die Zeilen der PV-Systeme (Traegergeraet +
Module + DC-Speicher) und die Orphan-Module.
"""
# Vorlage 5b des Refactorings grosser Dateien (18.09.2026): Phasen des Endpunkts
# `roi.py::get_roi_dashboard` byte-identisch als Funktionen, Schnittstelle als Schluesselwort-
# Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel — Gate ist
# `plans/skript-golden-master-investitionen.py` (alte gegen neue Antworten, bitgleich).
# ⚠ Dieses Modul importiert Helfer und Schemas aus `roi.py`; `roi.py` importiert die Phasen
# deshalb erst IM Endpunkt (sonst Importzyklus) — dieselbe Bauform wie die Lazy-Importe der
# Energieprofil-Routen.

from typing import Optional, Any
from sqlalchemy import select, func
from datetime import date
from backend.core.investition_kennwerte import (
    get_bkw_kwp,
    get_pv_kwp,
    get_speicher_kapazitaet_kwh,
    get_speicher_kopplung,
    get_speicher_kopplung_gepflegt,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.core.berechnungen.erzeuger_traeger import traegt_erzeugungsgroessen_selbst
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.core.investition_parameter import (
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    SPEICHER_KOPPLUNG_DC,
)
from backend.core.berechnungen.speicher_wirtschaftlichkeit import aggregiere_speicher_ist
from backend.services.speicher_wirtschaftlichkeit import (
    EffektiverLadepreisErgebnis,
    berechne_effektiver_ladepreis,
    berechne_ist_wirkungsgrad,
    wirkungsgrad_ist_fuer_speicher,
)
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH, berechne_roi
from backend.services.monats_fakten import lade_monats_fakten
from backend.core.berechnungen import einspeise_erloes_euro, relevante_kosten_aus_investitionen
from backend.core.berechnungen.kapitalrechnung import annahme_dauer_text, kapitaleinsatz_euro
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.api.routes.investitionen.roi import (
    ROIBerechnung,
    ROIKomponente,
    _SpeicherRoi,
    _bkw_pauschal_beitrag,
    _speicher_roi,
)


async def pv_einsparung_und_speicher_ist(
    *,
    _anlage_fakten,
    anlage_id,
    db,
    einspeiseverguetung_cent,
    investitionen,
    jahr,
    strompreis_cent,
):
    """PV-Einsparung einmal berechnen (Jahresdurchschnitt oder Einzeljahr, PVGIS-gewichtet), Speicher-IST-Aggregate,
    effektiver Ladepreis und IST-Wirkungsgrad je Speicher; legt die Summen-Akkumulatoren an.

    Aus `get_roi_dashboard` Zeilen 953-1239 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 5b.
    """
    # ==========================================================================
    # Phase 2: Hilfsfunktion für PV-Erzeugungsdaten
    # ==========================================================================

    async def berechne_pv_einsparung_aus_monatsdaten() -> tuple[float, float, dict]:
        """
        Berechnet PV-Einsparung für alle PV-Module gemeinsam.

        Die PV-Erzeugung kommt aus den Monats-Fakten (ADR-002/**P10**), die sie
        nach **P7** auflösen: gemessene Pro-Modul-Werte, und wo nur das
        Anlagen-Aggregat (`Monatsdaten.pv_erzeugung_kwh`) gepflegt ist, dessen
        kWp-Verteilung. Dieser Docstring nannte das Aggregat bis 2026-07-31 ein
        „Legacy-Feld!" — genau die Annahme, die P7 widerlegt hat: es ist kein
        Legacy, sondern der einzige Wert bei manueller Pflege und beim Import
        mit einem Gesamt-PV-Sensor. Die rohe IMD-Summe daneben lieferte dort 0
        und damit 32,00 € statt 212,00 € Jahres-Einsparung — der ROI-Fortschritt
        und die Amortisation standen um 85 % zu niedrig (Befund F-5).

        Einspeisung/Netzbezug kommen weiterhin aus Monatsdaten (Zählerwerte).
        """
        # 1. PV-Module IDs ermitteln
        # Issue #123: historische PV-Einsparung — keine aktiv-Filterung, damit
        # spätere Stilllegung Vergangenheit nicht entfernt.
        pv_ids_result = await db.execute(
            select(Investition.id)
            .where(Investition.anlage_id == anlage_id)
            .where(Investition.typ == "pv-module")
        )
        pv_module_ids = [row[0] for row in pv_ids_result.all()]

        # 2. Einspeisung aus Monatsdaten (Zählerwert)
        md_query = select(
            Monatsdaten.monat,
            Monatsdaten.jahr,
            func.sum(Monatsdaten.einspeisung_kwh).label('einspeisung'),
        ).where(Monatsdaten.anlage_id == anlage_id)

        if jahr is not None:
            md_query = md_query.where(Monatsdaten.jahr == jahr)

        # 3. PV-Erzeugung je Monat über die Monats-Fakten (ADR-002/P10)
        async def get_pv_erzeugung(filter_jahr: Optional[int] = None) -> dict[tuple[int, int], float]:
            """Modul-PV je Monat, kanonisch aufgelöst (P7).

            `erzeugung.pv_module_kwh` ist bewusst die **Modul**-Summe, nicht
            `pv_kwh`: das Balkonkraftwerk hat in diesem Dashboard eine eigene
            ROI-Zeile (`standalone`), seine Erzeugung zählte hier sonst zweimal.
            `None` heißt N42-Lücke (mindestens ein aktives Modul ohne Wert und
            ohne Aggregat) und wird — wie bisher — als 0 verrechnet.
            """
            if not pv_module_ids:
                return {}

            # ⭐ Dieselbe Anlage, dasselbe Fenster, dieselbe Schicht — die Fakten
            # stehen seit dem Kopf dieser Funktion schon da (`_anlage_fakten`).
            # Sie ein zweites Mal zu bauen kostete an der produktiven Anlage die
            # Haelfte der ROI-Laufzeit (gemessen 15.09.2026: 3,9 s gesamt).
            if filter_jahr == jahr:
                fakten = _anlage_fakten
            else:
                fakten = await lade_monats_fakten(
                    db, anlage_id,
                    von=(filter_jahr, 1) if filter_jahr is not None else None,
                    bis=(filter_jahr, 12) if filter_jahr is not None else None,
                )
            return {
                f.schluessel: (f.erzeugung.pv_module_kwh or 0.0) for f in fakten
            }

        if jahr is None:
            # Alle Jahre: Jahresdurchschnitt
            md_count_query = select(
                func.count().label('total_records'),
                func.count(func.distinct(Monatsdaten.jahr)).label('anzahl_jahre')
            ).where(Monatsdaten.anlage_id == anlage_id)
            count_result = await db.execute(md_count_query)
            count_row = count_result.one()
            total_records = count_row.total_records
            anzahl_jahre = count_row.anzahl_jahre or 1

            md_query = md_query.group_by(Monatsdaten.monat)
            md_result = await db.execute(md_query)
            md_by_month = {r.monat: r for r in md_result.all()}

            # PV-Erzeugung aus InvestitionMonatsdaten
            pv_erzeugung_data = await get_pv_erzeugung()
            total_erzeugung = sum(pv_erzeugung_data.values())

            total_einspeisung = sum(r.einspeisung or 0 for r in md_by_month.values())
            anzahl_monate = len(md_by_month)

            if anzahl_monate > 0 and anzahl_jahre > 0:
                avg_einspeisung = total_einspeisung / anzahl_jahre
                avg_erzeugung = total_erzeugung / anzahl_jahre
                avg_monate_pro_jahr = total_records / anzahl_jahre

                if avg_monate_pro_jahr < 12:
                    faktor = 12.0 / avg_monate_pro_jahr
                    methode = 'durchschnitt_hochgerechnet'
                else:
                    faktor = 1.0
                    methode = 'durchschnitt'

                einspeisung_jahr = avg_einspeisung * faktor
                erzeugung_jahr = avg_erzeugung * faktor
                # Eigenverbrauch = Erzeugung - Einspeisung
                eigenverbrauch_jahr = max(0, erzeugung_jahr - einspeisung_jahr)
                hinweis = f'Jahresdurchschnitt (Ø aus {anzahl_jahre} Jahren)'
                if methode == 'durchschnitt_hochgerechnet':
                    hinweis += ', hochgerechnet auf 12 Monate'
            else:
                return 0, 0, {'hinweis': 'Keine Monatsdaten vorhanden'}
        else:
            # Einzelnes Jahr
            md_query = md_query.group_by(Monatsdaten.monat)
            md_result = await db.execute(md_query)
            md_by_month = {r.monat: r for r in md_result.all()}

            # PV-Erzeugung aus InvestitionMonatsdaten für dieses Jahr
            pv_erzeugung_data = await get_pv_erzeugung(jahr)
            total_erzeugung = sum(pv_erzeugung_data.values())

            total_einspeisung = sum(r.einspeisung or 0 for r in md_by_month.values())
            anzahl_monate = len(md_by_month)
            vorhandene_monate = sorted(md_by_month.keys())

            if anzahl_monate > 0:
                # PVGIS-Hochrechnung versuchen
                pvgis_prognose = await lade_aktive_prognose(db, anlage_id)

                methode = 'linear'
                faktor = 12.0 / anzahl_monate

                if pvgis_prognose and pvgis_prognose.monatswerte and anzahl_monate < 12:
                    pvgis_monatswerte = pvgis_prognose.monatswerte
                    # Gespeicherte Keys sind 'e_m'/'monat' (siehe pvgis.py); zuvor
                    # las dieser Pfad 'E_m'/'month' → Summe immer 0 → PVGIS-Gewichtung
                    # griff nie, stiller Fallback auf lineare Hochrechnung.
                    pvgis_jahres_summe = sum(m.get('e_m', 0) for m in pvgis_monatswerte)
                    if pvgis_jahres_summe > 0:
                        pvgis_vorhandene_summe = sum(
                            m.get('e_m', 0) for m in pvgis_monatswerte
                            if m.get('monat', 0) in vorhandene_monate
                        )
                        if pvgis_vorhandene_summe > 0:
                            faktor = 1.0 / (pvgis_vorhandene_summe / pvgis_jahres_summe)
                            methode = 'pvgis'

                einspeisung_jahr = total_einspeisung * faktor
                erzeugung_jahr = total_erzeugung * faktor
                # Eigenverbrauch = Erzeugung - Einspeisung
                eigenverbrauch_jahr = max(0, erzeugung_jahr - einspeisung_jahr)

                if methode == 'pvgis':
                    hinweis = f'PVGIS-gewichtete Hochrechnung für {jahr} ({anzahl_monate} Monate)'
                elif anzahl_monate >= 12:
                    hinweis = f'Berechnet aus {anzahl_monate} Monaten für {jahr}'
                else:
                    hinweis = f'Lineare Hochrechnung für {jahr} aus {anzahl_monate} Monaten'
            else:
                return 0, 0, {'hinweis': f'Keine Monatsdaten für {jahr}'}

        # Eigenverbrauch ableiten wenn nicht vorhanden
        if eigenverbrauch_jahr == 0 and erzeugung_jahr > 0:
            eigenverbrauch_jahr = erzeugung_jahr - einspeisung_jahr

        # Einsparung berechnen. §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh
        # = None, weil auf Monatsdaten-Aggregat-Ebene keine Negativpreis-Spalte
        # vorliegt → volle Einspeisung wie zuvor (verhaltensneutral).
        einspeise_erloes = einspeise_erloes_euro(
            einspeisung_jahr, None, einspeiseverguetung_cent
        ).erloes_euro
        ev_ersparnis = eigenverbrauch_jahr * strompreis_cent / 100
        jahres_einsparung = einspeise_erloes + ev_ersparnis
        co2 = erzeugung_jahr * CO2_FAKTOR_STROM_KG_KWH

        detail = {
            'einspeisung_kwh_jahr': round(einspeisung_jahr, 0),
            'eigenverbrauch_kwh_jahr': round(eigenverbrauch_jahr, 0),
            'erzeugung_kwh_jahr': round(erzeugung_jahr, 0),
            'einspeise_erloes_euro': round(einspeise_erloes, 2),
            'ev_ersparnis_euro': round(ev_ersparnis, 2),
            'hinweis': hinweis,
        }

        return jahres_einsparung, co2, detail

    # ==========================================================================
    # Phase 3: Berechne ROI für PV-Systeme (aggregiert)
    # ==========================================================================

    def _relevante_kosten(*invs) -> float:
        """Relevante Kosten über den Layer-SoT (ADR-001) — je Position geklemmt.

        N-137: Hier stand `kosten − alternativ` an sechs Stellen, ohne Klemmung.
        Eine Position, deren gepflegte Alternative teurer war als sie selbst,
        senkte damit die relevanten Kosten der ganzen Anlage — und der
        Amortisations-Fortschritt, der in derselben Sicht daneben steht, rechnet
        über `relevante_kosten_aus_investitionen` mit `max(0, …)`. Zwei Nenner in
        einer Sicht sind genau das, was dieses Paket beseitigt.
        """
        return relevante_kosten_aus_investitionen(invs)

    berechnungen: list[ROIBerechnung] = []
    gesamt_investition = 0.0
    gesamt_relevante = 0.0
    # F-19: kumulierte sonstige AUSGABEN (positiver Betrag). Sie gehen NICHT in
    # `gesamt_einsparung`, sondern über `kapitaleinsatz_euro` in den Nenner.
    # Bauschritt 7: die ERTRÄGE ebenso, dort mindernd — SoT
    # `core/berechnungen/kapitalrechnung.py`.
    gesamt_sonstige_ausgaben = 0.0
    gesamt_sonstige_ertraege = 0.0
    gesamt_einsparung = 0.0
    gesamt_co2 = 0.0
    # Konzept §5/§8-6: Summe der Betriebskosten, die in DIESER Zahl abgezogen
    # wurden — Grundlage der Annahme-Zeile. Bewusst am Ort des Abzugs
    # mitsummiert statt hinterher neu über die Investitionen gebildet: die
    # Annahme muss die Rechnung beschreiben, nicht die Datenlage.
    gesamt_betriebskosten = 0.0

    # Etappe B (#264): Speicher-IST-Aggregate einmal laden — sowohl für
    # DC-gekoppelte (Phase 3) als auch standalone AC-Speicher (Phase 5).
    # Pro Speicher wird `entladung_kwh` und `ladung_netz_kwh` aus allen
    # aktiven Monatsdaten summiert und auf ein Jahr hochgerechnet, damit
    # das ROI-Modell die echte PV/Netz-Aufteilung nutzen kann statt der
    # impliziten 100%-PV-Annahme.
    #
    # Etappe C (#264): zusätzlich aus dem stündlichen TagesEnergieProfil
    # den effektiven Ø-Netzladepreis (Tibber/aWATTar) und den SoC-
    # korrigierten IST-Wirkungsgrad ermitteln. Beide werden an den Spread-
    # Service durchgereicht und überstimmen den Param-Wert.
    speicher_invs_alle = [i for i in investitionen if i.typ == InvestitionTyp.SPEICHER.value]
    speicher_ist_by_inv: dict[int, "SpeicherIstAggregat | None"] = {}
    speicher_ladepreis_anlage: Optional[EffektiverLadepreisErgebnis] = None
    speicher_eta_by_inv: dict[int, "WirkungsgradErgebnis | None"] = {}
    if speicher_invs_alle:
        speicher_ids = [i.id for i in speicher_invs_alle]
        sp_imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(speicher_ids))
        )
        sp_imd_by_inv: dict[int, list[InvestitionMonatsdaten]] = {}
        for imd in sp_imd_result.scalars().all():
            sp_imd_by_inv.setdefault(imd.investition_id, []).append(imd)
        for sp in speicher_invs_alle:
            # Filter analog #236: Stilllegung/Inbetriebnahme respektieren.
            aktive_daten = [
                (imd.verbrauch_daten or {})
                for imd in sp_imd_by_inv.get(sp.id, [])
                if sp.ist_aktiv_im_monat(imd.jahr, imd.monat)
            ]
            speicher_ist_by_inv[sp.id] = aggregiere_speicher_ist(aktive_daten)

        # Etappe C: TEP-Lookups einmalig pro Anlage. Periode = älteste
        # Speicher-Inbetriebnahme bis heute (oder neueste Stilllegung).
        installs = [sp.anschaffungsdatum for sp in speicher_invs_alle if sp.anschaffungsdatum]
        stilllegungen = [sp.stilllegungsdatum for sp in speicher_invs_alle if sp.stilllegungsdatum]
        if installs:
            periode_von = min(installs)
            periode_bis = max(stilllegungen) if stilllegungen and len(stilllegungen) == len(speicher_invs_alle) else date.today()
            speicher_ladepreis_anlage = await berechne_effektiver_ladepreis(
                db, anlage_id=anlage_id, von=periode_von, bis=periode_bis,
            )

            # Pro Speicher η-IST aus IMD-Aggregaten und (bei kurzem Fenster)
            # SoC-Werten am Periodenrand.
            for sp in speicher_invs_alle:
                # ⭐ **Seit S3b über den SoT-Helper** (22.09.2026): dieselben vier
                # Schritte — Aggregat, `None`-Wache, nutzbare Kapazität,
                # `berechne_ist_wirkungsgrad` — standen hier, im
                # Speicher-Dashboard und im Komponenten-Hub je einmal
                # ausgeschrieben. Mit dem HA-Export wäre ein vierter Nachbau
                # dazugekommen, und der erste, dessen Ergebnis als ct-Betrag in
                # eine Automation geht. **Identisches Verhalten:** der Helfer
                # liefert `None` genau dann, wenn `aggregiere_speicher_ist` es
                # täte — also in dem Fall, in dem hier bisher `continue` stand.
                erg = await wirkungsgrad_ist_fuer_speicher(
                    db,
                    anlage_id=anlage_id,
                    speicher=sp,
                    verbrauch_daten_je_monat=[
                        (imd.verbrauch_daten or {})
                        for imd in sp_imd_by_inv.get(sp.id, [])
                        if sp.ist_aktiv_im_monat(imd.jahr, imd.monat)
                    ],
                    von=periode_von,
                    bis=periode_bis,
                )
                if erg is not None:
                    speicher_eta_by_inv[sp.id] = erg

    # PV-Einsparung einmal berechnen (wird auf Module verteilt)
    pv_jahres_einsparung, pv_co2, pv_detail = await berechne_pv_einsparung_aus_monatsdaten()
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_relevante_kosten", "berechnungen", "gesamt_betriebskosten", "gesamt_co2", "gesamt_einsparung", "gesamt_investition", "gesamt_relevante", "gesamt_sonstige_ausgaben", "gesamt_sonstige_ertraege", "pv_co2", "pv_detail", "pv_jahres_einsparung", "speicher_eta_by_inv", "speicher_invs_alle", "speicher_ist_by_inv", "speicher_ladepreis_anlage",) if k in _loc}


def pv_systeme_zeilen(
    *,
    _relevante_kosten,
    _sonstige_ausgaben_kumuliert_fuer,
    _sonstige_ertraege_kumuliert_fuer,
    _treppe_zeile,
    basis_jahr,
    berechnungen,
    einspeiseverguetung_cent,
    gesamt_betriebskosten,
    gesamt_co2,
    gesamt_einsparung,
    gesamt_investition,
    gesamt_relevante,
    gesamt_sonstige_ausgaben,
    gesamt_sonstige_ertraege,
    investitionen,
    orphan_pv_module,
    pv_co2,
    pv_detail,
    pv_jahres_einsparung,
    pv_systeme,
    speicher_eta_by_inv,
    speicher_invs_alle,
    speicher_ist_by_inv,
    speicher_ladepreis_anlage,
    standalone,
    strompreis_cent,
):
    """F-37: der Speicher-Anteil wird AUS dem PV-Topf gekuerzt; dann je PV-System (Kopf + Module + DC-Speicher) die
    ROI-Zeile mit Komponenten, Kapitaleinsatz und Treppe.

    Aus `get_roi_dashboard` Zeilen 1240-1607 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 5b.
    """
    # ==========================================================================
    # F-37: Der Speicher bekommt seinen Anteil AUS dem PV-Topf, nicht daneben
    # ==========================================================================
    #
    # `pv_jahres_einsparung` ist `Eigenverbrauch × Strompreis + Einspeisung ×
    # Vergütung` — die **vollständige** Ersparnis der Anlage. Und
    # `Eigenverbrauch = Erzeugung − Einspeisung` enthält alles, was durch den
    # Speicher lief: was in den Akku ging und wieder heraus, wurde nicht
    # eingespeist. (Am Code belegt: `berechnungen/verbrauch.py` zieht die
    # Speicherladung ab, **um** den Direktverbrauch zu erhalten — sie steckt
    # also in `pv − einspeisung`.)
    #
    # Bis v4.0.19 stellte die ROI-Sicht den Speicher-Spread **daneben** und
    # addierte beides. An der gemeldeten Anlage (#381) waren das 2.133 kWh ×
    # 31,95 ct **plus** 717,1 kWh × 23,95 ct — **55,9 ct für eine
    # Kilowattstunde, die einmal geflossen ist**: 895,64 € statt 723,89 €,
    # Amortisation 2,24 statt 2,77 Jahre.
    #
    # Der Weg ist **Zerlegung statt Addition** — dieselbe Doktrin, die
    # `aussichten/finanz_zerlegung.py::roi_und_fortschritt` seit 2026-08-10 anwendet („niemand rechnet eine
    # Komponenten-Ersparnis ein zweites Mal"). Solange die eine Sicht addiert
    # und die andere zerlegt, nennen zwei Sichten derselben Anlage verschiedene
    # Zahlen — die Drift-Klasse hinter P9/P10.
    #
    # ⚠ **Nur der PV-Anteil wird gekürzt.** Der Netz-Anteil (Arbitrage) entsteht
    # aus der Tarifdifferenz beim Laden aus dem Netz und steckt gerade **nicht**
    # im PV-Eigenverbrauch; ihn mitzukürzen nähme einem Arbitrage-Speicher echte
    # Ersparnis. Die Trennung liefert `berechne_speicher_ersparnis` bereits
    # fertig (`pv_anteil_euro` / `netz_anteil_euro`).
    #
    # ⚠ **Betrifft ALLE Speicher**, nicht nur die am Trägergerät: der häufigste
    # Fall ist der eigenständige AC-Speicher ohne Zuordnung, und der bekommt
    # seine Zeile in der Typkette weiter unten. Deshalb steht die Kürzung hier,
    # vor **beiden** Zweigen.
    speicher_roi_by_inv: dict[int, _SpeicherRoi] = {
        sp.id: _speicher_roi(
            sp,
            strompreis_cent=strompreis_cent,
            einspeiseverguetung_cent=einspeiseverguetung_cent,
            ist_aggregat=speicher_ist_by_inv.get(sp.id),
            eff_ladepreis=speicher_ladepreis_anlage,
            eta_ist=speicher_eta_by_inv.get(sp.id),
            entlade_preis_cent=(sp.parameter or {}).get(
                PARAM_SPEICHER["ENTLADE_VERMIEDENER_PREIS_CENT"],
                PARAM_SPEICHER_DEFAULTS["entlade_vermiedener_preis_cent"],
            ) if sp.parent_investition_id is None else 0,
            # Bestandserhalt: der DC-Zweig hat `entlade_preis` nie übergeben,
            # der AC-Zweig schon. Die Asymmetrie bleibt (s. `_speicher_roi`).
        )
        for sp in speicher_invs_alle
    }
    _speicher_pv_anteil = sum(r.pv_anteil_euro for r in speicher_roi_by_inv.values())
    _speicher_co2_pv = sum(r.co2_pv_kg for r in speicher_roi_by_inv.values())
    # `max(0, …)`: liegt der zugerechnete Speicher-Anteil über der gesamten
    # PV-Ersparnis (dünne oder widersprüchliche Datenlage), bleibt für die
    # Module 0 statt einer negativen Zeile. Die Summe kann dadurch nicht mehr
    # über der physikalischen Menge liegen — das ist die Zusicherung, die der
    # Symmetrie-Test prüft.
    pv_jahres_einsparung = max(0.0, pv_jahres_einsparung - _speicher_pv_anteil)
    pv_co2 = max(0.0, pv_co2 - _speicher_co2_pv)

    # Gesamt-kWp aller PV-Module für proportionale Verteilung.
    # kWp über den SoT-Helper (ADR-002/P3-a): ein nur im `parameter` gepflegtes
    # Modul (#229) bekam sonst `anteil = 0` — also 0 € Einsparung, 0 kg CO₂ und
    # keine Amortisation, während die übrigen Module zu viel zugerechnet bekamen.
    gesamt_kwp = sum(
        get_pv_kwp(inv)
        for system in pv_systeme.values()
        for inv in system["pv_module"]
    )
    gesamt_kwp += sum(get_pv_kwp(inv) for inv in orphan_pv_module)

    for wr_id, system in pv_systeme.items():
        wr = system["wr"]
        pv_module = system["pv_module"]
        dc_speicher = system["speicher"]
        # F-33: der Systemkopf ist seit #381 nicht mehr zwingend ein
        # Wechselrichter. Ein Balkonkraftwerk trägt — anders als ein WR — eine
        # **eigene** Erzeugung, solange keine Module an ihm hängen; dann muss
        # sein Beitrag in die Systemzeile, sonst verlöre ein BKW mit reinem
        # Speicher-Kind (Kanon seit v4.0.5) seine Einsparung ganz.
        kopf_ist_bkw = wr.typ == InvestitionTyp.BALKONKRAFTWERK.value
        # `traegt_erzeugungsgroessen_selbst` ist der SoT der Abtretung (N-266):
        # False heißt, die Modul-Kinder tragen die Erzeugung — dann darf der
        # Kopf nichts mehr beisteuern, sonst ist die Doppelzählung zurück.
        kopf_traegt_selbst = kopf_ist_bkw and traegt_erzeugungsgroessen_selbst(
            wr, investitionen
        )

        # Nur Systeme mit PV-Modulen anzeigen
        if not pv_module and not dc_speicher:
            # Trägergerät ohne zugeordnete Komponenten - als Hinweis zeigen
            standalone.append(wr)
            continue

        # Kosten summieren
        system_kosten = (wr.anschaffungskosten_gesamt or 0)
        system_alternativ = (wr.anschaffungskosten_alternativ or 0)
        system_betriebskosten = (wr.betriebskosten_jahr or 0)
        # Die beteiligten Positionen wandern mit, damit die relevanten Kosten
        # des Bündels je Position geklemmt werden (siehe `_relevante_kosten`)
        # statt als `Σ gesamt − Σ alternativ`.
        system_invs = [wr]

        komponenten: list[ROIKomponente] = []

        # Trägergerät als Komponente
        wr_kosten = wr.anschaffungskosten_gesamt or 0
        wr_alternativ = wr.anschaffungskosten_alternativ or 0
        # F-33: der Hinweis nennt den Grund, aus dem der Kopf keine eigene Zahl
        # trägt — und der ist je Typ ein anderer. Ein WR erzeugt nie selbst;
        # ein BKW mit Modul-Kindern hat abgetreten.
        if not kopf_ist_bkw:
            kopf_hinweis = 'Wechselrichter - Einsparung über PV-Module'
        elif kopf_traegt_selbst:
            kopf_hinweis = 'Balkonkraftwerk - eigene Erzeugung, Einsparung in der Systemzeile'
        else:
            kopf_hinweis = 'Balkonkraftwerk - Einsparung über die zugeordneten PV-Module'
        komponenten.append(ROIKomponente(
            investition_id=wr.id,
            bezeichnung=wr.bezeichnung,
            typ=wr.typ,
            kosten=wr_kosten,
            kosten_alternativ=wr_alternativ,
            relevante_kosten=_relevante_kosten(wr),
            einsparung=None,  # der Kopf trägt keine eigene Zeilen-Zahl
            co2_einsparung_kg=None,
            detail={'hinweis': kopf_hinweis}
        ))

        # PV-Module Einsparung proportional nach kWp verteilen
        system_kwp = sum(get_pv_kwp(inv) for inv in pv_module)
        system_einsparung = 0.0
        system_co2 = 0.0

        # F-33: BKW-Kopf ohne Modul-Kinder — seine eigene (pauschale)
        # Erzeugungs-Ersparnis geht in die Systemzeile. Bewusst DIESELBE
        # Formel wie im standalone-Zweig, damit sich für diesen Fall die
        # **Summe** nicht bewegt: repariert ist die Struktur (eine Zeile statt
        # zwei addierten), nicht die Pauschale. Dass die 80-%-Annahme einen
        # Speicher gar nicht kennt und deshalb neben dessen Mehr-Eigenverbrauch
        # zu hoch stehen kann, ist ein eigener Befund (Register N-272) und
        # ausdrücklich NICHT Teil von #381.
        if kopf_traegt_selbst:
            kopf_ertrag_kwh, kopf_einsparung, kopf_co2 = _bkw_pauschal_beitrag(
                wr,
                strompreis_cent=strompreis_cent,
                einspeiseverguetung_cent=einspeiseverguetung_cent,
            )
            system_einsparung += kopf_einsparung
            system_co2 += kopf_co2
            system_kwp += get_bkw_kwp(wr)

        for inv in pv_module:
            inv_kosten = inv.anschaffungskosten_gesamt or 0
            inv_alternativ = inv.anschaffungskosten_alternativ or 0
            system_kosten += inv_kosten
            system_alternativ += inv_alternativ
            system_betriebskosten += (inv.betriebskosten_jahr or 0)
            system_invs.append(inv)

            # Einsparung proportional nach kWp.
            # `anteil` vor dem Zweig setzen: Zeile 1066 liest es, sobald
            # `gesamt_kwp > 0` — bei einem Modul ganz ohne Nennleistung war es
            # dort ungebunden ⇒ 500er im ROI-Dashboard (an der Box gemessen).
            inv_kwp = get_pv_kwp(inv)
            anteil = 0.0
            if gesamt_kwp > 0 and inv_kwp > 0:
                anteil = inv_kwp / gesamt_kwp
                inv_einsparung = pv_jahres_einsparung * anteil
                inv_co2 = pv_co2 * anteil
            else:
                inv_einsparung = 0
                inv_co2 = 0

            system_einsparung += inv_einsparung
            system_co2 += inv_co2

            komponenten.append(ROIKomponente(
                investition_id=inv.id,
                bezeichnung=f"{inv.bezeichnung} ({inv_kwp} kWp)",
                typ=inv.typ,
                kosten=inv_kosten,
                kosten_alternativ=inv_alternativ,
                relevante_kosten=_relevante_kosten(inv),
                einsparung=round(inv_einsparung, 2),
                co2_einsparung_kg=round(inv_co2, 1),
                detail={
                    'anteil_prozent': round(anteil * 100, 1) if gesamt_kwp > 0 else 0,
                    'leistung_kwp': inv_kwp,
                }
            ))

        # DC-Speicher (am Hybrid-WR)
        for inv in dc_speicher:
            inv_kosten = inv.anschaffungskosten_gesamt or 0
            inv_alternativ = inv.anschaffungskosten_alternativ or 0
            system_kosten += inv_kosten
            system_alternativ += inv_alternativ
            system_betriebskosten += (inv.betriebskosten_jahr or 0)
            system_invs.append(inv)

            params = inv.parameter or {}
            # N127: BRUTTO-Kapazität über den SoT-Helper, ohne Default. Hier
            # stand `.get(…, 10)` — ein Speicher ohne gepflegte Kapazität bekam
            # still 10 kWh und daraus eine Jahres-Ersparnis, die es nie gab.
            # Sie geht NUR in den Prognose-Modus ein (s. `ist_aggregat` unten);
            # im IST-Modus rechnet `berechne_speicher_einsparung` aus der
            # gemessenen Entladung und die Kapazität bleibt ungelesen.
            kapazitaet = get_speicher_kapazitaet_kwh(inv)
            # A31-2/E-1: der Prognose-Modus rechnet NETTO — Kapazität × 250
            # Zyklen × η ist eine durchgefahrene Energiemenge, und durch den
            # Speicher geht nur der nutzbare Hub. `kapazitaet` (brutto) bleibt
            # daneben stehen: sie ist die *Beschreibung* der Komponente
            # (Detail-Feld und Label unten), nicht die Rechengröße.
            # F-37: die Rechnung liegt im Vorablauf — sie wird dort gebraucht,
            # um den PV-Topf zu kürzen, und darf hier kein zweites Mal
            # entstehen. `_speicher_roi` trägt Ergebnis und Quellen zusammen.
            _roi = speicher_roi_by_inv[inv.id]
            ist_aggregat = _roi.ist_aggregat
            nutzt_arbitrage = _roi.nutzt_arbitrage
            wirkungsgrad_eff, wirkungsgrad_quelle = _roi.wirkungsgrad_eff, _roi.wirkungsgrad_quelle
            lade_preis_eff, ladepreis_quelle = _roi.lade_preis_eff, _roi.ladepreis_quelle
            eff_ladepreis = speicher_ladepreis_anlage
            eta_ist = speicher_eta_by_inv.get(inv.id)
            kapazitaet_fehlt = _roi.kapazitaet_fehlt
            result = _roi.result
            inv_einsparung = result.jahres_einsparung_euro if result else None
            inv_co2 = result.co2_einsparung_kg if result else None
            system_einsparung += inv_einsparung or 0
            system_co2 += inv_co2 or 0

            # #351: `dc_gekoppelt` stand hier hart auf `True` — eine Behauptung
            # über eine Eigenschaft, die eedc nie erhoben hatte. Sie kommt jetzt
            # aus dem Feld (Vorbelegung: zugeordnet ⇒ DC), die Gruppierung
            # darüber bleibt unverändert an der Zuordnung.
            komp_detail: dict[str, Any] = {
                'kapazitaet_kwh': kapazitaet,
                'dc_gekoppelt': get_speicher_kopplung(inv) == SPEICHER_KOPPLUNG_DC,
                'kopplung': get_speicher_kopplung(inv),
                'kopplung_gepflegt': get_speicher_kopplung_gepflegt(inv) is not None,
            }
            if kapazitaet_fehlt:
                komp_detail['hinweis'] = (
                    'Keine Kapazität gepflegt — ohne sie lässt sich die Ersparnis '
                    'nicht abschätzen. Kapazität in der Investitionspflege nachtragen.'
                )
            if ist_aggregat is not None:
                komp_detail.update({
                    'modus': 'ist',
                    'ist_entladung_kwh_jahr': round(ist_aggregat.entladung_kwh_jahr, 1),
                    'ist_ladung_netz_kwh_jahr': round(ist_aggregat.ladung_netz_kwh_jahr, 1),
                    'ist_monate': ist_aggregat.anzahl_monate,
                    'pv_anteil_euro': result.pv_anteil_euro,
                    'netz_anteil_euro': result.arbitrage_anteil_euro,
                    'effektiver_ladepreis_cent': round(lade_preis_eff, 2) if (lade_preis_eff is not None and nutzt_arbitrage) else None,
                    'ladepreis_quelle': ladepreis_quelle,
                    'verwendetes_wirkungsgrad_prozent': round(wirkungsgrad_eff, 1),
                    'wirkungsgrad_quelle': wirkungsgrad_quelle,
                })
                # Etappe C1 Diagnose-Felder für UI-Badge bei dünner Datenbasis.
                if eff_ladepreis is not None and eff_ladepreis.quelle == "datenbasis-zu-duenn":
                    komp_detail['ladepreis_abdeckung_prozent'] = round(eff_ladepreis.abdeckung_prozent, 0)
                # ⛔ Der Degradations-Alarm stand hier bis zum 03.09.2026 und ist
                # ENTFALLEN (Entscheid Gernot: „ich sehe keinen Zusammenhang").
                # Am Code belegt, warum er hier nie hingehörte: Gesetzt wurde er
                # nur unter `eta_ist.wirkungsgrad_prozent is not None` — und
                # GENAU unter dieser Bedingung gibt `_aufloesen_wirkungsgrad` die
                # MESSUNG zurück (`:112`). Der Alarm konnte in dieser Sicht also
                # ausschließlich dann erscheinen, wenn der Parameter, über den er
                # sich beschwert, hier keine einzige Zahl beeinflusst. Er bleibt
                # im Komponenten-Hub (`dashboards.py`), wo der gepflegte Wert
                # zählt (Sizing, Tages-Vorschau, HA-Sensoren).
            else:
                komp_detail['modus'] = 'prognose'
            komponenten.append(ROIKomponente(
                investition_id=inv.id,
                # Ohne gepflegte Kapazität steht der Name ohne Klammerzusatz da —
                # „(None kWh)" wäre schlechter als gar keine Angabe (N127).
                bezeichnung=(
                    f"{inv.bezeichnung} ({kapazitaet} kWh)" if kapazitaet is not None
                    else inv.bezeichnung
                ),
                typ=inv.typ,
                kosten=inv_kosten,
                kosten_alternativ=inv_alternativ,
                relevante_kosten=_relevante_kosten(inv),
                einsparung=round(inv_einsparung, 2) if inv_einsparung is not None else None,
                co2_einsparung_kg=round(inv_co2, 1) if inv_co2 is not None else None,
                detail=komp_detail,
            ))

        # System-ROI berechnen
        # #310: manuell gepflegte sonstige Erträge/Ausgaben des Systems
        # (WR + PV-Module + DC-Speicher) einrechnen.
        # F-19: Ausgaben kumuliert in den NENNER. Bauschritt 7: die Erträge
        # ebenfalls — mit umgekehrtem Vorzeichen (§8/3 hatte sie nur aus dem
        # Zähler genommen).
        _system_ids = [wr.id, *(m.id for m in pv_module), *(s.id for s in dc_speicher)]
        system_sonstige_ausgaben = _sonstige_ausgaben_kumuliert_fuer(_system_ids)
        system_sonstige_ertraege = _sonstige_ertraege_kumuliert_fuer(_system_ids)
        system_relevante = _relevante_kosten(*system_invs)
        system_kapitaleinsatz = kapitaleinsatz_euro(
            relevante_kosten_euro=system_kosten - system_alternativ,
            sonstige_ausgaben_euro=system_sonstige_ausgaben,
            sonstige_ertraege_euro=system_sonstige_ertraege,
        )
        system_netto_einsparung = system_einsparung - system_betriebskosten
        roi_result = berechne_roi(system_kapitaleinsatz, system_einsparung, 0, system_betriebskosten)
        gesamt_betriebskosten += system_betriebskosten
        # N-525: jede Komponente stuft ihre Mehrkosten ab ihrem Jahr; die
        # Einsparung des Systems läuft ab seiner ersten Komponente (eine
        # Jahres-Einsparung je System — ein später ergänztes Modulfeld stuft
        # die Kosten, nicht die Einsparung; benannte Grenze).
        system_zeilen_jahr = _treppe_zeile(
            invs=system_invs,
            kosten_je_inv={
                k.investition_id: (k.kosten or 0.0) - (k.kosten_alternativ or 0.0)
                for k in komponenten
            },
            netto_einsparung=system_netto_einsparung,
        )

        # F-33: die Zeile trägt den Typ ihres KOPFES, nicht pauschal
        # "pv-system". Ein Balkonkraftwerk als „PV-System Toni" mit
        # Sonnen-Icon zu beschriften, hieße dem Melder aus #381 sein Gerät
        # umzubenennen — und es verstieße gegen Regel 0a (eine Datenrolle =
        # eine Farbe): ein BKW hat im Farb-SoT seine eigene. Dass die Zeile
        # ein System ist, macht die Komponenten-Liste darunter sichtbar.
        berechnungen.append(ROIBerechnung(
            investition_id=wr.id,  # Kopf-ID als System-ID
            anschaffungsjahr=system_zeilen_jahr if basis_jahr is not None else None,
            investition_bezeichnung=(
                wr.bezeichnung if kopf_ist_bkw else f"PV-System {wr.bezeichnung}"
            ),
            investition_typ=(
                InvestitionTyp.BALKONKRAFTWERK.value if kopf_ist_bkw else "pv-system"
            ),
            anschaffungskosten=system_kosten,
            anschaffungskosten_alternativ=system_alternativ,
            relevante_kosten=system_relevante,
            kapitaleinsatz=round(system_kapitaleinsatz, 2),
            jahres_einsparung=round(system_netto_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            amortisation_annahme=annahme_dauer_text(
                betriebskosten_jahr_euro=system_betriebskosten,
            ),
            co2_einsparung_kg=round(system_co2, 1),
            detail_berechnung={
                **pv_detail,
                'komponenten_count': len(komponenten),
                'system_kwp': system_kwp,
                'sonstige_netto_euro': round(system_sonstige_ertraege - system_sonstige_ausgaben, 2),
                'sonstige_ausgaben_euro': round(system_sonstige_ausgaben, 2),
                # Bauschritt 7: die Zeile nennt beide Seiten ihres Nenners.
                'sonstige_ertraege_euro': round(system_sonstige_ertraege, 2),
            },
            komponenten=komponenten,
        ))

        gesamt_investition += system_kosten
        gesamt_relevante += system_relevante
        gesamt_sonstige_ausgaben += system_sonstige_ausgaben
        gesamt_sonstige_ertraege += system_sonstige_ertraege
        gesamt_einsparung += system_netto_einsparung
        gesamt_co2 += system_co2
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("gesamt_betriebskosten", "gesamt_co2", "gesamt_einsparung", "gesamt_investition", "gesamt_kwp", "gesamt_relevante", "gesamt_sonstige_ausgaben", "gesamt_sonstige_ertraege", "pv_co2", "pv_jahres_einsparung", "speicher_roi_by_inv",) if k in _loc}


def orphan_modul_zeilen(
    *,
    _relevante_kosten,
    _sonstige_ausgaben_kumuliert_fuer,
    _sonstige_ertraege_kumuliert_fuer,
    _treppe_zeile,
    basis_jahr,
    berechnungen,
    gesamt_betriebskosten,
    gesamt_co2,
    gesamt_einsparung,
    gesamt_investition,
    gesamt_kwp,
    gesamt_relevante,
    gesamt_sonstige_ausgaben,
    gesamt_sonstige_ertraege,
    orphan_pv_module,
    pv_co2,
    pv_detail,
    pv_jahres_einsparung,
):
    """PV-Module ohne Traeger-Zuordnung (Altdaten): je Modul eine ROI-Zeile mit kWp-Anteil am PV-Topf.

    Aus `get_roi_dashboard` Zeilen 1608-1682 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 5b.
    """
    # ==========================================================================
    # Phase 4: Orphan PV-Module (ohne Wechselrichter-Zuordnung)
    # ==========================================================================

    for inv in orphan_pv_module:
        kosten = inv.anschaffungskosten_gesamt or 0
        alternativ = inv.anschaffungskosten_alternativ or 0
        relevante = _relevante_kosten(inv)

        # Einsparung proportional nach kWp.
        # `anteil` wird VOR dem Zweig gesetzt: Zeile 1231 liest es, sobald
        # `gesamt_kwp > 0` — bei einem Orphan-Modul ganz ohne Nennleistung war
        # es dort ungebunden und das ROI-Dashboard antwortete mit einem 500er
        # (an der Box gemessen). Die Migration auf `get_pv_kwp` nimmt dem
        # Fehler die häufigste Ursache (#229), beseitigt ihn aber nicht.
        inv_kwp = get_pv_kwp(inv)
        anteil = 0.0
        if gesamt_kwp > 0 and inv_kwp > 0:
            anteil = inv_kwp / gesamt_kwp
            jahres_einsparung = pv_jahres_einsparung * anteil
            co2_einsparung = pv_co2 * anteil
        else:
            jahres_einsparung = 0
            co2_einsparung = 0

        # #310: sonstige Erträge/Ausgaben des Moduls einrechnen — seit F-19
        # Ausgaben kumuliert im Nenner, seit Bauschritt 7 die Erträge dort
        # mindernd (keine Projektion auf beiden Seiten, §8/3).
        orphan_sonstige_ausgaben = _sonstige_ausgaben_kumuliert_fuer([inv.id])
        orphan_sonstige_ertraege = _sonstige_ertraege_kumuliert_fuer([inv.id])
        orphan_kapitaleinsatz = kapitaleinsatz_euro(
            relevante_kosten_euro=kosten - alternativ,
            sonstige_ausgaben_euro=orphan_sonstige_ausgaben,
            sonstige_ertraege_euro=orphan_sonstige_ertraege,
        )
        betriebskosten = inv.betriebskosten_jahr or 0
        netto_einsparung = jahres_einsparung - betriebskosten
        roi_result = berechne_roi(orphan_kapitaleinsatz, jahres_einsparung, 0, betriebskosten)
        gesamt_betriebskosten += betriebskosten
        orphan_zeilen_jahr = _treppe_zeile(
            invs=[inv], kosten_je_inv={inv.id: kosten - alternativ},
            netto_einsparung=netto_einsparung,
        )

        berechnungen.append(ROIBerechnung(
            investition_id=inv.id,
            investition_bezeichnung=f"{inv.bezeichnung} (ohne WR)",
            anschaffungsjahr=orphan_zeilen_jahr if basis_jahr is not None else None,
            investition_typ=inv.typ,
            anschaffungskosten=kosten,
            anschaffungskosten_alternativ=alternativ,
            relevante_kosten=relevante,
            kapitaleinsatz=round(orphan_kapitaleinsatz, 2),
            jahres_einsparung=round(netto_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            amortisation_annahme=annahme_dauer_text(betriebskosten_jahr_euro=betriebskosten),
            co2_einsparung_kg=round(co2_einsparung, 1),
            detail_berechnung={
                **pv_detail,
                'hinweis': 'PV-Modul ohne Wechselrichter-Zuordnung - bitte zuordnen',
                'anteil_prozent': round(anteil * 100, 1) if gesamt_kwp > 0 else 0,
                'sonstige_netto_euro': round(orphan_sonstige_ertraege - orphan_sonstige_ausgaben, 2),
                'sonstige_ausgaben_euro': round(orphan_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(orphan_sonstige_ertraege, 2),
            },
        ))

        gesamt_investition += kosten
        gesamt_relevante += relevante
        gesamt_sonstige_ausgaben += orphan_sonstige_ausgaben
        gesamt_sonstige_ertraege += orphan_sonstige_ertraege
        gesamt_einsparung += netto_einsparung
        gesamt_co2 += co2_einsparung
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("gesamt_betriebskosten", "gesamt_co2", "gesamt_einsparung", "gesamt_investition", "gesamt_relevante", "gesamt_sonstige_ausgaben", "gesamt_sonstige_ertraege",) if k in _loc}

