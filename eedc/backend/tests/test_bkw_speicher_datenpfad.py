"""
Der BKW-Akku hat GENAU EINEN Erfassungsweg (Kanon-Entscheid Gernot, 2026-07-31).

Ein Balkonkraftwerk mit Akku (Zendure, Anker SOLIX) wird so erfasst, dass der
Akku eine **eigene Investition vom Typ `speicher` mit Parent Balkonkraftwerk**
ist — „Weg A". Nur dieser Weg trägt Live-Leistung, Ladestand, Energiefluss-Knoten
und den Tages-/Stunden-Zählerpfad; er ist im Formular seit jeher deklariert
(`investitionFormHelpers.ts`) und wird vom Backend validiert
(`ERLAUBTE_PARENT_TYPEN`).

Die BKW-eigenen Felder `speicher_ladung_kwh`/`speicher_entladung_kwh` sind der
zurückgebaute zweite Weg („Weg B"). Sie bleiben **erfassbar** — Monatsabschluss,
CSV-Import, gepflegte Werte bleiben lesbar —, sind aber **nicht mehr zuordenbar**
(`nur_manuell`, s. `core/field_definitions.py`) und haben bewusst KEINEN
Zählerpfad. Paket D (`ca40678e`) hatte sie einen halben Tag lang angeschlossen;
dieses Modul pinnt die Rücknahme, damit sie nicht als „Lücke" wiederkehrt.

Was aus D bleibt und hier weiter gepinnt wird: `eigenverbrauch_kwh` verliert
seinen falschen MQTT-Ziel-Key. Er zeigte auf `pv`, also denselben Kanal wie die
Erzeugung — ein BKW, das beide Topics publizierte, überschrieb seine eigene
Erzeugung (aus 10 kWh wurden 4). Das war ein echter Datenfehler und ist
unabhängig vom Erfassungsweg.

Hintergrund zur Falle, die es dadurch gar nicht erst gibt: `bkw_{id}` steht in
`PV_KOMPONENTEN_PREFIXE` und wird als *Erzeugung* summiert. Eine Speicher-Menge
auf diesem Key hätte eine Entladung als PV-Erzeugung gezählt und eine Ladung die
BKW-Erzeugung still gekürzt — die Klasse des BKW-Bugs vom 2026-05-19 (Rainer-PN).
Mit dem Kanon trägt ein BKW genau einen Komponenten-Key, der Akku seinen eigenen.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen.energie import (
    summe_batterie_netto_kwh,
    summe_bkw_kwh,
    summe_pv_bkw_kwh,
)
from backend.core.field_definitions import (
    get_alle_felder_fuer_investition,
    get_felder_fuer_investition,
)
from backend.models.investition import (
    ERLAUBTE_PARENT_TYPEN,
    PARENT_PFLICHT_TYPEN,
)
from backend.services.mqtt_energy_history_service import _compute_deltas
from backend.services.snapshot.keys import (
    KUMULATIVE_ZAEHLER_FELDER,
    _categorize_counter,
    _is_kumulativ_feld,
)
from backend.services.snapshot.komponenten_beitraege import (
    investition_beitraege,
    investition_hourly_eintraege,
)


BKW_ID = 7
SPEICHER_ID = 9
BKW_SPEICHER_FELDER = ("speicher_ladung_kwh", "speicher_entladung_kwh")


def _bkw(inv_id=BKW_ID, hat_speicher=True):
    return SimpleNamespace(
        id=inv_id,
        typ="balkonkraftwerk",
        parameter={"hat_speicher": hat_speicher},
        parent_investition_id=None,
    )


def _akku_am_bkw(inv_id=SPEICHER_ID, parent=BKW_ID):
    """Weg A — der Akku als eigene Speicher-Investition unter dem BKW."""
    return SimpleNamespace(
        id=inv_id, typ="speicher", parameter={}, parent_investition_id=parent,
    )


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _bkw_mapping_voll() -> dict:
    """Ein BKW, auf dessen Akku-Feldern (Altbestand) noch Sensoren liegen."""
    return {"felder": {
        "pv_erzeugung_kwh": _sensor("sensor.bkw_ertrag"),
        "speicher_ladung_kwh": _sensor("sensor.bkw_akku_geladen"),
        "speicher_entladung_kwh": _sensor("sensor.bkw_akku_entladen"),
    }}


# ─── 1. Der Kanon: Weg A ist deklariert und Pflicht-frei ────────────────────

def test_speicher_darf_an_ein_balkonkraftwerk():
    """Die SoT der Parent-Regel. Stand bis 2026-07-31 in drei uneinigen Kopien;
    nur eine kannte das Balkonkraftwerk."""
    assert "balkonkraftwerk" in ERLAUBTE_PARENT_TYPEN["speicher"]
    assert "wechselrichter" in ERLAUBTE_PARENT_TYPEN["speicher"]
    # Optional — ein Hausspeicher ohne Parent bleibt gültig.
    assert "speicher" not in PARENT_PFLICHT_TYPEN


def test_akku_am_bkw_laeuft_durch_den_speicher_pfad():
    """Weg A erbt die volle Speicher-Mechanik: eigener Komponenten-Key mit
    Batterie-Präfix, Vorzeichen Entladung + / Ladung −."""
    beitraege = investition_beitraege(
        _akku_am_bkw(),
        {"felder": {"ladung_kwh": _sensor("sensor.a"), "entladung_kwh": _sensor("sensor.b")}},
    )
    nach_feld = {b.feld: b for b in beitraege}
    assert nach_feld["ladung_kwh"].target_key == f"batterie_{SPEICHER_ID}"
    assert nach_feld["entladung_kwh"].target_key == f"batterie_{SPEICHER_ID}"
    assert nach_feld["ladung_kwh"].vorzeichen == -1
    assert nach_feld["entladung_kwh"].vorzeichen == +1


def test_bkw_und_sein_akku_trennen_erzeugung_von_batterie():
    """Gegenprobe an den Σ-Helpern: die Erzeugungs-Summe sieht ausschließlich
    das BKW, die Batterie-Summe ausschließlich den Akku darunter."""
    komponenten_kwh = {
        f"bkw_{BKW_ID}": 10.0,           # Erzeugung des Balkonkraftwerks
        f"batterie_{SPEICHER_ID}": +2.0,  # netto: 6 entladen − 4 geladen
    }
    assert summe_bkw_kwh(komponenten_kwh) == 10.0
    assert summe_pv_bkw_kwh(komponenten_kwh) == 10.0
    assert summe_batterie_netto_kwh(komponenten_kwh) == 2.0


# ─── 2. Weg B ist zurückgebaut: kein Zählerpfad ─────────────────────────────

def test_bkw_speicherfelder_haben_keinen_zaehler_pfad():
    """Rücknahme von Paket D. Mit dem Kanon wäre ein zweiter Zählerpfad für
    dasselbe Gerät die Doppelerfassung, die der Rückbau beseitigt."""
    assert KUMULATIVE_ZAEHLER_FELDER["balkonkraftwerk"] == ("pv_erzeugung_kwh",)
    for feld in BKW_SPEICHER_FELDER:
        assert feld not in KUMULATIVE_ZAEHLER_FELDER["balkonkraftwerk"]
    # Der Akku am Typ `speicher` behält seinen Pfad — dort liegt der Kanon.
    assert KUMULATIVE_ZAEHLER_FELDER["speicher"] == (
        "ladung_kwh", "entladung_kwh", "ladung_netz_kwh",
    )
    assert _is_kumulativ_feld("ladung_kwh")


def test_bkw_eigenverbrauch_bleibt_ohne_zaehler_pfad():
    """Regressions-Schutz (war auch vorher grün): das Feld ist die manuell/per
    Import gepflegte Verfeinerung, SoT-Begründung in `bkw_finanz.py`."""
    assert "eigenverbrauch_kwh" not in KUMULATIVE_ZAEHLER_FELDER["balkonkraftwerk"]
    assert not _is_kumulativ_feld("eigenverbrauch_kwh")


def test_bkw_speicherfelder_bekommen_keine_energiefluss_kategorie():
    """Ohne Zählerpfad gibt es auch nichts zu kategorisieren."""
    p = {"hat_speicher": True}
    for feld in BKW_SPEICHER_FELDER:
        assert _categorize_counter(feld, "balkonkraftwerk", p) is None
    # Die Erzeugung bleibt unberührt PV.
    assert _categorize_counter("pv_erzeugung_kwh", "balkonkraftwerk", p) == "pv"
    # Und der Akku als eigene Investition kategorisiert weiterhin korrekt.
    assert _categorize_counter("ladung_kwh", "speicher", {}) == "ladung_batterie"
    assert _categorize_counter("entladung_kwh", "speicher", {}) == "entladung_batterie"


def test_bkw_eigenverbrauch_bekommt_keine_kategorie():
    assert _categorize_counter("eigenverbrauch_kwh", "balkonkraftwerk", {}) is None


def test_bkw_traegt_genau_einen_komponenten_key():
    """Auch mit zugeordneten Akku-Sensoren (Altbestand) bleibt das BKW eine
    reine Erzeuger-Komponente. Paket D gab ihm kurzzeitig einen zweiten Key."""
    beitraege = investition_beitraege(_bkw(), _bkw_mapping_voll())
    assert [(b.feld, b.target_key, b.vorzeichen) for b in beitraege] == [
        ("pv_erzeugung_kwh", f"bkw_{BKW_ID}", +1),
    ]
    assert not any(b.target_key.startswith("batterie_") for b in beitraege)


def test_hourly_eintraege_spiegeln_den_tagespfad():
    """K3-Eigenschaft (Issue #298): der Stunden-Pfad ist eine treue Projektion
    des Tages-SoT — gleiche Feldmenge, jedes Feld mit gültiger Kategorie."""
    tages_felder = {b.feld for b in investition_beitraege(_bkw(), _bkw_mapping_voll())}
    hourly = investition_hourly_eintraege(_bkw(), _bkw_mapping_voll())
    assert {e.feld for e in hourly} == tages_felder
    assert {e.feld: e.kategorie for e in hourly} == {"pv_erzeugung_kwh": "pv"}


def test_mqtt_bkw_speicherfelder_landen_nirgends():
    """Ein Altbestands-BKW, das die Akku-Topics weiter publiziert, darf keinen
    Batterie-Key mehr erzeugen — sonst zählte derselbe Akku doppelt, sobald
    der Anwender auf Weg A migriert."""
    start = {
        f"inv/{BKW_ID}/speicher_ladung_kwh": 100.0,
        f"inv/{BKW_ID}/speicher_entladung_kwh": 80.0,
    }
    end = {
        f"inv/{BKW_ID}/speicher_ladung_kwh": 104.0,
        f"inv/{BKW_ID}/speicher_entladung_kwh": 83.5,
    }
    deltas = _compute_deltas(end, start, {str(BKW_ID): "balkonkraftwerk"})
    assert not [k for k in deltas if k.startswith("batterie_")]
    # Der Rohwert fällt unverändert durch und wird von niemandem aufgesammelt.
    assert deltas[f"inv/{BKW_ID}/speicher_ladung_kwh"] == 4.0


def test_mqtt_akku_am_bkw_landet_auf_batterie_keys():
    """Die Gegenprobe: über Weg A erfasst, kommt derselbe Akku sauber an."""
    start = {f"inv/{SPEICHER_ID}/ladung_kwh": 100.0, f"inv/{SPEICHER_ID}/entladung_kwh": 80.0}
    end = {f"inv/{SPEICHER_ID}/ladung_kwh": 104.0, f"inv/{SPEICHER_ID}/entladung_kwh": 83.5}
    deltas = _compute_deltas(end, start, {str(SPEICHER_ID): "speicher"})
    assert deltas[f"batterie_{SPEICHER_ID}_ladung"] == 4.0
    assert deltas[f"batterie_{SPEICHER_ID}_entladung"] == 3.5


def test_mqtt_eigenverbrauch_ueberschreibt_die_erzeugung_nicht():
    """Der gemessene Datenfehler aus D — die Hälfte, die BLEIBT: beide Topics
    zeigten auf `pv`, der zweite gewann. Aus 10 kWh Erzeugung wurden 4 kWh."""
    start = {
        f"inv/{BKW_ID}/pv_erzeugung_kwh": 100.0,
        f"inv/{BKW_ID}/eigenverbrauch_kwh": 40.0,
    }
    end = {
        f"inv/{BKW_ID}/pv_erzeugung_kwh": 110.0,
        f"inv/{BKW_ID}/eigenverbrauch_kwh": 44.0,
    }
    deltas = _compute_deltas(end, start, {str(BKW_ID): "balkonkraftwerk"})
    assert deltas[f"pv_{BKW_ID}"] == 10.0
    assert deltas["pv"] == 10.0
    assert deltas[f"inv/{BKW_ID}/eigenverbrauch_kwh"] == 4.0


# ─── 3. Zurückgebaut heißt NICHT gelöscht ───────────────────────────────────

def test_bkw_speicherfelder_bleiben_erfassbar():
    """Der Rückbau-Modus dieses Projekts: gepflegte Werte bleiben lesbar und
    pflegbar. Monatsabschluss und CSV-Import bieten die Felder weiter an,
    solange `hat_speicher` gesetzt ist."""
    felder = {
        f["feld"]
        for f in get_felder_fuer_investition("balkonkraftwerk", {"hat_speicher": True})
    }
    for feld in BKW_SPEICHER_FELDER:
        assert feld in felder
    # Ohne Akku bleiben sie ausgeblendet — unverändert.
    ohne = {
        f["feld"]
        for f in get_felder_fuer_investition("balkonkraftwerk", {"hat_speicher": False})
    }
    assert not (set(BKW_SPEICHER_FELDER) & ohne)


def test_bkw_speicherfelder_sind_als_nur_manuell_markiert():
    """`nur_manuell` ist das, was sie von der Zuordnungs-Fläche fernhält —
    die Fläche und die Topic-Liste lesen genau dieses Attribut."""
    felder = {
        f["feld"]: f
        for f in get_alle_felder_fuer_investition("balkonkraftwerk", {"hat_speicher": True})
    }
    for feld in BKW_SPEICHER_FELDER:
        assert felder[feld].get("nur_manuell") is True, feld
    # Erzeugung und Eigenverbrauch bleiben zuordenbar.
    assert not felder["pv_erzeugung_kwh"].get("nur_manuell")
    assert not felder["eigenverbrauch_kwh"].get("nur_manuell")


def test_nur_manuell_faellt_aus_der_eingabe_antwort():
    """Steuer-Attribut, kein Anzeige-Attribut — wie `bedingung` auch."""
    felder = get_felder_fuer_investition("balkonkraftwerk", {"hat_speicher": True})
    assert all("nur_manuell" not in f for f in felder)
