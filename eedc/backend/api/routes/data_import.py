"""
Portal-Import API Routes.

Ermöglicht den Import von Energiedaten aus Hersteller-Portal-Exporten (CSV).
Unterstützt Auto-Detection des Formats und Vorschau vor dem Import.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.services.import_parsers import (
    list_parsers,
    get_parser,
    auto_detect_parser,
    ParsedMonthData,
)
from backend.api.routes.import_export.helpers import (
    _upsert_investition_monatsdaten,
    _distribute_legacy_pv_to_modules,
    _distribute_legacy_battery_to_storages,
)
from backend.services.activity_service import log_activity
from backend.services.erzeuger_ziel import ZielFehler, loese_ziel
from backend.services.provenance import write_with_provenance
from backend.services.import_hauszaehler import entscheide_hauszaehler
from backend.services.import_writer import zaehle_manuelle_werte
from backend.services.pv_orientation import get_pv_kwp
from backend.utils.investition_value import get_inv_value

logger = logging.getLogger(__name__)

router = APIRouter()

# Etappe 3d Päckchen 2: Source-Konstante für die Provenance-Wrapper.
# Aktuell werden alle Datenquellen unter external:portal_import geführt
# (gleiche Hierarchie-Klasse wie external:cloud_import:*), weil das
# Frontend den konkreten Cloud-Provider-Slug nicht durchreicht. Der writer
# differenziert via datenquelle für Diagnose-Queries auf data_provenance_log
# und steht deshalb im `ImportKontext`, nicht hier.
_PROVENANCE_SOURCE = "external:portal_import"


# ─── Schemas ─────────────────────────────────────────────────────────────────


class ParserInfoResponse(BaseModel):
    id: str
    name: str
    hersteller: str
    beschreibung: str
    erwartetes_format: str
    anleitung: str
    beispiel_header: str
    getestet: bool = True


class ParsedMonthResponse(BaseModel):
    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    eauto_km_gefahren: Optional[float] = None


class PreviewResponse(BaseModel):
    parser: ParserInfoResponse
    monate: list[ParsedMonthResponse]
    anzahl_monate: int


class ApplyMonthInput(BaseModel):
    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    eauto_km_gefahren: Optional[float] = None


class InvestitionsZuordnung(BaseModel):
    """
    Optionale manuelle Zuordnung von Import-Werten zu Investitionen.
    Wird nur benötigt wenn mehrere Investitionen desselben Typs vorhanden sind.
    """
    # PV: {inv_id: anteil_prozent} — muss 100 ergeben, sonst proportional
    pv: dict[int, float] = {}
    # Batterie: {inv_id: anteil_prozent} — muss 100 ergeben, sonst proportional
    batterie: dict[int, float] = {}
    # Wallbox: ID der zu verwendenden Wallbox (None = erste)
    wallbox_id: Optional[int] = None
    # E-Auto: ID des zu verwendenden E-Autos (None = erste)
    eauto_id: Optional[int] = None


class ApplyRequest(BaseModel):
    monate: list[ApplyMonthInput]
    zuordnung: Optional[InvestitionsZuordnung] = None
    # N-229 (#349, OliS2811): Eine Cloud-Station misst EIN Gerät, keine Anlage —
    # Solarman führt je Wechselrichter eine eigene „Station". Ohne Ziel schreibt
    # der Apply die anlagenweiten Hauszähler-Felder; bei zwei Stationen an einem
    # Hausanschluss überschreibt die zweite Einfuhr damit die erste.
    #
    # Mit Ziel gilt: die Werte gehören diesem Erzeuger. Geschrieben wird
    # ausschließlich seine `InvestitionMonatsdaten`-Zeile, `Monatsdaten` bleibt
    # unberührt — P7-konform, denn gemessene Pro-Modul-Werte schlagen das
    # Aggregat ohnehin (`core/berechnungen/pv_verteilung.py`), und ein Aggregat
    # aus EINER von zwei Stationen wäre genau die Teilsumme, die ADR-002/P7
    # verbietet. `None` = bisheriges Verhalten, unverändert.
    ziel_investition_id: Optional[int] = None


class ApplyResponse(BaseModel):
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]
    warnungen: list[str]
    # Etappe 3d Päckchen 2: Anzahl Feld-Werte, die durch Quellen-Hierarchie
    # geschützt wurden (manuell gepflegte Werte überleben Cloud-/Portal-Apply
    # auch bei ueberschreiben=True). Datenbasis für den Wizard-Hinweis
    # „X Felder durch manuelle Werte geschützt".
    geschuetzt_count: int = 0
    geschuetzte_felder: list[str] = []  # Top-15 Sample für Diagnose


class ZuordnungInvestition(BaseModel):
    id: int
    bezeichnung: str
    kwp: Optional[float] = None       # PV-Module
    kwh: Optional[float] = None       # Speicher
    default_anteil: float = 0.0       # vorberechneter Default-Anteil in %
    # True = die Bezugsgröße (kWp bzw. kWh) ist NICHT gepflegt, der Vorschlag
    # ist reine Gleichverteilung `100/N`. Der Wizard muss das sagen, statt eine
    # gleichmäßige Aufteilung als errechneten Vorschlag auszugeben (N59/P4).
    anteil_geschaetzt: bool = False


class ManuelleWerteInfo(BaseModel):
    """Was ein Import mit „Bestehende Monate überschreiben" ersetzen würde.

    Der Haken durchbricht seit 12.08. auch die Hierarchie über manuell
    gepflegten Werten. Damit das eine Anordnung bleibt und keine Überraschung,
    fragt der Wizard diese Zahl VOR dem Import ab.
    """
    betroffen: bool
    monate: int
    felder: int
    beispiele: list[str] = []


class ZuordnungInfo(BaseModel):
    benoetigt_zuordnung: bool
    pv_module: list[ZuordnungInvestition] = []
    speicher: list[ZuordnungInvestition] = []
    wallboxen: list[ZuordnungInvestition] = []
    eautos: list[ZuordnungInvestition] = []


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/parsers", response_model=list[ParserInfoResponse])
async def get_parsers():
    """Verfügbare Portal-Export-Parser mit Anleitungen."""
    return [p.to_dict() for p in list_parsers()]


@router.get("/manuelle-werte/{anlage_id}", response_model=ManuelleWerteInfo)
async def get_manuelle_werte(
    anlage_id: int,
    perioden: str = Query(
        ...,
        description="Kommaliste von Monaten im Format YYYY-MM, z. B. '2024-06,2024-07'",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Wie viele manuell gepflegte Werte würde ein Import mit Haken ersetzen?

    Der Wizard ruft das, bevor er „Bestehende Monate überschreiben" wirken
    lässt. Ohne diese Zahl wäre der Haken eine Überraschung statt einer
    Anordnung — genau der Vorwurf, den sich eedc vorher umgekehrt gefallen
    lassen musste („geschützt", obwohl der Anwender das Gegenteil angekreuzt
    hatte).
    """
    zerlegt: list[tuple[int, int]] = []
    for roh in perioden.split(","):
        roh = roh.strip()
        if not roh:
            continue
        try:
            jahr_s, monat_s = roh.split("-")
            jahr, monat = int(jahr_s), int(monat_s)
        except ValueError:
            raise HTTPException(400, f"Ungültiger Monat: '{roh}' (erwartet YYYY-MM)")
        if not (1 <= monat <= 12):
            raise HTTPException(400, f"Ungültiger Monat: '{roh}'")
        zerlegt.append((jahr, monat))

    bestand = await zaehle_manuelle_werte(db, anlage_id, zerlegt)
    return ManuelleWerteInfo(
        betroffen=bestand.betroffen,
        monate=bestand.monate,
        felder=bestand.felder,
        beispiele=bestand.beispiele,
    )


@router.get("/zuordnung-info/{anlage_id}", response_model=ZuordnungInfo)
async def get_zuordnung_info(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Investitions-Informationen zurück die für den Zuordnungs-Schritt benötigt werden.

    benoetigt_zuordnung=True wenn mindestens ein Investitionstyp mehrfach vorhanden ist
    (z.B. 2 PV-Module, 2 Speicher). In diesem Fall sollte der Wizard den Zuordnungs-Schritt
    anzeigen.

    Default-Anteile werden proportional nach kWp (PV) bzw. Kapazität (Speicher) berechnet.
    """
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()

    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    speicher = [i for i in investitionen if i.typ == "speicher"]
    wallboxen = [i for i in investitionen if i.typ == "wallbox"]
    eautos = [i for i in investitionen if i.typ == "e-auto"]

    benoetigt = len(pv_module) > 1 or len(speicher) > 1 or len(wallboxen) > 1 or len(eautos) > 1

    # P3/P6 (N59): Nennleistung und Kapazität kommen über die SoT-Helper.
    # Bis A20 stand hier `parameter["leistung_kwp"]` — ein Schlüssel, den KEINES
    # der drei Regime kennt (die kWp ist eine Spalte, der Legacy-JSON-Key heißt
    # `kwp`). Der falsche Schlüssel lieferte still 0, 0 sah aus wie „keine
    # Daten", und der Wizard schlug deshalb IMMER Gleichverteilung vor und ließ
    # die kWp-Spalte leer — bei 12/3 kWp also 50/50 statt 80/20. Wer den
    # Vorschlag übernahm, schrieb falsche Monatswerte in die IMD.
    def _kwp(inv: Investition) -> float:
        return get_pv_kwp(inv)

    def _kapazitaet(inv: Investition) -> float:
        return get_inv_value(inv, "kapazitaet_kwh")

    def _anteil(wert: float, alle: list[Investition], groesse) -> float:
        total = sum(groesse(i) for i in alle)
        if total > 0:
            return round(wert / total * 100, 1)
        # Gleichverteilung ist nur zulässig, wenn die Bezugsgröße WIRKLICH
        # unbekannt ist — und dann sagt der Wizard es (P4), statt stillschweigend
        # gleich zu verteilen (`anteil_geschaetzt`).
        return round(100.0 / len(alle), 1) if alle else 0.0

    pv_total = sum(_kwp(i) for i in pv_module)
    bat_total = sum(_kapazitaet(i) for i in speicher)

    return ZuordnungInfo(
        benoetigt_zuordnung=benoetigt,
        pv_module=[
            ZuordnungInvestition(
                id=i.id,
                bezeichnung=i.bezeichnung or i.typ,
                kwp=_kwp(i) or None,
                default_anteil=_anteil(_kwp(i), pv_module, _kwp),
                anteil_geschaetzt=pv_total <= 0,
            ) for i in pv_module
        ],
        speicher=[
            ZuordnungInvestition(
                id=i.id,
                bezeichnung=i.bezeichnung or i.typ,
                kwh=_kapazitaet(i) or None,
                default_anteil=_anteil(_kapazitaet(i), speicher, _kapazitaet),
                anteil_geschaetzt=bat_total <= 0,
            ) for i in speicher
        ],
        wallboxen=[
            ZuordnungInvestition(id=i.id, bezeichnung=i.bezeichnung or i.typ)
            for i in wallboxen
        ],
        eautos=[
            ZuordnungInvestition(id=i.id, bezeichnung=i.bezeichnung or i.typ)
            for i in eautos
        ],
    )


@router.post("/preview", response_model=PreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    parser_id: Optional[str] = Query(None, description="Parser-ID oder leer für Auto-Detect"),
):
    """CSV hochladen und Vorschau der erkannten Monatswerte erhalten (ohne Speichern)."""
    # Datei lesen
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content = content_bytes.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(400, "Datei konnte nicht gelesen werden. Bitte UTF-8 oder Latin-1 Encoding verwenden.")

    if not content.strip():
        raise HTTPException(400, "Die Datei ist leer.")

    # Parser wählen
    if parser_id:
        try:
            parser = get_parser(parser_id)
        except ValueError:
            raise HTTPException(400, f"Unbekannter Parser: {parser_id}")
    else:
        parser = auto_detect_parser(content, file.filename or "")
        if not parser:
            raise HTTPException(
                400,
                "Format nicht automatisch erkannt. Bitte Hersteller manuell wählen."
            )

    # Parsen
    try:
        months = parser.parse(content)
    except Exception as e:
        logger.exception("Fehler beim Parsen der Datei")
        raise HTTPException(400, f"Fehler beim Parsen: {str(e)}")

    if not months:
        raise HTTPException(400, "Keine Monatsdaten in der Datei gefunden.")

    return PreviewResponse(
        parser=ParserInfoResponse(**parser.info().to_dict()),
        monate=[ParsedMonthResponse(**m.to_dict()) for m in months],
        anzahl_monate=len(months),
    )


# ─── Import-Anwendung: Träger und Phasen ─────────────────────────────────────


@dataclass
class ImportKontext:
    """Die Eingänge eines Apply-Laufs — nach `_baue_import_kontext` nur gelesen.

    Elf Phasen brauchen dieselbe Menge (Session, Anlage, Geräte-Listen, Ziel,
    Provenance-Konstanten); als Einzelargumente wären das zehn bis vierzehn
    Schlüsselwörter je Aufruf. Wer hier etwas ändern will, ändert stattdessen
    ein Feld der `ImportBilanz` — der Kontext wird nie zurückgeschrieben.
    """

    db: AsyncSession
    anlage_id: int
    ueberschreiben: bool
    datenquelle: str
    zuordnung: Optional[InvestitionsZuordnung]
    pv_module: list[Investition]
    speicher: list[Investition]
    wallboxen: list[Investition]
    eautos: list[Investition]
    ziel: Optional[Investition] = None
    ziel_pv_module: list[Investition] = field(default_factory=list)
    ziel_speicher: list[Investition] = field(default_factory=list)
    source: str = _PROVENANCE_SOURCE
    writer: str = ""


@dataclass
class ImportBilanz:
    """Was der Lauf gezählt hat und zu sagen hat — der einzige geschriebene Zustand.

    Etappe 3d Päckchen 2: `geschuetzt_count`/`geschuetzte_felder` sind das
    Hierarchie-Schutz-Tracking (manuell gepflegte Werte, die der
    Provenance-Helper gegen Portal-/Cloud-Apply abweist).

    N-229/12.08.: `hauszaehler_uebernommen` sagt, ob der gerätegebundene Weg
    Hauszähler-Größen in die Monatszeile übernommen hat. Steuert den
    Abschlusshinweis — ohne das Flag behauptete er etwas, das im Konfliktfall
    nicht stattgefunden hat.
    """

    importiert: int = 0
    uebersprungen: int = 0
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    geschuetzt_count: int = 0
    geschuetzte_felder: list[str] = field(default_factory=list)  # Top-15 Sample
    hauszaehler_uebernommen: bool = False

    @property
    def erste_runde(self) -> bool:
        """Ist noch kein Monat übernommen? Warnungen gelten dem Lauf, nicht dem
        Monat — sonst steht derselbe Satz zwölfmal im Ergebnis."""
        return self.importiert == 0

    def _merke_feld(self, feld: str) -> None:
        """Die eine Stichproben-Regel: bis zu 15 Namen, keine Dubletten."""
        if len(self.geschuetzte_felder) < 15 and feld not in self.geschuetzte_felder:
            self.geschuetzte_felder.append(feld)

    def merke_geschuetzt(self, feld: str) -> None:
        """Ein direkt abgewiesenes Top-Level-Feld."""
        self.geschuetzt_count += 1
        self._merke_feld(feld)

    def merke_upsert(self, upsert_res) -> None:
        """Sammler für die Wizard-Hinweis-Telemetrie. Wird sowohl vom direkten
        `_upsert_und_merke`-Wrapper als auch via `on_upsert`-Callback aus den
        Helpers (`_distribute_*`) gerufen, damit indirekt geschriebene Felder
        nicht ohne Tracking durchschlüpfen."""
        self.geschuetzt_count += upsert_res.rejected_count
        for sub_key in upsert_res.rejected_fields:
            self._merke_feld(sub_key)


async def _upsert_und_merke(bilanz: ImportBilanz, *args, **kwargs):
    """Wrapper über _upsert_investition_monatsdaten der die rejected_*-
    Counts in den Apply-Response-Sammler legt. Periode steht im Audit-
    Log, daher dort nur Sub-Key-Sample für den Wizard-Hinweis."""
    upsert_res = await _upsert_investition_monatsdaten(*args, **kwargs)
    bilanz.merke_upsert(upsert_res)
    return upsert_res


async def _schreibe_top_level(
    bilanz: ImportBilanz, db: AsyncSession, obj, feld: str, wert,
    *, source: str, writer: str, ueberschreiben: bool,
):
    """Ein Top-Level-Feld über die Quellen-Hierarchie schreiben und das
    Ergebnis verbuchen.

    Die EINE Stelle für beide Schreibwege (gerätegebundener Hauszähler-Zweig
    und anlagenweite Monatszeile) — bis 20.09.2026 stand derselbe Vierzeiler
    zweimal wortgleich in `apply_import`.
    """
    res = await write_with_provenance(
        db, obj, feld, wert,
        source=source, writer=writer,
        # Der Haken IST die Anordnung des Anwenders (12.08.) —
        # vorher meldete der Import „geschützt" und tat nicht,
        # was angekreuzt war.
        benutzer_override=ueberschreiben,
    )
    if res.decision == "rejected_lower_priority":
        bilanz.merke_geschuetzt(feld)
    return res


async def _baue_import_kontext(
    db: AsyncSession, anlage_id: int, data: ApplyRequest,
    ueberschreiben: bool, datenquelle: str,
) -> ImportKontext:
    """Anlage prüfen, Investitionen laden, Ziel auflösen (N-229).

    Die Route bekommt einen fertigen Kontext oder gar keinen — beide 404/400
    entstehen hier, bevor ein Monat angefasst wird.
    """
    # Anlage prüfen
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    # Investitionen laden (für PV/Batterie-Verteilung)
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = inv_result.scalars().all()

    # ── Ziel-Erzeuger auflösen (N-229) ───────────────────────────────────────
    # Das Ziel ist der Wechselrichter bzw. das Balkonkraftwerk, an dem die
    # Quelle hängt; die Werte gehen an SEINE Kinder. Auflösung im SoT
    # `services/erzeuger_ziel.py` — der Monatsabschluss-Cloudabruf braucht
    # dieselbe, und zwei Kopien wären die klassische Drift.
    ziel: Optional[Investition] = None
    ziel_pv_module: list[Investition] = []
    ziel_speicher: list[Investition] = []
    if data.ziel_investition_id is not None:
        try:
            empfaenger = loese_ziel(
                data.ziel_investition_id, investitionen, anlage_id=anlage_id
            )
        except ZielFehler as e:
            raise HTTPException(e.status_code, str(e))
        ziel = empfaenger.ziel
        ziel_pv_module = empfaenger.pv_module
        ziel_speicher = empfaenger.speicher

    return ImportKontext(
        db=db, anlage_id=anlage_id, ueberschreiben=ueberschreiben,
        datenquelle=datenquelle, zuordnung=data.zuordnung,
        pv_module=[i for i in investitionen if i.typ == "pv-module"],
        speicher=[i for i in investitionen if i.typ == "speicher"],
        wallboxen=[i for i in investitionen if i.typ == "wallbox"],
        eautos=[i for i in investitionen if i.typ == "e-auto"],
        ziel=ziel, ziel_pv_module=ziel_pv_module, ziel_speicher=ziel_speicher,
        source=_PROVENANCE_SOURCE, writer=f"portal_apply:{datenquelle}",
    )


async def _verteile_ziel_erzeugung(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> bool:
    """PV und Speicherumsatz an die Kinder des Ziels — was diese Station misst,
    gehört ihren Geräten. `True`, wenn etwas geschrieben wurde."""
    etwas_geschrieben = False

    if (monat_input.pv_erzeugung_kwh or 0) > 0:
        w = await _distribute_legacy_pv_to_modules(
            ktx.db, monat_input.pv_erzeugung_kwh, ktx.ziel_pv_module,
            jahr, monat, ktx.ueberschreiben,
            source=ktx.source, writer=ktx.writer,
            on_upsert=bilanz.merke_upsert,
        )
        # Bei genau einem Empfänger ist nichts verteilt worden —
        # die Verteil-Warnung wäre dort schlicht unwahr.
        if len(ktx.ziel_pv_module) > 1 and bilanz.erste_runde:
            bilanz.warnungen.extend(w)
        etwas_geschrieben = True

    bat_lad = monat_input.batterie_ladung_kwh or 0
    bat_ent = monat_input.batterie_entladung_kwh or 0
    if bat_lad > 0 or bat_ent > 0:
        if ktx.ziel_speicher:
            w = await _distribute_legacy_battery_to_storages(
                ktx.db, bat_lad, bat_ent, ktx.ziel_speicher,
                jahr, monat, ktx.ueberschreiben,
                source=ktx.source, writer=ktx.writer,
                on_upsert=bilanz.merke_upsert,
            )
            if len(ktx.ziel_speicher) > 1 and bilanz.erste_runde:
                bilanz.warnungen.extend(w)
            etwas_geschrieben = True
        elif bilanz.erste_runde:
            bilanz.warnungen.append(
                f"Die Quelle liefert Speicherwerte, aber an "
                f"'{ktx.ziel.bezeichnung or ktx.ziel.typ}' hängt kein Speicher — "
                f"sie wurden nicht übernommen."
            )

    return etwas_geschrieben


async def _uebernimm_hauszaehler(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> bool:
    """Hauszähler-Größen (anlagenweit, nicht stationsbezogen) übernehmen.

    Entscheidungsregeln: `services/import_hauszaehler.py`. `True`, wenn die
    Monatszeile dadurch etwas bekommen hat.
    """
    md_ziel = (
        await ktx.db.execute(
            select(Monatsdaten).where(
                Monatsdaten.anlage_id == ktx.anlage_id,
                Monatsdaten.jahr == jahr,
                Monatsdaten.monat == monat,
            )
        )
    ).scalar_one_or_none()

    entscheid = entscheide_hauszaehler(
        neu_einspeisung_kwh=monat_input.einspeisung_kwh,
        neu_netzbezug_kwh=monat_input.netzbezug_kwh,
        bestand_einspeisung_kwh=(
            md_ziel.einspeisung_kwh if md_ziel else None
        ),
        bestand_netzbezug_kwh=md_ziel.netzbezug_kwh if md_ziel else None,
        hat_bestandszeile=md_ziel is not None,
        ueberschreiben=ktx.ueberschreiben,
        quelle_bezeichnung=f"'{ktx.ziel.bezeichnung or ktx.ziel.typ}'",
    )
    # Warnungen nur einmal je Lauf, nicht je Monat — sonst steht
    # derselbe Satz zwölfmal im Ergebnis.
    if entscheid.warnung and entscheid.warnung not in bilanz.warnungen:
        bilanz.warnungen.append(entscheid.warnung)

    if not entscheid.schreiben:
        return False

    if md_ziel is None:
        md_ziel = Monatsdaten(
            anlage_id=ktx.anlage_id, jahr=jahr, monat=monat
        )
        ktx.db.add(md_ziel)
        # flush, damit md_ziel.id für den Provenance-Audit-Log
        # existiert — dieselbe Reihenfolge wie im Weg ohne Ziel.
        await ktx.db.flush()
    for feld, wert in (
        ("einspeisung_kwh", entscheid.einspeisung_kwh),
        ("netzbezug_kwh", entscheid.netzbezug_kwh),
    ):
        if wert is None:
            continue
        await _schreibe_top_level(
            bilanz, ktx.db, md_ziel, feld, wert,
            source=ktx.source, writer=ktx.writer,
            ueberschreiben=ktx.ueberschreiben,
        )
    md_ziel.datenquelle = ktx.datenquelle
    bilanz.hauszaehler_uebernommen = True
    return True


# ── Gerätegebundener Weg (N-229) ─────────────────────────────────────────────
# **Kein Monats-Skip**: die Geräte-Zeile eines zweiten Erzeugers darf
# nicht daran scheitern, dass der erste den Monat bereits angelegt
# hat (#349 — genau das machte die zweite Solarman-Station
# unimportierbar). Über Ergänzen vs. Ersetzen entscheidet weiterhin
# `ueberschreiben`, aber je Sub-Key im Import-Writer statt für die
# ganze Monatszeile.
#
# ⚠ **Die Monatsdaten-Zeile wird hier sehr wohl geschrieben — aber
# nur ihre Hauszähler-Größen.** Bis 2026-08-12 blieb sie ganz
# unberührt, begründet mit P7 („eine von zwei Stationen ist eine
# Teilsumme"). Das gilt für Erzeugung und Speicherumsatz, **nicht**
# für Einspeisung und Netzbezug: die misst kein Wechselrichter, die
# kommen vom Smartmeter am Hausanschluss. Zwei Stationen an einem
# Anschluss melden denselben Wert — redundant, nicht partiell.
# Verboten ist das Summieren, nicht das Übernehmen. Ohne diesen
# Zweig entstand nie eine Zählerzeile und der Anwender hatte keinen
# Monatsabschluss mehr. Entscheidungsregeln:
# `services/import_hauszaehler.py`.
async def _importiere_monat_mit_ziel(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> None:
    """Ein Monat für den gerätegebundenen Weg — erst die Geräte, dann das Haus."""
    erzeugung = await _verteile_ziel_erzeugung(ktx, bilanz, monat_input, jahr, monat)
    hauszaehler = await _uebernimm_hauszaehler(ktx, bilanz, monat_input, jahr, monat)
    if erzeugung or hauszaehler:
        bilanz.importiert += 1
    else:
        bilanz.uebersprungen += 1


async def _hole_oder_lege_monatszeile_an(
    ktx: ImportKontext, bilanz: ImportBilanz, jahr: int, monat: int,
) -> Optional[Monatsdaten]:
    """Die Monatszeile des anlagenweiten Weges — `None`, wenn der Monat
    übersprungen wird (Bestand ohne „überschreiben").

    ⛔ Die frische Zeile wird hier schon der Session übergeben (`db.add`), also
    **vor** der PV-/Batterie-Verteilung: die Verteil-Helper flushen, und
    `_schreibe_monatszeile` prüft danach `md.id is None`.
    """
    # Bestehende Monatsdaten prüfen
    existing = await ktx.db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == ktx.anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        )
    )
    existing_md = existing.scalar_one_or_none()

    if existing_md and not ktx.ueberschreiben:
        bilanz.uebersprungen += 1
        return None

    # Monatsdaten erstellen oder aktualisieren
    if existing_md:
        return existing_md
    md = Monatsdaten(anlage_id=ktx.anlage_id, jahr=jahr, monat=monat)
    ktx.db.add(md)
    return md


async def _verteile_pv_nach_zuordnung(
    ktx: ImportKontext, bilanz: ImportBilanz, pv_kwh: float, jahr: int, monat: int,
) -> None:
    """Manuelle Zuordnung: % pro Modul."""
    for inv in ktx.pv_module:
        anteil = ktx.zuordnung.pv.get(inv.id, 0) / 100.0
        pv_anteil = round(pv_kwh * anteil, 1)
        if pv_anteil > 0:
            await _upsert_und_merke(
                bilanz, ktx.db, inv.id, jahr, monat,
                {"pv_erzeugung_kwh": pv_anteil}, ktx.ueberschreiben,
                source=ktx.source, writer=ktx.writer,
            )


async def _verteile_pv(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> Optional[float]:
    """PV-Erzeugung auf die Module verteilen; zurück kommt der Anlagenwert für
    die Monatszeile."""
    if monat_input.pv_erzeugung_kwh is None or monat_input.pv_erzeugung_kwh <= 0:
        return None
    if not ktx.pv_module:
        return monat_input.pv_erzeugung_kwh
    pv_kwh = monat_input.pv_erzeugung_kwh
    if ktx.zuordnung and ktx.zuordnung.pv:
        await _verteile_pv_nach_zuordnung(ktx, bilanz, pv_kwh, jahr, monat)
    else:
        # Proportional nach kWp (Default)
        w = await _distribute_legacy_pv_to_modules(
            ktx.db, pv_kwh, ktx.pv_module, jahr, monat, ktx.ueberschreiben,
            source=ktx.source, writer=ktx.writer,
            on_upsert=bilanz.merke_upsert,
        )
        if bilanz.erste_runde:
            bilanz.warnungen.extend(w)
    return monat_input.pv_erzeugung_kwh


async def _verteile_batterie_nach_zuordnung(
    ktx: ImportKontext, bilanz: ImportBilanz,
    bat_ladung_raw: Optional[float], bat_entladung_raw: Optional[float],
    jahr: int, monat: int,
) -> None:
    """Manuelle Zuordnung: % pro Speicher."""
    for inv in ktx.speicher:
        anteil = ktx.zuordnung.batterie.get(inv.id, 0) / 100.0
        vd = {}
        if bat_ladung_raw and bat_ladung_raw > 0:
            vd["ladung_kwh"] = round(bat_ladung_raw * anteil, 1)
        if bat_entladung_raw and bat_entladung_raw > 0:
            vd["entladung_kwh"] = round(bat_entladung_raw * anteil, 1)
        if vd:
            await _upsert_und_merke(
                bilanz, ktx.db, inv.id, jahr, monat, vd, ktx.ueberschreiben,
                source=ktx.source, writer=ktx.writer,
            )


async def _verteile_batterie(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> tuple[Optional[float], Optional[float]]:
    """Ladung/Entladung auf die Speicher verteilen; zurück kommen die
    Anlagenwerte für die Monatszeile."""
    bat_ladung_raw = monat_input.batterie_ladung_kwh
    bat_entladung_raw = monat_input.batterie_entladung_kwh
    if not ((bat_ladung_raw or 0) > 0 or (bat_entladung_raw or 0) > 0):
        return None, None
    if not ktx.speicher:
        return bat_ladung_raw, bat_entladung_raw
    if ktx.zuordnung and ktx.zuordnung.batterie:
        await _verteile_batterie_nach_zuordnung(
            ktx, bilanz, bat_ladung_raw, bat_entladung_raw, jahr, monat
        )
    else:
        # Proportional nach Kapazität (Default)
        w = await _distribute_legacy_battery_to_storages(
            ktx.db, bat_ladung_raw or 0, bat_entladung_raw or 0,
            ktx.speicher, jahr, monat, ktx.ueberschreiben,
            source=ktx.source, writer=ktx.writer,
            on_upsert=bilanz.merke_upsert,
        )
        if bilanz.erste_runde:
            bilanz.warnungen.extend(w)
    return bat_ladung_raw, bat_entladung_raw


async def _schreibe_monatszeile(
    ktx: ImportKontext, bilanz: ImportBilanz, md: Monatsdaten,
    monat_input: ApplyMonthInput, pv_erzeugung: Optional[float],
    bat_ladung: Optional[float], bat_entladung: Optional[float],
) -> None:
    """Die Top-Level-Felder der Monatszeile schreiben.

    Sie gehen über write_with_provenance, damit manuell
    gepflegte Form-Werte (manual:form, MANUAL) gegen den
    external:portal_import-Schreiber (EXTERNAL_AUTHORITATIVE) geschützt
    sind. Frische Rows (existing_md None) sind initial_write → applied.
    """
    if md.id is None:
        # Frisch via db.add(md) — flush damit md.id existiert + Provenance
        # später flag_modified greifen kann.
        await ktx.db.flush()

    top_level_writes: list[tuple[str, Optional[float]]] = [
        ("einspeisung_kwh", monat_input.einspeisung_kwh),
        ("netzbezug_kwh", monat_input.netzbezug_kwh),
        ("eigenverbrauch_kwh", monat_input.eigenverbrauch_kwh),
        ("pv_erzeugung_kwh", pv_erzeugung),
        ("batterie_ladung_kwh", bat_ladung),
        ("batterie_entladung_kwh", bat_entladung),
    ]
    for field_name, value in top_level_writes:
        if value is not None:
            await _schreibe_top_level(
                bilanz, ktx.db, md, field_name, value,
                source=ktx.source, writer=ktx.writer,
                ueberschreiben=ktx.ueberschreiben,
            )
    # datenquelle ist Pre-Provenance-Spalte — bleibt direkt gesetzt
    # (sie ist nicht Teil der Hierarchie-Logik und nutzt source_provenance nicht).
    md.datenquelle = ktx.datenquelle


def _wallbox_verbrauch(monat_input: ApplyMonthInput) -> dict:
    """Die Ladewerte einer Wallbox-Zeile aus der Einfuhr."""
    verbrauch = {"ladung_kwh": monat_input.wallbox_ladung_kwh}
    if monat_input.wallbox_ladung_pv_kwh is not None:
        verbrauch["ladung_pv_kwh"] = monat_input.wallbox_ladung_pv_kwh
        # #262: Pool-Max-Aggregationen (Cockpit, Wallbox-/E-Auto-
        # Dashboard) lesen `ladung_netz_kwh` direkt. evcc-CSV liefert
        # nur Gesamt + Solar-% → Netz wird hier explizit aus
        # `Total − PV` abgeleitet, damit PV-Anteil + Netz-Lade-Kosten
        # in allen Sichten konsistent sind. Read-Site-Helper deckt
        # Legacy-Daten ohne diesen Key zusätzlich ab.
        verbrauch["ladung_netz_kwh"] = max(
            0.0,
            monat_input.wallbox_ladung_kwh - monat_input.wallbox_ladung_pv_kwh,
        )
    if monat_input.wallbox_ladevorgaenge is not None:
        verbrauch["ladevorgaenge"] = monat_input.wallbox_ladevorgaenge
    return verbrauch


async def _schreibe_wallbox(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> None:
    """Die Ladedaten in die Wallbox-Investition schreiben."""
    if monat_input.wallbox_ladung_kwh is None or monat_input.wallbox_ladung_kwh <= 0:
        return
    if not ktx.wallboxen:
        if bilanz.erste_runde:
            bilanz.warnungen.append(
                "Wallbox-Ladedaten gefunden, aber keine Wallbox als Investition angelegt. "
                "Bitte zuerst eine Wallbox unter Investitionen anlegen."
            )
        return
    zuordnung = ktx.zuordnung
    # Manuelle Zuordnung oder erste Wallbox
    wb = next(
        (w for w in ktx.wallboxen if zuordnung and w.id == zuordnung.wallbox_id),
        ktx.wallboxen[0]
    )
    await _upsert_und_merke(
        bilanz, ktx.db, wb.id, jahr, monat, _wallbox_verbrauch(monat_input),
        ktx.ueberschreiben,
        source=ktx.source, writer=ktx.writer,
    )
    if len(ktx.wallboxen) > 1 and not (zuordnung and zuordnung.wallbox_id) and bilanz.erste_runde:
        bilanz.warnungen.append(
            f"Mehrere Wallboxen vorhanden – Ladedaten wurden der ersten "
            f"Wallbox '{wb.bezeichnung or wb.typ}' zugeordnet."
        )


async def _schreibe_eauto(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> None:
    """Die gefahrenen Kilometer in die E-Auto-Investition schreiben."""
    if monat_input.eauto_km_gefahren is None or monat_input.eauto_km_gefahren <= 0:
        return
    if not ktx.eautos:
        return
    zuordnung = ktx.zuordnung
    ea = next(
        (e for e in ktx.eautos if zuordnung and e.id == zuordnung.eauto_id),
        ktx.eautos[0]
    )
    await _upsert_und_merke(
        bilanz, ktx.db, ea.id, jahr, monat,
        {"km_gefahren": monat_input.eauto_km_gefahren},
        ktx.ueberschreiben,
        source=ktx.source, writer=ktx.writer,
    )


async def _importiere_monat_anlagenweit(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
    jahr: int, monat: int,
) -> None:
    """Anlagenweiter Weg: eine Monatszeile, verteilt auf die Geräte."""
    md = await _hole_oder_lege_monatszeile_an(ktx, bilanz, jahr, monat)
    if md is None:
        return

    pv_erzeugung = await _verteile_pv(ktx, bilanz, monat_input, jahr, monat)
    bat_ladung, bat_entladung = await _verteile_batterie(
        ktx, bilanz, monat_input, jahr, monat
    )
    await _schreibe_monatszeile(
        ktx, bilanz, md, monat_input, pv_erzeugung, bat_ladung, bat_entladung
    )
    await _schreibe_wallbox(ktx, bilanz, monat_input, jahr, monat)
    await _schreibe_eauto(ktx, bilanz, monat_input, jahr, monat)

    bilanz.importiert += 1


async def _importiere_monat(
    ktx: ImportKontext, bilanz: ImportBilanz, monat_input: ApplyMonthInput,
) -> None:
    """Ein Monat der Einfuhr — gerätegebunden oder anlagenweit."""
    jahr = monat_input.jahr
    monat = monat_input.monat

    if monat < 1 or monat > 12:
        bilanz.fehler.append(f"{jahr}/{monat:02d}: Ungültiger Monat")
        return

    if ktx.ziel is not None:
        await _importiere_monat_mit_ziel(ktx, bilanz, monat_input, jahr, monat)
        return

    await _importiere_monat_anlagenweit(ktx, bilanz, monat_input, jahr, monat)


def _abschluss_hinweise(ktx: ImportKontext, bilanz: ImportBilanz) -> None:
    """Was der Anwender am Ende erfährt. ⛔ Die Reihenfolge der beiden
    `insert(0, …)` ist das Ergebnis: erst Hauszähler, dann Geschützt — der
    Schutz-Hinweis steht dadurch am Ende ganz vorn."""
    # N-229: Sagen, was mit den Größen des Hauses geschehen ist. Sie gelten nur
    # einmal je Netzanschluss — deshalb werden sie übernommen, aber nie
    # summiert. (Bis 12.08. sagte dieser Hinweis, sie würden NICHT übernommen;
    # das war die Folge der falschen P7-Begründung, s. `_importiere_monat_mit_ziel`.)
    if ktx.ziel is not None and bilanz.hauszaehler_uebernommen:
        bilanz.warnungen.insert(0, (
            f"Erzeugung und Speicherwerte wurden '{ktx.ziel.bezeichnung or ktx.ziel.typ}' "
            "zugeordnet. Einspeisung und Netzbezug gelten für den ganzen "
            "Hausanschluss und wurden einmal in den Monat übernommen — eine "
            "zweite Quelle am selben Anschluss addiert sie nicht dazu."
        ))

    # Etappe 3d Päckchen 2: Wizard-Hinweis bei aktivierter Quellen-Hierarchie.
    if bilanz.geschuetzt_count > 0:
        sample = ", ".join(bilanz.geschuetzte_felder[:5])
        suffix = f" (z. B. {sample})" if sample else ""
        bilanz.warnungen.insert(0, (
            f"{bilanz.geschuetzt_count} Felder wurden durch manuell gepflegte Werte "
            f"geschützt — der Import hat sie nicht überschrieben{suffix}. "
            "Reset über Reparatur-Werkbank wenn gewollt."
        ))


@router.post("/apply/{anlage_id}", response_model=ApplyResponse)
async def apply_import(
    anlage_id: int,
    data: ApplyRequest,
    ueberschreiben: bool = Query(False, description="Bestehende Monatsdaten überschreiben"),
    datenquelle: str = Query("portal_import", description="Datenquelle (portal_import, cloud_import)"),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Bestätigte Monatswerte aus Portal-Import oder Cloud-Import in die Datenbank übernehmen."""
    ktx = await _baue_import_kontext(db, anlage_id, data, ueberschreiben, datenquelle)
    bilanz = ImportBilanz()

    for monat_input in data.monate:
        try:
            await _importiere_monat(ktx, bilanz, monat_input)
        except Exception as e:
            logger.exception(f"Fehler bei Monat {monat_input.jahr}/{monat_input.monat}")
            bilanz.fehler.append(f"{monat_input.jahr}/{monat_input.monat:02d}: {str(e)}")

    await db.flush()

    _abschluss_hinweise(ktx, bilanz)

    await log_activity(
        kategorie="portal_import",
        aktion=f"Portal-Import: {bilanz.importiert} Monate importiert",
        erfolg=len(bilanz.fehler) == 0,
        details=f"Quelle: {datenquelle}, übersprungen: {bilanz.uebersprungen}, geschützt: {bilanz.geschuetzt_count}",
        details_json={
            "importiert": bilanz.importiert, "uebersprungen": bilanz.uebersprungen,
            "geschuetzt": bilanz.geschuetzt_count, "fehler": bilanz.fehler[:5],
        },
        anlage_id=anlage_id,
        db=db,
    )

    return ApplyResponse(
        erfolg=len(bilanz.fehler) == 0,
        importiert=bilanz.importiert,
        uebersprungen=bilanz.uebersprungen,
        fehler=bilanz.fehler[:20],
        warnungen=bilanz.warnungen[:10],
        geschuetzt_count=bilanz.geschuetzt_count,
        geschuetzte_felder=bilanz.geschuetzte_felder,
    )
