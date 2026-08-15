"""Tages-Werte-Builder für die Werte/Tabelle-Embed-Sicht (IA v4 E3, Cockpit/Monat).

Liefert pro Tag eine vollständige Werte-Zeile (Energie-Bilanz + Quoten +
Speicher/WP + Finanzen + CO₂ + tag-native Peaks/PR/Börsenpreis) — die
numerische Zwillings-Quelle des Tagesverlauf-Charts.

**Keine Aggregat-Logik im Frontend** ([[feedback_aggregations_drift]]): die
Energie-Bilanz kommt aus dem SoT-Helper `bilanz_aus_stundenrows`
(core/berechnungen, identische Σ-Semantik wie der Monats-Endpoint
`get_monatsauswertung` → additive Symmetrie, vom Symmetrie-Test abgesichert).
Die Finanzen laufen über den `baue_finanz_zeile`-SoT (#326, je-Monat-Tarif);
Speicher/V2H/BKW werden bewusst mit 0 eingespeist, weil `einspeisung`/
`netzbezug` aus den stündlichen Netto-Flüssen kommen (Speicher ist dort schon
eingerechnet) — so ist die Finanz-Eigenverbrauchsmenge == der Energie-Spalte
`eigenverbrauch` (= PV − Einspeisung), keine Doppelzählung. Der Grundpreis ist
monatlich-fix und wird auf Tagesebene **nicht** anteilig verteilt.

**CO₂ — eine Definition, ein bewusst benannter Teil-Umfang (F-6, 2026-07-31).**
Bis dahin stand hier ``erzeugung × CO2_FAKTOR_STROM_KG_KWH``. Das war ein
Überlebender der DI-2-Ablösung: es schrieb auch der **eingespeisten** kWh die
volle Netzstrom-Vermeidung gut, lag also systematisch zu hoch. Gerechnet wird
jetzt über den Kanon ``berechne_co2_bilanz`` (ADR-001) — dieselbe Bezugsgröße
wie die Finanz-Spalte ``ev_ersparnis`` nebenan (Eigenverbrauch, nicht Erzeugung).

Der Tageswert trägt aus dieser Bilanz **nur den PV-Anteil** (``co2_pv_kg``):
WP-**Wärme** und E-Mobilitäts-**Kilometer** liegen ausschließlich monatlich vor
(``InvestitionMonatsdaten``); stündlich existiert von der Wärmepumpe nur die
Stromaufnahme (``TagesEnergieProfil.waermepumpe_kw``), und ohne Wärmemenge ist
die WP-Ersparnis nicht bestimmbar. Daraus folgt eine Aussage, die **nicht**
stillschweigend bleiben darf: **Σ Tage ≠ CO₂-Monatswert**, sobald die Anlage
eine Wärmepumpe oder ein E-Auto hat. Die vollständige Bilanz (PV + WP + E-Mob)
liefert ``/cockpit/nachhaltigkeit/{anlage}``; sie ist die Quelle von Cockpit/Jahr
und Auswertungen → CO₂. Die Spalte heißt im Client deshalb „CO₂-Einsparung (PV)".
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.energie_profil._shared import TagWerteResponse
from backend.core.berechnungen import (
    aggregiere_tep_komponenten,
    berechne_finanz_aggregat,
    bilanz_aus_stundenrows,
    delta_soc_kwh,
    erzeuger_kwh_je_investition,
    sonstiges_kwh_je_richtung,
    speicher_wirkungsgrad,
    summe_bkw_kwh,
    summe_pv_anlage_kwh,
    vollzyklen as berechne_vollzyklen,
)
from backend.core.calculations import berechne_co2_bilanz
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.einspeise_erloes_service import neg_preis_einspeisung_tageswert
from backend.services.finanz_zeilen import FinanzZeileEingabe, baue_finanz_zeile


async def baue_tage_werte(
    db: AsyncSession,
    anlage: Anlage,
    von: date,
    bis: date,
) -> list[TagWerteResponse]:
    """Baut die Tages-Werte-Zeilen für ``[von, bis]`` (inklusiv), aufsteigend.

    Eine Zeile pro Tag, der stündliche TEP-Daten **oder** eine
    Tageszusammenfassung hat. Energie aus TEP-Σ, tag-native Felder aus der
    Tageszusammenfassung.
    """
    anlage_id = anlage.id
    kwp = anlage.leistung_kwp or 0.0

    # Stündliche Rohdaten je Tag gruppieren
    tep_result = await db.execute(
        select(TagesEnergieProfil)
        .where(and_(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
        ))
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    tep_pro_tag: dict[date, list[TagesEnergieProfil]] = defaultdict(list)
    for r in tep_result.scalars().all():
        tep_pro_tag[r.datum].append(r)

    # Tageszusammenfassungen (tag-native Felder)
    tz_result = await db.execute(
        select(TagesZusammenfassung)
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
    )
    tz_pro_tag: dict[date, TagesZusammenfassung] = {
        t.datum: t for t in tz_result.scalars().all()
    }

    # Speicher-Kapazität für die Tages-Vollzyklen. Pro Tag ausgewertet, weil ein
    # Speicher mitten im Zeitraum dazukommen oder stillgelegt werden kann
    # ([[feedback_anschaffungsdatum_grenze]]).
    speicher_result = await db.execute(
        select(Investition).where(and_(
            Investition.anlage_id == anlage_id,
            Investition.typ == "speicher",
        ))
    )
    speicher_invs = list(speicher_result.scalars().all())

    # Sonstiges-Geräte für die beiden Sonstiges-Spalten. Wie beim Speicher pro
    # Tag ausgewertet — ein Heizstab kann mitten im Zeitraum dazukommen oder
    # stillgelegt werden ([[feedback_anschaffungsdatum_grenze]]).
    sonstiges_result = await db.execute(
        select(Investition).where(and_(
            Investition.anlage_id == anlage_id,
            Investition.typ == "sonstiges",
        ))
    )
    sonstiges_invs = list(sonstiges_result.scalars().all())

    # Monatsdaten des Zeitraums für den Flex-Ø-Override. Bei dynamischem Tarif
    # trägt `netzbezug_durchschnittspreis_cent` den ABGERECHNETEN Monats-Ø und
    # schlägt den Stammdaten-Arbeitspreis (`resolve_netzbezug_preis_cent`).
    # Ohne diese Zeilen rechnete der Tag mit dem Referenzpreis, während Monat
    # und Jahr den Ø nahmen — Σ Tage ≠ Monat ([[feedback_aggregator_symmetrie]]).
    md_result = await db.execute(
        select(Monatsdaten).where(and_(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr >= von.year,
            Monatsdaten.jahr <= bis.year,
        ))
    )
    md_pro_monat: dict[tuple[int, int], Monatsdaten] = {
        (m.jahr, m.monat): m for m in md_result.scalars().all()
    }

    alle_tage = sorted(set(tep_pro_tag) | set(tz_pro_tag))
    tarif_cache: dict[date, dict] = {}
    zeilen: list[TagWerteResponse] = []

    for tag in alle_tage:
        stunden_rows = tep_pro_tag.get(tag, [])
        bilanz = bilanz_aus_stundenrows(stunden_rows)
        tz = tz_pro_tag.get(tag)

        # Erträge je Erzeuger (#350, Rainer): erst der Boundary-Rollup, sonst die
        # Σ der Stunden-Komponenten. Der Rollup fehlt im Standalone-Betrieb und an
        # einzelnen Tagen auch im Add-on-Modus — genau deshalb liest die
        # Tages-Komponenten-Kachel im Client schon länger von den Stunden
        # (`v4/TagKomponenten.tsx`). Die ID-Normalisierung liegt im Layer, weil
        # dasselbe Balkonkraftwerk in den beiden Keyspaces `bkw_<id>` bzw.
        # `pv_<id>` heißt — je Roh-Key gruppiert ergäbe das zwei Spalten für ein
        # Gerät (s. `erzeuger_kwh_je_investition`).
        erzeuger_kwh = erzeuger_kwh_je_investition(tz.komponenten_kwh if tz else None)
        if not erzeuger_kwh:
            erzeuger_kwh = erzeuger_kwh_je_investition(
                aggregiere_tep_komponenten(stunden_rows)
            )

        # Sonstiges je Richtung — dieselbe Quellen-Präzedenz wie eine Zeile
        # darüber: erst der Boundary-Rollup, sonst die Σ der Stunden. Die
        # Kategorien werden **je Tag** gebildet, damit die Laufzeitgrenze des
        # Geräts gilt und nicht die des Zeitraums.
        sonstiges_kategorien = {
            str(i.id): ((i.parameter or {}).get("kategorie") or "")
            for i in sonstiges_invs if i.ist_aktiv_an(tag)
        }
        sonstiges = sonstiges_kwh_je_richtung(
            tz.komponenten_kwh if tz else None, sonstiges_kategorien
        )
        if sonstiges.erzeugung_kwh is None and sonstiges.verbrauch_kwh is None:
            sonstiges = sonstiges_kwh_je_richtung(
                aggregiere_tep_komponenten(stunden_rows), sonstiges_kategorien
            )
        # ── Speicher-η: derselbe Maßstab wie im Monat (Melder Knallfrosch,
        # T89667 #163). Der rohe Quotient Entladung ÷ Ladung stand hier ohne
        # jede Einordnung — an einem Tag, der voll beginnt und leer endet,
        # ergibt er über 100 %. `Cockpit → Monat` unterdrückt das seit F-22 und
        # nennt die Quelle; die Tagessicht tat beides nicht. ΔSoC kommt aus den
        # ohnehin geladenen Stunden-Rows, kostet also keine zusätzliche Abfrage.
        soc_delta = delta_soc_kwh(
            [r.soc_prozent for r in stunden_rows],
            sum(
                get_speicher_nutzbare_kapazitaet_kwh(i) or 0
                for i in speicher_invs if i.ist_aktiv_an(tag)
            ),
        )
        eta = speicher_wirkungsgrad(
            bilanz.speicher_ladung_kwh, bilanz.speicher_entladung_kwh, soc_delta,
        )

        # §51 gilt nur für Anlagen mit gesetztem Schalter — das Gate liegt im
        # Erlös-Service, nicht hier (bis 2026-08-03 las diese Zeile die Spalte
        # roh und kürzte den Erlös auch ohne §51-Pflicht).
        neg_preis_kwh = neg_preis_einspeisung_tageswert(
            anlage, tz.einspeisung_neg_preis_kwh if tz else None
        )

        # ── Finanzen über den SoT-Helper (je-Monat-Tarif, §51-bereinigt) ──
        eingabe = FinanzZeileEingabe(
            jahr=tag.year,
            monat=tag.month,
            einspeisung_kwh=bilanz.einspeisung_kwh,
            netzbezug_kwh=bilanz.netzbezug_kwh,
            pv_erzeugung_kwh=bilanz.erzeugung_kwh,
            neg_preis_kwh=neg_preis_kwh,
            # Speicher/V2H/BKW = 0: Netto-Flüsse bilden Speicher schon ab.
            monatsdaten=md_pro_monat.get((tag.year, tag.month)),
        )
        finanz_zeile = await baue_finanz_zeile(
            db, anlage_id, eingabe, tarif_cache=tarif_cache
        )
        finanz = berechne_finanz_aggregat([finanz_zeile])
        netzbezug_kosten = bilanz.netzbezug_kwh * finanz_zeile.netzbezug_preis_cent / 100
        netto_ertrag = finanz.netto_ertrag_euro
        netto_bilanz = netto_ertrag - netzbezug_kosten

        zeilen.append(TagWerteResponse(
            datum=tag,
            stunden_verfuegbar=(tz.stunden_verfuegbar if tz else bilanz.stunden),
            datenquelle=(tz.datenquelle if tz else None),
            # Energie. `erzeugung` ist None, solange keine Stunde einen PV-Wert
            # trug — eine 0 wäre hier nicht „nichts erzeugt", sondern „nicht
            # gemessen" (`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`). Betrifft
            # Anlagen, deren PV nur als Anlagen-Aggregat gepflegt ist: das
            # versorgt den Monat, nicht die Tagesebene.
            erzeugung=(round(bilanz.erzeugung_kwh, 3) if bilanz.pv_erfasst else None),
            # PV/BKW-Split (R17/Verlauf) aus dem Tages-komponenten_kwh-JSON.
            pv_anlage=round(summe_pv_anlage_kwh(tz.komponenten_kwh) if tz else 0.0, 3),
            bkw=round(summe_bkw_kwh(tz.komponenten_kwh) if tz else 0.0, 3),
            eigenverbrauch=_r(bilanz.eigenverbrauch_kwh, 3),
            einspeisung=round(bilanz.einspeisung_kwh, 3),
            netzbezug=round(bilanz.netzbezug_kwh, 3),
            gesamtverbrauch=round(bilanz.gesamtverbrauch_kwh, 3),
            direktverbrauch=round(bilanz.direktverbrauch_kwh, 3),
            # Quoten
            autarkie=_r(bilanz.autarkie_prozent, 1),
            evQuote=_r(bilanz.ev_quote_prozent, 1),
            spezErtrag=(
                round(bilanz.erzeugung_kwh / kwp, 2)
                if kwp > 0 and bilanz.pv_erfasst else None
            ),
            # Speicher (None wenn kein Lade-/Entlade-Geschehen)
            speicher_ladung=_nz(bilanz.speicher_ladung_kwh),
            speicher_entladung=_nz(bilanz.speicher_entladung_kwh),
            speicher_effizienz=_r(eta.prozent, 1),
            speicher_effizienz_quelle=eta.quelle,
            speicher_vollzyklen=_r(berechne_vollzyklen(
                bilanz.speicher_entladung_kwh,
                sum(
                    get_speicher_kapazitaet_kwh(i) or 0
                    for i in speicher_invs if i.ist_aktiv_an(tag)
                ),
            ), 2),
            wp_strom=_nz(bilanz.wp_strom_kwh),
            sonstiges_erzeugung=_r(sonstiges.erzeugung_kwh, 3),
            sonstiges_verbrauch=_r(sonstiges.verbrauch_kwh, 3),
            # Finanzen — bewusst UNGERUNDET, wie der Monatspfad
            # (`aktueller_monat.py`) sie liefert. Bis 15.08.2026 stand hier je
            # ein `round(…, 2)`, und das erzeugte zwei sichtbare Widersprüche
            # auf derselben Seite (Melder Knallfrosch, T89667 #163):
            #   · Die Finanz-Bilanz-Tabelle summiert die gerundeten Summanden
            #     (7,49 + 8,55 = 16,04), die Netto-Ertrag-Kachel zeigte die
            #     gerundete Summe (16,05) — Summe der Gerundeten gegen
            #     gerundete Summe.
            #   · „Ø-Preis Netz" teilt Kosten ÷ Menge. Bei 0,19 kWh machte der
            #     auf 2 Stellen gerundete Cent-Betrag daraus 31,6 ct/kWh,
            #     während dieselbe Seite mit ~29,5 ct rechnete.
            # Gerundet wird jetzt erst bei der Anzeige (Client, 2 Stellen); die
            # Σ-Zeile der Werte-Tabelle summiert dadurch ebenfalls exakt.
            einspeise_erloes=finanz.einspeise_erloes_euro,
            ev_ersparnis=finanz.ev_ersparnis_euro,
            netzbezug_kosten=netzbezug_kosten,
            netto_ertrag=netto_ertrag,
            netto_bilanz=netto_bilanz,
            # CO₂ — Kanon statt eigener Formel; nur der PV-Anteil ist auf
            # Tagesebene bestimmbar (s. Modul-Docstring). WP-Strom wird bewusst
            # NICHT übergeben: ohne die zugehörige Wärmemenge wäre die
            # WP-Komponente rein negativ und damit eine Falschaussage.
            # Ohne erfassten Eigenverbrauch gibt es keine CO₂-Aussage — vorher
            # wurde aus dem negativen Eigenverbrauch eine negative „Einsparung".
            co2_einsparung=(
                round(
                    berechne_co2_bilanz(
                        eigenverbrauch_kwh=bilanz.eigenverbrauch_kwh
                    ).co2_pv_kg,
                    1,
                )
                if bilanz.eigenverbrauch_kwh is not None else None
            ),
            # Tag-native
            ueberschuss_kwh=round(bilanz.ueberschuss_kwh, 3),
            defizit_kwh=round(bilanz.defizit_kwh, 3),
            peak_pv_kw=(tz.peak_pv_kw if tz else None),
            peak_netzbezug_kw=(tz.peak_netzbezug_kw if tz else None),
            peak_einspeisung_kw=(tz.peak_einspeisung_kw if tz else None),
            # PR ohne erfasste PV ist keine 0, sondern keine Aussage. Der
            # Aggregator schreibt sie seit demselben Paket gar nicht mehr;
            # diese Zeile deckt die Tage, die vorher schon eine 0 gespeichert
            # haben — es gibt bewusst keinen Migrationslauf.
            performance_ratio=(
                tz.performance_ratio if (tz and bilanz.pv_erfasst) else None
            ),
            batterie_vollzyklen=(tz.batterie_vollzyklen if tz else None),
            temperatur_min_c=(tz.temperatur_min_c if tz else None),
            temperatur_max_c=(tz.temperatur_max_c if tz else None),
            strahlung_summe_wh_m2=(tz.strahlung_summe_wh_m2 if tz else None),
            boersenpreis_avg_cent=(tz.boersenpreis_avg_cent if tz else None),
            boersenpreis_min_cent=(tz.boersenpreis_min_cent if tz else None),
            negative_preis_stunden=(tz.negative_preis_stunden if tz else None),
            # Ausweis-Spalte: dasselbe Gate wie die Rechnung darüber — sonst
            # nennt die Tagestabelle eine §51-Menge, die die Monatstabelle bei
            # derselben Anlage verschweigt (`monatsdaten.py`).
            einspeisung_neg_preis_kwh=neg_preis_kwh,
            # Leer bleibt leer: ohne eigenen Sensor je Erzeuger gibt es hier
            # keinen Wert. Auf Tagesebene wird **nicht** nach kWp verteilt
            # (anders als im Monat) — eine verteilte Tageszahl wäre in der
            # Spalte „Dach Süd" eine Behauptung über eine Messung, die es nicht
            # gibt (#352-Klasse).
            erzeuger_kwh={k: round(v, 3) for k, v in erzeuger_kwh.items()} or None,
        ))

    return zeilen


def _r(v: float | None, dec: int) -> float | None:
    return round(v, dec) if v is not None else None


def _nz(v: float) -> float | None:
    """0-Σ → None (keine aktive Komponente an dem Tag)."""
    return round(v, 3) if abs(v) > 1e-9 else None
