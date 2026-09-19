"""
Monatsabschluss API — Read- und Vorschau-Endpoints.

GET  /{anlage_id}/{jahr}/{monat}                — Status aller Felder, Vorschläge, Warnungen
GET  /naechster/{anlage_id}                     — Nächster unvollständiger Monat
GET  /historie/{anlage_id}                      — Historie der letzten N Monatsabschlüsse

Schreib-Pfad (POST {anlage_id}/{jahr}/{monat}) liegt in wizard.py.
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.exceptions import not_found
from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.core.database import get_db
from backend.core.field_definitions import (
    OPTIONALE_FELDER,
    ZAEHLERSTAND_FELD,
    basis_feld_key,
    einheit_fuer,
    get_basis_felder,
    get_felder_fuer_investition,
    ist_stand_feld,
    ist_zaehler_differenz_feld,
)
from backend.models.anlage import Anlage
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.cloud_import.quellen import lade_quellen
from backend.services.ha_state_service import get_ha_state_service
from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
from backend.services.provenance import (
    ABGELEITET_KAPAZITAET_ANTEIL,
    ABGELEITET_KWP_ANTEIL,
)
from backend.services.vorschlag_service import Vorschlag, VorschlagQuelle, VorschlagService
from backend.services.zaehlerstaende import lade_zaehlerstaende

from ._shared import (
    MONAT_NAMEN,
    _vorschlag_to_response,
    _warnung_to_response,
    logger,
)

if TYPE_CHECKING:  # pragma: no cover — nur für die Signatur, kein Laufzeit-Import
    # ⛔ Bewusst NICHT auf Modulebene: `berechne_monats_durchschnittspreis` wird
    # funktionslokal importiert, und daran hängt die Patchbarkeit in den Proben
    # (dieselbe Regel wie beim HA-Statistik-Dienst, N-156).
    from backend.services.strompreis_aggregator import StrompreisAggregat

router = APIRouter()


# =============================================================================
# Konfidenz der Connector-Vorschläge
# =============================================================================
# Ein Connector liefert EINEN Zählerstand pro Kategorie (PV gesamt, Batterie
# gesamt). Gibt es mehrere Module/Speicher, wird dieser Gesamtwert anteilig
# nach Nennleistung bzw. Kapazität zerlegt (`_distribute_by_param`) — der
# Vorschlag je Gerät ist dann KEINE Messung dieses Geräts, sondern ein Modell.
# Es ist dieselbe Einschränkung, die der Daten-Checker als „Pro-String-
# Genauigkeit eingeschränkt" meldet (services/daten_checker/energieprofil.py).
#
# Eine projektweite Konfidenz-Skala gibt es nicht; die Nachbarwerte sind:
#   95 WP-Gesamtstrom = Σ(Heizen+WW) · 92 HA-Statistik · 91 MQTT-Inbound ·
#   90 Connector-Zählerstand · 90/55 Speicher-Ladepreis · 85 Kraftstoffpreis ·
#   80 Vormonat · 70 Vorjahr / HA-Momentanwert · 60 WP-Wärme = Strom×COP ·
#   50 Ø 12 Monate · 30 Jahresfahrleistung÷12
# (services/vorschlag_service.py, strompreis_aggregator.py, views.py).
#
# Der verteilte Wert liegt deshalb unter JEDER gemessenen Quelle (90/91/92),
# aber über „Wert vom Vormonat" (80): Summe und Monat sind gemessen, nur der
# Verteilungsschlüssel ist gerechnet.
KONFIDENZ_CONNECTOR_GEMESSEN = 90
KONFIDENZ_CONNECTOR_VERTEILT = 85

# Welche Ableitungs-Marke ein zerlegter Vorschlag trägt — die Zerlegung folgt
# dem Kennwert des Geräts (#352): PV nach kWp, Speicher nach Kapazität, wie
# `_mapped_or_distribute` es rechnet.
_ABGELEITET_JE_FELD = {
    "pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL,
    "ladung_kwh": ABGELEITET_KAPAZITAET_ANTEIL,
    "entladung_kwh": ABGELEITET_KAPAZITAET_ANTEIL,
}


def _abgeleitet_marke(feld: str) -> Optional[str]:
    """Marke für ein zerlegtes Feld; ``None`` für Felder ohne Zerlegung."""
    return _ABGELEITET_JE_FELD.get(feld)


# =============================================================================
# Pydantic-Models — view-spezifisch
# =============================================================================

class FeldStatus(BaseModel):
    """Status eines einzelnen Feldes."""
    feld: str
    label: str
    einheit: str
    aktueller_wert: Optional[float] = None
    aktueller_text: Optional[str] = None  # Für Textfelder wie Beschreibung, Notizen
    quelle: Optional[str] = None  # ha_sensor, snapshot, manuell, berechnet
    vorschlaege: list = []
    warnungen: list = []
    strategie: Optional[str] = None  # Aus sensor_mapping
    sensor_id: Optional[str] = None  # Wenn strategie=sensor
    typ: str = "number"  # number oder text
    gruppe: Optional[str] = None  # zaehler, wetter, preise (für Frontend-Gruppierung)
    # PN 90128: die vom Nutzer bewusst behaltene Situation dieses Feldes —
    # {"sensor": <Vorschlagswert damals>, "wert": <behaltener Wert>} oder None.
    # Der Client zeigt „weicht ab" nicht mehr als offenen Punkt, solange beide
    # Werte noch stimmen; die Abweichung bleibt sichtbar (kein Wegklicken).
    geprueft_gegen: Optional[dict] = None
    # #407: bei einem STAND-Feld (`ist_stand_feld`) der gespeicherte Stand des
    # Vormonats — sein Anfang. Der Client rechnet daraus die Differenz, während
    # der Anwender tippt (Tachostand → gefahrene km), statt auf das nächste
    # Laden zu warten. Bei Mengen-Feldern immer None.
    stand_vormonat: Optional[float] = None


class InvestitionStatus(BaseModel):
    """Status einer Investition im Monatsabschluss."""
    id: int
    typ: str
    bezeichnung: str
    felder: list[FeldStatus]
    kategorie: Optional[str] = None          # Für Typ "sonstiges": erzeuger/verbraucher/speicher
    sonstige_positionen: list[dict] = []     # Strukturierte Erträge & Ausgaben


class MonatsabschlussResponse(BaseModel):
    """Vollständiger Status für einen Monat."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    ist_abgeschlossen: bool
    ha_mapping_konfiguriert: bool
    connector_konfiguriert: bool = False
    cloud_import_konfiguriert: bool = False
    mqtt_inbound_konfiguriert: bool = False
    portal_import_vorhanden: bool = False
    datenquelle: Optional[str] = None  # "portal_import", "cloud_import", "mqtt_inbound", "manual", etc.

    # Basis-Felder (Zählerdaten)
    basis_felder: list[FeldStatus]

    # Optionale Felder (Sonderkosten, Notizen - nicht aus HA)
    optionale_felder: list[FeldStatus] = []

    # Investition-Felder
    investitionen: list[InvestitionStatus]


class NaechsterMonatResponse(BaseModel):
    """Nächster unvollständiger Monat."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    ha_mapping_konfiguriert: bool


# =============================================================================
# Eingänge — einmal beschafft, danach nur gelesen
# =============================================================================

@dataclass
class ConnectorMonatswerte:
    """Monatsdelta des lokalen Connectors und seine Zerlegung auf die Geräte."""

    #: Ob überhaupt ein Connector eingerichtet ist. Dieses Feld trägt zugleich
    #: das Antwortfeld `connector_konfiguriert` — der Ausdruck
    #: `bool(cfg and cfg.get("connector_id"))` steht damit genau EINMAL im Baum.
    konfiguriert: bool = False
    #: Anlagenweite Monatsdifferenz je Basis-Feld, oder ``None``.
    delta: Optional[dict] = None
    #: ``{inv_id: {feld: wert}}`` — der auf die Geräte zerlegte Gesamtwert.
    inv_verteilung: dict[int, dict[str, float]] = field(default_factory=dict)
    # Felder, deren Vorschlagswert ein ZERLEGTER Anlagen-Gesamtwert ist (mehr als
    # ein Empfänger): {inv_id: {feld: Beschreibung}}. Steuert Beschriftung und
    # Konfidenz — bei genau einem Modul/Speicher geht der Zählerstand
    # unverändert dorthin, das ist eine Messung und bleibt als solche etikettiert.
    verteilt_hinweis: dict[int, dict[str, str]] = field(default_factory=dict)


@dataclass
class MonatsabschlussKontext:
    """Die Eingänge des Monatsabschluss-Status — gebaut, dann nur noch gelesen.

    Zehn dieser Werte brauchen **beide** Aufbereiter (Basis-Felder und
    Investitions-Felder). Als Keyword-Parameter wären das Signaturen mit zehn
    bis dreizehn Argumenten; als Träger-Objekt steht jede Herkunft an genau
    einer Stelle. Nach `baue_kontext` schreibt niemand mehr hinein.
    """

    db: AsyncSession
    anlage: Anlage
    anlage_id: int
    jahr: int
    monat: int
    vorschlag_service: VorschlagService
    sensor_mapping: dict
    basis_mapping: dict
    inv_mappings: dict
    monatsdaten: Optional[Monatsdaten]
    datenquelle: Optional[str]
    basis_geprueft: dict
    ha_stats_werte: dict[str, float]
    connector: ConnectorMonatswerte
    cloud_import_konfiguriert: bool
    mqtt_energy: dict[str, float]
    mqtt_inv_energy: dict[int, dict[str, float]]
    alle_basis_felder: list
    # N-535: das Ergebnis der Freischaltfrage aus `lade_basis_feldliste` — genau
    # die Zahl, die der Vorschlag für `netzbezug_durchschnittspreis_cent`
    # braucht. Sie reist mit, statt ein zweites Mal gerechnet zu werden.
    preis_messung: Optional["StrompreisAggregat"]
    zaehler_ende: dict[int, float]


async def lade_anlage_mit_investitionen(db: AsyncSession, anlage_id: int) -> Anlage:
    """Die Anlage samt Investitionen — oder 404."""
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")
    return anlage


async def lade_monatsdaten(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> Optional[Monatsdaten]:
    """Die bereits gespeicherte Monatszeile, falls es sie gibt."""
    md_result = await db.execute(
        select(Monatsdaten)
        .where(and_(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        ))
    )
    return md_result.scalar_one_or_none()


async def lade_basis_feldliste(
    db: AsyncSession, anlage: Anlage, anlage_id: int, jahr: int, monat: int
) -> tuple[list, Optional["StrompreisAggregat"]]:
    """Die Basis-Felder dieses Monats — bedingte Felder mit dem Stichtag aufgelöst.

    Returns:
        ``(feldliste, preis_messung)``. Die Messung ist das Ergebnis der
        Freischaltfrage und wird **mitgegeben, nicht ein zweites Mal
        gerechnet** (N-535): derselbe Aufruf beantwortet „erscheint das Feld
        ‚Ø Strompreis'?" und „welchen Wert schlagen wir vor?". Bis zum
        19.09.2026 rief der Vorschlagszweig den Aggregator selbst — mit
        identischen Argumenten, ohne Cache, also eine überflüssige
        `TagesEnergieProfil`-Abfrage über den ganzen Monat je Formularaufruf.
    """
    # Bedingungen für bedingte Basis-Felder ermitteln. Stichtag ist der Monat,
    # der abgeschlossen wird — sonst entscheidet die HEUTIGE Vertragsart, ob das
    # Feld „Ø Strompreis" erscheint: nach einem Wechsel dynamisch → fest käme man
    # an den abgerechneten Ø eines Altmonats nicht mehr heran.
    tarife = await lade_tarife_fuer_anlage(db, anlage_id, target_date=date(jahr, monat, 1))
    allgemein_tarif = tarife.get("allgemein")
    # N-267: Ein Zeittarif (HT/NT) schaltet dasselbe Feld frei — er ist der
    # zweite Fall derselben Frage („welcher EINE Preis beschreibt den Monat?").
    # Ohne Stundenwerte rechnet eedc sonst mit dem Hochtarif, und genau dann
    # braucht der Anwender den Weg, seinen abgerechneten Ø einzutragen.
    # ⛔ KEIN eigenes Feld und KEIN geschaetzter NT-Anteil: ein Feld, das zum
    # Falschausfuellen einlaedt, ist schlechter als kein Feld (#392-Lehre).
    # ⭐ **Und STUNDENPREISE IN DIESEM MONAT schalten es ebenfalls frei**
    # (#412, OB73-gif). Wo eedc den Bezugspreis aus mitgeschriebenen
    # Stundenpreisen bildet, muss der Anwender seinen **abgerechneten** Ø
    # danebenstellen können — sonst rechnet eedc mit einer Messung, die der
    # Anwender nicht durch die Abrechnung ersetzen kann.
    #
    # ⛔ **Hier stand am 11.09.2026 zwischenzeitlich „ein zugeordneter
    # Strompreis-Sensor genügt". Das war falsch und ist zurückgenommen.** Der
    # Zuordnungs-Slot für diesen Sensor ist selbst nur bei `vertragsart ==
    # "dynamisch"` sichtbar (`datenquellen.py`, begründet mit Forum #89667/54).
    # Der Zustand „Sensor zugeordnet, Vertragsart nicht dynamisch" entsteht
    # deshalb im Wesentlichen auf **einem** Weg: einem Tarifwechsel
    # dynamisch → fest, bei dem das Mapping stehen bleibt. Und genau dort
    # richtete die Sensor-Bedingung Schaden an: Sie ist **stichtagslos**,
    # während diese Route stichtagsgenau arbeitet (P8) — das Feld wäre danach
    # in **jedem** Monat erschienen, auch in reinen Festpreis-Monaten, wo es
    # keinen Ø einzutragen gibt. Wörtlich die #392-Lehre vier Zeilen darüber.
    #
    # ⭐ **Positive Evidenz statt einer Negativ-Prüfung auf ein optionales
    # Dropdown** — dieselbe Bauform und dieselbe Begründung wie in
    # `speicher_wirtschaftlichkeit.berechne_effektiver_ladepreis`: „das Feld
    # ist ein optionales Dropdown, leer ist der Normalfall." Stundenpreise
    # **dieses** Monats kann es nicht fälschlich geben.
    #
    # ⚠ Gefragt wird der SoT-Aggregator, nicht eine eigene Query: Er entscheidet
    # auch in der Preis-Kaskade, ob eine Messung vorliegt. Zwei Antworten auf
    # dieselbe Frage wären die F-56-Klasse.
    from backend.core.berechnungen.zeittarif import hat_zeitfenster
    from backend.services.strompreis_aggregator import (
        berechne_monats_durchschnittspreis,
    )
    _messung = await berechne_monats_durchschnittspreis(anlage_id, jahr, monat, db)
    hat_gemessene_preise = bool(_messung and _messung.gewichtet_cent is not None)
    hat_dynamischen_tarif = bool(
        hat_gemessene_preise
        or (
            allgemein_tarif
            and (allgemein_tarif.vertragsart == "dynamisch" or hat_zeitfenster(allgemein_tarif))
        )
    )
    # #392: dieselbe Stichtags-Logik für die variable Einspeisevergütung —
    # entscheidend ist der Tarif des abzuschließenden Monats, nicht der heutige.
    hat_variable_einspeisung = bool(
        allgemein_tarif and getattr(allgemein_tarif, "einspeisung_variabel", False)
    )
    aktive_inv_typen = {i.typ for i in anlage.investitionen if not i.stilllegungsdatum}

    # Alle Basis-Felder aus Registry (inkl. aufgelöster bedingter Felder)
    return get_basis_felder(
        hat_dynamischen_tarif=hat_dynamischen_tarif,
        aktive_inv_typen=aktive_inv_typen,
        hat_variable_einspeisung=hat_variable_einspeisung,
    ), _messung


async def lade_zaehler_ende(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> dict[int, float]:
    """Zählerstände zum Monatsende (#377). **Ein eigener Weg, und zwar mit
    Absicht:** Jeder andere Vorschlag ist eine MENGE — eine Zählerdifferenz, ein
    Monatsverbrauch. Der Zählerstand ist ein STAND, und
    `ist_zaehler_differenz_feld` liefert für ihn bewusst `False`: würde er
    denselben Pfad nehmen, käme `MAX − MIN` heraus, also der **Verbrauch des
    Monats** — genau die Zahl, die der Anwender hier NICHT eintragen soll.
    Vorgeschlagen wird deshalb der letzte mitgeschriebene Stand des Monats.
    """
    zaehler_ende: dict[int, float] = {}
    try:
        _letzter_tag = monthrange(jahr, monat)[1]
        for _zf in await lade_zaehlerstaende(
            db, anlage_id,
            datetime(jahr, monat, 1),
            datetime(jahr, monat, _letzter_tag, 23, 59, 59),
            mit_verlauf=False, nur_aktive=False,
        ):
            if _zf.stand_ende is not None:
                zaehler_ende[_zf.investition_id] = _zf.stand_ende
    except Exception:  # pragma: no cover - Vorschläge dürfen nie die Seite kippen
        logger.exception("Zählerstände für den Monatsabschluss nicht ladbar")
    return zaehler_ende


def _verteile_gesamtwert(
    anlage: Anlage,
    field_inv_map: dict,
    kategorie: str,
    inv_typ: str,
    kennwert: str,
    feld: str,
    wert: Optional[float],
    hinweis: str,
    ziel: ConnectorMonatswerte,
) -> None:
    """Zerlegt EINEN Anlagen-Gesamtwert auf die Geräte eines Typs.

    ⛔ Zerlegt wird über `_mapped_or_distribute` — die Zuordnungs-SoT
    (ADR-002/P3), dieselbe wie in der Connector-Vorschau. Nie über
    `_distribute_by_param` direkt.
    """
    from backend.api.routes.connector import _mapped_or_distribute
    if wert is None or wert <= 0:
        return
    geraete = [i for i in anlage.investitionen if i.typ == inv_typ]
    if not geraete:
        return
    verteilung = _mapped_or_distribute(
        field_inv_map, kategorie, geraete, wert, kennwert
    )
    # Genau ein Empfänger = der Zählerstand geht unverzerrt
    # dorthin (ein Modul, oder eine explizite Zuordnung).
    ist_verteilt = len(verteilung) > 1
    for inv, anteil in verteilung:
        ziel.inv_verteilung.setdefault(inv.id, {})[feld] = anteil
        if ist_verteilt:
            ziel.verteilt_hinweis.setdefault(inv.id, {})[feld] = hinweis


def lade_connector_monatswerte(
    anlage: Anlage, jahr: int, monat: int
) -> ConnectorMonatswerte:
    """Connector-Status und Monatswerte berechnen.

    Drei Tore hintereinander statt ineinander: kein Connector, keine
    Zählerstände, kein Monatsdelta — jedes davon endet in einem leeren
    Ergebnis, und der Aufrufer muss keines der drei kennen.
    """
    werte = ConnectorMonatswerte()
    connector_config = anlage.connector_config
    werte.konfiguriert = bool(connector_config and connector_config.get("connector_id"))
    if not werte.konfiguriert:
        return werte

    from backend.api.routes.connector import _calc_month_delta
    snapshots = connector_config.get("meter_snapshots", {})
    if not snapshots:
        return werte

    _delta = _calc_month_delta(snapshots, jahr, monat)
    werte.delta = _delta.werte if _delta else None
    if not werte.delta:
        return werte

    # Explizite Kategorie→Investition-Zuordnung — dieselbe SoT wie die
    # Connector-Vorschau (`api/routes/connector.py:484`) und die
    # MQTT-Energie-Bridge. Wer sein Wechselrichter-Feld einem Modul
    # zugeordnet hat, bekommt dessen Wert und keine kWp-Zerlegung.
    field_inv_map = connector_config.get("field_inv_map") or {}

    # PV auf Module verteilen
    _verteile_gesamtwert(
        anlage, field_inv_map, "pv", "pv-module", "leistung_kwp",
        "pv_erzeugung_kwh", werte.delta.get("pv_erzeugung_kwh"),
        "anteilig nach kWp auf die Strings verteilt — "
        "Pro-String-Genauigkeit eingeschränkt",
        werte,
    )
    # Batterie auf Speicher verteilen
    for bat_feld, inv_feld in [
        ("batterie_ladung_kwh", "ladung_kwh"),
        ("batterie_entladung_kwh", "entladung_kwh"),
    ]:
        _verteile_gesamtwert(
            anlage, field_inv_map, "speicher", "speicher", "kapazitaet_kwh",
            inv_feld, werte.delta.get(bat_feld),
            "anteilig nach Kapazität auf die Speicher verteilt — "
            "Pro-Speicher-Genauigkeit eingeschränkt",
            werte,
        )
    return werte


def _mqtt_inv_feld(mqtt_key: str) -> Optional[tuple[int, str]]:
    """`inv/3/ladung_kwh` → `(3, "ladung_kwh")`; alles andere → ``None``."""
    parts = mqtt_key.split("/", 2)  # ["inv", "3", "ladung_kwh"]
    if len(parts) != 3:
        return None
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        return None


async def lade_mqtt_monatsmengen(
    db: AsyncSession, anlage: Anlage, jahr: int, monat: int
) -> tuple[dict[str, float], dict[int, dict[str, float]]]:
    """MQTT Inbound Energy-Daten sammeln — als Monatsmenge, nicht als Stand.

    Returns:
        ``(mqtt_energy, mqtt_inv_energy)`` — Basis-Felder und
        ``{inv_id: {feld: wert}}``; leer, wenn kein Inbound läuft.
    """
    mqtt_energy: dict[str, float] = {}
    mqtt_inv_energy: dict[int, dict[str, float]] = {}  # inv_id → {feld: wert}
    mqtt_svc = get_mqtt_inbound_service()
    if not mqtt_svc:
        return mqtt_energy, mqtt_inv_energy

    energy = mqtt_svc.cache.get_energy_data(anlage.id)
    if not energy:
        return mqtt_energy, mqtt_inv_energy

    # ⛔ F-66 (gruaGit, Discussion #396): Der Cache trägt den zuletzt
    # empfangenen **Zählerstand**, nicht die Monatsmenge — so sagt es die
    # Topic-Registry, und so schreibt der Absender. Bis zum 27.08. wurde
    # dieser Stand hier ungerechnet als „Monatswert" mit Konfidenz 91
    # angeboten: elf Felder meldeten „weicht ab" (6675,3 gegen 552,75),
    # und „Sensorwert übernehmen" daneben hätte den Lebensstand als
    # Monatsmenge gespeichert. Jetzt wird die **Menge des angefragten
    # Monats** aus den mitgeschriebenen Ständen gebildet.
    #
    # ⭐ Der Monatsbezug ist der zweite Teil des Fehlers und wiegt ebenso
    # schwer: Der Cache kennt nur das Jetzt. Für einen Monat aus dem
    # Frühjahr stand hier der heutige Stand — ein Vorschlag, der die
    # Frage gar nicht gehört hat, die er beantwortet.
    from backend.services.mqtt_energy_history_service import mqtt_monats_deltas
    from backend.services.snapshot.keys import extract_quellen_energy

    # Laufender Monat: bis jetzt, nicht bis zum Monatsende — ein Stand in
    # der Zukunft existiert nicht, und `delta` lieferte sonst None.
    _jetzt = datetime.now()
    _bis = _jetzt if (jahr, monat) == (_jetzt.year, _jetzt.month) else None
    monats_mengen = await mqtt_monats_deltas(
        db, anlage.id, jahr, monat, list(energy.keys()),
        quellen_energy=extract_quellen_energy(anlage), bis=_bis,
    )

    # Basis-Felder
    basis_map = {
        "einspeisung_kwh": "einspeisung_kwh",
        "netzbezug_kwh": "netzbezug_kwh",
    }
    for mqtt_key, feld_name in basis_map.items():
        val = monats_mengen.get(mqtt_key)
        if val is not None and val > 0:
            mqtt_energy[feld_name] = val

    # Investitions-Felder: inv/{inv_id}/{key}
    for mqtt_key, val in monats_mengen.items():
        if not mqtt_key.startswith("inv/") or val is None or val <= 0:
            continue
        ziel = _mqtt_inv_feld(mqtt_key)
        if ziel:
            mqtt_inv_energy.setdefault(ziel[0], {})[ziel[1]] = val

    return mqtt_energy, mqtt_inv_energy


def _sensor_ids_aus_mapping(basis_mapping: dict, inv_mappings: dict) -> list[str]:
    """Alle zugeordneten sensor_ids — Basis-Seite und Investitions-Seite."""
    all_sensor_ids = [
        cfg["sensor_id"] for cfg in basis_mapping.values()
        if cfg and cfg.get("strategie") == "sensor" and cfg.get("sensor_id")
    ]
    for inv_cfg in inv_mappings.values():
        if not isinstance(inv_cfg, dict):
            continue
        all_sensor_ids += [
            fcfg["sensor_id"] for fcfg in inv_cfg.get("felder", inv_cfg).values()
            if isinstance(fcfg, dict) and fcfg.get("strategie") == "sensor" and fcfg.get("sensor_id")
        ]
    return all_sensor_ids


async def lade_ha_statistik_werte(
    basis_mapping: dict, inv_mappings: dict, jahr: int, monat: int
) -> dict[str, float]:
    """HA Statistics Service für Sensor-Vorschläge: sensor_id → Monatsdifferenz.

    N-156/F-26: kein vorgeschaltetes `HA_INTEGRATION_AVAILABLE`
    (= SUPERVISOR_TOKEN) mehr — `is_available` weiter unten stellt
    dieselbe Frage und beantwortet sie für beide Wege (Recorder-DB oder
    WebSocket). Wer HA per Long-Lived-Token angebunden hat, bekam bis
    2026-08-11 im Monatsabschluss **keine** Sensor-Vorschläge, obwohl die
    Langzeitstatistik erreichbar war.
    """
    import asyncio

    # Alle sensor_ids aus dem Mapping sammeln — **vor** der Erreichbarkeitsfrage:
    # `is_available` baut im Zweifel eine Verbindung auf und zahlt bei nicht
    # erreichbarer HA einen vollen Timeout. Ohne einen einzigen Sensor-Eintrag
    # gibt es hier nichts zu holen, und ein Betrieb ganz ohne HA darf für diese
    # Antwort nicht warten.
    all_sensor_ids = _sensor_ids_aus_mapping(basis_mapping, inv_mappings)
    if not all_sensor_ids:
        return {}

    from backend.services.ha_statistics_service import get_ha_statistics_service
    ha_stats_svc = get_ha_statistics_service()
    if not ha_stats_svc.is_available:
        return {}

    try:
        stats_result = await asyncio.to_thread(ha_stats_svc.get_monatswerte, all_sensor_ids, jahr, monat)
        return {s.sensor_id: s.differenz for s in stats_result.sensoren if s.differenz is not None}
    except Exception:
        logger.warning("HA Statistics DB nicht erreichbar für Monatsabschluss-Vorschläge")
    return {}


async def baue_kontext(
    *, db: AsyncSession, anlage: Anlage, anlage_id: int, jahr: int, monat: int
) -> MonatsabschlussKontext:
    """Alle Eingänge EINMAL beschaffen — Mapping, Connector, MQTT, Monatszeile,
    HA-Statistik, Feldliste, Zählerstände.

    ⚠ **Zwei Beschaffungen stehen hier früher als in der Fassung bis RF-1:** die
    Feldliste und die Zählerstände zum Monatsende. Zwischen ihrer alten und
    ihrer neuen Stelle liegt **kein Schreibzugriff** — alles dazwischen
    (`get_vorschlaege`, `pruefe_plausibilitaet`) sind reine Lesepfade.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    basis_mapping = sensor_mapping.get("basis", {})
    inv_mappings = sensor_mapping.get("investitionen", {})

    connector = lade_connector_monatswerte(anlage, jahr, monat)
    # N-229: Seit mehrere Quellen speicherbar sind, steht dort eine Liste —
    # `lade_quellen` liest beide Formen. Ein roher `.get("provider_id")` wäre
    # an der neuen Form ein AttributeError.
    cloud_import_konfiguriert = bool(lade_quellen(anlage.connector_config))
    mqtt_energy, mqtt_inv_energy = await lade_mqtt_monatsmengen(
        db, anlage, jahr, monat
    )

    # Bestehende Monatsdaten laden
    monatsdaten = await lade_monatsdaten(db, anlage_id, jahr, monat)

    ha_stats_werte = await lade_ha_statistik_werte(
        basis_mapping, inv_mappings, jahr, monat
    )

    alle_basis_felder, preis_messung = await lade_basis_feldliste(
        db, anlage, anlage_id, jahr, monat
    )

    return MonatsabschlussKontext(
        db=db,
        anlage=anlage,
        anlage_id=anlage_id,
        jahr=jahr,
        monat=monat,
        vorschlag_service=VorschlagService(db),
        sensor_mapping=sensor_mapping,
        basis_mapping=basis_mapping,
        inv_mappings=inv_mappings,
        monatsdaten=monatsdaten,
        # Datenquelle des Monats ermitteln
        datenquelle=getattr(monatsdaten, "datenquelle", None) if monatsdaten else None,
        # PN 90128: bewusst behaltene Abweichungen (Basis-Felder) — je Feld
        # {"sensor": …, "wert": …}; leer, solange nichts bestätigt wurde.
        basis_geprueft=(getattr(monatsdaten, "geprueft_gegen", None) or {}) if monatsdaten else {},
        ha_stats_werte=ha_stats_werte,
        connector=connector,
        cloud_import_konfiguriert=cloud_import_konfiguriert,
        mqtt_energy=mqtt_energy,
        mqtt_inv_energy=mqtt_inv_energy,
        alle_basis_felder=alle_basis_felder,
        preis_messung=preis_messung,
        zaehler_ende=await lade_zaehler_ende(db, anlage_id, jahr, monat),
    )


# =============================================================================
# Basis-Felder und optionale Felder
# =============================================================================

async def _bedingte_basis_vorschlaege(
    ctx: MonatsabschlussKontext,
    feld: str,
    strategie: Optional[str],
    sensor_id: Optional[str],
    vorschlaege: list,
) -> None:
    """── Feld-spezifische Vorschläge (bedingte Felder) ──────────────────

    Der einzige Ort, an dem die Vorschlagskaskade nach dem **Feldnamen**
    unterscheidet. `vorschlaege` wird an Ort und Stelle ergänzt — die
    Reihenfolge (`insert(0, …)` gegen `append`) ist die Vorschlagsordnung.
    """
    if feld == "netzbezug_durchschnittspreis_cent":
        # 1. Verbrauchsgewichteter Ø aus Energieprofil-Stundendaten (höchste Qualität)
        # ⭐ N-535: **derselbe** Aggregat-Aufruf, der in `lade_basis_feldliste`
        # entschieden hat, ob dieses Feld überhaupt erscheint. Er stand hier bis
        # zum 19.09.2026 ein zweites Mal mit identischen Argumenten
        # (`anlage_id, jahr, monat, db`) und ohne Cache — und genau dann, wenn
        # der erste eine Messung geliefert hatte, also immer, wenn er überhaupt
        # stattfand. Zwei Antworten auf dieselbe Frage wären zudem die
        # F-56-Klasse; eine Antwort ist auch fachlich das Richtige.
        aggr = ctx.preis_messung
        if aggr and aggr.gewichtet_cent is not None:
            abdeckung_pct = round(aggr.abdeckung * 100)
            vorschlaege.insert(0, Vorschlag(
                wert=aggr.gewichtet_cent,
                quelle=VorschlagQuelle.BERECHNUNG,
                konfidenz=aggr.konfidenz,
                beschreibung=(
                    f"Verbrauchsgewichteter Ø aus {aggr.abgedeckte_stunden} "
                    f"Stundenpreisen ({abdeckung_pct} % Abdeckung)"
                ),
            ))
        # 2. HA-Sensor-Vorschlag als Fallback (Momentanwert, weniger genau)
        if strategie == "sensor" and sensor_id:
            ha_state_svc = get_ha_state_service()
            sensor_wert = await ha_state_svc.get_sensor_state(sensor_id)
            if sensor_wert is not None:
                vorschlaege.append(Vorschlag(
                    wert=round(sensor_wert, 2),
                    quelle=VorschlagQuelle.HA_SENSOR,
                    konfidenz=70,
                    beschreibung="Aktueller HA-Sensor-Wert (Momentanpreis, kein Monatsmittel)",
                ))
    elif feld == "kraftstoffpreis_euro":
        # Vorschlag aus TagesZusammenfassung-Durchschnitt
        from backend.services.kraftstoff_preis_service import get_monatsdurchschnitt
        avg_preis = await get_monatsdurchschnitt(
            ctx.anlage_id, ctx.jahr, ctx.monat, ctx.db
        )
        if avg_preis is not None:
            vorschlaege.insert(0, Vorschlag(
                wert=avg_preis,
                quelle=VorschlagQuelle.BERECHNUNG,
                konfidenz=85,
                beschreibung="Monatsdurchschnitt aus EU Weekly Oil Bulletin",
            ))


async def baue_basis_feld(
    ctx: MonatsabschlussKontext, feld_config: dict
) -> FeldStatus:
    """Ein Basis-Feld: Wert, Mapping, Vorschlagskaskade, Warnungen.

    Die drei Quellen-Einfügungen (HA-Statistik · Connector · MQTT) stehen
    zusammen und in dieser Reihenfolge: sie SIND die Kaskade, `insert(0, …)`
    ist ihre Ordnung.
    """
    feld = feld_config["feld"]
    aktueller_wert = getattr(ctx.monatsdaten, feld, None) if ctx.monatsdaten else None

    # Mapping-Info - verwende mapping_key aus der Konfiguration
    mapping_key = feld_config.get("mapping_key", feld)
    mapping_info = ctx.basis_mapping.get(mapping_key, {})
    strategie = mapping_info.get("strategie") if mapping_info else None
    sensor_id = mapping_info.get("sensor_id") if mapping_info else None

    # Quelle bestimmen
    quelle = None
    if aktueller_wert is not None:
        quelle = ctx.datenquelle if ctx.datenquelle else "manuell"

    # Vorschläge holen (historische Daten) — nur für Standard-Basis-Felder
    vorschlaege = await ctx.vorschlag_service.get_vorschlaege(
        ctx.anlage_id, feld, ctx.jahr, ctx.monat
    )

    # Bei konfiguriertem Sensor: HA Statistics Wert als Vorschlag hinzufügen
    if strategie == "sensor" and sensor_id and sensor_id in ctx.ha_stats_werte:
        stats_wert = ctx.ha_stats_werte[sensor_id]
        if stats_wert > 0:
            vorschlaege.insert(0, Vorschlag(
                wert=round(stats_wert, 1),
                quelle=VorschlagQuelle.HA_STATISTICS,
                konfidenz=92,
                beschreibung="Aus HA-Statistik (Recorder-DB)",
            ))

    # Connector-Vorschlag einfügen
    if ctx.connector.delta and feld in ctx.connector.delta:
        conn_wert = ctx.connector.delta[feld]
        if conn_wert is not None and conn_wert > 0:
            vorschlaege.insert(0, Vorschlag(
                wert=round(conn_wert, 1),
                quelle=VorschlagQuelle.LOCAL_CONNECTOR,
                # Basis-Feld = anlagenweiter Zählerstand, nichts verteilt.
                konfidenz=KONFIDENZ_CONNECTOR_GEMESSEN,
                beschreibung="Vom Wechselrichter (Zählerstand-Differenz)",
            ))

    # MQTT Inbound-Vorschlag einfügen (Konfidenz 91)
    if feld in ctx.mqtt_energy:
        vorschlaege.insert(0, Vorschlag(
            wert=ctx.mqtt_energy[feld],
            quelle=VorschlagQuelle.MQTT_INBOUND,
            konfidenz=91,
            beschreibung="Aus MQTT-Zählerständen (Differenz über den Monat)",
        ))

    await _bedingte_basis_vorschlaege(ctx, feld, strategie, sensor_id, vorschlaege)

    # Warnungen prüfen (nur wenn Wert vorhanden)
    warnungen = []
    if aktueller_wert is not None:
        warnungen = await ctx.vorschlag_service.pruefe_plausibilitaet(
            ctx.anlage_id, feld, aktueller_wert, ctx.jahr, ctx.monat
        )

    return FeldStatus(
        feld=feld,
        label=feld_config["label"],
        einheit=feld_config["einheit"],
        aktueller_wert=aktueller_wert,
        quelle=quelle,
        vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
        warnungen=[_warnung_to_response(w) for w in warnungen],
        strategie=strategie,
        sensor_id=sensor_id,
        gruppe=feld_config.get("gruppe"),
        geprueft_gegen=ctx.basis_geprueft.get(feld),
    )


async def baue_basis_felder(ctx: MonatsabschlussKontext) -> list[FeldStatus]:
    """Basis-Felder aufbereiten."""
    return [await baue_basis_feld(ctx, feld_config) for feld_config in ctx.alle_basis_felder]


def _optionales_feld(feld_config: dict, monatsdaten: Optional[Monatsdaten]) -> FeldStatus:
    """Ein optionales Feld — Text oder Zahl.

    ⛔ **Die beiden Zweige bleiben getrennt.** Der Text-Zweig entscheidet die
    Quelle am **Wahrheitswert** (`if aktueller_text`), der Zahl-Zweig an
    `is not None`. Zusammengelegt bekäme der leere String `""` eine andere
    Antwort als heute.
    """
    feld = feld_config["feld"]
    feld_typ = feld_config.get("typ", "number")
    gespeichert = getattr(monatsdaten, feld, None) if monatsdaten else None

    if feld_typ == "text":
        return FeldStatus(
            feld=feld,
            label=feld_config["label"],
            einheit=feld_config["einheit"],
            aktueller_text=gespeichert,
            quelle="manuell" if gespeichert else None,
            typ="text",
        )

    return FeldStatus(
        feld=feld,
        label=feld_config["label"],
        einheit=feld_config["einheit"],
        aktueller_wert=gespeichert,
        quelle="manuell" if gespeichert is not None else None,
        typ="number",
    )


def baue_optionale_felder(monatsdaten: Optional[Monatsdaten]) -> list[FeldStatus]:
    """Optionale Felder aufbereiten (manuelle Eingaben, nicht aus HA)."""
    return [_optionales_feld(feld_config, monatsdaten) for feld_config in OPTIONALE_FELDER]


# =============================================================================
# Investitionen
# =============================================================================

async def _ergaenze_investitions_vorschlaege(
    ctx: MonatsabschlussKontext,
    inv,
    feld: str,
    strategie: Optional[str],
    sensor_id: Optional[str],
    vorschlaege: list,
) -> None:
    """Die vier Fremdquellen eines Investitions-Feldes, in ihrer Reihenfolge.

    HA-Statistik · Zählerstand (#377) · Connector (zerlegt oder gemessen) ·
    MQTT-Inbound. `vorschlaege` wird an Ort und Stelle ergänzt.
    """
    # Bei konfiguriertem Sensor: HA Statistics Wert als Vorschlag hinzufügen.
    # Nur für Zählerfelder — der Wert ist eine Zählerdifferenz
    # (MAX−MIN), bei einem Preis-Feld also die Monats-Spreizung. Ohne
    # den Filter stand die mit Konfidenz 92 ÜBER dem korrekt
    # gerechneten Vorschlag (s. `ist_zaehler_differenz_feld`).
    if (
        strategie == "sensor" and sensor_id and sensor_id in ctx.ha_stats_werte
        and ist_zaehler_differenz_feld(feld)
    ):
        stats_wert = ctx.ha_stats_werte[sensor_id]
        if stats_wert > 0:
            vorschlaege.insert(0, Vorschlag(
                wert=round(stats_wert, 1),
                quelle=VorschlagQuelle.HA_STATISTICS,
                konfidenz=92,
                beschreibung="Aus HA-Statistik (Recorder-DB)",
            ))

    # Zählerstand (#377) — der mitgeschriebene Stand, keine Differenz.
    # Er steht ganz vorn: für dieses Feld gibt es keinen zweiten Weg,
    # und ein Vormonats-/Durchschnittswert wäre hier sogar schädlich
    # (der Stand eines Gaszählers hat keinen Mittelwert).
    if feld == ZAEHLERSTAND_FELD and inv.id in ctx.zaehler_ende:
        vorschlaege.insert(0, Vorschlag(
            wert=ctx.zaehler_ende[inv.id],
            quelle=VorschlagQuelle.ZAEHLERSTAND,
            konfidenz=95,
            beschreibung="Mitgeschriebener Stand am Monatsende",
        ))

    # Connector-Vorschlag einfügen — bei mehreren Modulen/Speichern ist
    # der Wert der ZERLEGTE Anlagen-Gesamtwert und wird als solcher
    # beschriftet (A3/a2: keine Anzeige behauptet, gemessen zu sein).
    inv_conn_values = ctx.connector.inv_verteilung.get(inv.id, {})
    if feld in inv_conn_values:
        conn_wert = inv_conn_values[feld]
        if conn_wert > 0:
            verteilt_hinweis = ctx.connector.verteilt_hinweis.get(inv.id, {}).get(feld)
            vorschlaege.insert(0, Vorschlag(
                wert=round(conn_wert, 1),
                quelle=VorschlagQuelle.LOCAL_CONNECTOR,
                konfidenz=(
                    KONFIDENZ_CONNECTOR_VERTEILT if verteilt_hinweis
                    else KONFIDENZ_CONNECTOR_GEMESSEN
                ),
                beschreibung=(
                    f"Vom Wechselrichter — Gesamtwert, {verteilt_hinweis}"
                    if verteilt_hinweis
                    else "Vom Wechselrichter (Zählerstand-Differenz)"
                ),
                # #352: der Client meldet die Marke beim Speichern
                # zurück, damit der zerlegte Wert in der Provenance
                # nicht als Gerätemessung landet.
                abgeleitet=(
                    _abgeleitet_marke(feld) if verteilt_hinweis else None
                ),
            ))

    # MQTT Inbound-Vorschlag einfügen (Konfidenz 91)
    mqtt_inv_values = ctx.mqtt_inv_energy.get(inv.id, {})
    if feld in mqtt_inv_values:
        vorschlaege.insert(0, Vorschlag(
            wert=mqtt_inv_values[feld],
            quelle=VorschlagQuelle.MQTT_INBOUND,
            konfidenz=91,
            beschreibung="Aus MQTT-Zählerständen (Differenz über den Monat)",
        ))


async def baue_investitions_feld(
    ctx: MonatsabschlussKontext,
    inv,
    feld_config: dict,
    verbrauch_daten: dict,
    inv_mapping: dict,
    inv_geprueft: dict,
) -> FeldStatus:
    """Ein Feld einer Investition: Wert, Mapping, Vorschläge, Warnungen, Anfang."""
    feld = feld_config["feld"]
    aktueller_wert = verbrauch_daten.get(feld)

    # Mapping-Info
    feld_mapping = inv_mapping.get(feld, {})
    strategie = feld_mapping.get("strategie") if feld_mapping else None
    sensor_id = feld_mapping.get("sensor_id") if feld_mapping else None

    # Vorschläge holen (historische Daten)
    vorschlaege = await ctx.vorschlag_service.get_vorschlaege(
        ctx.anlage_id, feld, ctx.jahr, ctx.monat, investition_id=inv.id
    )

    await _ergaenze_investitions_vorschlaege(
        ctx, inv, feld, strategie, sensor_id, vorschlaege
    )

    # Warnungen prüfen
    warnungen = []
    if aktueller_wert is not None:
        warnungen = await ctx.vorschlag_service.pruefe_plausibilitaet(
            ctx.anlage_id, feld, aktueller_wert, ctx.jahr, ctx.monat, inv.id
        )

    # #407: der Anfang eines Stand-Feldes reist mit (s. FeldStatus).
    stand_vormonat = None
    if ist_stand_feld(feld):
        stand_vormonat = await ctx.vorschlag_service.vormonat_wert(
            ctx.anlage_id, feld, ctx.jahr, ctx.monat, inv.id
        )

    return FeldStatus(
        feld=feld,
        label=feld_config["label"],
        # #377: Die Einheit kann am GERÄT hängen (Zählerstand: m³/l/…)
        # statt am Feld. Ein Leser für alle (S5) — sonst stünde im
        # Monatsformular nichts neben der Zahl.
        einheit=einheit_fuer(feld, inv),
        aktueller_wert=aktueller_wert,
        quelle=(ctx.datenquelle or "manuell") if aktueller_wert is not None else None,
        vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
        warnungen=[_warnung_to_response(w) for w in warnungen],
        strategie=strategie,
        sensor_id=sensor_id,
        geprueft_gegen=inv_geprueft.get(feld),
        stand_vormonat=stand_vormonat,
    )


async def baue_investition_status(
    ctx: MonatsabschlussKontext, inv
) -> Optional[InvestitionStatus]:
    """Eine Investition mit ihren Feldern — oder ``None``, wenn sie keine hat.

    ⚠ **ADR-002/P10-Ausnahme, und zwar hier:** Diese Funktion lädt die
    `InvestitionMonatsdaten`-**Zeile** selbst. Das Formular braucht sie roh
    (`verbrauch_daten`, `geprueft_gegen`, `sonstige_positionen`) — ein
    `MonatsFakt` trägt Mengen, keine Zeilen. Der Ausnahme-Eintrag in
    `test_wurzelmuster_konformitaet.py` zeigt auf **diese** Funktion.
    """
    # InvestitionMonatsdaten laden
    imd_result = await ctx.db.execute(
        select(InvestitionMonatsdaten)
        .where(and_(
            InvestitionMonatsdaten.investition_id == inv.id,
            InvestitionMonatsdaten.jahr == ctx.jahr,
            InvestitionMonatsdaten.monat == ctx.monat,
        ))
    )
    imd = imd_result.scalar_one_or_none()
    verbrauch_daten = imd.verbrauch_daten if imd else {}
    # PN 90128: bewusst behaltene Abweichungen dieser Investition.
    inv_geprueft = (getattr(imd, "geprueft_gegen", None) or {}) if imd else {}

    # Mapping für diese Investition - beachte die verschachtelte Struktur {"felder": {...}}
    inv_mapping_raw = ctx.inv_mappings.get(str(inv.id), {})
    inv_mapping = inv_mapping_raw.get("felder", inv_mapping_raw) if isinstance(inv_mapping_raw, dict) else {}

    # R1 (SOLL Wärme/Klima §3.2a): **erweiterte** Felder erscheinen hier nur,
    # wenn es sie an diesem Gerät belegbar gibt — *„was ein Gerät liefern
    # kann, sagt der zugeordnete Zähler, nicht seine Bauart."* Belegt heißt:
    # ein gepflegter Wert in diesem Monat **oder** eine Zuordnung.
    #
    # ⚠ **Beides, nicht nur eines.** Nur die Zuordnung zu prüfen verlöre den
    # Anwender, der seinen Kühlwert von Hand einträgt; nur den Wert zu prüfen
    # verlöre den ersten Monat einer frischen Zuordnung — dann stünde das
    # Feld genau in dem Moment nicht da, in dem es gebraucht wird.
    #
    # ⚠ **Die IMD-Zeile wird deshalb VOR der Feldliste geladen.** Bis zum
    # 26.08.2026 stand die Feldliste oben und die Zeile darunter; die
    # Reihenfolge trug keine Absicht, nur Gewohnheit.
    belegte_felder = {
        basis_feld_key(k) for k, v in (verbrauch_daten or {}).items()
        if v is not None
    } | {basis_feld_key(k) for k in inv_mapping}

    # Felder für diese Investition auflösen (Bedingungen berücksichtigen)
    felder_config = get_felder_fuer_investition(
        inv.typ, inv.parameter,
        anlage_investitionen=ctx.anlage.investitionen,
        belegte_felder=belegte_felder,
    )
    if not felder_config:
        return None

    felder: list[FeldStatus] = [
        await baue_investitions_feld(
            ctx, inv, feld_config, verbrauch_daten, inv_mapping, inv_geprueft
        )
        for feld_config in felder_config
    ]

    # sonstige_positionen aus verbrauch_daten lesen (für alle Typen)
    inv_sonstige_pos = []
    if verbrauch_daten and isinstance(verbrauch_daten.get("sonstige_positionen"), list):
        inv_sonstige_pos = verbrauch_daten["sonstige_positionen"]

    # Kategorie nur für Typ "sonstiges" relevant
    inv_kategorie = (inv.parameter or {}).get("kategorie") if inv.typ == "sonstiges" else None

    return InvestitionStatus(
        id=inv.id,
        typ=inv.typ,
        bezeichnung=inv.bezeichnung,
        felder=felder,
        kategorie=inv_kategorie,
        sonstige_positionen=inv_sonstige_pos,
    )


async def baue_investitionen_status(
    ctx: MonatsabschlussKontext,
) -> list[InvestitionStatus]:
    """Investitionen aufbereiten — ohne die, die in diesem Monat kein Feld führen."""
    investitionen_status: list[InvestitionStatus] = []
    for inv in ctx.anlage.investitionen:
        status = await baue_investition_status(ctx, inv)
        if status is not None:
            investitionen_status.append(status)
    return investitionen_status


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{anlage_id}/{jahr}/{monat}", response_model=MonatsabschlussResponse)
async def get_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Status aller Felder für einen Monat zurück.

    Enthält:
    - Aktuelle Werte (falls vorhanden)
    - Vorschläge für fehlende/leere Felder
    - Plausibilitätswarnungen
    - Mapping-Informationen
    """
    anlage = await lade_anlage_mit_investitionen(db, anlage_id)
    ctx = await baue_kontext(
        db=db, anlage=anlage, anlage_id=anlage_id, jahr=jahr, monat=monat
    )

    basis_felder = await baue_basis_felder(ctx)

    investitionen_status = await baue_investitionen_status(ctx)

    optionale_felder = baue_optionale_felder(ctx.monatsdaten)

    return MonatsabschlussResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        ist_abgeschlossen=ctx.monatsdaten is not None,
        ha_mapping_konfiguriert=bool(ctx.sensor_mapping),
        connector_konfiguriert=ctx.connector.konfiguriert,
        cloud_import_konfiguriert=ctx.cloud_import_konfiguriert,
        mqtt_inbound_konfiguriert=bool(ctx.mqtt_energy or ctx.mqtt_inv_energy),
        portal_import_vorhanden=ctx.datenquelle == "portal_import",
        datenquelle=ctx.datenquelle,
        basis_felder=basis_felder,
        optionale_felder=optionale_felder,
        investitionen=investitionen_status,
    )


@router.get("/naechster/{anlage_id}", response_model=Optional[NaechsterMonatResponse])
async def get_naechster_monat(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Findet den frühesten offenen (fehlenden/unvollständigen) Monat.

    Deckungsgleich mit der Frontend-Ableitung (`lib/monatsLuecken.ts`): derselbe
    Bereich [Anschaffungs-Anker … Vormonat(heute)], dieselbe Lücken-Logik — damit
    Status-Fusszeile und Monatsdaten-Block NICHT auseinanderdriften (§7 „eine
    Quelle"). Der frühere naive „letzter Monat + 1"-Sprung war blind für
    Binnen-Lücken (R20-2, [[feedback_aggregations_drift]]).

    Rückgabe: der früheste offene Monat, oder ``None`` bei lückenlosem Bereich.
    """
    from backend.core.monats_luecken import naechster_offener_monat_fuer
    from backend.core.berechnungen.spez_ertrag import PV_ERZEUGER_TYPEN

    # Anlage inkl. Investitionen laden — die Erzeuger stellen den Fallback-Anker,
    # wenn die Anlage kein Installationsdatum trägt (N-243).
    result = await db.execute(
        select(Anlage)
        .where(Anlage.id == anlage_id)
        .options(selectinload(Anlage.investitionen))
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # Vorhandene Monate = alle Monatsdaten-Zeilen (jahr, monat). Entspricht dem,
    # was das Frontend aus `listAggregiert` als `vorhandene` sieht.
    md_result = await db.execute(
        select(Monatsdaten.jahr, Monatsdaten.monat)
        .where(Monatsdaten.anlage_id == anlage_id)
    )
    vorhandene: set[tuple[int, int]] = {(jahr, monat) for jahr, monat in md_result.all()}

    offen = naechster_offener_monat_fuer(
        vorhandene=vorhandene,
        erzeuger_anschaffungsdaten=[
            inv.anschaffungsdatum for inv in anlage.investitionen
            if inv.typ in PV_ERZEUGER_TYPEN
        ],
        anlage_installationsdatum=anlage.installationsdatum,
        heute=date.today(),
    )
    if offen is None:
        return None

    naechster_jahr, naechster_monat = offen
    sensor_mapping = anlage.sensor_mapping or {}

    return NaechsterMonatResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        jahr=naechster_jahr,
        monat=naechster_monat,
        monat_name=MONAT_NAMEN[naechster_monat],
        ha_mapping_konfiguriert=bool(sensor_mapping),
    )


@router.get("/historie/{anlage_id}")
async def get_monatsabschluss_historie(
    anlage_id: int,
    limit: int = 12,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Historie der letzten Monatsabschlüsse zurück.

    Returns:
        Liste der letzten {limit} Monatsdaten
    """
    result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr.desc(), Monatsdaten.monat.desc())
        .limit(limit)
    )
    monatsdaten = result.scalars().all()

    return [
        {
            "id": md.id,
            "jahr": md.jahr,
            "monat": md.monat,
            "monat_name": MONAT_NAMEN[md.monat],
            "einspeisung_kwh": md.einspeisung_kwh,
            "netzbezug_kwh": md.netzbezug_kwh,
        }
        for md in monatsdaten
    ]
