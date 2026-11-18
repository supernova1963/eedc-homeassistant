"""Zuordnungs-Wechsel je Zählerschlüssel — Vorhaben «Sensorwechsel mit Grund», Bauplan B-1 (Fassung 2, Sitzung 1).

Eine Zeile = die **wirksame** Quelle eines Zählerschlüssels (``basis:<feld>`` / ``inv:<id>:<feld>``, dasselbe Schema wie
``sensor_snapshots.sensor_key``) hat sich geändert. Die Tabelle ist die fehlende Auskunft «welcher Sensor galt wann»:

* ``erklaert_ts`` — Sekunde der Änderung (Altbestand: Zeit des Protokoll-Eintrags; eine nachgetragene «Fortsetzung» trägt die
  Sekunde des Wechsels, den sie erklärt, eine nachgetragene «Korrektur» die Sekunde des Nachtrags — Bauplan §13 Nr. 75; der
  Einstieg «Zähler getauscht» den Zeitpunkt des Tauschs), örtliche Zeit ohne Zone wie ``sensor_snapshots.zeitpunkt`` und
  ``activity_log.timestamp``.
* ``ab_ts`` — erste volle Stunde **ab** ``erklaert_ts`` (10:47:42 → 11:00; genau 11:00:00 → 11:00). Regel: ein Stand mit
  ``zeitpunkt ≥ ab_ts`` gehört zur neuen Quelle, einer davor zur alten (Lesestelle ``services/zuordnung_wechsel/zeitpunkt.py``).
* ``vorher`` / ``nachher`` — die wirksame Quelle als kleines JSON (``art`` ha · mqtt · keine; Entität bzw. MQTT-Schlüssel mit
  Topic, Pfad, Faktor, Offset der Gateway-Zeile; **keine Zugangsdaten**). ``NULL`` = unbekannt.
* ``grund`` — ``fortsetzung`` · ``korrektur`` · leer (Sitzung 1 schreibt nur leer; der Dialog kommt in Sitzung 3).
* ``falsch_seit_ts`` — nur bei ``korrektur``: ab wann die vorige Quelle falsch war.
* ``herkunft`` — ``wechsel`` (eine Route hat die Quelle geändert) · ``nachtrag`` · ``altbestand`` (aus dem Aktivitäts-Protokoll
  überführt, ``services/zuordnung_wechsel/ueberfuehrung.py``).
* ``aufgehoben_durch`` — ID einer späteren Zeile, die diese aufhebt (Sitzung 4); ``lauf`` — Kennung eines Korrektur-Laufs.

``kanal_quelle`` bleibt der Vollzug im Kanal; diese Zeile ist die Erklärung — kein Leser vergleicht beide Zeitpunkte.
Löschen: ``ON DELETE CASCADE`` an der Anlage; Gerät und Innengerät räumen ausdrücklich
(``services/zuordnung_wechsel/raeumen.py``, Aufrufer ``api/routes/investitionen/crud.py``).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base

GRUND_FORTSETZUNG = "fortsetzung"
GRUND_KORREKTUR = "korrektur"
HERKUNFT_WECHSEL = "wechsel"
HERKUNFT_NACHTRAG = "nachtrag"
HERKUNFT_ALTBESTAND = "altbestand"


class ZuordnungWechsel(Base):
    __tablename__ = "zuordnung_wechsel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )
    sensor_key: Mapped[str] = mapped_column(String(120), nullable=False)
    erklaert_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ab_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    vorher: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    nachher: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    grund: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    falsch_seit_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    herkunft: Mapped[str] = mapped_column(String(20), nullable=False)
    aufgehoben_durch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lauf: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_zuordnung_wechsel_anlage_key", "anlage_id", "sensor_key", "ab_ts"),
    )
