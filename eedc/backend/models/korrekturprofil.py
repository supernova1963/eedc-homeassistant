"""
Korrekturprofil — anlagen-spezifische Lernfaktor-Tabelle.

Speichert das mehrdimensionale Korrekturprofil aus
docs/KONZEPT-KORREKTURPROFIL.md. Pro Anlage existiert genau ein Profil
für `(anlage_id, investition_id, quelle, profil_typ)` — der Aggregator
schreibt jeweils das aktuell beste verfügbare `profil_typ`-Niveau, der
Live-Lookup nutzt die Fallback-Kaskade über mehrere `profil_typ`-Zeilen.

Schema bewusst flexibel (`bin_definition` + `faktoren` als JSON), damit
Variante C (`investition_id` gesetzt) und alle Fallback-Stufen ohne
Schema-Änderung tragen.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


# Profil-Typen (siehe KONZEPT-KORREKTURPROFIL.md)
PROFIL_TYP_SONNENSTAND_WETTER = "sonnenstand_wetter"
PROFIL_TYP_SONNENSTAND = "sonnenstand"
PROFIL_TYP_STUNDE = "stunde"  # Saisonbin × Stunde (klassische Variante-A-Logik)
PROFIL_TYP_SKALAR = "skalar"  # Skalar-Lernfaktor mit O1+O2

PROFIL_TYP_KASKADE = (
    PROFIL_TYP_SONNENSTAND_WETTER,
    PROFIL_TYP_SONNENSTAND,
    PROFIL_TYP_STUNDE,
    PROFIL_TYP_SKALAR,
)


class Korrekturprofil(Base):
    """Lernfaktor-Profil pro `(anlage, investition?, quelle, profil_typ)`.

    `investition_id` = NULL → Anlagensumme (Default).
    `investition_id` gesetzt → Variante C (String-spezifisch, reaktiv).
    """

    __tablename__ = "korrekturprofile"
    __table_args__ = (
        UniqueConstraint(
            "anlage_id",
            "investition_id",
            "quelle",
            "profil_typ",
            name="uq_korrekturprofil_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False, index=True
    )
    investition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investitionen.id", ondelete="CASCADE"), nullable=True
    )
    # Wetter-/Strahlungsquelle, gegen die korrigiert wird. Heute ausschließlich
    # "openmeteo" (EEDC-Default). Wird für künftige Solcast-Direktkorrektur
    # bereits jetzt mitgeführt.
    quelle: Mapped[str] = mapped_column(String(20), nullable=False, default="openmeteo")
    profil_typ: Mapped[str] = mapped_column(String(30), nullable=False)
    # einer aus PROFIL_TYP_KASKADE

    # Bin-Definition für Reproduzierbarkeit der faktoren-Schlüssel.
    # sonnenstand_wetter:
    #   {"azimut_aufloesung": 10, "elevation_aufloesung": 10,
    #    "wetterklassen": ["klar", "diffus", "wechselhaft"]}
    # sonnenstand: {"azimut_aufloesung": 10, "elevation_aufloesung": 10}
    # stunde: {"saisonbin": "monat" | "quartal" | "gesamt"}
    # skalar: {"variante": "legacy" | "o12"}
    bin_definition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Korrektur-Faktoren pro Bin.
    # sonnenstand_wetter: {"110_30_klar": 0.72, "110_30_diffus": 0.95, ...}
    # sonnenstand: {"110_30": 0.80, ...}
    # stunde: {"4": {"7": 0.85, ...}, ...}  (Saisonbin → Stunde → Faktor)
    # skalar: {"value": 1.01}
    faktoren: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Datenpunkte pro Bin — Basis für Fallback-Kaskade
    # ({bin_key: anzahl_stunden}). Bei Skalar: {"value": gesamt_tage}.
    datenpunkte_pro_bin: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Aggregator-Metadaten
    tage_eingegangen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aktualisiert_am: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    # Skalar-Faktor-Wert für schnellen Zugriff (z. B. Diagnose-Header).
    # NULL für nicht-skalare Profil-Typen.
    faktor_skalar: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    anlage = relationship("Anlage")
    investition = relationship("Investition")
