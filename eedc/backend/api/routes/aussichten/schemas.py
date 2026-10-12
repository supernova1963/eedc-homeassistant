"""Aussichten — die Antwortmodelle (Kurzfrist · Langfrist · Trend · Wetter · Finanz-Prognose).
"""
# Reiner Umzug aus `api/routes/aussichten.py` (18.09.2026, Vorlage 7 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from typing import Optional, List
from pydantic import BaseModel


# =============================================================================
# Pydantic Schemas
# =============================================================================

class TagesPrognoseSchema(BaseModel):
    """Prognose für einen einzelnen Tag."""
    datum: str
    pv_prognose_kwh: float
    globalstrahlung_kwh_m2: Optional[float]
    sonnenstunden: Optional[float]
    temperatur_max_c: Optional[float]
    temperatur_min_c: Optional[float]
    niederschlag_mm: Optional[float]
    bewoelkung_prozent: Optional[int]
    wetter_symbol: str

class KurzfristPrognoseResponse(BaseModel):
    """Response für Kurzfrist-Prognose (7-16 Tage)."""
    anlage_id: int
    anlagenname: str
    anlagenleistung_kwp: float
    prognose_zeitraum: dict
    summe_kwh: float
    durchschnitt_kwh_tag: float
    tageswerte: List[TagesPrognoseSchema]
    datenquelle: str
    abgerufen_am: str
    system_losses_prozent: float

class MonatsPrognoseSchema(BaseModel):
    """Prognose für einen Monat."""
    jahr: int
    monat: int
    monat_name: str
    pvgis_prognose_kwh: float
    trend_korrigiert_kwh: float
    konfidenz_min_kwh: float
    konfidenz_max_kwh: float
    historische_performance_ratio: Optional[float]

class TrendAnalyseSchema(BaseModel):
    """Trend-Analyse-Informationen."""
    durchschnittliche_performance_ratio: float
    trend_richtung: str
    datenbasis_monate: int

class LangfristPrognoseResponse(BaseModel):
    """Response für Langfrist-Prognose (Monate)."""
    anlage_id: int
    anlagenname: str
    anlagenleistung_kwp: float
    prognose_zeitraum: dict
    jahresprognose_kwh: float
    monatswerte: List[MonatsPrognoseSchema]
    trend_analyse: TrendAnalyseSchema
    datenquellen: List[str]

class JahresVergleichSchema(BaseModel):
    """Jahresvergleich-Daten."""
    jahr: int
    gesamt_kwh: float
    spezifischer_ertrag_kwh_kwp: float
    performance_ratio: Optional[float]
    anzahl_monate: int  # Anzahl Monate mit Daten
    ist_vollstaendig: bool  # True wenn 12 Monate Daten vorhanden

class SaisonaleMusterSchema(BaseModel):
    """Saisonale Muster."""
    beste_monate: List[str]
    schlechteste_monate: List[str]

class DegradationSchema(BaseModel):
    """Degradations-Informationen."""
    geschaetzt_prozent_jahr: Optional[float]
    hinweis: str
    methode: Optional[str] = None  # "vollstaendig" oder "tmy_ergaenzt"
    zuverlaessig: bool = False  # True erst ab 3+ Jahren

class TrendAnalyseResponse(BaseModel):
    """Response für Trend-Analyse."""
    anlage_id: int
    anlagenname: str
    anlagenleistung_kwp: float
    analyse_zeitraum: dict
    jahres_vergleich: List[JahresVergleichSchema]
    saisonale_muster: SaisonaleMusterSchema
    degradation: DegradationSchema
    datenquellen: List[str]

class WetterVorhersageTag(BaseModel):
    """Wettervorhersage für einen Tag."""
    datum: str
    temperatur_max_c: Optional[float]
    temperatur_min_c: Optional[float]
    niederschlag_mm: Optional[float]
    sonnenstunden: Optional[float]
    bewoelkung_prozent: Optional[int]
    wetter_symbol: str

class WetterVorhersageResponse(BaseModel):
    """Response für reine Wettervorhersage."""
    anlage_id: int
    standort: dict
    tage: List[WetterVorhersageTag]
    abgerufen_am: str

# Finanzen-Schemas
class FinanzPrognoseMonatSchema(BaseModel):
    """Finanzprognose für einen Monat."""
    jahr: int
    monat: int
    monat_name: str
    pv_erzeugung_kwh: float
    eigenverbrauch_kwh: float
    einspeisung_kwh: float
    einspeise_erloes_euro: float
    ev_ersparnis_euro: float
    netto_ertrag_euro: float
    # Komponenten-Details
    speicher_beitrag_kwh: float = 0  # Zusätzlicher EV durch Speicher
    v2h_beitrag_kwh: float = 0  # Zusätzlicher EV durch V2H
    wp_verbrauch_kwh: float = 0  # Wärmepumpe-Stromverbrauch

class KomponentenBeitragSchema(BaseModel):
    """Beitrag einer Komponente zur Finanzprognose."""
    typ: str
    bezeichnung: str
    beitrag_kwh_jahr: float
    beitrag_euro_jahr: float
    beschreibung: str

class ErtragJeInvestitionSchema(BaseModel):
    """Der kumulierte, GEMESSENE Netto-Ertrag einer ROI-Zeile (Bauschritt 5).

    ``investition_id`` ist die **Zeilen**-ID der ROI-Sicht: beim PV-System der
    Wechselrichter, sonst die Investition selbst. Der Betrag darf negativ sein
    — eine Komponente, deren Betriebskosten ihre Erträge übersteigen, soll das
    sagen dürfen, statt auf 0 geschönt zu werden.
    """

    investition_id: int
    bisherige_ertraege_euro: float

class FinanzPrognoseResponse(BaseModel):
    """Response für Finanzprognose."""
    anlage_id: int
    anlagenname: str
    prognose_zeitraum: dict

    # Strompreise
    einspeiseverguetung_cent_kwh: float
    netzbezug_preis_cent_kwh: float
    grundpreis_euro_monat: float = 0

    # Jahresprognose
    jahres_erzeugung_kwh: float
    jahres_eigenverbrauch_kwh: float
    jahres_einspeisung_kwh: float
    eigenverbrauchsquote_prozent: float

    # Finanzen
    jahres_einspeise_erloes_euro: float
    jahres_ev_ersparnis_euro: float
    ust_eigenverbrauch_euro: Optional[float] = None  # USt auf Eigenverbrauch (nur bei Regelbesteuerung)
    jahres_netto_ertrag_euro: float

    # Komponenten-Beiträge (NEU)
    komponenten_beitraege: List[KomponentenBeitragSchema] = []

    # Speicher-spezifisch
    speicher_ev_erhoehung_kwh: float = 0
    speicher_ev_erhoehung_euro: float = 0

    # E-Auto/V2H-spezifisch
    v2h_rueckspeisung_kwh: float = 0
    v2h_ersparnis_euro: float = 0
    eauto_ladung_pv_kwh: float = 0
    #: PV-Ladung × Strompreis — ⭐ **Information, kein Posten** (N-672): dieser Betrag steckt bereits in
    #: ``jahres_ev_ersparnis_euro`` (der Eigenverbrauch der Anlage enthält die PV-Ladung) und geht in
    #: ``jahres_netto_ertrag_euro`` NICHT ein; die E-Auto-Ersparnis belastet dieselbe kWh mit demselben Preis.
    eauto_ersparnis_euro: float = 0

    # Wärmepumpe-spezifisch
    wp_stromverbrauch_kwh: float = 0
    wp_pv_anteil_kwh: float = 0
    wp_pv_ersparnis_euro: float = 0

    # Alternativkosten-Einsparungen (NEU)
    wp_alternativ_ersparnis_euro: float = 0  # vs. Gas/Öl
    eauto_alternativ_ersparnis_euro: float = 0  # vs. Benzin

    # Investitionen (erweitert mit Alternativkosten-Berechnung)
    investition_pv_system_euro: float = 0  # PV, Speicher, Wallbox
    investition_wp_mehrkosten_euro: float = 0  # WP-Kosten minus Gasheizung
    investition_eauto_mehrkosten_euro: float = 0  # E-Auto minus Verbrenner
    investition_sonstige_euro: float = 0  # Andere Investitionen
    investition_gesamt_euro: float  # Relevante Kosten (inkl. Mehrkosten-Ansatz)
    # F-19: der tatsächliche Nenner des Amortisations-Fortschritts — relevante
    # Kosten plus die kumulierten sonstigen AUSGABEN. Er steht in der Response,
    # damit die Zahl nachvollziehbar bleibt UND der Symmetrie-Wächter sie
    # direkt vergleichen kann, statt sie aus Prozentwerten zurückzurechnen.
    kapitaleinsatz_euro: float = 0.0
    #: N-719 (12.10.2026): der ZÄHLER des Fortschritts — die bisherigen Erträge ohne beide Seiten der sonstigen
    #: Positionen (F-19, Bauschritt 7: Ausgaben wieder aufgeschlagen, Erträge abgezogen). Die Kachel nennt damit
    #: Zähler ÷ Nenner der Quote (`amortisation_ertraege_euro ÷ kapitaleinsatz_euro`) statt der Zeitraum-Bilanz
    #: `bisherige_ertraege_euro` ÷ Mehrkosten (gemessen «1.276 € ÷ 10.000 €» neben 16,9 %; richtig 1.776 ÷ 10.500).
    amortisation_ertraege_euro: float = 0.0
    bisherige_ertraege_euro: float  # Kumulierte Erträge seit Inbetriebnahme
    amortisations_fortschritt_prozent: float  # Wie viel % bereits amortisiert (kumuliert)
    amortisation_erreicht: bool
    amortisation_prognose_jahr: Optional[int]  # Geschätztes Jahr der Amortisation
    restlaufzeit_bis_amortisation_monate: Optional[int]
    #: Konzept §5/§8-6 — die Annahme hinter **diesen beiden** Feldern.
    #: ⚠ Der Fortschritt selbst (`amortisations_fortschritt_prozent`) ist eine
    #: Messung und unterstellt nichts (§4). Restlaufzeit und Prognosejahr sind
    #: es nicht: sie rechnen den offenen Rest mit `jahres_netto_ertrag_euro`
    #: hoch und sind damit **Dauer-Aussagen** — also fällt genau dieses Paar
    #: unter §5 und trägt denselben Satz wie das ROI-Dashboard.
    amortisation_annahme: Optional[str] = None
    # Bauschritt 5 (§8): derselbe Zähler, auf die ROI-Zeilen zerlegt. Der
    # NENNER kommt je Zeile aus dem ROI-Dashboard (`kapitaleinsatz`) — genau
    # wie bei der anlagenweiten Kachel, die schon heute ihren Zähler von hier
    # und ihren Nenner von dort bezieht.
    ertraege_je_investition: List[ErtragJeInvestitionSchema] = []
    #: Was zu keiner Zeile gehören KANN — anlagenweite Monatspositionen (sie
    #: haben keine Investition, §8/4) und die dienstlichen Ladekosten. Steht
    #: ausdrücklich in der Response: ein wachsender Rest ist ein Befund, kein
    #: Rundungsfehler.
    ertraege_nicht_zurechenbar_euro: float = 0.0

    # Monatswerte
    monatswerte: List[FinanzPrognoseMonatSchema]

    datenquellen: List[str]
