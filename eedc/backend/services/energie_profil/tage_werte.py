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
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.energie_profil._shared import TagWerteResponse
from backend.core.berechnungen import berechne_finanz_aggregat, bilanz_aus_stundenrows
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
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

    alle_tage = sorted(set(tep_pro_tag) | set(tz_pro_tag))
    tarif_cache: dict[date, dict] = {}
    zeilen: list[TagWerteResponse] = []

    for tag in alle_tage:
        bilanz = bilanz_aus_stundenrows(tep_pro_tag.get(tag, []))
        tz = tz_pro_tag.get(tag)

        # ── Finanzen über den SoT-Helper (je-Monat-Tarif, §51-bereinigt) ──
        eingabe = FinanzZeileEingabe(
            jahr=tag.year,
            monat=tag.month,
            einspeisung_kwh=bilanz.einspeisung_kwh,
            netzbezug_kwh=bilanz.netzbezug_kwh,
            pv_erzeugung_kwh=bilanz.erzeugung_kwh,
            neg_preis_kwh=(tz.einspeisung_neg_preis_kwh if tz else None),
            # Speicher/V2H/BKW = 0: Netto-Flüsse bilden Speicher schon ab.
            monatsdaten=None,
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
            # Energie
            erzeugung=round(bilanz.erzeugung_kwh, 3),
            eigenverbrauch=round(bilanz.eigenverbrauch_kwh, 3),
            einspeisung=round(bilanz.einspeisung_kwh, 3),
            netzbezug=round(bilanz.netzbezug_kwh, 3),
            gesamtverbrauch=round(bilanz.gesamtverbrauch_kwh, 3),
            direktverbrauch=round(bilanz.direktverbrauch_kwh, 3),
            # Quoten
            autarkie=_r(bilanz.autarkie_prozent, 1),
            evQuote=_r(bilanz.ev_quote_prozent, 1),
            spezErtrag=(round(bilanz.erzeugung_kwh / kwp, 2) if kwp > 0 else None),
            # Speicher (None wenn kein Lade-/Entlade-Geschehen)
            speicher_ladung=_nz(bilanz.speicher_ladung_kwh),
            speicher_entladung=_nz(bilanz.speicher_entladung_kwh),
            speicher_effizienz=_r(bilanz.speicher_effizienz_prozent, 1),
            wp_strom=_nz(bilanz.wp_strom_kwh),
            # Finanzen
            einspeise_erloes=round(finanz.einspeise_erloes_euro, 2),
            ev_ersparnis=round(finanz.ev_ersparnis_euro, 2),
            netzbezug_kosten=round(netzbezug_kosten, 2),
            netto_ertrag=round(netto_ertrag, 2),
            netto_bilanz=round(netto_bilanz, 2),
            # CO₂
            co2_einsparung=round(bilanz.erzeugung_kwh * CO2_FAKTOR_STROM_KG_KWH, 1),
            # Tag-native
            ueberschuss_kwh=round(bilanz.ueberschuss_kwh, 3),
            defizit_kwh=round(bilanz.defizit_kwh, 3),
            peak_pv_kw=(tz.peak_pv_kw if tz else None),
            peak_netzbezug_kw=(tz.peak_netzbezug_kw if tz else None),
            peak_einspeisung_kw=(tz.peak_einspeisung_kw if tz else None),
            performance_ratio=(tz.performance_ratio if tz else None),
            batterie_vollzyklen=(tz.batterie_vollzyklen if tz else None),
            temperatur_min_c=(tz.temperatur_min_c if tz else None),
            temperatur_max_c=(tz.temperatur_max_c if tz else None),
            strahlung_summe_wh_m2=(tz.strahlung_summe_wh_m2 if tz else None),
            boersenpreis_avg_cent=(tz.boersenpreis_avg_cent if tz else None),
            boersenpreis_min_cent=(tz.boersenpreis_min_cent if tz else None),
            negative_preis_stunden=(tz.negative_preis_stunden if tz else None),
            einspeisung_neg_preis_kwh=(tz.einspeisung_neg_preis_kwh if tz else None),
        ))

    return zeilen


def _r(v: float | None, dec: int) -> float | None:
    return round(v, dec) if v is not None else None


def _nz(v: float) -> float | None:
    """0-Σ → None (keine aktive Komponente an dem Tag)."""
    return round(v, 3) if abs(v) > 1e-9 else None
