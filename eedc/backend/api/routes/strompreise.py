"""
Strompreise API Routes

CRUD Endpoints für Stromtarife.
"""

from typing import Iterable, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.strompreis import Strompreis, StrompreisZeitfenster
from backend.models.anlage import Anlage


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ZeitfensterBase(BaseModel):
    """Ein HT/NT-Zeitfenster am Tarif (N-267, Discussion #380).

    ``von_stunde``/``bis_stunde`` sind **Uhrzeiten**, keine Slot-Indizes — die
    Umrechnung auf die Backward-Slots (#144) macht
    ``core/berechnungen/zeittarif.py``. ``bis_stunde = 24`` bedeutet Mitternacht;
    ``von > bis`` läuft über Mitternacht (Nachtstrom 22–06).
    """
    von_stunde: int = Field(..., ge=0, le=23)
    bis_stunde: int = Field(..., ge=1, le=24)
    wochentage: str = Field(
        "0123456",
        pattern=r"^[0-6]{1,7}$",
        description="Montag = 0 … Sonntag = 6; Vorbelegung: jeden Tag",
    )
    arbeitspreis_cent_kwh: float = Field(..., ge=0)

    @field_validator("wochentage")
    @classmethod
    def _tage_eindeutig(cls, v: str) -> str:
        if len(set(v)) != len(v):
            raise ValueError("Ein Wochentag darf nur einmal vorkommen")
        return "".join(sorted(set(v)))

    @model_validator(mode="after")
    def _spanne_ist_nicht_leer(self):
        """``von == bis`` ist mehrdeutig — leerer Tag oder ganzer Tag?

        Beides wäre vertretbar, und genau deshalb wird nichts geraten. Wer den
        ganzen Tag meint, trägt 0–24 ein.
        """
        if self.von_stunde == self.bis_stunde:
            raise ValueError(
                "„Von\" und „Bis\" dürfen nicht gleich sein — für den ganzen Tag 0 bis 24 eintragen"
            )
        return self


class ZeitfensterResponse(ZeitfensterBase):
    id: int

    class Config:
        from_attributes = True


class StrompreisBase(BaseModel):
    """Basis-Schema für Strompreis."""
    netzbezug_arbeitspreis_cent_kwh: float = Field(..., ge=0)
    einspeiseverguetung_cent_kwh: float = Field(..., ge=0)
    grundpreis_euro_monat: Optional[float] = Field(0, ge=0)
    # G19-1 K3: jährliche Zähler-/Messstellengebühr (Ausweis in der Jahresaufstellung)
    zaehlergebuehr_euro_jahr: Optional[float] = Field(None, ge=0)
    gueltig_ab: date
    gueltig_bis: Optional[date] = None
    tarifname: Optional[str] = Field(None, max_length=255)
    anbieter: Optional[str] = Field(None, max_length=255)
    vertragsart: Optional[str] = Field(None, max_length=50)
    verwendung: str = Field("allgemein", description="Tarif-Verwendung: allgemein, waermepumpe, wallbox")
    # #392: „Einspeisevergütung wechselt monatlich" — schaltet das Monatsfeld
    # `einspeise_durchschnittspreis_cent` im Monatsabschluss frei.
    einspeisung_variabel: bool = False
    # N-267: HT/NT-Zeitfenster. Leere Liste = Einpreistarif wie bisher.
    zeitfenster: list[ZeitfensterBase] = Field(default_factory=list)


class StrompreisCreate(StrompreisBase):
    """Schema für Strompreis-Erstellung."""
    anlage_id: int


class StrompreisUpdate(BaseModel):
    """Schema für Strompreis-Update."""
    netzbezug_arbeitspreis_cent_kwh: Optional[float] = Field(None, ge=0)
    einspeiseverguetung_cent_kwh: Optional[float] = Field(None, ge=0)
    grundpreis_euro_monat: Optional[float] = Field(None, ge=0)
    zaehlergebuehr_euro_jahr: Optional[float] = Field(None, ge=0)
    gueltig_ab: Optional[date] = None
    gueltig_bis: Optional[date] = None
    tarifname: Optional[str] = Field(None, max_length=255)
    anbieter: Optional[str] = Field(None, max_length=255)
    vertragsart: Optional[str] = Field(None, max_length=50)
    verwendung: Optional[str] = Field(None, description="Tarif-Verwendung: allgemein, waermepumpe, wallbox")
    einspeisung_variabel: Optional[bool] = None
    # N-267: die Fenster werden als GANZE Liste ersetzt, nicht einzeln gepflegt —
    # ein Tarif hat wenige, und Teil-Updates bräuchten eine zweite Route samt
    # eigener Rechteprüfung für einen Nutzen, den niemand gemeldet hat.
    # `None` = unverändert lassen, `[]` = alle Fenster entfernen.
    zeitfenster: Optional[list[ZeitfensterBase]] = None


class StrompreisResponse(StrompreisBase):
    """Schema für Strompreis-Response."""
    id: int
    anlage_id: int
    zeitfenster: list[ZeitfensterResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


# =============================================================================
# Helper: Tarife nach Verwendung laden
# =============================================================================

async def lade_tarife_fuer_anlage(
    db: AsyncSession,
    anlage_id: int,
    target_date: Optional[date] = None,
) -> dict[str, Strompreis | None]:
    """
    Lädt die zum target_date gültigen Tarife nach Verwendung.

    Args:
        target_date: Stichtag für den Tarif (default: heute).
                     Für historische Berechnungen den 1. des jeweiligen Monats übergeben.

    Returns:
        Dict mit Keys 'allgemein', 'waermepumpe', 'wallbox'.
        WP/Wallbox fallen auf allgemein zurück wenn kein Spezialtarif existiert.
    """
    stichtag = target_date or date.today()
    query = select(Strompreis).where(
        Strompreis.anlage_id == anlage_id,
        Strompreis.gueltig_ab <= stichtag,
        (Strompreis.gueltig_bis.is_(None) | (Strompreis.gueltig_bis >= stichtag))
    ).order_by(Strompreis.gueltig_ab.desc())

    result = await db.execute(query)
    alle_preise = result.scalars().all()

    # Nach Verwendung gruppieren (erster = neuester wg. ORDER BY DESC)
    tarife: dict[str, Strompreis | None] = {"allgemein": None, "waermepumpe": None, "wallbox": None}
    for preis in alle_preise:
        verwendung = preis.verwendung or "allgemein"
        if verwendung in tarife and tarife[verwendung] is None:
            tarife[verwendung] = preis

    # Fallback: WP/Wallbox → allgemein
    allgemein = tarife["allgemein"]
    if tarife["waermepumpe"] is None:
        tarife["waermepumpe"] = allgemein
    if tarife["wallbox"] is None:
        tarife["wallbox"] = allgemein

    return tarife


async def monats_strompreis_lookup(
    db: AsyncSession,
    anlage_id: int,
    verwendung: str,
    monate: Iterable[tuple[int, int]],
    fallback_bezug: float,
) -> dict[tuple[int, int], float]:
    """``{(jahr, monat): netzbezugspreis_cent}`` — der Tarif, der DAMALS galt.

    F-18: bis 2026-08-08 war die Monatstarif-Auflösung in
    ``_gewichtete_monatspreise`` eingeschlossen und nur über dessen
    Ø-Rückgabe erreichbar. Cockpit → Jahr und beide HA-Export-Pfade kamen
    deshalb gar nicht an sie heran und rechneten mit dem **heutigen** Tarif.
    Als eigener Helfer ist sie das, was der Layer-SoT
    ``aufgeloester_strompreis_cent`` als Eingabe erwartet — dieselbe Rolle,
    die ``Monatsdaten.kraftstoffpreis_euro`` auf der Benzinseite längst hat.

    Bewusst **ohne** Flex-Ø: der ``resolve_netzbezug_preis_cent``-Override
    braucht die Monatsdaten-Zeile, die hier nicht vorliegt. Wer sie hat
    (Cockpit über ``f.tarif.wallbox_preis_effektiv_cent``), liefert den
    genaueren Wert — beide sind derselbe Stammtarif, nur einmal mit und
    einmal ohne den abgerechneten Durchschnitt.
    """
    # N-267: Der Zeittarif faehrt hier mit, weil diese Funktion die DRITTE
    # Bildungsstelle des Monatspreises ist (neben `monats_fakten::_lade_tarif`
    # und `finanz_zeilen::baue_finanz_zeile`). Haette sie sie nicht, stuende in
    # der E-Mob-Ersparnis der Hochtarif, waehrend Cockpit und PDF daneben den
    # gewichteten Preis nennen — genau die „zwei Zahlen auf einer Seite",
    # gegen die F-18 gebaut wurde.
    from backend.services.strompreis_aggregator import wirksamer_arbeitspreis_cent

    lookup: dict[tuple[int, int], float] = {}
    zeittarif_cache: dict = {}
    for jahr, monat in dict.fromkeys(monate):
        m_tarife = await lade_tarife_fuer_anlage(
            db, anlage_id, target_date=date(jahr, monat, 1)
        )
        m_tarif = resolve_tarif_for_komponente(m_tarife, verwendung)
        if m_tarif is None:
            lookup[(jahr, monat)] = fallback_bezug
            continue
        lookup[(jahr, monat)] = await wirksamer_arbeitspreis_cent(
            db, anlage_id, jahr, monat, m_tarif, cache=zeittarif_cache
        )
    return lookup


def resolve_netzbezug_preis_cent(monatsdaten_obj, tarif_preis_cent: float) -> float:
    """
    Löst den effektiven Netzbezugspreis für einen Monat auf.

    Fallback-Kette:
    1. monatsdaten.netzbezug_durchschnittspreis_cent (dynamischer Tarif-Ø)
    2. tarif_preis_cent (fixer Preis aus Stammdaten)
    """
    if monatsdaten_obj and getattr(monatsdaten_obj, 'netzbezug_durchschnittspreis_cent', None) is not None:
        return monatsdaten_obj.netzbezug_durchschnittspreis_cent
    return tarif_preis_cent


def resolve_tarif_for_komponente(
    tarife: dict,
    komponente: str = "allgemein",
) -> Optional[Strompreis]:
    """Dieselbe Kaskade wie `resolve_strompreis_for_komponente` — aber die
    **Tarifzeile** statt ihres Preises.

    Es gibt sie seit N-267 (HT/NT-Zeitfenster): Der wirksame Arbeitspreis eines
    Monats hängt nicht mehr nur an einer Spalte, sondern an den Fenstern der
    Zeile. Wer sie braucht, braucht das Objekt.

    ⚑ **Eine Kaskade, zwei Sichten** — `resolve_strompreis_for_komponente` ist
    seither über diese Funktion ausgedrückt. Die Regel (Komponente → allgemein →
    Default) steht damit weiterhin an **einer** Stelle; eine zweite Fassung wäre
    genau die Drift, gegen die der Helfer im Drift-Audit E gebaut wurde.
    """
    if komponente != "allgemein":
        komp_tarif = tarife.get(komponente)
        if komp_tarif and komp_tarif.netzbezug_arbeitspreis_cent_kwh is not None:
            return komp_tarif
    allgemein = tarife.get("allgemein")
    if allgemein and allgemein.netzbezug_arbeitspreis_cent_kwh is not None:
        return allgemein
    return None


def resolve_strompreis_for_komponente(
    tarife: dict,
    komponente: str = "allgemein",
    fallback: Optional[float] = None,
) -> float:
    """Liest komponenten-spezifischen Tarif mit Fallback auf allgemein.

    Single Source of Truth für die Strompreis-Lookup-Kaskade (Drift-Audit E):
    1. Komponenten-spezifischer Tarif (z.B. `waermepumpe` oder `wallbox`)
    2. Allgemeiner Tarif
    3. Kanonischer Default `NETZBEZUG_DEFAULT_CENT` (oder explizit übergebener Fallback)

    Args:
        tarife: Dict aus `lade_tarife_fuer_anlage()`
        komponente: "allgemein" | "waermepumpe" | "wallbox"
        fallback: Override des kanonischen Defaults (z.B. wenn Caller eine
                  spezielle Default-Logik braucht)

    Returns:
        Strompreis in ct/kWh.
    """
    from backend.core.wirtschaftlichkeit_defaults import NETZBEZUG_DEFAULT_CENT

    tarif = resolve_tarif_for_komponente(tarife, komponente)
    if tarif is not None:
        return tarif.netzbezug_arbeitspreis_cent_kwh

    return fallback if fallback is not None else NETZBEZUG_DEFAULT_CENT


def resolve_einspeiseverguetung_cent(
    tarife: dict,
    fallback: Optional[float] = None,
) -> float:
    """Liest die Einspeisevergütung aus dem allgemeinen Tarif.

    Das Gegenstück zu `resolve_strompreis_for_komponente` für die ANDERE
    Preisseite. Es gibt es, weil der P8-Sweep (v4.0.5) den Arbeitspreis auf
    den Monats-Stichtag gezogen hat und die Vergütung nicht: wo beide in
    dieselbe Formel gehen — jeder Spread `bezug − einspeise` bei Speicher,
    V2H und BKW —, stammten die zwei Summanden danach aus verschiedenen
    Zeitpunkten. Ein Resolver je Seite macht die Asymmetrie beim Lesen
    sichtbar, statt sie in ein `if tarif else DEFAULT` je Aufrufer zu streuen.

    Anders als beim Arbeitspreis gibt es keine Komponenten-Staffelung: eine
    Wärmepumpe hat einen eigenen Bezugstarif, aber keine eigene Vergütung.

    Args:
        tarife: Dict aus `lade_tarife_fuer_anlage()` — für einen historischen
                Monat mit dessen Stichtag geladen (ADR-002/P8).
        fallback: Override des kanonischen Defaults.

    Returns:
        Einspeisevergütung in ct/kWh.
    """
    from backend.core.wirtschaftlichkeit_defaults import EINSPEISEVERGUETUNG_DEFAULT_CENT

    allgemein = tarife.get("allgemein")
    if allgemein and allgemein.einspeiseverguetung_cent_kwh is not None:
        return allgemein.einspeiseverguetung_cent_kwh

    return fallback if fallback is not None else EINSPEISEVERGUETUNG_DEFAULT_CENT


def resolve_einspeise_preis_cent(monatsdaten_obj, tarif_verguetung_cent: float) -> float:
    """
    Löst die effektive Einspeisevergütung für einen Monat auf (#392).

    Fallback-Kette — dieselbe Bauform wie `resolve_netzbezug_preis_cent`:
    1. monatsdaten.einspeise_durchschnittspreis_cent (variable Vergütung,
       z. B. OeMAG-Marktpreis — der Satz des Monats)
    2. tarif_verguetung_cent (Stammwert aus dem Tarif, typischerweise über
       `resolve_einspeiseverguetung_cent` mit dem Monats-Stichtag geladen)

    `is not None`, nicht truthy: **0 ct ist ein gepflegter Wert** (seit
    08.08.2026 die Vorbelegung eines neuen Tarifs) und gewinnt.
    """
    if monatsdaten_obj and getattr(monatsdaten_obj, 'einspeise_durchschnittspreis_cent', None) is not None:
        return monatsdaten_obj.einspeise_durchschnittspreis_cent
    return tarif_verguetung_cent


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/", response_model=list[StrompreisResponse])
async def list_strompreise(
    anlage_id: Optional[int] = Query(None, description="Filter nach Anlage"),
    aktuell: Optional[bool] = Query(None, description="Nur aktuell gültige"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Strompreise zurück, optional gefiltert.

    Args:
        anlage_id: Optional - nur Preise dieser Anlage
        aktuell: Optional - nur aktuell gültige Tarife

    Returns:
        list[StrompreisResponse]: Liste der Strompreise
    """
    query = select(Strompreis)

    if anlage_id:
        query = query.where(Strompreis.anlage_id == anlage_id)

    if aktuell:
        today = date.today()
        query = query.where(
            and_(
                Strompreis.gueltig_ab <= today,
                (Strompreis.gueltig_bis.is_(None) | (Strompreis.gueltig_bis >= today))
            )
        )

    query = query.order_by(Strompreis.gueltig_ab.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/aktuell/{anlage_id}", response_model=StrompreisResponse)
async def get_aktueller_strompreis(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt den aktuell gültigen Strompreis einer Anlage zurück.

    Args:
        anlage_id: ID der Anlage

    Returns:
        StrompreisResponse: Der aktuelle Tarif

    Raises:
        404: Kein aktueller Tarif gefunden
    """
    today = date.today()
    query = select(Strompreis).where(
        Strompreis.anlage_id == anlage_id,
        Strompreis.gueltig_ab <= today,
        (Strompreis.gueltig_bis.is_(None) | (Strompreis.gueltig_bis >= today))
    ).order_by(Strompreis.gueltig_ab.desc()).limit(1)

    result = await db.execute(query)
    preis = result.scalar_one_or_none()

    if not preis:
        raise HTTPException(
            status_code=404,
            detail="Kein aktueller Strompreis für diese Anlage gefunden"
        )

    return preis


@router.get("/aktuell/{anlage_id}/{verwendung}", response_model=StrompreisResponse)
async def get_aktueller_strompreis_fuer(
    anlage_id: int,
    verwendung: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt den aktuellen Tarif für eine bestimmte Verwendung zurück.
    Fällt auf 'allgemein' zurück wenn kein Spezialtarif existiert.
    """
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    preis = tarife.get(verwendung) or tarife.get("allgemein")

    if not preis:
        raise HTTPException(
            status_code=404,
            detail=f"Kein aktueller Strompreis für Verwendung '{verwendung}' gefunden"
        )

    return preis


@router.get("/{strompreis_id}", response_model=StrompreisResponse)
async def get_strompreis(strompreis_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt einen einzelnen Strompreis zurück.

    Args:
        strompreis_id: ID des Strompreises

    Returns:
        StrompreisResponse: Der Strompreis

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Strompreis).where(Strompreis.id == strompreis_id))
    preis = result.scalar_one_or_none()

    if not preis:
        raise not_found("Strompreis")

    return preis


@router.post("/", response_model=StrompreisResponse, status_code=status.HTTP_201_CREATED)
async def create_strompreis(data: StrompreisCreate, db: AsyncSession = Depends(get_db)):
    """
    Erstellt einen neuen Strompreis.

    Args:
        data: Strompreis-Daten

    Returns:
        StrompreisResponse: Der erstellte Strompreis

    Raises:
        404: Anlage nicht gefunden
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == data.anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise not_found("Anlage")

    werte = data.model_dump()
    fenster = werte.pop("zeitfenster", []) or []
    preis = Strompreis(**werte)
    preis.zeitfenster = [StrompreisZeitfenster(**f) for f in fenster]
    db.add(preis)
    await db.flush()
    await db.refresh(preis)
    return preis


@router.put("/{strompreis_id}", response_model=StrompreisResponse)
async def update_strompreis(
    strompreis_id: int,
    data: StrompreisUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert einen Strompreis.

    Args:
        strompreis_id: ID des Strompreises
        data: Zu aktualisierende Felder

    Returns:
        StrompreisResponse: Der aktualisierte Strompreis

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Strompreis).where(Strompreis.id == strompreis_id))
    preis = result.scalar_one_or_none()

    if not preis:
        raise not_found("Strompreis")

    update_data = data.model_dump(exclude_unset=True)
    # N-267: Die Fenster sind eine Beziehung, keine Spalte — `setattr` mit den
    # Dicts aus dem Schema wuerde SQLAlchemy eine Liste von dicts unterschieben.
    # `delete-orphan` an der Beziehung raeumt die ersetzten Zeilen mit ab.
    neue_fenster = update_data.pop("zeitfenster", None)
    for field, value in update_data.items():
        setattr(preis, field, value)
    if neue_fenster is not None:
        preis.zeitfenster = [StrompreisZeitfenster(**f) for f in neue_fenster]

    await db.flush()
    await db.refresh(preis)
    return preis


@router.delete("/{strompreis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strompreis(strompreis_id: int, db: AsyncSession = Depends(get_db)):
    """
    Löscht einen Strompreis.

    Args:
        strompreis_id: ID des Strompreises

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Strompreis).where(Strompreis.id == strompreis_id))
    preis = result.scalar_one_or_none()

    if not preis:
        raise not_found("Strompreis")

    await db.delete(preis)
