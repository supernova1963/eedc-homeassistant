"""
Cockpit Übersicht — Aggregierte KPI-Übersicht für eine Anlage.
"""

from collections import Counter
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import not_found
from backend.core.investition_kennwerte import get_erzeuger_kwp, get_speicher_kapazitaet_kwh
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    FinanzMonatsZeile,
    berechne_dienstliche_ladekosten,
    berechne_finanz_aggregat,
    berechne_spez_ertrag_annualisiert,
    berechne_verbrauchs_kennzahlen,
    berechne_netzbezug_kosten,
    eauto_effizienz_100km,
    erzeugung_hinter_zaehler_kwh,
    monatsgewichte_aus_pvgis,
    vollzyklen as berechne_vollzyklen,
)
from backend.core.berechnungen import relevante_kosten_aus_investitionen
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.core.calculations import berechne_co2_bilanz
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten
from backend.core.investition_parameter import ist_dienstlich
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis_periode,
    get_emob_heimladung_canonical,
)

router = APIRouter()


class CockpitUebersichtResponse(BaseModel):
    """Aggregierte Cockpit-Übersicht."""

    # Energie-Bilanz (kWh)
    pv_erzeugung_kwh: float
    gesamtverbrauch_kwh: float
    netzbezug_kwh: float
    einspeisung_kwh: float
    direktverbrauch_kwh: float
    eigenverbrauch_kwh: float

    # Quoten (%)
    autarkie_prozent: float
    eigenverbrauch_quote_prozent: float
    direktverbrauch_quote_prozent: float
    spezifischer_ertrag_kwh_kwp: Optional[float]
    anlagenleistung_kwp: float

    # Speicher aggregiert
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float
    speicher_effizienz_prozent: Optional[float]
    speicher_vollzyklen: Optional[float]
    speicher_kapazitaet_kwh: float
    hat_speicher: bool

    # Wärmepumpe aggregiert
    wp_waerme_kwh: float
    wp_strom_kwh: float
    wp_heizung_kwh: float
    wp_warmwasser_kwh: float
    wp_cop: Optional[float]
    wp_ersparnis_euro: float
    hat_waermepumpe: bool

    # E-Mobilität aggregiert (E-Auto + Wallbox)
    emob_km: float
    emob_ladung_kwh: float
    emob_pv_anteil_prozent: Optional[float]
    emob_ersparnis_euro: float
    # Ø Verbrauch (kWh/100 km) zentral via core/berechnungen/emob.py (gemessen > Ladung).
    emob_verbrauch_100km: Optional[float] = None
    emob_verbrauch_quelle: str = "keine"
    hat_emobilitaet: bool

    # Balkonkraftwerk aggregiert
    bkw_erzeugung_kwh: float
    bkw_eigenverbrauch_kwh: float
    hat_balkonkraftwerk: bool

    # Sonstiges aggregiert (Pool, Sauna, Klima — wenn nicht als WP/Luft-Luft
    # geführt, etc.). Erzeuger und Verbraucher getrennt, weil pro Investition
    # nur eine Seite aktiv ist (siehe inv.parameter.kategorie).
    sonstiges_erzeugung_kwh: float
    sonstiges_verbrauch_kwh: float
    hat_sonstiges: bool

    # Finanzen (Euro)
    einspeise_erloes_euro: float
    # §51 EEG: nicht vergüteter Erlös (Einspeisung in Negativpreis-Stunden).
    # `None` = keine Tages-Aggregate vorhanden (Anwender ohne Strompreis-
    # Sensor / Börsenpreis-Mitschrift); `0.0` = vorhanden, aber keine
    # Negativpreis-Einspeisung im Zeitraum.
    einspeise_neg_preis_kwh: Optional[float] = None
    nicht_vergueteter_erloes_euro: Optional[float] = None
    ev_ersparnis_euro: float
    netzbezug_kosten_euro: float = 0
    ust_eigenverbrauch_euro: Optional[float] = None
    netto_ertrag_euro: float
    bkw_ersparnis_euro: float = 0
    sonstige_netto_euro: float = 0
    jahres_rendite_prozent: Optional[float]
    investition_gesamt_euro: float
    investition_vollkosten_euro: float
    investition_mehrkosten_euro: float
    steuerliche_behandlung: Optional[str] = None

    # Umwelt (kg CO2)
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float

    # Meta
    anzahl_monate: int
    zeitraum_von: Optional[str]
    zeitraum_bis: Optional[str]


@router.get("/uebersicht/{anlage_id}", response_model=CockpitUebersichtResponse)
async def get_cockpit_uebersicht(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Filter nach Jahr (leer = alle)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Aggregierte Cockpit-Übersicht für eine Anlage.

    Berechnet alle KPIs über den gesamten Zeitraum oder ein einzelnes Jahr.

    Datenquellen:
    - Monatsdaten: NUR für Anlagen-Energiebilanz (einspeisung, netzbezug)
    - InvestitionMonatsdaten: ALLE Komponenten-Details (Speicher, WP, E-Auto, PV-Strings, etc.)
    """
    # Anlage laden
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # Investitionen laden — KEIN aktiv-Filter (Issue #123): historische KPIs
    # dürfen später deaktivierte/stillgelegte Komponenten nicht rückwirkend ausblenden.
    inv_query = select(Investition).where(
        Investition.anlage_id == anlage_id,
    )
    inv_result = await db.execute(inv_query)
    investitionen = inv_result.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    # Tarife laden (allgemein + Spezialtarife für WP/Wallbox).
    # ACHTUNG: `tarife` ist der HEUTE gültige Satz und damit nur für die
    # Anzeige des aktuellen Tarifs und die Komponenten-Kennwerte gedacht.
    # Alles, was über MONATE summiert, holt sich seinen Tarif aus `fakt.tarif`
    # bzw. über `baue_finanz_zeile` — beide mit dem Monats-Stichtag (ADR-002/P8).
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    wp_tarif = tarife.get("waermepumpe")
    wallbox_tarif = tarife.get("wallbox")

    netzbezug_preis_cent = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif else NETZBEZUG_DEFAULT_CENT
    einspeise_verguetung_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif else EINSPEISEVERGUETUNG_DEFAULT_CENT
    wp_preis_cent = wp_tarif.netzbezug_arbeitspreis_cent_kwh if wp_tarif else netzbezug_preis_cent
    wallbox_preis_cent = wallbox_tarif.netzbezug_arbeitspreis_cent_kwh if wallbox_tarif else netzbezug_preis_cent

    # Monats-Tarif-Auflösung (ein Cache für den ganzen Request) — geteilt mit
    # `lade_monats_fakten` und `baue_finanz_zeile`, damit jeder Stichtag genau
    # einmal aus der DB kommt.
    _tarif_cache: dict[date, dict] = {}

    # =====================================================================
    # MONATSZEILE AUS DEN MONATS-FAKTEN (ADR-002/P10)
    # =====================================================================
    # Bis 2026-07-31 hat dieser Endpoint die IMD-Zeilen selbst geladen und
    # typweise zu Monatswerten gefaltet — knapp 160 Zeilen, die es in
    # `aussichten.py`, `ha_export.py`, `jahresbericht.py` und
    # `investitionen/crud.py` in leicht abweichenden Fassungen noch einmal gab.
    # Die Rechnung hier war korrekt (Befund F-5 traf die anderen Sichten, nicht
    # diese) — genau das ist der Grund für den Umbau: **eine selbst faltende
    # Sicht ist die nächste Drift-Quelle**, auch wenn sie heute stimmt
    # (`docs/KONZEPT-MONATS-FAKTEN.md` §11).
    #
    # Die Schicht wendet Zeitfilter (#153/#155/#236: aktiv · Anschaffung ·
    # Stilllegung), Dienstwagen-Filter (#308) und die P7-PV-Auflösung genau
    # einmal an. Der Jahres-Filter läuft jetzt über `von`/`bis` — vorher filterte
    # er die IMD- und die Monatsdaten-Query, **nicht** aber `lade_pv_je_monat`:
    # bei `?jahr=` stand die PV ALLER Jahre in der Erzeugungs-Kachel, im
    # spezifischen Ertrag und in der Energiebilanz (kein Frontend-Aufrufer
    # übergibt heute ein Jahr, deshalb hat es niemand gesehen — s. Übergabe N-10).
    _fenster = ((jahr, 1), (jahr, 12)) if jahr else (None, None)
    fakten = await lade_monats_fakten(
        db, anlage_id, von=_fenster[0], bis=_fenster[1], tarif_cache=_tarif_cache
    )

    speicher_ladung = sum(f.speicher.ladung_kwh for f in fakten)
    speicher_entladung = sum(f.speicher.entladung_kwh for f in fakten)
    wp_waerme = sum(f.wp.waerme_kwh for f in fakten)
    wp_strom = sum(f.wp.strom_kwh for f in fakten)
    wp_heizung = sum(f.wp.heizung_kwh for f in fakten)
    wp_warmwasser = sum(f.wp.warmwasser_kwh for f in fakten)
    bkw_erzeugung = sum(f.bkw.erzeugung_kwh for f in fakten)
    bkw_eigenverbrauch = sum(f.bkw.eigenverbrauch_gemessen_kwh for f in fakten)
    sonstiges_erzeugung = sum(f.sonstiges.erzeugung_kwh for f in fakten)
    sonstiges_verbrauch = sum(f.sonstiges.verbrauch_kwh for f in fakten)
    sonstige_ertraege_gesamt = sum(f.sonstiges.ertraege_euro for f in fakten)
    sonstige_ausgaben_gesamt = sum(f.sonstiges.ausgaben_euro for f in fakten)
    v2h_entladung = sum(f.emob.v2h_entladung_kwh for f in fakten)

    # E-Mobilitäts-Pool: EINE Quelle liefert die konsistente Heimladungs-
    # Trias (pv + netz == ladung). Früher feldweises max() über pv/netz —
    # das konnte pv aus der einen, netz aus der anderen Quelle nehmen und
    # PV-Anteil > 100 % erzeugen (#262 junky84). Externe Lade-Kosten (#260)
    # kommen paarweise aus der Quelle mit den höheren Extern-Kosten.
    #
    # **Bewusst EINMAL global gepoolt, nicht monatsweise summiert** (Falle 3 der
    # S1-Übergabe): die Quellenwahl E-Auto-IMD vs. Wallbox-IMD ist in der Schicht
    # eine Monats-Entscheidung, hier eine Zeitraum-Entscheidung — beides
    # vertretbar, aber es sind zwei verschiedene Zahlen. Die Schicht reicht
    # deshalb die bereits dienstwagen- und laufzeitgefilterten Rohdicts durch,
    # damit dieselbe Poolung über denselben SoT laufen kann.
    emob_pool = get_emob_heimladung_canonical(
        eauto_imd_data=[d for f in fakten for d in f.emob.eauto_ladedaten],
        wallbox_imd_data=[d for f in fakten for d in f.emob.wallbox_ladedaten],
    )
    emob_ladung = emob_pool.ladung_kwh
    emob_pv_ladung = emob_pool.pv_kwh
    emob_netz_ladung = emob_pool.netz_kwh
    emob_km = sum(f.emob.km for f in fakten)
    # Ø Verbrauch (kWh/100 km) via zentralem Helper — gemessener Fahrverbrauch hat
    # Vorrang, sonst Ladungs-Näherung; konsistent zu E-Auto-Dashboard + Komponenten.
    emob_eff = eauto_effizienz_100km(
        sum(f.emob.fahrverbrauch_kwh for f in fakten), emob_ladung, emob_km
    )
    emob_extern_euro_total = emob_pool.extern_euro

    # G20-2: km PRO FAHRZEUG (inv.id) und pro Monat, damit das eMob-Ersparnis-
    # Aggregat = Σ der Per-Fahrzeug-Läufe (jeder mit dem Verbrauchs-Parameter
    # SEINES Fahrzeugs) ist statt EIN Lauf mit dem Referenz-Parameter des ersten
    # Autos ([[feedback_aggregator_symmetrie]]).
    eauto_km_by_inv: dict[int, float] = {}
    eauto_km_pro_monat_by_inv: dict[int, dict[tuple[int, int], float]] = {}
    for f in fakten:
        for _inv_id, _km in f.emob.km_je_fahrzeug.items():
            eauto_km_by_inv[_inv_id] = eauto_km_by_inv.get(_inv_id, 0.0) + _km
            _pm = eauto_km_pro_monat_by_inv.setdefault(_inv_id, {})
            _pm[f.schluessel] = _pm.get(f.schluessel, 0.0) + _km

    # Dienstliche Ladekosten über den Layer-SoT (ADR-001) — dieselbe Formel wie
    # in `aussichten.get_finanz_prognose` und im HA-Export, die sie bis
    # 2026-07-31 alle drei verschieden (bzw. gar nicht) rechneten.
    # Beide Preise stammen aus dem Tarif DES MONATS (P8): der Netzanteil aus dem
    # effektiven Wallbox-Preis (Flex-Ø vor Wallbox-Tarif vor Anlagentarif), der
    # PV-Anteil aus dem Netzbezugspreis. Letzteres nimmt die EV-Gutschrift
    # zurück, die `berechne_finanz_aggregat` unten für dieselben kWh
    # gutschreibt — der frühere Abzug zur Einspeisevergütung tat das nicht und
    # ließ dem Dienstwagen netto +22 ct je verschenkter kWh (N-18).
    # Die ENERGIEBILANZ oben bleibt davon unberührt: energetisch ist die Ladung
    # Eigenverbrauch hinter dem Zähler.
    dienstlich_ladekosten_euro = berechne_dienstliche_ladekosten(
        DienstlicheLadungZeile(
            ladung_pv_kwh=f.emob.dienstlich_ladung_pv_kwh,
            ladung_netz_kwh=f.emob.dienstlich_ladung_netz_kwh,
            netzbezug_preis_cent=f.tarif.netzbezug_preis_cent,
            wallbox_preis_cent=f.tarif.wallbox_preis_effektiv_cent,
        )
        for f in fakten
    ).gesamt_euro
    sonstige_ausgaben_gesamt += dienstlich_ladekosten_euro

    # Anschaffungsdatum-Grenze: Energiebilanz + Erträge nur über Monate, in denen
    # mindestens ein Erzeuger hinter dem Zähler aktiv war (PV-Module ∪
    # Balkonkraftwerke ∪ sonstige Erzeuger wie BHKW). Konsequente Anwendung des
    # einzigen Manipulationshebels „Anschaffungsdatum" (Gernot 2026-06-07,
    # [[feedback_anschaffungsdatum_grenze]]) — symmetrisch zum kumulierten
    # Amortisations-Pfad in aussichten.get_finanz_prognose und zur covered_months-
    # Logik unten ([[feedback_aggregator_symmetrie]]). Der frühere lokale Nachbau
    # `_pv_aktiv_im_monat` ist weg; `meta.erzeuger_aktiv` ist dieselbe Regel an
    # der einen Stelle (ohne registrierten Erzeuger greift sie nicht).
    md_pv = [f for f in fakten if f.meta.hat_zaehlerzeile and f.meta.erzeuger_aktiv]

    einspeisung = sum(f.zaehler.einspeisung_kwh for f in md_pv)
    netzbezug = sum(f.zaehler.netzbezug_kwh for f in md_pv)

    # PV je Monat über den Read-time-SoT der Schicht: gemessene Modulwerte +
    # Lücken aus dem Anlagen-Aggregat, plus das BKW (das Aggregat deckt nur
    # `pv-module` ab). Ersetzt das globale Entweder-oder
    # (`pv_erzeugung_inv if pv_erzeugung_inv > 0 else pv_erzeugung_md`), das eine
    # Anlage mit gemischter Historie um ihre Aggregat-Monate brachte.
    pv_erzeugung = sum(f.erzeugung.pv_kwh for f in fakten)
    # Monate, in denen überhaupt PV aufgelöst wurde — gemessen ODER über das
    # Aggregat gefüllt. Ein BKW-Monat ohne erfasste Erzeugung zählt hier nicht
    # mit: er trägt 0 zu `pv_erzeugung` bei und würde als Nenner-Monat den
    # spezifischen Ertrag verzerren.
    pv_monate = {
        f.schluessel for f in fakten
        if f.erzeugung.pv_je_modul or f.bkw.erzeugung_kwh > 0
    }

    # Netzpunkt-Bilanz: sonstige Erzeuger (z. B. BHKW) speisen hinter denselben
    # Zähler → ihre Erzeugung gehört in die EV/Autarkie-Ableitung, sonst drückt
    # der gemessene Einspeise-Zähler die PV-Bilanz still zu niedrig (Konzept
    # Sonstiger Erzeuger). `pv_erzeugung` bleibt rein für PV-Kennzahlen unten
    # (spez. Ertrag/Performance-Ratio/SOLL-IST) — Falle 1 der S1-Übergabe.
    erzeugung_bilanz = erzeugung_hinter_zaehler_kwh(pv_erzeugung, sonstiges_erzeugung)

    # Kanonische Verbrauchs-Kennzahlen über den SoT-Helper (ADR-001) statt der
    # früher hier duplizierten Inline-Formel — inkl. V2H (E-Auto → Haus) als
    # Eigenverbrauch, einheitlich mit HA-Export/Aussichten/Jahresbericht.
    _kz = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=erzeugung_bilanz,
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
        v2h_entladung_kwh=v2h_entladung,
    )
    direktverbrauch = _kz.direktverbrauch_kwh
    eigenverbrauch = _kz.eigenverbrauch_kwh
    gesamtverbrauch = _kz.gesamtverbrauch_kwh
    autarkie = _kz.autarkie_prozent
    ev_quote = _kz.eigenverbrauchsquote_prozent
    dv_quote = _kz.direktverbrauchsquote_prozent

    # Anlagenleistung aus Investitionen (nur aktive — stillgelegte nicht mitzählen)
    today = date.today()
    anlagenleistung_kwp = 0.0
    for inv in investitionen:
        if not inv.ist_aktiv_an(today):
            continue
        # kWp über den SoT-Dispatcher (ADR-002/P3-a): er kennt für PV-Module
        # Spalte → `parameter` (#229) und für BKW zusätzlich
        # `leistung_wp × anzahl`. Die frühere Handschrift hier las bei
        # `leistung_wp: null` `None * anzahl` und warf einen TypeError — ein
        # 500er in der Cockpit-Übersicht (N-H).
        if inv.typ in ("pv-module", "balkonkraftwerk"):
            anlagenleistung_kwp += get_erzeuger_kwp(inv)

    if anlagenleistung_kwp == 0 and anlage.leistung_kwp:
        anlagenleistung_kwp = anlage.leistung_kwp

    # Spezifischer Ertrag periodengenau & jahresverlauf-gewichtet (#YTD-spez-ertrag):
    # Roh-Division pv_erzeugung / kWp ergibt im laufenden Jahr einen viel zu
    # niedrigen Wert, weil der Nenner für 12 Monate ausgelegt ist. Naive
    # Proration (Monate/12) ignoriert den Jahresverlauf — Jan–Mai sind ~30%
    # des Jahresertrags, nicht 42%. Daher Periodenanteil über die
    # PVGIS-Monatsverteilung gewichten; Fallback auf typische 52°N-Verteilung
    # bzw. Gleichverteilung wenn keine PVGIS-Prognose vorliegt.
    #
    # WICHTIG (Folge-Bug "alle Jahre"): covered_months darf NUR Monate
    # enthalten, in denen tatsächlich eine PV-/BKW-Investition aktiv war.
    # Sonst rutschen WP-/Speicher-/Zähler-Monate aus der Zeit vor PV-Inbetrieb-
    # nahme rein, periode_anteil wird zu groß und spez_ertrag zu klein
    # (Symptom: ~300 kWh/kWp bei "alle Jahre").
    # Aus derselben Quelle wie `pv_erzeugung` oben: jeder Monat mit aufgelöster
    # PV zählt — gemessen ODER über das Aggregat gefüllt. Der frühere Aufbau
    # (rohe IMD-Zeilen, dann ein Fallback „nur wenn GAR keine IMD existieren")
    # trug denselben Fehler wie die Erzeugungssumme: bei gemischter Historie
    # fehlten die Aggregat-Monate, `periode_anteil` wurde zu klein und der
    # spezifische Ertrag entsprechend zu hoch.
    covered_months: set[tuple[int, int]] = set(pv_monate)

    # Annualisierung über den SoT-Helper (per-Monat-aktives kWp + saisonale
    # Gewichtung) — deckungsgleich mit dem HA-Export-Sensor
    # ([[feedback_aggregator_symmetrie]], Rainer-PN 2026-06-11).
    monatsgewichte: Optional[dict[int, float]] = None
    if covered_months and anlagenleistung_kwp > 0:
        pvgis = await lade_aktive_prognose(db, anlage_id)
        monatsgewichte = monatsgewichte_aus_pvgis(
            pvgis.monatswerte if pvgis else None
        ) or None

    spez_ertrag = berechne_spez_ertrag_annualisiert(
        pv_erzeugung_kwh=pv_erzeugung,
        covered_months=covered_months if anlagenleistung_kwp > 0 else set(),
        investitionen=investitionen,
        fallback_kwp=anlagenleistung_kwp,
        monatsgewichte=monatsgewichte,
    )

    # Komponenten-Flags und Berechnungen (nur aktive Investitionen)
    speicher_invs = [i for i in investitionen if i.typ == "speicher" and i.ist_aktiv_an(today)]
    hat_speicher = len(speicher_invs) > 0
    speicher_kapazitaet = sum(
        get_speicher_kapazitaet_kwh(i) or 0 for i in speicher_invs
    )
    speicher_effizienz = (speicher_entladung / speicher_ladung * 100) if speicher_ladung > 0 else None
    # Vollzyklen = ENTLADUNG ÷ Kapazität über den Layer-SoT. Hier stand bis zum
    # 04.08. die LADUNG — die eine Route, die der Kanon-Sweep vom 2026-07-28
    # (Entscheid Gernot, Rainer-PN 89768) übersehen hat. Die beiden Zahlen
    # liegen genau um den Speicher-Wirkungsgrad auseinander; die Begründung
    # („ein Vollzyklus ist die einmal entnommene Kapazität") steht im Docstring
    # von `vollzyklen`. Der Wert hatte hier keinen Client-Leser — mit dem
    # Speicher-Block in Cockpit → Jahr (#358 Phase 1) bekommt er einen.
    speicher_vollzyklen = berechne_vollzyklen(speicher_entladung, speicher_kapazitaet)

    wp_invs = [i for i in investitionen if i.typ == "waermepumpe" and i.ist_aktiv_an(today)]
    hat_waermepumpe = len(wp_invs) > 0
    # JAZ/COP nur wenn beide Seiten gemessen sind. Bei Split-Klimaanlagen
    # (wp_art="luft_luft") ist Wärmemengenzähler typischerweise nicht
    # vorhanden → wp_waerme=0 obwohl Stromverbrauch läuft. Heute lieferte
    # die Formel dann 0.0 (irreführende JAZ), jetzt None ("—" im UI).
    wp_cop = (wp_waerme / wp_strom) if wp_strom > 0 and wp_waerme > 0 else None
    # Multi-WP: erste WP als Parameter-Referenz (Wirkungsgrad/Gas-Default).
    # Drift-Audit Domäne A1 / Issue #178: vorher 10ct hartcodiert + ignorierte
    # User-Param `alter_preis_cent_kwh`.
    wp_ref_parameter = wp_invs[0].parameter if wp_invs else None
    wp_ersparnis_result = berechne_wp_ersparnis(
        wp_waerme_kwh=wp_waerme,
        wp_strom_kwh=wp_strom,
        wp_strompreis_cent=wp_preis_cent,
        wp_parameter=wp_ref_parameter,
    )
    wp_ersparnis = wp_ersparnis_result.ersparnis_euro

    emob_invs = [
        i for i in investitionen
        if i.typ in ("e-auto", "wallbox")
        and i.ist_aktiv_an(today)
        and not ist_dienstlich(i)
    ]
    hat_emobilitaet = len(emob_invs) > 0
    emob_pv_anteil = (emob_pv_ladung / emob_ladung * 100) if emob_ladung > 0 else None
    # #260: per-Monat-korrekter Benzinpreis (EU-OB-Monatspreis aus Monatsdaten),
    # km-gewichtet — derselbe Pfad wie E-Auto-Dashboard + Monatsberichte. Vorher
    # rief die Übersicht den Skalar-Helper mit dem statischen Inv-Parameter-Preis
    # (1,80 €-Default) auf → Drift gegen die Monatsberichte (NongJoWo).
    benzinpreis_lookup = {
        f.schluessel: f.tarif.kraftstoffpreis_euro
        for f in fakten
        if f.meta.hat_zaehlerzeile
    }
    # G20-2 (Gernot 2026-07-20): eMob-Ersparnis = Σ der Per-Fahrzeug-Läufe (jeder
    # mit dem Verbrauchs-Parameter SEINES Fahrzeugs), statt EIN Lauf über die
    # Gesamt-km mit dem Referenz-Parameter des ersten E-Autos (der bei
    # unterschiedlichem Verbrauch je Fahrzeug falsch rechnete). Die gepoolte
    # Heim-Netzladung + externen Kosten werden km-anteilig auf die Fahrzeuge
    # verteilt (Pool bleibt EINE Quelle). Bei genau EINEM E-Auto ist der 100 %-
    # Anteil == der frühere Einmal-Lauf → bitgleich. [[feedback_aggregator_symmetrie]]
    total_eauto_km = sum(eauto_km_by_inv.values())
    emob_ersparnis = 0.0
    benzin_verbrauch = 0.0
    if total_eauto_km > 0:
        for _inv_id, _km_total in eauto_km_by_inv.items():
            if _km_total <= 0:
                continue
            _share = _km_total / total_eauto_km
            _car_result = berechne_eauto_ersparnis_periode(
                km_pro_monat=[(j, mo, km) for (j, mo), km in eauto_km_pro_monat_by_inv[_inv_id].items()],
                ladung_netz_kwh_gesamt=emob_netz_ladung * _share,
                ladung_extern_euro_gesamt=emob_extern_euro_total * _share,
                wallbox_strompreis_cent=wallbox_preis_cent,
                eauto_parameter=getattr(inv_by_id.get(_inv_id), "parameter", None),
                monats_benzinpreis_lookup=benzinpreis_lookup,
            )
            emob_ersparnis += _car_result.ersparnis_euro
            benzin_verbrauch += (_km_total / 100) * _car_result.verwendeter_verbrauch_l_100km
    emob_ersparnis = round(emob_ersparnis, 2)

    bkw_invs = [i for i in investitionen if i.typ == "balkonkraftwerk" and i.ist_aktiv_an(today)]
    hat_balkonkraftwerk = len(bkw_invs) > 0

    sonstiges_invs = [i for i in investitionen if i.typ == "sonstiges" and i.ist_aktiv_an(today)]
    hat_sonstiges = len(sonstiges_invs) > 0

    # Finanzen — die Zeile entsteht aus dem Monats-Fakt (`finanz_zeile_eingabe`),
    # nicht mehr aus site-eigenen Maps. Der Tarif je Monat kommt aus demselben
    # `_tarif_cache`, den auch die Schicht benutzt.
    netzbezug_kosten = 0.0
    # #326: Finanz-Aggregation (Einspeise-Erlös §51 + EV-/BKW-Ersparnis) über den
    # SoT-Helper `berechne_finanz_aggregat` — per-Monat mit dem Monats-Flexpreis
    # (Σ EV_m × p_m), deckungsgleich mit Jahresbericht-PDF, HA-Export und
    # Auswertungen→Finanzen. Kein netzbezug-gewichteter Ø-Preis mehr.
    finanz_zeilen: list[FinanzMonatsZeile] = []

    # PV-Window-gefiltert (md_pv): Einspeise-Erlös, Netzbezugskosten und die
    # per-Monat-EV-/BKW-Ersparnis zählen nur Monate mit aktiver PV — wie die
    # Energiebilanz oben und der Amortisations-Pfad in aussichten.
    for f in md_pv:
        # Netzbezugskosten: derselbe effektive Preis wie in der Finanz-Zeile
        # (Flex-Ø vor Monats-Arbeitspreis, P8) plus der Grundpreis des Monats.
        netzbezug_kosten += berechne_netzbezug_kosten(
            f.zaehler.netzbezug_kwh,
            f.tarif.netzbezug_preis_cent,
            f.tarif.grundpreis_euro_monat,
        )
        # #326: FinanzMonatsZeile über den gemeinsamen Builder (einzige erlaubte
        # Konstruktions-Stelle, Wächter).
        finanz_zeilen.append(await baue_finanz_zeile(
            db, anlage_id, finanz_zeile_eingabe(f), tarif_cache=_tarif_cache
        ))

    # §51 EEG: nicht vergüteter Erlös + zugehörige kWh kommen aus dem Aggregat;
    # `hat_neg_preis_daten` bleibt False, wenn KEIN Monat Tages-Aggregate hat,
    # und signalisiert dem Frontend „keine Strompreis-Mitschrift gepflegt".
    _finanz = berechne_finanz_aggregat(finanz_zeilen)
    einspeise_erloes = _finanz.einspeise_erloes_euro
    # #326: per-Monat summiert (Σ EV_m × flexpreis_m) statt Gesamt-EV × Ø-Preis —
    # deckungsgleich mit Auswertungen→Finanzen.
    ev_ersparnis = _finanz.ev_ersparnis_euro
    nicht_vergueteter_erloes_sum = _finanz.nicht_vergueteter_erloes_euro
    nicht_verguetete_kwh_sum = _finanz.nicht_verguetete_kwh
    hat_neg_preis_daten = _finanz.hat_neg_preis_daten
    # Netto-Kanon (ADR-002/P9): `pv_erzeugung_kwh` der Finanz-Zeile ist
    # „PV-Module + BKW" — der daraus abgeleitete Eigenverbrauch deckt den
    # BKW-Anteil also mit ab. `_finanz.bkw_ersparnis_euro` trägt deshalb NUR
    # noch die BKW-Monate OHNE erfasste Erzeugung (`bkw_finanz_beitrag`, oben);
    # für alle anderen ist er 0 und die Addition hier folgenlos. Den Term ganz
    # wegzulassen (Stand 2026-07-31) ließ genau diese Anlagen ihre Ersparnis
    # verlieren.
    netto_ertrag = einspeise_erloes + ev_ersparnis + _finanz.bkw_ersparnis_euro

    investition_vollkosten = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    # Zugleich die kanonische USt-Bemessungsgrundlage (N-129) — die Formel stand
    # hier als Inline-Kopie, jetzt liegt sie im Layer.
    investition_mehrkosten = relevante_kosten_aus_investitionen(investitionen)

    # N-137/N-134: Hier stand bis 04.08. eine dritte Summe — PV-System voll +
    # WP-/eAuto-Mehrkosten aus `parameter["alternativ_kosten_euro"]` + Sonstiges
    # voll. Dieser Parameter-Schlüssel hat baumweit KEINEN Schreiber; gepflegt
    # wird die Spalte `anschaffungskosten_alternativ`, die der Daten-Checker mit
    # WARNING einfordert. Die Summe rechnete also mit Festannahmen (8.000 /
    # 35.000 €) an genau dem Feld vorbei, nach dem eedc fragt — und ein Fallback
    # darunter setzte bei 0 auf die VOLLkosten, also auf eine vierte Lesart.
    # Wortgleich stand sie ein zweites Mal in `aussichten.py`.
    #
    # Seit dem Entscheid zu N-137 gibt es EINE Definition relevanter Kosten
    # (Mehrkosten, Layer-SoT). `investition_gesamt_euro` bleibt als Feld
    # erhalten — es ist ausgeliefert und typisiert (`api/cockpit.ts`) —, trägt
    # aber denselben Wert wie `investition_mehrkosten_euro`. Der Fallback
    # entfällt: sind die relevanten Kosten 0, gibt es nichts zu amortisieren,
    # und der ROI-Fortschritt sagt das (None), statt gegen die Vollkosten zu
    # rechnen.
    investition_gesamt = investition_mehrkosten

    betriebskosten_ges = sum(i.betriebskosten_jahr or 0 for i in investitionen)

    steuerliche_beh = getattr(anlage, 'steuerliche_behandlung', None) or 'keine_ust'
    # N-129 + N-130: Bis 04.08. bekam die USt hier `investition_gesamt` — die
    # ad-hoc zusammengesetzte Summe darüber, die als einzige Sicht im Baum
    # NICHT `anschaffungskosten_alternativ` las, sondern die Parameter-Defaults
    # 35.000/8.000 €. Und sie bekam die PV des ganzen gewählten Zeitraums als
    # „Jahres-Erzeugung": bei „alle Jahre" stand eine mehrjährige Menge im
    # Nenner gegen eine Ein-Jahres-AfA ⇒ die USt fiel um den Faktor der
    # Jahresanzahl zu niedrig aus (Demo-Bestand: 646 € statt 2.447 €).
    #
    # Je Kalenderjahr dieselben Eingänge wie die Perioden-Kennzahlen oben:
    # Zählerwerte aus `md_pv`, Mengen aus `fakten`.
    monate_je_jahr = Counter(f.jahr for f in fakten)
    ust_jahresanteile: list[UstJahresanteil] = []
    for _jahr in sorted(monate_je_jahr):
        _f_jahr = [f for f in fakten if f.jahr == _jahr]
        _md_jahr = [f for f in md_pv if f.jahr == _jahr]
        _pv_jahr = sum(f.erzeugung.pv_kwh for f in _f_jahr)
        _kz_jahr = berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=erzeugung_hinter_zaehler_kwh(
                _pv_jahr, sum(f.sonstiges.erzeugung_kwh for f in _f_jahr)
            ),
            einspeisung_kwh=sum(f.zaehler.einspeisung_kwh for f in _md_jahr),
            netzbezug_kwh=sum(f.zaehler.netzbezug_kwh for f in _md_jahr),
            speicher_ladung_kwh=sum(f.speicher.ladung_kwh for f in _f_jahr),
            speicher_entladung_kwh=sum(f.speicher.entladung_kwh for f in _f_jahr),
            v2h_entladung_kwh=sum(f.emob.v2h_entladung_kwh for f in _f_jahr),
        )
        ust_jahresanteile.append(UstJahresanteil(
            jahr=_jahr,
            eigenverbrauch_kwh=_kz_jahr.eigenverbrauch_kwh,
            pv_kwh=_pv_jahr,
            monate=monate_je_jahr[_jahr],
        ))
    ust_eigenverbrauch = ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=ust_jahresanteile,
        bemessungsgrundlage_euro=investition_mehrkosten,
        betriebskosten_jahr_euro=betriebskosten_ges,
    )
    netto_ertrag -= ust_eigenverbrauch

    # #326: BKW-Ersparnis ebenfalls per-Monat (Σ BKW-EV_m × flexpreis_m).
    bkw_ersparnis = _finanz.bkw_ersparnis_euro
    sonstige_netto = sonstige_ertraege_gesamt - sonstige_ausgaben_gesamt
    # #326 (rilmor-mhrs): Die manuell gepflegten „Sonstige Erträge & Ausgaben"
    # gehören in den ANGEZEIGTEN Netto-Ertrag — exakt wie Auswertungen→Finanzen
    # (Einspeiseerlös + EV-Ersparnis + Sonstige-Erträge − Sonstige-Ausgaben).
    # Bisher floss sonstige_netto nur in kumulative_ersparnis/ROI ein, nicht in
    # die Netto-Ertrag-Kachel → das Cockpit zeigte eine andere Summe als die
    # Auswertungen. Aufschlagen NACH dem USt-Abzug (USt betrifft nur den
    # Eigenverbrauch, nicht die Finanzpositionen).
    netto_ertrag += sonstige_netto

    # CO2-Bilanz (DI-2: kanonischer Helper — dieselbe Bilanz wie der HA-Export)
    _co2 = berechne_co2_bilanz(
        eigenverbrauch_kwh=eigenverbrauch,
        wp_waerme_kwh=wp_waerme,
        wp_strom_kwh=wp_strom,
        emob_km=emob_km,
        emob_netz_ladung_kwh=emob_netz_ladung,
        benzin_verbrauch_liter=benzin_verbrauch,
    )
    co2_pv = _co2.co2_pv_kg
    co2_wp = _co2.co2_wp_kg
    co2_emob = _co2.co2_emob_kg
    co2_gesamt = _co2.co2_gesamt_kg

    # Zeitraum — jeder Monat mit einer Spur: Zählerzeile, sichtbare IMD-Zeile
    # oder aufgelöste PV. Genau das ist die Kandidaten-Menge der Schicht.
    zeitraum_von = None
    zeitraum_bis = None
    anzahl_monate = 0
    alle_monate: set[tuple[int, int]] = {f.schluessel for f in fakten}

    if alle_monate:
        sorted_alle = sorted(alle_monate)
        first = sorted_alle[0]
        last = sorted_alle[-1]
        zeitraum_von = f"{first[0]}-{first[1]:02d}"
        zeitraum_bis = f"{last[0]}-{last[1]:02d}"
        anzahl_monate = len(alle_monate)

    betriebskosten_zeitraum = betriebskosten_ges * anzahl_monate / 12 if anzahl_monate > 0 else 0
    # sonstige_netto steckt bereits in netto_ertrag (#326) — hier NICHT erneut
    # addieren, sonst Doppelzählung im ROI. Dasselbe gilt für `bkw_ersparnis`:
    # er ist seit P9 Teil von `netto_ertrag` (und bei mitgeschriebener BKW-
    # Erzeugung ohnehin 0, weil dann `ev_ersparnis` ihn trägt). Bis 2026-07-31
    # stand er hier zusätzlich — der ROI-Fortschritt war bei BKW-Besitzern um
    # die BKW-Ersparnis zu hoch.
    kumulative_ersparnis = netto_ertrag + wp_ersparnis + emob_ersparnis - betriebskosten_zeitraum
    roi_fortschritt = (kumulative_ersparnis / investition_gesamt * 100) if investition_gesamt > 0 else None

    return CockpitUebersichtResponse(
        pv_erzeugung_kwh=round(pv_erzeugung, 1),
        gesamtverbrauch_kwh=round(gesamtverbrauch, 1),
        netzbezug_kwh=round(netzbezug, 1),
        einspeisung_kwh=round(einspeisung, 1),
        direktverbrauch_kwh=round(direktverbrauch, 1),
        eigenverbrauch_kwh=round(eigenverbrauch, 1),
        autarkie_prozent=round(autarkie, 1),
        eigenverbrauch_quote_prozent=round(ev_quote, 1),
        direktverbrauch_quote_prozent=round(dv_quote, 1),
        spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 1) if spez_ertrag else None,
        anlagenleistung_kwp=round(anlagenleistung_kwp, 2),
        speicher_ladung_kwh=round(speicher_ladung, 1),
        speicher_entladung_kwh=round(speicher_entladung, 1),
        speicher_effizienz_prozent=round(speicher_effizienz, 1) if speicher_effizienz else None,
        speicher_vollzyklen=round(speicher_vollzyklen, 1) if speicher_vollzyklen else None,
        speicher_kapazitaet_kwh=round(speicher_kapazitaet, 1),
        hat_speicher=hat_speicher,
        wp_waerme_kwh=round(wp_waerme, 1),
        wp_strom_kwh=round(wp_strom, 1),
        wp_heizung_kwh=round(wp_heizung, 1),
        wp_warmwasser_kwh=round(wp_warmwasser, 1),
        wp_cop=round(wp_cop, 2) if wp_cop else None,
        wp_ersparnis_euro=round(wp_ersparnis, 2),
        hat_waermepumpe=hat_waermepumpe,
        emob_km=round(emob_km, 0),
        emob_ladung_kwh=round(emob_ladung, 1),
        emob_pv_anteil_prozent=round(emob_pv_anteil, 1) if emob_pv_anteil else None,
        emob_ersparnis_euro=round(emob_ersparnis, 2),
        emob_verbrauch_100km=round(emob_eff.wert, 1) if emob_eff.wert is not None else None,
        emob_verbrauch_quelle=emob_eff.quelle,
        hat_emobilitaet=hat_emobilitaet,
        bkw_erzeugung_kwh=round(bkw_erzeugung, 1),
        bkw_eigenverbrauch_kwh=round(bkw_eigenverbrauch, 1),
        hat_balkonkraftwerk=hat_balkonkraftwerk,
        sonstiges_erzeugung_kwh=round(sonstiges_erzeugung, 1),
        sonstiges_verbrauch_kwh=round(sonstiges_verbrauch, 1),
        hat_sonstiges=hat_sonstiges,
        einspeise_erloes_euro=round(einspeise_erloes, 2),
        einspeise_neg_preis_kwh=(
            round(nicht_verguetete_kwh_sum, 1) if hat_neg_preis_daten else None
        ),
        nicht_vergueteter_erloes_euro=(
            round(nicht_vergueteter_erloes_sum, 2) if hat_neg_preis_daten else None
        ),
        ev_ersparnis_euro=round(ev_ersparnis, 2),
        netzbezug_kosten_euro=round(netzbezug_kosten, 2),
        ust_eigenverbrauch_euro=round(ust_eigenverbrauch, 2) if ust_eigenverbrauch > 0 else None,
        netto_ertrag_euro=round(netto_ertrag, 2),
        bkw_ersparnis_euro=round(bkw_ersparnis, 2),
        sonstige_netto_euro=round(sonstige_netto, 2),
        jahres_rendite_prozent=round(roi_fortschritt, 1) if roi_fortschritt else None,
        investition_gesamt_euro=round(investition_gesamt, 2),
        investition_vollkosten_euro=round(investition_vollkosten, 2),
        investition_mehrkosten_euro=round(investition_mehrkosten, 2),
        steuerliche_behandlung=steuerliche_beh if steuerliche_beh != "keine_ust" else None,
        co2_pv_kg=round(co2_pv, 1),
        co2_wp_kg=round(co2_wp, 1),
        co2_emob_kg=round(co2_emob, 1),
        co2_gesamt_kg=round(co2_gesamt, 1),
        anzahl_monate=anzahl_monate,
        zeitraum_von=zeitraum_von,
        zeitraum_bis=zeitraum_bis,
    )
