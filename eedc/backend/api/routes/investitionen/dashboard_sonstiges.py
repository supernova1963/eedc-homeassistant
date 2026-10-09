"""Komponenten-Dashboard Sonstiges (Erzeuger · Verbraucher · Zaehler · Abgabe an Dritte).

GET /api/investitionen/dashboard/sonstiges/{anlage_id}
"""
# Reiner Umzug aus `api/routes/investitionen/dashboards.py` (18.09.2026, Vorlage 6 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `dashboards.py` haengt den Router an der
# bisherigen Stelle ein und exportiert die Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeiseverguetung_cent,
    resolve_strompreis_for_komponente,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.services.zaehlerstaende import lade_zaehlerstaende, zaehler_art, zaehler_einheit
from backend.core.berechnungen.speicher_wirtschaftlichkeit import berechne_speicher_ersparnis
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.core.field_definitions import (
    get_sonstiges_verbrauch_kwh,
    ist_gepflegte_sonstiges_kategorie,
    ist_zaehler_kategorie,
)
from backend.core.berechnungen import (
    sonstiges_richtung,
    eigenverbrauchsquote_prozent,
    einspeise_erloes_euro,
    speicher_wirkungsgrad,
)
from backend.api.routes.investitionen.crud import InvestitionResponse
from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse, _gewichtete_monatspreise

router = APIRouter()


class SonstigesMonatsWert(BaseModel):
    """Ein Monat eines sonstigen **Verbrauchers**, so wie die Kopfzahlen ihn rechnen (N-645; Bauform N-638).

    Der Hub-Vergleich summierte bis 4.1.3 den Legacy-Zwilling ``verbrauch_kwh`` (Kopf und Lesetür nehmen den Kanon
    ``verbrauch_sonstig_kwh`` zuerst): wer nur den Kanon pflegt, sah 0, wer beide hat, den alten Wert. Der Verlauf
    stapelte PV- und Netzbezug — ein Verbraucher ohne diese Messung hatte dort kein Segment, obwohl der Kopf seinen
    Verbrauch nennt. **Fachentscheid Master 09.10.2026:** der Teil des Verbrauchs, den keine PV-/Netz-Messung
    aufteilt, steht als eigenes Segment *nicht aufgeteilt* (K5-Bauform: die Aufteilung steht neben der Gesamtmenge,
    nie über ihr). Σ Monate = ``gesamt_verbrauch_kwh``, ``bezug_pv_kwh``, ``bezug_netz_kwh``.

    Nur die Kategorie *Verbraucher* trägt die Reihe: Erzeuger, Speicher und Zähler lesen ihren Verlauf weiter aus den
    Monatszeilen, und dort ist der Kopf dasselbe Rohfeld.
    """
    jahr: int
    monat: int
    #: ``get_sonstiges_verbrauch_kwh`` (Kanon ``verbrauch_sonstig_kwh`` zuerst)
    verbrauch_kwh: float
    bezug_pv_kwh: float
    bezug_netz_kwh: float
    #: Verbrauch − PV − Netz, nie < 0 — ohne PV-/Netz-Messung der ganze Verbrauch
    nicht_aufgeteilt_kwh: float


class SonstigesDashboardResponse(BaseModel):
    """Sonstiges Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    #: N-645: die bewertete Monatsreihe eines Verbrauchers — Hub-Verlauf und -Vergleich lesen sie statt
    #: ``monatsdaten[].verbrauch_daten``. Leer für Erzeuger, Speicher und Zähler.
    monatsreihe: list[SonstigesMonatsWert] = []
    zusammenfassung: dict[str, Any]

def _monatsverbrauch_aus_verlauf(fenster) -> list[dict]:
    """Verbrauch je Kalendermonat aus einem Stand-Verlauf (#377).

    Aus einer **Bestands**reihe (Zählerstände) wird eine **Fluss**reihe
    (Verbrauch je Monat): je Monat der letzte bekannte Stand, dann die Differenz
    zum letzten Stand des Vormonats.

    ⚠ **Der erste Monat der Aufzeichnung bekommt keinen Wert.** Es gibt keinen
    Vormonatsstand, gegen den man ihn messen könnte — eine 0 dort wäre die
    Behauptung „in diesem Monat wurde nichts verbraucht" (ADR-002/P4).

    ⚠ Ein **Rücksprung** (neuer Zähler ohne Stilllegung) ergäbe eine negative
    Differenz. Sie wird ausgelassen statt gekappt: eine stille Kappung machte
    aus einem Widerspruch eine plausibel aussehende Zahl. Der Daten-Checker
    macht daraus einen Hinweis mit dem Weg (§4: stilllegen + neu anlegen).
    """
    if fenster is None or not fenster.verlauf:
        return []
    letzter_je_monat: dict[tuple[int, int], float] = {}
    for punkt in fenster.verlauf:
        letzter_je_monat[(punkt.zeitpunkt.year, punkt.zeitpunkt.month)] = punkt.stand

    out: list[dict] = []
    vorher: Optional[float] = None
    for (j, m) in sorted(letzter_je_monat):
        stand = letzter_je_monat[(j, m)]
        if vorher is not None and stand >= vorher:
            out.append({
                'jahr': j, 'monat': m,
                'verbrauch': round(stand - vorher, 3),
                'stand': stand,
            })
        vorher = stand
    return out

@router.get("/dashboard/sonstiges/{anlage_id}", response_model=list[SonstigesDashboardResponse])
async def get_sonstiges_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(
        None, description="Override: Strompreis (auto aus dem Monatstarif wenn leer)"
    ),
    einspeiseverguetung_cent: Optional[float] = Query(
        None, description="Override: Einspeisevergütung (auto aus dem Monatstarif wenn leer)"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Sonstiges Dashboard für eine Anlage.

    Zeigt sonstige Investitionen (Mini-BHKW, Pelletofen, etc.) mit kategorie-abhängigen Daten.

    **Dieselbe Klasse wie Befund F-4 beim Balkonkraftwerk**, hier für BEIDE
    Preisseiten: die Query-Parameter waren Pflichtwerte mit den Defaults 30,0
    und 8,0 ct/kWh, und ``v4/komponentenAdapter.tsx`` ruft die Route ohne
    Preise auf — die Konstanten galten also immer, unabhängig vom gepflegten
    Tarif. Ein BHKW rechnete seine Ersparnis mit 30 ct, auch wenn der Vertrag
    auf 24 ct lautete.

    Jetzt kommen beide Preise je Monat aus dem dann gültigen Tarif
    (ADR-002/**P8**), gewichtet mit der Menge, die die jeweilige Kategorie
    tatsächlich bewertet: Eigenverbrauch beim Erzeuger, Netzbezug beim
    Verbraucher, Entladung beim Speicher. Die Query-Parameter bleiben als
    Override erhalten.
    """
    tarife_heute = await lade_tarife_fuer_anlage(db, anlage_id)
    fallback_bezug = (
        strompreis_cent
        if strompreis_cent is not None
        else resolve_strompreis_for_komponente(tarife_heute, "allgemein")
    )
    fallback_einspeise = (
        einspeiseverguetung_cent
        if einspeiseverguetung_cent is not None
        else resolve_einspeiseverguetung_cent(tarife_heute)
    )

    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SONSTIGES.value)
    )
    sonstige = inv_result.scalars().all()

    if not sonstige:
        return []

    dashboards = []
    for inv in sonstige:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == inv.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        # #308: SoT-Filter auf die Laufzeit (Anschaffung→Stilllegung), wie bei
        # den fünf anderen Dashboards in dieser Datei. Ohne ihn flossen Monate
        # vor Anschaffung / nach Stilllegung in die gesamt_*-Summen.
        monatsdaten = [
            md for md in md_result.scalars().all()
            if inv.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        params = inv.parameter or {}
        # N-244: ohne gepflegte Kategorie wird hier nicht mehr „Erzeuger"
        # geraten. Der Einwand aus N-250 („über viele Monate gibt es kein
        # einzelnes *hat Erzeugung*") stimmt für einen Monat — über den ganzen
        # Bestand ist die Frage beantwortbar, und genau den hat diese Schleife
        # schon geladen. Vorher aggregierte ein ungepflegtes **Verbrauchs**gerät
        # ausschließlich Erzeugungsfelder: der Hub zeigte lauter Nullen, obwohl
        # gepflegte Verbrauchswerte danebenlagen.
        kategorie = params.get('kategorie')
        if not ist_gepflegte_sonstiges_kategorie(kategorie):
            kategorie = sonstiges_richtung(
                None,
                hat_erzeugung=any(
                    (md.verbrauch_daten or {}).get('erzeugung_kwh') for md in monatsdaten
                ),
            )
        beschreibung = params.get('beschreibung', '')

        # Aggregation basierend auf Kategorie
        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_verbrauch = 0
        gesamt_bezug_pv = 0
        gesamt_bezug_netz = 0
        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_sonstige_ertraege = 0
        gesamt_sonstige_ausgaben = 0

        # Gewichte für die Tarif-Mittelung (ADR-002/P8): je Kategorie die
        # Menge, die unten auch bewertet wird. Ein Monat ohne bewertete Menge
        # trägt keinen Preis bei — sonst zöge ein datenloser Altmonat mit
        # altem Tarif den Ø nach unten.
        preis_gewichte: dict[tuple[int, int], float] = {}
        monatsreihe: list[SonstigesMonatsWert] = []

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            summen = berechne_sonstige_summen(d)
            gesamt_sonstige_ertraege += summen["ertraege_euro"]
            gesamt_sonstige_ausgaben += summen["ausgaben_euro"]

            if kategorie == 'erzeuger':
                gesamt_erzeugung += d.get('erzeugung_kwh', 0)
                gesamt_eigenverbrauch += d.get('eigenverbrauch_kwh', 0)
                gesamt_einspeisung += d.get('einspeisung_kwh', 0)
                preis_gewichte[(md.jahr, md.monat)] = d.get('eigenverbrauch_kwh', 0) or 0
            elif kategorie == 'verbraucher':
                gesamt_verbrauch += get_sonstiges_verbrauch_kwh(d)
                gesamt_bezug_pv += d.get('bezug_pv_kwh', 0)
                gesamt_bezug_netz += d.get('bezug_netz_kwh', 0)
                # N-645: dieselben drei Werte je Monat, dazu der Rest ohne Aufteilung.
                monatsreihe.append(_verbraucher_monatswert(md, d))
                preis_gewichte[(md.jahr, md.monat)] = (
                    (d.get('bezug_netz_kwh', 0) or 0) + (d.get('bezug_pv_kwh', 0) or 0)
                )
            elif kategorie == 'speicher':
                gesamt_ladung += d.get('ladung_kwh', 0)
                gesamt_entladung += d.get('entladung_kwh', 0)
                preis_gewichte[(md.jahr, md.monat)] = d.get('entladung_kwh', 0) or 0

        gesamt_sonstige_netto = gesamt_sonstige_ertraege - gesamt_sonstige_ausgaben

        # Beide Preisseiten je Monat, EIN Aufruf: bei den Kategorien
        # `erzeuger` und `speicher` gehen sie gemeinsam in eine Formel
        # (Eigenverbrauch gegen Einspeisung bzw. der Spread), und zwei
        # Zeitpunkte in einer Differenz sind genau der Fehler, den P8 meint.
        preise = await _gewichtete_monatspreise(
            db, anlage_id, "allgemein", preis_gewichte,
            fallback_bezug=fallback_bezug,
            fallback_einspeise=fallback_einspeise,
        )
        inv_strompreis_cent = preise.bezug_cent
        inv_einspeise_cent = preise.einspeise_cent

        # Berechnungen je nach Kategorie
        if kategorie == 'erzeuger':
            eigenverbrauch_quote = eigenverbrauchsquote_prozent(gesamt_eigenverbrauch, gesamt_erzeugung)
            ersparnis_eigenverbrauch = gesamt_eigenverbrauch * inv_strompreis_cent / 100
            # §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh = None auf
            # Monatsdaten-Aggregat-Ebene → volle Einspeisung (verhaltensneutral).
            erloes_einspeisung = einspeise_erloes_euro(
                gesamt_einspeisung, None, inv_einspeise_cent
            ).erloes_euro
            gesamt_ersparnis = ersparnis_eigenverbrauch + erloes_einspeisung + gesamt_sonstige_netto
            co2_ersparnis = gesamt_eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
                'gesamt_eigenverbrauch_kwh': round(gesamt_eigenverbrauch, 1),
                'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),
                'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
                'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
                'erloes_einspeisung_euro': round(erloes_einspeisung, 2),
                'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
                'co2_ersparnis_kg': round(co2_ersparnis, 1),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        elif kategorie == 'verbraucher':
            pv_anteil = (gesamt_bezug_pv / gesamt_verbrauch * 100) if gesamt_verbrauch > 0 else 0
            kosten_netz = gesamt_bezug_netz * inv_strompreis_cent / 100
            # Ersparnis: PV-Strom statt Netzstrom + sonstige Erträge/Ausgaben
            ersparnis_pv = gesamt_bezug_pv * inv_strompreis_cent / 100 + gesamt_sonstige_netto

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_verbrauch_kwh': round(gesamt_verbrauch, 1),
                'bezug_pv_kwh': round(gesamt_bezug_pv, 1),
                'bezug_netz_kwh': round(gesamt_bezug_netz, 1),
                'pv_anteil_prozent': round(pv_anteil, 1),
                'kosten_netz_euro': round(kosten_netz, 2),
                'ersparnis_pv_euro': round(ersparnis_pv, 2),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        elif ist_zaehler_kategorie(kategorie):
            # #377 — ein Zähler wird ERFASST, nicht BEWERTET.
            #
            # ⚠ **Ohne diesen Zweig fiele er in den Speicher-Zweig darunter**
            # (`else`) und bekäme eine Effizienz aus Ladung/Entladung, die er
            # nicht hat, sowie eine Ersparnis aus einem Spread, den es für Gas
            # nicht gibt — vier Nullen, die wie eine Aussage aussehen. Genau
            # das ist der v4.0.17-Befund bei der Klimaanlage, und die Antwort
            # ist dieselbe: **„nicht bewertet" sagen, statt Nullen zu zeigen.**
            #
            # Eine Wirtschaftlichkeit ist hier nicht bloß unbekannt, sie ist
            # nicht anwendbar: Gas- und Wasserkosten sind Haushaltskosten und
            # gehören nicht in die Bewertung der PV-Anlage (Präzedenz: der
            # Einspeise-Erlös eines Fremd-Erzeugers, `field_definitions.py`).
            zaehler_fenster = next(
                (
                    z for z in await lade_zaehlerstaende(
                        db, anlage_id,
                        datetime(1970, 1, 1), datetime.now(),
                        mit_verlauf=True, nur_aktive=False,
                    )
                    if z.investition_id == inv.id
                ),
                None,
            )
            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'zaehler_art': zaehler_art(inv),
                'einheit': zaehler_einheit(inv),
                'stand_anfang': zaehler_fenster.stand_anfang if zaehler_fenster else None,
                'stand_ende': zaehler_fenster.stand_ende if zaehler_fenster else None,
                'differenz': zaehler_fenster.differenz if zaehler_fenster else None,
                'anfang_vollstaendig': (
                    zaehler_fenster.anfang_vollstaendig if zaehler_fenster else True
                ),
                'verlauf': [
                    {'zeitpunkt': p.zeitpunkt.isoformat(), 'stand': p.stand}
                    for p in (zaehler_fenster.verlauf if zaehler_fenster else [])
                ],
                # Der Verbrauch JE MONAT — die Differenz zweier aufeinander
                # folgender Stände.
                #
                # ⚑ **Warum das Backend sie rechnet und nicht der Hub:** Ein
                # Zählerstand ist eine Bestandsgröße, sein Verbrauch eine
                # Flussgröße — das ist ein Wechsel der Größenart, keine
                # Formatierung. Im Client gerechnet gäbe es die Rechnung
                # „Ende − Anfang" ein zweites Mal, und die zweite läuft
                # irgendwann anders (die P10-Klasse).
                'monatsverbrauch': _monatsverbrauch_aus_verlauf(zaehler_fenster),
                # Bewusst KEINE der `gesamt_*`-, `ersparnis_*`- oder
                # `co2_*`-Größen: Ein Feld mit 0 wäre eine Behauptung.
                'bewertet': False,
                'nicht_bewertet_grund': (
                    "Ein Verbrauchszähler wird in eedc erfasst und angezeigt, aber "
                    "nicht bewertet: Gas, Wasser oder Heizöl sind Haushaltskosten "
                    "und gehören nicht in die Wirtschaftlichkeit der PV-Anlage."
                ),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        else:  # speicher
            # Layer-SoT statt eigener Division (N-252) — dieselbe Zahl wie
            # Speicher-Dashboard, Cockpit und HA-Sensor.
            _eta_sonst = speicher_wirkungsgrad(
                gesamt_ladung, gesamt_entladung, None, langes_fenster_quelle="fenster_lang"
            )
            effizienz = _eta_sonst.prozent
            # Ersparnis über den Layer-SoT (#358): Spread zwischen Netzbezug und
            # Einspeisung, beide Seiten aus derselben Monats-Mittelung
            # (ADR-002/P8). Der Spread stand hier als Inline-Formel; ein
            # Speicher unter „Sonstiges" erfasst keine Netzladung, der Aufruf
            # ist deshalb verhaltensgleich — er bindet die Definition nur an
            # ihre eine Heimat (ADR-001).
            ersparnis = berechne_speicher_ersparnis(
                entladung_kwh=gesamt_entladung,
                bezug_preis_cent=inv_strompreis_cent,
                einspeise_verg_cent=inv_einspeise_cent,
            ).ersparnis_euro + gesamt_sonstige_netto

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_ladung_kwh': round(gesamt_ladung, 1),
                'gesamt_entladung_kwh': round(gesamt_entladung, 1),
                'effizienz_prozent': round(effizienz, 1) if effizienz is not None else None,
                'effizienz_quelle': _eta_sonst.quelle,
                'ersparnis_euro': round(ersparnis, 2),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        dashboards.append(SonstigesDashboardResponse(
            investition=inv,
            monatsdaten=monatsdaten,
            monatsreihe=monatsreihe,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


def _verbraucher_monatswert(md, d: dict) -> SonstigesMonatsWert:
    """Ein Monat eines Verbrauchers aus denselben Werten, die die Kopfzahlen summieren (N-645).

    Verbrauch über die Lesetür (Kanon vor Legacy), PV- und Netzbezug wie der Kopf; was beide nicht erklären, ist
    *nicht aufgeteilt* — ohne Messung der ganze Verbrauch, mit Teilmessung der Rest, nie negativ (eine Aufteilung,
    die mehr misst als der Verbrauch, wird nicht „korrigiert", der Rest ist dann 0).
    """
    verbrauch = float(get_sonstiges_verbrauch_kwh(d))
    pv = float(d.get('bezug_pv_kwh', 0) or 0)
    netz = float(d.get('bezug_netz_kwh', 0) or 0)
    return SonstigesMonatsWert(
        jahr=md.jahr,
        monat=md.monat,
        verbrauch_kwh=verbrauch,
        bezug_pv_kwh=pv,
        bezug_netz_kwh=netz,
        nicht_aufgeteilt_kwh=max(0.0, verbrauch - pv - netz),
    )
