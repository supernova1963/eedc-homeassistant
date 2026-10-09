"""Komponenten-Dashboard Waermepumpe (Kennzahlen je Geraet, Achsen, Wetternormierung, Betriebsart-Split).

GET /api/investitionen/dashboard/waermepumpe/{anlage_id}
"""
# Reiner Umzug aus `api/routes/investitionen/dashboards.py` (18.09.2026, Vorlage 6 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `dashboards.py` haengt den Router an der
# bisherigen Stelle ein und exportiert die Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import date
from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_strompreis_for_komponente,
)
from backend.core.investition_parameter import PARAM_WAERMEPUMPE, abgrenzung_stoerung
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.mitteltemperatur import lade_heizgradtage_je_monat
from backend.services.waermepumpe_kennzahlen_je_geraet import kennzahlen_aus_monatszeilen
from backend.core.calculations import co2_wp_ersparnis_kg
from backend.core.field_definitions import get_wp_strom_kwh, get_wp_warmwasser_kwh
from backend.core.berechnungen import (
    modus_strom_zeile,
    HEIZGRENZE_C,
    heizgradtage_grund,
    heiz_effizienz_gepflegt,
)
from backend.core.berechnungen.waermepumpe_kennzahl import (
    ersparnis_vorbehalt,
    heizwaerme_kwh,
    waerme_gesamt_kwh,
    waerme_herkunft,
)
from backend.api.routes.investitionen.crud import InvestitionResponse
from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse

router = APIRouter()


class WpMonatsWert(BaseModel):
    """Ein Monat der Wärmepumpe, so wie die Kopfzahlen ihn rechnen (N-643, N-644; Bauform N-638).

    Der Hub-Verlauf („Wärmeerzeugung pro Monat", Monatstabelle) und die Aussicht lasen bis 4.1.3
    ``heizenergie_kwh``/``warmwasser_kwh``/``stromverbrauch_kwh`` roh — ein gemeinsamer Wärmezähler
    (``waerme_kwh``), die Heizwärme aus Betriebsart-Zählern (N-398) und die getrennte Strommessung standen
    dort als 0. Die Reihe kommt aus der Faltung, die auch die Kopfzahlen bildet
    (``waermepumpe_kennzahlen_je_geraet.mengen_aus_monatszeilen``); Σ Monate = ``gesamt_stromverbrauch_kwh``,
    ``gesamt_heizenergie_kwh``, ``gesamt_warmwasser_kwh``, ``gesamt_waerme_kwh``.
    """
    jahr: int
    monat: int
    #: ``get_wp_strom_kwh`` — dieselbe Strom-Definition wie Nenner und Monats-Fakten (W-15)
    strom_kwh: float
    #: ``heizwaerme_kwh`` (Gerätefeld, sonst Betriebsart-Nutzenergie Heizen), 0 ohne Zähler — wie der Kopf
    heizung_kwh: float
    #: ``get_wp_warmwasser_kwh``
    warmwasser_kwh: float
    #: ``waerme_gesamt_kwh`` — Gesamtwert vor Summanden (D1). Ohne Warmwasser-Achse trägt die Fläche „Wärme"
    #: diesen Wert (S2: ein gemeinsamer Zähler ist Gesamtwärme, keine Heizwärme)
    waerme_kwh: float


class WaermepumpeDashboardResponse(BaseModel):
    """Wärmepumpe Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    #: N-643/N-644: die bewertete Monatsreihe — Hub-Verlauf, Monatstabelle und Aussicht lesen sie statt
    #: ``monatsdaten[].verbrauch_daten``.
    monatsreihe: list[WpMonatsWert] = []
    zusammenfassung: dict[str, Any]

@router.get("/dashboard/waermepumpe/{anlage_id}", response_model=list[WaermepumpeDashboardResponse])
async def get_waermepumpe_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis (auto aus WP-Tarif wenn leer)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Wärmepumpe Dashboard für eine Anlage.

    Zeigt alle Wärmepumpen mit COP, Heizkosten, Ersparnis vs. alte Heizung.
    """
    # WP-Tarif laden
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    wp_tarif = tarife.get("waermepumpe")
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "waermepumpe")

    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WAERMEPUMPE.value)
    )
    waermepumpen = inv_result.scalars().all()

    if not waermepumpen:
        return []

    # Anlage einmal laden — get_counter_lifetime braucht sensor_mapping.
    anlage_result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = anlage_result.scalar_one_or_none()
    if anlage is None:
        return []

    from backend.services.datenquellen_resolver import inv_feld_hat_quelle
    from backend.services.sensor_snapshot_service import get_counter_lifetime

    # Batch-Query: Alle Monatsdaten für alle Wärmepumpen auf einmal laden
    wp_ids = [w.id for w in waermepumpen]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(wp_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Counter-Tagesinkremente (Starts + Betriebsstunden, Issue #169 / #238):
    # Quelle TagesZusammenfassung.komponenten_starts mit
    # {"wp_starts_anzahl": {"<inv_id>": <int>},
    #  "wp_betriebsstunden": {"<inv_id>": <float>}}.
    # Wird hier für Max/Tag-KPI + Σ-Betriebsstunden-Aggregat gebraucht.
    # Σ Lebensdauer-Starts kommt direkt aus dem Hersteller-Sensor
    # (`get_counter_lifetime`), Σ-Betriebsstunden ebenfalls direkt aus dem
    # Sensor — beide sind kumulative Counter, der Sensor ist die Wahrheit.
    # #308 (detLAN): Die Counter-Tagesinkremente MÜSSEN auf die WP-Laufzeit
    # (Anschaffung→Stilllegung) gefiltert werden — symmetrisch zum
    # Monatsdaten-Filter unten (`ist_aktiv_im_monat`). Ohne diesen Filter
    # summierte `summe_erfasst` die gesamte je erfasste Sensor-Historie
    # (inkl. Backfill-Tagen vor Anschaffung) und lief gegen den vollen
    # Lebensdauer-Zählerstand — physikalisch unmöglich (Σ seit Anschaffung
    # > Lebensdauer). Der LTS-Abruf selbst ist korrekt; gefehlt hat der
    # Anschaffungsdatum-Scope im Read-Pfad ([[feedback_anschaffungsdatum_grenze]]).
    # `ist_aktiv_im_zeitraum(tag, tag)` prüft Laufzeit-Fenster UND `aktiv`-Flag
    # (aktiv=False = wie gelöscht → nirgends, bis reaktiviert; Gernot 2026-06-05).
    # Symmetrisch zum Monatsdaten-Filter, der dieselbe Sichtbarkeitsregel nutzt.
    wp_by_id = {w.id: w for w in waermepumpen}
    tz_result = await db.execute(
        select(TagesZusammenfassung.datum, TagesZusammenfassung.komponenten_starts)
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .where(TagesZusammenfassung.komponenten_starts.is_not(None))
    )
    starts_by_inv: dict[int, list[int]] = {wid: [] for wid in wp_ids}
    stunden_by_inv: dict[int, list[float]] = {wid: [] for wid in wp_ids}
    for tz_datum, komp_starts in tz_result.all():
        wp_map = (komp_starts or {}).get("wp_starts_anzahl") or {}
        for inv_id_str, count in wp_map.items():
            try:
                inv_id = int(inv_id_str)
            except (TypeError, ValueError):
                continue
            wp = wp_by_id.get(inv_id)
            if wp is None or not wp.ist_aktiv_im_zeitraum(tz_datum, tz_datum):
                continue
            if isinstance(count, (int, float)) and count > 0:
                starts_by_inv[inv_id].append(int(count))
        stunden_map = (komp_starts or {}).get("wp_betriebsstunden") or {}
        for inv_id_str, hours in stunden_map.items():
            try:
                inv_id = int(inv_id_str)
            except (TypeError, ValueError):
                continue
            wp = wp_by_id.get(inv_id)
            if wp is None or not wp.ist_aktiv_im_zeitraum(tz_datum, tz_datum):
                continue
            if isinstance(hours, (int, float)) and hours > 0:
                stunden_by_inv[inv_id].append(float(hours))

    # Anlage-Monatsdaten für den Monats-Gaspreis (Vorrang vor dem
    # WP-Parameter-Default, wie in `aussichten/finanz_eingaenge.py` und im HA-Export).
    wp_anlage_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    wp_anlage_md = {(m.jahr, m.monat): m for m in wp_anlage_md_result.scalars().all()}

    # Heizgradtage für die Wetternormierung (SOLL Wärme/Klima §4.1, K-2/K-3).
    # ⭐ **Einmal je Request, VOR der Geräteschleife** — das Wetter ist eine
    # Eigenschaft der **Anlage**, nicht des Geräts: Zwei Wärmepumpen an einem
    # Standort teilen dieselbe Außentemperatur, und je Gerät zu laden hieße,
    # dieselbe Reihe mehrfach zu lesen und Gefahr zu laufen, sie versehentlich
    # zu filtern. Die Liste ist deshalb in jedem Geräte-Eintrag identisch
    # (`test_wp_hub_wetternormierung.py`).
    wp_heizgradtage = await lade_heizgradtage_je_monat(db, anlage_id)
    wp_heizgradtage_liste = [
        {
            'jahr': h.jahr, 'monat': h.monat, 'kd': h.kd,
            'tage_mit_temperatur': h.tage_mit_temperatur,
            'tage_im_monat': h.tage_im_monat,
        }
        for h in sorted(
            wp_heizgradtage.values(), key=lambda h: (h.jahr, h.monat),
        )
    ]

    dashboards = []
    for wp in waermepumpen:
        # Issue #153 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(wp.id, [])
            if wp.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        # ⭐ **WK-16a (14.09.2026): die Faltung steht nicht mehr hier.**
        # Sie ist wortgleich nach `services/waermepumpe_kennzahlen_je_geraet.py`
        # gehoben — **eine** Rechenstelle für die Kennzahl je Gerät, die der
        # Komponenten-Hub UND der Cockpit-Block *Wärme/Klima* rufen (D-Sicht 3).
        # Bis dahin gab es die Gerätezahlen nur hier; das Cockpit verwies mit
        # einem Link darauf. Sie dort neu zu rechnen wäre die W-3-Klasse
        # gewesen — dieselbe Kennzahl an zwei Orten —, und diese Funktion hat
        # sie schon dreimal erlebt (W-3 · W-15 · N-397).
        #
        # ⚠ **Der Zeitfilter bleibt hier**: `monatsdaten` ist bereits über
        # `ist_aktiv_im_monat` geschnitten (#153/#236). Der Dienst faltet, was
        # er bekommt — Hub und Cockpit filtern verschieden (Lebensdauer gegen
        # Zeitfenster), die Faltung selbst ist dieselbe.
        _kz, _faltung = kennzahlen_aus_monatszeilen(wp, monatsdaten)
        _mengen = _kz.mengen
        gesamt_strom = _mengen.strom_kwh
        gesamt_strom_heizen = _mengen.strom_heizen_kwh
        gesamt_strom_warmwasser = _mengen.strom_warmwasser_kwh
        gesamt_heizung = _mengen.heizung_kwh
        gesamt_warmwasser = _mengen.warmwasser_kwh
        hat_getrennte_strom = _mengen.hat_getrennte_strommessung
        gesamt_heizung_getrennt = _mengen.heizung_getrennt_kwh
        gesamt_warmwasser_getrennt = _mengen.warmwasser_getrennt_kwh
        waerme_ist_gesamt_getrennt = _mengen.waerme_ist_gesamt_getrennt
        waerme_abgeleitet = _mengen.waerme_abgeleitet
        gesamt_waerme = _mengen.waerme_kwh
        gesamt_kaelte = _mengen.kaelte_kwh
        gesamt_modus_heizen = _faltung.modus_heizen_kwh
        gesamt_modus_kuehlen = _faltung.modus_kuehlen_kwh
        gesamt_modus_warmwasser = _faltung.modus_warmwasser_kwh
        gesamt_modus_lueften = _faltung.modus_lueften_kwh
        gesamt_modus_entfeuchten = _faltung.modus_entfeuchten_kwh
        gesamt_nutz_lueften = _faltung.nutzenergie_lueften_kwh
        gesamt_nutz_entfeuchten = _faltung.nutzenergie_entfeuchten_kwh
        gesamt_modus_funktionsfremd_abzug = _mengen.funktionsfremd_abzug_kwh
        gesamt_modus_abdeckung_h = _faltung.modus_abdeckung_h
        gesamt_modus_bezug = _faltung.modus_bezug_kwh
        modus_gemessen = _faltung.modus_gemessen
        jaz_je_monat = _faltung.jaz_je_monat
        # N-379 / #404 (8ear) — die Achsen-Frage. `_hat_warmwasser` ist die
        # Bauart-Frage (R1, erste Hälfte), `_ww_je_erfasst` die Zähler-Frage
        # (zweite Hälfte): *„was ein Gerät liefern kann, sagt der zugeordnete
        # Zähler, nicht seine Bauart"*. Beides gehört zur **Anzeige** des Hubs,
        # nicht zur Kennzahl — deshalb bleibt es hier.
        #
        # ⚠ **Nur der Total-Fall** (Entscheid 29.08.): unterdrückt wird, was NIE
        # gemessen wurde. Ein einziger gepflegter Monat — auch mit 0 — lässt die
        # Achse stehen, denn dann ist die 0 der übrigen Monate eine Messung.
        _hat_warmwasser = _mengen.hat_warmwasser_groesse
        _ww_je_erfasst = _faltung.warmwasser_je_erfasst
        _ww_hat_quelle = inv_feld_hat_quelle(
            anlage.sensor_mapping, wp.id, "warmwasser_kwh"
        )
        _az_gesamt = _kz.gesamt
        durchschnitt_cop = _az_gesamt.wert

        # Drift-Audit Domäne A1 / Issue #178: vorher las dieser Endpoint
        # `gas_kwh_preis_cent` (toter Key, Form schreibt `alter_preis_cent_kwh`)
        # und ignorierte den Wirkungsgrad-Faktor → Ergebnis +16€ Drift.
        #
        # ADR-002/P8: JE MONAT rechnen statt Energien über die Lebensdauer zu
        # summieren und einmal mit dem HEUTIGEN Tarif zu multiplizieren. Ein
        # Tarifwechsel hätte sonst die gesamte WP-Historie neu bewertet. Der
        # Helper ist linear und kennt keine Jahres-Fixkosten, die Summe der
        # Monate ist also identisch, solange der Preis konstant ist. Nebenbei
        # erledigt das den TODO „monatlicher Gaspreis-Override": er wird jetzt
        # wie in `aussichten/finanz_rueckblick.py` je Monat gezogen.
        wp_kosten = 0.0
        alte_heizung_kosten = 0.0
        # F-42: Die Ersparnis kommt aus dem Layer-SoT (ADR-001), statt hier als
        # Differenz `alte_heizung_kosten - wp_kosten` nachgebaut zu werden. Bei
        # bewertbaren Wärmepumpen sind beide Wege zahlengleich — der Helper ist
        # linear —, es bewegt sich also keine bestehende Zahl.
        #
        # ⚑ **Gemessen, nicht behauptet:** Diese Umstellung allein ist NICHT der
        # Schutz. Der Sprengsatz „Differenz statt SoT-Summe" blieb stumm, weil
        # die `bewertbar`-Sperre unten den Wert ohnehin auf `None` zieht. Rot
        # wird erst die Kombination *Differenz **und** keine Sperre* — dann
        # stünde für eine Klimaanlage `0 € Gas − 1.312 € Strom` als **negative
        # Ersparnis** im Hub. Wer eine der beiden Hälften entfernt, muss die
        # andere prüfen; der Prüfer dafür ist
        # `test_f42_route_ersparnis_wird_nie_negativ`.
        ersparnis = 0.0
        # Trägt mindestens ein Monat einen echten Vergleich? Sonst gibt es
        # keine Ersparnis-, Alt-Kosten- und CO₂-Zahl, die etwas behauptet.
        bewertbar = False
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            # N-391: kanonisch wie die Zeile oben (D1) — ohne diesen Aufruf
            # blieben Ersparnis, Alt-Kosten und CO₂ einer Wärmepumpe mit
            # gemeinsamem Wärmemengenzähler leer, obwohl ihre Wärme gemessen ist.
            m_waerme = waerme_gesamt_kwh(
                d.get('waerme_kwh'),
                heizwaerme_kwh(d),                       # N-398
                get_wp_warmwasser_kwh(d, wp.parameter),  # N-379
            )
            # B3/H-1 (05.09.2026): **dieselbe** Strom-Definition wie Nenner (W-15)
            # und Monats-Fakten. Hier stand die Rohspalte — bei getrennter
            # Strommessung ist sie leer (Registry: `!getrennte_strommessung`),
            # und der Hub nannte WP-Kosten 0 € und als Ersparnis die vollen
            # Alt-Kosten (F7 gemessen: 480 € statt 180 €). Dritte Runde der
            # W-15-Klasse in dieser Funktion.
            m_strom = get_wp_strom_kwh(d, wp.parameter)
            if m_waerme <= 0 and m_strom <= 0:
                continue
            m_tarife = await lade_tarife_fuer_anlage(
                db, anlage_id, target_date=date(md.jahr, md.monat, 1)
            )
            m_wp_preis = resolve_strompreis_for_komponente(
                m_tarife, "waermepumpe", fallback=strompreis_cent
            )
            m_anlage_md = wp_anlage_md.get((md.jahr, md.monat))
            m_ergebnis = berechne_wp_ersparnis(
                wp_waerme_kwh=m_waerme,
                wp_strom_kwh=m_strom,
                wp_strompreis_cent=m_wp_preis,
                wp_parameter=wp.parameter,
                monats_gaspreis_cent=(
                    m_anlage_md.gaspreis_cent_kwh if m_anlage_md else None
                ),
                # E-B: Kühlen ersetzt keine Heizung — sein Strom gehört nicht
                # in den Vergleich (sonst: gemessene −45,04 € Ersparnis).
                #
                # ⛔ **Hier stand bis zum 26.08.2026 `d.get(MODUS_STROM_FELD[…])`**
                # — also **nur der abgeleitete** Wert. Bei einer Zeile mit
                # gemessenen Betriebsart-Zählern steht dieses Feld gar nicht in
                # den Daten: E-B griff dort auf 0 und der Kühlstrom blieb im
                # Vergleich. Getroffen war ausgerechnet, wer am genauesten misst.
                # Dieselbe Klasse wie die Schleife darüber (F-56) — die Weiche
                # gehört in den SoT, nicht in eine dritte Kopie.
                strom_kuehlen_kwh=modus_strom_zeile(d).kuehlen_kwh,
            )
            wp_kosten += m_ergebnis.wp_kosten_euro
            alte_heizung_kosten += m_ergebnis.alte_heizung_kosten_euro
            ersparnis += m_ergebnis.ersparnis_euro
            bewertbar = bewertbar or m_ergebnis.bewertbar

        # CO2-Ersparnis: kanonischer Helfer (ADR-001, DI-1/DI-2-A). Vorher rechnete
        # dieser Endpoint `wärme × f_gas − strom × f_strom` OHNE den Gas-Kessel-
        # Wirkungsgrad (η_gas) — die vermiedene Gas-Wärme muss aber erst über η_gas
        # in Brennstoff zurückgerechnet werden. Als 4. WP-CO₂-Read-Site driftete das
        # Dashboard nach DI-1 sichtbar gegen Cockpit/Jahresbericht/Nachhaltigkeit
        # (Demo lifetime: 2303,6 → 2744,3 kg, = Σ der Cockpit-Jahreswerte).
        # N-88/F2b: der Traeger entscheidet mit — ohne ersetzte Heizung gibt es
        # keine vermiedene Verbrennung (Filter im SoT, nicht hier).
        co2_ersparnis = co2_wp_ersparnis_kg(
            gesamt_waerme, gesamt_strom,
            (wp.parameter or {}).get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]),
            # E-B: Kühlen ersetzt keine Heizung (#263 K-2).
            strom_kuehlen_kwh=gesamt_modus_kuehlen,
        )

        # Kompressor-Starts: Σ Lebensdauer kommt direkt aus dem Hersteller-
        # Sensor (Hersteller zählt seit Werks-Inbetriebnahme, das ist die
        # Wahrheit). Drift zwischen Hersteller-Counter und EEDC-Tagesinkrementen
        # wird im Daten-Checker sichtbar gemacht, nicht im Read-Pfad versteckt.
        # Max/Tag bleibt aus EEDC-Tagesinkrementen (echte Höchst-Tagessumme).
        # #238/#290 (detLAN-Kompromiss): Hauptwert der Kachel ist die seit
        # Anschaffung von eedc erfasste Summe der Tagesinkremente (Anzeige
        # konsequent ab Anschaffungsdatum limitiert, auch wenn der Hersteller-
        # Counter weiter zurückreicht). Der rohe Lebensdauer-Zählerstand
        # (`get_counter_lifetime`) bleibt erhalten, wandert aber nur noch als
        # Zählerstand in die Kachel-Info/Tooltip.
        wp_starts_list = starts_by_inv.get(wp.id, [])
        starts_lifetime = await get_counter_lifetime(
            db, anlage, wp, 'wp_starts_anzahl'
        )
        kompressor_starts_gesamt = (
            int(round(starts_lifetime)) if starts_lifetime is not None else None
        )
        kompressor_starts_summe_erfasst = (
            int(round(sum(wp_starts_list))) if wp_starts_list else None
        )
        kompressor_starts_max_tag = max(wp_starts_list) if wp_starts_list else None

        # Betriebsstunden (#238 detLAN): Σ Lebensdauer + Max/Tag analog zu den
        # Starts. KPI „Ø Laufzeit pro Start" und „Starts pro Betriebsstunde"
        # nur sichtbar wenn beide Werte für denselben Lebensdauer-Stand vorhanden
        # sind — ansonsten wären sie Krücken, weil Starts- und Stunden-Sensor
        # zu unterschiedlichen Zeitpunkten in Betrieb genommen worden sein
        # können.
        wp_stunden_list = stunden_by_inv.get(wp.id, [])
        betriebsstunden_gesamt = await get_counter_lifetime(
            db, anlage, wp, 'wp_betriebsstunden'
        )
        betriebsstunden_summe_erfasst = (
            round(sum(wp_stunden_list), 1) if wp_stunden_list else None
        )
        betriebsstunden_max_tag = (
            round(max(wp_stunden_list), 1) if wp_stunden_list else None
        )
        # Ratios aus den seit-Anschaffung erfassten Summen (gleicher Zeitraum
        # für Starts und Stunden — die zwei Lebensdauer-Counter können zu
        # unterschiedlichen Zeitpunkten in Betrieb genommen worden sein).
        oe_laufzeit_pro_start_h: Optional[float] = None
        starts_pro_betriebsstunde: Optional[float] = None
        if (
            betriebsstunden_summe_erfasst is not None
            and kompressor_starts_summe_erfasst is not None
            and kompressor_starts_summe_erfasst > 0
            and betriebsstunden_summe_erfasst > 0
        ):
            oe_laufzeit_pro_start_h = round(
                betriebsstunden_summe_erfasst / kompressor_starts_summe_erfasst, 2
            )
            starts_pro_betriebsstunde = round(
                kompressor_starts_summe_erfasst / betriebsstunden_summe_erfasst, 3
            )

        zusammenfassung = {
            'gesamt_stromverbrauch_kwh': round(gesamt_strom, 1),
            'gesamt_heizenergie_kwh': round(gesamt_heizung, 1),
            'gesamt_warmwasser_kwh': round(gesamt_warmwasser, 1),
            # N-379 / SOLL §3.3/S2 — „Ein Balken sagt, was er zeigt."
            # Der Client baute die Aufteilung bis hierher aus einem FESTEN Paar
            # Heizung/Warmwasser, unabhaengig davon, ob es die Achse am Geraet
            # gibt. An dietmars Klimaanlage stand deshalb „Warmwasser 889 kWh ·
            # 100 %" (T89667 #295), an jeder Waermepumpe ohne
            # Warmwasser-Zaehler eine Dauer-Null (8ear, #404).
            #
            # ⛔ **Es sagt NICHT „hier fehlt ein Zaehler".** Abdeckung ist Sache
            # des Daten-Checkers; hier steht nur, ob es die Groesse am Geraet
            # ueberhaupt gibt.
            'hat_warmwasser_achse': (
                _hat_warmwasser and (_ww_je_erfasst or _ww_hat_quelle)
            ),
            'gesamt_waerme_kwh': round(gesamt_waerme, 1),
            # F-42: „nicht bewertet heißt keine Zahl" (N-258-Klasse). Ohne
            # gemessene Wärme ist die JAZ keine 0, sondern unbekannt; ohne
            # ersetzte Heizung gibt es weder Alt-Kosten noch Ersparnis noch
            # vermiedenes CO₂. Vorher stand hier für eine Klimaanlage mit
            # 4.375 kWh Verbrauch viermal „0,00" — während dieselbe Anlage in
            # Cockpit → Jahr „—" und in Auswertungen → ROI „nicht bewertet"
            # sagte. `None` statt 0 heilt alle drei Anzeigen auf einmal
            # (Komponenten-Hub, Cockpit → Aussicht, Kostenvergleich), weil die
            # Format-Kette im Client `null` bereits als „—" trägt.
            #
            # `wp_kosten_euro` bleibt eine Zahl: Strom × Preis ist immer
            # bestimmt und die einzige Aussage, die hier ohne Vergleich gilt.
            # W-15: `None` **und** der Grund daneben — bisher gab es hier nur
            # die Zahl oder gar nichts, und der Anwender stand ohne Auskunft da.
            'durchschnitt_cop': (
                round(durchschnitt_cop, 2) if durchschnitt_cop is not None else None
            ),
            'durchschnitt_cop_grund': _az_gesamt.grund,
            # P12: je Monat — die Zeitreihe, aus der Vergleich und Trend lesen.
            'jaz_je_monat': jaz_je_monat,
            # Wetternormierung (SOLL §4.1): der **Nenner** je Monat, dazu die
            # Definition und — wo die Reihe nicht so weit zurückreicht wie die
            # Verbrauchshistorie — der Grund (S3).
            #
            # ⛔ **Kein Feld „hat getrennte Strommessung" daneben.** Ob der
            # Client den normierten Modus anbietet, entscheidet er an
            # `heizen_nenner_kwh` (steht schon in `jaz_je_monat`) — ein zweiter
            # Weg zur selben Auskunft wäre die Drift, die P12 gerade abgeschafft
            # hat.
            'heizgradtage_je_monat': wp_heizgradtage_liste,
            'heizgradtage_grund': heizgradtage_grund(
                wp_heizgradtage,
                erster_monat_mit_bedarf=(
                    min((md.jahr, md.monat) for md in monatsdaten)
                    if monatsdaten else None
                ),
            ),
            'heizgrenze_c': HEIZGRENZE_C,
            # W-6: Der Heizstab-Satz gab es bis zum 26.08. **nur im Cockpit**
            # (`aktueller_monat.py`). Genau ihn verspricht die Melder-Antwort an
            # dietmar1968 aber für den Komponenten-Hub — dort war er nie.
            'durchschnitt_cop_hinweis': _az_gesamt.hinweis,
            'wp_kosten_euro': round(wp_kosten, 2),
            'alte_heizung_kosten_euro': round(alte_heizung_kosten, 2) if bewertbar else None,
            'ersparnis_euro': round(ersparnis, 2) if bewertbar else None,
            'co2_ersparnis_kg': round(co2_ersparnis, 1) if bewertbar else None,
            'anzahl_monate': len(monatsdaten),
            # _summe_erfasst = seit Anschaffung von eedc erfasst (Kachel-Hauptwert);
            # _gesamt = roher Lebensdauer-Zählerstand (Kachel-Tooltip/Info, #238/#290).
            'kompressor_starts_summe_erfasst': kompressor_starts_summe_erfasst,
            'kompressor_starts_gesamt': kompressor_starts_gesamt,
            'kompressor_starts_max_tag': kompressor_starts_max_tag,
            'betriebsstunden_summe_erfasst': betriebsstunden_summe_erfasst,
            'betriebsstunden_gesamt': (
                round(betriebsstunden_gesamt, 1)
                if betriebsstunden_gesamt is not None else None
            ),
            'betriebsstunden_max_tag': betriebsstunden_max_tag,
            'oe_laufzeit_pro_start_h': oe_laufzeit_pro_start_h,
            'starts_pro_betriebsstunde': starts_pro_betriebsstunde,
        }

        # ── Modus-Split (#263 K-2, S4 · Konzept §4) ─────────────────────────
        # Alles oder nichts: ohne eine einzige erfasste Stunde gibt es keine
        # Aufteilung — und dann steht dort **keine 0**, sondern gar nichts.
        # Eine 0 hieße „hat nicht geheizt"; das weiß eedc ohne Modus-Signal
        # nicht (ADR-002/P4, die N-258-Klasse).
        # ⚠ **Zwei Wege hierher** (#263): abgeleitet (dann gibt es
        # Abdeckungs-Stunden) oder gemessen (dann gibt es keine — ein Zähler
        # zählt kWh, keine Stunden mit Signal). Nur die Abdeckung zu prüfen
        # hieße, eine gemessene Aufteilung nirgends zu zeigen.
        if gesamt_modus_abdeckung_h > 0 or modus_gemessen:
            zusammenfassung['modus_strom_heizen_kwh'] = round(gesamt_modus_heizen, 1)
            zusammenfassung['modus_strom_kuehlen_kwh'] = round(gesamt_modus_kuehlen, 1)
            zusammenfassung['modus_strom_warmwasser_kwh'] = round(gesamt_modus_warmwasser, 1)
            zusammenfassung['modus_strom_lueften_kwh'] = round(gesamt_modus_lueften, 1)
            zusammenfassung['modus_strom_entfeuchten_kwh'] = round(gesamt_modus_entfeuchten, 1)
            # R-C (WK-16f/N-398): die **Mengen**zeile neben dem Strom — nur mit
            # Zahl (D-Sicht). Ein Feld, das die Datenquellen-Flaeche anbietet,
            # muss irgendwo erscheinen; eine 0-Zeile an jeder Waermepumpe waere
            # dagegen genau die Zeile, die fuer fast jeden nichts sagt (E4).
            if gesamt_nutz_lueften:
                zusammenfassung['modus_nutzenergie_lueften_kwh'] = round(
                    gesamt_nutz_lueften, 1)
            if gesamt_nutz_entfeuchten:
                zusammenfassung['modus_nutzenergie_entfeuchten_kwh'] = round(
                    gesamt_nutz_entfeuchten, 1)
            # „nicht aufgeteilt" wird NIE gespeichert, sondern immer gerechnet
            # (Konzept §3.1, Folge 2) — damit ist es für Altmonate, Ausfälle
            # und Handpflege gleichermaßen vollständig. Auf 0 geklemmt: die
            # Invariante hält das schon im Schreibpfad, aber eine negative
            # Restmenge wäre auf jeder Fläche Unsinn.
            # Bezug ist der Strom der Monate MIT Split — nicht der Gesamtstrom
            # des Geräts über alle Monate. Sonst zählte ein Monat vor der
            # Sensor-Zuordnung als „nicht aufgeteilt" (dieselbe Klasse wie der
            # anlagenweite Bezug in `WpFakten.modus_nicht_aufgeteilt_kwh`).
            zusammenfassung['modus_nicht_aufgeteilt_kwh'] = round(
                max(0.0, gesamt_modus_bezug - gesamt_modus_heizen - gesamt_modus_kuehlen
                    - gesamt_modus_warmwasser
                    - gesamt_modus_lueften - gesamt_modus_entfeuchten), 1
            )
            zusammenfassung['modus_abdeckung_h'] = round(gesamt_modus_abdeckung_h, 1)
            zusammenfassung['modus_gemessen'] = modus_gemessen
            # W-17b: Der Hub zeigt EIN Geraet — hier faellt die Grundmenge mit
            # dem Geraete-Strom fast zusammen. Fast, nicht ganz: Monate ohne
            # Split zaehlen im Bezug NICHT mit (s. Kommentar oben), im
            # Gesamtstrom schon. Der Balken nennt seine Grundmenge deshalb auch
            # hier — sonst waere es dieselbe stumme Differenz wie anlagenweit,
            # nur kleiner.
            zusammenfassung['modus_strom_bezug_kwh'] = round(gesamt_modus_bezug, 1)
        # Die Kennzeichnung der Wärme steht unabhängig davon: sie gilt auch für
        # Monate, deren Split später verworfen wurde.
        zusammenfassung['waerme_abgeleitet'] = waerme_abgeleitet
        zusammenfassung['waerme_abgeleitet_faktor'] = (
            heiz_effizienz_gepflegt(wp.parameter) if waerme_abgeleitet else None
        )
        # B3/H-2 (SOLL §3.3 Hub-Zeile, §6 Präzisierung 05.09.): die Herkunft der
        # Wärme und der Vorbehalt an Ersparnis/CO₂ — fertig formuliert aus dem
        # Layer, damit Cockpit (B4) und PDF dieselben Worte tragen.
        zusammenfassung['waerme_herkunft'] = waerme_herkunft(
            waerme_abgeleitet, zusammenfassung['waerme_abgeleitet_faktor'],
        )
        zusammenfassung['ersparnis_vorbehalt'] = ersparnis_vorbehalt(
            waerme_abgeleitet=waerme_abgeleitet,
            abgrenzung=abgrenzung_stoerung(wp),
        )

        # W-5 (SOLL §4.1): Arbeitszahl Kühlen. ⚠ **Bewusst außerhalb des
        # `hat_getrennte_strom`-Blocks darunter:** Sie hängt an den
        # Betriebsart-Zählern, nicht an der Heizen/Warmwasser-Trennung. Eine
        # Klimaanlage hat oft genau diese Zähler und nie eine getrennte
        # Strommessung — sie hier mit einzusperren hieße, die Zahl genau dem
        # Gerätetyp vorzuenthalten, für den sie gebaut ist.
        # WK-16a: aus dem Dienst, nicht daneben gerechnet — dieselbe Eingabe,
        # dieselbe Sperre, derselbe Wert.
        _az_kuehlen = _kz.kuehlen
        if _az_kuehlen.wert is not None or gesamt_modus_kuehlen > 0:
            zusammenfassung['jaz_kuehlen'] = (
                round(_az_kuehlen.wert, 2) if _az_kuehlen.wert is not None else None
            )
            zusammenfassung['jaz_kuehlen_grund'] = _az_kuehlen.grund
            # A6 (N-365): die beiden Zahlen, aus denen die Arbeitszahl
            # ENTSTANDEN ist — aus demselben Layer-Objekt wie der Wert, nicht
            # aus den Anzeigefeldern daneben. Sie sind `None`, wo es keinen
            # Wert gibt (der Layer setzt sie nur mit `wert`), und der Grund
            # steht dann weiterhin allein da.
            zusammenfassung['jaz_kuehlen_zaehler_kwh'] = (
                round(_az_kuehlen.zaehler_kwh, 1)
                if _az_kuehlen.zaehler_kwh is not None else None
            )
            zusammenfassung['jaz_kuehlen_nenner_kwh'] = (
                round(_az_kuehlen.nenner_kwh, 1)
                if _az_kuehlen.nenner_kwh is not None else None
            )
            zusammenfassung['gesamt_kaelte_kwh'] = round(gesamt_kaelte, 1)

        # W-4 (SOLL §4.1): Arbeitszahl je Funktion, wenn separate Strommessung
        # vorliegt. Q und E stammen aus **denselben** Monaten
        # (`*_getrennt`-Summen) — das ist die R2-Abgrenzung, und sie war hier
        # schon richtig gebaut.
        #
        # ⛔ **Drei Mängel standen hier bis zum 26.08.2026, alle im selben
        # Dreizeiler:**
        #
        #  1. **Der Quotient wurde SELBST gerechnet** statt über den Layer —
        #     die W-3-Klasse (die JAZ stand einmal an drei Orten). Damit fehlten
        #     hier **alle** R2-Sperren außer der abgeleiteten Wärme: ein
        #     Heizstab auf dem Zähler oder ein versetzter Zeitraum sperrte die
        #     Gesamtzahl, diese beiden aber nicht.
        #  2. **`0` statt „keine Aussage"** bei gesperrter Lage. Eine 0 heißt
        #     „Arbeitszahl null", nicht „unbekannt" (ADR-002/P4).
        #  3. **`cop_*` als Name**, obwohl das Projekt Perioden-Kennzahlen
        #     durchgängig als **JAZ** führt und COP ausdrücklich technischen
        #     Backend-Berechnungen vorbehält (Glossar, v3.23.4/#167).
        #
        # ⚠ **Angezeigt wurden sie durchaus** — im Komponenten-Hub als „JAZ
        # Heizen"/„JAZ Warmwasser" (`v4/komponentenAdapter.tsx`, Sekundär-Strip
        # „Betrieb & getrennte JAZ"). Sie fehlten dagegen in der **Monatssicht**,
        # und dort tragen sie seit dem 26.08. dieselben Werte aus derselben
        # Quelle. Der Anzeigename war schon vorher „JAZ" — nur der Feldname
        # hinkte hinterher, was Mangel 3 überhaupt erst erklärt.
        if hat_getrennte_strom:
            # R2, so weit dieser Endpunkt sehen kann: Er liest **ein** Gerät aus
            # seinen eigenen Monatszeilen. Die Anwender-Angabe „Fremdanteil auf
            # den Zählern" gilt hier genauso wie überall (ein Heizstab auf dem
            # WP-Zähler macht E zu groß, auch je Funktion). Die anlagenweite
            # Lage „nicht alle Geräte melden Wärme" gibt es hier NICHT — bei
            # einem einzelnen Gerät ist sie gegenstandslos —, und den
            # Zeitraum-Versatz kennt nur die Vier-Quellen-Auflösung in
            # `aktueller_monat`. Beides ist keine Lücke, sondern die Reichweite
            # dieser Sicht (dieselbe Begründung wie in `cockpit/komponenten.py`).
            zusammenfassung['gesamt_strom_heizen_kwh'] = round(gesamt_strom_heizen, 1)
            zusammenfassung['gesamt_strom_warmwasser_kwh'] = round(gesamt_strom_warmwasser, 1)
            zusammenfassung['gesamt_heizung_getrennt_kwh'] = round(gesamt_heizung_getrennt, 1)
            zusammenfassung['gesamt_warmwasser_getrennt_kwh'] = round(gesamt_warmwasser_getrennt, 1)
            # WK-16a: aus dem Dienst. ⚠ Der `if hat_getrennte_strom`-Riegel
            # darüber bleibt — er entscheidet, ob die Zahlen ÜBERHAUPT in die
            # Antwort gehören; der Dienst rechnet sie ohnehin nur mit
            # `hat_split` und liefert sonst den Grund.
            _az_funktion = _kz.je_funktion
            zusammenfassung['jaz_heizen'] = (
                round(_az_funktion.heizen.wert, 2)
                if _az_funktion.heizen.wert is not None else None
            )
            zusammenfassung['jaz_heizen_grund'] = _az_funktion.heizen.grund
            zusammenfassung['jaz_warmwasser'] = (
                round(_az_funktion.warmwasser.wert, 2)
                if _az_funktion.warmwasser.wert is not None else None
            )
            zusammenfassung['jaz_warmwasser_grund'] = _az_funktion.warmwasser.grund
            # A6 (N-365) — wie beim Kühlen: Zähler und Nenner aus DEMSELBEN
            # Layer-Objekt. ⛔ Nicht aus `gesamt_heizung_getrennt` /
            # `gesamt_strom_heizen` nachgebaut — nicht wegen eines Abzugs (den
            # gibt es je Funktion bewusst nicht, SOLL-§9-E7), sondern weil der
            # Layer entscheidet, OB es eine Zahl geben darf: bei abgeleiteter
            # Wärme oder Abgrenzungs-Störung stehen beide Rohsummen weiter in
            # dieser Antwort, und eine daraus gebaute Herleitung zeigte genau
            # die Rechnung, die es nicht geben darf (Konzept §3.5).
            # Probe: `test_a6_arbeitszahl_je_funktion_herleitung.py`.
            for _fn, _az in (('heizen', _az_funktion.heizen),
                             ('warmwasser', _az_funktion.warmwasser)):
                zusammenfassung[f'jaz_{_fn}_zaehler_kwh'] = (
                    round(_az.zaehler_kwh, 1) if _az.zaehler_kwh is not None else None
                )
                zusammenfassung[f'jaz_{_fn}_nenner_kwh'] = (
                    round(_az.nenner_kwh, 1) if _az.nenner_kwh is not None else None
                )

        dashboards.append(WaermepumpeDashboardResponse(
            investition=wp,
            monatsdaten=monatsdaten,
            monatsreihe=_faltung.monatsreihe,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards
