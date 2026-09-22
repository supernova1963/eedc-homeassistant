"""
EEDC Sensor Export für Home Assistant.

Definiert alle KPIs und berechneten Werte, die an HA exportiert werden können.
Unterstützt zwei Export-Methoden:
1. REST API - HA liest Werte über rest platform
2. MQTT Discovery - Native HA-Entitäten via MQTT Auto-Discovery
"""

import math
from dataclasses import dataclass, field
from typing import Literal, Optional, Any
from enum import Enum


#: Die **einzigen** HA-Komponententypen, die eedc publiziert (KONZEPT-EEDC-AT-HA §2).
#:
#: ⛔ **Das ist eine Entscheidung, kein technischer Riegel.** Einen `switch` oder
#: `number` zu publizieren kostet dieselben Zeilen wie den `binary_sensor` hier —
#: eedc hat es bis `77c6e211^` (13.03.2026) sogar getan (MWD-Startwerte als
#: `homeassistant/number/eedc_*`). Was eedc nicht schaltet, schaltet es, **weil es
#: so entschieden ist** (31.08.2026: bereitstellen statt zustellen), nicht weil es
#: nicht ginge. Wer die Menge hier erweitert, ändert diese Entscheidung — und der
#: Wächter `test_s2_zweiter_komponententyp.py::test_nur_zwei_komponententypen`
#: sorgt dafür, dass das ein bewusster Schritt ist und kein Nebeneffekt.
KOMPONENTEN_TYPEN: tuple[str, ...] = ("sensor", "binary_sensor")


#: Der **Paket-Stand**, den dieser Code mitbringt — eine fortlaufende ganze Zahl.
#:
#: ⭐ **Warum eine Zahl und kein Versionsstring** (N-545, 22.09.2026): Die
#: Release-Nummer entscheidet der Maintainer zum Zeitpunkt des Releases;
#: `release.sh` zieht sie in fünf Dateien nach, nicht aber in einer Sensor-
#: Definition. Ein `seit_version = "4.0.50"` hier wäre also eine **Behauptung**
#: über eine Zahl, die dieser Code nicht kennt — die Lab-Kopie hieß beim Bau
#: `4.0.50-rc1`, das Release kann anders heißen. Ein Paket-Stand ist von der
#: Versionsnummer entkoppelt und bleibt bei jedem Bump unberührt.
#:
#: Wer ein neues Sensor-Paket ausliefert, erhöht diese Zahl um 1, trägt ein Label
#: nach und setzt `seit_paket` an **jeder** neuen Definition. Dass niemand das
#: Letzte vergisst, hält `test_n545_neue_sensoren_bei_bestand_abgewaehlt.py` fest.
AKTUELLES_SENSOR_PAKET: int = 1

#: Klartext je Paket-Stand — was der Anwender in der Abwahl-Fläche liest.
SENSOR_PAKET_LABELS: dict[int, str] = {
    1: "eedc@ha, Teil 1 — Steuerungshilfen, Preise und Speicher",
}


class SensorCategory(str, Enum):
    """Sensor-Kategorien für Gruppierung."""
    ANLAGE = "anlage"           # PV-Anlage Gesamt
    ENERGIE = "energie"         # Energie-Werte (kWh)
    QUOTE = "quote"             # Prozent-Werte (Autarkie, EV-Quote)
    FINANZEN = "finanzen"       # Euro-Werte
    UMWELT = "umwelt"           # CO2-Werte
    INVESTITION = "investition" # Investitions-KPIs
    E_AUTO = "e_auto"           # E-Auto spezifisch
    WAERMEPUMPE = "waermepumpe" # Wärmepumpe spezifisch
    SPEICHER = "speicher"       # Speicher spezifisch
    WALLBOX = "wallbox"         # Wallbox spezifisch
    STATUS = "status"           # Status-Informationen (letzter Import, etc.)
    PROGNOSE = "prognose"       # PV-Prognose (eedc-eigen, Vorausschau)
    PREIS = "preis"             # Börsenpreis-Trigger (dynamische Tarife)
    # ── S2/S3 „eedc@ha, Teil 1" (21.09.2026) ────────────────────────────────
    # `steuerung` buendelt die anlagenweiten Entscheidungs- und Plan-Groessen
    # (Ueberschuss, guenstige Stunde, bestes Fenster, Arbitrage-Vorschlag).
    # ⚠ **Warum eine eigene Gruppe und nicht „prognose"/„preis"** (Entscheid
    # Gernot 21.09.): die Abwahl-Flaeche zeigt je Gruppe eine Liste; unter
    # „Prognose" staenden sonst 20+ Zeilen, von denen die Haelfte gar keine
    # Prognose ist. Die Gruppe ist eine **Lese**-Ordnung, keine zweite
    # Wahrheit — abgewaehlt wird weiterhin je `key`.
    STEUERUNG = "steuerung"     # Entscheidungs-/Plan-Groessen fuer Automationen
    SONSTIGES = "sonstiges"     # Sonstige Verbraucher je Geraet (Pool, Sauna, Heizstab)


@dataclass
class SensorDefinition:
    """Definition eines exportierbaren Sensors."""
    key: str                           # Eindeutiger Schlüssel (z.B. "pv_erzeugung_gesamt")
    name: str                          # Anzeigename (z.B. "PV Erzeugung Gesamt")
    unit: str                          # Einheit (z.B. "kWh", "%", "€")
    icon: str                          # MDI Icon (z.B. "mdi:solar-power")
    category: SensorCategory           # Kategorie für Gruppierung
    formel: str                        # Berechnungsformel als Text
    device_class: Optional[str] = None # HA device_class (z.B. "energy", "monetary")
    state_class: Optional[str] = None  # HA state_class (z.B. "total", "measurement")
    entity_category: Optional[str] = None  # HA entity_category (z.B. "diagnostic")
    #: HA-Komponententyp des Discovery-Topics (`homeassistant/{komponente}/…`).
    #:
    #: ⭐ **Warum ein Feld an der Definition und keine Namenskonvention** (S2,
    #: 21.09.2026): Der Typ entscheidet über drei Dinge auf einmal — das
    #: Config-Topic, die erlaubten Felder im Payload (`binary_sensor` kennt
    #: weder `unit_of_measurement` noch `state_class`) und die Form des
    #: Zustands (`ON`/`OFF` statt einer Zahl). Wer ihn aus dem Schlüsselnamen
    #: ableitet, verteilt dieselbe Entscheidung auf drei Stellen, die
    #: auseinanderlaufen können — genau die Klasse, aus der #400 entstand
    #: (Publisher und Entferner bildeten ihre Adressen getrennt).
    #:
    #: ⚠ Ein `binary_sensor` trägt **nie** `unit` oder `state_class`; der
    #: Klassen-Vertrag (`test_ha_export_sensor_klassen_vertrag.py`) hält das
    #: fest, damit es nicht erst in HAs Protokoll auffällt.
    komponente: Literal["sensor", "binary_sensor"] = "sensor"
    #: Mit welchem **Sensor-Paket** kam diese Definition dazu? (N-545, 22.09.2026)
    #:
    #: ``0`` = „seit immer" — die 57 Definitionen, die es zum Zeitpunkt der
    #: Einführung schon gab (Stand `ca6cf36f`). Ein höherer Wert benennt das
    #: Paket, mit dem der Sensor NEU ist; `AKTUELLES_SENSOR_PAKET` oben führt die
    #: Zählung, `SENSOR_PAKET_LABELS` den Klartext.
    #:
    #: ⚠ **Das ist keine zweite Voreinstellung.** Die Definition steuert nichts —
    #: sie trägt nur ihren Paket-Stand. Ob ein Sensor exportiert wird, entscheidet
    #: allein die Abwahlliste in den Export-Settings
    #: (`mqtt_broker_settings.ABWAHL_FELD`); der Erstlauf-Schritt
    #: `migrations/migrate_sensor_paket_abwahl.py` liest den Paket-Stand **einmal
    #: je Paket** und trägt die neuen Schlüssel dort ein — aber nur bei
    #: **Bestands**installationen (eine Neuinstallation bekommt weiterhin alles,
    #: 28.08.-Entscheid).
    seit_paket: int = 0
    # ⛔ **Hier stand bis zum 28.08.2026 `enabled_by_default: bool = True`** — ein
    # Feld, das nichts steuerte: es wurde ausschliesslich in einer API-Antwort
    # durchgereicht und erreichte den Discovery-Payload nie. Mit dem Entscheid zu
    # #400 (alle Sensoren bleiben per Default AN, die Abwahl ist eine bewusste
    # Anwenderwahl) waere es dauerhaft irrefuehrend geblieben: ein Leser haette
    # angenommen, hier lasse sich eine Voreinstellung setzen, die es bewusst nicht
    # geben soll. Die Abwahl liegt in den Export-Settings
    # (`mqtt_broker_settings.ABWAHL_FELD`), nicht an der Definition.
    #
    # ⭐ **Auch `seit_paket` (N-545, 22.09.) ist keine Rueckkehr dieses Feldes.**
    # Die Abwahl liegt weiter in den Settings — die Definition traegt nur ihren
    # Paket-Stand. Aus ihm leitet der Erstlauf-Schritt EINMAL je Paket ab, was
    # fuer **Bestands**installationen abgewaehlt startet; wer den Sensor danach
    # anhakt, behaelt ihn ueber jeden Neustart.


@dataclass
class SensorValue:
    """Ein berechneter Sensorwert mit Metadaten."""
    definition: SensorDefinition
    value: Any                          # Der aktuelle Wert
    berechnung: Optional[str] = None    # Konkrete Berechnung (z.B. "3200 ÷ 4670 × 100")
    zusatz_attribute: dict = field(default_factory=dict)  # Zusätzliche Attribute


# =============================================================================
# RUNDUNG JE GRÖSSENART — die EINE Regel für den Export-Payload
# =============================================================================
# Rainer-PN 89905/2: der Export lieferte für jede Größe dieselben zwei
# Nachkommastellen (`round(value, 2)` im Publisher) — bei 12.345,67 kWh sind das
# zwei Stellen Scheingenauigkeit, die in HA nur die Anzeige verlängern.
# Entscheid (B7): pro Größenart runden statt global, und die Regel steht HIER
# neben den Sensor-Definitionen — nicht an jeder Sensorzeile im Route-Modul.
#
# Leitplanke: Leistungswerte werden NICHT gekappt — aus 0,35 kW darf keine 0
# werden. Dasselbe gilt generell (s. `runde_exportwert`): kein echter Wert kippt
# durch die Rundung auf 0, notfalls mit mehr Stellen (max. 3).
NACHKOMMASTELLEN_JE_EINHEIT: dict[str, int] = {
    # Energie und Mengen — ganze Zahlen reichen
    "kWh": 0,
    "kWh/kWp": 0,
    "km": 0,
    "kg": 0,
    # Geld — Cent-genau
    "€": 2,
    "€/Jahr": 2,
    # Arbeitspreise — zwei Stellen, so genau wie die Börsen-Quelle selbst
    "ct/kWh": 2,
    # Quoten
    "%": 1,
    # Leistung — bewusst mit Stellen (kleine Leistungen dürfen nicht kippen)
    "kW": 2,
    # Übrige Kennzahlen
    "h": 1,
    "Jahre": 1,
    "kWh/100km": 1,
}
NACHKOMMASTELLEN_DEFAULT = 2   # dimensionslose Kennwerte (COP, Zyklen, Rang …)
NACHKOMMASTELLEN_MAX = 3       # Obergrenze für die Nullkipp-Ausweichung

# ── Ausnahme: Prognose-Energie ist eine TAGESMENGE, kein Zählerstand ─────────
# Burkard (T89667 #279, 31.08.2026) hat „Rest heute" über einen Nachmittag gegen
# das Stundenprofil nachgerechnet und eine Nachkommastelle gewünscht. Die Regel
# darüber hängt an der **Einheit** — und genau das ist die Ursache: „kWh" trägt
# hier den Jahresertrag (12.345 kWh, wo zwei Nachkommastellen Scheingenauigkeit
# sind — Rainer-PN 89905/2, Entscheid B7) UND die Tagesprognose (0–60 kWh, wo
# eine ganze Zahl grob ist). Eine Einheit, zwei Größenordnungen.
#
# ⛔ Der ausschlaggebende Grund ist NICHT die Genauigkeit, sondern eine Summe:
# `Rest heute` + `bisher erzeugt` = `heute (nachgeführt)`. Werden die Summanden
# einzeln auf ganze Zahlen gerundet, geht sie sichtbar nicht mehr auf (gemessen:
# 12,5 + 6,5 = 19,0 wird zu 12 + 6 = 18). Dass diese Addition aufgeht, ist genau
# das, was v4.0.36 für #401 — denselben Melder — repariert hat.
#
# ⚑ REGEL statt Liste: es hängt an (Kategorie, Einheit), nicht an zehn Schlüsseln.
# Ein künftiger Prognose-Sensor bekommt die Stelle damit von selbst, statt still
# ganzzahlig zu bleiben, weil ihn niemand in eine Liste nachgetragen hat.
NACHKOMMASTELLEN_JE_KATEGORIE: dict[tuple[str, str], int] = {
    ("prognose", "kWh"): 1,
}


def runde_exportwert(value: Any, unit: str, category: Any = None) -> Any:
    """Rundet einen Sensorwert nach seiner Größenart (Einheit der Definition).

    **Jeder** Export-Weg benutzt diesen Helfer, und zwar erst an der
    Serialisierungsgrenze: MQTT-Sensoren (``mqtt_client.publish_sensor``),
    MQTT-Monatsdaten (``runde_export_payload``) und REST
    (``SensorExportItem``, das Pydantic-Modell rundet sich selbst). Die
    Rundung hängt **nicht am Produzenten** — ``calculate_anlage_sensors`` und
    ``calculate_investition_sensors`` liefern ungerundet. Vorher rundeten
    ~25 Sensorzeilen im Route-Modul vor, sodass REST eine Nachkommastelle
    zeigte, wo MQTT ganzzahlig publizierte, und der MQTT-Wert zweimal
    hintereinander gerundet wurde.

    ``category`` ist optional und hebt die Einheiten-Regel nur dort auf, wo eine
    Einheit zwei Größenordnungen trägt (s. ``NACHKOMMASTELLEN_JE_KATEGORIE``).
    Wer sie nicht mitgibt, bekommt unverändert die Regel je Einheit — deshalb
    bleibt ``runde_export_payload`` (Felder ohne Definition) unberührt.

    Nicht-numerische Werte (Monatsname, „Speicher voll um") und ganze Zahlen
    gehen unverändert durch. Ein Wert, der bei der vorgesehenen Stellenzahl auf
    0 fiele, obwohl er nicht 0 ist, bekommt so viele Stellen wie nötig
    (höchstens ``NACHKOMMASTELLEN_MAX``) — sonst würde aus 0,35 kW eine 0.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        return value

    stellen = NACHKOMMASTELLEN_JE_EINHEIT.get(unit, NACHKOMMASTELLEN_DEFAULT)
    if category is not None:
        # `category` kommt je Weg anders an: MQTT reicht das Enum durch, REST den
        # bereits serialisierten String. Beide auf denselben Schlüssel bringen,
        # statt am Aufrufer zu normalisieren — sonst hätte der eine Weg die
        # Ausnahme und der andere nicht, und das ist genau die Drift, gegen die
        # dieser Helfer gebaut wurde.
        kat = getattr(category, "value", category)
        stellen = NACHKOMMASTELLEN_JE_KATEGORIE.get((str(kat), unit), stellen)
    gerundet = round(value, stellen)
    while gerundet == 0 and value != 0 and stellen < NACHKOMMASTELLEN_MAX:
        stellen += 1
        gerundet = round(value, stellen)
    # Ganzzahlige Größen als echte ganze Zahl ausliefern: „1234" statt „1234.0".
    return int(gerundet) if stellen == 0 else gerundet


def runde_export_payload(daten: dict, einheiten: dict[str, str] | None = None) -> dict:
    """Rundet die Werte eines Export-Payloads, der keine Sensor-Definition hat.

    Für Payloads wie die MQTT-Monatsdaten, deren Felder ihre Größenart nicht
    mitbringen: der Aufrufer gibt sie in ``einheiten`` mit — dort, wo er auch
    die Felder auswählt, damit ein neu aufgenommenes Feld die Einheit direkt
    daneben stehen hat. Ein Feld ohne Eintrag fällt bewusst auf
    ``NACHKOMMASTELLEN_DEFAULT`` (2) zurück: das ist die Stellenzahl, die der
    Export bis v4.0.6 für **alles** benutzt hat, also nie gröber als vorher.

    Struktur, Feldnamen und Reihenfolge bleiben unangetastet — an dem Payload
    hängen fremde HA-Automationen.
    """
    einheiten = einheiten or {}
    return {
        schluessel: runde_exportwert(wert, einheiten.get(schluessel, ""))
        for schluessel, wert in daten.items()
    }


# =============================================================================
# SENSOR-DEFINITIONEN - Anlage (PV-Gesamt)
# =============================================================================
ANLAGE_SENSOREN = [
    SensorDefinition(
        key="pv_erzeugung_gesamt_kwh",
        name="PV Erzeugung Gesamt",
        unit="kWh",
        icon="mdi:solar-power",
        category=SensorCategory.ENERGIE,
        formel="Σ PV-Erzeugung aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="direktverbrauch_gesamt_kwh",
        name="Direktverbrauch Gesamt",
        unit="kWh",
        icon="mdi:lightning-bolt",
        category=SensorCategory.ENERGIE,
        formel="Σ Direktverbrauch (PV direkt verbraucht ohne Speicher)",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="eigenverbrauch_gesamt_kwh",
        name="Eigenverbrauch Gesamt",
        unit="kWh",
        icon="mdi:home-lightning-bolt",
        category=SensorCategory.ENERGIE,
        formel="Σ Eigenverbrauch aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="einspeisung_gesamt_kwh",
        name="Einspeisung Gesamt",
        unit="kWh",
        icon="mdi:transmission-tower-export",
        category=SensorCategory.ENERGIE,
        formel="Σ Einspeisung aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="netzbezug_gesamt_kwh",
        name="Netzbezug Gesamt",
        unit="kWh",
        icon="mdi:transmission-tower-import",
        category=SensorCategory.ENERGIE,
        formel="Σ Netzbezug aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="gesamtverbrauch_kwh",
        name="Gesamtverbrauch",
        unit="kWh",
        icon="mdi:home-lightning-bolt-outline",
        category=SensorCategory.ENERGIE,
        formel="Eigenverbrauch + Netzbezug",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="autarkie_prozent",
        name="Autarkie",
        unit="%",
        icon="mdi:home-battery",
        category=SensorCategory.QUOTE,
        formel="Eigenverbrauch ÷ Gesamtverbrauch × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eigenverbrauch_quote_prozent",
        name="Eigenverbrauchsquote",
        unit="%",
        icon="mdi:percent",
        category=SensorCategory.QUOTE,
        formel="Eigenverbrauch ÷ PV-Erzeugung × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="spezifischer_ertrag_kwh_kwp",
        name="Spezifischer Ertrag",
        unit="kWh/kWp",
        icon="mdi:solar-power-variant",
        category=SensorCategory.ANLAGE,
        formel="PV-Erzeugung ÷ Anlagenleistung, aufs Jahr normiert (saisonal gewichtet, wie Cockpit)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="netto_ertrag_euro",
        name="Netto-Ertrag",
        unit="€",
        icon="mdi:cash-plus",
        category=SensorCategory.FINANZEN,
        formel="Einspeiseerlös + EV-Ersparnis",
        device_class="monetary",
        state_class="total",
    ),
    SensorDefinition(
        key="einspeise_erloes_euro",
        name="Einspeiseerlös",
        unit="€",
        icon="mdi:cash-check",
        category=SensorCategory.FINANZEN,
        formel="Einspeisung × Einspeisevergütung",
        device_class="monetary",
        state_class="total",
    ),
    SensorDefinition(
        key="eigenverbrauch_ersparnis_euro",
        name="Eigenverbrauch-Ersparnis",
        unit="€",
        icon="mdi:piggy-bank",
        category=SensorCategory.FINANZEN,
        formel="Eigenverbrauch × Netzbezugspreis",
        device_class="monetary",
        state_class="total",
    ),
    SensorDefinition(
        key="co2_ersparnis_kg",
        name="CO2 Einsparung",
        unit="kg",
        icon="mdi:molecule-co2",
        category=SensorCategory.UMWELT,
        formel="PV-Eigenverbrauch + Wärmepumpe + E-Mobilität (vermiedenes CO₂)",
        state_class="total_increasing",
    ),
    # ── Grundlast (#395 Punkt 5, OB73-gif) ───────────────────────────────────
    #
    # ⛔ **„Grundlast" bezeichnet in eedc ZWEI verschiedene Zahlen** (Fund N-332,
    # gemessen 27.08.): Cockpit → Live zeigt den Median über das VERBRAUCHS-
    # PROFIL — ohne eigene Historie ist das ein BDEW-H0-Modellwert. Cockpit →
    # Monat/Jahr zeigt den Median der GEMESSENEN Nachtstunden.
    #
    # ⭐ **Der Sensor nimmt die gemessene.** Ein Modellwert, der als Sensor in
    # eine Automation läuft, ist die teuerste Sorte Zahl: er sieht aus wie eine
    # Messung und ist eine Annahme. Wer nichts gemessen hat, bekommt hier
    # nichts — nicht 0,3 kW aus dem Standardprofil.
    SensorDefinition(
        key="eedc_grundlast_kw",
        name="Grundlast",
        unit="kW",
        icon="mdi:home-lightning-bolt",
        category=SensorCategory.ENERGIE,
        formel=(
            "Median der GEMESSENEN Nacht-Stunden-Leistung (0–5 Uhr) des laufenden Monats "
            "aus dem stündlichen Energieprofil — dieselbe Formel und dieselbe Quelle wie "
            "die Kachel in Cockpit → Monat. Ohne gemessene Nachtstunden gibt es den Sensor nicht."
        ),
        device_class="power",
        state_class="measurement",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Investitionen (ROI)
# =============================================================================
INVESTITION_SENSOREN = [
    SensorDefinition(
        key="investition_gesamt_euro",
        name="Investition Gesamt",
        unit="€",
        icon="mdi:cash",
        category=SensorCategory.INVESTITION,
        formel="Σ Anschaffungskosten aller Investitionen",
        device_class="monetary",
        state_class="total",
    ),
    # ⛔ KEIN `device_class="monetary"` (F-63, sechster Fall — im Melder-Protokoll
    # nicht sichtbar, bei der Erhebung ueber alle Definitionen gefunden). HA laesst
    # fuer `monetary` ausschliesslich `state_class="total"` zu, also einen
    # aufsummierbaren Betrag. Dies hier ist keiner: `€/Jahr` ist eine RATE, und
    # `monetary` erwartet ueberdies eine ISO-Waehrung als Einheit. Der Sensor war
    # damit von HAs Langzeitstatistik ausgeschlossen — dieselbe Folge wie bei den
    # fuenf Prognose-Sensoren oben, nur mit anderer device_class und deshalb in
    # einer anderen Log-Zeile. Ohne `device_class` ist `measurement` richtig: ein
    # Momentanwert einer Jahresrate, den HA als min/mean/max fuehren darf.
    SensorDefinition(
        key="jahres_ersparnis_euro",
        name="Jahresersparnis",
        unit="€/Jahr",
        icon="mdi:cash-refund",
        category=SensorCategory.INVESTITION,
        formel="Σ Jährliche Einsparungen",
        state_class="measurement",
    ),
    SensorDefinition(
        key="roi_prozent",
        name="ROI",
        unit="%",
        icon="mdi:chart-line",
        category=SensorCategory.INVESTITION,
        formel="Jahresersparnis ÷ Investition × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="amortisation_jahre",
        name="Amortisation",
        unit="Jahre",
        icon="mdi:calendar-clock",
        category=SensorCategory.INVESTITION,
        formel="Investition ÷ Jahresersparnis",
        state_class="measurement",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - E-Auto
# =============================================================================
E_AUTO_SENSOREN = [
    SensorDefinition(
        key="e_auto_km_gesamt",
        name="Gefahrene km",
        unit="km",
        icon="mdi:car-electric",
        category=SensorCategory.E_AUTO,
        formel="Σ Gefahrene Kilometer",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="e_auto_verbrauch_kwh_100km",
        name="Verbrauch",
        unit="kWh/100km",
        icon="mdi:gauge",
        category=SensorCategory.E_AUTO,
        formel="Gesamtverbrauch ÷ km × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="e_auto_pv_anteil_prozent",
        name="PV-Anteil Ladung",
        unit="%",
        icon="mdi:solar-power",
        category=SensorCategory.E_AUTO,
        formel="PV-Ladung ÷ Gesamt-Ladung × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="e_auto_ersparnis_vs_benzin_euro",
        name="Ersparnis vs Benzin",
        unit="€",
        icon="mdi:fuel",
        category=SensorCategory.E_AUTO,
        formel="Benzinkosten (alternativ) - Stromkosten",
        device_class="monetary",
        state_class="total",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Wärmepumpe
# =============================================================================
WAERMEPUMPE_SENSOREN = [
    SensorDefinition(
        key="wp_betriebsmodus",
        name="Betriebsmodus",
        unit="",
        icon="mdi:hvac",
        category=SensorCategory.WAERMEPUMPE,
        formel=(
            "Aktueller Betriebsmodus laut zugeordneter climate-Quelle, über den Kanon "
            "normalisiert (Heizen · Warmwasser · Kühlen · Entfeuchten · Lüften · "
            "Aus · Unbestimmt); "
            "hvac_action verfeinert ihn, wo das Gerät sie liefert: Nennt sie eine "
            "Richtung (Heizen/Kühlen/Entfeuchten/Lüften) oder Aus, gilt sie; "
            "Leerlauf (idle) behält den eingestellten Modus, weil ein taktendes "
            "Gerät seine Betriebsart nicht verliert. "
            "Ohne zugeordnete Quelle gibt es den Sensor nicht."
        ),
    ),
    SensorDefinition(
        key="wp_cop_durchschnitt",
        name="COP Durchschnitt",
        unit="",
        icon="mdi:heat-pump",
        category=SensorCategory.WAERMEPUMPE,
        formel="Wärmeenergie ÷ Stromverbrauch",
        state_class="measurement",
    ),
    SensorDefinition(
        key="wp_ersparnis_euro",
        name="WP Ersparnis",
        unit="€",
        icon="mdi:cash-plus",
        category=SensorCategory.WAERMEPUMPE,
        formel="Kosten alte Heizung - WP-Kosten",
        device_class="monetary",
        state_class="total",
    ),
    # #263 K-2 (S4): der Modus-Split. **Teilmengen** von `stromverbrauch_kwh` —
    # wer sie in HA addiert, zählt doppelt. Sie erscheinen nur, wenn eedc den
    # Betriebsmodus mitgeschrieben hat; ohne ihn fehlen die Sensoren, statt 0
    # zu melden (eine 0 hieße „hat nicht geheizt", s. ADR-002/P4).
    SensorDefinition(
        key="wp_strom_heizen_modus_kwh",
        name="Strom Heizbetrieb",
        unit="kWh",
        icon="mdi:fire",
        category=SensorCategory.WAERMEPUMPE,
        formel="Σ Stunden im Heizbetrieb × Stromverbrauch (Teilmenge des Gesamtstroms)",
        device_class="energy",
        state_class="total",
    ),
    # N-336 (27.08.): Warmwasser ist die dritte Betriebsart, die eedc aus dem
    # Modus ableiten kann. ⚠ **Nicht zu verwechseln mit `strom_warmwasser_kwh`**
    # aus der getrennten Strommessung: das ist ein SUMMAND (Heizen + Warmwasser
    # = Gesamt), dieser Sensor eine TEILMENGE. Wer beide addiert, zählt doppelt
    # — der Satz gilt für die ganze Gruppe hier und steht deshalb oben.
    SensorDefinition(
        key="wp_strom_warmwasser_modus_kwh",
        name="Strom Warmwasserbetrieb",
        unit="kWh",
        icon="mdi:water-boiler",
        category=SensorCategory.WAERMEPUMPE,
        formel="Σ Stunden im Warmwasserbetrieb × Stromverbrauch (Teilmenge des Gesamtstroms)",
        device_class="energy",
        state_class="total",
    ),
    SensorDefinition(
        key="wp_strom_kuehlen_modus_kwh",
        name="Strom Kühlbetrieb",
        unit="kWh",
        icon="mdi:snowflake",
        category=SensorCategory.WAERMEPUMPE,
        formel="Σ Stunden im Kühlbetrieb × Stromverbrauch (Teilmenge des Gesamtstroms)",
        device_class="energy",
        state_class="total",
    ),
    # Issue #238: Counter-KPIs (nur wenn der jeweilige Zähler gemappt ist).
    SensorDefinition(
        key="wp_kompressor_starts",
        name="Kompressor-Starts",
        unit="",
        icon="mdi:restart",
        category=SensorCategory.WAERMEPUMPE,
        formel="Σ erfasste Kompressor-Starts (Laufzeit der WP)",
        state_class="total",
    ),
    SensorDefinition(
        key="wp_betriebsstunden",
        name="Betriebsstunden",
        unit="h",
        icon="mdi:clock-outline",
        category=SensorCategory.WAERMEPUMPE,
        formel="Σ erfasste Betriebsstunden (Laufzeit der WP)",
        device_class="duration",
        state_class="total",
    ),
    # ── S2/S3 „eedc@ha, Teil 1" (21.09.2026): Entscheidung + Plan je WP ─────
    #
    # ⚠ **Die Achse entscheidet, nicht die Bauart** (ADR-002/P13, Wärme/Klima
    # R1). Ob ein Gerät ein Warmwasser-, Heiz- oder Kühlfenster bekommt, hängt
    # daran, ob diese Achse am **Zähler** liegt bzw. gepflegt ist — nie daran,
    # ob es eine Luft-Luft- oder Luft-Wasser-Wärmepumpe ist.
    SensorDefinition(
        key="wp_warmwasserbetrieb",
        seit_paket=1,
        name="Warmwasserbetrieb",
        unit="",
        icon="mdi:water-boiler",
        category=SensorCategory.WAERMEPUMPE,
        formel="AN, wenn der mitgeschriebene Betriebsmodus der letzten vollen Stunde 'warmwasser' war",
        device_class="running",
        komponente="binary_sensor",
    ),
    SensorDefinition(
        key="wp_warmwasser_fenster_ab",
        seit_paket=1,
        name="Warmwasser-Fenster ab",
        unit="",
        icon="mdi:water-thermometer",
        category=SensorCategory.WAERMEPUMPE,
        # ⚠ Deckt auch den **in der WP verbauten Heizstab** (Fall H-B des
        # Wärme/Klima-Konzepts, §5.7): sein Strom läuft über denselben Zähler.
        # Ein Heizstab ist keine eedc-Größe, sein Zähler ist eine.
        formel="Beginn des günstigsten 2-Stunden-Fensters heute für den Ø-Warmwasserstrom; Menge, Kosten und Herkunft (gemessen/abgeleitet) als Attribut",
        device_class="timestamp",
    ),
    SensorDefinition(
        key="wp_heizfenster_stunden",
        seit_paket=1,
        name="Günstige Heizstunden heute",
        unit="h",
        icon="mdi:radiator",
        category=SensorCategory.WAERMEPUMPE,
        # ⚠ **Was eedc hier NICHT kennt und nicht erfindet:** Heizkurve,
        # Vorlauftemperatur, Speichervermögen des Gebäudes. Wie weit eine
        # Anhebung trägt, entscheidet die Regelung der Wärmepumpe — eedc nennt
        # Fenster und Preisvorteil, nicht die Gradzahl.
        formel="Anzahl der Stunden innerhalb der erwarteten Heizzeit, in die sich das Heizprofil günstiger verschieben ließe; erwartetes Heizstrom-Stundenprofil als Attribut",
        # Bewusst ohne `device_class: duration`: das ist keine gelaufene Zeit,
        # sondern eine Anzahl von Stunden-Slots. HA würde sie sonst mit den
        # Betriebsstunden darüber in eine Reihe stellen.
        state_class="measurement",
    ),
    SensorDefinition(
        key="wp_kuehlfenster_ab",
        seit_paket=1,
        name="Kühlfenster ab",
        unit="",
        icon="mdi:snowflake-melt",
        category=SensorCategory.WAERMEPUMPE,
        # ⚠ Kühlen bleibt **keine Wärme-Achse** (Wärme/Klima R1) — das hier ist
        # Strom-Timing, keine Kennzahl. Zwei Kriterien, beide nötig: Kühlstrom
        # am Zähler UND gepflegte `leistung_kuehlen_w`.
        formel="Beginn des Überschuss-Fensters vor der Stunde der Tageshöchsttemperatur (Vorkühlen); Frist und Überschussmenge als Attribut",
        device_class="timestamp",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Speicher
# =============================================================================
SPEICHER_SENSOREN = [
    SensorDefinition(
        key="speicher_zyklen",
        name="Vollzyklen",
        unit="",
        icon="mdi:battery-sync",
        category=SensorCategory.SPEICHER,
        formel="Entladung ÷ Kapazität",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="speicher_effizienz_prozent",
        name="Speicher-Effizienz",
        unit="%",
        icon="mdi:battery-check",
        category=SensorCategory.SPEICHER,
        formel="Entladung ÷ Ladung × 100",
        state_class="measurement",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Letzter Import (Status)
# =============================================================================
LETZTER_IMPORT_SENSOREN = [
    SensorDefinition(
        key="letzter_import_jahr",
        name="Letzter Import - Jahr",
        unit="",
        icon="mdi:calendar",
        category=SensorCategory.STATUS,
        formel="Jahr des zuletzt erfassten Monats",
        state_class="measurement",
        entity_category="diagnostic",
    ),
    SensorDefinition(
        key="letzter_import_monat",
        name="Letzter Import - Monat",
        unit="",
        icon="mdi:calendar-month",
        category=SensorCategory.STATUS,
        formel="Monat des zuletzt erfassten Datensatzes (1-12)",
        state_class="measurement",
        entity_category="diagnostic",
    ),
    SensorDefinition(
        key="letzter_import_monat_name",
        name="Letzter Import - Monatsname",
        unit="",
        icon="mdi:calendar-text",
        category=SensorCategory.STATUS,
        formel="Monatsname (z.B. 'Dezember 2025')",
        entity_category="diagnostic",
    ),
    SensorDefinition(
        key="anzahl_monate_erfasst",
        name="Erfasste Monate",
        unit="",
        icon="mdi:counter",
        category=SensorCategory.STATUS,
        formel="Anzahl der erfassten Monatsdaten",
        state_class="total",
        entity_category="diagnostic",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - PV-Prognose (eedc-eigen, Vorausschau) — Issue #150 A
# =============================================================================
# Anlage-weite Werte (kein investition_id) → gruppieren automatisch unter dem
# Anlage-Device. Stundenprofile reisen als Sensor-Attribut mit (HA historisiert
# Attribute nicht — kein 24-Topic-Spam).
#
# ⛔ KEIN `device_class` bei den Prognose-Sensoren (F-63, rapahl-PN 24.08.2026).
# Sie tragen kWh und sahen deshalb nach `device_class="energy"` aus — aber HA
# erlaubt fuer `energy` nur `state_class` `total`/`total_increasing`, weil es
# einen ZAEHLER erwartet. Eine Tagesprognose ist keiner: sie springt jeden Tag
# zurueck und darf nicht aufsummiert werden. Die Kombination `energy` +
# `measurement` hat HA nicht nur protokolliert, sondern die fuenf Sensoren von
# der Langzeitstatistik AUSGESCHLOSSEN — sie zeigten einen Wert und merkten sich
# nichts. Ohne `device_class` ist `measurement` zulaessig, HA schreibt min/mean/max,
# und die Einheit steht ohnehin in `unit`. `state_class="total"` waere die falsche
# Alternative gewesen: im Energie-Dashboard ergaebe die Summe von Prognosen Unsinn.
# Der Kanon stand schon im eigenen Code — `eedc_prognose_heute_rollend_kwh` (unten,
# neu mit v4.0.27) hat nie ein `device_class` getragen und wurde als einziger der
# sechs nie beanstandet. Gewaechtert: `tests/test_ha_export_sensor_klassen_vertrag.py`.
PROGNOSE_SENSOREN = [
    SensorDefinition(
        key="eedc_prognose_heute_kwh",
        name="PV-Prognose heute",
        unit="kWh",
        icon="mdi:solar-power",
        category=SensorCategory.PROGNOSE,
        formel="Kanonische eedc-Tagesprognose (OpenMeteo × Korrekturprofil-Kaskade), == App-Anzeige; Stundenprofil als Attribut",
        state_class="measurement",
    ),
    # rapahl-PN 2026-08-23: der nachgeführte Tageswert. „PV-Prognose heute"
    # summiert alle 24 VORHERGESAGTEN Stunden — auch die vergangenen, für die
    # längst Messwerte vorliegen; er folgt damit OpenMeteo, nicht der Realität.
    # Dieser hier folgt der Realität: was heute schon erzeugt wurde plus die
    # Prognose der Reststunden. Beide bleiben nebeneinander stehen, weil sie
    # verschiedene Fragen beantworten.
    SensorDefinition(
        key="eedc_prognose_heute_rollend_kwh",
        name="PV-Prognose heute (nachgeführt)",
        unit="kWh",
        icon="mdi:sun-clock",
        category=SensorCategory.PROGNOSE,
        formel="Heute bereits erzeugt + eedc-Prognose der verbleibenden Stunden — folgt dem IST, anders als die reine Tagesprognose",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_rest_today_kwh",
        name="PV-Prognose Rest heute",
        unit="kWh",
        icon="mdi:solar-power",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Prognose der verbleibenden Stunden heute, laufende Stunde anteilig nach Restminuten (OpenMeteo × Korrekturprofil-Kaskade)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_day_plus_1_kwh",
        name="PV-Prognose morgen",
        unit="kWh",
        icon="mdi:solar-power",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Tagesprognose morgen = Σ korrigierte Stunden-Slots (OpenMeteo × Korrekturprofil-Kaskade); Stundenprofil als Attribut",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_day_plus_2_kwh",
        name="PV-Prognose übermorgen",
        unit="kWh",
        icon="mdi:solar-power",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Tagesprognose übermorgen = Σ korrigierte Stunden-Slots (OpenMeteo × Korrekturprofil-Kaskade); Stundenprofil als Attribut",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_day_plus_3_kwh",
        name="PV-Prognose in 3 Tagen",
        unit="kWh",
        icon="mdi:solar-power",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Tagesprognose Tag+3 = Σ korrigierte Stunden-Slots (OpenMeteo × Korrekturprofil-Kaskade); Stundenprofil als Attribut",
        state_class="measurement",
    ),
    # ── Vormittag/Nachmittag (#395 Punkt 3, OB73-gif) ────────────────────────
    #
    # Für netzdienliches Laden: „warte ich auf den Nachmittags-Peak oder lade
    # ich früher voll?" — und **abends** dieselbe Frage für morgen. Deshalb vier
    # Sensoren statt zwei: die Abendentscheidung betrifft den Folgetag, und für
    # die ist „heute Nachmittag" zu spät.
    #
    # ⚠ **Der Schnitt liegt am Solar Noon**, wie in jeder eedc-Anzeige — nicht
    # bei 13:00 (Fund N-331). Die Grenze reist als Attribut `solar_noon` mit,
    # damit eine Automation sie lesen statt raten kann.
    SensorDefinition(
        key="eedc_prognose_heute_vormittag_kwh",
        name="PV-Prognose heute Vormittag",
        unit="kWh",
        icon="mdi:weather-sunset-up",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Prognose heute bis Solar Noon (Σ korrigierte Slots vor der astronomischen Tagesmitte; Grenze im Attribut solar_noon)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_heute_nachmittag_kwh",
        name="PV-Prognose heute Nachmittag",
        unit="kWh",
        icon="mdi:weather-sunset-down",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Prognose heute ab Solar Noon (Σ korrigierte Slots nach der astronomischen Tagesmitte; Grenze im Attribut solar_noon)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_morgen_vormittag_kwh",
        name="PV-Prognose morgen Vormittag",
        unit="kWh",
        icon="mdi:weather-sunset-up",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Prognose morgen bis Solar Noon — die Zahl für die Abendentscheidung (Grenze im Attribut solar_noon)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_morgen_nachmittag_kwh",
        name="PV-Prognose morgen Nachmittag",
        unit="kWh",
        icon="mdi:weather-sunset-down",
        category=SensorCategory.PROGNOSE,
        formel="eedc-Prognose morgen ab Solar Noon — die Zahl für die Abendentscheidung (Grenze im Attribut solar_noon)",
        state_class="measurement",
    ),
    # ── Verbrauchsprognose heute (#395 zweite Runde, OB73-gif) ──────────────
    #
    # Dieselbe Zahl wie die Kachel „Verbrauchsprognose" unter *Heute* in
    # Cockpit → Live: Σ des stündlichen Verbrauchsprofils, bei Wärmepumpe mit
    # der Temperaturkorrektur aus dem Forecast. **Gesamt**verbrauch (Haus +
    # Batterie + WP + Wallbox + Sonstige) — eine Haushalts-Prognose gibt es in
    # eedc nicht, und ein Sensor darf keine Zahl tragen, die nirgends angezeigt
    # wird. SoT: `services/verbrauchsprognose_heute.py`.
    #
    # ⛔ Nur aus einem INDIVIDUELLEN Profil — dieselbe Regel wie beim
    # Grundlast-Sensor (N-332): ein BDEW-Modellwert sähe in einer Automation
    # aus wie eine Messung. Ohne eigene Historie entsteht kein Sensor.
    # Kein `device_class` (F-63): eine Tagesprognose ist kein Zähler.
    SensorDefinition(
        key="eedc_verbrauchsprognose_heute_kwh",
        name="Verbrauchsprognose heute",
        unit="kWh",
        icon="mdi:home-clock-outline",
        category=SensorCategory.PROGNOSE,
        formel=(
            "Σ des individuellen Stunden-Verbrauchsprofils für heute (Werktag/Wochenende "
            "aus der eigenen Historie, Wärmepumpen-Anteil temperaturkorrigiert) — "
            "Gesamtverbrauch, dieselbe Zahl wie die Kachel in Cockpit → Live. "
            "Ohne eigenes Profil gibt es den Sensor nicht."
        ),
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_speicher_voll_um",
        name="Speicher voll um",
        unit="",
        icon="mdi:battery-clock",
        category=SensorCategory.PROGNOSE,
        formel=(
            "SoC-Simulation ab aktuellem Speicherstand: Uhrzeit, zu der der Speicher voll ist. "
            "Verbrauchsannahme = gewichtetes 8-Wochen-Profil (Attribute profil_typ, profil_stufe, "
            "profil_tage, verbrauch_annahme_kwh) — ein anderes Modell als "
            "eedc_verbrauchsprognose_heute_kwh."
        ),
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Börsenpreis-Trigger (dynamische Tarife) — Issue #150 B
# =============================================================================
PREIS_SENSOREN = [
    SensorDefinition(
        key="eedc_preis_rang",
        name="Börsenpreis-Rang",
        unit="",
        icon="mdi:sort-numeric-ascending",
        category=SensorCategory.PREIS,
        formel="Rang der aktuellen Stunde je Tag-/Nacht-Fenster (1=billigste … 5, 99=teuer/Rest); günstig nur unter der Günstig-Schwelle (Standard 10 % unter Ø ohne 3 Peaks, je Anlage einstellbar)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_preis_guenstige_stunden_anzahl",
        name="Günstige Stunden",
        unit="",
        icon="mdi:counter",
        category=SensorCategory.PREIS,
        formel="Anzahl Stunden heute unter der Günstig-Schwelle (je Anlage einstellbar) — ungekappt",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_preis_guenstige_stunden_tag",
        name="Günstige Stunden Tag",
        unit="",
        icon="mdi:weather-sunny",
        category=SensorCategory.PREIS,
        formel="Stunden unter der Günstig-Schwelle im Tag-Fenster (Sonnenauf→-untergang)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_preis_guenstige_stunden_nacht",
        name="Günstige Stunden Nacht",
        unit="",
        icon="mdi:weather-night",
        category=SensorCategory.PREIS,
        formel="Stunden unter der Günstig-Schwelle im Nacht-Fenster",
        state_class="measurement",
    ),
    # Die drei Werte, aus denen jede eigene Preis-Regel gebaut werden kann
    # (#335, rapahl-PN 2026-08-05). Bis v4.0.9 lieferte der Export nur die
    # fertige Zerlegung — weder der Preis der laufenden Stunde noch die
    # Bezugsgröße der Schwelle verließen eedc, und „liegt der Preis über oder
    # unter dem optimierten Ø?" war damit nicht beantwortbar.
    SensorDefinition(
        key="eedc_preis_aktuell_cent",
        name="Börsenpreis aktuell",
        unit="ct/kWh",
        icon="mdi:cash-clock",
        category=SensorCategory.PREIS,
        formel="Day-Ahead-Börsenpreis der laufenden Stunde",
        state_class="measurement",
    ),
    # rapahl-PN 2026-08-23: der schlichte Tages-Ø. Er stand weder im
    # Kennzahlenblock noch als Sensor, obwohl gleich drei Größen daneben auf den
    # Ø *ohne* die Peaks zeigen. Bewusst VOR dem optimierten Ø — allgemein
    # lesbare Zahl zuerst, dieselbe Ordnung wie in der Oberfläche.
    SensorDefinition(
        key="eedc_preis_tages_durchschnitt_cent",
        name="Börsenpreis Ø heute",
        unit="ct/kWh",
        icon="mdi:chart-line-variant",
        category=SensorCategory.PREIS,
        formel="Ø ALLER heutigen Börsenpreis-Stunden — ohne jeden Ausschluss; NICHT die Bezugsgröße der Günstig-Schwelle",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_preis_optimierter_durchschnitt_cent",
        name="Börsenpreis Ø ohne Peaks",
        unit="ct/kWh",
        icon="mdi:chart-line-variant",
        category=SensorCategory.PREIS,
        formel="Ø der heutigen Börsenpreise ohne die 3 teuersten Stunden — die Bezugsgröße der Günstig-Schwelle",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_preis_abstand_prozent",
        name="Börsenpreis-Abstand zum Ø",
        unit="%",
        icon="mdi:swap-vertical",
        category=SensorCategory.PREIS,
        formel="(Preis der laufenden Stunde − Ø ohne Peaks) ÷ |Ø| × 100 — negativ = billiger als der Ø",
        state_class="measurement",
    ),
    # N-173 (rapahl-PN 2026-08-11): derselbe Abstand als Betrag. Wer einen
    # dynamischen Tarif mit festen Bestandteilen zahlt, findet in der Prozent-
    # zahl keine übertragbare Größe — ein Aufschlag verschiebt Preis UND Ø um
    # denselben Betrag, die Differenz bleibt gleich, der Prozentwert nicht
    # (an seinen Zahlen: −9,93 ct auf beiden Kurven gegen −100,1 % vs. −33,2 %).
    # Der Prozent-Sensor bleibt unverändert daneben — er ist ausgeliefert.
    SensorDefinition(
        key="eedc_preis_abstand_cent",
        name="Börsenpreis-Abstand zum Ø (ct)",
        unit="ct/kWh",
        icon="mdi:swap-vertical-variant",
        category=SensorCategory.PREIS,
        formel="Preis der laufenden Stunde − Ø ohne Peaks — negativ = billiger; gegen feste Preisbestandteile unempfindlich",
        state_class="measurement",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Steuerungshilfen (Stufe 2 + 3, KONZEPT-EEDC-AT-HA §5)
# =============================================================================
# ⭐ **Wofuer diese Gruppe da ist.** Ein steuerungsfaehiges HA-Dashboard braucht
# drei Sorten Zahl: *was ist* (Stufe 1 — die 57 Sensoren darueber), *was gilt
# jetzt* (Stufe 2 — Ueberschuss, guenstige Stunde, Speicher voll) und *wann es
# gilt* (Stufe 3 — Fenster mit Betrag). Die ersten beiden Stufen liegen in eedc
# laengst als Groesse vor und wurden nur nie exportiert; die dritte ist eine
# Ableitung aus vorhandenen Stundenreihen.
#
# ⛔ **Vorschlag, kein Urteil.** Kein Name hier sagt „lade jetzt" oder „Anlage
# defekt". Sie nennen ein Fenster und einen Betrag; was daraus folgt, entscheidet
# die Automation des Anwenders — eedc ist nicht die Strom-Polizei. Deshalb heisst
# die Ampel „Prognose-Abweichung auffaellig" und nicht „Anlage defekt".
#
# ⚠ **Zwei Verbrauchsmodelle stehen nebeneinander** (N-392, entschieden 18.09.):
# alles hier rechnet mit dem 7-Tage-Profil der Live-Kachel (**Modell A**), nur
# der Arbitrage-Vorschlag mit dem 8-Wochen-Profil der Speicher-Simulation
# (**Modell B**) — weil er auf derselben Simulation sitzt wie
# `eedc_speicher_voll_um`. Jeder betroffene Sensor nennt sein Modell im Attribut
# `profil_typ`; zusammengefuehrt wird hier nichts.
STEUERUNG_SENSOREN = [
    # ── E1 · Ueberschuss ────────────────────────────────────────────────────
    SensorDefinition(
        key="eedc_ueberschuss_heute_kwh",
        seit_paket=1,
        name="Überschuss heute",
        unit="kWh",
        icon="mdi:solar-power-variant",
        category=SensorCategory.STEUERUNG,
        formel="Σ max(0; Erzeugung − Verbrauch) heute bis jetzt (15-Minuten-Takt); Defizit als Attribut",
        device_class="energy",
        # ⚠ `total` und nicht `measurement`: das IST ein Zaehler, er faengt nur
        # jede Nacht bei 0 an. HA kennt genau dafuer `total` (ein Rueckfall auf
        # 0 ist erlaubt). Die Prognose-Sensoren daneben tragen bewusst KEIN
        # device_class — sie sind kein Zaehler, sondern eine Vorhersage, und
        # ihre Summe ueber Tage ergaebe Unsinn. Der Unterschied ist nicht die
        # Einheit, sondern ob die Zahl etwas Gemessenes fortschreibt.
        state_class="total",
    ),
    SensorDefinition(
        key="eedc_ueberschuss_jetzt_kw",
        seit_paket=1,
        name="Überschuss letzte Stunde",
        unit="kW",
        icon="mdi:flash",
        category=SensorCategory.STEUERUNG,
        formel="Überschuss der letzten vollständigen Stundenzeile (Stundenmittel); negativ = Defizit",
        device_class="power",
        state_class="measurement",
    ),
    # ── E2 · die vier binary_sensor (anlagenweit; der fuenfte haengt an der WP) ──
    SensorDefinition(
        key="eedc_ueberschuss_verfuegbar",
        seit_paket=1,
        name="Überschuss verfügbar",
        unit="",
        icon="mdi:solar-power",
        category=SensorCategory.STEUERUNG,
        formel="AN, wenn der Überschuss der letzten vollen Stunde über 0 liegt",
        device_class="power",
        komponente="binary_sensor",
    ),
    SensorDefinition(
        key="eedc_guenstige_stunde",
        seit_paket=1,
        name="Günstige Stunde",
        unit="",
        icon="mdi:cash-clock",
        category=SensorCategory.STEUERUNG,
        formel="AN, wenn die laufende Stunde unter der Günstig-Schwelle liegt (dieselbe Markierung wie der Börsenpreis-Rang)",
        komponente="binary_sensor",
    ),
    SensorDefinition(
        key="eedc_speicher_voll",
        seit_paket=1,
        name="Speicher voll",
        unit="",
        icon="mdi:battery-high",
        category=SensorCategory.STEUERUNG,
        # ⚠ Bewusst OHNE `device_class`: HAs `battery_charging` hiesse „laedt",
        # und `battery` am binary_sensor hiesse „Batterie schwach" — beides das
        # Gegenteil dessen, was hier steht.
        formel="AN, wenn der kapazitätsgewichtete Ladestand der Anlage bei 99 % oder darüber liegt",
        komponente="binary_sensor",
    ),
    # ── E3 · derselbe Zeitpunkt als echter Zeitstempel ──────────────────────
    SensorDefinition(
        key="eedc_speicher_voll_um_ts",
        seit_paket=1,
        name="Speicher voll um (Zeitstempel)",
        unit="",
        icon="mdi:battery-clock",
        category=SensorCategory.STEUERUNG,
        # ⛔ **Warum ein zweiter Sensor und kein Umbau des bestehenden**
        # (Entscheid Gernot 21.09.): `eedc_speicher_voll_um` traegt seit v4.0.27
        # den Text „14:00" und ist oeffentlicher Vertrag. `device_class:
        # timestamp` verlangt ISO-8601 mit Zone — der Umbau braeche jede
        # Automation, die den Text vergleicht. Zwei Sensoren auf derselben
        # Simulation kosten ein Attribut `quelle`; ein gebrochener Vertrag
        # kostet den Anwender seine Automation.
        formel="Derselbe Zeitpunkt wie der Textsensor 'Speicher voll um' — als ISO-8601-Zeitstempel, damit HA 'in 2 h' anzeigen kann",
        device_class="timestamp",
    ),
    # ── E4 · Ladestand ──────────────────────────────────────────────────────
    SensorDefinition(
        key="eedc_speicher_soc_prozent",
        seit_paket=1,
        name="Ladestand",
        unit="%",
        icon="mdi:battery-70",
        category=SensorCategory.STEUERUNG,
        formel="Kapazitätsgewichteter Ladestand aller Speicher der Anlage; Aufschlüsselung je Speicher als Attribut",
        device_class="battery",
        state_class="measurement",
    ),
    # ── E5 · Netzbezugs-Spitze ──────────────────────────────────────────────
    SensorDefinition(
        key="eedc_netzbezug_spitze_heute_kw",
        seit_paket=1,
        name="Netzbezugs-Spitze heute",
        unit="kW",
        icon="mdi:transmission-tower-import",
        category=SensorCategory.STEUERUNG,
        # ⚠ **Zwei verschiedene Groessen, und der Sensor traegt die eine.** Der
        # Wert ist die hoechste gemessene LEISTUNG des Tages; das Attribut
        # `stunde_max_mittel` nennt die Stunde mit dem hoechsten
        # Stunden-MITTEL. Das ist nicht dieselbe Stunde und heisst deshalb
        # nicht „Stunde der Spitze" — eine Uhrzeit zum W-Peak gibt es in eedc
        # nicht (gemessen 21.09.2026).
        formel="Höchste gemessene Netzbezugs-Leistung heute; die Stunde mit dem höchsten Stundenmittel als Attribut",
        device_class="power",
        state_class="measurement",
    ),
    # ── P2 · Ueberschuss-Prognose ───────────────────────────────────────────
    SensorDefinition(
        key="eedc_ueberschuss_prognose_heute_kwh",
        seit_paket=1,
        name="Überschuss-Prognose heute",
        unit="kWh",
        icon="mdi:chart-areaspline",
        category=SensorCategory.STEUERUNG,
        # ⭐ **Die Groesse, die sonst niemand bilden kann.** evcc kennt das Auto
        # und vielleicht eine PV-Prognose, aber nicht den Verbrauchsgang DIESES
        # Hauses mit Waermepumpen-Korrektur. Der Ueberschuss ist die Differenz
        # der beiden — und sie kostet keine neue Rechnung, nur einen Export.
        formel="Σ max(0; PV-Prognose − Verbrauchsprognose) je Stunde heute; Stundenreihen und Überschuss-Blöcke als Attribut",
        # Eine Prognose ist kein Zaehler (F-63-Begruendung der PROGNOSE-Gruppe)
        # — deshalb hier KEIN device_class und `measurement`.
        state_class="measurement",
    ),
    # ── P3 · Arbitrage ──────────────────────────────────────────────────────
    SensorDefinition(
        key="eedc_arbitrage_vorschlag_kwh",
        seit_paket=1,
        name="Arbitrage-Vorschlag",
        unit="kWh",
        icon="mdi:swap-vertical-bold",
        category=SensorCategory.STEUERUNG,
        # ⚠ Ein Vorschlag ist keine gemessene Menge und auch keine Prognose —
        # deshalb weder device_class noch state_class. Er entsteht nur, wenn
        # sich etwas lohnt; sonst gibt es ihn nicht (ADR-002/P4).
        formel="Empfohlene Netzladung heute — laden in günstigen Stunden, entladen gegen das teuerste Defizit danach; Ersparnis als Attribut",
    ),
    # ── P5 · bestes Fenster ─────────────────────────────────────────────────
    SensorDefinition(
        key="eedc_bestes_fenster_ab",
        seit_paket=1,
        name="Bestes Fenster ab",
        unit="",
        icon="mdi:calendar-clock",
        category=SensorCategory.STEUERUNG,
        # ⭐ **Warum vier feste Dauern und keine Mengen-Eingabe** (Fachentscheid,
        # abgenommen 21.09.): ein Sensor kann keinen Parameter entgegennehmen —
        # eine HA-Karte liest Zustaende, sie ruft keine Services (§2, HACS
        # bleibt draussen). Das Kostenprofil je kWh ist mengenneutral, die vier
        # Dauern 1/2/3/4 h decken „jetzt oder um 14 Uhr" fuer Waschmaschine,
        # Trockner, Spuelmaschine und Auto.
        formel="Beginn des günstigsten 2-Stunden-Fensters ab jetzt; die Dauern 1/2/3/4 h und das Kostenprofil je kWh als Attribut",
        device_class="timestamp",
    ),
    # ── P6 · Abweichungs-Ampel ──────────────────────────────────────────────
    SensorDefinition(
        key="eedc_prognose_abweichung_heute_prozent",
        seit_paket=1,
        name="Prognose-Abweichung heute",
        unit="%",
        icon="mdi:chart-bell-curve",
        category=SensorCategory.STEUERUNG,
        formel="(IST bis zur letzten vollen Stunde − Prognose bis dahin) ÷ Prognose × 100 — negativ = weniger erzeugt als vorhergesagt",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_prognose_auffaellig",
        seit_paket=1,
        name="Prognose-Abweichung auffällig",
        unit="",
        icon="mdi:alert-outline",
        category=SensorCategory.STEUERUNG,
        # ⛔ **Der Name ist die Aussage.** Er sagt „die Abweichung ist
        # auffaellig", nicht „die Anlage ist defekt" — eedc sieht Verschattung,
        # Schnee, einen Sensorausfall und einen echten Defekt als dieselbe
        # Zahl. Ein Urteil waere eine Behauptung ueber eine Ursache, die eedc
        # nicht kennt.
        formel="AN, wenn die Tagesabweichung über dem Doppelten des mittleren Fehlers der letzten 30 Tage liegt — frühestens nach 3 vollen Sonnenstunden",
        device_class="problem",
        komponente="binary_sensor",
    ),

    # ── Stufe 3b · Preise und Speicher (S3b, 22.09.2026) ────────────────────
    #
    # ⚠ **ct/kWh traegt KEINE `device_class`** (F-63): HA kennt `monetary` nur
    # fuer einen Betrag, nicht fuer einen Preis je Einheit — mit `monetary`
    # wuerde HA versuchen, ct/kWh ueber die Zeit zu summieren. `measurement`
    # als `state_class` ist dagegen richtig: es ist ein Momentanwert.
    SensorDefinition(
        key="eedc_bezugspreis_jetzt_cent",
        seit_paket=1,
        name="Bezugspreis jetzt",
        unit="ct/kWh",
        icon="mdi:cash-clock",
        category=SensorCategory.STEUERUNG,
        formel=(
            "Arbeitspreis der laufenden Stunde: bei Festpreis/Zeitfenster exakt aus dem Tarif, "
            "bei dynamischem Tarif (1 + USt) × Börse + abgeleiteter Aufschlag; `preisquelle` sagt, welcher Fall"
        ),
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_einspeiseverguetung_cent",
        seit_paket=1,
        name="Einspeisevergütung",
        unit="ct/kWh",
        icon="mdi:transmission-tower-export",
        category=SensorCategory.STEUERUNG,
        formel="Vergütung je eingespeister kWh — Stammwert des Tarifs, bei variabler Vergütung der Monatswert",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_eigenverbrauch_wert_cent",
        seit_paket=1,
        name="Eigenverbrauch wert",
        unit="ct/kWh",
        icon="mdi:home-lightning-bolt",
        category=SensorCategory.STEUERUNG,
        formel="Bezugspreis − Einspeisevergütung: was eine selbst verbrauchte kWh spart (nur mit vollständigem Bezugspreis)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_speicher_strom_kosten_cent",
        seit_paket=1,
        name="Speicherstrom kostet",
        unit="ct/kWh",
        icon="mdi:battery-arrow-down",
        category=SensorCategory.STEUERUNG,
        formel="Einspeisevergütung ÷ Wirkungsgrad — was eine aus dem Speicher entnommene kWh kostet (gemessener oder gepflegter η, nie der Default)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_speicher_netzladen_kosten_cent",
        seit_paket=1,
        name="Netzladen kostet",
        unit="ct/kWh",
        icon="mdi:transmission-tower-import",
        category=SensorCategory.STEUERUNG,
        formel="Bezugspreis der laufenden Stunde ÷ Wirkungsgrad — nur für Speicher, die aus dem Netz laden dürfen",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_speicher_leer_um_ts",
        seit_paket=1,
        name="Speicher leer um",
        unit="",
        icon="mdi:battery-alert-variant-outline",
        category=SensorCategory.STEUERUNG,
        formel="Ende der ersten Stunde nach jetzt, in der der Ladestand in den Leerstand übergeht — Simulation, derselbe Lauf wie bei Speicher voll um",
        device_class="timestamp",
    ),
    SensorDefinition(
        key="eedc_speicher_reicht_bis_mitternacht",
        seit_paket=1,
        name="Speicher reicht bis Mitternacht",
        unit="",
        icon="mdi:battery-clock",
        category=SensorCategory.STEUERUNG,
        formel="AN, wenn der Ladestand bis Mitternacht nicht in den Leerstand übergeht und über der Schwelle endet — dieselbe Regel, derselbe Lauf",
        komponente="binary_sensor",
    ),
    SensorDefinition(
        key="eedc_abregelung_heute_kwh",
        seit_paket=1,
        name="Abregelung heute",
        unit="kWh",
        icon="mdi:scissors-cutting",
        category=SensorCategory.STEUERUNG,
        # ⚠ **Keine `device_class`** (F-63, wie die Prognose-Sensoren): das ist
        # eine Vorhersage, kein Zaehler — ihre Summe ueber Tage ergaebe Unsinn.
        formel="Erwarteter Kappungsverlust heute an der Wechselrichter-Grenze — in der Skala der Rohprognose (vor der eedc-Korrektur)",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eedc_einspeisung_unerwuenscht",
        seit_paket=1,
        name="Einspeisung unerwünscht",
        unit="",
        icon="mdi:cash-minus",
        category=SensorCategory.STEUERUNG,
        # ⛔ **Kein Urteil, ein Marktzustand.** Der Sensor sagt nicht „schalte
        # ab", sondern „in dieser Stunde ist der Boersenpreis negativ und es
        # wird Erzeugung erwartet". Was daraus folgt, entscheidet der Anwender.
        formel="AN, wenn der Börsenpreis der laufenden Stunde negativ ist UND für dieselbe Stunde PV-Erzeugung erwartet wird (§51 EEG als Slot-Regel)",
        komponente="binary_sensor",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Sonstige Verbraucher je Geraet (Stufe 3, P9)
# =============================================================================
# ⚠ **P9 ist auch Stufe 1.** Fuer ein Geraet der Kategorie *Sonstiges/
# Verbraucher* (Pool, Sauna, Trockner, Heizstab mit eigenem Zaehler = Fall H-A
# des Waerme/Klima-Konzepts) exportierte eedc bis zum 21.09.2026 **keinen
# einzigen Energiewert** — je Geraet lieferte die INVESTITION-Gruppe hoechstens
# `investition_gesamt_euro`, die drei anderen Keys jener Gruppe sind
# anlagenweit. Erst der Geraetesensor, dann das Fenster.
SONSTIGES_SENSOREN = [
    SensorDefinition(
        key="sonstiges_verbrauch_monat_kwh",
        seit_paket=1,
        name="Verbrauch (Monat)",
        unit="kWh",
        icon="mdi:power-plug",
        category=SensorCategory.SONSTIGES,
        formel="Stromverbrauch dieses Geräts im laufenden Monat; PV-Anteil und Netzbezug als Attribut",
        device_class="energy",
        state_class="total",
    ),
    SensorDefinition(
        key="sonstiges_fenster_ab",
        seit_paket=1,
        name="Bestes Fenster ab",
        unit="",
        icon="mdi:calendar-clock",
        category=SensorCategory.SONSTIGES,
        formel="Beginn des günstigsten 2-Stunden-Fensters für den Ø-Tagesverbrauch dieses Geräts",
        device_class="timestamp",
    ),
]

# =============================================================================
# ALLE SENSOREN ZUSAMMENGEFASST
# =============================================================================
ALL_SENSOR_DEFINITIONS = {
    "anlage": ANLAGE_SENSOREN,
    "investition": INVESTITION_SENSOREN,
    "e_auto": E_AUTO_SENSOREN,
    "waermepumpe": WAERMEPUMPE_SENSOREN,
    "speicher": SPEICHER_SENSOREN,
    "status": LETZTER_IMPORT_SENSOREN,
    "prognose": PROGNOSE_SENSOREN,
    "preis": PREIS_SENSOREN,
    "steuerung": STEUERUNG_SENSOREN,
    "sonstiges": SONSTIGES_SENSOREN,
}


def get_sensor_definition(key: str) -> Optional[SensorDefinition]:
    """Findet eine Sensor-Definition anhand des Keys."""
    for category_sensors in ALL_SENSOR_DEFINITIONS.values():
        for sensor in category_sensors:
            if sensor.key == key:
                return sensor
    return None


def get_all_sensor_definitions() -> list[SensorDefinition]:
    """Gibt alle Sensor-Definitionen als flache Liste zurück."""
    result = []
    for category_sensors in ALL_SENSOR_DEFINITIONS.values():
        result.extend(category_sensors)
    return result
