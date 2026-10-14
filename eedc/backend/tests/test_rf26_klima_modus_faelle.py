"""RF-26 Fall-Probe: jeder Meldungszweig des Klima-Checks, Reihenfolge und Abfragen.

Der Schnitt von ``_check_klima_modus_sensor`` (RF-26, Serie „Funktion vor Datei", 14.10.2026) ist ein reiner Umzug in derselben
Datei ``services/daten_checker/datenquelle/klima.py``: der Orchestrator lädt (drei ``select``), wählt die Geräte und hängt die
Meldungen an; die früheren Closures und die Meldungslisten sind Modulfunktionen daneben. Die drei DB-Kopien des Golden Masters
lösen keinen INFO-Zweig aus (Vorlage RF-26 §4.3) — diese 57 Fälle sind das Gate des Schnitts und erreichen am HEAD jede der
99 Anweisungen der Funktion. Je Fall eine Anlage mit Wärmepumpen, Monatszeilen und Zuordnung, genau ein Aufruf; geprüft
werden jede Meldung mit allen Feldern **in Reihenfolge** (A „Kühlanteil wird geschätzt" · B „mehrere verschiedene
Modus-Quellen" · C „nicht zugeordnet" bzw. A + die eine OK-Zeile) und die Parameter der Abfragen (das dritte ``select``
lädt nur die Zeilen der heizend-kühlenden Geräte).

Abgedeckte Regeln: #263 K-2 und B2 (Bauart ``luft_luft`` schlägt vor, ODER Kühl-Beleglage über Daten, ``felder``, ``live``
Kühlleistung, ``quellen`` ≠ „keine"; ADR-002 P13 Gruppe 2b) · F-60 (gemessen schlägt abgeleitet, Zuordnung UND gepflegte
Daten) · N-340 (Aufteilung braucht EINE Modus-Quelle; mehrdeutig ≠ nicht zugeordnet) · WK-06/E7 (geschätzter Kühlanteil;
ein Kühl-Zähler — auch in einem anderen Monat — hebt den Hinweis auf) · N-313-Klasse (aktiv an heute).

Schwesterdateien: test_daten_checker_klima_betriebsart.py (F-60), test_daten_checker_modus_quelle_mehrdeutig.py (N-340),
test_daten_checker_geschaetzter_kuehlanteil.py (WK-06), test_263_innengeraete.py (Innengeräte-Keys), test_b2_daten_checker_registry.py
(B2, Kühl-Spur statt Bauart), test_rf19_stammdaten_investitionen_faelle.py (dieselbe Fall-Probe für den Investitions-Check).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import event

from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity, LINK_DATENQUELLEN

# ── Fälle (wortgleich aus der Fall-Probe der Vorlage RF-26) ─────────────────────────────────────────────────────
LL = {"wp_art": "luft_luft"}
LW = {"wp_art": "luft_wasser"}
F5 = {"wp_art": "luft_wasser", "getrennte_strommessung": True}
F5_LL = {"wp_art": "luft_luft", "getrennte_strommessung": True}
ABGELEITET = {"strom_heizen_kwh": 750.0, "strom_warmwasser_kwh": 200.0, "modus_strom_heizen_kwh": 700.0,
              "modus_strom_warmwasser_kwh": 150.0, "modus_strom_kuehlen_kwh": 100.0, "modus_abdeckung_h": 700.0}
SENSOR = lambda e: {"strategie": "sensor", "sensor_id": e}


def wp(i, name, parameter, zeilen=(), aktiv=True, ab=date(2020, 1, 1), bis=None):
    """(id, Bezeichnung, parameter, [verbrauch_daten …], aktiv, Anschaffung, Stilllegung)"""
    return dict(id=i, name=name, parameter=parameter, zeilen=list(zeilen), aktiv=aktiv, ab=ab, bis=bis)


def faelle():
    F = {}
    F["leer"] = ([], {})
    F["luft_wasser_ohne_spur"] = ([wp(1, "WP", LW)], {})
    F["anderer_typ_luft_luft_param"] = ([dict(wp(1, "Akku", LL), typ="speicher")], {})
    F["luft_luft_ohne_modus"] = ([wp(1, "Split", LL)], {})
    F["luft_luft_modus"] = ([wp(1, "Split", LL)], {"investitionen": {"1": {"live": {"betriebsmodus": "climate.a"}}}})
    F["luft_luft_modus_leer"] = ([wp(1, "Split", LL)], {"investitionen": {"1": {"live": {"betriebsmodus": ""}}}})
    F["innengeraete_gleiche_quelle"] = ([wp(1, "Split", LL)], {"investitionen": {"1": {"live": {
        "betriebsmodus-1": "climate.a", "betriebsmodus-2": "climate.a"}}}})
    F["mehrdeutig"] = ([wp(1, "Multi", LL)], {"investitionen": {"1": {"live": {
        "betriebsmodus-1": "climate.a", "betriebsmodus-2": "climate.b"}}}})
    F["mapping_eintrag_kein_dict"] = ([wp(1, "Split", LL)], {"investitionen": {"1": "climate.a"}})
    F["mapping_none"] = ([wp(1, "Split", LL)], {"investitionen": None, "quellen": None})
    F["gemessen_felder"] = ([wp(1, "Split", LL)], {"investitionen": {"1": {"felder": {
        "betriebsart_strom_heizen_kwh": SENSOR("sensor.h")}}}})
    F["gemessen_felder_innengeraet"] = ([wp(1, "Split", LL)], {"investitionen": {"1": {"felder": {
        "betriebsart_strom_lueften_kwh-2": SENSOR("sensor.l2")}}}})
    F["gemessen_felder_ohne_sensor_id"] = ([wp(1, "Split", LL)], {"investitionen": {"1": {"felder": {
        "betriebsart_strom_heizen_kwh": {"strategie": "sensor"}}}}})
    F["gemessen_felder_strategie_manuell"] = ([wp(1, "Split", LL)], {"investitionen": {"1": {"felder": {
        "betriebsart_strom_heizen_kwh": {"strategie": "manuell", "sensor_id": "sensor.h"}, "stromverbrauch_kwh": SENSOR("s")}}}})
    F["gemessen_quellen"] = ([wp(1, "Split", LL)], {"quellen": {"inv_energy_1_betriebsart_strom_heizen_kwh": {"quelle": "mqtt"}}})
    F["gemessen_quellen_keine"] = ([wp(1, "Split", LL)], {"quellen": {"inv_energy_1_betriebsart_strom_heizen_kwh": {"quelle": "keine"}}})
    F["gemessen_quellen_fremdes_geraet"] = ([wp(1, "Split", LL)], {"quellen": {
        "inv_energy_11_betriebsart_strom_heizen_kwh": {"quelle": "mqtt"}, "inv_energy_1_stromverbrauch_kwh": {"quelle": "mqtt"},
        7: {"quelle": "mqtt"}}})
    F["gemessen_daten"] = ([wp(1, "Split", LL, zeilen=[{"betriebsart_strom_heizen_kwh": 12.0}])], {})
    F["gemischt_zwei"] = ([wp(1, "Split A", LL, zeilen=[{"betriebsart_strom_heizen_kwh": 12.0}]), wp(2, "Split B", LL)],
                          {"investitionen": {"2": {"live": {"betriebsmodus": "climate.b"}}}})
    F["abgeleitet_zwei"] = ([wp(1, "Split A", LL), wp(2, "Split B", LL)],
                            {"investitionen": {"1": {"live": {"betriebsmodus": "climate.a"}}, "2": {"live": {"betriebsmodus": "climate.b"}}}})
    F["gemessen_zwei"] = ([wp(1, "Split A", LL, zeilen=[{"betriebsart_strom_heizen_kwh": 1.0}]), wp(2, "Split B", LL)],
                          {"quellen": {"inv_energy_2_betriebsart_strom_kuehlen_kwh": {"quelle": "connector"}}})
    F["einer_ok_einer_ohne"] = ([wp(1, "Split A", LL), wp(2, "Split B", LL)],
                                {"investitionen": {"1": {"live": {"betriebsmodus": "climate.a"}}}})
    # Beleglage (B2): Kühl-Spur an einer Luft-Wasser-WP.
    F["spur_kuehlstrom_daten"] = ([wp(1, "LW", LW, zeilen=[{"betriebsart_strom_kuehlen_kwh": 4.0}])], {})
    F["spur_kuehlstrom_daten_innengeraet"] = ([wp(1, "LW", LW, zeilen=[{"betriebsart_strom_kuehlen_kwh-2": 4.0}])], {})
    F["spur_kaeltemenge_daten"] = ([wp(1, "LW", LW, zeilen=[{"betriebsart_nutzenergie_kuehlen_kwh": 9.0}])], {})
    F["spur_kaeltemenge_null"] = ([wp(1, "LW", LW, zeilen=[{"betriebsart_nutzenergie_kuehlen_kwh": 0.0}])], {})
    F["spur_zeile_ohne_daten"] = ([wp(1, "LW", LW, zeilen=[None])], {})
    F["spur_felder_kaeltemenge"] = ([wp(1, "LW", LW)], {"investitionen": {"1": {"felder": {
        "betriebsart_nutzenergie_kuehlen_kwh": SENSOR("sensor.k")}}}})
    F["spur_felder_kaeltemenge_ohne_sensor"] = ([wp(1, "LW", LW)], {"investitionen": {"1": {"felder": {
        "betriebsart_nutzenergie_kuehlen_kwh": {"strategie": "sensor", "sensor_id": ""}}}}})
    F["spur_felder_kuehlstrom_innengeraet"] = ([wp(1, "LW", LW)], {"investitionen": {"1": {"felder": {
        "betriebsart_strom_kuehlen_kwh-1": SENSOR("sensor.k1")}}}})
    F["spur_live_kuehlleistung"] = ([wp(1, "LW", LW)], {"investitionen": {"1": {"live": {"leistung_kuehlen_w-3": "sensor.p"}}}})
    F["spur_live_kuehlleistung_leer"] = ([wp(1, "LW", LW)], {"investitionen": {"1": {"live": {"leistung_kuehlen_w": None}}}})
    F["spur_quellen"] = ([wp(1, "LW", LW)], {"quellen": {"inv_energy_1_betriebsart_nutzenergie_kuehlen_kwh": {"quelle": "mqtt"}}})
    F["spur_quellen_keine"] = ([wp(1, "LW", LW)], {"quellen": {"inv_energy_1_betriebsart_nutzenergie_kuehlen_kwh": {"quelle": "keine"}}})
    F["spur_quellen_kein_dict"] = ([wp(1, "LW", LW)], {"quellen": {"inv_energy_1_betriebsart_nutzenergie_kuehlen_kwh": "mqtt"}})
    F["spur_quellen_none"] = ([wp(1, "LW", LW)], {"quellen": {"inv_energy_1_betriebsart_nutzenergie_kuehlen_kwh": None}})
    F["spur_und_modus"] = ([wp(1, "LW", LW)], {"investitionen": {"1": {"live": {"leistung_kuehlen_w": "sensor.p", "betriebsmodus": "climate.x"}}}})
    # Prüfung A (WK-06): geschätzter Kühlanteil.
    F["geschaetzt_f5_ohne_klimas"] = ([wp(1, "WP F5", F5, zeilen=[ABGELEITET])], {})
    F["geschaetzt_f5_luft_luft_modus"] = ([wp(1, "Split F5", F5_LL, zeilen=[ABGELEITET])],
                                          {"investitionen": {"1": {"live": {"betriebsmodus": "climate.a"}}}})
    F["geschaetzt_mit_kuehlzaehler_daten"] = ([wp(1, "WP F5", F5, zeilen=[dict(ABGELEITET, betriebsart_strom_kuehlen_kwh=90.0)])], {})
    F["geschaetzt_mit_kuehlzaehler_felder"] = ([wp(1, "WP F5", F5, zeilen=[ABGELEITET])], {"investitionen": {"1": {"felder": {
        "betriebsart_strom_kuehlen_kwh": SENSOR("sensor.k")}}}})
    F["geschaetzt_mit_kuehlzaehler_quellen"] = ([wp(1, "WP F5", F5, zeilen=[ABGELEITET])], {"quellen": {
        "inv_energy_1_betriebsart_strom_kuehlen_kwh": {"quelle": "mqtt"}}})
    F["geschaetzt_kuehlzaehler_anderer_monat"] = ([wp(1, "WP F5", F5, zeilen=[ABGELEITET, {"betriebsart_strom_kuehlen_kwh": 5.0}])], {})
    F["geschaetzt_nur_kaeltemenge"] = ([wp(1, "WP F5", F5, zeilen=[dict(ABGELEITET, betriebsart_nutzenergie_kuehlen_kwh=300.0)])], {})
    F["geschaetzt_ohne_abdeckung"] = ([wp(1, "WP F5", F5, zeilen=[dict(ABGELEITET, modus_abdeckung_h=0.0)])], {})
    F["geschaetzt_ohne_kuehlanteil"] = ([wp(1, "WP F5", F5, zeilen=[dict(ABGELEITET, modus_strom_kuehlen_kwh=0.0)])], {})
    F["geschaetzt_ohne_f5"] = ([wp(1, "WP", LW, zeilen=[ABGELEITET])], {})
    F["geschaetzt_zeile_fremdes_geraet"] = ([wp(1, "WP F5", F5), wp(2, "WP zwei", LW, zeilen=[ABGELEITET])], {})
    F["geschaetzt_parameter_none"] = ([wp(1, "WP", None, zeilen=[ABGELEITET])], {})
    F["geschaetzt_zwei_geraete"] = ([wp(1, "WP A", F5, zeilen=[ABGELEITET]), wp(2, "WP B", F5, zeilen=[ABGELEITET])], {})
    # Aktiv-Filter (N-313-Klasse).
    F["inaktiv_haken"] = ([wp(1, "Split", LL, aktiv=False)], {})
    F["stillgelegt"] = ([wp(1, "Split", LL, bis=date(2021, 1, 1))], {})
    F["noch_nicht_angeschafft"] = ([wp(1, "Split", LL, ab=date(2099, 1, 1))], {})
    F["stillgelegt_mit_f5"] = ([wp(1, "WP F5", F5, zeilen=[ABGELEITET], bis=date(2021, 1, 1))], {})
    # Reihenfolge: A, dann B, dann C — und mehrere je Liste.
    F["alle_drei_listen"] = ([wp(1, "Split F5", F5_LL, zeilen=[ABGELEITET]), wp(2, "Multi", LL), wp(3, "Ohne", LL),
                              wp(4, "Ohne zwei", LL), wp(5, "Multi zwei", LL)],
                             {"investitionen": {
                                 "2": {"live": {"betriebsmodus-1": "climate.a", "betriebsmodus-2": "climate.b"}},
                                 "5": {"live": {"betriebsmodus-1": "climate.c", "betriebsmodus-3": "climate.d"}}}})
    F["a_plus_ok_gemischt"] = ([wp(1, "Split F5", F5_LL, zeilen=[ABGELEITET]), wp(2, "Gemessen", LL,
                                zeilen=[{"betriebsart_strom_heizen_kwh": 3.0}])],
                               {"investitionen": {"1": {"live": {"betriebsmodus": "climate.a"}}}})
    # Das dritte `select` lädt nur die Zeilen der `klimas`, nicht aller aktiven (SQL-Parameter sichtbar).
    F["klima_und_nicht_klima"] = ([wp(1, "Split", LL), wp(2, "LW", LW, zeilen=[{"strom_kwh": 1.0}])],
                                  {"investitionen": {"1": {"live": {"betriebsmodus": "climate.a"}}}})
    return F

FAELLE = faelle()

# ── Erwartung (aufgezeichnet am HEAD vor dem Schnitt, `e0e6cf71`) ───────────────────────────────────────────────

_TITEL = {
    "A": "Kühlanteil wird geschätzt — es fehlt ein Stromzähler für den Kühlbetrieb",
    "B": "mehrere verschiedene Modus-Quellen — eedc teilt den Strom nicht auf",
    "C": "Betriebsmodus nicht zugeordnet — Heiz- und Kühlstrom bleiben zusammen",
}
_DETAILS = {
    'A': (
        'Deine Wärmepumpe misst Heizen und Warmwasser getrennt und teilt zusätzlich aus dem Betriebsmodus '
        'auf. Für den Kühlbetrieb gibt es aber keinen eigenen Stromzähler — eedc muss den Kühlanteil deshalb '
        'aus der Summe der beiden anderen Zähler schätzen. Die Mengen stimmen weiterhin: Verbrauch, Kosten '
        'und CO₂ rechnen mit dem vollen Strom. Nur die Aufteilung nach Betriebsart ist eine Verteilung und '
        'keine Messung, und deshalb kürzt sie die Arbeitszahl nicht. Ordne „Strom Kühlbetrieb“ zu, dann liest '
        'eedc ab, statt zu verteilen: Einstellungen → Datenquellen, beim Gerät das Feld „Strom Kühlbetrieb“. '
        'Das ist freiwillig — ohne die Zuordnung bleibt alles wie bisher.'
    ),
    'B': (
        'Du hast den Betriebsmodus an mehreren Innengeräten zugeordnet, und sie zeigen auf verschiedene '
        'Entitäten. Der Stromzähler dieses Geräts ist aber einer — für die Aufteilung braucht eedc deshalb '
        'genau eine Aussage darüber, was die ANLAGE gerade tut. Aus mehreren Innengeräte-Zuständen einen '
        'Anlagen-Zustand zu bilden, hängt an deiner Anlage: ob ein Innengerät lüften kann, während ein '
        'anderes heizt, ob das Außengerät beim Enteisen etwas meldet. Das weiß eedc nicht, und es rät nicht. '
        'Zwei Wege: Ordne dieselbe climate-Entität bei allen Innengeräten zu — dann ist es eine Quelle (bei '
        'einer Ein-Kreis-Anlage gibt ohnehin das Außengerät die Richtung vor). Oder baue in Home Assistant '
        'einen Template-Sensor, der deine Innengeräte zu einer Aussage zusammenfasst, und ordne dessen '
        'Ergebnis zu — die Vorlage steht im Handbuch unter „Wärme & Klima“. Bis dahin bleibt alles wie '
        'bisher, der Stromverbrauch zählt vollständig.'
    ),
    'C': (
        'Dieses Gerät heizt und kühlt über denselben Zähler. eedc sieht deshalb nur eine Zahl und kann nicht '
        'sagen, welcher Teil des Stroms ins Heizen ging und welcher ins Kühlen — aus den vorhandenen Werten '
        'lässt sich das nicht nachrechnen. Ordne dafür die climate-Entität des Geräts zu (in Home Assistant '
        'meist „climate.…“, sie zeigt Heizen/Kühlen/Aus): Einstellungen → Datenquellen, beim Gerät das Feld '
        '„Betriebsmodus“. Das ist freiwillig — ohne die Zuordnung bleibt alles wie bisher, der Stromverbrauch '
        'zählt vollständig. Ein Hinweis zur Erwartung: Die Aufteilung beginnt mit der Zuordnung und lässt '
        'sich nicht rückwirkend nachtragen.'
    ),
    'OK_GEMESSEN': (
        'Der Verbrauch je Betriebsart kommt gemessen aus deinen Zählern — eedc rechnet ihn nicht aus dem '
        'Betriebsmodus, sondern liest ihn ab.'
    ),
    'OK_ABGELEITET': (
        'eedc schreibt damit stündlich mit, ob das Gerät geheizt oder gekühlt hat, und kann den '
        'Stromverbrauch entsprechend aufteilen.'
    ),
    'OK_GEMISCHT': (
        'Bei einem Teil der Geräte kommt der Verbrauch je Betriebsart gemessen aus Zählern, beim Rest leitet '
        'eedc ihn stündlich aus dem Betriebsmodus ab.'
    ),
}

# Je Fall: Meldungen in Reihenfolge — (Art, Gerät bzw. OK-Titel, investition_id) — und die Parameter der Abfragen
# nach der Geräteabfrage `(1, 'waermepumpe')`: Zeilen aller aktiven Geräte, ggf. Zeilen der heizend-kühlenden Geräte.
ERWARTET = {
    'leer': ([], [(-1,)]),
    'luft_wasser_ohne_spur': ([], [(1,)]),
    'anderer_typ_luft_luft_param': ([], [(-1,)]),
    'luft_luft_ohne_modus': ([('C', 'Split', 1)], [(1,), (1,)]),
    'luft_luft_modus': ([('OK_ABGELEITET', 'Betriebsmodus ist zugeordnet bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'luft_luft_modus_leer': ([('C', 'Split', 1)], [(1,), (1,)]),
    'innengeraete_gleiche_quelle': ([('OK_ABGELEITET', 'Betriebsmodus ist zugeordnet bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'mehrdeutig': ([('B', 'Multi', 1)], [(1,), (1,)]),
    'mapping_eintrag_kein_dict': ([('C', 'Split', 1)], [(1,), (1,)]),
    'mapping_none': ([('C', 'Split', 1)], [(1,), (1,)]),
    'gemessen_felder': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'gemessen_felder_innengeraet': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'gemessen_felder_ohne_sensor_id': ([('C', 'Split', 1)], [(1,), (1,)]),
    'gemessen_felder_strategie_manuell': ([('C', 'Split', 1)], [(1,), (1,)]),
    'gemessen_quellen': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'gemessen_quellen_keine': ([('C', 'Split', 1)], [(1,), (1,)]),
    'gemessen_quellen_fremdes_geraet': ([('C', 'Split', 1)], [(1,), (1,)]),
    'gemessen_daten': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'gemischt_zwei': ([('OK_GEMISCHT', 'Heiz- und Kühlstrom werden getrennt bei allen 2 heizend-kühlenden Gerät(en)', None)], [(1, 2), (1, 2)]),
    'abgeleitet_zwei': ([('OK_ABGELEITET', 'Betriebsmodus ist zugeordnet bei allen 2 heizend-kühlenden Gerät(en)', None)], [(1, 2), (1, 2)]),
    'gemessen_zwei': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei allen 2 heizend-kühlenden Gerät(en)', None)], [(1, 2), (1, 2)]),
    'einer_ok_einer_ohne': ([('C', 'Split B', 2)], [(1, 2), (1, 2)]),
    'spur_kuehlstrom_daten': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'spur_kuehlstrom_daten_innengeraet': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'spur_kaeltemenge_daten': ([('C', 'LW', 1)], [(1,), (1,)]),
    'spur_kaeltemenge_null': ([('C', 'LW', 1)], [(1,), (1,)]),
    'spur_zeile_ohne_daten': ([], [(1,)]),
    'spur_felder_kaeltemenge': ([('C', 'LW', 1)], [(1,), (1,)]),
    'spur_felder_kaeltemenge_ohne_sensor': ([], [(1,)]),
    'spur_felder_kuehlstrom_innengeraet': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'spur_live_kuehlleistung': ([('C', 'LW', 1)], [(1,), (1,)]),
    'spur_live_kuehlleistung_leer': ([], [(1,)]),
    'spur_quellen': ([('C', 'LW', 1)], [(1,), (1,)]),
    'spur_quellen_keine': ([], [(1,)]),
    'spur_quellen_kein_dict': ([], [(1,)]),
    'spur_quellen_none': ([], [(1,)]),
    'spur_und_modus': ([('OK_ABGELEITET', 'Betriebsmodus ist zugeordnet bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'geschaetzt_f5_ohne_klimas': ([('A', 'WP F5', 1)], [(1,)]),
    'geschaetzt_f5_luft_luft_modus': ([('A', 'Split F5', 1), ('OK_ABGELEITET', 'Betriebsmodus ist zugeordnet bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'geschaetzt_mit_kuehlzaehler_daten': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'geschaetzt_mit_kuehlzaehler_felder': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'geschaetzt_mit_kuehlzaehler_quellen': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'geschaetzt_kuehlzaehler_anderer_monat': ([('OK_GEMESSEN', 'Betriebsart wird gemessen bei 1 heizend-kühlenden Gerät(en)', None)], [(1,), (1,)]),
    'geschaetzt_nur_kaeltemenge': ([('A', 'WP F5', 1), ('C', 'WP F5', 1)], [(1,), (1,)]),
    'geschaetzt_ohne_abdeckung': ([], [(1,)]),
    'geschaetzt_ohne_kuehlanteil': ([], [(1,)]),
    'geschaetzt_ohne_f5': ([], [(1,)]),
    'geschaetzt_zeile_fremdes_geraet': ([], [(1, 2)]),
    'geschaetzt_parameter_none': ([], [(1,)]),
    'geschaetzt_zwei_geraete': ([('A', 'WP A', 1), ('A', 'WP B', 2)], [(1, 2)]),
    'inaktiv_haken': ([], [(-1,)]),
    'stillgelegt': ([], [(-1,)]),
    'noch_nicht_angeschafft': ([], [(-1,)]),
    'stillgelegt_mit_f5': ([], [(-1,)]),
    'alle_drei_listen': ([('A', 'Split F5', 1), ('B', 'Multi', 2), ('B', 'Multi zwei', 5), ('C', 'Split F5', 1), ('C', 'Ohne', 3), ('C', 'Ohne zwei', 4)], [(1, 2, 3, 4, 5), (1, 2, 3, 4, 5)]),
    'a_plus_ok_gemischt': ([('A', 'Split F5', 1), ('OK_GEMISCHT', 'Heiz- und Kühlstrom werden getrennt bei allen 2 heizend-kühlenden Gerät(en)', None)], [(1, 2), (1, 2)]),
    'klima_und_nicht_klima': ([('OK_ABGELEITET', 'Betriebsmodus ist zugeordnet bei 1 heizend-kühlenden Gerät(en)', None)], [(1, 2), (1,)]),
}


def _erwartete_meldung(art: str, text: str, inv_id):
    if art in _TITEL:
        return dict(kategorie=CheckKategorie.KLIMA_MODUS_SENSOR, schwere=CheckSeverity.INFO, meldung=f"„{text}“: {_TITEL[art]}",
                    details=_DETAILS[art], link=LINK_DATENQUELLEN, action_kind=None, action_params=None, action_label=None,
                    investition_id=inv_id)
    return dict(kategorie=CheckKategorie.KLIMA_MODUS_SENSOR, schwere=CheckSeverity.OK, meldung=text, details=_DETAILS[art],
                link=None, action_kind=None, action_params=None, action_label=None, investition_id=None)


async def _lauf(db, geraete, sensor_mapping):
    anlage = Anlage(id=1, anlagenname="Fall", leistung_kwp=10.0, installationsdatum=date(2020, 1, 1))
    db.add(anlage)
    await db.flush()
    for g in geraete:
        db.add(Investition(id=g["id"], anlage_id=1, typ=g.get("typ", "waermepumpe"), bezeichnung=g["name"],
                           anschaffungsdatum=g["ab"], stilllegungsdatum=g["bis"], aktiv=g["aktiv"], parameter=g["parameter"]))
    await db.flush()
    for g in geraete:
        for k, v in enumerate(g["zeilen"]):
            db.add(InvestitionMonatsdaten(investition_id=g["id"], jahr=2025, monat=k + 1, verbrauch_daten=v))
    anlage.sensor_mapping = sensor_mapping or None
    await db.commit()
    db.expunge_all()
    anlage = await db.get(Anlage, 1)
    params: list = []

    def _sql(conn, cursor, statement, parameters, context, executemany):
        params.append(parameters)

    engine = db.bind.sync_engine
    event.listen(engine, "before_cursor_execute", _sql)
    try:
        res = await DatenChecker(db)._check_klima_modus_sensor(anlage)
    finally:
        event.remove(engine, "before_cursor_execute", _sql)
    return res, params


def test_jeder_fall_hat_eine_erwartung():
    assert set(FAELLE) == set(ERWARTET)
    assert len(FAELLE) == 57


@pytest.mark.parametrize("name", list(FAELLE))
async def test_fall(db, name):
    geraete, sensor_mapping = FAELLE[name]
    res, params = await _lauf(db, geraete, sensor_mapping)
    zeilen, abfragen = ERWARTET[name]
    ist = [dict(kategorie=e.kategorie, schwere=e.schwere, meldung=e.meldung, details=e.details, link=e.link,
                action_kind=e.action_kind, action_params=e.action_params, action_label=e.action_label,
                investition_id=e.investition_id) for e in res]
    assert ist == [_erwartete_meldung(*z) for z in zeilen]
    assert [tuple(p) for p in params] == [(1, "waermepumpe"), *abfragen]
