"""Ladeblöcke je Auto — N-555 Stufe 3 (Konzept Heimladung/Fahrverbrauch 7.2, Regel 9, Anhang D).

Eine Zeile je **Ladevorgang** eines E-Autos: der Sprung seines Heimlade-Zählers („Heim: gesamt")
und die Wallbox-Stunden, die ihm zugeordnet sind (``services/emob_ladebloecke.py``).

**Sitzungsgebunden, nicht tagesgebunden:** ein Vorgang über Mitternacht berührt zwei Tage — der
Sprung liegt an D+1, Stunden an D. Deshalb eine eigene Tabelle statt einer Tagesspalte.

⛔ **Nicht in ``TagesZusammenfassung.komponenten_kwh``/``komponenten``:** dort meldete
``daten_checker/emob.py::_check_emob_doppelzaehlung_tage`` jeden Tag, an dem Wallbox und Auto
beide eine Ladung tragen (Fable-Runde 7, „Übersehen").

``kwh`` ist der Sprung (G2), ``pv_kwh``/``netz_kwh`` ``NULL``, wenn keine Blockstunde ableitbar war
(Bündel, W-A) — der Leser nimmt dann den Wallbox-Monatsanteil. ``stunden`` trägt je Blockstunde
``{"beginn", "kwh", "n", "pv_anteil"}`` (Monatsverteilung, D-3). Geschrieben wird die Zeile vom
Stufe-3-Hook in ``aggregate_day`` (idempotent je Tag: die Sprünge eines Tages werden ersetzt).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class EmobLadeblock(Base):
    __tablename__ = "emob_ladebloecke"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )
    investition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("investitionen.id", ondelete="CASCADE"), nullable=False
    )
    #: Beginn der frühesten Blockstunde (lokal, naiv — wie ``sensor_snapshots.zeitpunkt``).
    beginn: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    #: Ende der Sprungstunde.
    ende: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kwh: Mapped[float] = mapped_column(Float, nullable=False)
    pv_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    netz_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stunden: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    stunden_gedeckt: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    luecke: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: N-569-Ergänzung (Anhang E): davon aus dem Speicher — Teilmenge von ``pv_kwh``;
    #: ``NULL`` ohne Speicherzähler oder ohne ableitbare Blockstunde.
    speicher_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    regel: Mapped[str] = mapped_column(String(40), nullable=False)
    #: ``ha_statistics`` | ``snapshot`` — woher die Slots kamen.
    quelle: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint("anlage_id", "investition_id", "ende", name="uq_emob_ladeblock"),
        Index("ix_emob_ladeblock_anlage_ende", "anlage_id", "ende"),
    )
