"""
Kanalstatistik — eedc nach HA-Bauform, Etappe E1 (Bauplan `bauplan-ha-bauform-s1-s2.md` §2).

Drei Tabellen nach dem Vorbild von Home Assistants Langzeitstatistik:

* ``kanal`` — eine Größe einer Anlage, Schlüssel im bestehenden Snapshot-Schema
  (``basis:<feld>``, ``inv:<id>:<feld>``, ``modus:inv:<id>:<betriebsart>``). **Keine** gemischten
  Achsen-Kanäle (G3): Zusammensetzung und Filter (aktiv · Anschaffung · Stilllegung · Dienstwagen)
  bleiben zur Lesezeit in den Monats-Fakten (ADR-002/P10).
* ``kanal_quelle`` — woher die Zeilen eines Kanals ab ``gueltig_ab`` stammen: Familie, Herkunft
  (HA-``statistic_id`` bzw. MQTT-Schlüssel) und ``offset``. Ein Sensortausch legt einen neuen
  Eintrag an; die Kanal-Summe ist ``sum + offset`` der für die Stunde gültigen Quelle und läuft
  damit stetig weiter (beim Stand bleibt ``state`` roh der Stand, ``offset`` überbrückt nur die
  Differenz), während die Zeilen selbst **wörtlich** bleiben (der Spiegel muss mit HA
  vergleichbar sein — Konsistenzlauf in E2).
* ``kanal_statistik`` — eine Zeile je Kanal und Stunde. ``start_ts`` = Stundenbeginn als
  Unix-Sekunden (UTC, absolut; örtliche Zeit nur bei Anzeige). Eindeutig über
  ``(kanal_id, start_ts)``: je Kanal und Stunde genau EINE Familie (Rangfolge Bauplan §2).

**Stand E2: wird geschrieben und nachgefüllt, noch von keiner Sicht gelesen.** Der Bestand
(``sensor_snapshots``, Stunden- und Tageszeilen) läuft unverändert weiter.

Löschen: alle drei Tabellen hängen per ``ON DELETE CASCADE`` an der Anlage — dasselbe Verhalten
wie ``sensor_snapshots`` (``models/sensor_snapshot.py``). Eine gelöschte Investition räumt ihre
Kanäle ebenso wenig wie heute ihre Snapshots (``api/routes/investitionen/crud.py::delete_investition``
löscht keine ``sensor_snapshots``-Zeile).
"""

from typing import Optional

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base

#: Kanal-Arten (Bauplan §2): Menge mit HAs Reset-Regel · Mittelwert je Stunde · Stand (Δ ohne Reset-Regel).
ART_SUM = "sum"
ART_MEAN = "mean"
ART_STAND = "stand"
KANAL_ARTEN: frozenset[str] = frozenset({ART_SUM, ART_MEAN, ART_STAND})

#: Familien einer Zeile (Bauplan §2, G1). ``abgeleitet`` steht im Auftrag E1 für Kanäle wie
#: ``kosten:*`` — E1 schreibt keinen davon.
FAMILIE_SPIEGEL = "spiegel"
#: ``bestand`` bleibt UNBELEGT (Entscheid Gernot 06.10., Bauplan §3b): die bisherigen Stunden- und Tageszeilen
#: werden nicht in Kanäle umgewandelt; sie bleiben die Quelle für Zeiträume, die die Kanäle nicht voll decken.
FAMILIE_BESTAND = "bestand"
FAMILIE_MITSCHRIFT = "mitschrift"
FAMILIE_ABGELEITET = "abgeleitet"
KANAL_FAMILIEN: frozenset[str] = frozenset({
    FAMILIE_SPIEGEL, FAMILIE_BESTAND, FAMILIE_MITSCHRIFT, FAMILIE_ABGELEITET,
})


class Kanal(Base):
    __tablename__ = "kanal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Einheit der gespeicherten Zahlen (``kWh`` bei ``sum`` nach der Umrechnung des heutigen Lesers,
    #: beim Stand die Einheit des Geräts, bei der Betriebsart ``Anteil`` = Bruchteil der Stunde 0…1).
    einheit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    art: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Nur für abgeleitete Kanäle: ein Neuaufbau ändert keine Zeile davor (W2). Unix-Sekunden.
    aufbaubar_ab: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("anlage_id", "key", name="uq_kanal_anlage_key"),
    )


class KanalQuelle(Base):
    __tablename__ = "kanal_quelle"

    kanal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kanal.id", ondelete="CASCADE"), primary_key=True
    )
    #: Erste Stunde (``start_ts``), für die diese Quelle gilt.
    gueltig_ab: Mapped[int] = mapped_column(Integer, primary_key=True)
    familie: Mapped[str] = mapped_column(String(12), nullable=False)
    #: HA-Entity bzw. MQTT-Schlüssel (``inv/14/pv_erzeugung_kwh``); bei der Betriebsart die
    #: ``climate``-Entität.
    statistic_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    #: Art ``sum``: Kanalwert = ``sum + offset`` (stetig über einen Sensortausch).
    #: Art ``stand``: Der Stand ist immer ``state`` roh — die Zahl auf dem Zähler (F-58); ``offset`` dient
    #: nur der Differenz über eine Quellgrenze, nie als Kanalwert.
    offset: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class KanalStatistik(Base):
    __tablename__ = "kanal_statistik"

    kanal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kanal.id", ondelete="CASCADE"), primary_key=True
    )
    start_ts: Mapped[int] = mapped_column(Integer, primary_key=True)
    sum: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    state: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    familie: Mapped[str] = mapped_column(String(12), nullable=False)
    # Der Primärschlüssel (kanal_id, start_ts) IST der eindeutige Index des Auftrags — SQLite legt
    # ihn als `sqlite_autoindex_kanal_statistik_1` an. Ein zweiter, gleich gebauter Index verdoppelte
    # nur den Platzbedarf der größten Tabelle.


class KanalNachfuellung(Base):
    """Marke „Vorgeschichte nachgefüllt" je KANAL und Entity (HA-Bauform E2, Auftrag Punkt 3; Entscheid Master 06.10.).

    Eine Zeile = für diesen Kanal ist die Vorgeschichte der Entity ``statistic_id`` aus HA geholt (oder
    geprüft und als nicht füllbar befunden — Grund in ``ergebnis``). Das Nachfüllen
    (``services/kanal/nachfuellen.py``) fragt einen Kanal mit Marke für seine heutige Entity **nicht** mehr
    bei HA an. Fehlt die Marke — neuer Kanal, oder die Zuordnung zeigt auf eine andere Entity (neue
    ``kanal_quelle``) —, holt der nächste Lauf (Startlauf oder vom Stundenlauf angestoßen) sie nach. Ein
    abgebrochener Lauf setzt keine Marke; der Fortschritt steckt in den Zeilen selbst.

    Bis 06.10. war die Marke je Anlage und Familie — ein später zugeordneter Sensor bekam dann nie seine
    Vorgeschichte. E2 ist nicht ausgeliefert: die Tabelle gab es beim Anwender nie, es braucht keine Migration.
    """

    __tablename__ = "kanal_nachfuellung"

    kanal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kanal.id", ondelete="CASCADE"), primary_key=True
    )
    #: Die Entity, deren Vorgeschichte gefüllt bzw. geprüft ist.
    statistic_id: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Unix-Sekunden des Abschlusses.
    abgeschlossen_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Zählung für diesen Kanal (Zeilen, Blöcke, ggf. Grund, warum nichts zu füllen war).
    ergebnis: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True), nullable=True)
