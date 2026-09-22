"""Komponenten-Dashboard Speicher (IST-Aggregate, Spread ueber die Lebensdauer, Wirkungsgrad-SoT).

GET /api/investitionen/dashboard/speicher/{anlage_id}
"""
# Reiner Umzug aus `api/routes/investitionen/dashboards.py` (18.09.2026, Vorlage 6 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `dashboards.py` haengt den Router an der
# bisherigen Stelle ein und exportiert die Namen weiter, die Aufrufer und Tests bisher von dort importierten.

import logging
from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from dataclasses import asdict
from datetime import date
from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeise_preis_cent,
    resolve_einspeiseverguetung_cent,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.core.investition_parameter import PARAM_SPEICHER, PARAM_SPEICHER_DEFAULTS
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    aggregiere_speicher_ist,
    berechne_speicher_ersparnis,
    ist_eta_degradation_alarm,
)
from backend.services.speicher_wirtschaftlichkeit import (
    berechne_effektiver_ladepreis,
    berechne_ist_wirkungsgrad,
    wirkungsgrad_ist_fuer_speicher,
)
from backend.core.field_definitions import get_speicher_netzladung_kwh
from backend.core.berechnungen import (
    gleitende_effizienz,
    pruefe_speicher_durchsatz_konsistenz,
    speicher_wirkungsgrad,
    vollzyklen as berechne_vollzyklen,
)
from backend.api.routes.investitionen.crud import InvestitionResponse
from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class SpeicherDashboardResponse(BaseModel):
    """Speicher Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]
    # Gleitende 12-Monats-Effizienz (carry-over-immun) — ersetzt die naive
    # Pro-Monats-Effizienz, die durch den SoC-Übertrag >100 % zappeln konnte.
    effizienz_verlauf: list[dict[str, Any]] = []

@router.get("/dashboard/speicher/{anlage_id}", response_model=list[SpeicherDashboardResponse])
async def get_speicher_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None),
    einspeiseverguetung_cent: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Speicher Dashboard für eine Anlage.

    Zeigt alle Speicher mit Zyklen, Effizienz, Eigenverbrauchserhöhung.
    Drift-Audit E: Tarife aus DB statt 30/8-Defaults aus Query-Param.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
    )
    speicher_list = inv_result.scalars().all()

    if not speicher_list:
        return []

    # Tarife aus DB laden (falls Query-Params nicht explizit übergeben)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    if strompreis_cent is None:
        strompreis_cent = resolve_strompreis_for_komponente(tarife, "allgemein")
    if einspeiseverguetung_cent is None:
        einspeiseverguetung_cent = resolve_einspeiseverguetung_cent(tarife)

    # Monatsdaten für Durchschnittspreis-Fallback laden
    anlage_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    anlage_md_dict = {
        (m.jahr, m.monat): m for m in anlage_md_result.scalars().all()
    }

    # Gewichteter Ø-Netzbezugspreis für Spread-Berechnung — Basistarif JE MONAT
    # (ADR-002/P8). Mit dem heutigen Tarif als Basis hätte eine Preiserhöhung
    # den Ø über die gesamte Speicher-Historie angehoben und damit den
    # Arbitrage-Spread rückwirkend verändert. Der Flex-Ø des Monats behält
    # weiterhin Vorrang (`resolve_netzbezug_preis_cent`).
    #
    # Die Einspeisevergütung läuft seit v4.0.7 durch DIESELBE Schleife: der
    # Spread ist `bezug − einspeise`, und solange nur der Minuend je Monat
    # aufgelöst wurde, stammten die beiden Summanden aus verschiedenen
    # Zeitpunkten. Gewichtet wird sie mit derselben Menge wie der Bezugspreis
    # — der Spread wird auf die Entladung angewendet, für die es hier keine
    # eigene Monatsaufteilung gibt.
    gew_preis_sum = 0.0
    gew_einspeise_sum = 0.0
    for m in anlage_md_dict.values():
        m_tarife = await lade_tarife_fuer_anlage(
            db, anlage_id, target_date=date(m.jahr, m.monat, 1)
        )
        m_basis = resolve_strompreis_for_komponente(
            m_tarife, "allgemein", fallback=strompreis_cent
        )
        gew_preis_sum += resolve_netzbezug_preis_cent(m, m_basis) * (m.netzbezug_kwh or 0)
        # #392: der Monatssatz der variablen Vergütung schlägt den Stamm-
        # Monatstarif — dieselbe zweite Auflösungsstufe wie beim Bezugspreis
        # eine Zeile darüber.
        gew_einspeise_sum += resolve_einspeise_preis_cent(
            m,
            resolve_einspeiseverguetung_cent(m_tarife, fallback=einspeiseverguetung_cent),
        ) * (m.netzbezug_kwh or 0)
    gew_kwh_sum = sum(m.netzbezug_kwh or 0 for m in anlage_md_dict.values())
    eff_strompreis_cent = gew_preis_sum / gew_kwh_sum if gew_kwh_sum > 0 else strompreis_cent
    eff_einspeise_cent = (
        gew_einspeise_sum / gew_kwh_sum if gew_kwh_sum > 0 else einspeiseverguetung_cent
    )

    # Batch-Query: Alle Monatsdaten für alle Speicher auf einmal laden
    speicher_ids = [s.id for s in speicher_list]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(speicher_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Etappe C (#264): TEP-basierter effektiver Ladepreis — anlageweit, einmal.
    # Periode = älteste Speicher-Installation bis heute (oder neueste
    # Stilllegung, wenn alle Speicher stillgelegt sind). Try/except-gekapselt:
    # das Dashboard darf nie an einem Helper sterben (analog aussichten/finanz_zerlegung.py).
    installs = [s.anschaffungsdatum for s in speicher_list if s.anschaffungsdatum]
    stilllegungen = [s.stilllegungsdatum for s in speicher_list if s.stilllegungsdatum]
    periode_von = min(installs) if installs else None
    periode_bis = (
        max(stilllegungen)
        if stilllegungen and len(stilllegungen) == len(speicher_list)
        else date.today()
    )
    eff_ladepreis = None
    if periode_von is not None:
        try:
            eff_ladepreis = await berechne_effektiver_ladepreis(
                db, anlage_id=anlage_id, von=periode_von, bis=periode_bis,
            )
        except Exception as e:
            logger.warning(
                f"Speicher-Dashboard Anlage {anlage_id}: effektiver Ladepreis "
                f"fehlgeschlagen: {type(e).__name__}: {e}"
            )

    dashboards = []
    for speicher in speicher_list:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(speicher.id, [])
            if speicher.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_arbitrage_kwh = 0
        arbitrage_preis_sum = 0
        arbitrage_count = 0

        monats_reihe: list[tuple[int, int, float, float]] = []
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            md_ladung = d.get('ladung_kwh', 0) or 0
            md_entladung = d.get('entladung_kwh', 0) or 0
            gesamt_ladung += md_ladung
            gesamt_entladung += md_entladung
            monats_reihe.append((md.jahr, md.monat, md_ladung, md_entladung))
            # Arbitrage (Netzladung zu günstigen Zeiten) — Kanon-Key
            # `ladung_netz_kwh` + Legacy-Fallback über den SoT-Helper; der
            # rohe Legacy-Read las nach der v3.26-Key-Migration immer 0.
            netzladung = get_speicher_netzladung_kwh(d)
            if netzladung > 0:
                gesamt_arbitrage_kwh += netzladung
                # ⛔ **Der Rückfall auf `netzbezug_durchschnittspreis_cent` ist
                # am 17.09.2026 entfallen, und er war schlimmer als eine Null.**
                # Er setzte den LADEpreis auf den Monats-Ø des BEZUGS — die
                # Gegenseite derselben Rechnung ist aber `eff_strompreis_cent`,
                # ebenfalls ein Mittel derselben Monatszahlen, nur anders
                # gewichtet (Netzladung gegen Netzbezug). Der „Arbitrage-Gewinn"
                # war damit die Differenz zweier Gewichtungen **einer** Zahl:
                # Rauschen, durch `max(0, …)` im Layer einseitig auf die
                # positive Seite geklemmt und kommentarlos als Gewinn
                # ausgewiesen. Ohne ihn ist das Ergebnis exakt 0 — die
                # dokumentierte Semantik „kostenneutrale Durchleitung".
                #
                # SOLL Flex-Tarife **P-1**: Eine Abrechnung gilt für die Größe,
                # für die sie ausgestellt ist. Eine Bezugsabrechnung sagt nichts
                # über den Preis einer Speicherladung.
                #
                # ⚠ **`is not None`, nicht `> 0`** (**P-8**): Bei dynamischen
                # Tarifen wird auch zu 0 ct oder negativ geladen — genau dann
                # ist die Arbitrage am größten. Die alte Prüfung warf diese
                # Monate aus der Gewichtung.
                preis = d.get('speicher_ladepreis_cent')
                if preis is not None:
                    arbitrage_preis_sum += preis * netzladung
                    arbitrage_count += netzladung

        # Effizienz — Σentladung/Σladung über die gesamte Historie. Über ein
        # langes Fenster mittelt sich der SoC-Übertrag aus (siehe
        # core/berechnungen/speicher.py); pro Monat wäre der Wert verzerrt.
        # Seit N-252 über den Layer-SoT: Er trägt dieselbe Rechnung, aber er
        # kappt bei 100 % und sagt dann, WARUM kein Wert kommt. Das `or 0`, das
        # hier stand, machte aus „nicht ermittelbar" eine glatte 0 % — dieselbe
        # Fake-0-Klasse wie in N-87.
        _eta = speicher_wirkungsgrad(
            gesamt_ladung, gesamt_entladung, None, langes_fenster_quelle="fenster_lang"
        )
        effizienz = _eta.prozent
        verlauf = gleitende_effizienz(monats_reihe)
        durchsatz = pruefe_speicher_durchsatz_konsistenz(gesamt_ladung, gesamt_entladung)
        if not durchsatz.konsistent:
            logger.warning(
                f"Speicher-Dashboard Anlage {anlage_id}, Speicher {speicher.id}: "
                f"{durchsatz}"
            )

        # Vollzyklen über den Layer-SoT — ENTLADUNG ÷ Kapazität (Kanon seit
        # 2026-07-28). Vorher stand hier die Ladung, während der HA-Sensor
        # schon die Entladung nahm: zwei Zahlen unter demselben Namen.
        params = speicher.parameter or {}
        # N127: BRUTTO-Kapazität über den SoT-Helper, ohne Default. Hier stand
        # `.get(…, 10)` — ein Speicher ohne gepflegte Kapazität bekam still
        # 10 kWh und daraus eine Zyklenzahl, die es nie gab. Ohne Kapazität
        # gibt es keine Zyklenzahl: `None` („unbekannt"), nicht 0 („nie
        # zyklisiert"). Bei gepflegter Kapazität bleibt der bisherige
        # 0-Ersatz für „keine Entladung" unverändert.
        kapazitaet = get_speicher_kapazitaet_kwh(speicher)
        arbitrage_faehig = params.get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"], PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"])
        vollzyklen = (
            (berechne_vollzyklen(gesamt_entladung, kapazitaet) or 0)
            if kapazitaet is not None else None
        )

        # Etappe C (#264): SoC-korrigierter η-IST pro Speicher.
        # aggregiere_speicher_ist als SoT-Helper statt Parallel-Summe.
        eta_ist = None
        if monatsdaten and periode_von is not None:
            try:
                # ⭐ **Seit S3b über den SoT-Helper** (22.09.2026) — er trägt die
                # N-140-Wache in sich: `aggregiere_speicher_ist` liefert `None`
                # im VÖLLIG NORMALEN Fall (weniger als `SPEICHER_IST_MIN_MONATE`
                # Monate Historie oder gar keine erfasste Entladung). Der
                # ungeprüfte Zugriff auf `.jahres_faktor` machte daraus einen
                # `AttributeError`, den der breite `except` unten als „η-IST
                # fehlgeschlagen" ins Log schrieb: eine frische Anlage erzeugte
                # bei jedem Abruf eine Warnung über einen Fehler, den es nicht
                # gab. Jetzt steht die Wache an **einer** Stelle statt an drei.
                # Identisches Verhalten: `eta_ist` bleibt `None`.
                eta_ist = await wirkungsgrad_ist_fuer_speicher(
                    db, anlage_id=anlage_id, speicher=speicher,
                    verbrauch_daten_je_monat=[md.verbrauch_daten or {} for md in monatsdaten],
                    von=periode_von, bis=periode_bis,
                )
            except Exception as e:
                logger.warning(
                    f"Speicher-Dashboard Anlage {anlage_id}, Speicher {speicher.id}: "
                    f"η-IST fehlgeschlagen: {type(e).__name__}: {e}"
                )

        # Ersparnis über den Layer-SoT (#358): Spread zwischen Netzbezug und
        # Einspeisung, aber NUR auf dem PV-Anteil der Entladung. BEIDE Preis-
        # Seiten aus derselben Monatsschleife oben — ein Ø-Bezugspreis gegen die
        # heutige Vergütung wäre ein Spread aus zwei Zeitpunkten (ADR-002/P8).
        #
        # Hier stand der Spread als Inline-Formel auf der GESAMTEN Entladung,
        # daneben ein zweiter Posten „Arbitrage-Gewinn" auf der Netzladung — der
        # Hub addiert beide in der Wirtschaftlichkeits-Aufstellung
        # (`komponentenAdapter.tsx`), also wurde netzgeladene Energie zweimal
        # gutgeschrieben: einmal mit dem PV-Spread (den sie nicht verdient, sie
        # hätte nie eingespeist werden können) und einmal mit ihrem echten
        # Arbitrage-Vorteil. Der Layer trennt beides sauber; die zwei Posten
        # unten sind seither disjunkt und summieren sich auf `ersparnis`.
        # ── Die Ladepreis-Kaskade des Speichers (SOLL Flex-Tarife, [A-2]) ──
        #
        # **Messung schlägt gepflegt** — Entscheid Gernot 17.09.2026, und zwar
        # umgekehrt zum Netzbezug: Dort ist der gepflegte Wert die *Abrechnung*
        # und damit die externe Wahrheit. **Ein Ladepreis steht auf keiner
        # Rechnung**; der gepflegte Wert ist entweder der übernommene Vorschlag
        # (also dieselbe Messung) oder eine Schätzung. Er bleibt als bewusste
        # Korrektur erhalten, verdrängt die slot-scharfe Messung aber nicht mehr.
        #
        # ⚠ Nur belastbare Quellen: `dyn-tarif` (gemessener Endpreis) und
        # `boersenpreis` (Stundenform bei ausdrücklich dynamischem Tarif). Die
        # Diagnose-Quellen (`kein-dyn-tarif`, `keine-netzladung`, …) tragen
        # keinen verwendbaren Preis — dort gilt der gepflegte Wert, sonst keiner.
        _gemessener_ladepreis = (
            eff_ladepreis.effektiver_ladepreis_cent
            if eff_ladepreis is not None
            and eff_ladepreis.quelle in ("dyn-tarif", "boersenpreis")
            else None
        )
        arbitrage_avg_preis = (arbitrage_preis_sum / arbitrage_count) if arbitrage_count > 0 else 0
        ladepreis_fuer_gewinn = (
            _gemessener_ladepreis if _gemessener_ladepreis is not None
            else (arbitrage_avg_preis if arbitrage_count > 0 else None)
        )
        # ── Die Nutzenseite (SOLL Flex-Tarife P-5, 17.09.2026) ──
        #
        # Was eine Entladung wert ist, ist der Bezug, den sie **in ihrer
        # Stunde** vermeidet. Bewertet wurde sie bis hierher mit dem
        # Lebensdauer-Ø des Bezugs — bei einem Flex-Tarif systematisch zu
        # niedrig, denn entladen wird abends, wenn der Strom teuer ist.
        #
        # ⭐ **Der Wert gilt BEIDE Anteile** (Entscheid Gernot, 17.09.2026):
        # PV-Anteil (Entladung gegen Einspeisevergütung) und Netz-Anteil
        # (Arbitrage) teilen sich dieselbe Nutzenseite. Nur den Netz-Anteil
        # umzustellen hieße, zwei Auflösungen in eine Kachel zu schreiben —
        # genau der Widerspruch, gegen den P-5 steht.
        #
        # Ohne Stundenpreise liefert der Helper `None`, und es bleibt beim
        # bisherigen Lebensdauer-Ø: Für Festpreis-Anlagen bewegt sich damit
        # keine Zahl (SOLL §10, Prüfstein 2).
        _entladewert = (
            eff_ladepreis.entladewert_cent if eff_ladepreis is not None else None
        )
        _sp = berechne_speicher_ersparnis(
            entladung_kwh=gesamt_entladung,
            bezug_preis_cent=(
                _entladewert if _entladewert is not None else eff_strompreis_cent
            ),
            einspeise_verg_cent=eff_einspeise_cent,
            ladung_netz_kwh=gesamt_arbitrage_kwh,
            # Nur ein ERMITTELTER η darf die Netz-/PV-Aufteilung steuern; ohne
            # ihn greift der dokumentierte Default (95 %). Vorher konnte hier
            # ein Wert über 100 % einlaufen und den Netz-Anteil aufblähen.
            **({"wirkungsgrad_prozent": effizienz} if effizienz else {}),
            # `is not None`, nicht `> 0` (P-8): Ein Ladepreis von 0 ct ist ein
            # Wert — und der Fall mit dem GRÖSSTEN Arbitrage-Gewinn.
            lade_preis_cent=ladepreis_fuer_gewinn,
        )
        ersparnis = _sp.ersparnis_euro
        arbitrage_gewinn = _sp.netz_anteil_euro

        zusammenfassung = {
            'gesamt_ladung_kwh': round(gesamt_ladung, 1),
            'gesamt_entladung_kwh': round(gesamt_entladung, 1),
            'effizienz_prozent': round(effizienz, 1) if effizienz is not None else None,
            'effizienz_quelle': _eta.quelle,
            'vollzyklen': round(vollzyklen, 1) if vollzyklen is not None else None,
            'zyklen_pro_monat': (
                (round(vollzyklen / len(monatsdaten), 1) if monatsdaten else 0)
                if vollzyklen is not None else None
            ),
            'kapazitaet_kwh': kapazitaet,
            # P4: die fehlende Kapazität sagt sich selbst, statt als 0 oder als
            # erfundene 10 durchzulaufen (N127). Das Frontend hängt daraus einen
            # Hinweis in das bestehende `hinweise`-Array des Speicher-Geräts.
            'kapazitaet_fehlt': kapazitaet is None,
            'ersparnis_euro': round(ersparnis, 2),
            # PV-Anteil und Arbitrage-Gewinn sind die beiden DISJUNKTEN Hälften
            # von `ersparnis_euro` (#358) — die Aufstellung im Hub addiert sie,
            # deshalb darf sich hier nichts überlappen.
            'pv_anteil_euro': round(_sp.pv_anteil_euro, 2),
            'anzahl_monate': len(monatsdaten),
            # Arbitrage-Daten
            'arbitrage_faehig': arbitrage_faehig,
            'arbitrage_kwh': round(gesamt_arbitrage_kwh, 1),
            'arbitrage_avg_preis_cent': round(arbitrage_avg_preis, 1) if arbitrage_avg_preis > 0 else None,
            'arbitrage_gewinn_euro': round(arbitrage_gewinn, 2),
            # Invariante: Σentladung ≤ Σladung — kumulativ unmöglich zu verletzen.
            'durchsatz_inkonsistent': not durchsatz.konsistent,
        }

        # Etappe C (#264): TEP-basierte KPIs fürs UI — effektiver Ladepreis
        # mit Quellen-Transparenz (C1/C4), SoC-korrigierter η-IST + Degradations-
        # Alarm (C3). Felder sind optional; das Frontend fällt sonst auf die
        # bestehenden Werte (arbitrage_avg_preis_cent, effizienz_prozent) zurück.
        if eff_ladepreis is not None:
            zusammenfassung['effektiver_ladepreis_cent'] = (
                round(eff_ladepreis.effektiver_ladepreis_cent, 2)
                if eff_ladepreis.effektiver_ladepreis_cent is not None else None
            )
            zusammenfassung['effektiver_ladepreis_quelle'] = eff_ladepreis.quelle
            if eff_ladepreis.quelle == "datenbasis-zu-duenn":
                zusammenfassung['ladepreis_abdeckung_prozent'] = round(
                    eff_ladepreis.abdeckung_prozent, 0
                )
        if eta_ist is not None:
            wirkungsgrad_param = params.get(
                PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"],
                PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"],
            )
            zusammenfassung['ist_wirkungsgrad_prozent'] = (
                round(eta_ist.wirkungsgrad_prozent, 1)
                if eta_ist.wirkungsgrad_prozent is not None else None
            )
            zusammenfassung['wirkungsgrad_quelle'] = eta_ist.quelle
            zusammenfassung['param_wirkungsgrad_prozent'] = round(wirkungsgrad_param, 1)
            if eta_ist.wirkungsgrad_prozent is not None:
                zusammenfassung['eta_degradation_alarm'] = ist_eta_degradation_alarm(
                    ist_wirkungsgrad_prozent=eta_ist.wirkungsgrad_prozent,
                    param_wirkungsgrad_prozent=wirkungsgrad_param,
                )

        dashboards.append(SpeicherDashboardResponse(
            investition=speicher,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
            effizienz_verlauf=[asdict(m) for m in verlauf],
        ))

    return dashboards
