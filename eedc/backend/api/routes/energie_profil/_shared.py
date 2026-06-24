"""
Energie-Profil Routes — gemeinsame Helper, Konstanten, Pydantic-Models.

Wird von views.py (Read-Endpoints) und repair.py (Repair-Endpoints) genutzt.
"""

import logging
import re
from datetime import date
from typing import Optional

from pydantic import BaseModel

from backend.models.investition import Investition

logger = logging.getLogger(__name__)


# seite je Investitionstyp
_TYP_SEITE: dict[str, str] = {
    "pv-module":       "quelle",
    "balkonkraftwerk": "quelle",
    "wechselrichter":  "quelle",
    "speicher":        "bidirektional",
    "e-auto":          "bidirektional",
    "wallbox":         "senke",
    "waermepumpe":     "senke",
}

# Virtuelle Serien (kein Investment dahinter)
# `netz` = Alt-Konvention (kombinierter, vorzeichenbehafteter Live-Σ-Key).
# `netzbezug`/`einspeisung` = Neu-Konvention seit Phase B / v3.34.2 (positiver
# Split aus dem Boundary-Pfad, komponenten_beitraege). Alle drei Kategorie
# "netz" → werden in der Energieprofil-Auswertung gleich (BIDI) behandelt; ohne
# die beiden Split-Keys fielen Neu-Tage in Geräteliste/Diagnose-Serien still
# durch `_key_to_serie_info → None` (Achse-3-Konsument-Robustheit, #316).
_VIRTUAL_SERIEN: dict[str, dict] = {
    "haushalt":    {"label": "Haushalt",    "typ": "virtual", "kategorie": "haushalt", "seite": "senke"},
    "netz":        {"label": "Stromnetz",   "typ": "virtual", "kategorie": "netz",     "seite": "bidirektional"},
    "netzbezug":   {"label": "Netzbezug",   "typ": "virtual", "kategorie": "netz",     "seite": "bidirektional"},
    "einspeisung": {"label": "Einspeisung", "typ": "virtual", "kategorie": "netz",     "seite": "bidirektional"},
    "pv_gesamt":   {"label": "PV Gesamt",   "typ": "virtual", "kategorie": "pv",       "seite": "quelle"},
}

# Optionale Suffixe bei WP-Serien (waermepumpe_{id}_heizen)
_SUFFIX_LABELS = {"heizen": " Heizen", "warmwasser": " Warmwasser"}

# Kategorien die bereits in dedizierten Spalten landen (kein Extra-Tracking nötig)
_DEDIZIERTE_KATEGORIEN = {"pv", "batterie", "netz", "haushalt", "waermepumpe", "wallbox", "eauto"}


def _key_to_serie_info(
    key: str, inv_map: dict[int, "Investition"]
) -> Optional[dict]:
    """Löst einen Komponenten-Key zu Label + Typ auf."""
    if key in _VIRTUAL_SERIEN:
        return {"key": key, **_VIRTUAL_SERIEN[key]}

    m = re.match(r'^([a-z]+)_(\d+)(?:_([a-z]+))?$', key)
    if not m:
        return None

    inv_id = int(m.group(2))
    suffix = m.group(3)
    inv = inv_map.get(inv_id)
    if not inv:
        return None

    label = inv.bezeichnung
    if suffix and suffix in _SUFFIX_LABELS:
        label += _SUFFIX_LABELS[suffix]

    # seite bestimmen
    seite = _TYP_SEITE.get(inv.typ, "senke")
    if inv.typ == "sonstiges" and isinstance(inv.parameter, dict):
        kat = inv.parameter.get("kategorie", "verbraucher")
        if kat == "erzeuger":
            seite = "quelle"
        elif kat == "speicher":
            seite = "bidirektional"

    return {
        "key": key,
        "label": label,
        "typ": inv.typ,
        "kategorie": m.group(1),
        "seite": seite,
    }


def detail_kategorie(info: dict, inv: Optional["Investition"]) -> str:
    """Feinere Anzeige-Kategorie eines Komponenten-Keys (Monats-Auswertung).

    Aus views.py extrahiert (ADR-001 testbar). Netz-Erkennung läuft über die
    `kategorie` (nicht den Roh-Key), damit BEIDE Netz-Konventionen — Alt-`netz`
    und Neu-Split `netzbezug`/`einspeisung` — auf dieselbe Detail-Kategorie
    `netz` fallen (Achse-3-Konsument-Robustheit, #316). Sonst landete ein
    Neu-Split-Key über die Fallthrough-Logik fälschlich in
    `sonstige_verbraucher`.
    """
    kat = info.get("kategorie", "sonstige")
    typ = info.get("typ", "")
    if kat == "netz":
        return "netz"
    if typ == "pv-module":
        return "pv_module"
    if typ == "balkonkraftwerk":
        return "bkw"
    if typ == "speicher":
        return "speicher"
    if typ == "waermepumpe":
        return "waermepumpe"
    if typ in ("wallbox", "e-auto"):
        return "wallbox_eauto"
    if kat == "haushalt":
        return "haushalt"
    if typ == "sonstiges" and inv and isinstance(inv.parameter, dict):
        unterkat = inv.parameter.get("kategorie", "verbraucher")
        if unterkat == "erzeuger":
            return "sonstige_erzeuger"
        if unterkat == "speicher":
            return "speicher"
        return "sonstige_verbraucher"
    if kat == "pv":
        return "pv_module"
    return "sonstige_verbraucher"


# ── Response Models ──────────────────────────────────────────────────────────

class SerieInfo(BaseModel):
    """Metadaten einer Komponenten-Serie (für Label-Auflösung im Frontend)."""
    key: str
    label: str
    typ: str        # z.B. "sonstiges", "pv-module", "virtual"
    kategorie: str  # z.B. "sonstige", "pv", "netz"
    seite: str      # "quelle" | "senke" | "bidirektional"


class StundenWertResponse(BaseModel):
    """Stündlicher Energiewert eines Tages."""
    stunde: int
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    batterie_kw: Optional[float] = None
    waermepumpe_kw: Optional[float] = None
    wallbox_kw: Optional[float] = None
    ueberschuss_kw: Optional[float] = None
    defizit_kw: Optional[float] = None
    temperatur_c: Optional[float] = None
    globalstrahlung_wm2: Optional[float] = None
    soc_prozent: Optional[float] = None
    komponenten: Optional[dict] = None  # Rohwerte aller Serien (key → kW)
    # WP-Kompressor-Starts in dieser Stunde, summiert über alle WPs (Issue #136).
    # Pro-Investitions-Aufschlüsselung lebt auf Tagesebene in TagesZusammenfassung.komponenten_starts.
    wp_starts_anzahl: Optional[int] = None
    # WP-Betriebsstunden in dieser Stunde, summiert über alle WPs (Issue #238).
    wp_betriebsstunden: Optional[float] = None


class StundenAntwort(BaseModel):
    """Tagesdetail-Antwort: Stundenwerte + aufgelöste Serie-Labels."""
    stunden: list[StundenWertResponse]
    serien: list[SerieInfo]  # alle in komponenten vorkommenden Serien mit Label


class WochenmusterPunkt(BaseModel):
    """Durchschnittlicher Stundenwert pro Wochentag."""
    wochentag: int      # 0=Mo, 1=Di, …, 6=So
    stunde: int         # 0–23
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    batterie_kw: Optional[float] = None
    anzahl_tage: int = 0


class HeatmapZelle(BaseModel):
    """Eine Zelle der Monats-Heatmap (Tag × Stunde)."""
    tag: int          # 1..31
    stunde: int       # 0..23
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    ueberschuss_kw: Optional[float] = None  # pv − verbrauch


class PeakStunde(BaseModel):
    """Eine einzelne Peak-Stunde im Monat."""
    datum: date
    stunde: int
    wert_kw: float


class TagesprofilStunde(BaseModel):
    """Ein Stundenpunkt im typischen Tagesprofil (Ø über Monat)."""
    stunde: int
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None


class KomponentenEintrag(BaseModel):
    """Ein einzelnes Gerät mit Monatssumme."""
    key: str
    label: str
    kategorie: str       # "pv", "waermepumpe", "wallbox", "eauto", "sonstiges", …
    typ: str             # z.B. "pv-module", "balkonkraftwerk", "waermepumpe", "sonstiges"
    seite: str           # "quelle" | "senke" | "bidirektional"
    kwh: float           # positiv = Erzeugung, negativ = Verbrauch
    anteil_prozent: Optional[float] = None  # vom Gesamt-PV bzw. Gesamt-Verbrauch


class KategorieSumme(BaseModel):
    """Monatssumme pro Kategorie (für KPI-Strip)."""
    kategorie: str       # "pv_module", "bkw", "sonstige_erzeuger", "waermepumpe", "wallbox_eauto", "sonstige_verbraucher", "haushalt"
    kwh: float
    anteil_prozent: Optional[float] = None


class MonatsAuswertungResponse(BaseModel):
    """Monatsauswertung aus TagesEnergieProfil + TagesZusammenfassung."""
    jahr: int
    monat: int
    tage_im_monat: int
    tage_mit_daten: int

    # Energie-Summen (kWh)
    pv_kwh: float
    verbrauch_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    ueberschuss_kwh: float
    defizit_kwh: float

    # Kennzahlen
    autarkie_prozent: Optional[float] = None
    eigenverbrauch_prozent: Optional[float] = None
    performance_ratio_avg: Optional[float] = None
    batterie_vollzyklen_summe: Optional[float] = None

    # Erweiterte Analyse-KPIs
    grundbedarf_kw: Optional[float] = None          # Ø Verbrauch Nachtstunden 0–5 Uhr
    batterie_ladung_kwh: Optional[float] = None      # Σ Energie in die Batterie
    batterie_entladung_kwh: Optional[float] = None   # Σ Energie aus der Batterie
    batterie_wirkungsgrad: Optional[float] = None    # Entladung / Ladung
    direkt_eigenverbrauch_kwh: Optional[float] = None  # Σ min(pv, verbrauch) je Stunde
    pv_tag_best_kwh: Optional[float] = None
    pv_tag_schnitt_kwh: Optional[float] = None
    pv_tag_schlecht_kwh: Optional[float] = None

    # Typisches Tagesprofil (24 Punkte, Ø über Monat)
    typisches_tagesprofil: list[TagesprofilStunde] = []

    # Per-Komponente Aggregation
    kategorien: list[KategorieSumme] = []
    komponenten: list[KomponentenEintrag] = []

    # Peaks (Top-N Stunden)
    peak_netzbezug: list[PeakStunde] = []
    peak_einspeisung: list[PeakStunde] = []
    peak_pv: Optional[PeakStunde] = None

    # Heatmap-Matrix
    heatmap: list[HeatmapZelle] = []

    # Börsenpreis / Negativpreis (§51 EEG)
    boersenpreis_avg_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None

    # Datenqualität (Issue #135): Anteil der Stunden ohne gemappten Zähler
    # Ermöglicht dem Frontend, Warnhinweise zu Datenlücken anzuzeigen.
    stunden_fehlend_pv: int = 0
    stunden_fehlend_verbrauch: int = 0


class TagesZusammenfassungResponse(BaseModel):
    """Tageszusammenfassung mit Per-Komponenten-kWh."""
    datum: date
    ueberschuss_kwh: Optional[float] = None
    defizit_kwh: Optional[float] = None
    peak_pv_kw: Optional[float] = None
    peak_netzbezug_kw: Optional[float] = None
    peak_einspeisung_kw: Optional[float] = None
    batterie_vollzyklen: Optional[float] = None
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    strahlung_summe_wh_m2: Optional[float] = None
    performance_ratio: Optional[float] = None
    stunden_verfuegbar: int = 0
    datenquelle: Optional[str] = None
    komponenten_kwh: Optional[dict] = None
    # Per-Komponenten Counter-Werte pro Tag (z.B. WP-Kompressor-Starts, Issue #136)
    # Form: {"wp_starts_anzahl": {"<inv_id>": <int>}}
    komponenten_starts: Optional[dict] = None
    # Börsenpreis-Aggregation (§51 EEG)
    boersenpreis_avg_cent: Optional[float] = None
    boersenpreis_min_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None


class TagWerteResponse(BaseModel):
    """Tageszeile für die Werte/Tabelle-Embed-Sicht in Tagesgranularität
    (IA v4 E3, Cockpit/Monat). Feldnamen sind **deckungsgleich mit den
    Frontend-Registry-Keys** (`lib/werte`), damit der Tag-Accessor `getTagWert`
    — wie `getMonatWert` — direkt `row[key]` lesen kann.

    Energie-Bilanz + Quoten + Speicher/WP stammen aus `bilanz_aus_stundenrows`
    (Σ stündl. TEP-Rows, identische Semantik wie `get_monatsauswertung` →
    additive Symmetrie). Finanzen über den `baue_finanz_zeile`-SoT (#326,
    je-Monat-Tarif). Die `*_kw`/PR/Börsenpreis-Felder sind tag-native (kein
    Monats-Pendant).
    """
    datum: date
    stunden_verfuegbar: int = 0
    datenquelle: Optional[str] = None
    # Energie (additive kWh) — Registry-Keys
    erzeugung: float = 0.0
    eigenverbrauch: float = 0.0
    einspeisung: float = 0.0
    netzbezug: float = 0.0
    gesamtverbrauch: float = 0.0
    direktverbrauch: float = 0.0
    # Quoten (%)
    autarkie: Optional[float] = None
    evQuote: Optional[float] = None
    spezErtrag: Optional[float] = None
    # Speicher
    speicher_ladung: Optional[float] = None
    speicher_entladung: Optional[float] = None
    speicher_effizienz: Optional[float] = None
    # Wärmepumpe (nur Strom je Tag ableitbar; Wärme/COP bleiben monat-only)
    wp_strom: Optional[float] = None
    # Finanzen (€) — einfaches lineares Modell wie createMonatsZeitreihe
    einspeise_erloes: float = 0.0
    ev_ersparnis: float = 0.0
    netzbezug_kosten: float = 0.0
    netto_ertrag: float = 0.0
    netto_bilanz: float = 0.0
    # CO₂
    co2_einsparung: float = 0.0
    # ── Tag-native Zusatzmetriken (kein Monats-Registry-Pendant) ──
    ueberschuss_kwh: Optional[float] = None
    defizit_kwh: Optional[float] = None
    peak_pv_kw: Optional[float] = None
    peak_netzbezug_kw: Optional[float] = None
    peak_einspeisung_kw: Optional[float] = None
    performance_ratio: Optional[float] = None
    batterie_vollzyklen: Optional[float] = None
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    strahlung_summe_wh_m2: Optional[float] = None
    boersenpreis_avg_cent: Optional[float] = None
    boersenpreis_min_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None


class TagDetailResponse(BaseModel):
    """Tages-Detail-Werte für Cockpit/Tag, die NICHT in der Tages-Bilanz/
    `TagWerteResponse` stehen, aber aus Snapshots/TEP tagesgenau erhebbar sind
    (D1 „maximal erheben", SPEC-COCKPIT-TAG-JAHR Abschnitt F). Pro gewähltem Tag
    EIN Aufruf (anders als die 90-Tage-Werte-Spanne — diese Felder sind
    snapshot-teuer). Felder sind `None`, wenn der jeweilige Sensor nicht gemappt
    ist bzw. keine Snapshot-/TEP-Daten vorliegen → das Frontend lässt sie weg.
    """
    datum: date
    # WP-Strom-Split (getrennte Strommessung) — Tages-Boundary-Diff.
    wp_strom_heizen_kwh: Optional[float] = None
    wp_strom_warmwasser_kwh: Optional[float] = None
    # WP-Wärme (thermisch, nur mit Wärmemengenzähler-Sensor) — Tages-Boundary-Diff.
    # Ermöglicht Tages-JAZ (= Wärme ÷ Strom) und Wärme-Aufteilung.
    wp_heizung_kwh: Optional[float] = None
    wp_warmwasser_kwh: Optional[float] = None
    # Speicher-Netzladung (Arbitrage) — Tages-Boundary-Diff.
    speicher_ladung_netz_kwh: Optional[float] = None
    # Speicher effektiver Netz-Ladepreis (stundengewichtet, Tagesspanne).
    speicher_effektiver_ladepreis_cent: Optional[float] = None
    speicher_effektiver_ladepreis_quelle: Optional[str] = None
    # E-Mobilität PV-/Netz-Anteil der Ladung — Tages-Boundary-Diff (nur bei Sensor).
    emob_ladung_pv_kwh: Optional[float] = None
    emob_ladung_netz_kwh: Optional[float] = None
    # PV Tages-SOLL = OM-Tagesprognose × eedc-Lernfaktor (wie Genauigkeits-Tracking).
    soll_pv_kwh: Optional[float] = None
    # Tages-Tarif (Monatstarif je Tag) — für Wirkungsverluste € + Tarif-Zeile.
    einspeise_preis_cent: Optional[float] = None
    netzbezug_preis_cent: Optional[float] = None


class ReaggregatePreviewBoundary(BaseModel):
    sensor_key: str
    kategorie: Optional[str] = None
    zeitpunkt: str
    alt_kwh: Optional[float] = None
    neu_kwh: Optional[float] = None


class ReaggregatePreviewSlot(BaseModel):
    stunde: int
    kategorie: str
    alt_kwh: Optional[float] = None
    neu_kwh: Optional[float] = None


class ReaggregatePreviewCounterTagesdelta(BaseModel):
    feld: str
    alt: Optional[int] = None
    neu: Optional[int] = None


class ReaggregatePreviewResponse(BaseModel):
    datum: str
    boundaries: list[ReaggregatePreviewBoundary]
    slot_deltas: list[ReaggregatePreviewSlot]
    tagesumme_alt: dict[str, Optional[float]]
    tagesumme_neu: dict[str, Optional[float]]
    ha_verfuegbar: bool
    counter_tagesdelta: list[ReaggregatePreviewCounterTagesdelta]


class StundenPrognose(BaseModel):
    """Prognose für eine Stunde: PV, Verbrauch, Netto-Bilanz, Batterie-SoC."""
    stunde: int
    pv_kw: float
    verbrauch_kw: float
    netto_kw: float           # pv - verbrauch (positiv=Überschuss)
    netzbezug_kw: float       # max(0, Bedarf nach Batterie-Entladung)
    einspeisung_kw: float     # max(0, Überschuss nach Batterie-Ladung)
    soc_prozent: Optional[float] = None  # Simulierter Batterie-SoC


class TagesPrognoseResponse(BaseModel):
    """Kombinierte Verbrauchs- + PV- + Batterie-Prognose für einen Tag."""
    datum: str
    stunden: list[StundenPrognose]
    # Zusammenfassung
    pv_summe_kwh: float
    verbrauch_summe_kwh: float
    netzbezug_summe_kwh: float
    einspeisung_summe_kwh: float
    eigenverbrauch_kwh: float
    autarkie_prozent: float
    # Speicher (optional)
    speicher_kapazitaet_kwh: Optional[float] = None
    speicher_voll_um: Optional[str] = None
    speicher_leer_um: Optional[str] = None
    # Meta
    verbrauch_basis: str        # "gleicher_wochentag", "tagestyp", "alle"
    pv_quelle: str              # "openmeteo" oder "solcast"
    daten_tage: int
