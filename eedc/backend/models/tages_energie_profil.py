"""
Tages-Energieprofil Modelle.

Persistente Speicherung stündlicher Energiedaten für langfristige Analyse
und Speicher-Dimensionierungs-Simulation.

Daten werden täglich nach Mitternacht aus HA-Sensor-History / MQTT aggregiert
und bleiben dauerhaft erhalten (HA-History hat nur ~10 Tage Retention).

Zwei Tabellen:
  - TagesEnergieProfil: 24 Zeilen pro Anlage+Tag (stündliche Auflösung)
  - TagesZusammenfassung: 1 Zeile pro Anlage+Tag (Tagessummen + KPIs)
"""

from datetime import datetime, date
from typing import Any, Optional

from sqlalchemy import (
    Integer, Float, String, Date, DateTime, ForeignKey,
    UniqueConstraint, Index, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class TagesEnergieProfil(Base):
    """
    Stündliches Energieprofil einer Anlage.

    Eine Zeile pro Anlage + Datum + Stunde (max. 24 Zeilen pro Tag).
    Speichert sowohl Gesamtwerte als auch Per-Komponenten-Aufschlüsselung.
    """

    __tablename__ = "tages_energie_profil"
    __table_args__ = (
        UniqueConstraint("anlage_id", "datum", "stunde",
                         name="uq_tep_anlage_datum_stunde"),
        Index("ix_tep_anlage_datum", "anlage_id", "datum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )

    datum: Mapped[date] = mapped_column(Date, nullable=False)
    stunde: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-23

    # Gesamtwerte (kW Stundenmittel) — vorzeichenbasiert aggregiert
    # pv_kw: alle lokalen Erzeuger (PV-Module, BKW, BHKW, Sonstiges wenn positiv)
    pv_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # verbrauch_kw: alle Senken gesamt (Haushalt + WP + Wallbox + Sonstiges wenn negativ)
    verbrauch_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    einspeisung_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    netzbezug_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # batterie_kw: alle Speicher inkl. V2H — positiv=Entladung(Quelle), negativ=Ladung(Senke).
    # Vorzeichen-SoT: core.berechnungen.batterie_kw_spalte (= −Bilanz-Netto). NICHT
    # auf "Ladung positiv" zurückdrehen — alle Consumer (tagesbilanz, Charts,
    # speicher_wirtschaftlichkeit, komponenten[batterie_*]) erwarten Entladung positiv.
    batterie_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Einzelne Verbraucher (kW, Absolutwert) — für Effizienz- und Musteranalyse
    waermepumpe_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wallbox_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Counter pro Stunde (Issue #136): Anzahl WP-Kompressor-Starts in dieser Stunde,
    # summiert über alle WP-Investitionen mit gemapptem Starts-Zähler.
    # Pro-Investitions-Aufschlüsselung lebt auf Tagesebene in TagesZusammenfassung.komponenten_starts.
    wp_starts_anzahl: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Counter pro Stunde (Issue #238): WP-Betriebsstunden in dieser Stunde (0..1 h pro
    # WP), summiert über alle WP-Investitionen mit gemapptem Betriebsstunden-Zähler.
    wp_betriebsstunden: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Bilanz
    ueberschuss_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # max(0, pv - verbrauch) — was hätte gespeichert werden können
    defizit_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # max(0, verbrauch - pv) — was aus Speicher/Netz gedeckt werden musste

    # Wetter (IST-Daten, von Open-Meteo oder Sensor)
    temperatur_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    globalstrahlung_wm2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Bewölkung (0-100%), Niederschlag (mm), WMO-Code — pro Stunde aus Open-Meteo
    # Für Wetter-Stratifizierung und Korrekturprofil (siehe KONZEPT-KORREKTURPROFIL.md)
    bewoelkung_prozent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    niederschlag_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wetter_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Batterie-SoC (Stundenmittel, %) — der Ladestand der ANLAGE, seit N-239
    # kapazitätsgewichtet über alle Speicher (Σ Inhalt ÷ Σ Kapazität, SoT
    # `core.berechnungen.speicher.anlagen_soc_prozent`). Bis 2026-08-12 trug die
    # Spalte bei mehreren Speichern still den Wert des ERSTEN gemappten Sensors.
    soc_prozent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Aufschlüsselung dazu: {investition_id: soc_prozent} (N-239). Eigene Spalte
    # und NICHT in `komponenten` — das Dict dort trägt kW/kWh und wird von
    # Whitelist-Konsumenten summiert; ein Prozentwert darin wäre genau die
    # Einheiten-Verwechslung, aus der der BKW-Doppelzählungs-Bug entstand.
    # `None` bei Altbestand: der Tag wurde vor N-239 aggregiert und trägt die
    # Ein-Gerät-Zahl — der Daten-Checker meldet das und bietet die Neuberechnung an.
    #
    # ⚠ `none_as_null=True` ist hier **Bedingung**, nicht Geschmack: ohne das
    # schreibt SQLAlchemy ein Python-`None` als JSON-`null` (die Zeichenkette),
    # während `ALTER TABLE ADD COLUMN` bei Altbestand echtes SQL-NULL hinterlässt.
    # Die Erkennung des Daten-Checkers (`soc_je_speicher IS NULL`) fände dann je
    # nach Herkunft die eine Hälfte nicht — genau die stille Sorte Fehler, gegen
    # die dieser Befund gebaut ist.
    soc_je_speicher: Mapped[Optional[dict]] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )

    # Betriebsmodus je Wärmepumpe in dieser Stunde (#263 K-2):
    # {investition_id: "heizen"|"kuehlen"|"entfeuchten"|"lueften"|"aus"|"unbestimmt"}.
    #
    # Eine Split-Klimaanlage heizt und kühlt über DENSELBEN Zähler; die
    # Aufteilung ist aus keinem vorhandenen Feld rekonstruierbar. Sie entsteht
    # nur, wenn eedc den Modus zur Messzeit mitschreibt — und die Stundenzeile
    # ist genau der Ort, an dem die Menge schon steht (`komponenten` führt
    # `waermepumpe_<id>` als Stunden-kWh je Gerät). Stunde × Modus × kWh, mehr
    # braucht die spätere Aggregation nicht.
    #
    # Eigene Spalte und NICHT in `komponenten` — dieselbe Begründung wie bei
    # `soc_je_speicher` eine Zeile darüber: jenes Dict trägt kW/kWh und wird von
    # Whitelist-Konsumenten summiert; ein Zustandswert darin wäre die
    # Einheiten-Verwechslung, aus der der BKW-Doppelzählungs-Bug entstand.
    #
    # ⚠ `none_as_null=True` ist auch hier Bedingung, nicht Geschmack (s. o.):
    # `ALTER TABLE ADD COLUMN` hinterlässt bei Altbestand echtes SQL-NULL,
    # SQLAlchemy schriebe ohne das Flag die Zeichenkette `null`.
    #
    # ⚠ **`None` heißt „nicht hingesehen", nicht „kein Modus".** Eine Stunde
    # ohne Eintrag hat kein Modus-Signal (Sensor nicht zugeordnet, HA-Ausfall,
    # Tag vor der Zuordnung); der Wert `"unbestimmt"` dagegen heißt
    # „hingesehen, Seite nicht zuordenbar" (Automatik ohne Ist-Signal). Die
    # zwei Fälle dürfen nie ineinander übersetzt werden — der Anwender muss
    # „das Gerät lief anders" von „eedc hat nicht gemessen" unterscheiden
    # können (Konzept §3.3).
    betriebsmodus_je_wp: Mapped[Optional[dict]] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )

    # Strompreis (ct/kWh, Stundenmittel)
    # strompreis_cent: Endpreis aus HA-Sensor (Tibber etc.) — nur wenn Sensor konfiguriert
    strompreis_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # boersenpreis_cent: EPEX Day-Ahead Großhandelspreis (aWATTar API) — immer befüllt
    boersenpreis_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Per-Komponenten-Aufschlüsselung (wie Tagesverlauf-Butterfly)
    # z.B. {"pv_3": 2.1, "waermepumpe_5": -0.8, "haushalt": -1.2}
    komponenten: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Per-Feld-Provenance (Etappe 3d Päckchen 1, KONZEPT-DATENPIPELINE.md Sektion 3.2).
    source_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    anlage = relationship("Anlage")


class TagesZusammenfassung(Base):
    """
    Tägliche Zusammenfassung einer Anlage.

    Eine Zeile pro Anlage + Datum.
    Aggregierte Kennzahlen für Monatsrollup und Speicher-Simulation.
    """

    __tablename__ = "tages_zusammenfassung"
    __table_args__ = (
        UniqueConstraint("anlage_id", "datum",
                         name="uq_tz_anlage_datum"),
        Index("ix_tz_anlage_datum", "anlage_id", "datum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )

    datum: Mapped[date] = mapped_column(Date, nullable=False)

    # Energie-Bilanzen (kWh, Summe der Stundenwerte)
    ueberschuss_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    defizit_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Spitzenleistungen (kW)
    peak_pv_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_netzbezug_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_einspeisung_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Batterie-Nutzung
    batterie_vollzyklen: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Berechnung: Σ |ΔSoC| / 2 / 100 (ein Vollzyklus = 0→100→0)

    # Wetter-Tageswerte
    temperatur_min_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperatur_max_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strahlung_summe_wh_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Summe Globalstrahlung über den Tag (Wh/m²) — HORIZONTAL (GHI, OpenMeteo
    # `shortwave_radiation`). ⛔ NICHT der Nenner der Performance Ratio, s. unten.

    # Summe der Modulebenen-Einstrahlung über den Tag (Wh/m², kWp-gewichtet über
    # alle Orientierungsgruppen) — GTI, OpenMeteo `global_tilted_irradiance`.
    #
    # ⭐ N-384 (2026-09-03): DAS IST DER NENNER DER PERFORMANCE RATIO, und bis hierher
    # wurde er nirgends gespeichert. `aggregator.py` hat ihn je Tag berechnet, durch ihn
    # geteilt und wieder verworfen; angezeigt wurde daneben `strahlung_summe_wh_m2` —
    # also die WAAGERECHTE Strahlung, die nicht in der Formel steht. Wer nachrechnete,
    # bekam zwangsläufig eine andere Zahl, und der Widerspruch war für niemanden
    # auflösbar, auch nicht für uns. Aufgefallen an coolxmad (#353), der seit dem 30.07.
    # an genau dieser Zahl misst.
    # ⛔ RÜCKWÄRTS LEER: Bestandszeilen bleiben NULL. NULL heißt „nicht erhoben" — dort
    # darf KEINE Zahl stehen, insbesondere nicht wieder die GHI (derselbe Fehler mit
    # neuem Etikett). Die Anzeige lässt die Bezugsgröße dann weg.
    gti_summe_wh_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Performance Ratio: IST-Ertrag / (GTI × kWp / 1000) — Modulebene, nicht horizontal
    # (#139: mit GHI liefen PR-Werte im Winter künstlich auf 1,5–2,8).
    performance_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # PV-Prognose (kWh): Vom Wetter-Endpoint berechnete Tagesprognose.
    # Dient als Referenzwert für den Lernfaktor (IST/Prognose-Vergleich).
    # ANZEIGE-Wert (rollend, Overwrite): folgt OpenMeteo intraday mit.
    pv_prognose_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Genauigkeits-Tracking-Endwert (Prognose-Kanon §6): rollt mit
    # `pv_prognose_kwh` mit, bis OpenMeteo für den Tag konvergiert ist (nach
    # Sonnenuntergang) — dann via `pv_prognose_final_at` eingefroren. Das
    # Genauigkeits-Ranking liest DIESES Feld (Fallback `pv_prognose_kwh`),
    # damit der Tagesabschluss nicht aus einem Mid-Correction-Snapshot
    # gerechnet wird. Der Anzeige-Wert bleibt rollend (drei-Größen-Modell).
    pv_prognose_final_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pv_prognose_final_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Solar Forecast ML Tagesprognose (kWh): Von SFML-Sensor gelesene ML-Prognose.
    # Für Phase 2: Cockpit-Vergleich EEDC vs. ML vs. IST.
    sfml_prognose_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Solcast PV-Prognose (kWh): Tages-Forecast von Solcast (API oder HA-Sensor).
    # p50 = wahrscheinlichster Wert, p10/p90 = Konfidenzband.
    solcast_prognose_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    solcast_p10_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    solcast_p90_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Day-Ahead Stundenprofil (kWh, 24 Werte): vor Sonnenaufgang gefrorener
    # Forecast für den Tag, indexiert von Stunde 0 bis 23 (Backward-Slot-Konvention,
    # Index h = Energie im Intervall [h-1, h)). Dient als Datenbasis für künftige
    # Stundenprofil-Diagnostik (siehe docs/archive/KONZEPT-KORREKTURPROFIL.md).
    pv_prognose_stundenprofil: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    solcast_prognose_stundenprofil: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # SFML/Tom-HA echtes Stundenprofil (24 kWh-Slots, Backward) — bei gewählter
    # SFML-Quelle SFMLs eigene Kurvenform statt GTI-Schmier (Tracking #110 „A").
    sfml_prognose_stundenprofil: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Anzahl verfügbarer Stundenwerte (Qualitätsindikator)
    stunden_verfuegbar: Mapped[int] = mapped_column(Integer, default=0)

    # Datenquelle
    datenquelle: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # "ha_sensor", "mqtt", "scheduler", "monatsabschluss"

    # Börsenpreis-Tagesaggregation (EPEX Day-Ahead, immer befüllt wenn verfügbar)
    boersenpreis_avg_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    boersenpreis_min_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    negative_preis_stunden: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # kWh die bei negativem Börsenpreis eingespeist wurden (§51 EEG — Vergütungsausfall)
    einspeisung_neg_preis_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Kraftstoffpreis (Euro-Super 95, €/Liter, nationaler Wochendurchschnitt)
    # Quelle: EU Weekly Oil Bulletin. Für E-Auto-Ersparnisberechnung.
    kraftstoffpreis_euro: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # PV-/Netz-Anteil der Heimladung — ABGELEITET, nicht gemessen (N-141 Weg c,
    # `docs/KONZEPT-WALLBOX-EAUTO.md` Phase 5). Eine Wallbox zählt Kilowatt-
    # stunden, nicht deren Herkunft; wer kein evcc betreibt, hatte für den
    # PV-Anteil gar keine Quelle. Der Aggregator rechnet ihn nach der Regel
    # `einspeise_deckung` aus den Stundengrößen dieses Tages
    # (SoT `core/berechnungen/pv_anteil_ladung.py`).
    #
    # ⚠ **Ein gepflegter echter Wert gewinnt immer** — diese beiden Spalten
    # füllen nur Lücken (`services/monats_fakten.py`), sie überschreiben nichts.
    # `None` heißt „keine Aussage", ausdrücklich NICHT 0 kWh PV: genau diese
    # Behauptung löst der Fund auf.
    #
    # ⚠ Ihre Summe ist die Ladung der **gedeckten** Stunden, nicht zwingend die
    # Tagesladung — Stunden ohne Netzbezugs-/Einspeisungswert zählen nicht mit.
    # Wie viele es waren, steht in der Provenance (`stunden_gedeckt`/
    # `stunden_mit_ladung`), damit eine Teilsumme sich als solche zu erkennen
    # gibt (P4-Linie).
    emob_ladung_pv_abgeleitet_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    emob_ladung_netz_abgeleitet_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Per-Komponenten Tages-kWh (Summe der stündlichen kW-Werte)
    # z.B. {"pv_3": 22.5, "waermepumpe_5": -8.3, "wallbox_7": -12.1, "haushalt": -15.2}
    # Vorzeichen: positiv = Erzeugung (PV), negativ = Verbrauch (WP, Wallbox, etc.)
    komponenten_kwh: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Per-Komponenten Tages-Counter (Anzahl, kein kWh) — Issue #136.
    # z.B. {"wp_starts_anzahl": {"5": 12}} = WP-Investition 5 hatte 12 Starts an dem Tag.
    # Wird aus Snapshot-Differenz Tag-Anfang vs. Folgetag-Anfang berechnet.
    komponenten_starts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Per-Feld-Provenance (Etappe 3d Päckchen 1, KONZEPT-DATENPIPELINE.md Sektion 3.2).
    source_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    anlage = relationship("Anlage")
