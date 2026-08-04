"""
Monatsdaten API Routes

CRUD Endpoints für monatliche Energiedaten.
"""

from datetime import date
from typing import Annotated, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel, Field

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.core.calculations import (
    berechne_monatskennzahlen,
    MonatsKennzahlen,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.core.berechnungen import (
    berechne_finanz_aggregat,
    berechne_netzbezug_kosten,
)
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.utils.sonstige_positionen import ist_gueltige_position
from backend.core.field_definitions import get_feld_hinweise
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_netzbezug_preis_cent,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.services.monats_fakten import (
    TAGESWERT_BKW,
    TAGESWERT_PV,
    TAGESWERT_SPEICHER,
    finanz_zeile_eingabe,
    lade_monats_fakten,
)
from backend.services.provenance import (
    log_delete,
    seed_provenance,
    write_json_subkey_with_provenance,
    write_with_provenance,
)
from backend.services.pv_monatswerte import lade_pv_je_monat, pv_summe_je_monat


# Source-Tag-Konstanten (Etappe 3d Päckchen 3)
_MANUAL_WRITER = "monatsdaten_form"
_AUTO_WRITER = "monatsdaten_compute"

# Berechnete Aggregate werden serverseitig aus User-Eingaben abgeleitet.
# Source `auto:monatsabschluss` (Stufe 3) erlaubt einem späteren manuellen
# Override (Stufe 1), den abgeleiteten Wert zu schlagen — bewusst.
_COMPUTED_FIELDS = ("direktverbrauch_kwh", "eigenverbrauch_kwh", "gesamtverbrauch_kwh")


# =============================================================================
# Pydantic Schemas
# =============================================================================

class MonatsdatenBase(BaseModel):
    """Basis-Schema für Monatsdaten."""
    jahr: int = Field(..., ge=2000, le=2100)
    monat: int = Field(..., ge=1, le=12)
    einspeisung_kwh: float = Field(..., ge=0)
    netzbezug_kwh: float = Field(..., ge=0)
    pv_erzeugung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_entladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_netz_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladepreis_cent: Optional[float] = Field(None, ge=0)
    netzbezug_durchschnittspreis_cent: Optional[float] = Field(None, ge=0)
    kraftstoffpreis_euro: Optional[float] = Field(None, ge=0)
    gaspreis_cent_kwh: Optional[float] = Field(None, ge=0)
    globalstrahlung_kwh_m2: Optional[float] = Field(None, ge=0)
    sonnenstunden: Optional[float] = Field(None, ge=0)
    datenquelle: Optional[str] = Field(None, max_length=50)
    notizen: Optional[str] = Field(None, max_length=1000)
    # G19-1: Strukturierte sonstige Erträge & Ausgaben auf Anlage-Ebene
    # ([{bezeichnung, betrag, typ: ertrag|ausgabe}]). Leere Liste = bewusst
    # alle Positionen gelöscht; None = Feld nicht angefasst.
    sonstige_positionen: Optional[list[dict]] = None


class MonatsdatenCreate(MonatsdatenBase):
    """Schema für Monatsdaten-Erstellung."""
    anlage_id: int
    # Investitions-spezifische Monatsdaten (E-Auto km, Speicher Ladung, WP Verbrauch, etc.)
    investitionen_daten: Optional[dict[str, dict[str, Any]]] = None
    # PN 90128: bewusst behaltene Abweichungen je Basis-Feld
    # ({feld: {"sensor": …, "wert": …}}). Siehe Monatsdaten.geprueft_gegen.
    geprueft_gegen: Optional[dict[str, dict[str, float]]] = None


class MonatsdatenUpdate(BaseModel):
    """Schema für Monatsdaten-Update."""
    einspeisung_kwh: Optional[float] = Field(None, ge=0)
    netzbezug_kwh: Optional[float] = Field(None, ge=0)
    # Investitions-spezifische Monatsdaten
    investitionen_daten: Optional[dict[str, dict[str, Any]]] = None
    pv_erzeugung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_entladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_netz_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladepreis_cent: Optional[float] = Field(None, ge=0)
    netzbezug_durchschnittspreis_cent: Optional[float] = Field(None, ge=0)
    kraftstoffpreis_euro: Optional[float] = Field(None, ge=0)
    gaspreis_cent_kwh: Optional[float] = Field(None, ge=0)
    globalstrahlung_kwh_m2: Optional[float] = Field(None, ge=0)
    sonnenstunden: Optional[float] = Field(None, ge=0)
    notizen: Optional[str] = Field(None, max_length=1000)
    # G19-1: siehe MonatsdatenBase
    sonstige_positionen: Optional[list[dict]] = None
    # PN 90128: siehe MonatsdatenCreate. `{}` = alle Bestätigungen zurückgenommen.
    geprueft_gegen: Optional[dict[str, dict[str, float]]] = None


class KennzahlenResponse(BaseModel):
    """Berechnete Kennzahlen."""
    direktverbrauch_kwh: float
    gesamtverbrauch_kwh: float
    eigenverbrauch_kwh: float
    eigenverbrauchsquote_prozent: float
    autarkiegrad_prozent: float
    spezifischer_ertrag_kwh_kwp: Optional[float]
    einspeise_erloes_euro: float
    netzbezug_kosten_euro: float
    eigenverbrauch_ersparnis_euro: float
    netto_ertrag_euro: float
    co2_einsparung_kg: float


class MonatsdatenResponse(MonatsdatenBase):
    """Schema für Monatsdaten-Response."""
    id: int
    anlage_id: int
    direktverbrauch_kwh: Optional[float]
    eigenverbrauch_kwh: Optional[float]
    gesamtverbrauch_kwh: Optional[float]

    class Config:
        from_attributes = True


class MonatsdatenMitKennzahlen(MonatsdatenResponse):
    """Monatsdaten mit berechneten Kennzahlen."""
    kennzahlen: Optional[KennzahlenResponse] = None


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


# =============================================================================
# Aggregierte Monatsdaten (Zählerwerte + InvestitionMonatsdaten)
# =============================================================================

class AggregierteMonatsdatenResponse(BaseModel):
    """Monatsdaten mit aggregierten Werten aus InvestitionMonatsdaten.

    Komponenten-Aggregate sind Optional[float]: **None bedeutet "in dem
    Monat keine aktive Komponente dieses Typs"** (vor Anschaffung / nach
    Stilllegung / Anlage hat den Typ nicht), **0 bedeutet "Komponente
    aktiv, IMD vorhanden, Wert tatsächlich 0"** (z.B. Heizung im Sommer).
    Die Unterscheidung darf nicht durch Default-0 verwischt werden
    (CLAUDE.md "0-Werte prüfen" + #236).
    """
    # `None` = dieser Monat hat **keine Zählerzeile** (`Monatsdaten`-Datensatz) und
    # kommt nur mit `inkl_ohne_zaehlerzeile=true` in die Antwort. Er trägt dann
    # IMD-Mengen, aber keinen Datensatz, den man bearbeiten oder löschen könnte —
    # wer die Zeile verlinkt oder eine Edit-Aktion daran hängt, muss das prüfen.
    id: Optional[int]
    anlage_id: int
    jahr: int
    monat: int
    # Zählerwerte (aus Monatsdaten) — Anlage-weit, bleiben float
    einspeisung_kwh: float
    netzbezug_kwh: float
    globalstrahlung_kwh_m2: Optional[float]
    sonnenstunden: Optional[float]
    # Dynamischer Monats-Ø-Netzbezugspreis (Flex-Tarif, Tibber/aWATTar/EPEX).
    # None = kein Flex-Wert gepflegt → Frontend fällt auf den statischen Tarif
    # zurück (gleiche Quelle wie Cockpit via resolve_netzbezug_preis_cent, #326).
    netzbezug_durchschnittspreis_cent: Optional[float]
    # Aggregiert aus InvestitionMonatsdaten - PV
    #
    # ⚠️ ZWEI BEDEUTUNGEN, EIN NAME — bewusst so (A17, Namens-Schritt 1):
    # DIESES Response-Feld = **PV-Module + Balkonkraftwerk(e)**, gerechnet aus den
    # InvestitionMonatsdaten. Die DB-Spalte `Monatsdaten.pv_erzeugung_kwh` heißt
    # gleich, ist aber etwas anderes: das **manuell/importiert gepflegte
    # Gesamt-Aggregat der PV-Module** (Legacy-Feld, Eingang der Read-time-kWp-
    # Verteilung, siehe `core/berechnungen/pv_verteilung.py`). Beide liegen in
    # dieser Datei nebeneinander: das Feld entsteht unten aus den IMD, die Spalte
    # geht als `aggregat_kwh` in `resolve_pv_je_modul`.
    # **Nicht umbenannt**, weil der Identifier nach außen wirkt: MQTT-Topic-Segment
    # (`connector_mqtt_bridge.py`: `{prefix}/inv/{pv_inv}/pv_erzeugung_kwh`),
    # CSV-Spaltenname, JSON-Backup-Feld und `field_definitions`-Key. Eine
    # Umbenennung wäre ein Bruch nach außen, unabhängig von der Semantik-Frage.
    pv_erzeugung_kwh: Optional[float]  # Summe PV-Module + BKW (NICHT die DB-Spalte!)
    # R17/Verlauf-Vergleich: Module vs. BKW getrennt (Σ == pv_erzeugung_kwh).
    # Hieß bis A17 `pv_anlage_kwh` — irreführend, weil „PV-Anlage" im Produkt
    # überall die GANZE Anlage ist (der Komponenten-Hub „PV-Anlage" enthält
    # Wechselrichter, Module, Speicher UND Balkonkraftwerk), das Feld aber das
    # Gegenteil meint: Module OHNE BKW. Genau diese Verwechslung kostete `4ec3db60`
    # (zwei Stapel, die nicht zusammenpassten).
    pv_module_kwh: Optional[float]  # nur PV-Module (ohne BKW)
    bkw_kwh: Optional[float]  # nur Balkonkraftwerk(e)
    # Sonstige Erzeuger (typ=`sonstiges` + Kategorie `erzeuger`, z. B. BHKW) —
    # NICHT in `pv_erzeugung_kwh` enthalten (die bleibt rein PV), aber Teil der
    # Netzpunkt-Bilanz `erzeugung_hinter_zaehler_kwh` (v3.45.4), aus der
    # direktverbrauch/eigenverbrauch unten gerechnet werden. Ohne dieses Feld
    # kann eine UI die Verwendungsseite nicht in ihre Erzeuger zerlegen (A15/N43).
    sonstige_erzeugung_kwh: Optional[float]
    # Die Netzpunkt-Größe: ALLES, was hinter dem einen Hauszähler erzeugt wird
    # (`pv_module_kwh + bkw_kwh + sonstige_erzeugung_kwh`). Name aus dem Layer-SoT
    # `core/berechnungen/energie.py::erzeugung_hinter_zaehler_kwh` — bewusst nicht
    # „gesamt_erzeugung_kwh": „gesamt" beantwortet nicht, WOVON gesamt, und genau
    # der Netzpunkt-Bezug ist der Grund, dass es die Größe gibt (ein Erzeuger vor
    # dem Zähler oder an einem zweiten Netzpunkt gehörte nicht hinein).
    # Bisher musste jeder Konsument selbst summieren — zwei taten es schon
    # (`v4/komponentenAdapter.tsx`, `test_sonstiges_erzeuger_bilanz.py`).
    # ⚠️ Diese Größe darf NIE in eine PV-Kennzahl einfließen: spezifischer Ertrag
    # und Performance Ratio bleiben rein PV (v3.45.4) — der Brennstoff-Erzeuger
    # hätte im PV-Nenner nichts zu suchen und wäre ein stiller Rechenfehler.
    erzeugung_hinter_zaehler_kwh: Optional[float]
    # Aggregiert aus InvestitionMonatsdaten - Speicher
    speicher_ladung_kwh: Optional[float]  # Summe alle Speicher
    speicher_entladung_kwh: Optional[float]  # Summe alle Speicher
    speicher_netzladung_kwh: Optional[float]  # Anteil Netzladung an speicher_ladung_kwh (R17/Verlauf)
    # Aggregiert aus InvestitionMonatsdaten - Wärmepumpe
    wp_strom_kwh: Optional[float]
    wp_strom_heizen_kwh: Optional[float]  # Nur > 0 wenn getrennte_strommessung=True (#191)
    wp_strom_warmwasser_kwh: Optional[float]  # Nur > 0 wenn getrennte_strommessung=True (#191)
    wp_heizung_kwh: Optional[float]
    wp_warmwasser_kwh: Optional[float]
    # Aggregiert aus InvestitionMonatsdaten - E-Auto
    eauto_ladung_kwh: Optional[float]  # Summe PV + Netz
    eauto_km: Optional[float]
    # Aggregiert aus InvestitionMonatsdaten - Wallbox
    wallbox_ladung_kwh: Optional[float]
    wallbox_ladung_pv_kwh: Optional[float]
    # Berechnet
    direktverbrauch_kwh: float
    eigenverbrauch_kwh: float
    gesamtverbrauch_kwh: float
    autarkie_prozent: float
    eigenverbrauchsquote_prozent: float
    # §51 EEG: kWh, die bei negativem Börsenpreis eingespeist wurden (= fiktiver
    # §51-Abzug-Volumen). Σ der Tages-`einspeisung_neg_preis_kwh` über den Monat
    # (R17/Verlauf, Weg 1). None = Anlage unterliegt nicht §51 (`unterliegt_eeg_51`).
    einspeisung_neg_preis_kwh: Optional[float]
    # ── Finanzen je Monat (Fund N-22) ────────────────────────────────────────
    # Bis 2026-08-04 rechnete der **Client** sie selbst
    # (`pages/auswertung/types.ts::createMonatsZeitreihe`): eigene
    # Tarif-Stichtags-Auflösung, eigener §51-Abzug, eigene EV-Ersparnis — eine
    # zweite Finanz-Engine neben `services/finanz_zeilen.py::baue_finanz_zeile`.
    # Sie kannte den BKW-Ersatzträger (ADR-002/**P9**) nicht und zog die USt auf
    # Eigenverbrauch nicht ab, die alle vier Backend-Sichten abziehen. Dieselbe
    # Tabelle rechnete damit in der **Tages**-Granularität über den SoT
    # (`energie_profil/tage_werte.py`) und in der **Monats**-Granularität daneben.
    #
    # Der Grundpreis steckt in `netzbezug_kosten_euro` (Monatsposten, SoT
    # `berechne_netzbezug_kosten`), nicht im Arbeitspreis.
    einspeise_erloes_euro: float
    # §51-Diagnose: was der negative Börsenpreis gekostet hat. Der Erlös oben ist
    # bereits gekürzt — ohne diese Zahl wirkt die Kürzung wie ein Fehler.
    einspeise_nicht_verguetet_euro: float
    ev_ersparnis_euro: float
    # BKW-Monate **ohne** erfasste Erzeugung (Datenlücke): ihr gemessener
    # Eigenverbrauch trägt hier, sonst 0 — sonst zählte derselbe Fluss zweimal
    # (`bkw_finanz_beitrag`, ADR-002/P9).
    bkw_ersparnis_euro: float
    # Unentgeltliche Wertabgabe § 3 Abs. 1b UStG, **nur** bei
    # `steuerliche_behandlung == "regelbesteuerung"`, sonst 0,0. Je Monat aus dem
    # Eigenverbrauch dieses Monats × Selbstkosten je kWh; der Nenner der
    # Selbstkosten ist die **Jahres**-PV der ausgelieferten Monate, damit
    # Σ USt_m == USt(Σ EV_m) eines Jahres bleibt.
    ust_eigenverbrauch_euro: float
    netzbezug_kosten_euro: float
    # Einspeise-Erlös + EV- + BKW-Ersparnis − USt. **Ohne** „Sonstige Erträge &
    # Ausgaben" (die kommen aus der Komponenten-Zeitreihe und werden erst in der
    # Finanz-Sicht aufgeschlagen) — das ist der Unterschied zur Cockpit-Kachel.
    netto_ertrag_euro: float
    # Netto-Ertrag − Netzbezugskosten (die T-Konto-Ergebniszeile des Monats).
    netto_bilanz_euro: float
    # Der **effektive** Arbeitspreis des Monats: abgerechneter Flex-Ø vor dem
    # Stammdaten-Tarif (`resolve_netzbezug_preis_cent`, ADR-002/**P8**). Ohne
    # gepflegten Tarif der Default aus `wirtschaftlichkeit_defaults` — dass ein
    # Monat keine Tarif-Abdeckung hat, meldet der Daten-Checker.
    netzbezug_preis_cent: float
    # Legacy-Felder (für Migration-Warnung)
    hat_legacy_daten: bool
    # Feldgruppen, die NICHT aus der DB stammen, sondern aus der lokalen
    # Tagesebene (`inkl_nur_tageswerte`, N-121) — z. B. `["pv", "zaehler"]`.
    # `None` = alles steht so in der Datenbank. Eine Sicht, die solche Monate
    # zeigt, sagt es; ohne das Flag ist es immer `None`.
    aus_tageswerten: Optional[list[str]] = None

    class Config:
        from_attributes = True


@router.get("/aggregiert/{anlage_id}", response_model=list[AggregierteMonatsdatenResponse])
async def list_monatsdaten_aggregiert(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Filter nach Jahr"),
    # `Annotated`-Form, NICHT `= Query(False, …)`: als Default stünde dort sonst
    # das `Query`-Objekt selbst, und das ist truthy. Über HTTP fällt das nicht
    # auf (FastAPI ersetzt es), beim **direkten Funktionsaufruf** aber sehr wohl
    # — und genau so rufen die Tests dieser Route sie auf. Der erste Lauf hat
    # prompt `test_monat_ohne_zaehlerzeile_erscheint_nicht` gekippt.
    inkl_ohne_zaehlerzeile: Annotated[bool, Query(
        description=(
            "Auch Monate ohne Zählerzeile (kein Monatsabschluss) liefern. "
            "Diese Zeilen tragen `id: null` und keine Zählerwerte."
        ),
    )] = False,
    inkl_nur_tageswerte: Annotated[bool, Query(
        description=(
            "Auch Monate liefern, deren einzige Spur die lokale Tagesebene ist "
            "(weder Monatsabschluss noch Komponenten-Zeile). Setzt "
            "`inkl_ohne_zaehlerzeile` voraus und markiert die betroffenen "
            "Größen über `aus_tageswerten`."
        ),
    )] = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Monatsdaten mit aggregierten Werten aus InvestitionMonatsdaten zurück.

    Die Monatsgrößen kommen aus der Monats-Fakten-Schicht (ADR-002/**P10**,
    `services/monats_fakten.py`) — dort gelten Zeitfilter, Dienstwagen-Filter,
    die P7-Auflösung der PV und der Monatstarif genau einmal. Bis 2026-08-03
    faltete diese Route die `InvestitionMonatsdaten` selbst (Register N-15).

    **Default: nur Monate mit Zählerzeile**, absteigend — wie bisher. Eine
    `Monatsdaten`-Zeile entsteht erst beim **Monatsabschluss**; ein gelaufener
    Monat ohne Abschluss trägt seine IMD-Mengen, aber keinen Datensatz. In
    *Auswertungen → Tabelle* wäre er eine Zeile, die es dort nie gab (und die
    man weder bearbeiten noch löschen kann), deshalb bleibt er ausgeschlossen.

    Mit ``inkl_ohne_zaehlerzeile=true`` kommt er mit — für Sichten, die eine
    **Zeitreihe** zeigen statt einer Datensatz-Liste (Fund N-68: Cockpit → Jahr
    zeichnete sechs Monatsbalken, während die Kopfzahl acht Monate zählte, und
    der Rail-Balken des laufenden Jahres fiel entsprechend zu kurz aus). Solche
    Zeilen tragen ``id=None``, keine Zählerwerte (Einspeisung/Netzbezug = 0,0)
    und kein ``globalstrahlung``/``sonnenstunden``. Die aus den IMD gerechneten
    Größen — PV, Speicher, WP, E-Mob, Autarkie — sind vollständig.

    Mit zusätzlich ``inkl_nur_tageswerte=true`` kommen Monate mit, die **auch**
    keine Komponenten-Zeile haben und nur in der lokalen Tagesebene existieren
    (Fund **N-121**). Das ist der Normalfall für den **laufenden** Monat: einen
    automatischen Monatsabschluss gibt es nicht, deshalb fehlte er im Verlauf
    immer. Solche Zeilen tragen ``aus_tageswerten`` mit den Feldgruppen, die von
    dort stammen; Zählerwerte sind dann echte Messwerte statt 0,0. Der fehlende
    Abschluss selbst wird als Fehlerquelle vom **Daten-Checker** ausgewiesen
    (Kategorie ``monatsdaten_vollstaendigkeit``, mit Link auf den Abschluss) —
    hier wird er nicht zusätzlich beklagt, sondern schlicht mitgerechnet.

    **Die Finanzzeile je Monat kommt aus demselben SoT wie Cockpit,
    Jahresbericht-PDF und HA-Export** (`baue_finanz_zeile` +
    `berechne_finanz_aggregat`, seit Fund **N-22**). Bis 2026-08-04 rechnete der
    Client sie neben diesem Weg noch einmal selbst.
    """
    von = (jahr, 1) if jahr else None
    bis = (jahr, 12) if jahr else None
    # Ein Tarif-Cache für die ganze Anfrage: die Schicht füllt ihn beim Laden,
    # `baue_finanz_zeile` liest ihn danach nur noch. Ohne ihn löste jeder Monat
    # seinen Stichtag zweimal auf.
    tarif_cache: dict[date, dict] = {}
    fakten = await lade_monats_fakten(
        db, anlage_id, von=von, bis=bis, tarif_cache=tarif_cache,
        inkl_nur_tageswerte=inkl_nur_tageswerte,
    )
    # Absteigend (neueste zuerst) — Datums-Listen-Konvention, wie die frühere
    # `order_by(...desc())`.
    fakten = [
        f for f in reversed(fakten)
        if f.meta.hat_zaehlerzeile or inkl_ohne_zaehlerzeile
    ]

    if not fakten:
        return []

    # ── USt-Basis der Anlage (nur bei Regelbesteuerung wirksam) ──────────────
    # Investitionssumme + Betriebskosten in der Form, die drei der vier
    # Backend-Sichten verwenden (Jahresbericht-PDF, HA-Export, Aussichten):
    # die Vollkosten. Cockpit setzt an derselben Stelle eine zusammengesetzte
    # Summe aus Mehrkosten ein — dieselbe Anlage bekommt dort einen anderen
    # USt-Betrag (Register N-129). Hier wird die Mehrheitsform gewählt und die
    # Abweichung notiert, nicht stillschweigend eine fünfte gebaut.
    anlage_obj = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    inv_rows = (
        await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))
    ).scalars().all()
    investition_gesamt_euro = sum(i.anschaffungskosten_gesamt or 0 for i in inv_rows)
    betriebskosten_jahr_euro = sum(i.betriebskosten_jahr or 0 for i in inv_rows)
    # Nenner der Selbstkosten je kWh ist eine **Jahres**-Erzeugung. Je
    # Kalenderjahr über die ausgelieferten Monate summiert, damit die Summe der
    # Monats-USt genau die Jahres-USt ergibt (die Formel ist linear im
    # Eigenverbrauch). Ein angefangenes Jahr trägt entsprechend seinen
    # angefangenen Nenner — genauso rechnen Cockpit und PDF für einen
    # angefangenen Zeitraum.
    pv_je_jahr: dict[int, float] = {}
    for f in fakten:
        pv_je_jahr[f.jahr] = pv_je_jahr.get(f.jahr, 0.0) + f.erzeugung.pv_kwh

    result = []
    for f in fakten:
        md = f.meta.monatsdaten
        typen = f.meta.typen_mit_zeile

        # „Hat dieser Gerätetyp im Monat etwas beigetragen?" — Grundlage für
        # `None` statt `0` (P4). NICHT `aktive_investitionen`: eine aktive
        # Wärmepumpe ohne gepflegte Zeile ist aktiv und hat trotzdem nichts
        # geliefert. Die PV zählt zusätzlich als vorhanden, sobald die
        # P7-Auflösung einen Wert ergibt (auch ohne eigene Modul-Zeile, z. B.
        # aus dem Anlagen-Aggregat).
        # Feldgruppen, die aus der lokalen Tagesebene stammen (N-121). Sie
        # zählen für die „hat etwas beigetragen?"-Weichen genauso wie eine
        # IMD-Zeile — sonst käme ein belegter Wert als `None` heraus, und die
        # Sicht zeichnete wieder nichts.
        aus_tagen = f.meta.tageswert_gruppen
        hat_pv_imd = (
            "balkonkraftwerk" in typen
            or f.erzeugung.pv_module_kwh is not None
            or TAGESWERT_PV in aus_tagen
            or TAGESWERT_BKW in aus_tagen
        )
        # ALTBESTAND (N-28), bewusst so belassen: die BKW-eigenen Akku-Felder
        # zählen hier in dieselbe anlagenweite Speicher-Summe wie ein echter
        # Speicher, während `monats_fakten.SpeicherFakten` sie getrennt hält.
        # Diese Uneinheitlichkeit wird NICHT aufgelöst, sondern durch den Kanon
        # erledigt: ein BKW-Akku gehört als eigene `speicher`-Investition mit
        # Parent Balkonkraftwerk erfasst. Hier zu ändern hieße, die Zahlen genau
        # der Anwender zu bewegen, die noch auf dem alten Weg pflegen; sie
        # bekommen stattdessen den Migrationshinweis des Daten-Checkers
        # (`daten_checker/stammdaten.py::_check_bkw_akku_erfassungsweg`).
        hat_speicher_imd = (
            "speicher" in typen
            or "balkonkraftwerk" in typen
            or TAGESWERT_SPEICHER in aus_tagen
        )
        speicher_ladung = f.speicher.ladung_kwh + f.bkw.speicher_ladung_kwh
        speicher_entladung = f.speicher.entladung_kwh + f.bkw.speicher_entladung_kwh

        # E-Mob je Quelle getrennt ausweisen (die Response trägt eauto_* und
        # wallbox_* als eigene Felder) — über denselben SoT-Leser, nicht roh aus
        # dem Dict. `emob.ladung_kwh` (der Pool) wäre hier falsch: er wählt EINE
        # Quelle für die Gesamt-Heimladung, diese Sicht zeigt aber beide Seiten.
        eauto = f.emob.eauto_summe
        wallbox = f.emob.wallbox_summe

        einspeisung = f.zaehler.einspeisung_kwh
        netzbezug = f.zaehler.netzbezug_kwh
        _kz = f.kennzahlen

        # Legacy-Daten prüfen - nur warnen wenn:
        # 1. Legacy-Daten vorhanden sind (in Monatsdaten.pv_erzeugung_kwh oder batterie_*)
        # 2. UND keine entsprechenden InvestitionMonatsdaten existieren
        # (d.h. die Daten wären "verloren" wenn wir nur die neuen Quellen nutzen)
        # Ohne Zählerzeile gibt es auch keine Legacy-Spalten, die zu retten wären.
        hat_legacy_pv = bool(md is not None and md.pv_erzeugung_kwh and md.pv_erzeugung_kwh > 0)
        hat_legacy_speicher = bool(md is not None and (
            (md.batterie_ladung_kwh and md.batterie_ladung_kwh > 0) or
            (md.batterie_entladung_kwh and md.batterie_entladung_kwh > 0)
        ))
        hat_inv_pv = f.erzeugung.pv_kwh > 0
        hat_inv_speicher = speicher_ladung > 0 or speicher_entladung > 0
        hat_legacy = (hat_legacy_pv and not hat_inv_pv) or (hat_legacy_speicher and not hat_inv_speicher)

        # ── Finanzen dieses Monats über den SoT (N-22) ───────────────────────
        # `berechne_finanz_aggregat` über EINE Zeile: derselbe Weg, den der
        # Tages-Pfad derselben Tabelle längst geht (`tage_werte.py`).
        finanz_zeile = await baue_finanz_zeile(
            db, anlage_id, finanz_zeile_eingabe(f), tarif_cache=tarif_cache
        )
        finanz = berechne_finanz_aggregat([finanz_zeile])
        netzbezug_kosten = berechne_netzbezug_kosten(
            netzbezug, f.tarif.netzbezug_preis_cent, f.tarif.grundpreis_euro_monat
        )
        ust_eigenverbrauch = (
            ust_eigenverbrauch_fuer_anlage(
                anlage_obj,
                eigenverbrauch_kwh=finanz.eigenverbrauch_kwh,
                investition_gesamt_euro=investition_gesamt_euro,
                betriebskosten_jahr_euro=betriebskosten_jahr_euro,
                pv_erzeugung_jahr_kwh=pv_je_jahr.get(f.jahr, 0.0),
            )
            if anlage_obj is not None else 0.0
        )
        # `netto_ertrag_euro` des Aggregats ist die naive Summe der vier
        # Komponenten (Sonstige = 0, die kommen aus der Komponenten-Zeitreihe).
        netto_ertrag = finanz.netto_ertrag_euro - ust_eigenverbrauch

        result.append(AggregierteMonatsdatenResponse(
            # `md is None` ⇒ Monat ohne Zählerzeile (nur mit
            # `inkl_ohne_zaehlerzeile=true` in der Antwort). Die Zählerwerte
            # kommen ohnehin schon aus der Schicht (`f.zaehler`, dort 0,0), die
            # Spalten daneben existieren nicht — sie bleiben `None` statt still 0
            # zu werden.
            id=md.id if md is not None else None,
            anlage_id=md.anlage_id if md is not None else anlage_id,
            jahr=f.jahr,
            monat=f.monat,
            einspeisung_kwh=round(einspeisung, 1),
            netzbezug_kwh=round(netzbezug, 1),
            globalstrahlung_kwh_m2=md.globalstrahlung_kwh_m2 if md is not None else None,
            sonnenstunden=md.sonnenstunden if md is not None else None,
            netzbezug_durchschnittspreis_cent=(
                md.netzbezug_durchschnittspreis_cent if md is not None else None
            ),
            # Komponenten-Aggregate: None wenn keine aktive IMD beigetragen
            # hat, sonst tatsächlicher Wert (auch 0 ist legitim, z.B. WP im
            # Sommer 0 kWh Heizung).
            pv_erzeugung_kwh=round(f.erzeugung.pv_kwh, 1) if hat_pv_imd else None,
            pv_module_kwh=(
                round(f.erzeugung.pv_kwh - f.erzeugung.bkw_kwh, 1) if hat_pv_imd else None
            ),
            bkw_kwh=round(f.erzeugung.bkw_kwh, 1) if hat_pv_imd else None,
            sonstige_erzeugung_kwh=(
                round(f.erzeugung.sonstige_erzeuger_kwh, 1)
                if f.sonstiges.hat_erzeuger_zeile else None
            ),
            # Dieselbe Zahl, mit der direktverbrauch/eigenverbrauch gerechnet
            # wurden — nicht neu summiert, sonst driftet die ausgelieferte Größe
            # von der intern verwendeten ab. `None`, wenn WEDER PV noch ein
            # sonstiger Erzeuger beigetragen hat.
            erzeugung_hinter_zaehler_kwh=(
                round(f.erzeugung.hinter_zaehler_kwh, 1)
                if (hat_pv_imd or f.sonstiges.hat_erzeuger_zeile) else None
            ),
            speicher_ladung_kwh=round(speicher_ladung, 1) if hat_speicher_imd else None,
            speicher_entladung_kwh=round(speicher_entladung, 1) if hat_speicher_imd else None,
            speicher_netzladung_kwh=(
                round(f.speicher.netzladung_kwh, 1) if hat_speicher_imd else None
            ),
            wp_strom_kwh=round(f.wp.strom_kwh, 1) if "waermepumpe" in typen else None,
            wp_strom_heizen_kwh=round(f.wp.strom_heizen_kwh, 1) if f.wp.hat_split else None,
            wp_strom_warmwasser_kwh=(
                round(f.wp.strom_warmwasser_kwh, 1) if f.wp.hat_split else None
            ),
            wp_heizung_kwh=round(f.wp.heizung_kwh, 1) if "waermepumpe" in typen else None,
            wp_warmwasser_kwh=round(f.wp.warmwasser_kwh, 1) if "waermepumpe" in typen else None,
            eauto_ladung_kwh=round(eauto.ladung_kwh, 1) if "e-auto" in typen else None,
            eauto_km=round(f.emob.km, 1) if "e-auto" in typen else None,
            wallbox_ladung_kwh=round(wallbox.ladung_kwh, 1) if "wallbox" in typen else None,
            wallbox_ladung_pv_kwh=round(wallbox.pv_kwh, 1) if "wallbox" in typen else None,
            direktverbrauch_kwh=round(_kz.direktverbrauch_kwh, 1),
            eigenverbrauch_kwh=round(_kz.eigenverbrauch_kwh, 1),
            gesamtverbrauch_kwh=round(_kz.gesamtverbrauch_kwh, 1),
            autarkie_prozent=round(_kz.autarkie_prozent, 1),
            eigenverbrauchsquote_prozent=round(_kz.eigenverbrauchsquote_prozent, 1),
            # `None` heißt „nicht §51-pflichtig ODER kein Tages-Aggregat mit
            # Strompreis-Mitschrift" — eine 0 wäre dort eine Aussage, die
            # niemand belegen kann (Gate im Erlös-Service).
            einspeisung_neg_preis_kwh=(
                round(f.eeg.neg_preis_kwh, 1) if f.eeg.neg_preis_kwh is not None else None
            ),
            einspeise_erloes_euro=round(finanz.einspeise_erloes_euro, 2),
            einspeise_nicht_verguetet_euro=round(finanz.nicht_vergueteter_erloes_euro, 2),
            ev_ersparnis_euro=round(finanz.ev_ersparnis_euro, 2),
            bkw_ersparnis_euro=round(finanz.bkw_ersparnis_euro, 2),
            ust_eigenverbrauch_euro=round(ust_eigenverbrauch, 2),
            netzbezug_kosten_euro=round(netzbezug_kosten, 2),
            netto_ertrag_euro=round(netto_ertrag, 2),
            netto_bilanz_euro=round(netto_ertrag - netzbezug_kosten, 2),
            netzbezug_preis_cent=round(f.tarif.netzbezug_preis_cent, 2),
            hat_legacy_daten=hat_legacy,
            aus_tageswerten=sorted(aus_tagen) or None,
        ))

    return result


@router.get("/", response_model=list[MonatsdatenResponse])
async def list_monatsdaten(
    anlage_id: Optional[int] = Query(None, description="Filter nach Anlage"),
    jahr: Optional[int] = Query(None, description="Filter nach Jahr"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Monatsdaten zurück, optional gefiltert.

    Args:
        anlage_id: Optional - nur Daten dieser Anlage
        jahr: Optional - nur Daten dieses Jahres

    Returns:
        list[MonatsdatenResponse]: Liste der Monatsdaten
    """
    query = select(Monatsdaten)

    if anlage_id:
        query = query.where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        query = query.where(Monatsdaten.jahr == jahr)

    query = query.order_by(Monatsdaten.jahr.desc(), Monatsdaten.monat.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/feld-hinweise")
async def get_feld_hinweise_endpoint():
    """Feld-Hilfetexte als ``{kontext: {schluessel: hinweis}}``.

    Statisch (kein Anlage-/DB-Bezug), immer verfügbar (auch Standalone) — Single
    Source of Truth aus ``field_definitions``. Konsumiert vom Sensor-Zuordnungs-,
    vom künftigen MQTT-Inbound-Wizard und (perspektivisch) von der manuellen
    Monatsdaten-Eingabe, damit alle Kanäle identische Hilfetexte zeigen. Muss VOR
    ``/{monatsdaten_id}`` stehen, sonst als ID interpretiert (422).
    """
    return get_feld_hinweise()


@router.get("/{monatsdaten_id}", response_model=MonatsdatenMitKennzahlen)
async def get_monatsdaten(monatsdaten_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt einzelne Monatsdaten mit berechneten Kennzahlen zurück.

    Args:
        monatsdaten_id: ID der Monatsdaten

    Returns:
        MonatsdatenMitKennzahlen: Monatsdaten inkl. Kennzahlen

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Monatsdaten).where(Monatsdaten.id == monatsdaten_id))
    md = result.scalar_one_or_none()

    if not md:
        raise not_found("Monatsdaten")

    # Anlage und Strompreis laden für Kennzahlen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == md.anlage_id))
    anlage = anlage_result.scalar_one()

    # Tarif des Monats über den SoT-Helper. Die frühere Handquery hier ließ
    # `gueltig_bis` und `verwendung` weg: ein beendeter Tarif galt weiter, und
    # ein später angelegter WP-/Wallbox-Spezialtarif verdrängte über
    # `ORDER BY gueltig_ab DESC` den allgemeinen (Forum simon42 #89667/60).
    from datetime import date
    tarife = await lade_tarife_fuer_anlage(
        db, md.anlage_id, target_date=date(md.jahr, md.monat, 1)
    )
    strompreis = tarife.get("allgemein")

    # PV des Monats über den Read-time-SoT statt aus dem Aggregat-Feld: wer je
    # String misst, hat dort NULL stehen — die Kennzahlen dieses Endpoints
    # (Autarkie, Eigenverbrauchsquote, Erträge) rechneten dann mit PV = 0.
    pv_module = list((await db.execute(
        select(Investition).where(
            Investition.anlage_id == md.anlage_id,
            Investition.typ == "pv-module",
        )
    )).scalars().all())
    pv_kwh = pv_summe_je_monat(
        await lade_pv_je_monat(db, md.anlage_id, pv_module, md.jahr)
    ).get((md.jahr, md.monat))

    # Kennzahlen berechnen
    kennzahlen = berechne_monatskennzahlen(
        einspeisung_kwh=md.einspeisung_kwh,
        netzbezug_kwh=md.netzbezug_kwh,
        pv_erzeugung_kwh=pv_kwh or 0,
        batterie_ladung_kwh=md.batterie_ladung_kwh or 0,
        batterie_entladung_kwh=md.batterie_entladung_kwh or 0,
        einspeiseverguetung_cent=(
            strompreis.einspeiseverguetung_cent_kwh if strompreis else EINSPEISEVERGUETUNG_DEFAULT_CENT
        ),
        netzbezug_preis_cent=resolve_netzbezug_preis_cent(
            md,
            strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else NETZBEZUG_DEFAULT_CENT,
        ),
        grundpreis_euro_monat=strompreis.grundpreis_euro_monat or 0 if strompreis else 0,
        leistung_kwp=anlage.leistung_kwp,
    )

    response = MonatsdatenMitKennzahlen.model_validate(md)
    response.kennzahlen = KennzahlenResponse(**kennzahlen.__dict__)
    return response


@router.post("/", response_model=MonatsdatenResponse, status_code=status.HTTP_201_CREATED)
async def create_monatsdaten(data: MonatsdatenCreate, db: AsyncSession = Depends(get_db)):
    """
    Erstellt neue Monatsdaten.

    Args:
        data: Monatsdaten

    Returns:
        MonatsdatenResponse: Die erstellten Monatsdaten

    Raises:
        404: Anlage nicht gefunden
        409: Monat existiert bereits
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == data.anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise not_found("Anlage")

    # Duplikat prüfen
    existing = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == data.anlage_id,
            Monatsdaten.jahr == data.jahr,
            Monatsdaten.monat == data.monat
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Monatsdaten für {data.monat}/{data.jahr} existieren bereits"
        )

    # investitionen_daten separat extrahieren (nicht Teil des Monatsdaten-Models);
    # geprueft_gegen ebenfalls, es ist ein Messwert-Begleiter und darf weder in
    # die Provenance-Saat noch in die berechneten Felder geraten (PN 90128).
    investitionen_daten = data.investitionen_daten
    md_data = data.model_dump(exclude={'investitionen_daten', 'geprueft_gegen'})
    # G19-1: nur gültige Positionen persistieren (Bezeichnung nicht leer;
    # 0-€-Beträge sind legitim — gleiche Regel wie IMD, #286).
    if md_data.get('sonstige_positionen') is not None:
        md_data['sonstige_positionen'] = [
            p for p in md_data['sonstige_positionen'] if ist_gueltige_position(p)
        ]
    md = Monatsdaten(**md_data)
    md.geprueft_gegen = data.geprueft_gegen or {}

    # Berechnete Felder (werden berechnet wenn pv_erzeugung vorhanden)
    if md.pv_erzeugung_kwh is not None:
        md.direktverbrauch_kwh = max(0, md.pv_erzeugung_kwh - md.einspeisung_kwh - (md.batterie_ladung_kwh or 0))
        md.eigenverbrauch_kwh = md.direktverbrauch_kwh + (md.batterie_entladung_kwh or 0)
        md.gesamtverbrauch_kwh = md.eigenverbrauch_kwh + md.netzbezug_kwh
    elif md.einspeisung_kwh > 0 or md.netzbezug_kwh > 0:
        # Fallback: Gesamtverbrauch kann geschätzt werden
        md.gesamtverbrauch_kwh = md.netzbezug_kwh + md.einspeisung_kwh

    db.add(md)
    await db.flush()

    # Provenance-Markierung für fresh row: User-Eingabe vs. abgeleitete Felder
    user_fields = [
        f for f in md_data
        if f not in {"anlage_id", "jahr", "monat"}
        and f not in _COMPUTED_FIELDS
        and getattr(md, f, None) is not None
    ]
    if user_fields:
        seed_provenance(
            md, source="manual:form", writer=_MANUAL_WRITER,
            fields=user_fields,
        )
    auto_fields = [f for f in _COMPUTED_FIELDS if getattr(md, f, None) is not None]
    if auto_fields:
        seed_provenance(
            md, source="auto:monatsabschluss", writer=_AUTO_WRITER,
            fields=auto_fields,
        )

    await db.refresh(md)

    # Investitions-Monatsdaten speichern (E-Auto km, Speicher Ladung, WP Verbrauch, etc.)
    if investitionen_daten:
        await _save_investitionen_monatsdaten(db, investitionen_daten, data.jahr, data.monat)

    return md


async def _save_investitionen_monatsdaten(
    db: AsyncSession,
    investitionen_daten: dict[str, dict[str, Any]],
    jahr: int,
    monat: int,
) -> None:
    """
    Speichert Investitions-spezifische Monatsdaten (E-Auto km, Speicher Ladung, etc.).

    Provenance: Source `manual:form` pro `verbrauch_daten`-Sub-Key (Etappe 3d
    Päckchen 3). Per-Sub-Key durch den Resolver, kein Komplett-Override des
    JSON-Dicts mehr — sonst würden manuell gepflegte Sub-Keys von einem
    parallelen Cloud-Sync überschrieben.

    Sonderfall `geprueft_gegen` (PN 90128): der Schlüssel kommt im selben
    Investitions-Payload an, ist aber **kein** Messwert und landet deshalb in
    der gleichnamigen Spalte statt in `verbrauch_daten` — dort lesen
    Aggregatoren, CSV-Export und MQTT mit.
    """
    for inv_id_str, verbrauch_daten in investitionen_daten.items():
        try:
            inv_id = int(inv_id_str)
        except ValueError:
            continue

        # Prüfen ob Investition existiert
        inv_result = await db.execute(select(Investition).where(Investition.id == inv_id))
        if not inv_result.scalar_one_or_none():
            continue

        # Existierende InvestitionMonatsdaten für diesen Monat suchen
        existing_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == inv_id)
            .where(InvestitionMonatsdaten.jahr == jahr)
            .where(InvestitionMonatsdaten.monat == monat)
        )
        existing = existing_result.scalar_one_or_none()
        sub_payload = dict(verbrauch_daten or {})
        geprueft_gegen = sub_payload.pop("geprueft_gegen", None)

        if existing:
            for sub_key, value in sub_payload.items():
                await write_json_subkey_with_provenance(
                    db, existing, "verbrauch_daten", sub_key, value,
                    source="manual:form", writer=_MANUAL_WRITER,
                )
            if geprueft_gegen is not None:
                existing.geprueft_gegen = geprueft_gegen
                flag_modified(existing, "geprueft_gegen")
        else:
            imd = InvestitionMonatsdaten(
                investition_id=inv_id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=sub_payload,
                geprueft_gegen=geprueft_gegen or {},
            )
            db.add(imd)
            if sub_payload:
                await db.flush()
                seed_provenance(
                    imd, source="manual:form", writer=_MANUAL_WRITER,
                    json_subkeys={"verbrauch_daten": list(sub_payload.keys())},
                )

    await db.flush()


@router.put("/{monatsdaten_id}", response_model=MonatsdatenResponse)
async def update_monatsdaten(
    monatsdaten_id: int,
    data: MonatsdatenUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert Monatsdaten.

    Args:
        monatsdaten_id: ID der Monatsdaten
        data: Zu aktualisierende Felder

    Returns:
        MonatsdatenResponse: Die aktualisierten Monatsdaten

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Monatsdaten).where(Monatsdaten.id == monatsdaten_id))
    md = result.scalar_one_or_none()

    if not md:
        raise not_found("Monatsdaten")

    # investitionen_daten separat behandeln
    investitionen_daten = data.investitionen_daten
    update_data = data.model_dump(
        exclude_unset=True, exclude={'investitionen_daten', 'geprueft_gegen'}
    )

    # PN 90128: bewusst behaltene Abweichungen. Läuft NICHT durch den
    # Provenance-Resolver — das ist kein Messwert, der gegen eine andere Quelle
    # gewinnen oder verlieren könnte, sondern die Notiz des Nutzers zu genau
    # diesem Formular. `{}` nimmt alle Bestätigungen zurück, `None` (Feld nicht
    # gesendet) lässt sie unangetastet.
    if data.geprueft_gegen is not None:
        md.geprueft_gegen = data.geprueft_gegen
        flag_modified(md, "geprueft_gegen")
    # G19-1: nur gültige Positionen persistieren (leere Liste = bewusst geleert,
    # gleiche Semantik wie der IMD-Pfad in _save_investitionen_monatsdaten).
    if update_data.get('sonstige_positionen') is not None:
        update_data['sonstige_positionen'] = [
            p for p in update_data['sonstige_positionen'] if ist_gueltige_position(p)
        ]

    # User-Eingaben durch Resolver — manuelle Werte gewinnen gegen alle
    # niedriger priorisierten Quellen (auto/external/fallback/legacy).
    for field, value in update_data.items():
        await write_with_provenance(
            db, md, field, value,
            source="manual:form", writer=_MANUAL_WRITER,
        )

    # Berechnete Felder aktualisieren (werden berechnet wenn pv_erzeugung vorhanden).
    # Source `auto:monatsabschluss` — wird von späterer manueller Eingabe
    # geschlagen, schlägt aber legacy:unknown und fallback.
    new_computed: dict[str, Optional[float]] = {}
    if md.pv_erzeugung_kwh is not None:
        new_computed["direktverbrauch_kwh"] = max(
            0, md.pv_erzeugung_kwh - md.einspeisung_kwh - (md.batterie_ladung_kwh or 0)
        )
        new_computed["eigenverbrauch_kwh"] = (
            new_computed["direktverbrauch_kwh"] + (md.batterie_entladung_kwh or 0)
        )
        new_computed["gesamtverbrauch_kwh"] = new_computed["eigenverbrauch_kwh"] + md.netzbezug_kwh
    elif md.einspeisung_kwh > 0 or md.netzbezug_kwh > 0:
        new_computed["gesamtverbrauch_kwh"] = md.netzbezug_kwh + md.einspeisung_kwh

    for field, value in new_computed.items():
        await write_with_provenance(
            db, md, field, value,
            source="auto:monatsabschluss", writer=_AUTO_WRITER,
        )

    await db.flush()
    await db.refresh(md)

    # Investitions-Monatsdaten speichern
    if investitionen_daten:
        await _save_investitionen_monatsdaten(db, investitionen_daten, md.jahr, md.monat)

    return md


@router.delete("/{monatsdaten_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monatsdaten(monatsdaten_id: int, db: AsyncSession = Depends(get_db)):
    """
    Löscht Monatsdaten.

    Args:
        monatsdaten_id: ID der Monatsdaten

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Monatsdaten).where(Monatsdaten.id == monatsdaten_id))
    md = result.scalar_one_or_none()

    if not md:
        raise not_found("Monatsdaten")

    # Audit-Log VOR dem Delete (sonst sind die Natural-Keys nicht mehr lesbar).
    log_delete(db, md, source="manual:form", writer=_MANUAL_WRITER)

    await db.delete(md)
