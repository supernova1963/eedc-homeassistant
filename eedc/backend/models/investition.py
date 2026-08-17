"""
Investition Models

Speichert Investitionen (E-Auto, Wärmepumpe, Speicher, etc.) und deren Monatsdaten.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional, Any
from sqlalchemy import Integer, Float, String, Boolean, Date, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class InvestitionTyp(str, Enum):
    """Verfügbare Investitionstypen."""
    E_AUTO = "e-auto"
    WAERMEPUMPE = "waermepumpe"
    SPEICHER = "speicher"
    WALLBOX = "wallbox"
    WECHSELRICHTER = "wechselrichter"
    PV_MODULE = "pv-module"
    BALKONKRAFTWERK = "balkonkraftwerk"
    SONSTIGES = "sonstiges"


# Lesbare Typ-Bezeichnung — Single Source of Truth. Stand bis 2026-07-31
# byte-gleich in `pdf/builders/finanzbericht.py` und
# `pdf/builders/anlagendokumentation.py`; beide importieren jetzt von hier.
# Kein Roh-Enum in anwendersichtbarem Text ([[feedback_typ_labels_pattern]]).
TYP_LABELS: dict[str, str] = {
    InvestitionTyp.PV_MODULE.value: "PV-Modulfeld",
    InvestitionTyp.WECHSELRICHTER.value: "Wechselrichter",
    InvestitionTyp.SPEICHER.value: "Batteriespeicher",
    InvestitionTyp.WAERMEPUMPE.value: "Wärmepumpe",
    InvestitionTyp.WALLBOX.value: "Wallbox",
    InvestitionTyp.E_AUTO.value: "E-Fahrzeug",
    InvestitionTyp.BALKONKRAFTWERK.value: "Balkonkraftwerk",
    InvestitionTyp.SONSTIGES.value: "Sonstiges",
}


# =============================================================================
# Parent-Kind-Regel — Single Source of Truth
# =============================================================================
# Welcher Typ darf welchem Typ zugeordnet werden. Die Regel stand bis 2026-07-31
# in DREI uneinigen Kopien: `_validate_parent_child` und `get_parent_options`
# (beide in api/routes/investitionen/crud.py) sowie zwei Client-Konstanten
# (`investitionFormHelpers.ts`, `useSetupWizard.ts`). Nur eine kannte das
# Balkonkraftwerk vollständig — der Wizard bot es nie an, `get_parent_options`
# behauptete das Gegenteil. Beides gemessen beim BKW-Kanon-Entscheid.
#
# Der BKW-Akku (Zendure, Anker SOLIX) ist genau der Fall, für den der
# Balkonkraftwerk-Parent existiert: der Akku wird als eigene Speicher-Investition
# erfasst und bekommt damit Live-Leistung, SoC, Energiefluss-Knoten und
# Zählerpfad. Das ist der Kanon; die BKW-eigenen Speicher-Felder im
# Monatsabschluss sind Altbestand (`nur_manuell`, s. core/field_definitions.py).
#
# Das Client-Pendant lebt in
#   eedc/frontend/src/components/forms/sections/investitionFormHelpers.ts
# und wird von `useSetupWizard.ts` importiert statt nachgebaut.
#
# N-266 (2026-08-17): `pv-module` darf auch einem `balkonkraftwerk` zugeordnet
# werden. Ein BKW ist funktional Erzeuger UND Wechselrichter in einem (so steht
# es in `core/berechnungen/wr_kappung.py`), und ein Wechselrichter darf Module
# tragen — die Sperre war keine Entscheidung, sondern eine Lücke. Sie kostete
# ein BKW jede zweite Ausrichtung: das Gerät trägt EINE `ausrichtung` und EINE
# `neigung_grad`, zwei Module über Eck waren damit nicht abbildbar. Melder:
# azywietz-web (Discussion #366) und Daniel (Forum T89667 #172).
#
# Wer diese Zeile liest und eine Σ-Stelle baut: ein BKW mit Modul-Kindern tritt
# seine kWp, seine Erzeugung und seine Ausrichtung an die Kinder ab — der
# Selektor dafür ist `core/berechnungen/erzeuger_traeger.py`, NICHT eine eigene
# `if typ == balkonkraftwerk`-Fallunterscheidung. Seine AC-Grenze tritt es
# dagegen NICHT ab (die 800 VA sind eine Eigenschaft des Wechselrichters, nicht
# der Module).
ERLAUBTE_PARENT_TYPEN: dict[str, tuple[str, ...]] = {
    InvestitionTyp.PV_MODULE.value: (
        InvestitionTyp.WECHSELRICHTER.value,
        InvestitionTyp.BALKONKRAFTWERK.value,     # N-266 — mehrere Ausrichtungen
    ),
    InvestitionTyp.SPEICHER.value: (
        InvestitionTyp.WECHSELRICHTER.value,      # Hybrid-Wechselrichter (DC)
        # N-268: hier stand „BKW mit Akku (AC)". Gemeint war die
        # HAUSANBINDUNG, gelesen wurde es als SPEICHERKOPPLUNG — und die
        # entscheidet seit F-11 über SOLL-Zahlen (`wr_kappung`: am Träger der
        # Grenze hängt ein DC-Speicher ⇒ gar nicht kappen). Richtig ist DC:
        # ein Akku mit gesetztem Parent teilt sich den Erzeugungspfad, nur ein
        # AC-Speicher bringt seinen eigenen Wechselrichter mit und hat dann in
        # aller Regel gar keinen Parent. `get_speicher_kopplung` leitet genau
        # das ab, `wr_kappung.py` hatte recht. Gernots Einwand, 17.08.2026.
        InvestitionTyp.BALKONKRAFTWERK.value,     # BKW-Akku (DC, Kanon seit v4.0.5)
    ),
}

# Typen, für die eine Parent-Zuordnung PFLICHT ist (sofern ein Parent existiert).
PARENT_PFLICHT_TYPEN: frozenset[str] = frozenset({InvestitionTyp.PV_MODULE.value})

# Typen, an denen ein **Ertrag/Jahr** (`einsparung_prognose_jahr`) gepflegt
# werden kann — Konzept `docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md` §8/1+2.
#
# Für alle anderen Typen rechnet eedc die Jahres-Einsparung selbst (PV,
# Speicher, WP, E-Auto, BKW, Wechselrichter): dort ist der `else`-Zweig der
# ROI-Typkette in `api/routes/investitionen/crud.py` gar nicht erreichbar, ein
# gepflegter Wert bliebe wirkungslos — und in der Prognose (`aussichten.py`)
# stünde er dann gegen die selbst gerechnete Zahl. **Eine Menge, drei
# Verwender:** Formular (Client-Pendant `investitionFormHelpers.ts`),
# ROI-Dashboard, Aussichten-Prognose.
ERTRAGSFELD_TYPEN: frozenset[str] = frozenset({
    InvestitionTyp.WALLBOX.value,
    InvestitionTyp.SONSTIGES.value,
})


class Investition(Base):
    """
    Eine Investition/Erweiterung der PV-Anlage.

    Die typ-spezifischen Parameter werden als JSON gespeichert.

    Beispiel E-Auto Parameter:
        {
            "km_jahr": 15000,
            "verbrauch_kwh_100km": 18,
            "pv_anteil_prozent": 60,
            "benzinpreis_euro": 1.85,
            "nutzt_v2h": true,
            "v2h_entlade_preis_cent": 30
        }

    Beispiel PV-Module Parameter:
        {
            "anzahl_module": 40,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500
        }
    """

    __tablename__ = "investitionen"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Stammdaten
    typ: Mapped[str] = mapped_column(String(50), nullable=False)  # InvestitionTyp value
    bezeichnung: Mapped[str] = mapped_column(String(255), nullable=False)
    anschaffungsdatum: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    stilllegungsdatum: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Kosten
    anschaffungskosten_gesamt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    anschaffungskosten_alternativ: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # z.B. neuer Verbrenner
    betriebskosten_jahr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # PV-Module spezifische Felder (für PVGIS)
    leistung_kwp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Leistung in kWp
    ausrichtung: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Süd, Ost, West, etc.
    neigung_grad: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Modulneigung in Grad

    # Home Assistant Integration (für String-basierte IST-Erfassung)
    ha_entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # z.B. "sensor.fronius_string1_energy"

    # Typ-spezifische Parameter (JSON)
    parameter: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Prognose-Werte (berechnet)
    einsparung_prognose_jahr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    co2_einsparung_prognose_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Graue Herstellungs-Last (CO2) für die CO2-Amortisation (#284). Optionales
    # Override aus dem Herstellerdatenblatt; leer = Default-Richtwert nach Typ/Größe
    # (GRAUE_LAST_* in core/calculations.py).
    graue_last_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)

    # Verknüpfung (z.B. PV-Module -> Wechselrichter)
    parent_investition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investitionen.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    anlage = relationship("Anlage", back_populates="investitionen")
    monatsdaten = relationship("InvestitionMonatsdaten", back_populates="investition", cascade="all, delete-orphan")
    parent = relationship("Investition", remote_side=[id], backref="children")

    def __repr__(self) -> str:
        return f"<Investition(id={self.id}, typ='{self.typ}', name='{self.bezeichnung}')>"

    def ist_aktiv_an(self, tag: date) -> bool:
        """True, wenn die Investition an einem konkreten Tag aktiv war.

        `aktiv` ist manueller Override (aktiv=False = wie gelöscht → nirgends, bis
        reaktiviert), `stilllegungsdatum` finaler End-Marker. `is False`: nicht-
        persistierte Objekte (aktiv=None, Default greift erst beim Insert) = aktiv.
        """
        if self.aktiv is False:
            return False
        if self.anschaffungsdatum and self.anschaffungsdatum > tag:
            return False
        if self.stilllegungsdatum and self.stilllegungsdatum < tag:
            return False
        return True

    def ist_aktiv_im_zeitraum(self, start: date, end: date) -> bool:
        """True, wenn die Investition im Zeitraum [start, end] sichtbar/aktiv war.

        `aktiv=False` = wie gelöscht (ohne zu löschen): nirgends in Auswertungen
        anzeigen — auch nicht historisch — bis reaktiviert wird (Gernot 2026-06-05,
        [[feedback_anschaffungsdatum_grenze]]). Daher prüft auch die historische
        Sicht das `aktiv`-Flag; `anschaffungsdatum`/`stilllegungsdatum` begrenzen
        zusätzlich das Lebensdauer-Fenster. (Endgültiges Entfernen = Hard-Delete.)

        `is False` (nicht `not self.aktiv`): nur explizit deaktiviert blendet aus —
        ein frisch konstruiertes, noch nicht persistiertes Objekt hat `aktiv=None`
        (Spalten-Default `True` greift erst beim Insert) und gilt als aktiv.
        """
        if self.aktiv is False:
            return False
        if self.anschaffungsdatum and self.anschaffungsdatum > end:
            return False
        if self.stilllegungsdatum and self.stilllegungsdatum < start:
            return False
        return True

    def ist_aktiv_im_monat(self, jahr: int, monat: int) -> bool:
        """Convenience: True, wenn Investition im gegebenen Kalendermonat (teilweise) aktiv war."""
        from calendar import monthrange
        start = date(jahr, monat, 1)
        end = date(jahr, monat, monthrange(jahr, monat)[1])
        return self.ist_aktiv_im_zeitraum(start, end)


class InvestitionMonatsdaten(Base):
    """
    Monatliche Messwerte für eine Investition.

    Die Daten werden als JSON gespeichert, da sie je nach Typ unterschiedlich sind.

    Beispiel E-Auto verbrauch_daten:
        {
            "km_gefahren": 1200,
            "verbrauch_kwh": 216,
            "ladung_pv_kwh": 130,
            "ladung_netz_kwh": 86,
            "v2h_entladung_kwh": 25,
            "ladevorgaenge": 12
        }
    """

    __tablename__ = "investition_monatsdaten"
    __table_args__ = (
        UniqueConstraint("investition_id", "jahr", "monat", name="uq_inv_monatsdaten_periode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    investition_id: Mapped[int] = mapped_column(ForeignKey("investitionen.id", ondelete="CASCADE"), nullable=False)

    # Zeitraum
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    monat: Mapped[int] = mapped_column(Integer, nullable=False)

    # Typ-spezifische Verbrauchsdaten (JSON)
    verbrauch_daten: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Berechnete Werte
    einsparung_monat_euro: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    co2_einsparung_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Per-Feld-Provenance (Etappe 3d Päckchen 1, KONZEPT-DATENPIPELINE.md Sektion 3.2).
    source_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Idempotenz-Hash für Cloud-/CSV-Re-Imports (P2-Lieferung).
    source_hash: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    # „Gespeicherten Wert bewusst behalten" je Feld (PN 90128 / Auftrag 3b) —
    # gleiche Struktur und Semantik wie `Monatsdaten.geprueft_gegen`, dort steht
    # die ausführliche Begründung. Bewusst eine EIGENE Spalte und kein Sub-Key in
    # `verbrauch_daten`: dort stehen Messwerte, die von Aggregatoren, CSV-Export
    # und MQTT gelesen werden — eine Entscheidungs-Notiz dazwischen wäre ein
    # Fremdkörper im Datenpfad.
    geprueft_gegen: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    investition = relationship("Investition", back_populates="monatsdaten")

    def __repr__(self) -> str:
        return f"<InvestitionMonatsdaten(inv={self.investition_id}, {self.jahr}/{self.monat:02d})>"
