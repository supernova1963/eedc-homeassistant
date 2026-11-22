"""Spalten-Register des Diagnose-Pakets v4 (Profil «Diagnose») — Bauplan §3.2, Wächter W-7 (a)/(b)/(d).

Jede Spalte **jeder** Tabelle der MetaData trägt hier eine Klasse, oder die Tabelle steht unter ``NIE``; ``migrations`` steht
von Hand (sie hat kein Modell, DDL ``MIGRATIONS_DDL`` = ``core/database.py::_run_data_migrations``). Der Auszug liest je
Tabelle nur Spalten, die Register **und** Datenbank kennen (explizite Liste, nie ``SELECT *``).

Klassen: ``rein`` · ``raus`` (nie gelesen) · ``gerundet`` (2 Nachkommastellen, Q1) · ``bereinigt:log`` · ``bereinigt:email``
(E-Mail-Muster; bei JSON nur in Werten unter ``writer``) · ``bereinigt:struktur`` · ``allowlist`` (JSON: Oberschlüssel außerhalb
der Liste — Wahrheitswert und ``null`` bleiben, eine Zahl nur mit ``fremde_zahlen_bleiben``, sonst Marke mit Typ und Länge). ``freitext``: vom Anwender geschrieben
(zählt in «Notizen» der Inhaltsliste).

**Filterart** je Tabelle (W-7 d, «ein Paket = eine Anlage»): ``anlage`` (``anlage_id = X``; ``anlagen``: ``id = X``) ·
``ueber:<eltern>.<spalte>`` (``<spalte>`` in den ``id`` der Elternzeilen) · ``natural_key`` (``row_pk_json`` geparst) ·
``anlage_oder_null`` (``anlage_id = X`` oder ``NULL``, Q5) · ``ganz`` (nur ``migrations``).

**Blatt-Regel** je JSON-Spalte (K2): ein Text-Blatt bleibt nur unter einem Schlüssel aus ``text_schluessel`` (``"*"`` = jeder;
ein Blatt in einer Liste gehört zum Schlüssel der Liste) oder unter einem Elternschlüssel aus ``text_unter`` (für Schlüssel, die
eedc dynamisch bildet); sonst Marke. Leer = kein Text-Blatt erlaubt.

Importe nur stdlib + ``backend.core.investition_parameter`` (das Werkzeug lädt diese Datei ohne Backend-Last, ``als_json``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from backend.core import investition_parameter as _reg

PROFIL_DIAGNOSE = "diagnose"

KLASSEN = frozenset({"rein", "raus", "gerundet", "bereinigt:log", "bereinigt:email", "bereinigt:struktur", "allowlist"})

#: Tabellen, die nie ins Paket gehen (``settings`` nur über ``EINSTELLUNGEN`` in der Lage).
NIE = frozenset({"settings", "anlage_foto", "infothek_eintraege", "infothek_dateien", "infothek_investition", "api_cache"})

#: ``core/database.py::_run_data_migrations`` — wörtlich (W-7 a vergleicht mit dem Code).
MIGRATIONS_DDL = "CREATE TABLE IF NOT EXISTS migrations (  name VARCHAR(100) PRIMARY KEY,  applied_at TEXT NOT NULL)"

#: Schlüsselwörter (Spalten- und JSON-Schlüsselnamen): ein JSON-Schlüssel darauf wird geschwärzt, gleich welchen Typs; kein
#: ``rein`` und kein ``text_schluessel`` darf darauf passen (W-7 a, K6) — außer ``ERLAUBTE_SCHLUESSELWORT_NAMEN``.
SCHLUESSELWOERTER = re.compile(
    r"token|passw|secret|authori[sz]ation|api_?key|apikey|kundennummer|hash|credential|bearer|^pw$", re.I)
#: Idempotenz-Hashes über Import-Nutzdaten (``services/import_writer.py``), kein Geheimnis.
ERLAUBTE_SCHLUESSELWORT_NAMEN = frozenset({"source_hash", "input_hash"})


def ist_schluesselwort(name: str) -> bool:
    return name not in ERLAUBTE_SCHLUESSELWORT_NAMEN and bool(SCHLUESSELWOERTER.search(name))


#: Oberschlüssel von ``activity_log.details_json`` (AST über die Aufrufstellen + Ausdrucks-Quellen, W-7 b).
DETAILS_JSON_SCHLUESSEL = frozenset({
    "connector_id", "host", "importiert", "uebersprungen", "fehler", "geschuetzt", "field_id", "vorher", "nachher", "felder",
    "investition_id", "typ", "snapshots_entfernt", "kanaele_entfernt", "korrigiert", "gekuerzt", "datum",
    "reaggregation_fehler", "kanaele", "abschnitte", "gleich", "plan_id", "operation", "params", "actual_changes", "timestamp",
    "pv_erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh", "batterie_ladung_kwh", "batterie_entladung_kwh",
    "wallbox_ladung_kwh", "gefuellt", "zeilen", "bloecke", "markiert", "live_fallback", "unknown", "deckel_verworfen",
    "tagesstand_reihen", "kanal", "zeitpunkt", "kanalzeilen_geloescht", "quellen_markiert", "stundenzeilen_geleert",
    "tageszeilen_geleert", "felder_geleert", "pv", "speicher", "wallbox",
})

#: Schlüssel, die eedc-Code aus ``investitionen.parameter`` liest, ohne dass die Registry sie führt (N-797:
#: ``services/pv_orientation.py``, ``core/investition_kennwerte.py``).
PARAMETER_LESE_SCHLUESSEL = frozenset({"neigung_grad", "neigung", "ausrichtung", "kwp"})


def _parameter_registry() -> frozenset[str]:
    """Alle Schlüssel der Parameter-Registry (``PARAM_*``-Dicts ohne ``_DEFAULTS``) — aus v3 ``_parameter_erlaubt``."""
    schluessel: set[str] = set()
    for name in dir(_reg):
        wert = getattr(_reg, name)
        if name.startswith("PARAM_") and not name.endswith("_DEFAULTS") and isinstance(wert, dict):
            schluessel.update(str(v) for v in wert.values())
    return frozenset(schluessel)


#: ``investitionen.parameter``: Registry ∪ Altschlüssel ∪ Lese-Schlüssel − ``oberflaeche_url`` (URL kann Zugangsdaten tragen).
PARAMETER_ALLOWLIST = (_parameter_registry() | frozenset(_reg.LEGACY_PARAM_KEYS) | PARAMETER_LESE_SCHLUESSEL) - {"oberflaeche_url"}

#: ``settings`` → was in ``lage.einstellungen`` darf (Bauplan §3.3); jeder andere Schlüssel nur als Name.
EINSTELLUNGEN = {
    "mqtt_inbound": ("enabled",),
    "mqtt_export": ("enabled", "sensor_paket_stand", "abgewaehlte_sensoren"),
    "ha_remote": ("eingerichtet", "enabled"),
    "einstellungen_pin": ("gesetzt",),
    "sperre_secret": ("vorhanden",),
    "custom_import_templates": ("anzahl",),
    "community_nachsende_lauf": ("stand", "anlagen", "lauf_erledigt"),
    "wetter_altbestand_nachzug": ("<anlage_id>",),
}

#: ``settings`` mit Schlüssel-Präfix (``<präfix><kennung>``) → was in ``lage.einstellungen`` darf; nur Zustände der Anlage des
#: Pakets (``anlage_id``), Listen als Anzahl. ``korrektur_lauf:`` — Hintergrund-Lauf nach einem Sensorwechsel («löschen», «bleiben»;
#: ``services/zuordnung_wechsel/korrektur_lauf.py``).
EINSTELLUNGEN_PRAEFIX = {
    "korrektur_lauf:": ("sensor_key", "status", "erledigt", "tage", "fehler", "beginn", "ende", "fuellen"),
}

#: ``gruppen``: Liste fester Gruppennamen aus dem Code (``aggregate_day`` an Kanal-Tagen, ``snapshot/boundary_range.py``) —
#: zeigt, welche Gruppen eines Tages aus den Kanälen kommen (Register-Nachtrag nach dem ersten echten Paket, Master 15.11.).
_PROVENANCE_TS = frozenset({"source", "writer", "at", "input_hash", "abgeleitet", "gruppen"})


@dataclass(frozen=True)
class Spalte:
    klasse: str = "rein"
    json: bool = False
    text_schluessel: frozenset = frozenset()
    text_unter: frozenset = frozenset()
    #: ``allowlist``/``bereinigt:struktur``: erlaubte Oberschlüssel (``None`` = keine Oberschlüssel-Prüfung).
    oberschluessel: Optional[frozenset] = None
    #: Oberschlüssel außerhalb der Liste: bleibt eine Zahl stehen? Nur ``investitionen.parameter`` (Konzept §4.2); sonst
    #: (E10 ``connector_config``, ``sensor_mapping``, ``details_json``) wird auch eine Zahl Marke — eine numerisch gespeicherte
    #: Seriennummer oder Kennung bliebe sonst stehen (Einwertung Master S1). ``null`` und Wahrheitswerte bleiben immer.
    fremde_zahlen_bleiben: bool = False
    freitext: bool = False


@dataclass(frozen=True)
class Tabelle:
    filterart: str
    spalten: dict = field(default_factory=dict)

    @property
    def filterspalte(self) -> Optional[str]:
        """Spalte, ohne die der Filter nicht greift (fehlt sie in ``PRAGMA`` ⇒ Teilfehler ``filterspalte_fehlt``)."""
        if self.filterart in ("anlage", "anlage_oder_null"):
            return "id" if "anlage_id" not in self.spalten else "anlage_id"
        if self.filterart == "natural_key":
            return "row_pk_json"
        if self.filterart.startswith("ueber:"):
            return self.filterart.split(".", 1)[1]
        return None

    @property
    def eltern(self) -> Optional[str]:
        return self.filterart[len("ueber:"):].split(".", 1)[0] if self.filterart.startswith("ueber:") else None


def _js(klasse="rein", ts=(), tu=(), ober=None, fremde_zahlen=False) -> Spalte:
    return Spalte(klasse=klasse, json=True, text_schluessel=frozenset(ts), text_unter=frozenset(tu),
                  oberschluessel=None if ober is None else frozenset(ober), fremde_zahlen_bleiben=fremde_zahlen)


def _tab(filterart: str, namen: str, **sonder: Spalte) -> Tabelle:
    spalten = {n: sonder.get(n, Spalte()) for n in namen.split()}
    assert set(sonder) <= set(spalten), set(sonder) - set(spalten)
    return Tabelle(filterart, spalten)


_RAUS = Spalte("raus")
_RUND = Spalte("gerundet")
_LOG = Spalte("bereinigt:log")
_FREI = Spalte(freitext=True)
_LEER = _js()
_PROV = _js("bereinigt:email", ts=_PROVENANCE_TS)

#: Eine wirksame Quelle (``zuordnung_wechsel.vorher``/``nachher``): Oberschlüssel der Beschreibung, Text nur unter Art, Entität,
#: MQTT-Schlüssel, Topic und Pfad.
_ZUORDNUNG = _js("allowlist",
                 ober=("art", "entity_id", "mqtt_key", "topic", "payload_typ", "json_pfad", "array_index", "faktor", "offset"),
                 ts=("art", "entity_id", "mqtt_key", "topic", "payload_typ", "json_pfad"))

REGISTER: dict[str, Tabelle] = {
    "activity_log": _tab(
        "anlage_oder_null", "id timestamp kategorie aktion erfolg details details_json anlage_id",
        aktion=_LOG, details=_LOG,
        details_json=_js("bereinigt:struktur", ober=DETAILS_JSON_SCHLUESSEL, tu=("params",), ts=(
            "plan_id", "operation", "key", "datum", "felder", "field_id", "quelle", "entity_id", "strategie", "sensor_id",
            "connector_id", "host", "typ", "timestamp", "kanal", "zeitpunkt", "reaggregation_fehler"))),
    "anlagen": _tab(
        "anlage",
        "id anlagenname leistung_kwp installationsdatum standort_land standort_plz standort_ort standort_strasse latitude "
        "longitude horizont_daten ausrichtung neigung_grad wechselrichter_hersteller ha_sensor_pv_erzeugung "
        "ha_sensor_einspeisung ha_sensor_netzbezug ha_sensor_batterie_ladung ha_sensor_batterie_entladung mastr_id "
        "versorger_daten wetter_provider wetter_modell sensor_mapping connector_config community_hash community_auto_share "
        "netz_puffer_w prognose_quelle guenstig_schwelle_prozent prognose_basis vollbackfill_durchgefuehrt "
        "steuerliche_behandlung ust_satz_prozent unterliegt_eeg_51 created_at updated_at",
        standort_strasse=_RAUS, mastr_id=_RAUS, community_hash=_RAUS, latitude=_RUND, longitude=_RUND,
        horizont_daten=_LEER,
        versorger_daten=Spalte("raus", json=True),
        # `updated_at`: ISO-Zeitstempel, maschinengeschrieben (`datetime.now().isoformat()` der bis N-241 offenen Schreibtür
        # `api/routes/sensor_mapping.py`; am HEAD Altbestand) — Register-Nachtrag, Master 15.11.
        # `solcast_config` bleibt außerhalb der Allowlist (Marke; Konzept: fällt heraus).
        sensor_mapping=_js("allowlist",
                           ober=("basis", "investitionen", "quellen", "invertieren", "historie_hinweis", "live_sensors",
                                 "updated_at"),
                           ts=("sensor_id", "strategie", "quelle", "entity_id", "id", "label", "name", "seit",
                               "updated_at"),
                           tu=("live", "live_sensors")),
        connector_config=_js("allowlist", ober=("connector_id", "field_inv_map", "last_fetch", "meter_snapshots"),
                             ts=("connector_id", "last_fetch", "timestamp"))),
    "data_provenance_log": _tab(
        "natural_key",
        "id table_name row_pk_json field_name source writer written_at old_value new_value input_hash decision "
        "decision_reason",
        writer=Spalte("bereinigt:email")),
    "emob_ladebloecke": _tab(
        "anlage", "id anlage_id investition_id beginn ende kwh pv_kwh netz_kwh stunden stunden_gedeckt luecke speicher_kwh "
                  "regel quelle",
        stunden=_js(ts=("beginn",))),
    "investition_monatsdaten": _tab(
        "ueber:investitionen.investition_id",
        "id investition_id jahr monat verbrauch_daten einsparung_monat_euro co2_einsparung_kg source_provenance source_hash "
        "geprueft_gegen created_at updated_at",
        verbrauch_daten=_js(ts=("bezeichnung", "typ")), source_provenance=_PROV, geprueft_gegen=_LEER),
    "investitionen": _tab(
        "anlage",
        "id anlage_id typ bezeichnung anschaffungsdatum stilllegungsdatum anschaffungskosten_gesamt "
        "anschaffungskosten_alternativ betriebskosten_jahr leistung_kwp ausrichtung neigung_grad ha_entity_id parameter "
        "einsparung_prognose_jahr co2_einsparung_prognose_kg graue_last_kg aktiv parent_investition_id created_at updated_at",
        parameter=_js("allowlist", ober=PARAMETER_ALLOWLIST, ts=PARAMETER_ALLOWLIST | {"bezeichnung"}, fremde_zahlen=True)),
    "kanal": _tab("anlage", "id anlage_id key einheit art aufbaubar_ab"),
    "kanal_nachfuellung": _tab("ueber:kanal.kanal_id", "kanal_id statistic_id abgeschlossen_ts ergebnis",
                               ergebnis=_js(ts=("grund",))),
    "kanal_quelle": _tab("ueber:kanal.kanal_id", "kanal_id gueltig_ab familie statistic_id offset verworfen_ts"),
    "kanal_statistik": _tab("ueber:kanal.kanal_id", "kanal_id start_ts sum state mean min max familie"),
    "korrekturprofile": _tab(
        "anlage",
        "id anlage_id investition_id quelle profil_typ bin_definition faktoren datenpunkte_pro_bin tage_eingegangen "
        "aktualisiert_am faktor_skalar lern_basis_pro_bin lern_umstellung_am",
        # `lern_basis_pro_bin`: Bin-Schlüssel → maschinengeschriebene Statusmarke (`korrekturprofil_aggregator.py` schreibt nur
        # «alt»/«neu»), kein Anwendertext ⇒ Text unter jedem Schlüssel; er läuft als `"*"` durch `bereinige_log` (Master 15.11.).
        bin_definition=_js(ts=("wetterklassen", "saisonbin", "variante")), faktoren=_LEER, datenpunkte_pro_bin=_LEER,
        lern_basis_pro_bin=_js(ts=("*",))),
    "migrations": _tab("ganz", "name applied_at"),
    "monatsdaten": _tab(
        "anlage",
        "id anlage_id jahr monat einspeisung_kwh netzbezug_kwh pv_erzeugung_kwh direktverbrauch_kwh eigenverbrauch_kwh "
        "gesamtverbrauch_kwh batterie_ladung_kwh batterie_entladung_kwh batterie_ladung_netz_kwh batterie_ladepreis_cent "
        "netzbezug_durchschnittspreis_cent einspeise_durchschnittspreis_cent kraftstoffpreis_euro gaspreis_cent_kwh "
        "globalstrahlung_kwh_m2 sonnenstunden durchschnittstemperatur ueberschuss_kwh defizit_kwh batterie_vollzyklen "
        "performance_ratio peak_netzbezug_kw sonderkosten_euro sonderkosten_beschreibung sonstige_positionen datenquelle "
        "notizen source_provenance source_hash geprueft_gegen created_at updated_at",
        notizen=_FREI, sonderkosten_beschreibung=_FREI, sonstige_positionen=_js(ts=("bezeichnung", "typ")),
        source_provenance=_PROV, geprueft_gegen=_LEER),
    "mqtt_energy_snapshots": _tab("anlage", "id anlage_id timestamp energy_key value_kwh"),
    "mqtt_gateway_mappings": _tab(
        "anlage", "id anlage_id quell_topic ziel_key payload_typ json_pfad array_index faktor offset invertieren aktiv "
                  "beschreibung preset_id erstellt_am",
        beschreibung=_FREI),
    "mqtt_live_snapshots": _tab("anlage", "id anlage_id timestamp component_key value_w ts_unix min max"),
    "pvgis_monatsprognosen": _tab("ueber:pvgis_prognosen.prognose_id",
                                  "id prognose_id monat ertrag_kwh einstrahlung_kwh_m2 standardabweichung_kwh"),
    "pvgis_prognosen": _tab(
        "anlage",
        "id anlage_id abgerufen_am latitude longitude neigung_grad ausrichtung_grad system_losses jahresertrag_kwh "
        "spezifischer_ertrag_kwh_kwp gesamt_leistung_kwp monatswerte module_monatswerte horizont_verwendet raddatabase "
        "ist_aktiv created_at",
        latitude=_RUND, longitude=_RUND, monatswerte=_LEER, module_monatswerte=_LEER),
    "sensor_snapshots": _tab("anlage", "id anlage_id sensor_key zeitpunkt wert_kwh quelle"),
    "strompreis_zeitfenster": _tab("ueber:strompreise.strompreis_id",
                                   "id strompreis_id von_stunde bis_stunde wochentage arbeitspreis_cent_kwh"),
    "strompreise": _tab(
        "anlage",
        "id anlage_id netzbezug_arbeitspreis_cent_kwh einspeiseverguetung_cent_kwh grundpreis_euro_monat "
        "zaehlergebuehr_euro_jahr gueltig_ab gueltig_bis tarifname anbieter vertragsart einspeisung_variabel verwendung "
        "created_at updated_at"),
    "tages_energie_profil": _tab(
        "anlage",
        "id anlage_id datum stunde pv_kw verbrauch_kw einspeisung_kw netzbezug_kw batterie_kw waermepumpe_kw wallbox_kw "
        "wp_starts_anzahl wp_betriebsstunden ueberschuss_kw defizit_kw temperatur_c globalstrahlung_wm2 bewoelkung_prozent "
        "niederschlag_mm wetter_code soc_prozent soc_je_speicher betriebsmodus_je_wp strompreis_cent boersenpreis_cent "
        "komponenten spannen source_provenance created_at",
        soc_je_speicher=_LEER, betriebsmodus_je_wp=_js(ts=("*",)), komponenten=_LEER, spannen=_LEER,
        source_provenance=_PROV),
    "tages_zusammenfassung": _tab(
        "anlage",
        "id anlage_id datum ueberschuss_kwh defizit_kwh peak_pv_kw peak_netzbezug_kw peak_einspeisung_kw batterie_vollzyklen "
        "temperatur_min_c temperatur_max_c strahlung_summe_wh_m2 gti_summe_wh_m2 performance_ratio pv_prognose_kwh "
        "pv_prognose_final_kwh pv_prognose_final_at pv_prognose_eedc_final_kwh pv_prognose_eedc_mittag_kwh "
        "pv_prognose_om_mittag_kwh solcast_mittag_kwh sfml_mittag_kwh sfml_prognose_kwh solcast_prognose_kwh solcast_p10_kwh "
        "solcast_p90_kwh pv_prognose_stundenprofil solcast_prognose_stundenprofil sfml_prognose_stundenprofil "
        "lern_soll_stundenprofil_kwh pv_prognose_kaskade_stundenprofil lern_soll_kwh stunden_verfuegbar datenquelle "
        "boersenpreis_avg_cent boersenpreis_min_cent negative_preis_stunden einspeisung_neg_preis_kwh kraftstoffpreis_euro "
        "emob_ladung_pv_abgeleitet_kwh emob_ladung_netz_abgeleitet_kwh emob_ladung_speicher_abgeleitet_kwh komponenten_kwh "
        "komponenten_starts verworfen nachtrag source_provenance created_at updated_at",
        **{n: _LEER for n in ("pv_prognose_stundenprofil", "solcast_prognose_stundenprofil", "sfml_prognose_stundenprofil",
                              "lern_soll_stundenprofil_kwh", "pv_prognose_kaskade_stundenprofil", "komponenten_kwh",
                              "komponenten_starts", "verworfen", "nachtrag")},
        source_provenance=_PROV),
    # Sensorwechsel mit Grund (B-1): `vorher`/`nachher` sind wirksame Quellen — dieselbe Klasse wie `anlagen.sensor_mapping`
    # (Entität und MQTT-Topic als Text, keine Zugangsdaten; Form `services/zuordnung_wechsel/quelle.py`).
    "zuordnung_wechsel": _tab(
        "anlage", "id anlage_id sensor_key erklaert_ts ab_ts vorher nachher grund herkunft aufgehoben_durch "
        "ansatz stand_alt_ende stand_neu_null eingetragen_ts",
        vorher=_ZUORDNUNG, nachher=_ZUORDNUNG),
}


def als_json() -> str:
    """Das Register als JSON (für das Werkzeug unter ``~/.claude/plans/diagnose-werkzeug/``: Namen nur aus dem Register)."""
    def _spalte(s: Spalte) -> dict:
        return {"klasse": s.klasse, "json": s.json, "text_schluessel": sorted(s.text_schluessel),
                "text_unter": sorted(s.text_unter),
                "oberschluessel": None if s.oberschluessel is None else sorted(s.oberschluessel),
                "fremde_zahlen_bleiben": s.fremde_zahlen_bleiben, "freitext": s.freitext}

    return json.dumps({
        "profil": PROFIL_DIAGNOSE, "nie": sorted(NIE), "migrations_ddl": MIGRATIONS_DDL,
        "tabellen": {t: {"filterart": tab.filterart, "spalten": {n: _spalte(s) for n, s in tab.spalten.items()}}
                     for t, tab in sorted(REGISTER.items())},
    }, ensure_ascii=False, sort_keys=True)
