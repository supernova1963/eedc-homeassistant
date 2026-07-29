"""
Datenquellen-V4 §2i — Zuordnungs-Validierung (config-basiert, diagnostisch).

Regel-Tabellen für die vier Prüfungen: Einheit (#200), state_class,
Aggregat-Redundanz (C, Engine-Vorrang), HA-Doppelmapping (#314).
"""

from backend.services.datenquellen_validierung import (
    einheit_problem,
    state_class_problem,
    finde_redundante_aggregate,
    finde_doppelmappings,
)


# ─── Einheit (Leistung↔Energie, #200) ────────────────────────────────────

def test_einheit_mismatch():
    # Energie-Sensor in Leistungs-Feld → ERROR
    assert einheit_problem("W", "kWh")["schwere"] == "error"
    # Leistungs-Sensor in Energie-Feld → WARNING
    assert einheit_problem("kWh", "W")["schwere"] == "warning"


def test_einheit_ok_und_egal():
    assert einheit_problem("W", "kW") is None      # beide Leistung (kW→W normalisiert)
    assert einheit_problem("kWh", "kWh") is None    # gleich
    assert einheit_problem("%", "°C") is None        # keine Leistung/Energie → egal
    assert einheit_problem("W", None) is None        # Sensor-Einheit unbekannt
    assert einheit_problem(None, "kWh") is None       # Feld-Einheit unbekannt


# ─── state_class (HA-Energie-Feld ohne Langzeit-Statistik) ────────────────

def test_state_class_fehlt_nur_energie():
    assert state_class_problem("kWh", None)["schwere"] == "warning"
    assert state_class_problem("kWh", "")["schwere"] == "warning"
    assert state_class_problem("kWh", "total_increasing") is None
    # Live-W braucht kein state_class (liest state direkt)
    assert state_class_problem("W", None) is None
    assert state_class_problem("%", None) is None


# ─── Aggregat-Redundanz (C, Engine-Vorrang) ──────────────────────────────

def _f(id, feld, typ, belegt):
    return {"id": id, "feld": feld, "typ": typ, "belegt": belegt}


def test_pv_gesamt_redundant_wenn_alle_einzeln_belegt():
    """Vollständig gemessen → beide Aggregate wirkungslos (Stufe 1 der Präzedenz)."""
    felder = [
        _f("basis_energy_pv_gesamt_kwh", "pv_gesamt_kwh", "basis", True),
        _f("basis_live_pv_gesamt_w", "pv_gesamt_w", "basis", True),
        _f("inv_energy_2_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", True),
        _f("inv_live_2_leistung_w", "leistung_w", "pv-module", True),
    ]
    red = finde_redundante_aggregate(felder)
    assert "basis_energy_pv_gesamt_kwh" in red
    assert "basis_live_pv_gesamt_w" in red
    assert red["basis_energy_pv_gesamt_kwh"]["grund"] == "pv_aggregat"
    assert "inv_energy_2_pv_erzeugung_kwh" in red["basis_energy_pv_gesamt_kwh"]["wirksame_felder"]
    # Die Komponente selbst ist nicht redundant
    assert "inv_energy_2_pv_erzeugung_kwh" not in red


def test_pv_gesamt_kwh_bei_teil_abdeckung_nicht_redundant():
    """N131 §4 — zwei von drei Strings gemessen: das Aggregat füllt die Lücke.

    Vor 2026-07-29 riet die Fläche hier „auf keine setzen" — wer dem folgte,
    landete in `QUELLE_FEHLT` und damit auf 0 für die GANZE Anlage. Bedingung
    ist jetzt dieselbe wie in `_migrate_pv_erzeugung_aggregat_clear`: erst wenn
    JEDE aktive PV-Quelle einen eigenen Wert hat, darf das Aggregat weg.
    """
    felder = [
        _f("basis_energy_pv_gesamt_kwh", "pv_gesamt_kwh", "basis", True),
        _f("inv_energy_2_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", True),
        _f("inv_energy_3_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", True),
        _f("inv_energy_4_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", False),
    ]
    assert "basis_energy_pv_gesamt_kwh" not in finde_redundante_aggregate(felder)


def test_pv_gesamt_kwh_bkw_ohne_wert_schweigt():
    """BKW zählt wie in der Migration mit — Schweigen ist die sichere Richtung.

    Das Aggregat verteilt zwar nur auf `pv-module`, aber eine unbelegte
    BKW-Zuordnung als „alles gemessen" zu werten hieße, eine Handlungs-
    aufforderung auf eine unvollständige Erfassung zu stützen.
    """
    felder = [
        _f("basis_energy_pv_gesamt_kwh", "pv_gesamt_kwh", "basis", True),
        _f("inv_energy_2_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", True),
        _f("inv_energy_5_pv_erzeugung_kwh", "pv_erzeugung_kwh", "balkonkraftwerk", False),
    ]
    assert "basis_energy_pv_gesamt_kwh" not in finde_redundante_aggregate(felder)


def test_pv_gesamt_live_haengt_allein_an_leistung_w():
    """Live-Rolle ≠ Monats-Rolle (N131 §4).

    `live_komponenten_builder` bildet eine PV-Komponente nur mit `leistung_w`
    (`val_w is None` → `continue`). Ein kWh-Zähler je String macht das
    Live-Aggregat also NICHT wirkungslos — das Monats-Aggregat sehr wohl.
    """
    felder = [
        _f("basis_energy_pv_gesamt_kwh", "pv_gesamt_kwh", "basis", True),
        _f("basis_live_pv_gesamt_w", "pv_gesamt_w", "basis", True),
        _f("inv_energy_2_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", True),
        _f("inv_live_2_leistung_w", "leistung_w", "pv-module", False),
    ]
    red = finde_redundante_aggregate(felder)
    assert "basis_energy_pv_gesamt_kwh" in red      # alle Module messen kWh
    assert "basis_live_pv_gesamt_w" not in red      # kein String misst live


def test_pv_gesamt_allein_nicht_redundant():
    felder = [
        _f("basis_energy_pv_gesamt_kwh", "pv_gesamt_kwh", "basis", True),
        _f("inv_energy_2_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", False),  # keine
    ]
    assert finde_redundante_aggregate(felder) == {}


def test_netz_kombi_redundant_wenn_split_belegt():
    felder = [
        _f("basis_live_netz_kombi_w", "netz_kombi_w", "basis", True),
        _f("basis_live_einspeisung_w", "einspeisung_w", "basis", True),
        _f("basis_live_netzbezug_w", "netzbezug_w", "basis", False),
    ]
    red = finde_redundante_aggregate(felder)
    assert red["basis_live_netz_kombi_w"]["grund"] == "netz_kombi"  # schon 1 Split reicht


def test_batterie_leistung_kein_pv_aggregat_konflikt():
    """`leistung_w` einer Batterie ist KEINE PV-Komponente → kein Fehlalarm."""
    felder = [
        _f("basis_live_pv_gesamt_w", "pv_gesamt_w", "basis", True),
        _f("inv_live_3_leistung_w", "leistung_w", "batteriespeicher", True),
    ]
    assert finde_redundante_aggregate(felder) == {}


# ─── Doppelmapping (#314) ─────────────────────────────────────────────────

def test_doppelmapping_gleiche_entity():
    z = {
        "inv_energy_1_verbrauch_kwh": "sensor.wallbox",
        "inv_energy_2_verbrauch_kwh": "sensor.wallbox",   # dieselbe
        "basis_energy_einspeisung_kwh": "sensor.einsp",
    }
    d = finde_doppelmappings(z)
    assert "inv_energy_1_verbrauch_kwh" in d and "inv_energy_2_verbrauch_kwh" in d
    assert d["inv_energy_1_verbrauch_kwh"]["entity_id"] == "sensor.wallbox"
    assert "inv_energy_2_verbrauch_kwh" in d["inv_energy_1_verbrauch_kwh"]["andere_felder"]
    assert "basis_energy_einspeisung_kwh" not in d   # eindeutig


def test_doppelmapping_leer_bei_eindeutig():
    assert finde_doppelmappings({"a": "sensor.x", "b": "sensor.y"}) == {}


# ─── Takt-Check (#343 Baustein B, D2 2026-07-18) ─────────────────────────

def test_takt_gesunder_zaehler_ok():
    from backend.services.datenquellen_validierung import takt_problem
    # 48 h à ~15 gleichmäßige kleine Zuwächse → kein Problem
    werte, w = [], 100.0
    for _ in range(40):
        w += 0.25
        werte.append(w)
    assert takt_problem(werte) is None


def test_takt_session_ende_sprung_warnt():
    from backend.services.datenquellen_validierung import takt_problem
    # evcc-Klasse: flach, EIN großer Sprung am Lade-Session-Ende
    werte = [100.0] * 20 + [128.6] * 20
    p = takt_problem(werte)
    assert p is not None and p["art"] == "takt" and p["schwere"] == "warning"


def test_takt_wenige_grosse_schritte_warnt():
    from backend.services.datenquellen_validierung import takt_problem
    # Nur 3 Zuwächse in 48 h (< _TAKT_MIN_AENDERUNGEN) → sprunghaft
    werte = [100.0] * 5 + [110.0] * 5 + [122.0] * 5 + [130.0] * 5
    p = takt_problem(werte)
    assert p is not None and p["art"] == "takt"


def test_takt_duenne_datenlage_still():
    from backend.services.datenquellen_validierung import takt_problem
    assert takt_problem([]) is None
    assert takt_problem([100.0, 101.0]) is None          # < 4 Werte
    assert takt_problem([100.0, 100.0, 100.0, 100.0]) is None  # kein Zuwachs


# ─── Bedarfs-Einstufung (§2i-6): ist ein LEERES Feld eine Lücke? ─────────
#
# Anlass: der Rollup „n ohne Quelle" zählte jedes leere Feld und meldete auf
# einer korrekt eingerichteten Anlage lauter Fehlalarm — gemessen 3 von 3
# (PV-Zählerstand, PV gesamt (W), Netz kombiniert sind dort legitim leer).

from backend.services.datenquellen_validierung import stufe_bedarf_ein


def _feld(fid, feld, typ="basis", belegt=False, bedarf="optional",
          gruppe=None, bedingung_anlage=None):
    return {"id": fid, "feld": feld, "typ": typ, "belegt": belegt,
            "bedarf": bedarf, "bedarf_gruppe": gruppe,
            "bedingung_anlage": bedingung_anlage}


def test_leeres_pflichtfeld_ohne_alternative_bleibt_pflicht():
    """Der einzige Fall, der rot werden darf."""
    r = stufe_bedarf_ein([_feld("f1", "einspeisung_kwh", bedarf="pflicht")], set())
    assert r["f1"]["bedarf"] == "pflicht"
    assert r["f1"]["grund"] is None


def test_optionales_feld_bleibt_optional():
    r = stufe_bedarf_ein([_feld("f1", "aussentemperatur_c")], set())
    assert r["f1"]["bedarf"] == "optional"


def test_alternativ_gruppe_deckt_leeres_pflichtfeld_ab():
    """Anlagen-Zählerstand leer, aber ein PV-Modul misst → keine Lücke."""
    felder = [
        _feld("basis_pv", "pv_gesamt_kwh", bedarf="pflicht", gruppe="pv_energie"),
        _feld("mod_pv", "pv_erzeugung_kwh", typ="pv-module", belegt=True,
              bedarf="pflicht", gruppe="pv_energie"),
    ]
    r = stufe_bedarf_ein(felder, {"pv-module"})
    assert r["basis_pv"]["bedarf"] == "inaktiv"
    assert r["basis_pv"]["grund"] == "gruppe:pv_energie"
    assert r["basis_pv"]["text"]
    assert r["mod_pv"]["bedarf"] == "pflicht"  # das belegte Feld bleibt Pflicht


def test_gruppe_komplett_leer_bleibt_offen():
    """Deckt keiner der Wege den Wert ab, ist es sehr wohl eine Lücke."""
    felder = [
        _feld("basis_pv", "pv_gesamt_kwh", bedarf="pflicht", gruppe="pv_energie"),
        _feld("mod_pv", "pv_erzeugung_kwh", typ="pv-module", bedarf="pflicht",
              gruppe="pv_energie"),
    ]
    r = stufe_bedarf_ein(felder, {"pv-module"})
    assert r["basis_pv"]["bedarf"] == "pflicht"
    assert r["mod_pv"]["bedarf"] == "pflicht"


def test_netz_live_gruppe_kombi_gegen_getrennt():
    """`netz_kombi_w` leer ist richtig, wenn Einspeisung/Netzbezug belegt sind
    — genau die Konstellation, die eedc auch rechnerisch so auflöst."""
    felder = [
        _feld("e_w", "einspeisung_w", belegt=True, gruppe="netz_live"),
        _feld("n_w", "netzbezug_w", belegt=True, gruppe="netz_live"),
        _feld("k_w", "netz_kombi_w", gruppe="netz_live"),
    ]
    r = stufe_bedarf_ein(felder, set())
    assert r["k_w"]["bedarf"] == "inaktiv"


def test_wallbox_verdraengt_eauto_heimladung():
    """Phase 2a: mit Wallbox ist die Heimladung am E-Auto nicht zu erfassen."""
    felder = [_feld("ea_pv", "ladung_pv_kwh", typ="e-auto",
                    bedingung_anlage="keine_wallbox")]
    r = stufe_bedarf_ein(felder, {"e-auto", "wallbox"})
    assert r["ea_pv"]["bedarf"] == "inaktiv"
    assert r["ea_pv"]["grund"] == "keine_wallbox"
    assert "Wallbox" in r["ea_pv"]["text"]


def test_ohne_wallbox_ist_eauto_heimladung_normal():
    felder = [_feld("ea_pv", "ladung_pv_kwh", typ="e-auto",
                    bedingung_anlage="keine_wallbox")]
    r = stufe_bedarf_ein(felder, {"e-auto"})
    assert r["ea_pv"]["bedarf"] == "optional"


def test_verdraengtes_aber_belegtes_feld_bleibt_sichtbar_inaktiv():
    """Die ungünstige Kombination: Feld ist verdrängt UND belegt (Altbestand).

    Es darf nicht verschwinden — sonst ließe sich die wirkungslose Zuordnung
    nicht mehr entfernen. `inaktiv` + die bestehende Redundanz-Warnung führen
    den Nutzer zum Aufräumen.
    """
    felder = [_feld("ea_pv", "ladung_pv_kwh", typ="e-auto", belegt=True,
                    bedingung_anlage="keine_wallbox")]
    r = stufe_bedarf_ein(felder, {"e-auto", "wallbox"})
    assert r["ea_pv"]["bedarf"] == "inaktiv"


def test_belegtes_feld_zaehlt_fuer_seine_gruppe_auch_wenn_optional():
    """Ein belegtes optionales Feld deckt die Gruppe ebenfalls ab (PV-Leistung
    je Modul macht „PV gesamt (W)" überflüssig)."""
    felder = [
        _feld("mod_w", "leistung_w", typ="pv-module", belegt=True, gruppe="pv_live"),
        _feld("basis_w", "pv_gesamt_w", gruppe="pv_live"),
    ]
    r = stufe_bedarf_ein(felder, {"pv-module"})
    assert r["basis_w"]["bedarf"] == "inaktiv"
