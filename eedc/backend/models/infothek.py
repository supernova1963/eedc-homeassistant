"""
Infothek Models

Speichert Verträge, Zähler, Kontakte und Dokumentation.
Optionales Modul mit kategorie-spezifischen Vorlagen.
"""

from datetime import datetime
from typing import Optional, Any
from sqlalchemy import Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class InfothekEintrag(Base):
    """
    Ein Infothek-Eintrag (Vertrag, Zähler, Kontakt, etc.).

    Kategorie-spezifische Felder werden im parameter-JSON gespeichert.
    """

    __tablename__ = "infothek_eintraege"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Kernfelder
    bezeichnung: Mapped[str] = mapped_column(String(255), nullable=False)
    kategorie: Mapped[str] = mapped_column(String(50), nullable=False)
    notizen: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Kategorie-spezifische Felder (JSON)
    parameter: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Verknüpfung mit Investition (Etappe 3)
    investition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investitionen.id", ondelete="SET NULL"),
        nullable=True
    )

    # Verknüpfung mit Ansprechpartner (anderer Infothek-Eintrag, Kategorie "ansprechpartner")
    ansprechpartner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("infothek_eintraege.id", ondelete="SET NULL"),
        nullable=True
    )

    # Sortierung und Status
    sortierung: Mapped[int] = mapped_column(Integer, default=0)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    anlage = relationship("Anlage", back_populates="infothek_eintraege")
    dateien = relationship("InfothekDatei", back_populates="eintrag", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<InfothekEintrag(id={self.id}, bezeichnung='{self.bezeichnung}', kategorie='{self.kategorie}')>"


class InfothekDatei(Base):
    """
    Eine Datei (Foto oder PDF) zu einem Infothek-Eintrag.

    Bilder werden serverseitig auf max 500kb resized, Thumbnails auf ~50kb.
    PDFs werden ohne Konvertierung gespeichert (max 5 MB).
    Max 3 Dateien pro Eintrag.
    """

    __tablename__ = "infothek_dateien"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    eintrag_id: Mapped[int] = mapped_column(
        ForeignKey("infothek_eintraege.id", ondelete="CASCADE"), nullable=False
    )

    # Datei-Metadaten
    dateiname: Mapped[str] = mapped_column(String(255), nullable=False)
    dateityp: Mapped[str] = mapped_column(String(10), nullable=False)  # 'image' oder 'pdf'
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    beschreibung: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Datei-Daten (BLOB)
    daten: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    thumbnail: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # Nur für Bilder

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    eintrag = relationship("InfothekEintrag", back_populates="dateien")

    def __repr__(self) -> str:
        return f"<InfothekDatei(id={self.id}, dateiname='{self.dateiname}', dateityp='{self.dateityp}')>"
