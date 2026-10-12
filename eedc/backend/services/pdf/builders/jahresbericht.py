"""
Daten-Aggregation für den Jahresbericht.

Extrahiert die bisher in `api/routes/import_export/pdf_operations.py` inline
ausgeführte Logik und liefert ein einziges `context`-Dict, das das
Jinja2-Template direkt verwenden kann.

Reine Datenschicht — keine HTTP-, keine Render-Aufrufe.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    PV_ERZEUGER_TYPEN,
    berechne_spez_ertrag_annualisiert,
    monatsgewichte_aus_pvgis,
    PV_QUELLE_FEHLT,
    PV_QUELLE_VERTEILT,
    FinanzMonatsZeile,
    autarkie_prozent,
    berechne_finanz_aggregat,
    betriebskosten_im_zeitraum,
    eigenverbrauchsquote_prozent,
    soll_im_laufmonat,
    spezifischer_ertrag_kwh_kwp,
    speicher_wirkungsgrad,
    vollzyklen as berechne_vollzyklen,
)
from backend.core.berechnungen.dienstliche_ladekosten import DIENSTLICHE_LADEKOSTEN_HINWEIS
from backend.core.investition_kennwerte import get_speicher_kapazitaet_kwh
from backend.core.investition_parameter import ist_dienstlich
from backend.services.waermepumpe_jahreskennzahlen import waermepumpe_jahreskennzahlen
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten
from backend.services.monats_co2 import co2_bilanz_aus_fakt
from backend.core.calculations import co2_wp_ersparnis_kg
from backend.core.berechnungen.pv_verteilung import verluste_grund_zeitraum
from backend.core.berechnungen.ergebnis import ErgebnisEingang, berechne_ergebnis, ust_anteil_euro
from backend.services.ust_satz import (
    grundgesamtheit as ust_grundgesamtheit,
    ust_eigenverbrauch_zeitraum,
    ust_satz_des_jahres,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.services.pv_monatswerte import lade_pv_je_monat
from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
from backend.core.berechnungen.erzeuger_traeger import (
    erzeuger_traeger,
    selbst_tragende_bkw_ids,
    traeger_im_monat,
    soll_nenner_kwp,
    traeger_zeilen,
    verteilungsnenner_kwp,
)
from backend.core.investition_kennwerte import get_erzeuger_kwp

from ..charts import autarkie_chart, energie_fluss_chart, pv_erzeugung_chart
from .finanzbericht import TYP_LABELS as _INV_TYP_LABELS

logger = logging.getLogger(__name__)

MONATSNAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


async def build_jahresbericht_context(
    db: AsyncSession,
    anlage_id: int,
    jahr: Optional[int] = None,
) -> dict:
    """
    Lädt alle Daten und liefert ein flaches Context-Dict für `jahresbericht.html`.

    Args:
        db: AsyncSession
        anlage_id: ID der Anlage
        jahr: Optional. Fehlt es, wird der gesamte Zeitraum erzeugt.

    Raises:
        LookupError: Wenn die Anlage nicht existiert.
    """
    # RF-9 (Serie „Funktion vor Datei"): Orchestrator — die Abschnitte 2–11 sind Phasen-Funktionen in dieser Datei,
    # in derselben Reihenfolge wie bisher (die Datenbank-Abfragen laufen in derselben Folge). Jede Phase nimmt ihre
    # Verzweigungen mit; hier steht nur, was die Abschnitte verbindet, und das Kontext-Dict.
    # ── 1. Anlage ───────────────────────────────────────────────────────
    res = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = res.scalar_one_or_none()
    if not anlage:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")

    ist_gesamtzeitraum = jahr is None

    b = await _bestand(db, anlage, anlage_id, jahr)
    investitionen = b.investitionen
    pvgis_prognose, pvgis_by_month = await _pvgis_monatswerte(db, anlage_id)
    fakten, fakten_by_ym, _ust_saetze, _ust_monate = await _fakten_und_ust(
        db, anlage, anlage_id, jahr, investitionen, ist_gesamtzeitraum,
    )
    # N-693: der Kopf-Tarif braucht die Monate des Berichts — er steht deshalb hinter den Fakten (bis 12.10.2026
    # Abschnitt 2 vor allen anderen, als Handquery „jüngster Eintrag").
    tarif_zeitraeume = await _strompreis_kopf(db, anlage_id, fakten, jahr)
    alle_jahre, start_jahr, end_jahr = await _berichtsjahre(db, anlage, anlage_id, jahr, ist_gesamtzeitraum)
    s = _fakten_summen(fakten)
    t = await _monats_tabelle(
        db, anlage, anlage_id, jahr, investitionen, alle_jahre, fakten_by_ym, pvgis_by_month,
        _ust_saetze, _ust_monate, ist_gesamtzeitraum,
    )
    k = _finanz_kpis(anlage, jahr, investitionen, fakten, s, t)
    rf = await _rendite_und_fortschritt(db, anlage_id, jahr)
    co2_pv, co2_wp, co2_emob, co2_gesamt = _co2_bilanz(investitionen, fakten, t.zeilen_fakten, b, s)
    g = _geraete_kennzahlen(investitionen, fakten, b, s)
    wp_starts_summe, wp_betriebsstunden_summe, wp_laufzeit_pro_start = await _wp_zaehler(
        db, anlage_id, jahr, investitionen, b.hat_waermepumpe,
    )
    sv = await _string_vergleich(
        db, anlage, anlage_id, jahr, investitionen, alle_jahre, pvgis_prognose, ist_gesamtzeitraum,
    )
    chart_pv, chart_fluss, chart_autarkie = _charts(t.monats_zeilen, ist_gesamtzeitraum)

    # ── 12. Kontext-Dict ────────────────────────────────────────────────
    return {
        "erzeugt_am": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "ist_gesamtzeitraum": ist_gesamtzeitraum,
        "jahr": jahr,
        "start_jahr": start_jahr,
        "end_jahr": end_jahr,
        "zeitraum_label": (
            f"Gesamtzeitraum {start_jahr}–{end_jahr}"
            if ist_gesamtzeitraum else f"Jahresbericht {jahr}"
        ),
        "anlage": {
            "name": anlage.anlagenname,
            "leistung_kwp": anlage.leistung_kwp,
            "installationsdatum": anlage.installationsdatum,
            "mastr_id": anlage.mastr_id,
            "standort_plz": anlage.standort_plz,
            "standort_ort": anlage.standort_ort,
            "standort_strasse": anlage.standort_strasse,
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
        },
        "tarif": _kontext_tarif(tarif_zeitraeume),
        "kpis": {
            "pv_erzeugung_kwh": t.pv_gesamt,
            "eigenverbrauch_kwh": t.ev_gesamt,
            "abgabe_dritte_kwh": s.abgabe_gesamt if s.abgabe_gesamt > 0 else None,
            "einspeisung_kwh": t.einsp_gesamt,
            "netzbezug_kwh": t.netz_gesamt,
            "gesamtverbrauch_kwh": k.gesamtverbrauch,
            "autarkie_prozent": k.autarkie_jahr,
            "ev_quote_prozent": k.ev_quote,
            "spezifischer_ertrag": k.spez_ertrag_jahr,
            "einspeise_erloes_euro": k.einspeise_erloes,
            "ev_ersparnis_euro": k.ev_ersparnis,
            # N-588 (P15): die bewertete Menge hinter `ev_ersparnis_euro` und der Grund nicht bewerteter Verluste.
            "eigenverbrauch_ohne_verluste_kwh": k.finanz.eigenverbrauch_ohne_verluste_kwh,
            "wandlungsverluste_bewertet_kwh": k.finanz.wandlungsverluste_kwh,
            "verluste_grund": verluste_grund_zeitraum(
                (f.erzeugung.wandlungsverluste_kwh, f.erzeugung.verluste_grund) for f in t.zeilen_fakten),
            "sonstige_netto_euro": k.sonstige_netto_gesamt,
            "dienstliche_ladekosten_euro": k.dienstliche_ladekosten_gesamt,
            "dienstliche_ladekosten_hinweis": DIENSTLICHE_LADEKOSTEN_HINWEIS,
            "netto_ertrag_euro": k.netto_ertrag,
            "betriebskosten_zeitraum_euro": k.betriebskosten_zeitraum,
            "netto_nach_bk_euro": k.netto_nach_bk,
            "investition_gesamt_euro": k.investition_gesamt,
            # N-731 (12.10.2026, Entscheid Master): die Zeile „Investition Mehrkosten" nennt den Rendite-Nenner — die
            # Mehrkosten der bis 31.12. angeschafften Investitionen, Stillgelegte eingeschlossen (Cockpit → Übersicht,
            # N-720) — und ist so beschriftet. Bis dahin zählte sie nur die im Jahr aktiven (`aktiv_im_jahr`), und die
            # Rendite darunter teilte durch eine andere Zahl (GM Z1 2025: 120 000 gegen 130 000 €).
            "investition_mehrkosten_euro": rf.rendite_nenner_euro,
            "rendite_prozent": rf.rendite,
            "rendite_nenner_euro": rf.rendite_nenner_euro,
            "rendite_wp_ersparnis_euro": rf.wp_ersparnis_euro,
            "rendite_emob_ersparnis_euro": rf.emob_ersparnis_euro,
            "amortisation_prozent": rf.amortisation_pct,
            "amortisation_kapitaleinsatz_euro": rf.kapitaleinsatz_euro,
        },
        "speicher": {
            "vorhanden": b.hat_speicher,
            "kapazitaet_kwh": b.speicher_kapazitaet,
            "ladung_kwh": s.speicher_ladung,
            "entladung_kwh": s.speicher_entladung,
            "vollzyklen": g.speicher_zyklen,
            "effizienz_prozent": g.speicher_eff,
        },
        "waermepumpe": _kontext_waermepumpe(
            b.hat_waermepumpe, fakten, s, g, wp_starts_summe, wp_betriebsstunden_summe, wp_laufzeit_pro_start,
        ),
        "emob": {
            "vorhanden": b.hat_emobilitaet,
            "km": s.emob_km,
            "ladung_kwh": s.emob_ladung,
            "ladung_pv_kwh": s.emob_pv,
            "ladung_netz_kwh": s.emob_netz,
            "v2h_kwh": s.emob_v2h,
            "pv_anteil_prozent": g.emob_pv_anteil,
        },
        "bkw": {"vorhanden": b.hat_bkw},
        "co2": {
            "pv_kg": co2_pv,
            "wp_kg": co2_wp,
            "emob_kg": co2_emob,
            "gesamt_kg": co2_gesamt,
        },
        "monats_zeilen": t.monats_zeilen,
        "string_vergleiche": sv.string_vergleiche,
        "string_vergleich_monate_zeitraum": sv.monate_zeitraum,
        "string_vergleich_teilzeitraum": sv.teilzeitraum,
        "string_vergleich_verteilt": sv.verteilt,
        "investitionen": _kontext_investitionen(investitionen, b.inv_by_id),
        "charts": {
            "pv_erzeugung": chart_pv,
            "energie_fluss": chart_fluss,
            "autarkie": chart_autarkie,
        },
    }


@dataclass
class _TarifZeitraum:
    """Ein Abschnitt des Berichtszeitraums mit demselben Allgemeintarif (oder ohne Tarif)."""

    tarif: Optional[object]
    von: tuple[int, int]
    bis: tuple[int, int]


async def _strompreis_kopf(db: AsyncSession, anlage_id: int, fakten, jahr: Optional[int]) -> list[_TarifZeitraum]:
    """Abschnitt 2 — die Allgemeintarife im Berichtskopf: je Monat des Berichts der Tarif seines Stichtags (P8).

    N-693 (12.10.2026): dieselbe Auflösung wie die Monats-Fakten, mit denen jede Zeile des Berichts rechnet
    (`monats_fakten/tarif.py::_lade_tarif`: `lade_tarife_fuer_anlage(target_date=Monatserster)["allgemein"]`; hier
    über `lade_tarife_je_stichtag`, das dieselbe Regel `tarife_zum_stichtag` für alle Monate mit EINER Abfrage
    anwendet). Aufeinanderfolgende Monate mit demselben Tarif bilden einen Zeitraum; ein Monat ohne gültigen Tarif
    rechnet mit der Vorbelegung und steht als eigener Zeitraum da.

    ⛔ Bis dahin stand hier eine Handquery „jüngster Eintrag" ohne `verwendung` und ohne Stichtag: der Kopf nannte
    einen WP-, Wallbox- oder künftigen Tarif, und ein Bericht 2024 druckte den Tarif ab 10/2025. Gerechnet wurde mit
    dem Kopf nie — die Monatszeilen lösen ihren Tarif seit #326 selbst auf.

    Ohne Monate (leerer Bericht) gilt der Stichtag des Berichtsjahres: Dezember des Jahres, höchstens der laufende
    Monat; im Gesamtzeitraum der laufende Monat.
    """
    from backend.api.routes.strompreise import lade_tarife_je_stichtag

    monate = sorted({f.schluessel for f in fakten})
    if not monate:
        heute = date.today()
        laufend = (heute.year, heute.month)
        monate = [min((jahr, 12), laufend) if jahr is not None else laufend]
    tarife_je = await lade_tarife_je_stichtag(db, anlage_id, [date(j, m, 1) for j, m in monate])

    zeitraeume: list[_TarifZeitraum] = []
    for j, m in monate:
        tarif = tarife_je[date(j, m, 1)]["allgemein"]
        letzter = zeitraeume[-1] if zeitraeume else None
        if letzter is not None and _tarif_id(letzter.tarif) == _tarif_id(tarif):
            letzter.bis = (j, m)
        else:
            zeitraeume.append(_TarifZeitraum(tarif=tarif, von=(j, m), bis=(j, m)))
    return zeitraeume


def _tarif_id(tarif) -> Optional[int]:
    return tarif.id if tarif is not None else None


def _kwp_im_monat(investitionen, anlage, j: Optional[int], m: int) -> float:
    """Nenner der spezifischen Erträge — Σ der am Monatsende aktiven Erzeuger.

    F-58: Bis 2026-08-24 stand hier der gepflegte `anlage.leistung_kwp`.
    Der ist ein zeitloser Skalar und kannte weder Zubau noch Stilllegung;
    seit dem Wegfall des Summenvergleichs (N-76 Stufe 1) hielt ihn zudem
    nichts mehr gegen die Investitionen. Der Referenzwert bleibt Fallback
    für Bestände ganz ohne gepflegte Erzeuger.
    """
    # `j is None` = Gesamtzeitraum-Bericht (kein Jahr gewählt) — dann
    # gilt der heutige Bestand, wie beim `stichtag` der Speicher-Kapazität
    # weiter unten.
    tag = date(j, m, monthrange(j, m)[1]) if j is not None else date.today()
    return anlagen_kwp(
        investitionen, tag, mit_bkw=True, referenzwert=anlage.leistung_kwp,
    )


@dataclass
class _Bestand:
    """Abschnitt 3 — die Investitionen des Berichts und was der Kopf aus ihnen liest."""

    investitionen: list
    inv_by_id: dict
    hat_speicher: bool
    hat_waermepumpe: bool
    hat_emobilitaet: bool
    hat_bkw: bool
    speicher_kapazitaet: float


async def _bestand(db: AsyncSession, anlage, anlage_id: int, jahr: Optional[int]) -> _Bestand:
    """Abschnitt 3 — Investitionen laden, Typ-Kennzeichen, Speicher-Kapazität am Stichtag."""
    # ── 3. Investitionen ────────────────────────────────────────────────
    # KEIN aktiv-Filter (Issue #123): Jahresbericht ist historisch, spätere
    # Stilllegung darf Komponenten-Daten nicht rückwirkend entfernen. Wenn ein
    # Jahr ausgewählt ist, wird zusätzlich auf den Einsatzzeitraum gefiltert.
    from backend.utils.investition_filter import aktiv_im_jahr
    inv_stmt = select(Investition).where(Investition.anlage_id == anlage_id)
    if jahr is not None:
        inv_stmt = inv_stmt.where(aktiv_im_jahr(jahr))
    res = await db.execute(inv_stmt)
    investitionen = res.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    # DI-3: Dienstwagen zählen nicht als (private) E-Mobilität — konsistent zum
    # Cockpit (`hat_emobilitaet` schließt dienstliche Fahrzeuge aus).
    hat_emobilitaet = any(
        i.typ in ("e-auto", "wallbox") and not ist_dienstlich(i)
        for i in investitionen
    )
    hat_bkw = any(i.typ == "balkonkraftwerk" for i in investitionen)

    # BRUTTO-Kapazität über den SoT-Helper (ADR-002/P3-a). `or 0`, weil ein
    # ungepflegter Speicher `None` liefert und die Summe der übrigen weiterläuft.
    # F-24: Stichtag statt Summe über alles. `aktiv_im_jahr` oben lässt im
    # **Wechseljahr** beide Geräte durch (altes bis Juni, neues ab Juli) — und
    # ohne Jahresfilter ohnehin jedes je erfasste. Der Bericht nennt aber die
    # Kapazität der Anlage, nicht die Summe ihrer Gerätegeschichte: 15,4 + 30,8
    # = 46,2 statt 30,8 kWh (an einer Kopie des Dev-Bestands gemessen).
    # Stichtag ist das Jahresende des Berichtsjahres bzw. heute.
    stichtag = date(jahr, 12, 31) if jahr is not None else date.today()
    speicher_kapazitaet = 0.0
    for inv in investitionen:
        if inv.typ == "speicher" and inv.ist_aktiv_an(stichtag):
            speicher_kapazitaet += get_speicher_kapazitaet_kwh(inv) or 0
    return _Bestand(
        investitionen=investitionen, inv_by_id=inv_by_id, hat_speicher=hat_speicher,
        hat_waermepumpe=hat_waermepumpe, hat_emobilitaet=hat_emobilitaet, hat_bkw=hat_bkw,
        speicher_kapazitaet=speicher_kapazitaet,
    )


async def _pvgis_monatswerte(db: AsyncSession, anlage_id: int):
    """Abschnitt 4 — die aktive Prognose und ihre Monatswerte je Kalendermonat."""
    # ── 4. PVGIS-Prognose (die aktive) ──────────────────────────────────
    # Auswahlregel über den SoT `services/prognose_auswahl.py` — dieselbe
    # Funktion wie Cockpit, Aussichten, Energieprofil und HA-Export nutzen.
    # Der Monatswert-Key heißt `e_m` (so schreibt ihn `api/routes/pvgis.py`).
    pvgis_prognose = await lade_aktive_prognose(db, anlage_id)
    pvgis_by_month: dict[int, float] = {}
    if pvgis_prognose and pvgis_prognose.monatswerte:
        for mw in pvgis_prognose.monatswerte:
            pvgis_by_month[mw.get("monat", 0)] = mw.get("e_m", 0) or 0
    return pvgis_prognose, pvgis_by_month


async def _fakten_und_ust(
    db: AsyncSession, anlage, anlage_id: int, jahr: Optional[int], investitionen, ist_gesamtzeitraum: bool,
):
    """Abschnitt 5 — die Monats-Fakten des Zeitraums und die USt-Sätze je Kalenderjahr samt ihren Monaten."""
    # ── 5. Monats-Fakten (ADR-002/P10) ──────────────────────────────────
    # Die EINE Aufbereitung der Monatszeile: PV nach P7 aufgelöst (Messwerte +
    # Anlagen-Aggregat als Lückenfüller), Zeitfilter (#236), Dienstwagen-Filter
    # und Monatstarif stecken darin. Bis 2026-07-31 faltete dieser Builder die
    # IMD-Zeilen selbst und las die PV roh aus
    # `verbrauch_daten["pv_erzeugung_kwh"]` — bei einer Anlage, die nur das
    # Anlagen-Aggregat pflegt, stand deshalb 0 kWh und 32,00 € statt 212,00 € im
    # Bericht (Befund F-5 der Drift-Inventur, `docs/KONZEPT-MONATS-FAKTEN.md`).
    fakten = await lade_monats_fakten(
        db, anlage_id,
        von=None if ist_gesamtzeitraum else (jahr, 1),
        bis=None if ist_gesamtzeitraum else (jahr, 12),
    )
    fakten_by_ym = {f.schluessel: f for f in fakten}
    # USt auf den Eigenverbrauch — der EINE Eingang (`services/ust_satz.py`, G1, 03.10.2026): Satz je Kalenderjahr,
    # angewandt auf die Monate der Grundgesamtheit (abgeschlossen, Erzeuger aktiv). So ist Σ der Monatszeilen der
    # KPI-Betrag (E6a der Vorlage Ergebnisgrößen) — vorher fehlte die USt in den Zeilen ganz.
    _ust_saetze = {_j: ust_satz_des_jahres(anlage, investitionen, fakten, _j) for _j in sorted({f.jahr for f in fakten})}
    _ust_monate = {f.schluessel for _j in _ust_saetze for f in ust_grundgesamtheit(fakten, _j)}
    return fakten, fakten_by_ym, _ust_saetze, _ust_monate


async def _berichtsjahre(
    db: AsyncSession, anlage, anlage_id: int, jahr: Optional[int], ist_gesamtzeitraum: bool,
):
    """Abschnitt 6 — die Jahre des Berichts aus den Zählerzeilen: (alle_jahre, start_jahr, end_jahr)."""
    # ── 6. Monatsdaten (Zähler-Werte) ───────────────────────────────────
    if ist_gesamtzeitraum:
        res = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )
    else:
        res = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .where(Monatsdaten.jahr == jahr)
            .order_by(Monatsdaten.monat)
        )
    monatsdaten_list = list(res.scalars().all())

    if ist_gesamtzeitraum and monatsdaten_list:
        alle_jahre = sorted({m.jahr for m in monatsdaten_list})
    elif ist_gesamtzeitraum:
        start_jahr = anlage.installationsdatum.year if anlage.installationsdatum else datetime.now().year - 1
        alle_jahre = list(range(start_jahr, datetime.now().year + 1))
    else:
        alle_jahre = [jahr]
    start_jahr = alle_jahre[0]
    end_jahr = alle_jahre[-1]

    md_by_year_month: dict[tuple[int, int], Monatsdaten] = {
        (m.jahr, m.monat): m for m in monatsdaten_list
    }
    return alle_jahre, start_jahr, end_jahr


@dataclass
class _FaktenSummen:
    """Abschnitte 6/7 — die Summen über die Monats-Fakten des Zeitraums (ohne die Monatstabelle)."""

    sonstige_by_ym: dict
    erzeuger_erloes_gesamt: float
    speicher_ladung: float
    speicher_entladung: float
    wp_waerme: float
    abgabe_gesamt: float
    wp_heizung: Optional[float]
    wp_warmwasser: Optional[float]
    wp_strom: float
    wp_waerme_mit_ersatz: float
    wp_strom_mit_ersatz: float
    emob_km: float
    emob_v2h: float
    emob_ladung: float
    emob_pv: float
    emob_netz: float


def _fakten_summen(fakten) -> _FaktenSummen:
    """Abschnitte 6/7 — Sonstiges, Speicher, Wärmepumpe und E-Mobilität über den Zeitraum."""
    # PV-Erzeugung pro Jahr/Monat (Module + BKW, Cockpit-Konvention) — aus den
    # Monats-Fakten.
    #
    # ADR-002/P9: Beim Balkonkraftwerk entscheidet `bkw_finanz_beitrag` je
    # (BKW, Monat), ob die Erzeugung hier einfließt oder — mangels Erfassung —
    # der gemessene Eigenverbrauch als Rest-Term in die Finanz-Zeile geht.
    # Dieser Builder übergab den Rest-Term bisher gar nicht: ein BKW, das nur
    # `eigenverbrauch_kwh` führt, fehlte im Jahresbericht komplett, während
    # Cockpit und Aussichten es (unterschiedlich) berücksichtigten.
    bkw_rest_ev_by_ym = {f.schluessel: f.bkw.rest_eigenverbrauch_kwh for f in fakten}

    # N93: Sonstige Erzeuger (z. B. Mini-BHKW) speisen hinter DENSELBEN
    # Hauszähler — ihre Erzeugung gehört in die EV-/Autarkie-Ableitung, sonst
    # drückt der gemessene Einspeise-Zähler die Bilanz still zu niedrig.
    # **Bewusst getrennt von der PV (`fakt.erzeugung.pv_kwh`):** die PV-EIGENEN Kennzahlen
    # (spezifischer Ertrag, SOLL/IST, String-Vergleich) bleiben rein PV — ein
    # Brennstoff-Erzeuger im PV-Nenner wäre ein stiller Rechenfehler. Genau
    # deshalb trägt die Schicht beide Summen getrennt (`pv_kwh` vs.
    # `hinter_zaehler_kwh`).
    sonstige_erz_by_ym = {
        f.schluessel: f.erzeugung.sonstige_erzeuger_kwh for f in fakten
    }

    # #326: Sonstige Erträge/Ausgaben pro Jahr/Monat — damit die Monats-
    # Ertragsspalte deckungsgleich mit dem Jahres-Netto ist (rilmor-mhrs:
    # Dez 2022 musste negativ werden, Monatszeilen müssen auf den Summary
    # aufgehen). Die Schicht faltet dafür ALLE sichtbaren IMD-Positionen (#310:
    # unabhängig vom Typ) plus die Basis-Positionen der Monatsdaten-Zeile
    # (G19-1) — beides zusammen ergibt `sonstiges.netto_euro`.
    sonstige_by_ym = {f.schluessel: f.sonstiges.netto_euro for f in fakten}
    # Konzept §9 Weg 2: gepflegte Erlöse einzelner Erzeuger (eigener
    # Einspeisetarif) — eigener Summand, kein Teil des Sonstige-Netto.
    erzeuger_erloes_gesamt = sum(f.sonstiges.einspeise_erloes_euro for f in fakten)

    # ── 7. Aggregate Wärmepumpe / E-Mob / Speicher ──────────────────────
    speicher_ladung_by_ym = {f.schluessel: f.speicher.ladung_kwh for f in fakten}
    speicher_entladung_by_ym = {
        f.schluessel: f.speicher.entladung_kwh for f in fakten
    }
    v2h_by_ym = {f.schluessel: f.emob.v2h_entladung_kwh for f in fakten}
    speicher_ladung = sum(speicher_ladung_by_ym.values())
    speicher_entladung = sum(speicher_entladung_by_ym.values())

    wp_waerme = sum(f.wp.waerme_kwh for f in fakten)
    # §9.2 — Abgabe an Dritte über den Berichtszeitraum (kein Eigenverbrauch).
    abgabe_gesamt = sum(f.sonstiges.abgabe_kwh for f in fakten)
    # N-673: eine ungemessene Achse ist „keine Angabe" (None) — die Summe gibt es nur, wenn ein Monat sie misst.
    wp_heizung = (sum(f.wp.heizung_kwh or 0.0 for f in fakten)
                  if any(f.wp.heizung_kwh is not None for f in fakten) else None)
    wp_warmwasser = (sum(f.wp.warmwasser_kwh or 0.0 for f in fakten)
                     if any(f.wp.warmwasser_kwh is not None for f in fakten) else None)
    wp_strom = sum(f.wp.strom_kwh for f in fakten)
    # N-256: die Grundmenge des fossilen Vergleichs — nur Geräte mit Ersatz.
    wp_waerme_mit_ersatz = sum(f.wp.waerme_mit_ersatz_kwh for f in fakten)
    wp_strom_mit_ersatz = sum(f.wp.strom_mit_ersatz_kwh for f in fakten)
    # #263 K-2 (Konzept §3.5): abgeleitete Wärme trägt keine JAZ.
    wp_waerme_abgeleitet = sum(f.wp.waerme_abgeleitet_kwh for f in fakten)
    # DI-3: Dienstwagen zählen NICHT in km/CO₂/Heimladung/V2H des Berichts —
    # der Filter sitzt in der Schicht (`EmobFakten`), nicht mehr hier.
    emob_km = sum(f.emob.km for f in fakten)
    emob_v2h = sum(v2h_by_ym.values())

    # E-Mob-Heimladung: die Summe der Monats-Entscheide der Schicht (N-555,
    # Konzept Regel 1: „Ein Jahr ist die Summe seiner Monate"). Hier stand bis
    # 25.09.2026 EINE Quellenwahl über den ganzen Berichtszeitraum — eine Wallbox,
    # die erst ab Juli misst, verdrängte damit die gemessenen Monate davor.
    # Doppelzählung bei evcc-Setups (derselbe Fluss auf E-Auto UND Wallbox)
    # schließt die Monats-Entscheidung genauso aus: je Monat genau eine Quelle.
    emob_ladung = sum(f.emob.ladung_kwh for f in fakten)
    emob_pv = sum(f.emob.ladung_pv_kwh for f in fakten)
    emob_netz = sum(f.emob.ladung_netz_kwh for f in fakten)
    return _FaktenSummen(
        sonstige_by_ym=sonstige_by_ym, erzeuger_erloes_gesamt=erzeuger_erloes_gesamt,
        speicher_ladung=speicher_ladung, speicher_entladung=speicher_entladung, wp_waerme=wp_waerme,
        abgabe_gesamt=abgabe_gesamt, wp_heizung=wp_heizung, wp_warmwasser=wp_warmwasser, wp_strom=wp_strom,
        wp_waerme_mit_ersatz=wp_waerme_mit_ersatz, wp_strom_mit_ersatz=wp_strom_mit_ersatz, emob_km=emob_km,
        emob_v2h=emob_v2h, emob_ladung=emob_ladung, emob_pv=emob_pv, emob_netz=emob_netz,
    )


@dataclass
class _Tabelle:
    """Abschnitt 8 — die Monatszeilen, ihre Finanz-Zeilen und die Summen, die sie tragen."""

    monats_zeilen: list
    finanz_zeilen: list
    zeilen_fakten: list
    pv_gesamt: float
    erz_bilanz_gesamt: float
    einsp_gesamt: float
    netz_gesamt: float
    ev_gesamt: float


async def _monats_tabelle(
    db: AsyncSession, anlage, anlage_id: int, jahr: Optional[int], investitionen, alle_jahre, fakten_by_ym,
    pvgis_by_month, _ust_saetze, _ust_monate, ist_gesamtzeitraum: bool,
) -> _Tabelle:
    """Abschnitt 8 — je Monat eine Zeile (Einzeljahr: alle zwölf, Gesamtzeitraum: die mit Fakten)."""
    pv_gesamt = 0.0
    erz_bilanz_gesamt = 0.0  # N93: Σ Erzeugung hinter dem Zähler (PV + BHKW)
    einsp_gesamt = 0.0
    netz_gesamt = 0.0
    ev_gesamt = 0.0
    # N-588: die Monate, die die Monatstabelle trägt — ihr CO₂-PV kommt je Monat aus dem Kanon (unten, Abschnitt 9).
    zeilen_fakten: list = []

    # ── 8. Monats-Tabelle aufbauen ──────────────────────────────────────
    # #326: Tarif PRO MONAT (historische Tarife) statt Einheitstarif — die
    # FinanzMonatsZeile wird über den gemeinsamen Builder `baue_finanz_zeile`
    # gebaut (einzige erlaubte Konstruktions-Stelle, Konformitäts-Wächter), damit
    # Cockpit/Auswertungen/HA-Export/Jahresbericht garantiert dieselben Eingaben
    # nutzen. Der Builder löst den Monatstarif auf; das Display liest Preis/Erlös
    # aus der zurückgegebenen Zeile zurück (single source).
    from backend.services.finanz_zeilen import baue_finanz_zeile

    _tarif_cache: dict[date, dict] = {}
    monats_zeilen: list[dict] = []
    finanz_zeilen: list[FinanzMonatsZeile] = []

    def _leere_zeile(j: int, m: int) -> dict:
        """Anzeige-Zeile für einen Monat ganz ohne Spur (kein Zähler, kein IMD).

        Sie trägt nur den PVGIS-SOLL-Wert; ohne sie fehlten in der Jahres-
        tabelle Monate, in denen noch nichts erfasst ist. In den Finanz-Zeilen
        taucht sie nicht auf — sie wäre dort eine Zeile aus lauter Nullen.

        N-650 (10.10.2026): die Messgrößen stehen auf ``None`` statt 0 — die
        Tabelle druckt dafür „–" (`formatierung.LEER`), nicht „0 kWh", „0,0 %"
        und „0,00 €". Eine 0 ist eine Aussage (ADR-002/P4), ein Monat ohne
        Erfassung keine. Die Jahressummen laufen über die Fakten (`_zeile_fuer`),
        nicht über diese Zeile, und bleiben unverändert; die Diagramme lesen
        ``None`` wie bisher die 0 (`charts.py`: ``v or 0``).
        """
        return {
            "jahr": j, "monat": m,
            "monat_name": f"{MONATSNAMEN[m]} {j}" if ist_gesamtzeitraum else MONATSNAMEN[m],
            "pv_erzeugung_kwh": None, "pvgis_prognose_kwh": pvgis_by_month.get(m, 0),
            "eigenverbrauch_kwh": None, "einspeisung_kwh": None, "netzbezug_kwh": None,
            "autarkie_prozent": None, "spezifischer_ertrag": None,
            "einsp_erloes_euro": None, "ev_ersparnis_euro": None,
            "sonstige_netto_euro": None, "netto_ertrag_euro": None,
        }

    async def _zeile_fuer(fakt) -> dict:
        nonlocal pv_gesamt, erz_bilanz_gesamt, einsp_gesamt, netz_gesamt, ev_gesamt
        j, m = fakt.schluessel
        pv = fakt.erzeugung.pv_kwh
        einsp = fakt.zaehler.einspeisung_kwh
        netz = fakt.zaehler.netzbezug_kwh
        # #304: Eigenverbrauch über den SoT-Helper (PV + Speicher + V2H) statt
        # der naiven Formel PV − Einspeisung, die den Speicher ignorierte —
        # deckungsgleich mit Cockpit/HA-Export/Aussichten. N93: Bilanz-Eingang
        # sind ALLE Erzeuger hinter dem Zähler (v3.45.4), nicht nur die PV;
        # `pv` selbst bleibt rein PV und trägt weiter die PV-Kennzahlen.
        erzeugung_bilanz = fakt.erzeugung.hinter_zaehler_kwh
        ev = fakt.kennzahlen.eigenverbrauch_kwh
        gesamt = ev + netz
        autarkie = autarkie_prozent(ev, gesamt)
        # F-58: Nenner ist die Σ der im Monat aktiven Erzeuger. `mit_bkw=True`,
        # weil `pv` hier `fakt.erzeugung.pv_kwh` ist — Module PLUS
        # Balkonkraftwerk (die PV-Achse laut `monats_fakten`).
        spez = spezifischer_ertrag_kwh_kwp(pv, _kwp_im_monat(investitionen, anlage, fakt.jahr, fakt.monat)) or 0.0
        zeile = await baue_finanz_zeile(
            db, anlage_id, finanz_zeile_eingabe(fakt), tarif_cache=_tarif_cache
        )
        finanz_zeilen.append(zeile)
        # Display aus der Zeile — über DENSELBEN Aggregat-Helper wie der KPI (eine Zeile), damit Σ Zeilen = KPI auch
        # bei gemessenen Stundenpreisen gilt (EV-Ersparnis mit dem EV-gewichteten Preis, A-2). Bis 03.10.2026 rechnete
        # die Zeile `EV × Netzbezugspreis` selbst — bitgleich, solange es keinen eigenen EV-Preis gibt.
        _fz = berechne_finanz_aggregat([zeile])
        einsp_eur = _fz.einspeise_erloes_euro
        ev_eur = _fz.ev_ersparnis_euro
        sonstige_eur = fakt.sonstiges.netto_euro
        _satz = _ust_saetze.get(j)
        _ust_m = (
            # N-588 (F4): die USt bemisst die entnommene Menge — der Eigenverbrauch ohne Wandlungsverluste.
            ust_anteil_euro(_fz.eigenverbrauch_ohne_verluste_kwh, _satz.euro_je_kwh)
            if _satz is not None and (j, m) in _ust_monate else None
        )
        # Netto-Ertrag der Zeile = Stufe 1 der Ergebnis-Leiter (mit BKW-Rest, Erlös eigener Satz, Sonstigem, USt) —
        # bis 03.10.2026 `einsp + ev + sonstige`: Σ der Zeilen wich vom KPI darunter um USt, BKW-Rest und Erzeuger ab.
        _netto_m = berechne_ergebnis(ErgebnisEingang(
            einspeise_erloes=einsp_eur, ev_ersparnis=ev_eur, bkw_rest_ersparnis=_fz.bkw_ersparnis_euro,
            erzeuger_erloes=fakt.sonstiges.einspeise_erloes_euro, sonstige_netto=sonstige_eur,
            # N-633: derselbe Posten wie Cockpit → Monat und Übersicht (Monats-Fakten).
            dienstliche_ladekosten=fakt.emob.dienstliche_ladekosten_euro, ust_anteil=_ust_m,
        )).netto_ertrag
        pv_gesamt += pv
        erz_bilanz_gesamt += erzeugung_bilanz
        einsp_gesamt += einsp
        netz_gesamt += netz
        ev_gesamt += ev
        zeilen_fakten.append(fakt)
        return {
            "jahr": j,
            "monat": m,
            "monat_name": f"{MONATSNAMEN[m]} {j}" if ist_gesamtzeitraum else MONATSNAMEN[m],
            "pv_erzeugung_kwh": pv,
            "pvgis_prognose_kwh": pvgis_by_month.get(m, 0),
            "eigenverbrauch_kwh": ev,
            "einspeisung_kwh": einsp,
            "netzbezug_kwh": netz,
            "autarkie_prozent": autarkie,
            "spezifischer_ertrag": spez,
            "einsp_erloes_euro": einsp_eur,
            "ev_ersparnis_euro": ev_eur,
            "sonstige_netto_euro": sonstige_eur,
            "netto_ertrag_euro": _netto_m,
        }

    if ist_gesamtzeitraum:
        for j in alle_jahre:
            for m in range(1, 13):
                fakt = fakten_by_ym.get((j, m))
                if fakt is not None:
                    monats_zeilen.append(await _zeile_fuer(fakt))
    else:
        for m in range(1, 13):
            fakt = fakten_by_ym.get((jahr, m))
            monats_zeilen.append(
                await _zeile_fuer(fakt) if fakt is not None else _leere_zeile(jahr, m)
            )
    return _Tabelle(
        monats_zeilen=monats_zeilen, finanz_zeilen=finanz_zeilen, zeilen_fakten=zeilen_fakten,
        pv_gesamt=pv_gesamt, erz_bilanz_gesamt=erz_bilanz_gesamt, einsp_gesamt=einsp_gesamt,
        netz_gesamt=netz_gesamt, ev_gesamt=ev_gesamt,
    )


@dataclass
class _FinanzKpis:
    """Abschnitt 9 — Energie-Kennzahlen des Zeitraums, Finanz-Summary und Ergebnis-Leiter bis zur Amortisation."""

    gesamtverbrauch: float
    autarkie_jahr: Optional[float]
    ev_quote: Optional[float]
    spez_ertrag_jahr: float
    sonstige_netto_gesamt: float
    dienstliche_ladekosten_gesamt: float
    finanz: object
    einspeise_erloes: float
    ev_ersparnis: float
    investition_gesamt: float
    netto_ertrag: float
    betriebskosten_zeitraum: float
    netto_nach_bk: float


def _finanz_kpis(anlage, jahr: Optional[int], investitionen, fakten, s: _FaktenSummen, t: _Tabelle) -> _FinanzKpis:
    """Abschnitt 9 (erster Teil) — Jahres-KPIs und Finanzen aus den Monatszeilen und den Fakten."""
    ev_gesamt, netz_gesamt, erz_bilanz_gesamt, pv_gesamt = t.ev_gesamt, t.netz_gesamt, t.erz_bilanz_gesamt, t.pv_gesamt
    # ── 9. Jahres-KPIs / Finanzen / CO₂ ─────────────────────────────────
    gesamtverbrauch = ev_gesamt + netz_gesamt
    autarkie_jahr = autarkie_prozent(ev_gesamt, gesamtverbrauch)
    # N93: Nenner der EV-Quote ist die Erzeugung hinter dem Zähler — dieselbe
    # Größe, aus der der Eigenverbrauch oben abgeleitet wurde. Mit `pv_gesamt`
    # als Nenner stünde bei einem BHKW ein zu großer Zähler über einem zu
    # kleinen Nenner (Quote > 100 %, gedeckelt = still falsch).
    ev_quote = eigenverbrauchsquote_prozent(ev_gesamt, erz_bilanz_gesamt)  # cappt 100 %
    # F-58: wie die Monatszeilen — Σ der Erzeuger statt des gepflegten
    # Referenzwerts. Stichtag Jahresende, damit ein im Jahr zugebauter String
    # zählt und ein stillgelegter nicht mehr.
    spez_ertrag_jahr = spezifischer_ertrag_kwh_kwp(
        pv_gesamt, _kwp_im_monat(investitionen, anlage, jahr, 12),
    ) or 0.0

    # #326: Sonstige Erträge/Ausgaben (manuell gepflegt) gehören in den
    # Netto-Ertrag — exakt wie Cockpit/Auswertungen. Die Monats-Fakten sind
    # bereits auf den Einsatzzeitraum (ist_aktiv_im_monat, #236) gefiltert;
    # `sonstiges.netto_euro` faltet IMD- und G19-1-Basis-Positionen — per
    # Konstruktion deckungsgleich mit den Monatszeilen.
    sonstige_netto_gesamt = sum(s.sonstige_by_ym.values())
    # N-633: dienstliche Ladekosten — eigener Posten der Leiter, nicht Teil der Sonstigen (Kapitaleinsatz, F-19).
    dienstliche_ladekosten_gesamt = sum(f.emob.dienstliche_ladekosten_euro for f in fakten)
    # #326: Finanz-Summary über den SoT-Helper = Σ der per-Monat-Zeilen (EV mit
    # Monats-Flexpreis + §51-bereinigter Einspeise-Erlös) + Sonstige.
    _finanz = berechne_finanz_aggregat(
        t.finanz_zeilen,
        sonstige_netto_euro=sonstige_netto_gesamt,
        erzeuger_erloes_euro=s.erzeuger_erloes_gesamt,
    )
    einspeise_erloes = _finanz.einspeise_erloes_euro
    ev_ersparnis = _finanz.ev_ersparnis_euro

    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    # N-136 → N-731 (12.10.2026): die Mehrkosten-ZEILE des Berichts ist der Rendite-Nenner der Übersicht
    # (`_rendite_und_fortschritt`, Layer-SoT `relevante_kosten_aus_investitionen` je Position geklemmt, bis 31.12.
    # angeschafft, Stillgelegte eingeschlossen) — keine zweite Summe hier über die im Jahr aktiven Investitionen.
    # Bis 2026-08-30 stand hier `Σ gesamt − Σ alternativ` ungeklemmt (N-136), bis 12.10.2026 der SoT über
    # `aktiv_im_jahr` (zwei „Mehrkosten" im selben PDF bei einer Stilllegung vor dem Jahr).

    # #326-Inventur Dimension 2: USt auf Eigenverbrauch bei Regelbesteuerung.
    # Cockpit und Aussichten ziehen sie seit jeher ab, der Bericht nicht — bei
    # Regelbesteuerung wies er den Netto-Ertrag deshalb um den USt-Betrag zu
    # hoch aus. Vorprüfung + Satz-Default liegen im SoT-Helper, damit die
    # Regel nicht zum vierten Mal als Kopie im Baum steht.
    #
    # N-130: `jahr=None` erzeugt hier den **Anlagenbericht** über den gesamten
    # Zeitraum — der Client bietet das als „Gesamtzeitraum" an. Dieser Builder
    # war damit von der Zeitraum-Kollaps-Klasse betroffen, entgegen der
    # Registerzeile („nicht den Jahresbericht, der ist per Jahr"). Jetzt je
    # Kalenderjahr; bei `jahr=<J>` bleibt genau ein Anteil übrig und die Zahl
    # ändert sich nur um die neue Bemessungsgrundlage und die Monats-Anteiligkeit.
    # N-129: Bemessungsgrundlage über den Layer-SoT statt `investition_gesamt`.
    # ⛔ Hier stand bis 2026-08-30: „`investition_mehrkosten` daneben bleibt
    # unberührt — es trägt die Rendite/Amortisation und ist die ungeklemmte
    # Form". Das war die **Abgrenzung des N-129-Auftrags**, keine fachliche
    # Entscheidung für die ungeklemmte Form — und sie hat den Befund N-136
    # dreiundzwanzig Tage lang als gewollt gelesen aussehen lassen. Beide
    # Größen kommen jetzt aus dem Layer (s. `investition_mehrkosten` oben).
    # G1 (03.10.2026): der Satz aus dem EINEN Eingang `services/ust_satz.py` — im Jahr aktive Investitionen für
    # Bemessung UND Betriebskosten (Regel 05.06.2026), Grundgesamtheit = abgeschlossene Monate mit aktivem Erzeuger,
    # Σ der Monats-Eigenverbräuche. Bis dahin: alle Investitionen, alle Fakten-Monate dieses Builders.
    ust_eigenverbrauch = ust_eigenverbrauch_zeitraum(anlage, investitionen, fakten)
    # Stufe 1 der Ergebnis-Leiter — dieselbe Funktion wie Übersicht, HA-Sensor und Cockpit → Monat/Jahr.
    netto_ertrag = berechne_ergebnis(ErgebnisEingang(
        einspeise_erloes=_finanz.einspeise_erloes_euro, ev_ersparnis=_finanz.ev_ersparnis_euro,
        bkw_rest_ersparnis=_finanz.bkw_ersparnis_euro, erzeuger_erloes=_finanz.erzeuger_erloes_euro,
        sonstige_netto=_finanz.sonstige_netto_euro, dienstliche_ladekosten=dienstliche_ladekosten_gesamt,
        ust_anteil=ust_eigenverbrauch,
    )).netto_ertrag

    # N-699 (12.10.2026): die Laufzeit-Regel N-228 aus dem Layer — jede Komponente über IHRE aktiven Monate des
    # Berichtszeitraums, dieselbe Funktion wie Cockpit → Monat/Jahr, Übersicht und Aussichten. Hier stand bis dahin
    # `Σ Jahresbeträge × Monatszeilen ÷ 12`: im Einzeljahr immer zwölf Zeilen (auch leere Monate), im Gesamtzeitraum
    # jede je erfasste Komponente über den ganzen Zeitraum — gemessen 120 statt 20 € (laufendes Jahr, zwei Monate),
    # 240 statt 120 € (Speicher ab Juli). Die Monate sind die der Monats-Fakten — dieselbe Menge wie die Übersicht.
    betriebskosten_zeitraum = betriebskosten_im_zeitraum(investitionen, {f.schluessel for f in fakten})
    netto_nach_bk = netto_ertrag - betriebskosten_zeitraum
    return _FinanzKpis(
        gesamtverbrauch=gesamtverbrauch, autarkie_jahr=autarkie_jahr, ev_quote=ev_quote,
        spez_ertrag_jahr=spez_ertrag_jahr, sonstige_netto_gesamt=sonstige_netto_gesamt,
        dienstliche_ladekosten_gesamt=dienstliche_ladekosten_gesamt, finanz=_finanz,
        einspeise_erloes=einspeise_erloes, ev_ersparnis=ev_ersparnis, investition_gesamt=investition_gesamt,
        netto_ertrag=netto_ertrag,
        betriebskosten_zeitraum=betriebskosten_zeitraum, netto_nach_bk=netto_nach_bk,
    )


@dataclass
class _RenditeFortschritt:
    """Abschnitt 9 (zweiter Teil) — Rendite wie Cockpit → Übersicht, Amortisations-Fortschritt wie Auswertungen → ROI."""

    rendite: Optional[float]
    rendite_nenner_euro: Optional[float]
    wp_ersparnis_euro: Optional[float]
    emob_ersparnis_euro: Optional[float]
    amortisation_pct: Optional[float]
    kapitaleinsatz_euro: Optional[float]


async def _rendite_und_fortschritt(
    db: AsyncSession, anlage_id: int, jahr: Optional[int],
) -> _RenditeFortschritt:
    """Abschnitt 9 (zweiter Teil) — die beiden Quoten des Berichts aus den Sichten, die sie definieren (N-699).

    * **Rendite** = ``get_cockpit_uebersicht(jahr)`` (Route-Aufruf aus einem Service wie ``services/jahres_aggregat.py``):
      Zähler Netto-Ertrag + WP- + E-Mobilitäts-Ersparnis − Betriebskosten des Zeitraums, Nenner die Mehrkosten — die
      WP- und E-Auto-Ersparnis kommen aus den Monats-Fakten der Übersicht, keine Kopie ihrer Periodenrechnung hier.
    * **Amortisations-Fortschritt** = ``get_finanz_prognose`` (Kachel in *Auswertungen → ROI*, Layer
      ``core/berechnungen/amortisation.py``): bisherige Erträge ÷ Kapitaleinsatz (F-19) — im Gesamtzeitraum bis heute,
      im Einzeljahr mit Stichtag 31.12. des Berichtsjahres.

    Bis 12.10.2026 waren beide Zeilen dieselbe Zahl ``(Netto − Betriebskosten) ÷ Mehrkosten`` — ohne WP- und
    E-Auto-Ersparnis im Zähler, deren Mehrkosten im Nenner standen (gemessen 15,09 statt 21,2 % mit E-Auto).

    Kann eine der beiden Sichten nicht rechnen, steht ihre Zeile als „–" (P4: nicht ermittelbar statt einer eigenen
    Zahl daneben) und der Grund im Log — der Bericht bricht deshalb nicht ab (wie ``services/jahres_aggregat.py`` mit
    der Übersicht). Gemessen 12.10.2026: ``get_finanz_prognose`` stürzt bei einer PVGIS-Prognose mit fehlendem
    Monatswert (``e_m``) ab (``finanz_prognose.py:97``), der Bericht rechnete dort bisher.
    """
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    try:
        u = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=jahr, db=db)
    except Exception:  # noqa: BLE001 — eine Sicht, die nicht rechnet, kippt den Bericht nicht
        logger.exception("Jahresbericht: Cockpit-Übersicht %s für Anlage %s nicht berechenbar", jahr, anlage_id)
        u = None
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose

    # Einzeljahr: kumuliert bis zum 31.12. des Berichtsjahres (Entscheid Gernot 12.10.2026) — dieselbe Rechnung mit
    # Stichtag; ihr Kapitaleinsatz kennt nur die bis dahin angeschafften Investitionen (Entscheid Master).
    stichtag = date(jahr, 12, 31) if jahr is not None else None
    amortisation_pct = None
    kapitaleinsatz = None
    try:
        p = await get_finanz_prognose(anlage_id, monate=12, db=db, stichtag=stichtag)
    except Exception:  # noqa: BLE001 — wie oben
        logger.exception("Jahresbericht: Finanz-Prognose (Stichtag %s) für Anlage %s nicht berechenbar", stichtag, anlage_id)
    else:
        # Nur Quote und Nenner: `bisherige_ertraege_euro` der Antwort ist die Zeitraum-Bilanz, nicht der Zähler der
        # Quote (der trägt die sonstigen Positionen anders, F-19) — als „Erträge ÷ Kapitaleinsatz" gedruckt ginge
        # die Rechnung nicht auf (gemessen 1.276 ÷ 10.500 € neben 16,9 %).
        amortisation_pct = p.amortisations_fortschritt_prozent
        kapitaleinsatz = p.kapitaleinsatz_euro
    return _RenditeFortschritt(
        rendite=u.jahres_rendite_prozent if u is not None else None,
        rendite_nenner_euro=u.investition_mehrkosten_euro if u is not None else None,
        wp_ersparnis_euro=u.wp_ersparnis_euro if u is not None else None,
        emob_ersparnis_euro=u.emob_ersparnis_euro if u is not None else None,
        amortisation_pct=amortisation_pct,
        kapitaleinsatz_euro=kapitaleinsatz,
    )


def _co2_bilanz(investitionen, fakten, zeilen_fakten, b: _Bestand, s: _FaktenSummen):
    """Abschnitt 9 (CO₂) — (PV, Wärmepumpe, E-Mobilität, gesamt) in kg."""
    hat_waermepumpe, hat_emobilitaet = b.hat_waermepumpe, b.hat_emobilitaet
    wp_waerme_mit_ersatz, wp_strom_mit_ersatz = s.wp_waerme_mit_ersatz, s.wp_strom_mit_ersatz
    # DI-1: WP-CO₂ über den kanonischen Helper — vermiedenes Gas-CO₂ MINUS
    # WP-Strom-CO₂, deckungsgleich mit Cockpit/Social. Früher `wp_waerme × f_gas`
    # (ohne Wirkungsgrad, ohne Strom-Abzug) → WP-Ersparnis deutlich zu hoch.
    # Komponente roh (kann bei schlechter JAZ negativ sein), Gesamt-Bilanz per
    # max(0, …) geklammert — exakt wie das Cockpit.
    # N-588 (DI-2, P15): der PV-Anteil je Monat aus der EINEN Konstruktions-Stelle (`co2_bilanz_aus_fakt`) — mit dem
    # Eigenverbrauch ohne Wandlungsverluste, wo der Messpunkt-Vertrag hält. Bis 10.10.2026 stand hier
    # `ev_gesamt × Faktor` (der Randfall, den DI-2 noch offen ließ); ohne Verluste ist der Wert derselbe.
    _eauto_parameter = {i.id: i.parameter for i in investitionen if i.typ == "e-auto"}
    co2_pv = sum(co2_bilanz_aus_fakt(f, _eauto_parameter).co2_pv_kg for f in zeilen_fakten)
    # N-256: die Mengen der **ersetzenden** Geräte, nicht die der Anlage. Bis
    # 2026-08-29 stand hier die anlagenweite Summe, gesperrt nur, wenn KEINE
    # Wärmepumpe etwas ersetzt hatte (`alle_ersetzen_nichts`). Bei der häufigen
    # Lage „Wärmepumpe ersetzt Gas + Split-Klimaanlage ersetzt nichts" wurde
    # damit auch die Wärme der Klimaanlage als vermiedenes Gas gebucht — eine
    # Ersparnis, die es nie gab. Die Teilsummen kommen aus der Schicht, hier
    # wird nichts mehr gefiltert (P10).
    co2_wp = (
        0 if not hat_waermepumpe
        else co2_wp_ersparnis_kg(wp_waerme_mit_ersatz, wp_strom_mit_ersatz)
    )
    # N-555 (Nebenfund 1): die E-Mob-CO₂ aus der EINEN Rechenregel
    # (`core/calculations.py::berechne_co2_bilanz`, ADR-001/DI-2), zusammengestellt
    # je Monat wie *Cockpit → Nachhaltigkeit* (`services/monats_co2.co2_bilanz_aus_fakt`),
    # je Monat bei 0 geklemmt und summiert — dieselbe Zahl wie der CO₂-Block im
    # Cockpit für denselben Zeitraum. Hier stand bis 25.09.2026 `emob_km × 0,12`:
    # eine eigene Konstante, ohne Vergleichs-Verbrenner des Fahrzeugs, ohne den
    # Netzstrom der Ladung und ohne den getankten Anteil eines Plug-in-Hybrids.
    co2_emob = (
        sum(
            max(0.0, co2_bilanz_aus_fakt(f, _eauto_parameter).co2_emob_kg)
            for f in fakten
        )
        if hat_emobilitaet else 0
    )
    co2_gesamt = co2_pv + max(0, co2_wp) + max(0, co2_emob)
    return co2_pv, co2_wp, co2_emob, co2_gesamt


@dataclass
class _GeraeteKennzahlen:
    """Abschnitt 9 — Speicher-Vollzyklen/-Effizienz, Wärmepumpen-Jahreskennzahlen, PV-Anteil der Heimladung."""

    speicher_zyklen: Optional[float]
    speicher_eff: Optional[float]
    wpk: object
    wp_cop: Optional[float]
    emob_pv_anteil: Optional[float]


def _geraete_kennzahlen(investitionen, fakten, b: _Bestand, s: _FaktenSummen) -> _GeraeteKennzahlen:
    """Abschnitt 9 (Geräte) — die Kennzahlen je Gerätegruppe, alle über ihren Layer bzw. Service."""
    speicher_ladung, speicher_entladung = s.speicher_ladung, s.speicher_entladung
    speicher_kapazitaet = b.speicher_kapazitaet
    emob_pv, emob_ladung = s.emob_pv, s.emob_ladung
    # Vollzyklen = ENTLADUNG ÷ Kapazität über den Layer-SoT (Kanon 2026-07-28).
    speicher_zyklen = berechne_vollzyklen(speicher_entladung, speicher_kapazitaet)
    # N-700: η über den Layer-SoT (N-252) wie Cockpit → Übersicht — ein Berichtszeitraum ist lang genug, dass sich
    # der SoC-Übertrag ausmittelt (`fenster_lang`), die Obergrenze gilt trotzdem: über 100 % kann kein Speicher, der
    # Bericht druckt dann „–" statt der Zahl. Hier stand `_safe_div(entladung, ladung) × 100` — der Bericht zeigte
    # „110,0 %", wo das Cockpit „nicht ermittelbar" sagt, und der N-252-Wächter sah die Aufrufform nicht.
    speicher_eff = speicher_wirkungsgrad(
        speicher_ladung, speicher_entladung, None, langes_fenster_quelle="fenster_lang",
    ).prozent
    # ADR-002/P12 (02.09.2026): Die Arbeitszahl entsteht im Layer, nie hier.
    # **Bis dahin stand hier `_safe_div(wp_waerme, wp_strom)`** — von allen
    # R2-Sperren kannte der Bericht nur die abgeleitete Wärme.
    #
    # ⛔ **Was gefehlt hat, und warum es hier besonders wiegt:** Bauartmischung
    # (SOLL §5), Geräte ohne Wärmemeldung (§4.2 Fall 1), die Anwender-Angabe
    # zum Fremdanteil (W-7) und der funktionsfremde Strom (W-14/E4). Ein
    # Jahresbericht ist ein **Dokument** — die Zahl darin wird weitergegeben,
    # ausgedruckt und in einem Jahr wieder gelesen, wenn niemand mehr weiß,
    # aus welchen Geräten sie entstanden ist.
    #
    # ⚠ Die Faltung über die Monate ist dieselbe wie in `cockpit/uebersicht.py`:
    # **ein** Monat mit verletzter Abgrenzung macht die Jahreszahl zum
    # Mischquotienten, deshalb `any(...)` statt „überwiegend".
    # B6/Y-2 (05.09.2026): dieselbe Faltung wie Cockpit → Jahr — EINE
    # Service-Funktion, kein zweiter Quotient. Bis hierher rechnete der Bericht
    # eine eigene Arbeitszahl und warf ihren Grund weg: „–" ohne Grund im
    # gedruckten Bericht (S3), keine Kennzahl je Funktion, keine Kühl-Arbeitszahl,
    # keine Herkunft, kein Vorbehalt — während Cockpit → Jahr seit B4 alles trug.
    _wpk = waermepumpe_jahreskennzahlen(
        fakten, [i for i in investitionen if i.typ == "waermepumpe"],
    )
    wp_cop = _wpk.arbeitszahl.wert
    emob_pv_anteil = _safe_div(emob_pv, emob_ladung) * 100 if emob_ladung else None
    return _GeraeteKennzahlen(
        speicher_zyklen=speicher_zyklen, speicher_eff=speicher_eff, wpk=_wpk, wp_cop=wp_cop,
        emob_pv_anteil=emob_pv_anteil,
    )


async def _wp_zaehler(db: AsyncSession, anlage_id: int, jahr: Optional[int], investitionen, hat_waermepumpe: bool):
    """Abschnitt 9 (WP-Counter) — (Starts, Betriebsstunden, Ø Laufzeit je Start) oder None je Größe."""
    # ── WP-Counter (#238): Kompressor-Starts + Betriebsstunden über den
    # Berichtszeitraum aus TagesZusammenfassung.komponenten_starts summiert.
    # Quelle/Logik analog zum Monatsbericht (aktueller_monat.py); respektiert
    # Anschaffungs-/Stilllegungsdatum je WP über ist_aktiv_im_monat.
    wp_starts_summe: Optional[int] = None
    wp_betriebsstunden_summe: Optional[float] = None
    if hat_waermepumpe:
        wp_starts_summe, wp_betriebsstunden_summe = await _wp_zaehler_summen(db, anlage_id, jahr, investitionen)
    # Ø Laufzeit pro Start (h) als Auslegungs-Indikator — nur wenn beides vorhanden.
    wp_laufzeit_pro_start = (
        round(wp_betriebsstunden_summe / wp_starts_summe, 2)
        if wp_starts_summe and wp_betriebsstunden_summe else None
    )
    return wp_starts_summe, wp_betriebsstunden_summe, wp_laufzeit_pro_start


async def _wp_zaehler_summen(db: AsyncSession, anlage_id: int, jahr: Optional[int], investitionen):
    """Die Tageszähler der im jeweiligen Monat aktiven Wärmepumpen — (Starts, Stunden), je None ohne Zähler."""
    wp_starts_summe: Optional[int] = None
    wp_betriebsstunden_summe: Optional[float] = None
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from sqlalchemy import extract as _extract
    wp_invs = [i for i in investitionen if i.typ == "waermepumpe"]
    tz_stmt = (
        select(TagesZusammenfassung.datum, TagesZusammenfassung.komponenten_starts)
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .where(TagesZusammenfassung.komponenten_starts.is_not(None))
    )
    if jahr is not None:
        tz_stmt = tz_stmt.where(_extract("year", TagesZusammenfassung.datum) == jahr)
    tz_res = await db.execute(tz_stmt)
    starts_total = 0
    stunden_total = 0.0
    hat_starts = hat_stunden = False
    for datum_, komp in tz_res.all():
        aktive_ids = {
            str(i.id) for i in wp_invs
            if i.ist_aktiv_im_monat(datum_.year, datum_.month)
        }
        if not aktive_ids:
            continue
        for inv_id_str, c in ((komp or {}).get("wp_starts_anzahl") or {}).items():
            if inv_id_str in aktive_ids and isinstance(c, (int, float)) and c > 0:
                starts_total += int(c)
                hat_starts = True
        for inv_id_str, h in ((komp or {}).get("wp_betriebsstunden") or {}).items():
            if inv_id_str in aktive_ids and isinstance(h, (int, float)) and h > 0:
                stunden_total += float(h)
                hat_stunden = True
    if hat_starts:
        wp_starts_summe = starts_total
    if hat_stunden:
        wp_betriebsstunden_summe = round(stunden_total, 1)
    return wp_starts_summe, wp_betriebsstunden_summe


@dataclass
class _StringVergleich:
    """Abschnitt 10 — die Zeilen SOLL/IST und die Hinweise des Abschnitts."""

    string_vergleiche: list
    monate_zeitraum: int
    teilzeitraum: bool
    verteilt: bool


async def _string_vergleich(
    db: AsyncSession, anlage, anlage_id: int, jahr: Optional[int], investitionen, alle_jahre, pvgis_prognose,
    ist_gesamtzeitraum: bool,
) -> _StringVergleich:
    """Abschnitt 10 — String-Vergleich SOLL/IST je Erzeuger-Zeile, dieselbe Regel wie Komponenten → PV-Strings."""
    # ── 10. String-Vergleich SOLL/IST ───────────────────────────────────
    # Erzeuger, nicht nur `pv-module` (F-10): eine reine Balkonkraftwerk-Anlage
    # bekam hier eine leere Tabelle, obwohl sie seit #367 ein PVGIS-SOLL hat.
    # Dieselben Zeilen und derselbe Nenner wie Komponenten → PV-Strings
    # (`api/routes/cockpit/pv_strings.py`) — beide über dieselben Funktionen
    # des Selektor-Moduls (N-614).
    # N-266: `erzeuger_traeger` — ein Balkonkraftwerk mit Modul-Kindern ist hier
    # keine eigene String-Zeile mehr, seine Kinder sind es. Bliebe es drin,
    # stünde es doppelt in der Tabelle UND verdoppelte den Verteilungsnenner
    # `gesamt_kwp` darunter, sodass jeder String zu wenig SOLL bekäme.
    # ⛔ N-614: Das gilt je MONAT, nicht für den Berichtszeitraum. Bis 03.10.2026
    # lief der Selektor hier einmal über alle Erzeuger: ein BKW, dem im
    # Berichtszeitraum Module zugeordnet wurden, hatte keine Zeile, und seine
    # Erzeugung aus den Monaten davor fehlte in der Summe des Abschnitts
    # (gemessen: 930 gegen 1860 kWh der Monatstabelle desselben PDFs).
    # `struktur` bleibt die Zuordnung über alle Erzeuger des Berichts (zeitblind
    # wie bisher, Issue #123); welche BKW in welchem Monat noch selbst tragen,
    # entscheidet `selbst_tragende_bkw_ids` — Zeitfilter vor dem Selektor.
    erzeuger_alle = [i for i in investitionen if i.typ in PV_ERZEUGER_TYPEN]
    struktur = erzeuger_traeger(erzeuger_alle)
    # Die Monate des Berichts — für die Zeilen (welches BKW trägt im Zeitraum
    # irgendwann selbst) und für den Hinweis „n von N Monaten" unten.
    bericht_monate = [(j, m) for j in alle_jahre for m in range(1, 13)]
    selbst_je_monat = {
        jm: selbst_tragende_bkw_ids(erzeuger_alle, *jm) for jm in bericht_monate
    }
    selbst_im_zeitraum = frozenset().union(*selbst_je_monat.values())
    pv_module = traeger_zeilen(erzeuger_alle, struktur, selbst_im_zeitraum)
    # kWp über den SoT-Dispatcher (Spalte → parameter-JSON, beim BKW
    # `leistung_wp × anzahl`) — sonst ist der SOLL-Verteilungs-Nenner bei
    # `parameter`-gepflegten Modulen eine Teilsumme, und der
    # `or anlage.leistung_kwp`-Fallback greift nur bei Summe 0, nicht bei
    # gemischter Pflege (N73/P3).
    gesamt_kwp = verteilungsnenner_kwp(struktur, anlage.leistung_kwp)
    _nenner_im_monat = _soll_nenner_je_monat(
        anlage, pvgis_prognose, erzeuger_alle, struktur, selbst_je_monat, gesamt_kwp,
    )

    # ⛔ N-616: Die Monate, über die eine Zeile verglichen wird, sind die Monate,
    # in denen SIE einen Wert hat — dieselbe Regel wie Komponenten → PV-Strings
    # (`_lade_ist_je_modul`: jeder Monat, für den `lade_pv_je_monat` der Zeile
    # einen gemessenen oder verteilten Wert liefert). Bis 04.10.2026 stand das
    # volle Jahres-SOLL (× Jahre) gegen das IST der erfassten Monate: im
    # laufenden Jahr, im Jahr der Inbetriebnahme und im Gesamtzeitraum nannte
    # jede Zeile eine Abweichung, die nur das Datum maß (gemessen: 2026 mit 6
    # von 12 Monaten −52 %). „Monat mit Wert" schließt die Abtretung schon ein:
    # `lade_pv_je_monat` entscheidet je Monat, wer trägt (ADR-002/P11) — ein
    # BKW hat nach der Abtretung keinen Wert mehr, seine Kinder vor ihrer
    # Anschaffung keinen, ein stillgelegter String danach keinen. Damit gilt
    # die Monatsrechnung aus N-614 für jede Anlage, nicht nur für eine mit
    # spät tragendem Balkonkraftwerk.
    pv_aufgeloest = await lade_pv_je_monat(
        db, anlage_id, erzeuger_alle, None if ist_gesamtzeitraum else jahr,
    )
    monate_je_zeile: dict[int, list[tuple[int, int]]] = {}
    for jm, werte in sorted(pv_aufgeloest.items()):
        for inv_id, w in werte.items():
            if w.quelle != PV_QUELLE_FEHLT:
                monate_je_zeile.setdefault(inv_id, []).append(jm)
    # Dieselbe Prognose wie in Abschnitt 4 — sonst widerspräche der
    # String-Vergleich der Monatstabelle desselben PDFs.
    prognose_monate: dict[int, float] = {}
    if pvgis_prognose and pvgis_prognose.monatswerte:
        for mw in pvgis_prognose.monatswerte:
            prognose_monate[mw.get("monat", 0)] = mw.get("e_m", 0) or 0
    prognose_per_modul = _prognose_per_modul(pvgis_prognose)
    monate_zeitraum = len(bericht_monate)

    string_vergleiche = []
    for inv in pv_module:
        _string_zeile(
            string_vergleiche, inv, monate_je_zeile, pv_aufgeloest, prognose_per_modul, prognose_monate,
            _nenner_im_monat, pvgis_prognose, ist_gesamtzeitraum,
        )
    # Wird mindestens eine Zeile über weniger Monate verglichen als der
    # Berichtszeitraum hat (laufendes Jahr, Inbetriebnahme, Zubau, Stilllegung,
    # Lücke), sagt der Abschnitt es — sonst läse man eine Teilsumme als Jahr.
    string_vergleich_teilzeitraum = any(
        s["monate"] < monate_zeitraum for s in string_vergleiche
    )
    string_vergleich_verteilt = any(s["ist_verteilt"] for s in string_vergleiche)
    return _StringVergleich(
        string_vergleiche=string_vergleiche, monate_zeitraum=monate_zeitraum,
        teilzeitraum=string_vergleich_teilzeitraum, verteilt=string_vergleich_verteilt,
    )


def _soll_nenner_je_monat(anlage, pvgis_prognose, erzeuger_alle, struktur, selbst_je_monat, gesamt_kwp):
    """Der SOLL-Nenner je Monat (N-661, N-614) als Funktion `(j, m) → kWp`, je Monat einmal berechnet."""
    # ⭐ N-661 (Weg C, Gernot 11.10.2026): der SOLL-Nenner je String sind die
    # kWp, für die die aktive Prognose gerechnet ist (`soll_nenner_kwp`) —
    # dieselbe Regel wie Komponenten → PV-Strings. Bis dahin standen hier die im
    # Berichtsjahr aktiven Träger (`aktiv_im_jahr` oben): ein Zubau NACH dem
    # Berichtsjahr fehlte im Nenner, obwohl die Prognose ihn trägt, und jeder
    # String bekam zu viel SOLL (gemessen +50 %). Ohne Prognose-kWp gilt der
    # frühere Nenner — N-614: je Monat der Menge, die trägt (ein BKW, das im
    # Monat selbst trägt, ersetzt darin seine Kinder, nie beide im Nenner).
    _nenner_cache: dict[tuple[int, int], float] = {}

    def _nenner_im_monat(j: int, m: int) -> float:
        if (j, m) not in _nenner_cache:
            selbst = selbst_je_monat.get((j, m))
            if selbst is None:
                selbst = selbst_tragende_bkw_ids(erzeuger_alle, j, m)
            _nenner_cache[(j, m)] = soll_nenner_kwp(
                pvgis_prognose,
                gesamt_kwp if not selbst else verteilungsnenner_kwp(
                    traeger_im_monat(erzeuger_alle, struktur, selbst), anlage.leistung_kwp,
                ),
            )
        return _nenner_cache[(j, m)]

    return _nenner_im_monat


def _prognose_per_modul(pvgis_prognose) -> dict[int, dict[int, float]]:
    """Die Pro-Modul-Monatswerte der aktiven Prognose je Investition (leer ohne sie)."""
    # Exakte Pro-Modul-Prognosen (v2.3.2): PVGIS wird je Modulfeld mit dessen
    # eigener Ausrichtung/Neigung abgerufen und unter `module_monatswerte`
    # abgelegt. Ohne sie bleibt nur die kWp-Verteilung des Anlagen-Gesamtwerts —
    # die ignoriert Ausrichtungsunterschiede und liefert bei Ost-West-Dächern
    # ~20–25 % zu hohe SOLL-Werte (CHANGELOG v2.3.2). Muster 1:1 aus dem
    # API-Pfad `api/routes/cockpit/pv_strings.py` (dort seit v2.3.2 in Gebrauch),
    # damit PDF und Cockpit denselben SOLL-Wert zeigen.
    prognose_per_modul: dict[int, dict[int, float]] = {}
    if pvgis_prognose and pvgis_prognose.module_monatswerte:
        for inv_id_str, monatsdaten in pvgis_prognose.module_monatswerte.items():
            try:
                prognose_per_modul[int(inv_id_str)] = {
                    mw["monat"]: mw.get("e_m", 0) or 0 for mw in monatsdaten
                }
            except (ValueError, TypeError, KeyError):
                pass
    return prognose_per_modul


def _string_zeile(
    string_vergleiche, inv, monate_je_zeile, pv_aufgeloest, prognose_per_modul, prognose_monate, _nenner_im_monat,
    pvgis_prognose, ist_gesamtzeitraum: bool,
) -> None:
    """Eine Zeile des String-Vergleichs — angehängt, wenn SOLL oder IST einen Wert hat."""
    kwp = get_erzeuger_kwp(inv)
    # ⛔ N-620: IST je Zeile aus DERSELBEN Auflösung wie Komponenten →
    # PV-Strings — `lade_pv_je_monat` über Module UND Balkonkraftwerke
    # (oben, `pv_aufgeloest`). Bis 04.10.2026 kam das IST hier aus den
    # Monats-Fakten (`erzeugung.pv_je_modul` für Module,
    # `bkw.erzeugung_je_investition` für BKW). Beide Wege tragen dieselbe
    # Summe, aber nicht dieselbe Zeile: in einem Monat mit Anlagenwert und
    # einem BKW ohne eigenen Wert verteilen die Fakten den Rest nur auf die
    # Module (das BKW ist dort nicht Empfänger), PV-Strings auf Module und
    # BKW nach kWp (gemessen 2026: Balkon 68 gegen 192,7, WestP 1.726 gegen
    # 1.602 kWh; Σ beider Sichten 3.976). Der Kommentar oben sagt zu, dass
    # PDF und PV-Strings dieselben Zeilen zeigen — jetzt auch dieselben
    # Zahlen. Die Monats-Fakten selbst (`pv_kwh`, `bkw_kwh`, `pv_je_modul`,
    # P9) bleiben unberührt; nur die Zuordnung je Zeile kommt von hier.
    # F-10 (das BKW ist eine Erzeuger-Zeile) bleibt damit gewahrt: die
    # Auflösung liefert ihm seinen eigenen Wert, sonst seinen kWp-Anteil.
    monate = monate_je_zeile.get(inv.id, [])
    werte_zeile = [pv_aufgeloest[jm][inv.id] for jm in monate]
    ist_kwh = sum(w.pv_erzeugung_kwh for w in werte_zeile)
    # Kennzeichnung wie PV-Strings („geschätzt (kWp-Anteil)"): ein einziger
    # verteilter Monat macht den Zeitraum verteilt (`_rollup_quelle`).
    ist_verteilt = any(w.quelle == PV_QUELLE_VERTEILT for w in werte_zeile)
    modul_prognose = prognose_per_modul.get(inv.id)
    prognose_kwh = _soll_der_zeile(inv, kwp, monate, modul_prognose, prognose_monate, _nenner_im_monat)
    if prognose_kwh > 0 or ist_kwh > 0:
        abw = ist_kwh - prognose_kwh
        abw_pct = (abw / prognose_kwh * 100) if prognose_kwh > 0 else 0
        spez = _spez_ertrag_der_zeile(inv, kwp, ist_kwh, monate, modul_prognose, pvgis_prognose, ist_gesamtzeitraum)
        string_vergleiche.append({
            "bezeichnung": inv.bezeichnung,
            "leistung_kwp": kwp,
            "ausrichtung": inv.ausrichtung,
            "neigung_grad": inv.neigung_grad,
            "prognose_kwh": prognose_kwh,
            "ist_kwh": ist_kwh,
            "abweichung_kwh": abw,
            "abweichung_prozent": abw_pct,
            "spezifischer_ertrag": spez,
            # N-616: über wie viele Monate diese Zeile verglichen wird — das
            # Template nennt es, wenn es nicht alle des Zeitraums sind.
            "monate": len(monate),
            # N-620: IST in mindestens einem Monat nach kWp verteilt, nicht gemessen.
            "ist_verteilt": ist_verteilt,
        })


def _soll_der_zeile(inv, kwp, monate, modul_prognose, prognose_monate, _nenner_im_monat) -> float:
    """Das SOLL einer Zeile über ihre Monate (N-616, N-614, F-34)."""
    # SOLL nur über die Monate der Zeile (N-616), je Monat mit dem kWp-Anteil
    # an der Menge, die in diesem Monat trägt (N-614), und im Anschaffungs-/
    # Stilllegungsmonat auf die Laufzeit gekürzt (F-34) — dieselbe Regel wie
    # Komponenten → PV-Strings. Monate eines Jahres mit demselben Anteil
    # werden erst summiert und dann einmal mit ihm multipliziert: so ist ein
    # vollständig erfasstes Jahr Rechenschritt für Rechenschritt die frühere
    # Jahresformel `Σ PVGIS × Anteil` (bitgleich, nicht nur auf die
    # angezeigte Stelle).
    summen_je_anteil: dict[tuple[int, float], float] = {}
    gekuerzte_monate = 0.0
    for (j, m) in monate:
        if modul_prognose is not None:
            prog, faktor = modul_prognose.get(m, 0), 1.0
        else:
            nenner = _nenner_im_monat(j, m)
            prog, faktor = prognose_monate.get(m, 0), (kwp / nenner if nenner > 0 else 0)
        voll = prog * faktor
        gekuerzt = soll_im_laufmonat(voll, inv, j, m)
        if gekuerzt != voll:
            gekuerzte_monate += gekuerzt
        else:
            summen_je_anteil[(j, faktor)] = summen_je_anteil.get((j, faktor), 0.0) + prog
    prognose_kwh = 0.0
    for (_, faktor), summe in summen_je_anteil.items():
        prognose_kwh += summe * faktor
    prognose_kwh += gekuerzte_monate
    return prognose_kwh


def _spez_ertrag_der_zeile(inv, kwp, ist_kwh, monate, modul_prognose, pvgis_prognose, ist_gesamtzeitraum: bool):
    """Spezifischer Ertrag einer Zeile — Einzeljahr über ihre Monate, Gesamtzeitraum als Jahreswert."""
    # Spezifischer Ertrag. Im Einzeljahr Erzeugung ÷ kWp über die Monate
    # der Zeile, ohne Hochrechnung (wie PV-Strings und die Kopfkennzahl
    # „Spez. Ertrag (Zeitraum)"). Im Gesamtzeitraum ein Jahreswert — bis
    # 04.10.2026 ÷ ALLE Jahre des Berichts, sodass jeder später zugebaute
    # oder früher abgetretene Erzeuger zu niedrig stand. ⛔ Der Jahreswert
    # kommt aus DER Layer-Formel der Cockpit-Kachel und des HA-Sensors
    # (`berechne_spez_ertrag_annualisiert`, saisonal gewichtet), je Zeile
    # aufgerufen: die Monate mit Wert, die eigene Investition, als
    # Gewichte das Monats-SOLL dieser Zeile (Modul-Prognose, sonst die
    # PVGIS-Monatswerte der Anlage, ohne beides die 52°N-Verteilung der
    # Formel). Eine lineare Hochrechnung (Monate ÷ 12) stand hier einen
    # Bauschritt lang und lag bei wenigen Monaten weit daneben (gemessen
    # bei wahren 1.000 kWh/kWp: Mai–Sep 1.464, Okt–Feb 468, nur Juni
    # 1.620). `None` (kein Wert, keine Leistung) zeigt das PDF als „–".
    if ist_gesamtzeitraum:
        if modul_prognose is not None:
            gewichte = {m: w for m, w in modul_prognose.items() if w and w > 0} or None
        else:
            gewichte = monatsgewichte_aus_pvgis(
                pvgis_prognose.monatswerte if pvgis_prognose else None
            ) or None
        spez = berechne_spez_ertrag_annualisiert(
            pv_erzeugung_kwh=ist_kwh,
            covered_months=set(monate),
            investitionen=[inv],
            fallback_kwp=kwp,
            monatsgewichte=gewichte,
        )
    else:
        spez = (ist_kwh / kwp) if kwp else 0
    return spez


def _charts(monats_zeilen, ist_gesamtzeitraum: bool):
    """Abschnitt 11 — (PV-Erzeugung, Energie-Fluss, Autarkie) als Data-URIs; ohne Monatszeilen je None."""
    # ── 11. Charts (Base64 Data-URIs) ───────────────────────────────────
    monats_labels = [z["monat_name"] for z in monats_zeilen]
    chart_pv = chart_fluss = chart_autarkie = None
    if monats_zeilen:
        chart_pv = pv_erzeugung_chart(
            monats_labels,
            [z["pv_erzeugung_kwh"] for z in monats_zeilen],
            [z["pvgis_prognose_kwh"] for z in monats_zeilen] if not ist_gesamtzeitraum else None,
        )
        chart_fluss = energie_fluss_chart(
            monats_labels,
            [z["eigenverbrauch_kwh"] for z in monats_zeilen],
            [z["einspeisung_kwh"] for z in monats_zeilen],
            [z["netzbezug_kwh"] for z in monats_zeilen],
        )
        chart_autarkie = autarkie_chart(
            monats_labels,
            [z["autarkie_prozent"] for z in monats_zeilen],
        )
    return chart_pv, chart_fluss, chart_autarkie


def _tarif_angaben(strompreis) -> dict:
    """Anbieter, Name und Preise einer Tarifzeile — ohne Zeile die Vorbelegung, mit der die Monats-Fakten rechnen."""
    return {
        "anbieter": strompreis.anbieter if strompreis else None,
        "tarifname": strompreis.tarifname if strompreis else None,
        "netzbezug_cent": strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else NETZBEZUG_DEFAULT_CENT,
        "einspeise_cent": strompreis.einspeiseverguetung_cent_kwh if strompreis else EINSPEISEVERGUETUNG_DEFAULT_CENT,
        "grundpreis_euro_monat": strompreis.grundpreis_euro_monat if strompreis else None,
        "gueltig_ab": strompreis.gueltig_ab if strompreis else None,
    }


def _kontext_tarif(zeitraeume: list[_TarifZeitraum]) -> dict:
    """Kontext „tarif" (Abschnitt 2) — der Allgemeintarif am Ende des Berichtszeitraums; wechselt er im Zeitraum,
    dazu ``zeitraeume`` je Abschnitt (sonst leer), damit der Kopf den Wechsel nennt, den die Monatszeilen rechnen."""
    kontext = _tarif_angaben(zeitraeume[-1].tarif)
    kontext["zeitraeume"] = [
        {
            **_tarif_angaben(z.tarif),
            "ohne_tarif": z.tarif is None,
            "von": f"{z.von[1]:02d}/{z.von[0]}",
            "bis": f"{z.bis[1]:02d}/{z.bis[0]}",
        }
        for z in zeitraeume
    ] if len(zeitraeume) > 1 else []
    return kontext


def _kontext_waermepumpe(
    hat_waermepumpe, fakten, s: _FaktenSummen, g: _GeraeteKennzahlen, wp_starts_summe, wp_betriebsstunden_summe,
    wp_laufzeit_pro_start,
) -> dict:
    """Kontext „waermepumpe" — Mengen, Arbeitszahlen mit Grund, Zähler."""
    wp_waerme, _wpk = s.wp_waerme, g.wpk
    return {
        "vorhanden": hat_waermepumpe,
        # F-43: **Anzeige** trennt „nicht gemessen" von „gemessene 0", die
        # Rechnung oben nicht (dort ist 0 der richtige Summand). `WpFakten`
        # trägt `float = 0.0` als Default; ohne diese Trennung rendert
        # `fmt_kwh(0.0)` ein „0 kWh", während der COP daneben korrekt „–"
        # sagt — dieselbe Tabelle, zwei Wahrheiten. Eine Klimaanlage ohne
        # Wärmemengenzähler bekam so drei erfundene Nullen.
        # Konvention übernommen, nicht erfunden: `aktueller_monat.py`
        # trägt einen Monatswert ebenfalls nur `if wert > 0` ein — deshalb
        # sagen Cockpit → Monat und (darüber aggregiert) → Jahr längst „—".
        # Das PDF war der einzige Konsument, der es nicht tat.
        # HA-Bauform E4d (Bauplan §8a, Rest N-585): eine GEMESSENE 0 ist ein Wert — „0 kWh" statt „—", wenn ein
        # Monat des Berichts die Wärme gemessen hat (`WpFakten.waerme_gemessen`; „kein Betrieb", kein fehlender Zähler).
        "waerme_kwh": (
            wp_waerme if wp_waerme > 0 or any(f.wp.waerme_gemessen for f in fakten) else None
        ),
        # N-673: dieselbe Trennung für die Aufteilung — gemessen (auch 0) ⇒ Wert, ungemessen ⇒ „—".
        "heizung_kwh": s.wp_heizung,
        "warmwasser_kwh": s.wp_warmwasser,
        "strom_kwh": s.wp_strom,
        "cop": g.wp_cop,
        "cop_grund": _wpk.arbeitszahl.grund,
        "cop_hinweis": _wpk.arbeitszahl.hinweis,
        # Kennzahlen je Funktion nur, wo getrennt gemessen wurde (R2) — sonst
        # trägt der Grund, warum nicht.
        "hat_split": _wpk.hat_split,
        "jaz_heizen": _wpk.je_funktion.heizen.wert,
        "jaz_heizen_grund": _wpk.je_funktion.heizen.grund,
        "jaz_warmwasser": _wpk.je_funktion.warmwasser.wert,
        "jaz_warmwasser_grund": _wpk.je_funktion.warmwasser.grund,
        # Kühlen wie Heizen/Warmwasser: Zeile mit Wert oder mit Grund (S3) —
        # dieselbe Regel wie Monatsbericht und Cockpit → Jahr.
        "jaz_kuehlen": _wpk.kuehlen.wert,
        "jaz_kuehlen_grund": _wpk.kuehlen.grund,
        "waerme_herkunft": _wpk.herkunft if _wpk.abgeleitet else None,
        "ersparnis_vorbehalt": _wpk.vorbehalt,
        "starts_summe": wp_starts_summe,
        "betriebsstunden_summe": wp_betriebsstunden_summe,
        "laufzeit_pro_start_h": wp_laufzeit_pro_start,
    }


def _kontext_investitionen(investitionen, inv_by_id) -> list[dict]:
    """Kontext „investitionen" — die Komponenten-Auflistung des Berichts."""
    return [
        {
            "typ": i.typ,
            "typ_label": _INV_TYP_LABELS.get(i.typ, i.typ),
            "bezeichnung": i.bezeichnung,
            "anschaffungsdatum": i.anschaffungsdatum,
            # `leistung_kwp` ist ein Mehrzweckfeld (N-G): `jahresbericht.html`
            # rendert dieselbe Spalte als kWh (Speicher), kW AC
            # (Wechselrichter) und kWp (Rest). Nur für die Erzeuger-Typen
            # trägt sie PV-Semantik — dort läuft sie über den SoT-Helper,
            # damit eine nur im `parameter` gepflegte Nennleistung (#229)
            # nicht als leere Spalte im PDF landet. Für Speicher und
            # Wechselrichter bleibt die Rohspalte stehen: ein
            # PV-kWp-Fallback wäre dort schlicht die falsche Größe.
            "leistung_kwp": (
                (get_erzeuger_kwp(i) or None)
                if i.typ in ("pv-module", "balkonkraftwerk")
                else i.leistung_kwp
            ),
            "ausrichtung": i.ausrichtung,
            "neigung_grad": i.neigung_grad,
            "parameter": i.parameter or {},
            # #303 (kingcap1): Komponenten-Auflistung im WeasyPrint-Bericht
            # mit denselben Feldern wie der reportlab-Pfad — sonst fehlt z. B.
            # der Speicher als Komponente.
            "kosten_euro": i.anschaffungskosten_gesamt,
            "alternativkosten_euro": i.anschaffungskosten_alternativ,
            "parent_bezeichnung": (
                inv_by_id.get(i.parent_investition_id).bezeichnung
                if i.parent_investition_id and i.parent_investition_id in inv_by_id
                else None
            ),
        }
        for i in investitionen
    ]
