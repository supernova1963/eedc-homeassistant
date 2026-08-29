"""Konformitäts-Wächter: Proben lesen die ECHTE Uhr nur mit Ansage (M5-Rest).

**Anlass N-167.** Vier von 24 Stunden meldeten die Suite rot, ohne dass sich am
Produktcode etwas geändert hätte — Proben, die `datetime.now()` / `date.today()`
lesen, wetten auf die Stunde, in der sie zufällig laufen. Die **Antwort darauf**
ist seit dem 23.08. der Drei-Zonen-Lauf (Berlin · UTC · Pacific/Auckland, lokal
parallel und in CI); er fängt die stundenabhängige Wette, weil er sie in drei
weit auseinanderliegenden Stunden und regelmäßig an zwei verschiedenen Tagen
stellt.

**Was er NICHT kann, und warum dieser Wächter trotzdem existiert:** Die
Kalenderkanten (Monatsende · Jahreswechsel · Schaltjahr · Zeitumstellung) bleiben
ungemessen. ⛔ Sie bleiben es auch — **Gernots Entscheid vom 23.08.2026:
`freezegun` kommt nicht ins Projekt, auch nicht als Dev-Abhängigkeit.** Das ist
die getroffene Wahl, keine Vertagung; wer sie ändern will, bringt eine neue
Messung mit, nicht das alte Argument (Memory `project_freezegun_verworfen`,
`CLAUDE.md` §Gates).

Dieser Wächter tut deshalb genau eine Sache: **er verhindert, dass die 164.
Fundstelle dazukommt.** Er heilt keine der 163 bestehenden — er hält die Zahl
fest, damit sie fallen kann und nicht wieder steigt.

## Warum AST und nicht grep

Der Auftrag (`plans/auftrag-testsuite-etappen.md`, E2/M5-Rest) nannte einen
**grep**-Wächter. Am Baum gemessen wäre das ein Prüfer, der die *richtigen*
Dateien anmeckert: `grep -rlE "datetime\\.now\\(|date\\.today\\("` findet **57**
Dateien, der AST nur **50**. Die sieben Differenzdateien nennen das Muster
ausschließlich in **Kommentar oder Docstring** — mehrere davon schreiben dort
wörtlich, dass sie es bewusst *vermeiden*
(`test_wurzelmuster_p5_invariante.py:53`: „fest verdrahtet statt aus
`date.today()` abgeleitet", `test_n121_monate_ohne_db_spur.py:20`:
„Uhr-Unabhängigkeit … kein `date.today()`"). Ein Wächter, der Vorbildlichkeit
bestraft, wird beim ersten roten Lauf abgeschaltet.

## Warum Alias-Auflösung

`test_solcast_tagesprofile_357.py:335` liest `_date.today()` nach
`from datetime import date as _date`. Ein Prüfer, der nur auf die letzten zwei
Namensteile schaut, sieht dort `_date.today` und lässt es durch — die
Umbenennung wäre das billigste Schlupfloch überhaupt. Die Importe werden deshalb
je Datei aufgelöst.
"""

from __future__ import annotations

import ast
from pathlib import Path

from backend.tests.quellbaum import probenbaum

_TESTS = Path(__file__).resolve().parent

# Die drei Aufrufe, die die Prozessuhr lesen — aufgelöst auf ihre
# `datetime`-Herkunft, nicht auf den im Code sichtbaren Namen.
_UHR_AUFRUFE: frozenset[tuple[str, str]] = frozenset({
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("date", "today"),
})

# ── Baseline (gemessen 2026-08-23: 163 Fundstellen in 50 Dateien) ────────────
#
# Zahl je Datei, nicht nur der Dateiname: sonst dürfte eine bereits gelistete
# Datei beliebig viele neue Wetten dazubekommen. Die Liste ist **abschmelzend** —
# `test_baseline_ist_nicht_zu_hoch` meldet rot, sobald eine Zahl zu GROSS wird,
# und zwingt damit zum Senken statt zum Vergessen. Dieselbe Mechanik wie
# `test_p3a_baseline_ausnahmen_sind_noch_belegt`.
#
# Wer eine Datei hier streicht, hat sie uhr-unabhängig gemacht — das ist die
# einzige erlaubte Richtung.
_BASELINE: dict[str, int] = {
    "test_aggregate_day_restore_provenance_299.py": 1,
    "test_aggregator_290_preserve.py": 3,
    "test_aktueller_monat_datenquellen_prioritaet.py": 6,
    "test_backfill_konsolidierung.py": 6,
    "test_batterie_vorzeichen_historie_check.py": 5,
    "test_bkw_pv_achse_laufender_monat.py": 3,
    "test_bkw_wizard_kwp_f32.py": 1,
    "test_connector_daily_poll_300.py": 2,
    "test_d3_zaehler_flankenpruefungen.py": 2,
    "test_daten_checker_connector_monatswert.py": 1,
    "test_daten_checker_emob_doppelzaehlung_tage.py": 7,
    "test_daten_checker_emob_pool_pflege.py": 1,
    "test_daten_checker_leere_tage_trotz_zaehler.py": 11,
    "test_daten_checker_provenance_detail.py": 2,
    "test_daten_checker_pv_ueber_erfassung.py": 12,
    "test_daten_checker_stilllegung.py": 6,
    "test_daten_checker_wallbox_schwaeche_ab.py": 1,
    "test_daten_checker_zeitzone.py": 1,
    "test_eedc_prognose_kaskade.py": 1,
    "test_etappe_6_drift_check.py": 9,
    "test_f54_cloud_import_kein_phantom_connector.py": 1,
    "test_genauigkeit_ausreisser_296.py": 2,
    "test_genauigkeit_pv_only.py": 4,
    "test_genauigkeit_wetter_296.py": 3,
    "test_ha_export_prognose_150.py": 4,
    "test_ha_export_yaml_rest.py": 1,
    "test_ha_lts_monatswerte_lookup.py": 1,
    "test_ha_statistics_websocket_transport.py": 1,
    "test_hub_leer_grund.py": 2,
    "test_live_pv_zaehler_f49.py": 3,
    "test_migrate_v3_33_0_lts_komponenten_kwh.py": 1,
    "test_monats_luecken_symmetrie.py": 1,
    "test_multi_string_forecast_robustness_306.py": 4,
    "test_prognose_kanon.py": 11,
    # N-317 (29.08.), NEU in dieser Liste — die einzige erlaubte Richtung ist
    # sonst das Streichen, deshalb steht der Grund hier und im Docstring der
    # Probe: Der Pruefling verankert seinen Horizont SELBST an `date.today()`
    # (`get_prognosen_vergleich`), und `pv_invs_im_horizont` filtert die
    # Obermenge gegen genau dieses Fenster. Ein festes Datum in der Fixture
    # leerte die geladene Menge, statt die Probe unabhaengig zu machen — sie
    # prueft dann nichts mehr. Der andere Weg waere ein gestellter Kalender;
    # `freezegun` ist am 23.08.2026 verworfen. Deshalb GENAU EINE Ablesung, in
    # einer Fixture, die alle drei Proben teilen.
    "test_prognose_vergleich_bestand_je_tag.py": 1,
    "test_prognose_kanon_wettermodell_a30.py": 1,
    "test_prognose_modellrand_f36.py": 1,
    "test_pv_anteil_ladung_anschluss.py": 3,
    "test_reaggregate_tag_komponenten_rueckmeldung.py": 2,
    "test_repair_orchestrator.py": 1,
    "test_reparatur_lts_reichweite.py": 1,
    "test_reparatur_werkbank_komponenten_korrektur.py": 3,
    "test_solcast_tagesprofile_357.py": 7,
    "test_speicher_dyn_tarif_und_soc.py": 1,
    "test_speicher_netto_kapazitaet.py": 1,
    "test_symmetrie_aggregator_today.py": 6,
    "test_tag_status_leere_tagessicht.py": 5,
    "test_verbrauchsprofil_slot_konvention.py": 2,
    "test_wp_dashboard_betriebsstunden.py": 1,
    "test_wurzelmuster_p1_orientierung.py": 6,
    "test_wurzelmuster_p4_teilsumme.py": 2,
}


def _alias_karte(baum: ast.Module) -> dict[str, str]:
    """Sichtbarer Name → Herkunftsname aus `datetime`.

    `from datetime import date as _date` ⇒ `{"_date": "date"}`,
    `import datetime as dt` ⇒ `{"dt": "datetime"}`. Ohne diese Karte ist der
    Wächter durch eine Umbenennung zu unterlaufen — und im Bestand gibt es
    genau so eine Stelle.
    """
    karte: dict[str, str] = {}
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for name in knoten.names:
                if name.name.split(".")[0] == "datetime":
                    karte[name.asname or name.name.split(".")[0]] = name.name
        elif isinstance(knoten, ast.ImportFrom) and knoten.module == "datetime":
            for name in knoten.names:
                karte[name.asname or name.name] = name.name
    return karte


def _aufgeloester_pfad(
    knoten: ast.Attribute, karte: dict[str, str]
) -> tuple[str, str] | None:
    """Die letzten zwei Namensteile eines Aufrufziels, Aliase aufgelöst."""
    teile: list[str] = []
    aktuell: ast.expr = knoten
    while isinstance(aktuell, ast.Attribute):
        teile.append(aktuell.attr)
        aktuell = aktuell.value
    if not isinstance(aktuell, ast.Name):
        return None
    teile.append(karte.get(aktuell.id, aktuell.id))
    teile.reverse()
    voll = ".".join(teile).split(".")
    return (voll[-2], voll[-1]) if len(voll) >= 2 else None


def _uhr_fundstellen() -> dict[str, list[str]]:
    """`{Datei: [Datei:Zeile, …]}` aller Lesezugriffe auf die Prozessuhr."""
    treffer: dict[str, list[str]] = {}
    # Quelle: `quellbaum.probenbaum()` — der einzige Prüfer, der den TESTbaum
    # liest statt des Produktivbaums. `rel` dort ist `tests/…`; die Baseline
    # hier führt die Namen ohne dieses Präfix.
    for datei in probenbaum():
        baum = datei.baum
        karte = _alias_karte(baum)
        rel = datei.rel.removeprefix("tests/")
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)):
                continue
            if _aufgeloester_pfad(knoten.func, karte) in _UHR_AUFRUFE:
                treffer.setdefault(rel, []).append(f"{rel}:{knoten.lineno}")
    return treffer


_HINWEIS = (
    "\n\nEine Probe, die die Prozessuhr liest, wettet auf die Stunde ihres Laufs "
    "(N-167: vier von 24 Stunden rot ohne Code-Änderung). Stattdessen ein FESTES "
    "Datum in die Fixture schreiben und es dem Prüfling übergeben — die Suite "
    "läuft in drei Zeitzonen, ein fester Wert ist in allen dreien derselbe.\n"
    "Geht das an einer Stelle wirklich nicht, gehört die Datei mit ihrer neuen "
    "Zahl in _BASELINE — und zwar mit einer Begründung im Docstring der Probe, "
    "nicht kommentarlos."
)


def test_keine_neue_probe_liest_die_echte_uhr():
    """Keine Datei außerhalb der Baseline liest `now()` / `today()`.

    Der Wächter sagt bewusst NICHTS über die 163 bestehenden Stellen — er
    verhindert die 164. Das ist die ganze Zusage; eine größere wäre unwahr,
    solange die Kalenderkanten ohne gestellte Uhr ungemessen bleiben.
    """
    gefunden = _uhr_fundstellen()
    neu = sorted(set(gefunden) - set(_BASELINE))

    assert not neu, (
        "Neue Probe(n) lesen die echte Uhr:\n"
        + "\n".join(f"  {d} ({len(gefunden[d])}×, z. B. {gefunden[d][0]})" for d in neu)
        + _HINWEIS
    )


def test_baseline_datei_bekommt_keine_neue_wette_dazu():
    """Eine gelistete Datei darf nicht MEHR Uhr-Lesezugriffe bekommen.

    Ohne diese Probe wäre die Baseline ein Freibrief je Datei statt je
    Fundstelle: `test_daten_checker_pv_ueber_erfassung.py` steht mit 12 drin und
    dürfte auf 30 wachsen, ohne dass ein Gate rot würde.
    """
    gefunden = _uhr_fundstellen()
    gewachsen = [
        f"  {datei}: Baseline {erlaubt}, gefunden {len(gefunden.get(datei, []))}"
        for datei, erlaubt in sorted(_BASELINE.items())
        if len(gefunden.get(datei, [])) > erlaubt
    ]

    assert not gewachsen, (
        "Uhr-Lesezugriffe über die Baseline hinaus gewachsen:\n"
        + "\n".join(gewachsen)
        + _HINWEIS
    )


def test_baseline_ist_nicht_zu_hoch():
    """Die Baseline schmilzt ab — eine zu hohe Zahl ist selbst ein Fehler.

    Wer eine Probe uhr-unabhängig macht, muss die Zahl senken (oder den Eintrag
    streichen). Sonst deckt der alte Wert später eine neue Wette an derselben
    Stelle ab, und die Liste behauptet einen Rückstand, den es nicht mehr gibt.
    Dieselbe Absicherung wie `test_p3a_baseline_ausnahmen_sind_noch_belegt` —
    und derselbe Grund, aus dem `EXPECTED_ROUTES = 217` gegen 271 reale Routen
    jahrelang nichts mehr gemessen hat (M1).
    """
    gefunden = _uhr_fundstellen()
    zu_hoch = [
        f"  {datei}: Baseline {erlaubt}, tatsächlich "
        f"{len(gefunden.get(datei, []))} — Zahl senken"
        + (" bzw. Eintrag streichen" if not gefunden.get(datei) else "")
        for datei, erlaubt in sorted(_BASELINE.items())
        if len(gefunden.get(datei, [])) < erlaubt
    ]

    assert not zu_hoch, (
        "Baseline steht höher als der Bestand:\n" + "\n".join(zu_hoch)
    )
