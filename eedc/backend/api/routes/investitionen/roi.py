"""Investitionen API — ROI-Dashboard.

GET /api/investitionen/roi/{anlage_id} — Wirtschaftlichkeit aller aktiven Investitionen einer Anlage (PV-Systeme
aggregiert, Standalone je Geraet, Orphan-Module), Amortisation als Kalender-Treppe (N-525).

Dazu die Kennwert-Aufloeser Param-Fallback ↔ IST (Etappe C, #264), die strukturelle Gruppierung
`_gruppiere_investitionen` (auch `aussichten/finanz_zerlegung.py` liest sie) und die ROI-Schemas.
"""
# Reiner Umzug aus `api/routes/investitionen/crud.py` (18.09.2026, Vorlage 5 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. `crud.py` haengt den Router NACH seinen eigenen
# Routen ein (Reihenfolge in /api/openapi.json unveraendert) und exportiert die Namen weiter.

from dataclasses import dataclass
from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import date
from backend.core.exceptions import not_found
from backend.core.field_definitions import URTEIL_GILT, feld_urteil, ist_abgabe_kategorie
from backend.core.investition_kennwerte import (
    get_bkw_kwp,
    get_pv_kwp,
    get_speicher_kapazitaet_kwh,
    get_speicher_kopplung,
    get_speicher_kopplung_gepflegt,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.core.berechnungen.erzeuger_traeger import traegt_erzeugungsgroessen_selbst
from backend.api.deps import get_db
from backend.utils.investition_value import param_zahl
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_im_jahr, sort_investitionen_nach_typ
from backend.core.berechnungen.investitions_jahresertrag import (
    BEZEICHNUNG_ABGABE,
    jahresertrag_posten,
)
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_strompreis_for_komponente,
)
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
    SPEICHER_KOPPLUNG_DC,
)
from backend.core.wirtschaftlichkeit_defaults import EINSPEISEVERGUETUNG_DEFAULT_CENT
from backend.core.berechnungen.speicher_wirtschaftlichkeit import aggregiere_speicher_ist
from backend.services.speicher_wirtschaftlichkeit import (
    EffektiverLadepreisErgebnis,
    WirkungsgradErgebnis,
    berechne_effektiver_ladepreis,
    berechne_ist_wirkungsgrad,
)
from backend.services.eauto_wirtschaftlichkeit import (
    eigener_verbrauch_l_100km,
    fahranteil_prozent,
    letzter_kraftstoffpreis_aus_lookup,
    resolve_eauto_benzinpreis,
)
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.services.monats_fakten import ist_pv_ladeanteil_prozent, lade_monats_fakten
from backend.core.berechnungen import (
    einspeise_erloes_euro,
    ersetzt_keine_heizung,
    relevante_kosten_aus_investitionen,
)

router = APIRouter()


# ============================================================================
# Etappe C (#264): Helper-Auflösung Param-Fallback ↔ IST-Werte
# ============================================================================


def _aufloesen_wirkungsgrad(
    eta_ist: Optional[WirkungsgradErgebnis],
    *,
    param_wirkungsgrad: float,
) -> tuple[float, str]:
    """Liefert (wirkungsgrad_prozent, quelle) für die ROI-Berechnung.

    Etappe C1: Helper liefert immer ein Ergebnis. Bei `wirkungsgrad_prozent
    is None` (z. B. `quelle="fenster-zu-kurz"`) fallen wir auf den Param-Wert
    zurück, geben aber die Helper-Quelle weiter, damit das Frontend die
    Datenbasis im Badge ausweisen kann.
    """
    if eta_ist is None:
        return param_wirkungsgrad, "param"
    if eta_ist.wirkungsgrad_prozent is None:
        # Helper hat geantwortet, aber nichts berechenbar (kurzes Fenster +
        # keine SoC-Werte, oder ladung_kwh=0). Param mit Helper-Quelle.
        return param_wirkungsgrad, eta_ist.quelle
    return eta_ist.wirkungsgrad_prozent, eta_ist.quelle

def _aufloesen_ladepreis(
    eff_ladepreis: Optional[EffektiverLadepreisErgebnis],
    *,
    nutzt_arbitrage: bool,
    param_lade_preis: float,
) -> tuple[Optional[float], str]:
    """Liefert (ladepreis_cent, quelle) für die ROI-Berechnung.

    Etappe C1/C4: Helper liefert immer ein Ergebnis. Bei nicht-belastbarer
    Quelle (`keine-tep-daten`, `keine-netzladung`, `kein-dyn-tarif`,
    `datenbasis-zu-duenn` mit `effektiver_ladepreis_cent=None`) Param-Fallback. Ohne Arbitrage und
    ohne Param: `None` → der Spread-Service behandelt das als kostenneutral.
    """
    if eff_ladepreis is None:
        # Helper wurde gar nicht aufgerufen (z. B. kein Speicher)
        if nutzt_arbitrage:
            return param_lade_preis, "param"
        return None, "bezugspreis-fallback"
    if eff_ladepreis.effektiver_ladepreis_cent is None:
        if nutzt_arbitrage:
            return param_lade_preis, eff_ladepreis.quelle
        return None, eff_ladepreis.quelle
    return eff_ladepreis.effektiver_ladepreis_cent, eff_ladepreis.quelle

def _gruppiere_investitionen(
    investitionen: list[Investition],
) -> tuple[dict[int, dict], list[Investition], list[Investition]]:
    """Gruppiert Investitionen strukturell für die ROI-Berechnung.

    Reine Zwei-Pass-Zuordnung (keine DB-I/O, keine Berechnung, keine
    Anzeige-Strings) der bereits geladenen Investitions-Liste:

    - **PV-Systeme** — ein **Trägergerät** mit zugeordneten PV-Modulen und
      DC-gekoppelten Speichern. ROI nur auf System-Ebene sinnvoll.
    - **Standalone** — AC-gekoppelte Speicher (ohne gültigen Träger-Parent)
      und alle übrigen Typen (E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk
      **ohne Kinder**, Sonstiges).
    - **Orphan-PV-Module** — PV-Module ohne (gültige) Träger-Zuordnung
      (Altdaten).

    **Trägergerät ist nicht nur der Wechselrichter (F-33, #381).** Bis
    v4.0.18 stand hier ausschließlich `wechselrichter`. Seither erlaubt
    `ERLAUBTE_PARENT_TYPEN` einem **Balkonkraftwerk** beide Kind-Typen
    (Speicher seit v4.0.5, PV-Module seit N-266) — die Gruppierung wusste es
    nur nicht. Folge an der Anlage des Melders: BKW, Modul-Kind und
    Speicher-Kind bekamen **drei** ROI-Zeilen, deren Einsparungen aus
    **derselben** Energie stammen und trotzdem addiert wurden (1.079 € statt
    606 €/Jahr ⇒ Amortisation 1,9 statt 3,3 Jahre). Das Modul-Kind stand
    zusätzlich als „(ohne WR)" mit der Aufforderung da, etwas zuzuordnen, was
    der Nutzer zugeordnet **hatte**.

    Ein BKW wird deshalb genau dann Systemkopf, wenn **Kinder an ihm
    hängen**; ohne Kinder bleibt es standalone und alles ist bitgleich. Das
    ist dieselbe Doktrin, die `get_bkw_kwp` seit N-266 für die **Nennleistung**
    anwendet („hängen Module am BKW, ist deren Summe die Nennleistung des
    Geräts") und die die Monats-Fakten über `abgetretene_bkw_ids` für die
    **Erzeugung** anwenden — hier nur auf die **Einsparung** angewandt. Die
    Sperre gegen Doppelzählung saß bisher allein auf der Erzeugungsseite
    (`pv_module_kwh` schließt die BKW-Erzeugung aus); die neue Struktur ist
    an der **Struktur**-Seite daran vorbeigelaufen.

    Zwei-Pass-Ansatz: erst alle Trägergeräte registrieren, damit
    `parent_investition_id` unabhängig von der Sortierung aufgelöst werden
    kann.

    Returns:
        (pv_systeme, standalone, orphan_pv_module) — `pv_systeme` als
        ``traeger_id -> {"wr": Investition, "pv_module": [...], "speicher": [...]}``.
        Der Schlüssel `"wr"` heißt aus Bestandsgründen so und trägt seit F-33
        auch ein Balkonkraftwerk.
    """
    pv_systeme: dict[int, dict] = {}
    standalone: list[Investition] = []
    orphan_pv_module: list[Investition] = []

    # F-33: welche Investitionen werden überhaupt als Parent benannt? Nur ein
    # BKW MIT Kindern wird Systemkopf — eines ohne bleibt standalone und
    # behält seine bisherige Zeile unverändert. `ERLAUBTE_PARENT_TYPEN` ist
    # der SoT dafür, welche Kind-Typen es geben kann; hier zählt allein, ob
    # eines tatsächlich zeigt.
    benannte_parents = {
        inv.parent_investition_id
        for inv in investitionen
        if inv.parent_investition_id is not None
        and inv.typ in (InvestitionTyp.PV_MODULE.value, InvestitionTyp.SPEICHER.value)
    }

    for inv in investitionen:
        if inv.typ == InvestitionTyp.WECHSELRICHTER.value:
            pv_systeme[inv.id] = {"wr": inv, "pv_module": [], "speicher": []}
        elif (
            inv.typ == InvestitionTyp.BALKONKRAFTWERK.value
            and inv.id in benannte_parents
        ):
            pv_systeme[inv.id] = {"wr": inv, "pv_module": [], "speicher": []}

    for inv in investitionen:
        if inv.id in pv_systeme:
            continue  # Trägergerät, bereits im ersten Pass registriert
        elif inv.typ == InvestitionTyp.PV_MODULE.value:
            if inv.parent_investition_id and inv.parent_investition_id in pv_systeme:
                pv_systeme[inv.parent_investition_id]["pv_module"].append(inv)
            else:
                # PV-Modul ohne Träger-Zuordnung
                orphan_pv_module.append(inv)
        elif inv.typ == InvestitionTyp.SPEICHER.value:
            if inv.parent_investition_id and inv.parent_investition_id in pv_systeme:
                # DC-gekoppelter Speicher am Hybrid-WR oder am BKW
                pv_systeme[inv.parent_investition_id]["speicher"].append(inv)
            else:
                # AC-gekoppelter Speicher - eigenständig
                standalone.append(inv)
        else:
            # E-Auto, Wärmepumpe, Wallbox, BKW ohne Kinder, Sonstiges
            standalone.append(inv)

    return pv_systeme, standalone, orphan_pv_module

# =============================================================================
# ROI Berechnungen
# =============================================================================

class ROIKomponente(BaseModel):
    """Eine Komponente innerhalb eines PV-Systems."""
    investition_id: int
    bezeichnung: str
    typ: str  # pv-module, wechselrichter, speicher
    kosten: float
    kosten_alternativ: float
    relevante_kosten: float
    einsparung: Optional[float]  # Nur für PV-Module/Speicher, None für WR
    co2_einsparung_kg: Optional[float]
    detail: dict[str, Any]

class ROIBerechnung(BaseModel):
    """Ergebnis einer ROI-Berechnung für eine Investition oder ein PV-System."""
    investition_id: int  # Bei System: ID des Wechselrichters
    investition_bezeichnung: str
    investition_typ: str  # "pv-system" für aggregiert, sonst normal
    anschaffungskosten: float
    anschaffungskosten_alternativ: float
    relevante_kosten: float
    # F-19: der tatsächliche Nenner von `roi_prozent` und `amortisation_jahre`
    # = relevante Kosten + kumulierte sonstige Netto-KOSTEN. Ohne dieses Feld
    # könnte die Oberfläche ihren eigenen Rechenweg nicht mehr ausschreiben —
    # sie zeigt „Relevant ÷ Einsparung" an, und das wäre dann eine andere Zahl.
    # `relevante_kosten` behält seine Bedeutung (Mehrkosten = USt-Grundlage,
    # N-137). Default für Altbestand/Tests, die die Zeile direkt bauen.
    kapitaleinsatz: float = 0.0
    # N-525: das Jahr, ab dem diese Zeile in der Kalender-Treppe zählt — bei
    # einem PV-System die früheste Anschaffung seiner Komponenten. None ohne
    # gepflegtes Datum (dann zählt die Zeile ab `basis_jahr` bzw. Index 0).
    anschaffungsjahr: Optional[int] = None
    jahres_einsparung: float
    roi_prozent: Optional[float]
    amortisation_jahre: Optional[float]
    # Konzept §5/§8-6: die Dauer nennt ihre Annahme. Der Text kommt aus dem
    # Layer-SoT (`kapitalrechnung.annahme_dauer_text`) und richtet sich nach
    # den Daten dieser Zeile — mit gepflegten Betriebskosten rechnet eedc
    # Modell C statt A, und dann wäre „ohne künftige Instandhaltung" falsch.
    amortisation_annahme: Optional[str] = None
    co2_einsparung_kg: Optional[float]
    detail_berechnung: dict[str, Any]
    komponenten: Optional[list[ROIKomponente]] = None  # Für PV-Systeme

@dataclass
class _SpeicherRoi:
    """Das ROI-Ergebnis eines Speichers samt der Quellen seiner Eingaben.

    Existiert seit **F-37**. Vorher rechneten der DC-Zweig (Speicher am
    Trägergerät) und der AC-Zweig (eigenständiger Speicher) dieselbe Kette
    getrennt herunter — und beide erst **innerhalb** ihrer Schleife. Der Fix
    braucht die Beträge aber **vor** der Verteilung der PV-Ersparnis, weil er
    den PV-Anteil des Speichers aus demselben Topf nimmt statt ihn
    danebenzustellen. Der Helper macht beides möglich: eine Rechnung, dreimal
    gerufen (Vorablauf, DC-Zweig, AC-Zweig).
    """

    result: Optional[Any]
    kapazitaet_fehlt: bool
    param_wirkungsgrad: float
    wirkungsgrad_eff: float
    wirkungsgrad_quelle: str
    lade_preis_eff: Optional[float]
    ladepreis_quelle: str
    nutzt_arbitrage: bool
    ist_aggregat: Any = None

    @property
    def pv_anteil_euro(self) -> float:
        """Der Teil der Ersparnis, der aus PV-Strom stammt — der doppelte (F-37).

        Der **Netz**-Anteil bleibt außen vor: er entsteht aus der Tarifdifferenz
        beim Laden aus dem Netz und steckt gerade **nicht** im PV-Eigenverbrauch.
        Ihn mitzukürzen nähme einem Arbitrage-Speicher echte Ersparnis.
        """
        return getattr(self.result, "pv_anteil_euro", 0.0) or 0.0 if self.result else 0.0

    @property
    def co2_pv_kg(self) -> float:
        """CO₂ aus dem PV-Anteil — dieselbe Doppelzählung eine Spalte weiter."""
        return getattr(self.result, "co2_einsparung_kg", 0.0) or 0.0 if self.result else 0.0

def _speicher_roi(
    inv: Any,
    *,
    strompreis_cent: float,
    einspeiseverguetung_cent: float,
    ist_aggregat: Any,
    eff_ladepreis: Any,
    eta_ist: Any,
    entlade_preis_cent: float = 0,
) -> _SpeicherRoi:
    """Ersparnis eines Speichers, mit der Auflösung seiner Eingaben (F-37).

    Wortgleich zu dem, was bis v4.0.19 in beiden Schleifen stand — der
    ``entlade_preis_cent`` bleibt Parameter, weil der DC-Zweig ihn nie übergeben
    hat und der AC-Zweig schon. Diese Asymmetrie ist **Bestand** und wird hier
    bewusst nicht eingeebnet; sie einzuebnen bewegte Zahlen für Arbitrage-
    Speicher und gehört nicht in den Bau von F-37.
    """
    # Lokal wie in der Route: `calculations` bleibt aus dem Modul-Import
    # heraus (dort steht dieselbe Zeile mit derselben Begründung).
    from backend.core.calculations import berechne_speicher_einsparung

    params = inv.parameter or {}
    kapazitaet_netto = get_speicher_nutzbare_kapazitaet_kwh(inv)
    # N-571: param_zahl statt roher .get — ein geleertes Feld ("") lief sonst
    # bis in die Formel (calculations.py:285 bzw. speicher_wirtschaftlichkeit
    # :230) und beendete die ganze ROI-Sicht mit TypeError/500.
    wirkungsgrad = param_zahl(
        params,
        PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"],
        PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"],
    )
    # Bug #5 v3.25.0: vorher 'nutzt_arbitrage' (toter Schema-Key), Form/Wizard
    # schreiben 'arbitrage_faehig'.
    nutzt_arbitrage = params.get(
        PARAM_SPEICHER["ARBITRAGE_FAEHIG"],
        PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"],
    )
    lade_preis = param_zahl(
        params,
        PARAM_SPEICHER["LADE_DURCHSCHNITTSPREIS_CENT"],
        PARAM_SPEICHER_DEFAULTS["lade_durchschnittspreis_cent"],
    )

    wirkungsgrad_eff, wirkungsgrad_quelle = _aufloesen_wirkungsgrad(
        eta_ist, param_wirkungsgrad=wirkungsgrad,
    )
    lade_preis_eff, ladepreis_quelle = _aufloesen_ladepreis(
        eff_ladepreis,
        nutzt_arbitrage=nutzt_arbitrage,
        param_lade_preis=lade_preis,
    )

    # N127: ohne Kapazität und ohne IST-Messung gibt es keine Basis — dann
    # entfällt der Beitrag, statt eine erfundene Zahl zu bauen.
    kapazitaet_fehlt = kapazitaet_netto is None and ist_aggregat is None
    result = None if kapazitaet_fehlt else berechne_speicher_einsparung(
        kapazitaet_kwh=kapazitaet_netto or 0,
        wirkungsgrad_prozent=wirkungsgrad_eff,
        netzbezug_preis_cent=strompreis_cent,
        einspeiseverguetung_cent=einspeiseverguetung_cent,
        nutzt_arbitrage=nutzt_arbitrage,
        lade_preis_cent=lade_preis_eff,
        entlade_preis_cent=entlade_preis_cent,
        ist_entladung_kwh=ist_aggregat.entladung_kwh_jahr if ist_aggregat else None,
        ist_ladung_netz_kwh=ist_aggregat.ladung_netz_kwh_jahr if ist_aggregat else 0,
    )
    return _SpeicherRoi(
        result=result,
        kapazitaet_fehlt=kapazitaet_fehlt,
        param_wirkungsgrad=wirkungsgrad,
        wirkungsgrad_eff=wirkungsgrad_eff,
        wirkungsgrad_quelle=wirkungsgrad_quelle,
        lade_preis_eff=lade_preis_eff,
        ladepreis_quelle=ladepreis_quelle,
        nutzt_arbitrage=nutzt_arbitrage,
        ist_aggregat=ist_aggregat,
    )

def _bkw_pauschal_beitrag(
    inv: Any,
    *,
    strompreis_cent: float,
    einspeiseverguetung_cent: float,
) -> tuple[float, float, float]:
    """Die pauschale Jahres-Schätzung eines Balkonkraftwerks.

    Liefert ``(jahres_ertrag_kwh, jahres_einsparung_euro, co2_kg)``.

    **Warum es diesen Helper gibt (F-33, #381).** Die Formel stand allein im
    standalone-Zweig der ROI-Typkette. Seit ein BKW Systemkopf sein kann,
    braucht sie einen **zweiten** Aufrufer — und eine zweite Kopie wäre genau
    die Klasse, gegen die der vierte ADR-001-Nachtrag geschrieben ist: eine
    Formel ist nicht durchgesetzt, solange eine Kopie danebensteht.

    **Die Nennleistung kommt über den SoT-Helper (F-35, ADR-002/P3-a).** Hier
    stand ``params.get('leistung_wp', 800)`` — die Leistung **eines** Moduls,
    ohne ``anzahl``. Ein Balkonkraftwerk mit 4 × 500 Wp rechnete damit mit
    500 Wp statt 2.000 und meldete **ein Viertel** seiner Ersparnis. Genau so
    entstehen die 115 €, die in der Tabelle aus #381 unter dem Balkonkraftwerk
    stehen (500 × 0,9 × 0,8 × 0,3195 = 115,02 €) — der Melder hat den Fehler
    also mitgeliefert, ohne ihn zu kennen. Dieselbe Klasse wie #229: eine
    Größe, die je nach Herkunft an zwei Orten liegt, roh gelesen.
    ``get_bkw_kwp`` ist der Ort, an dem beide Formen zusammenlaufen.

    ⚠ **Der 800-Wp-Default bleibt vorerst** — er greift jetzt nur noch, wenn
    ``get_bkw_kwp`` **gar nichts** findet (weder Spalte noch ``kwp`` noch
    ``leistung_wp``). Genau genommen ist er dieselbe Sorte Annahme, die N127
    beim Speicher entfernt hat („keine Kapazität ⇒ keine Rechnung, sondern ein
    Hinweis"), und ADR-002 ist gegen Defaults geschrieben, die wie eine
    Messung aussehen. Das ist ein **eigener** Befund (Register N-273), keine
    stille Mitnahme: ihn zu ziehen ändert die Zeile für Altbestand ohne
    gepflegte Leistung von einer Zahl auf „—".
    """
    # kWp → Wp: der Helper liefert kWp (Spalte, `parameter`-JSON oder
    # `leistung_wp × anzahl`), die Pauschale rechnet historisch in Wp.
    kwp = get_bkw_kwp(inv)
    leistung_wp = kwp * 1000 if kwp else 800
    # Vereinfachte Berechnung: ca. 0.9 kWh/Wp/Jahr in Deutschland
    jahres_ertrag = leistung_wp * 0.9
    # 80% Eigenverbrauch typisch bei Balkonkraftwerk
    eigenverbrauch = jahres_ertrag * 0.8
    einspeisung = jahres_ertrag * 0.2

    # §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh = None bei dieser
    # synthetischen BKW-Schätzung → volle Einspeisung (verhaltensneutral).
    einspeise_erloes = einspeise_erloes_euro(
        einspeisung, None, einspeiseverguetung_cent
    ).erloes_euro
    ev_ersparnis = eigenverbrauch * strompreis_cent / 100
    return (
        jahres_ertrag,
        einspeise_erloes + ev_ersparnis,
        jahres_ertrag * CO2_FAKTOR_STROM_KG_KWH,
    )

class AmortisationsVerlaufJahr(BaseModel):
    """Ein Jahr der Break-Even-Kurve (N-525): Kapitaleinsatz als Treppe, Einsparung
    kumuliert — beides aus `kapitalrechnung.amortisations_verlauf`, der Client
    zeichnet nur. `jahr` ist ein Kalenderjahr, oder ein Index ab 0, wenn keine
    Komponente ein Anschaffungsdatum trägt (`basis_jahr` None)."""
    jahr: int
    kapitaleinsatz_kumuliert_euro: float
    einsparung_kumuliert_euro: float

class ROIDashboardResponse(BaseModel):
    """Gesamte ROI-Übersicht für eine Anlage."""
    anlage_id: int
    anlage_name: str
    gesamt_investition: float
    gesamt_relevante_kosten: float
    # F-19 + Bauschritt 7: kumulierte sonstige AUSGABEN und ERTRÄGE (beide als
    # positiver Betrag) und der daraus gebildete Nenner
    # `relevante + ausgaben − ertraege`. `gesamt_relevante_kosten` bleibt die
    # Mehrkosten-Größe (SoT `core/berechnungen/kapitalrechnung.py`).
    gesamt_sonstige_ausgaben_euro: float = 0.0
    gesamt_sonstige_ertraege_euro: float = 0.0
    gesamt_kapitaleinsatz: float = 0.0
    gesamt_jahres_einsparung: float
    gesamt_roi_prozent: Optional[float]
    gesamt_amortisation_jahre: Optional[float]
    # Kalender-Anker für die Amortisations-Kurve (Radiocarbonat, Forum v4.0.0):
    # frühestes Anschaffungsjahr der berücksichtigten Investitionen = „Jahr 0"
    # der Break-Even-Kurve. `gesamt_amortisation_jahr` ist das daraus abgeleitete
    # voraussichtliche Break-Even-Kalenderjahr. Beide `None`, wenn kein
    # Anschaffungsdatum gepflegt ist bzw. die Amortisation offen bleibt.
    basis_jahr: Optional[int] = None
    gesamt_amortisation_jahr: Optional[int] = None
    # N-525: die Kurve selbst. Jede ROI-Zeile zählt Kosten und Einsparung ab
    # ihrem Anschaffungsjahr, sonstige Ausgaben/Erträge im Jahr ihrer Buchung.
    # `gesamt_amortisation_jahr` ist seither der Schnittpunkt DIESER Reihe
    # (F-19: Kachel und Kurve nennen dasselbe Jahr), nicht mehr basis + ⌈Dauer⌉ —
    # beides fällt nur bei einer Anlage zusammen, die auf einmal gebaut wurde.
    amortisations_verlauf: list[AmortisationsVerlaufJahr] = []
    # Konzept §5/§8-6 — die Annahme hinter der Gesamt-Dauer, aus demselben
    # Layer-SoT wie die Zeilen. Sie gilt für Kachel, Break-Even-Kurve und
    # Summenzeile gemeinsam; ohne sie stünde in *Auswertungen → ROI* eine
    # Zukunftsaussage ohne genannte Voraussetzung.
    amortisation_annahme: Optional[str] = None
    gesamt_co2_einsparung_kg: float
    berechnungen: list[ROIBerechnung]
    # Vorgeschlagener Default-Wert für den Benzinpreis-Slider (UI): letzter
    # `Monatsdaten.kraftstoffpreis_euro` aus dem EU Weekly Oil Bulletin, sonst
    # der Param-Default. Nur ein Hinweis — bei E-Auto-Berechnungen wird pro
    # Investition aufgelöst (Slider → per-Inv-Param → Monatsdaten → Default).
    benzinpreis_hinweis_euro: Optional[float] = None

def _achse_gilt(params: dict, feld: str) -> bool:
    """Gilt diese Wärme-Achse am Gerät? — **die Registry antwortet, nie die Bauart.**

    WK-15c/R1 (ADR-002/P13). ``feld`` ist ``"heizenergie_kwh"`` (Heiz-Achse) oder
    ``"warmwasser_kwh"`` (Warmwasser-Achse); `URTEIL_GILT` heißt *uneingeschränkt
    vorhanden*. Eine **Brauchwasser**-WP hat keine Heiz-Achse (`!brauchwasser`,
    weich), eine **Split-Klimaanlage** keinen Warmwasserkreis (`!luft_luft`,
    hart — N-304).

    ⚠ **`feld_urteil` und nicht `groesse_gibt_es_am_geraet`** — das liefert an der
    Brauchwasser-WP `True`, weil die Bedingung dort weich ist („untypisch, nicht
    unmöglich": wer doch einen kleinen Heizkreis hat, darf seinen Zähler
    behalten). Für den **Lesepfad** einer gemessenen Menge ist das richtig; für
    die Frage, ob eine **geschätzte** Achse eine Geldzahl tragen darf, ist es zu
    weit. Dieselbe Trennlinie wie in `daten_checker/stammdaten.py` (WK-15b).
    """
    return feld_urteil("waermepumpe", feld, params) == URTEIL_GILT

def _wp_nicht_bewertbar(params: dict) -> Optional[str]:
    """Warum lässt sich diese Wärmepumpe nicht gegen eine Altanlage rechnen?

    Gibt den Anzeige-Hinweis zurück (truthy) oder ``None``, wenn die Bewertung
    laufen darf. **Drei** Gründe, alle **gepflegt statt geraten** (N-88/F2b):

    1. **Es wurde nichts ersetzt.** Dann gibt es keinen Vergleichsgegenstand —
       unabhängig von der Bauart. Ein Neubau ohne Vorgängerheizung, eine
       Klimaanlage, die nur kühlt.
    2. **An den Achsen dieses Geräts steht nur die alte Vorbelegung**
       (12.000/3.000). Sie beschreibt ein Haus mit Heizung *und* Warmwasser;
       fehlt dem Gerät eine der beiden Achsen, ist sie keine Antwort, sondern
       eine offene Frage (WK-15c — der Absatz im Rumpf nennt die Messung).
    3. **Es ist kein Wärmebedarf gepflegt.** Die ROI-Zeile ist eine *Prognose*
       aus Bedarf × JAZ/COP, nicht die gemessene Ersparnis. Ohne Bedarf gäbe es
       nichts zu rechnen — bis 2026-08-16 sprang hier ein Default von 12.000 +
       3.000 kWh ein und erfand damit die Eingabe, die fehlte. **Ein Bedarf auf
       einer Achse, die es am Gerät nicht gibt, zählt dabei nicht mit.**

    ⚠ **Sichtbare Folge für Bestandsanlagen:** Eine Wärmepumpe, die nie über das
    Investitionsformular gespeichert wurde (Import, Setup-Wizard), trug bisher
    diese 12.000/3.000 stillschweigend und bekam daraus eine Zeile. Sie steht
    jetzt als „nicht bewertet" da, bis der Bedarf gepflegt ist. Das ist der
    Punkt: Die alte Zahl war keine Schätzung des Anwenders, sondern eine
    Behauptung von eedc.
    """
    if ersetzt_keine_heizung(params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])):
        return (
            'Nicht bewertet: Für dieses Gerät ist „nichts ersetzt (Neubau)" '
            'hinterlegt — es gibt also keine frühere Heizung, gegen die sich '
            'eine Ersparnis rechnen ließe. Stromverbrauch, PV-Anteil und Kosten '
            'werden unverändert ausgewertet.'
        )
    # Bestandsschutz gegen den K-0b-Phantomwert, ohne Daten still zu ändern:
    # Das Investitionsformular hat die Vorbelegung 12.000/3.000 bis v4.0.6
    # MITGESPEICHERT, und seit K-0b sind die zwei Felder für Klimaanlagen
    # unsichtbar — der Anwender konnte den Wert seither weder sehen noch
    # korrigieren. Er als „gepflegt" zu lesen, gäbe genau diesen Geräten die
    # 1.100 €/Jahr zurück, die K-0b abgeschafft hat.
    #
    # Deshalb: exakt die unveränderte Vorbelegung an einer Luft-Luft-WP zählt
    # nicht als Antwort, sondern als offene Frage — Befund plus Weg heraus,
    # statt eine Migration, die rät ([[feedback_kein_grosser_heiler_knopf]]).
    # Wer wirklich damit heizt, trägt seinen echten Bedarf ein und bekommt die
    # Bewertung; wer nur kühlt, wählt „nichts ersetzt". Für klassische
    # Wärmepumpen bleibt die Vorbelegung eine brauchbare Schätzung und wird
    # unverändert gerechnet — dort war sie immer sichtbar und änderbar.
    # ⭐ **WK-15c: dieselbe Sperre, an der Achse statt an der Bauart.** Sie galt
    # bis zum 14.09.2026 nur für `luft_luft` — und ließ damit genau den Fall
    # durch, der sie ausgelöst hat: Das Formular belegt `heizwaermebedarf_kwh`
    # auch an einer **Brauchwasser**-WP mit 12.000 vor (die Ausnahme in
    # `investitionFormHelpers.ts` kannte nur `luft_luft`), und daraus wurden
    # **714,29 €/Jahr und 1.721 kg CO₂** — gemessen; mit `heiz = 0` sind es
    # 142,86 € und 344 kg. **571 € erfundene Ersparnis** für Heizwärme, die das
    # Gerät nie abgibt. Exakt die K-0b-Bauform, nur eine Bauart weiter.
    #
    # Die Verallgemeinerung fragt die **Achsen**: Die Vorbelegung 12.000/3.000
    # beschreibt ein Haus mit Heizung **und** Warmwasser. Fehlt dem Gerät eine
    # der beiden Achsen, passt das Paar als Ganzes nicht — dann zählt es als
    # offene Frage, nicht als Antwort. Wo **beide** Achsen gelten (klassische
    # Wärmepumpe), bleibt es unverändert eine brauchbare Schätzung und wird
    # gerechnet; dort war die Zahl immer sichtbar und änderbar.
    #
    # ⚠ **Die Bedingung ist ein Oberbegriff der alten, nicht ihr Ersatz:** Jedes
    # Gerät, das bisher gesperrt war, bleibt gesperrt (`luft_luft` mit beiden
    # Defaults erfüllt sie weiter). Neu gesperrt ist, wessen **geltende** Achse
    # nur die Vorbelegung trägt — an einer Klimaanlage also auch dann, wenn
    # jemand daneben einen Warmwasserbedarf gepflegt hat: Der zählt an einem
    # Gerät ohne Warmwasserkreis ohnehin nicht mehr mit (N-304), und übrig
    # bliebe allein die vorbelegte Heizwärme.
    #
    # ⛔ Ein gepflegter **Gesamtbedarf** (`waermebedarf_kwh`, nur über Importe
    # erreichbar) ist eine echte Antwort und hebt die Sperre auf.
    heiz_gilt = _achse_gilt(params, "heizenergie_kwh")
    ww_gilt = _achse_gilt(params, "warmwasser_kwh")
    nur_vorbelegung = (
        not (heiz_gilt and ww_gilt)
        and not params.get(PARAM_WAERMEPUMPE["WAERMEBEDARF_KWH"])
        and (
            not heiz_gilt
            or params.get(PARAM_WAERMEPUMPE["HEIZWAERMEBEDARF_KWH"])
            == PARAM_WAERMEPUMPE_DEFAULTS["heizwaermebedarf_kwh"]
        )
        and (
            not ww_gilt
            or params.get(PARAM_WAERMEPUMPE["WARMWASSERBEDARF_KWH"])
            == PARAM_WAERMEPUMPE_DEFAULTS["warmwasserbedarf_kwh"]
        )
    )
    if nur_vorbelegung:
        # Der Weg heraus hängt daran, welche Achse das Gerät hat — ein Rat, der
        # auf eine nicht vorhandene Achse zeigt, wäre so wenig auflösbar wie der
        # Hinweis, den WK-15b abgeschafft hat.
        weg = (
            'Heizt du mit dem Gerät, trag deinen tatsächlichen Bedarf ein; '
            'kühlst du nur, wähle beim ersetzten Energieträger „nichts ersetzt".'
            if heiz_gilt else
            'Trag deinen tatsächlichen Warmwasserbedarf ein; hat das Gerät keine '
            'frühere Anlage ersetzt, wähle beim ersetzten Energieträger '
            '„nichts ersetzt".'
        )
        return (
            'Nicht bewertet: Bei diesem Gerät steht noch die alte Vorbelegung von '
            '12.000 kWh Heizwärme und 3.000 kWh Warmwasser — Werte, die eedc früher '
            f'selbst eingesetzt hat. {weg} Stromverbrauch, PV-Anteil und Kosten '
            'werden unverändert ausgewertet.'
        )
    # ⚠ **Ein Bedarf auf einer Achse, die es am Gerät nicht gibt, ist kein
    # Bedarf** (WK-15c). Sonst liefe der Rechenzweig unten an — und lieferte,
    # weil er dieselbe Achse auf 0 setzt, eine **0-€-Zeile** statt der
    # ehrlichen Auskunft „nicht bewertet": eine Null, die wie ein Messergebnis
    # aussieht, ist die schlechtere Falschaussage (dieselbe Unterscheidung wie
    # beim AC-Speicher ohne Kapazität).
    hat_bedarf = bool(
        params.get(PARAM_WAERMEPUMPE["WAERMEBEDARF_KWH"])
        or (heiz_gilt and params.get(PARAM_WAERMEPUMPE["HEIZWAERMEBEDARF_KWH"]))
        or (ww_gilt and params.get(PARAM_WAERMEPUMPE["WARMWASSERBEDARF_KWH"]))
    )
    if not hat_bedarf:
        # Der Rat nennt nur Achsen, die es am Gerät gibt (WK-15c) — eine
        # Brauchwasser-WP nach dem Heizwärmebedarf zu fragen, ist genau der
        # Hinweis, den WK-15b im Daten-Checker abgeschafft hat.
        felder = (
            'den Heizwärme- und Warmwasserbedarf' if heiz_gilt and ww_gilt
            else 'deinen Warmwasserbedarf' if ww_gilt
            else 'deinen Heizwärmebedarf'
        )
        return (
            'Nicht bewertet: Für dieses Gerät ist kein Wärmebedarf gepflegt. '
            f'Trag {felder} pro Jahr ein (Energieausweis '
            'oder Schätzung), oder wähle beim ersetzten Energieträger „nichts '
            'ersetzt", wenn es keine Vorgängerheizung gab. Stromverbrauch, '
            'PV-Anteil und Kosten werden unverändert ausgewertet.'
        )
    return None

def _angezeigte_jahres_einsparung(
    *, jahres_einsparung: float, betriebskosten: float, detail: Any
) -> float:
    """Die Zahl, die in der Spalte *Jahres-Einsparung* landet — und in der Summe.

    **N-258.** Bis 2026-08-16 stand hier unbedingt
    ``jahres_einsparung - betriebskosten``. Bei einer Zeile, für die eedc gar
    keine Ersparnis bewertet (``nicht_bewertet``), ergab das ``0 - 200`` — also
    **−200 € „Einsparung"** für ein Gerät, dessen Hinweistext mit „Nicht
    bewertet: …" beginnt. Gemessen an der Demo-Wärmepumpe: die Anlagen-Summe
    fiel um 1.555 € statt um die 1.355 € der entfallenen Ersparnis.

    ⚠ **Es war nie ein Rechenfehler** — die Betriebskosten fallen real an. Die
    Behauptung war falsch: Eine Zahl in der *Einsparungs*-Spalte sagt „so viel
    spart dieses Gerät", und genau das ist hier unbekannt.

    **Die Betriebskosten bleiben deshalb überall sonst stehen** — in
    ``gesamt_betriebskosten`` und in ``berechne_roi`` (dort als eigenes
    Argument, nicht als negativer Zähler). Unterdrückt wird ausschließlich der
    Anzeige- und Summenbeitrag, den die Oberfläche ohnehin als „—" zeigt.
    """
    if isinstance(detail, dict) and detail.get('nicht_bewertet'):
        return 0.0
    return jahres_einsparung - betriebskosten

@router.get("/roi/{anlage_id}", response_model=ROIDashboardResponse)
async def get_roi_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis in Cent/kWh (auto aus DB wenn leer)"),
    einspeiseverguetung_cent: Optional[float] = Query(None, description="Override: Einspeisevergütung in Cent/kWh (auto aus DB wenn leer)"),
    benzinpreis_euro: Optional[float] = Query(None, description="Override: Benzinpreis in Euro/Liter (Slider). Bei None: per-Inv-Param → letzter Monatsdaten-Preis → Default 1,65."),
    jahr: Optional[int] = Query(None, description="Jahr für Auswertung (None = alle Jahre)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Berechnet ROI für alle aktiven Investitionen einer Anlage.

    PV-Systeme (Wechselrichter + zugeordnete PV-Module + DC-Speicher) werden
    als aggregierte Einheit berechnet, da der ROI nur auf System-Ebene sinnvoll ist.

    Args:
        anlage_id: ID der Anlage
        strompreis_cent: Aktueller Strompreis für Berechnungen
        einspeiseverguetung_cent: Aktuelle Einspeisevergütung
        benzinpreis_euro: Aktueller Benzinpreis für E-Auto-Vergleich
        jahr: Optionales Jahr für die Auswertung (None = alle Jahre)

    Returns:
        ROIDashboardResponse: Vollständige ROI-Übersicht
    """
    from backend.core.calculations import berechne_roi
    from backend.services.ust_satz import ust_hochrechnung
    from backend.core.berechnungen.kapitalrechnung import (
        amortisations_verlauf,
        annahme_dauer_text,
        kapitaleinsatz_euro,
    )
    # Vorlage 5b: die Phasen liegen in roi_eingaenge / roi_pv / roi_standalone. Sie importieren
    # Helfer und Schemas aus DIESEM Modul — der Import steht deshalb hier im Endpunkt, nicht auf
    # Modulebene (Importzyklus). Dieselbe Bauform wie die Lazy-Importe der Energieprofil-Routen.
    from backend.api.routes.investitionen.roi_eingaenge import lade_roi_eingaenge
    from backend.api.routes.investitionen.roi_pv import pv_einsparung_und_speicher_ist, pv_systeme_zeilen, orphan_modul_zeilen
    from backend.api.routes.investitionen.roi_standalone import standalone_zeilen

    # ── lade_roi_eingaenge (Vorlage 5b: Phase in roi_eingaenge.py, Schnittstelle 5 ein / 18 aus) ──
    _out = await lade_roi_eingaenge(
        anlage_id=anlage_id,
        db=db,
        einspeiseverguetung_cent=einspeiseverguetung_cent,
        jahr=jahr,
        strompreis_cent=strompreis_cent,
    )
    if "_anlage_fakten" in _out: _anlage_fakten = _out["_anlage_fakten"]
    if "_ist_pv_ladeanteil" in _out: _ist_pv_ladeanteil = _out["_ist_pv_ladeanteil"]
    if "_sonstige_ausgaben_kumuliert_fuer" in _out: _sonstige_ausgaben_kumuliert_fuer = _out["_sonstige_ausgaben_kumuliert_fuer"]
    if "_sonstige_ertraege_kumuliert_fuer" in _out: _sonstige_ertraege_kumuliert_fuer = _out["_sonstige_ertraege_kumuliert_fuer"]
    if "_treppe_zeile" in _out: _treppe_zeile = _out["_treppe_zeile"]
    if "anlage" in _out: anlage = _out["anlage"]
    if "anlage_sonstige_ausgaben" in _out: anlage_sonstige_ausgaben = _out["anlage_sonstige_ausgaben"]
    if "anlage_sonstige_ertraege" in _out: anlage_sonstige_ertraege = _out["anlage_sonstige_ertraege"]
    if "basis_jahr" in _out: basis_jahr = _out["basis_jahr"]
    if "benzinpreis_hinweis_euro" in _out: benzinpreis_hinweis_euro = _out["benzinpreis_hinweis_euro"]
    if "einspeiseverguetung_cent" in _out: einspeiseverguetung_cent = _out["einspeiseverguetung_cent"]
    if "ersparnis_zeilen" in _out: ersparnis_zeilen = _out["ersparnis_zeilen"]
    if "investitionen" in _out: investitionen = _out["investitionen"]
    if "kapital_ereignisse" in _out: kapital_ereignisse = _out["kapital_ereignisse"]
    if "letzter_marktpreis" in _out: letzter_marktpreis = _out["letzter_marktpreis"]
    if "strompreis_cent" in _out: strompreis_cent = _out["strompreis_cent"]
    if "wallbox_strompreis" in _out: wallbox_strompreis = _out["wallbox_strompreis"]
    if "wp_strompreis" in _out: wp_strompreis = _out["wp_strompreis"]
    # ==========================================================================
    # Phase 1: Gruppiere Investitionen nach PV-Systemen und Standalone
    # ==========================================================================
    # Strukturierung extrahiert nach modul-internem `_gruppiere_investitionen`
    # (rein, DB-/Anzeige-frei). `pv_systeme`: wr_id -> {wr, pv_module[], speicher[]};
    # `orphan_pv_module`: PV-Module ohne WR-Zuordnung (Altdaten).
    pv_systeme, standalone, orphan_pv_module = _gruppiere_investitionen(investitionen)

    # ── pv_einsparung_und_speicher_ist (Vorlage 5b: Phase in roi_pv.py, Schnittstelle 7 ein / 16 aus) ──
    _out = await pv_einsparung_und_speicher_ist(
        _anlage_fakten=_anlage_fakten,
        anlage_id=anlage_id,
        db=db,
        einspeiseverguetung_cent=einspeiseverguetung_cent,
        investitionen=investitionen,
        jahr=jahr,
        strompreis_cent=strompreis_cent,
    )
    if "_relevante_kosten" in _out: _relevante_kosten = _out["_relevante_kosten"]
    if "berechnungen" in _out: berechnungen = _out["berechnungen"]
    if "gesamt_betriebskosten" in _out: gesamt_betriebskosten = _out["gesamt_betriebskosten"]
    if "gesamt_co2" in _out: gesamt_co2 = _out["gesamt_co2"]
    if "gesamt_einsparung" in _out: gesamt_einsparung = _out["gesamt_einsparung"]
    if "gesamt_investition" in _out: gesamt_investition = _out["gesamt_investition"]
    if "gesamt_relevante" in _out: gesamt_relevante = _out["gesamt_relevante"]
    if "gesamt_sonstige_ausgaben" in _out: gesamt_sonstige_ausgaben = _out["gesamt_sonstige_ausgaben"]
    if "gesamt_sonstige_ertraege" in _out: gesamt_sonstige_ertraege = _out["gesamt_sonstige_ertraege"]
    if "pv_co2" in _out: pv_co2 = _out["pv_co2"]
    if "pv_detail" in _out: pv_detail = _out["pv_detail"]
    if "pv_jahres_einsparung" in _out: pv_jahres_einsparung = _out["pv_jahres_einsparung"]
    if "speicher_eta_by_inv" in _out: speicher_eta_by_inv = _out["speicher_eta_by_inv"]
    if "speicher_invs_alle" in _out: speicher_invs_alle = _out["speicher_invs_alle"]
    if "speicher_ist_by_inv" in _out: speicher_ist_by_inv = _out["speicher_ist_by_inv"]
    if "speicher_ladepreis_anlage" in _out: speicher_ladepreis_anlage = _out["speicher_ladepreis_anlage"]
    # ── pv_systeme_zeilen (Vorlage 5b: Phase in roi_pv.py, Schnittstelle 26 ein / 11 aus) ──
    _out = pv_systeme_zeilen(
        _relevante_kosten=_relevante_kosten,
        _sonstige_ausgaben_kumuliert_fuer=_sonstige_ausgaben_kumuliert_fuer,
        _sonstige_ertraege_kumuliert_fuer=_sonstige_ertraege_kumuliert_fuer,
        _treppe_zeile=_treppe_zeile,
        basis_jahr=basis_jahr,
        berechnungen=berechnungen,
        einspeiseverguetung_cent=einspeiseverguetung_cent,
        gesamt_betriebskosten=gesamt_betriebskosten,
        gesamt_co2=gesamt_co2,
        gesamt_einsparung=gesamt_einsparung,
        gesamt_investition=gesamt_investition,
        gesamt_relevante=gesamt_relevante,
        gesamt_sonstige_ausgaben=gesamt_sonstige_ausgaben,
        gesamt_sonstige_ertraege=gesamt_sonstige_ertraege,
        investitionen=investitionen,
        orphan_pv_module=orphan_pv_module,
        pv_co2=pv_co2,
        pv_detail=pv_detail,
        pv_jahres_einsparung=pv_jahres_einsparung,
        pv_systeme=pv_systeme,
        speicher_eta_by_inv=speicher_eta_by_inv,
        speicher_invs_alle=speicher_invs_alle,
        speicher_ist_by_inv=speicher_ist_by_inv,
        speicher_ladepreis_anlage=speicher_ladepreis_anlage,
        standalone=standalone,
        strompreis_cent=strompreis_cent,
    )
    if "gesamt_betriebskosten" in _out: gesamt_betriebskosten = _out["gesamt_betriebskosten"]
    if "gesamt_co2" in _out: gesamt_co2 = _out["gesamt_co2"]
    if "gesamt_einsparung" in _out: gesamt_einsparung = _out["gesamt_einsparung"]
    if "gesamt_investition" in _out: gesamt_investition = _out["gesamt_investition"]
    if "gesamt_kwp" in _out: gesamt_kwp = _out["gesamt_kwp"]
    if "gesamt_relevante" in _out: gesamt_relevante = _out["gesamt_relevante"]
    if "gesamt_sonstige_ausgaben" in _out: gesamt_sonstige_ausgaben = _out["gesamt_sonstige_ausgaben"]
    if "gesamt_sonstige_ertraege" in _out: gesamt_sonstige_ertraege = _out["gesamt_sonstige_ertraege"]
    if "pv_co2" in _out: pv_co2 = _out["pv_co2"]
    if "pv_jahres_einsparung" in _out: pv_jahres_einsparung = _out["pv_jahres_einsparung"]
    if "speicher_roi_by_inv" in _out: speicher_roi_by_inv = _out["speicher_roi_by_inv"]
    # ── orphan_modul_zeilen (Vorlage 5b: Phase in roi_pv.py, Schnittstelle 18 ein / 7 aus) ──
    _out = orphan_modul_zeilen(
        _relevante_kosten=_relevante_kosten,
        _sonstige_ausgaben_kumuliert_fuer=_sonstige_ausgaben_kumuliert_fuer,
        _sonstige_ertraege_kumuliert_fuer=_sonstige_ertraege_kumuliert_fuer,
        _treppe_zeile=_treppe_zeile,
        basis_jahr=basis_jahr,
        berechnungen=berechnungen,
        gesamt_betriebskosten=gesamt_betriebskosten,
        gesamt_co2=gesamt_co2,
        gesamt_einsparung=gesamt_einsparung,
        gesamt_investition=gesamt_investition,
        gesamt_kwp=gesamt_kwp,
        gesamt_relevante=gesamt_relevante,
        gesamt_sonstige_ausgaben=gesamt_sonstige_ausgaben,
        gesamt_sonstige_ertraege=gesamt_sonstige_ertraege,
        orphan_pv_module=orphan_pv_module,
        pv_co2=pv_co2,
        pv_detail=pv_detail,
        pv_jahres_einsparung=pv_jahres_einsparung,
    )
    if "gesamt_betriebskosten" in _out: gesamt_betriebskosten = _out["gesamt_betriebskosten"]
    if "gesamt_co2" in _out: gesamt_co2 = _out["gesamt_co2"]
    if "gesamt_einsparung" in _out: gesamt_einsparung = _out["gesamt_einsparung"]
    if "gesamt_investition" in _out: gesamt_investition = _out["gesamt_investition"]
    if "gesamt_relevante" in _out: gesamt_relevante = _out["gesamt_relevante"]
    if "gesamt_sonstige_ausgaben" in _out: gesamt_sonstige_ausgaben = _out["gesamt_sonstige_ausgaben"]
    if "gesamt_sonstige_ertraege" in _out: gesamt_sonstige_ertraege = _out["gesamt_sonstige_ertraege"]
    # ── standalone_zeilen (Vorlage 5b: Phase in roi_standalone.py, Schnittstelle 25 ein / 7 aus) ──
    _out = await standalone_zeilen(
        _anlage_fakten=_anlage_fakten,
        _ist_pv_ladeanteil=_ist_pv_ladeanteil,
        _relevante_kosten=_relevante_kosten,
        _sonstige_ausgaben_kumuliert_fuer=_sonstige_ausgaben_kumuliert_fuer,
        _sonstige_ertraege_kumuliert_fuer=_sonstige_ertraege_kumuliert_fuer,
        _treppe_zeile=_treppe_zeile,
        basis_jahr=basis_jahr,
        benzinpreis_euro=benzinpreis_euro,
        berechnungen=berechnungen,
        einspeiseverguetung_cent=einspeiseverguetung_cent,
        gesamt_betriebskosten=gesamt_betriebskosten,
        gesamt_co2=gesamt_co2,
        gesamt_einsparung=gesamt_einsparung,
        gesamt_investition=gesamt_investition,
        gesamt_relevante=gesamt_relevante,
        gesamt_sonstige_ausgaben=gesamt_sonstige_ausgaben,
        gesamt_sonstige_ertraege=gesamt_sonstige_ertraege,
        letzter_marktpreis=letzter_marktpreis,
        speicher_eta_by_inv=speicher_eta_by_inv,
        speicher_ladepreis_anlage=speicher_ladepreis_anlage,
        speicher_roi_by_inv=speicher_roi_by_inv,
        standalone=standalone,
        strompreis_cent=strompreis_cent,
        wallbox_strompreis=wallbox_strompreis,
        wp_strompreis=wp_strompreis,
    )
    if "gesamt_betriebskosten" in _out: gesamt_betriebskosten = _out["gesamt_betriebskosten"]
    if "gesamt_co2" in _out: gesamt_co2 = _out["gesamt_co2"]
    if "gesamt_einsparung" in _out: gesamt_einsparung = _out["gesamt_einsparung"]
    if "gesamt_investition" in _out: gesamt_investition = _out["gesamt_investition"]
    if "gesamt_relevante" in _out: gesamt_relevante = _out["gesamt_relevante"]
    if "gesamt_sonstige_ausgaben" in _out: gesamt_sonstige_ausgaben = _out["gesamt_sonstige_ausgaben"]
    if "gesamt_sonstige_ertraege" in _out: gesamt_sonstige_ertraege = _out["gesamt_sonstige_ertraege"]
    # USt auf Eigenverbrauch bei Regelbesteuerung (reduziert Gesamt-Einsparung)
    steuerliche_beh = getattr(anlage, 'steuerliche_behandlung', None) or 'keine_ust'
    if steuerliche_beh == "regelbesteuerung" and pv_detail.get('erzeugung_kwh_jahr', 0) > 0:
        alle_inv_result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id)
        )
        alle_inv = alle_inv_result.scalars().all()
        # G1 (03.10.2026): Investitionsmenge aus dem EINEN Eingang `services/ust_satz.py` — im Kalenderjahr aktiv, für
        # Bemessung UND Betriebskosten (bis dahin: alle für die Bemessung, die heute aktiven für die Betriebskosten,
        # N-228). `*_kwh_jahr` ist eine auf zwölf Monate hochgerechnete Jahresmenge ⇒ ein Anteil, `monate=12`.
        # `jahr` ist hier nur das Etikett des Jahres; `isinstance` statt `jahr or …`, weil `= Query(None, …)` beim
        # direkten Funktionsaufruf das truthy `Query`-Objekt ablegt (N-111).
        ust_abzug = ust_hochrechnung(
            anlage, alle_inv, jahr if isinstance(jahr, int) else date.today().year,
            pv_detail.get('eigenverbrauch_kwh_jahr', 0), pv_detail.get('erzeugung_kwh_jahr', 0),
        )
        gesamt_einsparung -= ust_abzug

    # Die anlagenweiten Positionen wirken erst hier — sie gehören zu keiner
    # Zeile (Bauschritt 4). Beide Seiten gehen in den Nenner: die Ausgabe
    # erhöht ihn, der Ertrag mindert ihn (Bauschritt 7). Die Seiten-Zuordnung
    # ist dieselbe wie bei den komponentengebundenen.
    gesamt_sonstige_ausgaben += anlage_sonstige_ausgaben
    gesamt_sonstige_ertraege += anlage_sonstige_ertraege

    # Gesamt-ROI. Nenner ist der Kapitaleinsatz (F-19 + Bauschritt 7): die
    # relevanten Kosten plus die kumulierten sonstigen Ausgaben, minus die
    # kumulierten sonstigen Erträge. `gesamt_relevante` selbst bleibt unberührt
    # — es ist zugleich die USt-Bemessungsgrundlage (N-137), und dort hat weder
    # eine Reparatur noch eine Förderung etwas zu suchen.
    gesamt_kapitaleinsatz = kapitaleinsatz_euro(
        relevante_kosten_euro=gesamt_relevante,
        sonstige_ausgaben_euro=gesamt_sonstige_ausgaben,
        sonstige_ertraege_euro=gesamt_sonstige_ertraege,
    )
    gesamt_roi = berechne_roi(gesamt_kapitaleinsatz, gesamt_einsparung, 0)

    # N-525: Kalender-Treppe statt Anker + Dauer. Bis 2026-09-18 stand hier
    # `basis_jahr + ⌈Dauer⌉` — „dieselbe Näherung, die die Kurve ohnehin macht".
    # Jetzt macht die Kurve sie nicht mehr: der Layer stuft jede Zeile ab ihrem
    # Jahr, und das Break-Even-Jahr ist der Schnittpunkt dieser Reihe. Für eine
    # Anlage, die auf einmal gebaut wurde, ist das dieselbe Zahl (Probe im
    # Layer-Test); für eine gewachsene liegt es später — und stimmt.
    _verlauf = amortisations_verlauf(
        kapital=kapital_ereignisse, ersparnis=ersparnis_zeilen,
    )
    amortisations_verlauf_zeilen = [
        AmortisationsVerlaufJahr(
            jahr=p.jahr,
            kapitaleinsatz_kumuliert_euro=round(p.kapitaleinsatz_kumuliert_euro, 2),
            einsparung_kumuliert_euro=round(p.einsparung_kumuliert_euro, 2),
        )
        for p in _verlauf.jahre
    ]
    gesamt_amortisation_jahr = (
        _verlauf.break_even_jahr if basis_jahr is not None else None
    )

    return ROIDashboardResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        gesamt_investition=round(gesamt_investition, 2),
        gesamt_relevante_kosten=round(gesamt_relevante, 2),
        gesamt_sonstige_ausgaben_euro=round(gesamt_sonstige_ausgaben, 2),
        gesamt_sonstige_ertraege_euro=round(gesamt_sonstige_ertraege, 2),
        gesamt_kapitaleinsatz=round(gesamt_kapitaleinsatz, 2),
        gesamt_jahres_einsparung=round(gesamt_einsparung, 2),
        gesamt_roi_prozent=gesamt_roi['roi_prozent'],
        gesamt_amortisation_jahre=gesamt_roi['amortisation_jahre'],
        basis_jahr=basis_jahr,
        gesamt_amortisation_jahr=gesamt_amortisation_jahr,
        amortisations_verlauf=amortisations_verlauf_zeilen,
        amortisation_annahme=annahme_dauer_text(
            betriebskosten_jahr_euro=gesamt_betriebskosten,
        ),
        gesamt_co2_einsparung_kg=round(gesamt_co2, 1),
        berechnungen=berechnungen,
        benzinpreis_hinweis_euro=round(benzinpreis_hinweis_euro, 3),
    )
