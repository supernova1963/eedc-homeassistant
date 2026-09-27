"""ROI-Dashboard — die Standalone-Zeilen: die Typkette fuer eigenstaendige Speicher, E-Autos (inkl. PHEV #331),
Waermepumpen (bewertet nur mit gepflegtem Bedarf, N-88/WK-15c), Balkonkraftwerke ohne Kinder, Wechselrichter ohne
Module sowie Wallbox/Sonstiges ueber den Ertrag/Jahr (Konzept §8/1, §9.2).
"""
# Vorlage 5b des Refactorings grosser Dateien (18.09.2026): Phasen des Endpunkts
# `roi.py::get_roi_dashboard` byte-identisch als Funktionen, Schnittstelle als Schluesselwort-
# Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel — Gate ist
# `plans/skript-golden-master-investitionen.py` (alte gegen neue Antworten, bitgleich).
# ⚠ Dieses Modul importiert Helfer und Schemas aus `roi.py`; `roi.py` importiert die Phasen
# deshalb erst IM Endpunkt (sonst Importzyklus) — dieselbe Bauform wie die Lazy-Importe der
# Energieprofil-Routen.

from typing import Any
from backend.core.field_definitions import ist_abgabe_kategorie
from backend.core.investition_kennwerte import (
    get_bkw_kwp,
    get_speicher_kopplung,
    get_speicher_kopplung_gepflegt,
)
from backend.models.investition import InvestitionTyp
from backend.utils.investition_value import param_zahl
from backend.core.berechnungen.investitions_jahresertrag import (
    BEZEICHNUNG_ABGABE,
    jahresertrag_posten,
)
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
)
from backend.services.eauto_wirtschaftlichkeit import (
    eigener_verbrauch_l_100km,
    fahranteil_prozent,
    resolve_eauto_benzinpreis,
)
from backend.core.calculations import (
    berechne_eauto_einsparung,
    berechne_waermepumpe_einsparung,
    berechne_roi,
)
from backend.core.berechnungen.kapitalrechnung import (
    annahme_dauer_text,
    jahres_ersparnis_euro,
    kapitaleinsatz_euro,
)
from backend.api.routes.investitionen.roi import (
    ROIBerechnung,
    _achse_gilt,
    _angezeigte_jahres_einsparung,
    _bkw_pauschal_beitrag,
    _wp_nicht_bewertbar,
)


async def standalone_zeilen(
    *,
    _anlage_fakten,
    _ist_pv_ladeanteil,
    _relevante_kosten,
    _sonstige_ausgaben_kumuliert_fuer,
    _sonstige_ertraege_kumuliert_fuer,
    _treppe_zeile,
    basis_jahr,
    benzinpreis_euro,
    berechnungen,
    einspeiseverguetung_cent,
    gesamt_betriebskosten,
    gesamt_co2,
    gesamt_einsparung,
    gesamt_investition,
    gesamt_relevante,
    gesamt_sonstige_ausgaben,
    gesamt_sonstige_ertraege,
    letzter_marktpreis,
    speicher_eta_by_inv,
    speicher_ladepreis_anlage,
    speicher_roi_by_inv,
    standalone,
    strompreis_cent,
    wallbox_strompreis,
    wp_strompreis,
):
    """Je Standalone-Investition die ROI-Zeile: Einsparung nach Typ, sonstige Positionen im Nenner, Treppe, Summen.

    Aus `get_roi_dashboard` Zeilen 1683-2159 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 5b.
    """
    # ==========================================================================
    # Phase 5: Standalone-Investitionen (wie bisher)
    # ==========================================================================

    for inv in standalone:
        params = inv.parameter or {}
        kosten = inv.anschaffungskosten_gesamt or 0
        alternativ = inv.anschaffungskosten_alternativ or 0
        relevante = _relevante_kosten(inv)
        jahres_einsparung = 0.0
        co2_einsparung = 0.0
        detail: dict[str, Any] = {}

        if inv.typ == InvestitionTyp.SPEICHER.value:
            # Eigenständig geführter Speicher (keine WR-Zuordnung) — Bug #5
            # v3.25.0 fix wie oben. #351: dieser Zweig hieß „AC-gekoppelter
            # Speicher" und nannte das auch im ausgelieferten `hinweis`; das war
            # eine Folgerung aus der Zuordnung, kein erhobener Wert. Die Kopplung
            # steht jetzt im Feld, der Zweig bleibt der der **Rechnung**.
            # N127 + A31-2: Kapazität über die SoT-Helper, ohne Default — s. den
            # DC-Pfad oben. Der Prognose-Modus rechnet NETTO; hier gibt es kein
            # Detail-Feld mit der Brutto-Zahl, also wird sie auch nicht gelesen.
            kopplung = get_speicher_kopplung(inv)
            kopplung_felder: dict[str, Any] = {
                'kopplung': kopplung,
                'kopplung_gepflegt': get_speicher_kopplung_gepflegt(inv) is not None,
            }
            # F-37: siehe DC-Pfad — die Rechnung liegt im Vorablauf, weil sie
            # dort den PV-Topf kürzt. Dieser Zweig trägt den eigenständigen
            # (meist AC-gekoppelten) Speicher und ist der HÄUFIGSTE Fall: ein
            # AC-Speicher bringt seinen eigenen Wechselrichter mit und hat
            # darum in aller Regel gar keine Zuordnung.
            _roi = speicher_roi_by_inv[inv.id]
            ist_aggregat = _roi.ist_aggregat
            nutzt_arbitrage = _roi.nutzt_arbitrage
            wirkungsgrad_eff, wirkungsgrad_quelle = _roi.wirkungsgrad_eff, _roi.wirkungsgrad_quelle
            lade_preis_eff, ladepreis_quelle = _roi.lade_preis_eff, _roi.ladepreis_quelle
            eff_ladepreis = speicher_ladepreis_anlage
            eta_ist = speicher_eta_by_inv.get(inv.id)
            kapazitaet_fehlt = _roi.kapazitaet_fehlt
            result = _roi.result
            if result is None:
                # `jahres_einsparung`/`co2_einsparung` bleiben bei 0 — die
                # Gesamtsumme darf keinen Beitrag bekommen. Dass es ein
                # fehlender Wert und keine Null-Ersparnis ist, sagt `detail`
                # (P4); `ROIBerechnung.jahres_einsparung` ist nicht optional.
                # N-89: `kapazitaet_fehlt` allein hat das der ROI-Tabelle NICHT
                # gesagt — sie liest ausschließlich `nicht_bewertet` (der
                # Mechanismus aus N-87). Die Zeile stand deshalb mit „0 €" da,
                # also mit der Behauptung „spart nichts", statt mit „unbekannt".
                # `kapazitaet_fehlt` bleibt: es ist die speicherspezifische
                # URSACHE und wird vom Komponenten-Hub gelesen
                # (`v4/komponentenAdapter.tsx`), `nicht_bewertet` die
                # anzeigeseitige Folge.
                detail = {
                    'hinweis': (
                        'Keine Kapazität gepflegt — ohne sie lässt sich die '
                        'Ersparnis nicht abschätzen. Kapazität in der '
                        'Investitionspflege nachtragen.'
                    ),
                    'kapazitaet_fehlt': True,
                    'nicht_bewertet': True,
                    'modus': 'prognose',
                    **kopplung_felder,
                }
            else:
                jahres_einsparung = result.jahres_einsparung_euro
                co2_einsparung = result.co2_einsparung_kg
                detail = {
                    'nutzbare_speicherung_kwh': result.nutzbare_speicherung_kwh,
                    'pv_anteil_euro': result.pv_anteil_euro,
                    'arbitrage_anteil_euro': result.arbitrage_anteil_euro,
                    'hinweis': 'Eigenständig gerechneter Speicher',
                    'modus': 'ist' if ist_aggregat is not None else 'prognose',
                    **kopplung_felder,
                }
            if ist_aggregat is not None:
                detail.update({
                    'ist_entladung_kwh_jahr': round(ist_aggregat.entladung_kwh_jahr, 1),
                    'ist_ladung_netz_kwh_jahr': round(ist_aggregat.ladung_netz_kwh_jahr, 1),
                    'ist_monate': ist_aggregat.anzahl_monate,
                    # `arbitrage_anteil_euro` ist im IST-Modus der gemessene
                    # Netz-Anteil-Vorteil (siehe calculations.berechne_speicher_einsparung).
                    'netz_anteil_euro': result.arbitrage_anteil_euro,
                    'effektiver_ladepreis_cent': round(lade_preis_eff, 2) if (lade_preis_eff is not None and nutzt_arbitrage) else None,
                    'ladepreis_quelle': ladepreis_quelle,
                    'verwendetes_wirkungsgrad_prozent': round(wirkungsgrad_eff, 1),
                    'wirkungsgrad_quelle': wirkungsgrad_quelle,
                })
                if eff_ladepreis is not None and eff_ladepreis.quelle == "datenbasis-zu-duenn":
                    detail['ladepreis_abdeckung_prozent'] = round(eff_ladepreis.abdeckung_prozent, 0)
                # ⛔ Degradations-Alarm entfallen (03.09.2026) — Begründung im
                # DC-Zweig oben, gleicher Sachverhalt.

        elif inv.typ == InvestitionTyp.E_AUTO.value:
            # Bugs #1, #2, #3, #4 v3.25.0: vorher las dieser Block aus toten Schema-Keys
            # ('km_jahr', 'pv_anteil_prozent', 'benzin_verbrauch_liter_100km', 'nutzt_v2h')
            # — Form/Wizard schreiben aber 'jahresfahrleistung_km', 'pv_ladeanteil_prozent',
            # 'vergleich_verbrauch_l_100km', 'v2h_faehig'. ROI ignorierte deshalb alle vier
            # User-Eingaben und nutzte stattdessen die hier hinterlegten Defaults.
            km_jahr = param_zahl(params, PARAM_E_AUTO["JAHRESFAHRLEISTUNG_KM"], PARAM_E_AUTO_DEFAULTS["jahresfahrleistung_km"])
            verbrauch = param_zahl(params, PARAM_E_AUTO["VERBRAUCH_KWH_100KM"], PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"])
            # N-188: die Prognose rät den PV-Anteil nicht mehr, wenn das IST ihn
            # kennt. Rangfolge: gepflegter Parameter (auch **0** — geprüft wird
            # die Anwesenheit, nicht die Größe, F-15-Klasse) → IST-Anteil aus den
            # Monats-Fakten → Default. Bis hierher stand dieselbe Anlage auf
            # 60 % in der Prognose und dem gemessenen Anteil im IST; zwei Zahlen
            # für dieselbe Größe, nur auf zwei Zeitachsen.
            pv_anteil = param_zahl(params, PARAM_E_AUTO["PV_LADEANTEIL_PROZENT"])
            if pv_anteil is None:
                pv_anteil = await _ist_pv_ladeanteil()
            if pv_anteil is None:
                pv_anteil = PARAM_E_AUTO_DEFAULTS["pv_ladeanteil_prozent"]
            benzin_verbrauch = param_zahl(params, PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"], PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"])
            nutzt_v2h = params.get(PARAM_E_AUTO["V2H_FAEHIG"], PARAM_E_AUTO_DEFAULTS["v2h_faehig"])
            v2h_entladung = param_zahl(params, PARAM_E_AUTO["V2H_ENTLADUNG_KWH_JAHR"], 0)
            v2h_preis = param_zahl(params, PARAM_E_AUTO["V2H_ENTLADE_PREIS_CENT"], strompreis_cent)

            # Benzinpreis-Auflösung: Slider-Override > per-Inv-Param > letzter
            # Monatsdaten-Preis (EU OB) > Default 1,65. Korrigiert die v3.25.0-
            # Lücke: 'benzinpreis_euro' wurde damals nicht in die Liste der
            # aus `params` zu lesenden Felder aufgenommen.
            preis = resolve_eauto_benzinpreis(
                query_override=benzinpreis_euro,
                eauto_parameter=params,
                letzter_monats_benzinpreis=letzter_marktpreis,
            )

            result = berechne_eauto_einsparung(
                km_jahr=km_jahr,
                verbrauch_kwh_100km=verbrauch,
                pv_anteil_prozent=pv_anteil,
                strompreis_cent=wallbox_strompreis,
                benzinpreis_euro_liter=preis.preis_euro,
                benzin_verbrauch_liter_100km=benzin_verbrauch,
                nutzt_v2h=nutzt_v2h,
                v2h_entladung_kwh_jahr=v2h_entladung,
                v2h_preis_cent=v2h_preis,
                # #331: PHEV. Beide ohne Default — fehlen sie, rechnet die
                # Prognose exakt wie vorher (100 % elektrisch).
                #
                # Über die SoT-Helper, nicht über den Rohwert: `teile_fahrleistung`
                # nimmt `Optional[float]` und ruft auf allem, was `is not None`
                # ist, `float()` — ein geleertes Feld (`""`, seit dem
                # Formular-Fix der Rückweg aus einer gesetzten Angabe) hätte
                # diese Route mit einem 500er beendet. Die Helper machen aus
                # „nicht gepflegt" in allen seinen Gestalten `None`.
                eigener_verbrauch_l_100km=eigener_verbrauch_l_100km(params),
                elektrischer_fahranteil_prozent=fahranteil_prozent(params),
            )
            jahres_einsparung = result.jahres_einsparung_euro
            co2_einsparung = result.co2_einsparung_kg
            detail = {
                'strom_kosten_euro': result.strom_kosten_euro,
                'benzin_kosten_alternativ_euro': result.benzin_kosten_alternativ_euro,
                'v2h_einsparung_euro': result.v2h_einsparung_euro,
                'verwendeter_benzinpreis_euro': round(preis.preis_euro, 3),
                'benzinpreis_quelle': preis.quelle,
                'hinweis': f'E-Auto: {km_jahr} km/Jahr',
            }
            # #331: nur bei einem Plug-in-Hybrid — bei einem BEV bleibt das
            # Detail-Dict Zeichen für Zeichen das von vorher.
            if result.fossile_kosten_euro:
                detail['fossile_kosten_euro'] = result.fossile_kosten_euro
                detail['km_elektrisch'] = result.km_elektrisch
                detail['km_verbrenner'] = result.km_verbrenner
                detail['hinweis'] = (
                    f'Plug-in-Hybrid: {km_jahr} km/Jahr, davon '
                    f'{result.km_elektrisch:.0f} km elektrisch'
                )

        elif inv.typ == InvestitionTyp.WAERMEPUMPE.value and _wp_nicht_bewertbar(params):
            # N-88/F2b — der Nachfolger des `wp_art == luft_luft`-Sonderwegs.
            #
            # Bis 2026-08-16 stand hier: „Eine Split-Klimaanlage ersetzt keine
            # Heizung." **Das ist falsch** (Gernot, 16.08.): Eine Luft-Luft-WP
            # kann sehr wohl eine Gasheizung ersetzen — ob sie dafür die
            # effizienteste Bauart ist, ist eine andere Frage und nicht die,
            # die diese Zeile beantwortet. Wer mit seiner Klimaanlage heizt und
            # den Bedarf pflegt, bekommt seine Bewertung jetzt.
            #
            # Der echte Defekt von K-0b war nie die Bauart, sondern eine
            # **erfundene Eingabe**: `heizwaermebedarf`/`warmwasserbedarf`
            # fielen auf 12.000 + 3.000 kWh zurück, wenn niemand sie gepflegt
            # hatte ⇒ rund 1.100 €/Jahr und 2.210 kg CO₂ gegen eine Heizung,
            # die es nie gab. Der Default ist deshalb unten weg; unbewertet ist
            # jetzt, wer die Frage nicht beantwortet hat statt wer den falschen
            # Gerätetyp trägt.
            #
            # ⚠ **Die Begründung dieses Zweigs war zusätzlich unwahr** und ist
            # mit ihm gefallen: Sie behauptete, die gemessenen Pfade lieferten
            # für dasselbe Gerät 0. Das galt nur, solange keine Wärme gepflegt
            # war — der Schutz dort ist `wp_waerme_kwh <= 0`, keine Typ-Regel.
            # Sobald jemand die Heizwärme erfasste (und die Zuordnungs-Fläche
            # verlangte sie bis heute als Pflicht, s. N-86), rechneten Cockpit,
            # Aussichten, WP-Dashboard, Jahresbericht-PDF und der HA-Sensor
            # sehr wohl — nur diese Zeile nicht.
            #
            # Kein Fake-0 statt eines fehlenden Werts: `nicht_bewertet` sagt der
            # Anzeige, dass hier etwas FEHLT und keine Null-Ersparnis steht —
            # dieselbe Unterscheidung wie beim AC-Speicher ohne Kapazität oben.
            # Die Anschaffungskosten zählen weiter (wie beim Wechselrichter ohne
            # PV-Module): unbewertet heißt nicht unsichtbar.
            detail = {'hinweis': _wp_nicht_bewertbar(params), 'nicht_bewertet': True}

        elif inv.typ == InvestitionTyp.WAERMEPUMPE.value:
            # Modus-Auswahl: gesamt_jaz (Standard), scop (EU-Label) oder getrennte_cops
            effizienz_modus = params.get(PARAM_WAERMEPUMPE["EFFIZIENZ_MODUS"], PARAM_WAERMEPUMPE_DEFAULTS["effizienz_modus"])
            # ⛔ Hier stand bis 2026-09-13 `pv_anteil = params.get(…PV_ANTEIL_PROZENT…)`
            # und ging als `pv_anteil_prozent` in die Formel: diese Zeile war die
            # EINZIGE Sicht, in der das Formularfeld eine Geldzahl bewegte, und
            # sie widersprach den drei anderen Ersparnis-Zahlen derselben
            # Wärmepumpe. Sie ist entfallen (SOLL Wärme/Klima S1b, N-459) — der
            # WP-Strom wird voll belastet, sein PV-Anteil steht auf der PV-Seite.
            # Nebenwirkung: `pv_anteil_prozent: null` im Parameter-JSON legte
            # diese ganze Route mit einem TypeError lahm; mit dem Leser fällt
            # auch der Absturz weg.
            alter_energietraeger = params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"], PARAM_WAERMEPUMPE_DEFAULTS["alter_energietraeger"])
            alter_preis = param_zahl(params, PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"], PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"])
            alternativ_zusatzkosten = params.get(PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0) or 0
            # N-88/F2b: KEIN Default mehr — `_wp_nicht_bewertbar` oben laesst diesen
            # Zweig nur mit gepflegtem Bedarf ueberhaupt laufen. Der frueher hier
            # stehende Rueckfall auf 12.000 + 3.000 kWh war die erfundene Eingabe
            # hinter dem K-0b-Phantomwert.
            heizwaermebedarf = params.get(PARAM_WAERMEPUMPE["HEIZWAERMEBEDARF_KWH"]) or 0
            warmwasserbedarf = params.get(PARAM_WAERMEPUMPE["WARMWASSERBEDARF_KWH"]) or 0
            # ⭐ **WK-15c: Eine Achse, die es am Gerät nicht gibt, trägt keine
            # Zahl.** Gemessen an einer Brauchwasser-WP mit der Formular-
            # Vorbelegung 12.000/3.000: **714,29 €/Jahr und 1.721 kg CO₂**
            # gegenüber 142,86 € und 344 kg mit `heiz = 0` — **571 € Ersparnis
            # für Heizwärme, die das Gerät nie abgibt**. Spiegelbildlich an
            # einer Split-Klimaanlage der Warmwasserbedarf (N-304: kein
            # Warmwasserkreis; ein dort gepflegter Wert erzeugte eine Ersparnis
            # für Wärme, die nie erzeugt wurde — dieselbe Klasse, die für die
            # **gemessene** Menge schon abgeräumt ist).
            #
            # ⛔ **Die Layer-Formel bleibt registry-frei** (ADR-001): Sie rechnet,
            # was man ihr gibt; *welche* Achse dieses Gerät hat, ist eine Frage
            # an die Registry und gehört zum Aufrufer. `calculations.py` behält
            # deshalb auch seine Defaults 12.000/3.000 — sie greifen nur, wenn
            # ein Aufrufer `None` durchreicht, und das tut hier keiner (`or 0`).
            if not _achse_gilt(params, "heizenergie_kwh"):
                heizwaermebedarf = 0
            if not _achse_gilt(params, "warmwasser_kwh"):
                warmwasserbedarf = 0

            if effizienz_modus == 'getrennte_cops':
                # Getrennte COPs für Heizung und Warmwasser
                cop_heizung = param_zahl(params, PARAM_WAERMEPUMPE["COP_HEIZUNG"], PARAM_WAERMEPUMPE_DEFAULTS["cop_heizung"])
                cop_warmwasser = param_zahl(params, PARAM_WAERMEPUMPE["COP_WARMWASSER"], PARAM_WAERMEPUMPE_DEFAULTS["cop_warmwasser"])

                result = berechne_waermepumpe_einsparung(
                    heizwaermebedarf_kwh=heizwaermebedarf,
                    warmwasserbedarf_kwh=warmwasserbedarf,
                    cop_heizung=cop_heizung,
                    cop_warmwasser=cop_warmwasser,
                    effizienz_modus='getrennte_cops',
                    strompreis_cent=wp_strompreis,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                    alternativ_zusatzkosten_jahr=alternativ_zusatzkosten,
                )
                hinweis = f'WP: COP Heizung {cop_heizung}, Warmwasser {cop_warmwasser}'

            elif effizienz_modus == 'scop':
                # EU-Label SCOP-Werte (saisonale Effizienz)
                scop_heizung = param_zahl(params, PARAM_WAERMEPUMPE["SCOP_HEIZUNG"], PARAM_WAERMEPUMPE_DEFAULTS["scop_heizung"])
                scop_warmwasser = param_zahl(params, PARAM_WAERMEPUMPE["SCOP_WARMWASSER"], PARAM_WAERMEPUMPE_DEFAULTS["scop_warmwasser"])
                vorlauftemperatur = param_zahl(params, PARAM_WAERMEPUMPE["VORLAUFTEMPERATUR"], PARAM_WAERMEPUMPE_DEFAULTS["vorlauftemperatur"])

                result = berechne_waermepumpe_einsparung(
                    heizwaermebedarf_kwh=heizwaermebedarf,
                    warmwasserbedarf_kwh=warmwasserbedarf,
                    scop_heizung=scop_heizung,
                    scop_warmwasser=scop_warmwasser,
                    effizienz_modus='scop',
                    strompreis_cent=wp_strompreis,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                    alternativ_zusatzkosten_jahr=alternativ_zusatzkosten,
                )
                hinweis = f'WP: SCOP {scop_heizung} (VL {vorlauftemperatur}°C)'

            else:
                # Standard: Ein JAZ für alles (gemessene Jahresarbeitszahl)
                jaz = param_zahl(params, PARAM_WAERMEPUMPE["JAZ"], PARAM_WAERMEPUMPE_DEFAULTS["jaz"])
                # Wärmebedarf: explizit oder aus Komponenten
                waermebedarf = param_zahl(params, PARAM_WAERMEPUMPE["WAERMEBEDARF_KWH"])
                if waermebedarf is None:
                    waermebedarf = heizwaermebedarf + warmwasserbedarf

                result = berechne_waermepumpe_einsparung(
                    waermebedarf_kwh=waermebedarf,
                    jaz=jaz,
                    effizienz_modus='gesamt_jaz',
                    strompreis_cent=wp_strompreis,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                    alternativ_zusatzkosten_jahr=alternativ_zusatzkosten,
                )
                hinweis = f'Wärmepumpe: JAZ {jaz}'

            jahres_einsparung = result.jahres_einsparung_euro
            co2_einsparung = result.co2_einsparung_kg
            detail = {
                'wp_kosten_euro': result.wp_kosten_euro,
                'alte_heizung_kosten_euro': result.alte_heizung_kosten_euro,
                'effizienz_modus': effizienz_modus,
                'hinweis': hinweis,
            }

        elif inv.typ == InvestitionTyp.BALKONKRAFTWERK.value:
            # Balkonkraftwerk hat eigenen Mikro-WR integriert.
            # F-33: dieselbe Formel wie beim BKW-Systemkopf — sie liegt seit
            # #381 in `_bkw_pauschal_beitrag`, damit es nicht zwei Kopien gibt.
            # Hierher kommt nur noch ein BKW OHNE Kinder; mit Kindern ist es
            # Systemkopf und diese Zeile entsteht gar nicht.
            # F-35: die Anzeige nennt dieselbe Leistung, mit der gerechnet
            # wurde — sonst stünde im Hinweis „500 Wp" neben einer Zahl aus
            # 2.000 Wp.
            _bkw_kwp = get_bkw_kwp(inv)
            leistung_wp = _bkw_kwp * 1000 if _bkw_kwp else 800
            jahres_ertrag, jahres_einsparung, co2_einsparung = _bkw_pauschal_beitrag(
                inv,
                strompreis_cent=strompreis_cent,
                einspeiseverguetung_cent=einspeiseverguetung_cent,
            )
            eigenverbrauch = jahres_ertrag * 0.8

            detail = {
                'leistung_wp': leistung_wp,
                'jahres_ertrag_kwh': round(jahres_ertrag, 0),
                'eigenverbrauch_kwh': round(eigenverbrauch, 0),
                'hinweis': f'Balkonkraftwerk {leistung_wp} Wp',
            }

        elif inv.typ == InvestitionTyp.WECHSELRICHTER.value:
            # Wechselrichter ohne zugeordnete PV-Module
            detail = {
                'hinweis': 'Wechselrichter ohne zugeordnete PV-Module - bitte PV-Module zuordnen',
            }

        else:
            # Wallbox, Sonstiges — die einzigen Typen, für die eedc **keine**
            # Ersparnis konstruiert: sie hängt allein am gepflegten Feld
            # „Ertrag/Jahr" (`ERTRAGSFELD_TYPEN`, Konzept §8/1).
            #
            # ⛔ **Bis 2026-09-01 setzte dieser Zweig als EINZIGER kein
            # `nicht_bewertet`** — und zeigte damit genau die Fake-0, gegen die
            # N-87 angetreten war und die N-258 am 16.08. für die Wärmepumpe
            # abgestellt hat. An der Demo-Anlage gemessen (01.09., alle vier
            # Zeilen ohne gepflegtes Feld):
            #   Wallbox 800 €            → „0,00 €"
            #   Mini-BHKW 8.000 €        → **„−300,00 €"**  (0 − betriebskosten_jahr)
            #   Heizstab · Gaszähler     → „0,00 €"
            # Die −300 € sind wörtlich der N-258-Fall („−200 € Einsparung für
            # ein Gerät, dessen Hinweis mit *Nicht bewertet* beginnt"), nur an
            # einem anderen Zweig; `_angezeigte_jahres_einsparung` fängt ihn
            # ausschließlich über dieses Flag.
            #
            # ⚑ Und der Gaszähler zeigt, dass es nicht nur um die Optik geht:
            # die *Zähler*-Kategorie unter Sonstiges ist seit v4.0.23
            # ausdrücklich „nur erfassen und anzeigen, **ohne Bewertung**" —
            # eine 0 in der Einsparungs-Spalte behauptete dort das Gegenteil.
            #
            # `is None` statt truthy (CLAUDE.md, 0-Werte): eine gepflegte **0**
            # ist eine Aussage des Anwenders („bringt nichts") und bleibt eine
            # bewertete Zeile. Nur das ungepflegte Feld ist unbewertet.
            # ⚠ `co2_einsparung_prognose_kg` steht bewusst NICHT in der
            # Bedingung: es hat keinen Schreiber (nur in `InvestitionResponse`,
            # nicht in Base/Create/Update, kein Formularfeld, 0 Datensätze im
            # Bestand) — es kann also keinen gepflegten CO₂-Wert verdecken.
            # §9.2 Geldseite (11b): der Jahres-Ertrag kommt aus dem SoT, nicht
            # mehr direkt aus dem Feld. Für ein Gerät der Kategorie *Abgabe an
            # Dritte* rechnet er aus den **gemessenen Monatserlösen**; für alles
            # andere gilt §8/1 unverändert. Der Vorrang (gemessen vor geschätzt)
            # ist dort entschieden — hier wird er nur gelesen.
            #
            # ⛔ Der Laufzeit-Filter bleibt bei DIESER Route und wird NICHT
            # angeglichen: Ohne `jahr` lädt sie bewusst auch stillgelegte
            # Investitionen (`:1189` — „Issue #123: spätere Stilllegung darf
            # Vergangenheit nicht löschen"), während Aussichten und HA-Export
            # auf „heute aktiv" filtern, weil sie PROGNOSEN sind. Zwei Fragen,
            # zwei Umfänge — wer das einebnet, beantwortet eine davon falsch.
            posten = jahresertrag_posten(inv, _anlage_fakten)
            co2_einsparung = inv.co2_einsparung_prognose_kg or 0
            if posten is None:
                jahres_einsparung = 0
                detail = {
                    'hinweis': (
                        'Kein Erlös gepflegt — die abgegebenen Kilowattstunden '
                        'tragen ohne ihn kein Geld: weder als Eigenverbrauch '
                        'noch als Einspeisung, und eedc kennt deinen Satz '
                        'nicht. Der Erlös lässt sich am Gerät monatlich als '
                        '„Erlös (€)" pflegen; ersatzweise ein Jahresbetrag als '
                        '„Ertrag/Jahr (€)" in der Investitionspflege.'
                    ) if ist_abgabe_kategorie((inv.parameter or {}).get('kategorie')) else (
                        'Kein Ertrag/Jahr gepflegt — ohne ihn bewertet eedc diese '
                        'Zeile nicht. Der Wert lässt sich in der Investitionspflege '
                        'als „Ertrag/Jahr (€)" nachtragen.'
                    ),
                    'nicht_bewertet': True,
                }
            else:
                jahres_einsparung = jahres_ersparnis_euro([posten])
                detail = {
                    'hinweis': (
                        f'{posten.bezeichnung}: {posten.monate} Monate gemessen, '
                        'auf ein Jahr hochgerechnet'
                    ) if posten.bezeichnung == BEZEICHNUNG_ABGABE
                    else 'Manuelle Prognose verwendet'
                }

        # #310: manuell gepflegte sonstige Erträge/Ausgaben einrechnen — seit
        # F-19 die Ausgaben kumuliert im Nenner statt annualisiert im Zähler,
        # seit Bauschritt 7 die Erträge ebenso, nur mindernd.
        inv_sonstige_ausgaben = _sonstige_ausgaben_kumuliert_fuer([inv.id])
        inv_sonstige_ertraege = _sonstige_ertraege_kumuliert_fuer([inv.id])
        inv_kapitaleinsatz = kapitaleinsatz_euro(
            relevante_kosten_euro=kosten - alternativ,
            sonstige_ausgaben_euro=inv_sonstige_ausgaben,
            sonstige_ertraege_euro=inv_sonstige_ertraege,
        )
        if isinstance(detail, dict):
            detail['sonstige_netto_euro'] = round(inv_sonstige_ertraege - inv_sonstige_ausgaben, 2)
            detail['sonstige_ausgaben_euro'] = round(inv_sonstige_ausgaben, 2)
            detail['sonstige_ertraege_euro'] = round(inv_sonstige_ertraege, 2)
            # ⛔ **Hier stand bis 2026-08-16 die Rücknahme des Flags (N-87):**
            # „Hat der Anwender selbst einen Betrag gepflegt, ist die Zeile sehr
            # wohl bewertet — dann seine Zahl zeigen statt „—"." **Diese
            # Prämisse ist gefallen (N-258, gemessen):** Die
            # Einsparungs-Spalte trägt seinen Betrag nie. Eine gepflegte
            # Förderung von 180 € an einer unbewerteten Wärmepumpe ließ die
            # Zeile „0,00 €" zeigen — also genau die Fake-0, gegen die N-87
            # angetreten war; ein Wartungsposten ließ sie „−200,00 €" zeigen.
            # Der gepflegte Betrag wirkt, wo er hingehört: im
            # **Kapitaleinsatz** (oben, `inv_kapitaleinsatz` — 8.000 → 7.820
            # bzw. 8.180) und in `sonstige_*_euro` im `detail`. Die Rücknahme
            # nahm der Zeile obendrein ihren sichtbaren Grund: der Zusatz
            # „· nicht bewertet" hängt am selben Flag.
        betriebskosten = inv.betriebskosten_jahr or 0
        netto_einsparung = _angezeigte_jahres_einsparung(
            jahres_einsparung=jahres_einsparung,
            betriebskosten=betriebskosten,
            detail=detail,
        )
        roi_result = berechne_roi(inv_kapitaleinsatz, jahres_einsparung, 0, betriebskosten)
        gesamt_betriebskosten += betriebskosten
        inv_zeilen_jahr = _treppe_zeile(
            invs=[inv], kosten_je_inv={inv.id: kosten - alternativ},
            netto_einsparung=netto_einsparung,
        )

        berechnungen.append(ROIBerechnung(
            investition_id=inv.id,
            investition_bezeichnung=inv.bezeichnung,
            investition_typ=inv.typ,
            anschaffungsjahr=inv_zeilen_jahr if basis_jahr is not None else None,
            anschaffungskosten=kosten,
            anschaffungskosten_alternativ=alternativ,
            relevante_kosten=relevante,
            kapitaleinsatz=round(inv_kapitaleinsatz, 2),
            jahres_einsparung=round(netto_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            amortisation_annahme=annahme_dauer_text(betriebskosten_jahr_euro=betriebskosten),
            co2_einsparung_kg=round(co2_einsparung, 1) if co2_einsparung else None,
            detail_berechnung=detail,
        ))

        gesamt_investition += kosten
        gesamt_relevante += relevante
        gesamt_sonstige_ausgaben += inv_sonstige_ausgaben
        gesamt_sonstige_ertraege += inv_sonstige_ertraege
        gesamt_einsparung += netto_einsparung
        gesamt_co2 += co2_einsparung
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("gesamt_betriebskosten", "gesamt_co2", "gesamt_einsparung", "gesamt_investition", "gesamt_relevante", "gesamt_sonstige_ausgaben", "gesamt_sonstige_ertraege",) if k in _loc}

