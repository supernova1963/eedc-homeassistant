"""
Strompreis Model

Speichert Stromtarife mit Gültigkeitszeiträumen.
"""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Float, Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class Strompreis(Base):
    """
    Stromtarif mit Gültigkeitszeitraum.

    Ermöglicht historische Preise für korrekte Berechnungen.

    Attributes:
        netzbezug_arbeitspreis_cent_kwh: Preis pro kWh in Cent
        einspeiseverguetung_cent_kwh: Vergütung pro kWh in Cent
        grundpreis_euro_monat: Monatlicher Grundpreis
        gueltig_ab/bis: Gültigkeitszeitraum
    """

    __tablename__ = "strompreise"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Preise
    netzbezug_arbeitspreis_cent_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    einspeiseverguetung_cent_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    grundpreis_euro_monat: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0)
    # G19-1 K3 (R19-3): jährliche Zähler-/Messstellengebühr — reiner AUSWEIS in
    # der Jahresaufstellung (Cockpit/Jahr-Finanzen), wird NICHT in Netto-Ertrag/
    # Kosten verrechnet (Kennzahlen-Änderung wäre ein eigener Entscheid).
    zaehlergebuehr_euro_jahr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Gültigkeit
    gueltig_ab: Mapped[date] = mapped_column(Date, nullable=False)
    gueltig_bis: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # NULL = aktuell gültig

    # Tarif-Info
    tarifname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    anbieter: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vertragsart: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # fix, dynamisch, etc.

    # #392 (gruaGit, OeMAG): die Einspeisevergütung wechselt monatlich.
    # Gefragt wird die EIGENSCHAFT („wechselt der Betrag je Monat?"), nicht der
    # Vertragsname — „Direktvermarktung" wurde am 21.08.2026 geprüft und
    # verworfen (bei geförderter Direktvermarktung ist der Erlös stabil, das
    # Feld lüde zum Falschausfüllen mit dem Monatsmarktwert ein). Bewusst
    # unabhängig von `vertragsart`: gruaGits Fall ist fixer Bezug + variable
    # Einspeisung. Mit dem Häkchen bietet der Monatsabschluss
    # `Monatsdaten.einspeise_durchschnittspreis_cent` an; der Monatswert
    # schlägt den Stammwert (`resolve_einspeise_preis_cent`, Symmetrie zu P8).
    einspeisung_variabel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Verwendung (Spezialtarife)
    verwendung: Mapped[str] = mapped_column(String(30), nullable=False, default="allgemein", server_default="allgemein")  # allgemein, waermepumpe, wallbox

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    anlage = relationship("Anlage", back_populates="strompreise")

    # N-267 (MeinerB, Discussion #380): Zeitfenster mit abweichendem Arbeitspreis.
    # ⚑ `lazy="selectin"` ist NICHT optional: `lade_tarife_fuer_anlage` ist die
    # EINE Ladestelle (ADR-002/P8) und laeuft in einer AsyncSession — ein
    # Lazy-Load beim ersten Zugriff auf `zeitfenster` wuerde dort mit
    # `MissingGreenlet` abbrechen statt still langsam zu sein. Mit selectin
    # kommen die Fenster in EINER zusaetzlichen Abfrage je Ladevorgang mit.
    zeitfenster: Mapped[list["StrompreisZeitfenster"]] = relationship(
        "StrompreisZeitfenster",
        back_populates="strompreis",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="StrompreisZeitfenster.von_stunde",
    )

    def gilt_am(self, stichtag: date) -> bool:
        """P8-Prädikat: gilt dieser Tarifsatz am Stichtag?

        Spiegelt die WHERE-Klausel von `lade_tarife_fuer_anlage`
        (`gueltig_ab <= stichtag` und offenes oder noch nicht erreichtes
        `gueltig_bis`). Eine Stelle für die Regel statt handgeschriebener
        Datumsvergleiche je Aufrufer — die Drift-Klasse, gegen die P8 gebaut
        wurde (Prüfbericht Daten-Checker 2026-08-22/B8, D5).
        """
        return self.gueltig_ab <= stichtag and (
            self.gueltig_bis is None or self.gueltig_bis >= stichtag
        )

    def __repr__(self) -> str:
        return f"<Strompreis(anlage={self.anlage_id}, ab={self.gueltig_ab}, {self.netzbezug_arbeitspreis_cent_kwh}ct)>"


class StrompreisZeitfenster(Base):
    """Ein Zeitfenster mit abweichendem Arbeitspreis (HT/NT) — N-267.

    **Warum eine eigene Tabelle und nicht zwei Spalten am Tarif.** Der Melder
    (MeinerB, Discussion #380) hat die guenstigste Bauform, die es gibt: EIN
    Fenster, taeglich gleich, nur Bezug. Das Fachgebiet hat sie nicht — der
    klassische DACH-Nachtstrom liegt bei 22–06 **plus Wochenende**, oesterreichischer
    und Schweizer Niedertarif oft Mo–Fr 22–06 **und** Sa 13:00 bis Mo 06:00, und
    manche Tarife haben **zwei** Fenster am Tag. Ein Modell aus dem Fall des
    Melders muesste beim zweiten Melder aufgebrochen werden; die **Ansicht** darf
    schmal anfangen, das Modell nicht.

    **Was ein Fenster ersetzt und was nicht.** Nur den **Arbeitspreis** des
    Netzbezugs. Grundpreis, Zaehlergebuehr und Einspeiseverguetung bleiben
    unberuehrt — es gibt in DACH keinen Zeittarif auf der Einspeiseseite
    (fest oder monatlich variabel, letzteres seit #392 abgebildet).

    **Die Fenster erben die `verwendung` ihres Tarifs.** Ein Waermepumpen-Tarif
    (§14a) kann eigene Fenster tragen, ohne dass das hier etwas kostet: das
    Fenster haengt an der Tarifzeile, und die traegt die Verwendung schon.
    """

    __tablename__ = "strompreis_zeitfenster"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    strompreis_id: Mapped[int] = mapped_column(
        ForeignKey("strompreise.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: Beginn der **Uhrzeit**-Spanne, 0–23. Das Fenster deckt ``[von_stunde, bis_stunde)``.
    von_stunde: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Ende der Spanne, 1–24 (24 = Mitternacht). ``von > bis`` laeuft ueber Mitternacht.
    bis_stunde: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Wochentage als Ziffernfolge, Montag = ``0`` … Sonntag = ``6``.
    #: Vorbelegung ``"0123456"`` = jeden Tag (der Fall des Melders).
    wochentage: Mapped[str] = mapped_column(
        String(7), nullable=False, default="0123456", server_default="0123456"
    )

    #: Der Arbeitspreis **in** diesem Fenster (ct/kWh). Ausserhalb gilt
    #: ``Strompreis.netzbezug_arbeitspreis_cent_kwh``.
    arbeitspreis_cent_kwh: Mapped[float] = mapped_column(Float, nullable=False)

    strompreis = relationship("Strompreis", back_populates="zeitfenster")

    def deckt_uhrzeit(self, zeitpunkt: datetime) -> bool:
        """Faellt diese **Uhrzeit** in das Fenster?

        ⚠ **Die Wochentag-Maske gilt fuer den Tag der Uhrzeit selbst**, nicht
        fuer den Tag, an dem ein ueber Mitternacht laufendes Fenster begonnen
        hat. „Mo–Fr 22–06" deckt damit Freitag 22–24 Uhr, **nicht** Samstag
        00–06 Uhr. Das ist eine Festlegung und keine Auslegung: die andere
        Lesart ist genauso vertretbar, und **beide sind ausdrueckbar** — wer die
        Nacht von Freitag auf Samstag mitnehmen will, legt ein zweites Fenster
        (Sa, 00–06) an. Eine Regel, die man nicht sieht, ist schlimmer als eine,
        die man einmal liest.

        ⚠ Der Aufrufer uebergibt die **Uhrzeit**, nicht den Slot-Index — die
        Umrechnung der Backward-Slots (#144) macht
        ``core/berechnungen/zeittarif.py``. Diese Methode kennt nur die Uhr.
        """
        if str(zeitpunkt.weekday()) not in (self.wochentage or "0123456"):
            return False
        h = zeitpunkt.hour
        if self.von_stunde < self.bis_stunde:
            return self.von_stunde <= h < self.bis_stunde
        # Ueber Mitternacht: [von, 24) plus [0, bis)
        return h >= self.von_stunde or h < self.bis_stunde

    def __repr__(self) -> str:
        return (
            f"<StrompreisZeitfenster({self.von_stunde}-{self.bis_stunde} Uhr, "
            f"{self.wochentage}, {self.arbeitspreis_cent_kwh}ct)>"
        )
