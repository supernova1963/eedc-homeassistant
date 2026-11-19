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
* ``ansatz``, ``stand_alt_ende``, ``stand_neu_null`` — **die Rand-Werte eines Wechsels «bleiben» zwischen zwei Sensoren**
  (Sensorwechsel U2 a1, Rechenweg F1, Bauplan Nr. 138/139): ``ansatz`` leer (wie vor U2: die Zeile liest wörtlich wie am
  ``665fa8d3b``) · ``offen`` / ``offen_schnitt`` (noch nicht angesetzt — liest wie eine Naht ohne Rand-Werte) · ``beide`` (ohne
  Überlappung: die Stunde vor ``ab_ts`` zählt den alten und den neuen Sensor) · ``schnitt`` (mit Überlappung: Schnitt an
  ``ab_ts − 1 h``). ``stand_alt_ende`` / ``stand_neu_null``: letzter Stand des alten Sensors und Nullpunkt des neuen (bei
  ``beide`` 0) **in der Höhe der gespeicherten Zählerstand-Reihe** — die Reihe hebt ihre Stände ab ``ab_ts`` um die Differenz
  (``core/berechnungen/zaehler_naht.py``); Kanal und HA-Leser nehmen ihre Rand-Werte aus HA selbst (Messfrage M3).
  An einer **Lücken-Zeile** trägt ``ansatz`` den Wert ``hoehe_ungeprueft`` (Halt H-1 aus U1-K, Option A): die Korrektur füllt
  erst nach dieser leeren Zeit derselben Quelle, und kein Rand-Stand war prüfbar — der Rand gilt als Höhenwechsel
  (``zeitpunkt.ohne_hoehenwechsel``). ``nachher`` bleibt dort leer (die Erkennung «Lücken-Zeile» ändert sich nicht).
  Seit U2 a2 legen Feld-Route, Preset und «Grund nachtragen» eine Fortsetzung zwischen zwei HA-Entitäten mit ``offen`` an; der
  Dienst ``services/zuordnung_wechsel/ansatz.py`` setzt sie an (``beide``/``schnitt``, ``ab_ts`` = G + 1 h). An einer
  **Korrektur-Zeile** zwischen zwei HA-Entitäten trägt ``ansatz = schnitt`` die Rand-Stände an «Falsch seit»
  (``korrektur._rand_an_falsch_seit``; G = ``falsch_seit_ts − 1 h``).

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
GRUND_KORREKTUR = "korrektur"
HERKUNFT_WECHSEL = "wechsel"
HERKUNFT_NACHTRAG = "nachtrag"
HERKUNFT_ALTBESTAND = "altbestand"
#: Ansatz eines Wechsels «bleiben» (U2 a1, F1). Ohne Wert: wie vor U2.
ANSATZ_OFFEN = "offen"
ANSATZ_OFFEN_SCHNITT = "offen_schnitt"
ANSATZ_BEIDE = "beide"
ANSATZ_SCHNITT = "schnitt"
#: Lücken-Zeile, deren Ende (Beginn des Gefüllten) auf ungeprüfter Höhe liegt (H-1 aus U1-K, Option A).
ANSATZ_HOEHE_UNGEPRUEFT = "hoehe_ungeprueft"
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
    falsch_seit_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    herkunft: Mapped[str] = mapped_column(String(20), nullable=False)
    aufgehoben_durch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lauf: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ansatz: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    stand_alt_ende: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stand_neu_null: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_zuordnung_wechsel_anlage_key", "anlage_id", "sensor_key", "ab_ts"),
    )
