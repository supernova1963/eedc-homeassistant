"""Zuordnungs-Wechsel je Zählerschlüssel — Vorhaben «Sensorwechsel mit Grund», Bauplan B-1 (Fassung 2, Sitzung 1).

Eine Zeile = die **wirksame** Quelle eines Zählerschlüssels (``basis:<feld>`` / ``inv:<id>:<feld>``, dasselbe Schema wie
``sensor_snapshots.sensor_key``) hat sich geändert. Die Tabelle ist die fehlende Auskunft «welcher Sensor galt wann»:

* ``erklaert_ts`` — Sekunde der Änderung (der Einstieg «Zähler getauscht»: der Zeitpunkt des Tauschs), örtliche Zeit ohne Zone
  wie ``sensor_snapshots.zeitpunkt`` und ``activity_log.timestamp``.
* ``ab_ts`` — erste volle Stunde **ab** ``erklaert_ts`` (10:47:42 → 11:00; genau 11:00:00 → 11:00). Regel: ein Stand mit
  ``zeitpunkt ≥ ab_ts`` gehört zur neuen Quelle, einer davor zur alten (Lesestelle ``services/zuordnung_wechsel/zeitpunkt.py``).
* ``vorher`` / ``nachher`` — die wirksame Quelle als kleines JSON (``art`` ha · mqtt · keine; Entität bzw. MQTT-Schlüssel mit
  Topic, Pfad, Faktor, Offset der Gateway-Zeile; **keine Zugangsdaten**). ``NULL`` = unbekannt.
* ``grund`` — ``fortsetzung`` («Bisherige Werte bleiben», auch «Zähler getauscht») · leer (ein Wechsel ohne Frage, etwa
  nach «Keine»). «Daten vor der Änderung löschen» verzeichnet keine Zeile (``services/feld_loeschen.py``).
* ``herkunft`` — ``wechsel`` (eine Route hat die Quelle geändert).
* ``aufgehoben_durch`` — ID einer späteren Zeile, die diese aufhebt (Sitzung 4).

Seit Weg B (Sitzung B3a) entfernt: die Korrektur mit ``grund = korrektur`` und ``falsch_seit_ts``, ihre Lücken-Zeilen
(``ansatz = hoehe_ungeprueft``), ``lauf`` sowie die Herkünfte ``nachtrag``/``altbestand`` — die Tabelle war in v4.3.1 noch nicht
ausgeliefert. Eine solche Zeile aus einer Datenbank eines Zwischenstands liest wie ein Wechsel ohne Grund
(``zeitpunkt.quelle_am``); ihre Spalten bleiben dort ungelesen stehen.
* ``ansatz``, ``stand_alt_ende``, ``stand_neu_null`` — **die Rand-Werte eines Wechsels «bleiben» zwischen zwei Sensoren**
  (Sensorwechsel U2 a1, Rechenweg F1, Bauplan Nr. 138/139): ``ansatz`` leer (wie vor U2: die Zeile liest wörtlich wie am
  ``665fa8d3b``) · ``offen`` / ``offen_schnitt`` (noch nicht angesetzt — liest wie eine Naht ohne Rand-Werte) · ``beide`` (ohne
  Überlappung: die Stunde vor ``ab_ts`` zählt den alten und den neuen Sensor) · ``schnitt`` (mit Überlappung: Schnitt an
  ``ab_ts − 1 h``). ``stand_alt_ende`` / ``stand_neu_null``: letzter Stand des alten Sensors und Nullpunkt des neuen (bei
  ``beide`` 0) **in der Höhe der gespeicherten Zählerstand-Reihe** — die Reihe hebt ihre Stände ab ``ab_ts`` um die Differenz
  (``core/berechnungen/zaehler_naht.py``); Kanal und HA-Leser nehmen ihre Rand-Werte aus HA selbst (Messfrage M3).
  Seit U2 a2 legen Feld-Route und Preset eine Fortsetzung zwischen zwei HA-Entitäten mit ``offen`` an; der Dienst
  ``services/zuordnung_wechsel/ansatz.py`` setzt sie an (``beide``/``schnitt``, ``ab_ts`` = G + 1 h).

``kanal_quelle`` bleibt der Vollzug im Kanal; diese Zeile ist die Erklärung — kein Leser vergleicht beide Zeitpunkte.
Löschen: ``ON DELETE CASCADE`` an der Anlage; Gerät und Innengerät räumen ausdrücklich
(``services/zuordnung_wechsel/raeumen.py``, Aufrufer ``api/routes/investitionen/crud.py``).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base

GRUND_FORTSETZUNG = "fortsetzung"
HERKUNFT_WECHSEL = "wechsel"
#: Ansatz eines Wechsels «bleiben» (U2 a1, F1). Ohne Wert: wie vor U2.
ANSATZ_OFFEN = "offen"
ANSATZ_OFFEN_SCHNITT = "offen_schnitt"
ANSATZ_BEIDE = "beide"
ANSATZ_SCHNITT = "schnitt"
#: Angesetzt: die Zeile trägt Rand-Stände.
ANSATZ_MIT_RAND = frozenset({ANSATZ_BEIDE, ANSATZ_SCHNITT})


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
    herkunft: Mapped[str] = mapped_column(String(20), nullable=False)
    aufgehoben_durch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ansatz: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    stand_alt_ende: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stand_neu_null: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    #: Sensorwechsel U3-K (Nachmessung B5): wann eedc die Zeile eingetragen hat (Wechsel «bleiben», «Zähler getauscht» — den
    #: Grund trägt eine Zeile ab ihrer Anlage). ``monatswert_ueberholt`` nennt nur Monate bis zu diesem Monat; ``NULL`` an einer
    #: Bestandszeile = unbekannt (dann wie vorher bis zum letzten Monat).
    eingetragen_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=datetime.now)

    __table_args__ = (
        Index("ix_zuordnung_wechsel_anlage_key", "anlage_id", "sensor_key", "ab_ts"),
    )
