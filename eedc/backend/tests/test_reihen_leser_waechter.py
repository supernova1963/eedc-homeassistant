"""Wächter «Reihen-Leser» (Sensorwechsel mit Grund, Bauplan B-5/B-8, Sitzung 2, 17.11.2026).

**Regel.** Jede Stelle, die Stände der Zählerstand-Reihe (``sensor_snapshots``, ``mqtt_energy_snapshots``) liest, steht in
``REIHEN_LESER`` — mit ihrer **Einstufung** gegenüber einer Naht (B-3: «keine Differenz zweier Stände über eine
Fortsetzungs-Naht») und dem Grund. Eine neue Lesestelle ohne Eintrag ist rot, ein Eintrag ohne Lesestelle ebenso (verwaist).
Wer einen neuen Leser schreibt, entscheidet damit sichtbar, wie er mit einer Naht umgeht.

**Einstufungen:**

* ``naht`` — **Naht beachtet**: der Leser bildet seine Menge je Abschnitt (``core/berechnungen/zaehler_naht.py``, Nähte aus
  ``zuordnung_wechsel.zeitpunkt.fortsetzungs_naehte``).
* ``kanal`` — **Kanal zuerst** (B-5): der Leser nimmt das Δ des eigenen Kanals, wo er das Fenster voll trägt
  (``kanal/feld_leser.py``), sonst die Reihe mit Naht.
* ``bewusst`` — **bewusst nicht**: liest die Reihe **ohne Naht-Schutz**, mit Grund.
* ``ohne_aufrufer`` — kein Produktiv-Aufrufer (Bauplan §7 Nr. 14: führen, nicht entfernen).
* ``primitiv`` — Lese-Baustein: liefert Stände, bildet selbst keine Menge (die Einstufung trägt sein Aufrufer).
* ``schreiber`` — füllt oder schreibt die Reihe, bildet keine Menge (Zuordnung zum Zeitpunkt: B-0).
* ``stand`` — zeigt einen Stand, keine Differenz.
* ``anzeige`` — stellt gespeicherte Stände oder Zeilen gegenüber bzw. zählt sie (Werkbank-Vorschau alt/neu, Diagnose); bildet
  keine Menge, die eine Sicht als Wert zeigt (Sitzung 4, Bauplan §12 Nr. 61).

``ha_spiegel``: die Stelle liest Felder, die einen HA-Spiegel haben können (HA-Zuordnung). **B-8** (Befund «Naht ohne
verzeichneten Wechsel») entfällt genau dann, wenn kein Eintrag ``bewusst`` mit ``ha_spiegel`` bleibt — **entfallen (Entscheid
Gernot 18.11.2026, Bauplan §12 Nr. 61)**: seit Sitzung 4 ist die Liste aus der Struktur leer (die zwei Stellen ohne Menge stehen
als ``anzeige``, der Stände-Nachbau ``kanal/nachfuellen._rohstaende`` als ``naht``), und
``test_b8_liste_ohne_naht_schutz_mit_ha_spiegel`` hält sie leer — ein neuer Eintrag ``bewusst`` mit ``ha_spiegel`` ist rot.

**Was er erkennt (AST, Produktivbaum ohne ``tests/``):** einen Aufruf eines Lese-Bausteins (``PRIMITIVE``, Name oder
Attribut), einen Zugriff auf die Wertspalte ``SensorSnapshot.wert_kwh`` / ``MqttEnergySnapshot.value_kwh`` und SQL-Text
``FROM``/``JOIN`` auf beide Tabellen — je umschließender Funktion (Modulebene: ``<modul>``). **Nicht erfasst (benannt):** ein
ORM-Objekt der Reihe, dessen Wert über die Instanz gelesen wird (``row.wert_kwh`` nach ``select(SensorSnapshot)``), und ein
Leser, der die Reihe nur über das Ergebnis eines eingestuften Lesers sieht (Ladeblöcke über ``TagesTabelle.zusatz_slots`` —
L13 erbt L5). Gegenprobe je Form im Test.

Vorlage: Leser-Inventar L1–L18 (Messblatt Sitzung 0, ``opus-berichte/SENSORWECHSEL-S0-2026-11-16.md`` M-A); die Leser-Tabelle des
Berichts Sitzung 2 nennt dieselben Einträge. Schwesterdateien: test_kanal_lesen_waechter.py (wer die Kanal-Lese-Schicht
importiert), test_tageswert_aus_reihe_ist_die_eine_regel.py.
"""

from __future__ import annotations

import ast
import re

from backend.tests.quellbaum import produktivbaum

NAHT, KANAL, BEWUSST, OHNE_AUFRUFER = "naht", "kanal", "bewusst", "ohne_aufrufer"
PRIMITIV, SCHREIBER, STAND, ANZEIGE = "primitiv", "schreiber", "stand", "anzeige"
EINSTUFUNGEN = {NAHT, KANAL, BEWUSST, OHNE_AUFRUFER, PRIMITIV, SCHREIBER, STAND, ANZEIGE}

#: Lese-Bausteine der Reihe — ihr Aufruf macht die umschließende Funktion zu einer Lesestelle.
PRIMITIVE = frozenset({
    "get_snapshot", "reihe_im_fenster", "letzter_stand_vor", "letzter_stand_im_fenster", "erster_stand_im_fenster",
    "_reihe_ueber_bereich", "_raender_mit_heilung", "lade_zaehler_verlaeufe", "_get_mqtt_snapshot_at",
    "_get_closest_snapshot", "_get_earliest_snapshot_after", "_db_snap_at",
})
SPALTEN = frozenset({("SensorSnapshot", "wert_kwh"), ("MqttEnergySnapshot", "value_kwh")})
_SQL = re.compile(r"\b(from|join)\s+(sensor_snapshots|mqtt_energy_snapshots)\b", re.IGNORECASE)

#: ``"datei::funktion"`` → ``(Leser-Nr. aus dem Inventar oder «—», Einstufung, ha_spiegel, Grund)``.
REIHEN_LESER: dict[str, tuple[str, str, bool, str]] = {
    # ── Mengen der Tagesansicht und der Tageszeile ──
    "services/snapshot/aggregator.py::_tageswert_aus_raendern": (
        "L1/L2", NAHT, True, "Tageswert = Summe der Abschnitte (reader.tageswert_ueber_abschnitte)"),
    "services/snapshot/aggregator.py::_tagesdetail_boundary_diff_mit_grund": (
        "L2", NAHT, True, "Ränder und Rückfall; die Menge über _tageswert_aus_raendern. In get_tagesdetail_kwh gilt davor "
        "Kanal vor Reihe je Zähler (_typ_summe → kanal/feld_leser.kanal_feldwerte) — die 15 Tage der Produktiv-Anlage"),
    "services/snapshot/aggregator.py::slots_aus_staenden": (
        "L5", NAHT, True, "Slot-Bildung von snapshot_tagestabelle (seit Fund-Päckchen F eine Funktion, auch für ein MQTT-Feld "
        "neben HA-Feldern in lts_tagestabelle): Naht-Slot zählt nur den neuen Abschnitt, auch als Bündel über eine Lücke "
        "(N-817); eine Naht "
        "mit Rand-Ständen (U2 a1, F5) hebt die Stände beim Laden (zaehler_naht.gehobene_staende) und teilt nicht; "
        "die Heimlade-Slots (zusatz_slots) für die Ladeblöcke (L13) gehen durch dieselbe Schleife"),
    "services/snapshot/aggregator.py::get_daily_counter_deltas_by_inv": (
        "L7", NAHT, True, "Zählwerk Tag über _zaehlwerk_tag (zaehler_naht.zaehlwerk_menge)"),
    "services/snapshot/aggregator.py::_zaehlwerk_tag": (
        "L7", NAHT, True, "die Abschnitts-Form der Zählwerke (Starts, Betriebsstunden)"),
    "services/snapshot/aggregator.py::get_hourly_counter_sum_by_feld": (
        "L8", NAHT, True, "Naht-Slot zählt 0; mit Rand-Ständen (U2 a1) gehoben beim Laden, der Slot zählt seine Menge"),
    "services/snapshot/aggregator.py::_diff": (
        "—", OHNE_AUFRUFER, True, "Closure von get_komponenten_tageskwh — ohne Produktiv-Aufrufer (Messblatt S0 M-A)"),
    "services/snapshot/bereichs_leser.py::_tageswerte_des_feldes": (
        "L3", KANAL, True, "kanal_zuerst=True (Speicher-Netzladung der Monats-Fakten, §7 Nr. 12) — sonst Reihe mit Naht"),
    "services/snapshot/bereichs_leser.py::_anker": (
        "L3", NAHT, True, "Lückenanker R1 des Bereichs-Lesers (seit 4b-1-K2 aus _randstaende herausgelöst; an einem gesperrten "
        "Stück dessen Ende, Nr. 112); die Menge bildet _randstaende je Abschnitt (reader.tageswert_ueber_abschnitte, "
        "Lücken-Regel zaehler_naht); Wärme-Verlauf (a) liest so"),
    "services/snapshot/stunden_leser.py::lade_stundenformen": (
        "L6", NAHT, True, "Stundenform der WP-Zähler ohne WP-Kanal: Naht-Slot 0, auch als Bündel über eine Lücke; mit "
        "Rand-Ständen (U2 a1) gehoben beim Laden"),
    "services/snapshot/reader.py::delta": (
        "L4", NAHT, True, "Menge über ein Fenster je Abschnitt (MQTT-Monat, Cockpit → Monat)"),
    "services/snapshot/reader.py::delta_mit_rand": (
        "L4", NAHT, True, "über delta"),
    "services/zaehlerstaende.py::lade_zaehlerstaende": (
        "L9", NAHT, True, "Differenz je Abschnitt (zaehler_naht.stand_differenz)"),
    "services/daten_checker/zaehler.py::_check_zaehlerstaende": (
        "L10", NAHT, True, "Bruch über eine Naht ist kein Bruch (finde_reihen_brueche mit Nähten)"),
    "services/kanal/schreiber.py::_eigene_summe": (
        "L16", NAHT, False, "MQTT «Eigene Summe»: eine Fortsetzung teilt die Periode (kanal/naht.zeilen_mit_naehten, B-4)"),
    "services/snapshot/reader.py::finde_zaehler_ruecksprunge": (
        "L11", NAHT, False, "Befund zaehler_ruecksprung — nur MQTT-Reihen; ein Paar über eine Fortsetzungs-Naht ist kein "
        "Rücksprung (zaehler_naht.ueber_naht, Sitzung 4)"),
    "services/kanal/nachfuellen.py::_rohstaende": (
        "L15", NAHT, True, "Stände-Nachbau (Familie Mitschrift, HA-Stände wörtlich) vor der ersten Kanalzeile: _laeufe teilt an "
        "jeder verzeichneten Fortsetzung (neue Quelle ohne Zuwachs, Sitzung 4); eine später nachgetragene trägt "
        "kanal/naht.nachtrag_fortsetzung (Einstieg «Zähler getauscht», «Grund nachtragen»); an einer Naht mit Rand-Ständen "
        "setzen beide denselben Versatz wie die gehobene Reihe (U2 a1, F5)"),
    # ── zeigen oder zählen, keine Menge einer Sicht (Sitzung 4, Bauplan §12 Nr. 61) ──
    "services/snapshot/reaggregator.py::_counter_delta_alt": (
        "L14", ANZEIGE, True, "Werkbank-Vorschau: Gegenüberstellung alt/neu der gespeicherten Stände, keine Anzeige-Menge"),
    "api/routes/diagnostics.py::live_snapshot_5min_diagnostics": (
        "—", ANZEIGE, True, "Diagnose-Route: zählt und zeigt Fünf-Minuten-Zeilen, keine Menge"),
    # ── bewusst nicht ──
    "services/mqtt_energy_history_service.py::get_tages_kwh": (
        "L17", BEWUSST, False, "MQTT-Live heute/gestern (Rückgang: der neue Stand zählt als Tageswert) — Live-Wert, nach zwei "
        "Tagen vorbei; die Menge der Tage trägt der Kanal (B-4)"),
    "services/live_verbrauchsprofil_service.py::_profil_from_mqtt": (
        "L18", BEWUSST, False, "Verbrauchsprofil aus 7 Tagen MQTT-Stichproben (Form, keine Menge); eine Naht-Stunde fällt aus"),
    # ── Bausteine, Schreiber, Stand ──
    "services/snapshot/reader.py::get_snapshot": ("—", PRIMITIV, True, "ein Stand zum Zeitpunkt, heilt nach B-0"),
    "services/snapshot/reader.py::reihe_im_fenster": ("—", PRIMITIV, True, "die Stände zwischen zwei Rändern"),
    "services/snapshot/reader.py::letzter_stand_vor": ("—", PRIMITIV, True, "Lückenanker R1"),
    "services/snapshot/reader.py::letzter_stand_im_fenster": ("—", PRIMITIV, True, "Rückfall R-4"),
    "services/snapshot/reader.py::erster_stand_im_fenster": ("—", PRIMITIV, True, "Rückfall R-4 / N-472"),
    "services/snapshot/reader.py::_get_mqtt_snapshot_at": ("—", PRIMITIV, False, "MQTT-Stand zum Zeitpunkt"),
    "services/snapshot/reader.py::zaehler_faellt_im_fenster": (
        "—", OHNE_AUFRUFER, True, "ohne Produktiv-Aufrufer (Messblatt S0 M-A)"),
    "services/snapshot/reader.py::get_counter_lifetime": ("—", STAND, True, "Zählerstand seit Beginn (WP-Dashboard)"),
    "services/snapshot/bereichs_leser.py::_reihe_ueber_bereich": ("L3", PRIMITIV, True, "die eine Abfrage des Bereichs"),
    "services/snapshot/bereichs_leser.py::_raender_mit_heilung": ("L3", PRIMITIV, True, "Ränder mit Heilung"),
    "services/snapshot/reaggregator.py::_db_snap_at": ("L14", PRIMITIV, True, "gespeicherter Stand der Vorschau"),
    "services/snapshot/reaggregator.py::_boundaries": ("L14", STAND, True, "Vorschau: Grenzstände alt/neu nebeneinander"),
    "services/zuordnung_wechsel/ansatz.py::_letzter_stand": (
        "—", STAND, True, "Sensorwechsel U2 a2: der gespeicherte Stand des alten Sensors am Rand eines Wechsels «bleiben» "
        "(Rand-Stand in der Höhe der Reihe, Rückfall nur aus HAs Statistik) — ein Stand, keine Menge"),
    "services/zaehlerstaende.py::lade_zaehler_verlaeufe": ("L9", PRIMITIV, True, "Punktreihe Snapshots + gepflegte Stände"),
    "services/mqtt_energy_history_service.py::_get_closest_snapshot": ("L17", PRIMITIV, False, "MQTT-Stand"),
    "services/mqtt_energy_history_service.py::_get_earliest_snapshot_after": ("L17", PRIMITIV, False, "MQTT-Stand"),
    "services/snapshot/writer.py::snapshot_anlage": ("—", SCHREIBER, True, "Stundenschreiber (B-0)"),
    "services/snapshot/fallback.py::live_snapshot_if_missing": ("—", SCHREIBER, True, "Live-Rückfall der laufenden Stunde (B-0)"),
}

#: Die Einträge «liest die Reihe ohne Naht-Schutz» für Felder mit HA-Spiegel — die Liste, an der B-8 entschied. Seit Sitzung 4
#: leer (B-8 entfällt, Entscheid Gernot 18.11.2026); Gleichheit, damit ein neuer Eintrag im Diff steht und rot ist.
OHNE_NAHT_SCHUTZ_MIT_HA_SPIEGEL: set[str] = set()


def _funktion_von(knoten: ast.AST, eltern: dict) -> str:
    q = knoten
    while q in eltern and not isinstance(q, (ast.FunctionDef, ast.AsyncFunctionDef)):
        q = eltern[q]
    return q.name if isinstance(q, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<modul>"


def ist_lesestelle(n: ast.AST) -> bool:
    """Ein Knoten, der die Reihe liest (Aufruf eines Bausteins, Wertspalte, SQL-Text)."""
    if isinstance(n, ast.Call):
        f = n.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        return name in PRIMITIVE
    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
        return (n.value.id, n.attr) in SPALTEN
    return isinstance(n, ast.Constant) and isinstance(n.value, str) and bool(_SQL.search(n.value))


def lesestellen(quelle: str, rel: str) -> set[str]:
    """``{"datei::funktion"}`` aller Lesestellen einer Quelldatei."""
    baum = ast.parse(quelle)
    eltern = {c: p for p in ast.walk(baum) for c in ast.iter_child_nodes(p)}
    return {f"{rel}::{_funktion_von(n, eltern)}" for n in ast.walk(baum) if ist_lesestelle(n)}


def _alle() -> set[str]:
    out: set[str] = set()
    for d in produktivbaum():
        out |= lesestellen(d.quelle, d.rel)
    return out


def test_jede_lesestelle_ist_eingestuft():
    gefunden = _alle()
    neu = sorted(gefunden - set(REIHEN_LESER))
    verwaist = sorted(set(REIHEN_LESER) - gefunden)
    assert not neu, ("Neue Lesestelle der Zählerstand-Reihe ohne Einstufung — in REIHEN_LESER eintragen (naht · kanal · "
                     f"bewusst mit Grund · …): {neu}")
    assert not verwaist, f"Eintrag ohne Lesestelle (umbenannt oder entfernt) — Eintrag nachziehen: {verwaist}"


def test_einstufung_und_grund():
    for key, (_nr, einstufung, _ha, grund) in REIHEN_LESER.items():
        assert einstufung in EINSTUFUNGEN, key
        assert grund.strip(), key


def test_b8_liste_ohne_naht_schutz_mit_ha_spiegel():
    ist = {k for k, (_nr, e, ha, _g) in REIHEN_LESER.items() if e == BEWUSST and ha}
    assert ist == OHNE_NAHT_SCHUTZ_MIT_HA_SPIEGEL


def test_gegenprobe_je_form():
    """Sprengsatz: je Erkennungs-Form eine Lesestelle in einer erfundenen Datei — jede wird gefunden (und wäre ohne
    Eintrag rot)."""
    quelle = '''
from backend.services.snapshot.reader import get_snapshot

async def neu_aufruf(db):
    return await get_snapshot(db, 1, "k", None, None)

async def neu_attribut(db):
    from backend.services import snapshot
    return await snapshot.reader.reihe_im_fenster(db, 1, "k", None, None)

def neu_spalte():
    from backend.models.sensor_snapshot import SensorSnapshot
    return SensorSnapshot.wert_kwh

SQL = "SELECT wert_kwh FROM sensor_snapshots WHERE anlage_id = 1"

def ohne():
    return "sensor_snapshots ist ein Name, kein SQL"
'''
    assert lesestellen(quelle, "x.py") == {"x.py::neu_aufruf", "x.py::neu_attribut", "x.py::neu_spalte", "x.py::<modul>"}
