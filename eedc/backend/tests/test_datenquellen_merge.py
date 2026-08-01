"""Unit-Tests für den extrahierten Datenquellen-Prioritizer (ADR-001).

Spur A des Backend-Refactoring-Plans: die Merge-/Präzedenz-Logik aus
get_aktueller_monat wurde nach core/berechnungen/datenquellen.merge_datenquellen
herausgelöst (verhaltensneutral). Diese Unit-Tests prüfen den Helper isoliert
(kein DB/HA) — die End-to-End-Symmetrie bleibt durch
test_aktueller_monat_datenquellen_prioritaet.py abgedeckt.

Werte sind hier einfache Strings statt (float, DatenquelleInfo)-Tupel — der
Helper ist typ-agnostisch über den Wert.

Die Connector-Abdeckung (Zeitraum, den das Snapshot-Delta wirklich misst) kommt
als eigenes Argument herein und entscheidet im laufenden Monat über
Überschreiben vs. Füllen.
"""

from __future__ import annotations

from datetime import datetime

from backend.core.berechnungen import (
    connector_deckt_monatsanfang,
    merge_datenquellen,
    teilzeitraum_felder,
)

MONAT_START = datetime(2026, 7, 1)
AB_MONATSANFANG = datetime(2026, 6, 30, 23, 55)   # letzter Snapshot vor dem Monat
AB_DEM_28STEN = datetime(2026, 7, 28, 6, 0)       # Connector erst spät eingerichtet


def test_laufender_monat_praezedenz_ha_stats_gewinnt():
    """saved < connector < mqtt < ha_stats: bei Konkurrenz gewinnt ha_stats."""
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector"},
        mqtt_energy={"x": "mqtt"},
        ha_stats={"x": "ha"},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_MONATSANFANG,
        monat_start=MONAT_START,
    )
    assert res["x"] == "ha"


def test_laufender_monat_connector_ohne_hoehere_quellen():
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector"},
        mqtt_energy={},
        ha_stats={},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_MONATSANFANG,
        monat_start=MONAT_START,
    )
    assert res["x"] == "connector"


def test_vergangener_monat_setdefault_kein_override():
    """Abgeschlossener Monat: connector/ha_stats überschreiben saved NICHT."""
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector"},
        mqtt_energy={},  # für vergangene Monate vom Aufrufer leer
        ha_stats={"x": "ha"},
        ist_aktueller_monat=False,
    )
    assert res["x"] == "saved"


def test_vergangener_monat_fuellt_fehlende_felder():
    """Setdefault füllt Felder, die saved nicht hat (connector vor ha_stats)."""
    res = merge_datenquellen(
        saved={"a": "saved"},
        connector={"b": "connector"},
        mqtt_energy={},
        ha_stats={"b": "ha", "c": "ha"},
        ist_aktueller_monat=False,
    )
    assert res["a"] == "saved"
    assert res["b"] == "connector"  # connector kommt vor ha_stats → gewinnt das setdefault
    assert res["c"] == "ha"


def test_disjunkte_quellen_werden_vereinigt():
    res = merge_datenquellen(
        saved={"a": "s"},
        connector={"b": "c"},
        mqtt_energy={"d": "m"},
        ha_stats={"e": "h"},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_MONATSANFANG,
        monat_start=MONAT_START,
    )
    assert res == {"a": "s", "b": "c", "d": "m", "e": "h"}


def test_eingaben_werden_nicht_mutiert():
    saved = {"x": "saved"}
    connector = {"x": "connector"}
    merge_datenquellen(
        saved=saved, connector=connector, mqtt_energy={}, ha_stats={},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_MONATSANFANG, monat_start=MONAT_START,
    )
    assert saved == {"x": "saved"}
    assert connector == {"x": "connector"}


# ---------------------------------------------------------------------------
# Connector-Abdeckung: Teilzeitraum darf keinen Monatswert überschreiben
# ---------------------------------------------------------------------------

def test_laufender_monat_connector_ab_monatsanfang_ueberschreibt():
    """Abdeckung beginnt am (bzw. vor dem) Monatsersten → vollwertiger
    Monatswert, der Connector bleibt die frischere Quelle."""
    res = merge_datenquellen(
        saved={"einspeisung_kwh": "saved"},
        connector={"einspeisung_kwh": "connector"},
        mqtt_energy={},
        ha_stats={},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_MONATSANFANG,
        monat_start=MONAT_START,
    )
    assert res["einspeisung_kwh"] == "connector"


def test_laufender_monat_connector_ab_dem_28sten_ueberschreibt_nicht():
    """Abdeckung beginnt am 28. → das Delta misst drei Tage, nicht den Monat.
    Der gespeicherte Monatswert (Import) bleibt stehen; der Connector füllt
    nur, was sonst fehlen würde."""
    res = merge_datenquellen(
        saved={"einspeisung_kwh": "saved"},
        connector={"einspeisung_kwh": "connector", "netzbezug_kwh": "connector"},
        mqtt_energy={},
        ha_stats={},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_DEM_28STEN,
        monat_start=MONAT_START,
    )
    assert res["einspeisung_kwh"] == "saved"
    assert res["netzbezug_kwh"] == "connector"  # Lücke wird weiterhin gefüllt


def test_laufender_monat_ohne_abdeckung_ueberschreibt_nicht():
    """Ohne Beleg über den gemessenen Zeitraum wird nicht überschrieben."""
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector"},
        mqtt_energy={},
        ha_stats={},
        ist_aktueller_monat=True,
    )
    assert res["x"] == "saved"


def test_abgeschlossener_monat_ignoriert_abdeckung():
    """#325 bleibt unberührt: im abgeschlossenen Monat ist *gespeichert*
    authoritativ, auch wenn die Abdeckung den ganzen Monat umfasst."""
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector", "y": "connector"},
        mqtt_energy={},
        ha_stats={},
        ist_aktueller_monat=False,
        connector_abdeckung_von=AB_MONATSANFANG,
        monat_start=MONAT_START,
    )
    assert res["x"] == "saved"
    assert res["y"] == "connector"


def test_deckt_monatsanfang_grenzfaelle():
    """Genau auf dem Monatsersten zählt als abgedeckt; unbekannt zählt nicht."""
    assert connector_deckt_monatsanfang(MONAT_START, MONAT_START) is True
    assert connector_deckt_monatsanfang(AB_MONATSANFANG, MONAT_START) is True
    assert connector_deckt_monatsanfang(AB_DEM_28STEN, MONAT_START) is False
    assert connector_deckt_monatsanfang(None, MONAT_START) is False
    assert connector_deckt_monatsanfang(AB_MONATSANFANG, None) is False


# ---------------------------------------------------------------------------
# Teilzeitraum-Felder: welcher Gewinner misst nur ein Bruchstück? (#361)
# ---------------------------------------------------------------------------

def test_teilzeitraum_leer_wenn_connector_den_monat_deckt():
    assert teilzeitraum_felder(
        saved={}, connector={"pv_erzeugung_kwh": "c"}, mqtt_energy={}, ha_stats={},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_MONATSANFANG, monat_start=MONAT_START,
    ) == set()


def test_teilzeitraum_nennt_nur_die_felder_die_der_connector_gewinnt():
    """`saved` gewinnt im setdefault-Zweig, HA-Statistik überschreibt im
    laufenden Monat — beides sind keine Bruchstücke mehr."""
    assert teilzeitraum_felder(
        saved={"einspeisung_kwh": "s"},
        connector={
            "einspeisung_kwh": "c", "netzbezug_kwh": "c", "pv_erzeugung_kwh": "c",
        },
        mqtt_energy={},
        ha_stats={"netzbezug_kwh": "h"},
        ist_aktueller_monat=True,
        connector_abdeckung_von=AB_DEM_28STEN, monat_start=MONAT_START,
    ) == {"pv_erzeugung_kwh"}


def test_teilzeitraum_ohne_abdeckungs_angabe():
    """Unbekannte Abdeckung zählt als „deckt nicht" — wie beim Merge."""
    assert teilzeitraum_felder(
        saved={}, connector={"pv_erzeugung_kwh": "c"}, mqtt_energy={}, ha_stats={},
        ist_aktueller_monat=True,
    ) == {"pv_erzeugung_kwh"}


def test_teilzeitraum_leer_ohne_connector():
    assert teilzeitraum_felder(
        saved={"x": "s"}, connector={}, mqtt_energy={}, ha_stats={"x": "h"},
        ist_aktueller_monat=True,
    ) == set()


def test_teilzeitraum_abgeschlossener_monat_ha_stats_fuellt_nur():
    """Im abgeschlossenen Monat greift HA-Statistik per setdefault — sie
    verdrängt einen bereits gesetzten Connector-Wert also nicht, der bleibt
    ein Bruchstück."""
    assert teilzeitraum_felder(
        saved={}, connector={"pv_erzeugung_kwh": "c"}, mqtt_energy={},
        ha_stats={"pv_erzeugung_kwh": "h"},
        ist_aktueller_monat=False,
        connector_abdeckung_von=AB_DEM_28STEN, monat_start=MONAT_START,
    ) == {"pv_erzeugung_kwh"}
