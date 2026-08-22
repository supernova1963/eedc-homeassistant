"""
Akzeptanztest Nachlauf v4.0.3 — die Reparatur-Brücke:
`DatenChecker._check_leere_tage_trotz_zaehler()` meldet Tage, an denen ein
kWh-Zähler zugeordnet ist und HA-Statistics einen Tageswert liefert, die
gespeicherte `TagesZusammenfassung` aber leer/0 ist. Aktion: Bereichs-Knopf
(`reaggregate_range`, max. 31 Tage/Lauf) plus Einzeltag-Knöpfe
(`reaggregate_day`) — user-getriggert, nie als Start-Migration.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_daten_checker_leere_tage_trotz_zaehler.py

Testet:
  1. Basis-Zähler zugeordnet, Tageszeile 0, HA hat Werte → Befund + beide Aktionen
  2. Tageszeile fehlt ganz → Befund (dort zählt auch PV, der Drift-Check ist blind)
  3. #311-Gegenprobe: HA liefert nichts → KEIN Befund, ehrliche OK-Meldung
  4. Gegenprobe: Tageszeile gefüllt → OK ohne einen einzigen LTS-Read
  5. Kein zweiter Turm: vorhandene Zeile mit PV 0 → kein Befund (DATENQUELLE_DRIFT)
  6. Standalone (kein HA-LTS) → leer
  7. Kein Zähler zugeordnet → leer
  8. Span > 31 Tage → Bereichs-Fenster begrenzt, Rest genannt, 15 Einzeltage
  9. Ohne Leistungs-Zuordnung: Befund ja, Knopf nein (E2E 2026-07-30)
 10. Standalone: MQTT-Energie ersetzt die W-Zuordnung → Knopf wieder da
 11. Abfrage-Budget (45 LTS-Reads/Lauf) wird gedeckelt UND benannt
 12. Vor Inbetriebnahme wird nicht gemeldet

N-57 (Forum simon42 #89667/83, dietmar1968) — der Check darf nur anbieten, was
`aggregate_day` einlösen kann. Der Lauf lädt seine Investitionen mit
`aktiv_am_tag(datum)`; die erwartete Schlüsselmenge ist deshalb **tagesabhängig**:

 13. `aktiv=False` → nicht gemeldet, aktive Nachbar-Komponente aber schon
 14. Anschaffungsdatum mitten im Fenster → davor still, danach gemeldet
 15. Stilllegung mitten im Fenster → spiegelbildlich, Stilllegungstag inklusiv
 16. dietmars Konstellation (inaktiv UND Anschaffung in der Zukunft) → kein Knopf
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.models.investition import Investition  # noqa: E402
from backend.services.daten_checker import DatenChecker, CheckKategorie  # noqa: E402

_KAT = CheckKategorie.TAGESWERTE_FEHLEN.value

_SENSOR = {"strategie": "sensor", "sensor_id": "sensor.x"}


def _make_anlage(*, mit_pv=True, installationsdatum=None, mit_live=True,
                 wp_ids=()):
    mapping = {
        "basis": {"einspeisung": dict(_SENSOR), "netzbezug": dict(_SENSOR)},
    }
    if mit_live:
        # Ohne Leistungs-Zuordnung kann `aggregate_day` nichts holen — der Check
        # bietet dann bewusst keinen Knopf an (E2E 2026-07-30).
        mapping["basis"]["live"] = {"einspeisung_w": "sensor.netz_w"}
    investitionen = {}
    if mit_pv:
        investitionen["7"] = {"felder": {"pv_erzeugung_kwh": dict(_SENSOR)}}
    for wp_id in wp_ids:
        # Wärmepumpe statt PV, wo der Lebensdauer-Filter geprüft wird: PV-Keys
        # gehören auf einer VORHANDENEN Tageszeile dem Drift-Check (kein zweiter
        # Turm) und würden den Befund aus einem anderen Grund verschlucken.
        investitionen[str(wp_id)] = {"felder": {"stromverbrauch_kwh": dict(_SENSOR)}}
    if investitionen:
        mapping["investitionen"] = investitionen
    return SimpleNamespace(
        id=1,
        sensor_mapping=mapping,
        installationsdatum=installationsdatum,
    )


def _make_anlage_ohne_zaehler():
    return SimpleNamespace(id=1, sensor_mapping={}, installationsdatum=None)


def _make_inv(inv_id=7, typ="pv-module", bezeichnung="Dach Süd",
              aktiv=True, anschaffungsdatum=None, stilllegungsdatum=None):
    """Echtes Model-Objekt (nicht persistiert) — der Check ruft `ist_aktiv_an`.

    Ein Double mit eigener Aktiv-Logik wäre genau die zweite Definition, gegen
    die N-57 antritt.
    """
    return Investition(
        id=inv_id, anlage_id=1, typ=typ, parameter={},
        bezeichnung=bezeichnung, parent_investition_id=None,
        aktiv=aktiv, anschaffungsdatum=anschaffungsdatum,
        stilllegungsdatum=stilllegungsdatum,
    )


def _make_tz(datum: date, komponenten: dict):
    return SimpleNamespace(id=1, anlage_id=1, datum=datum, komponenten_kwh=komponenten)


async def _run_check(anlage, tz_list, invs_list, ha_func, ha_available=True,
                     mqtt_energie=False):
    """db.execute-Reihenfolge im SUT: 1) Investition, 2) TagesZusammenfassung,
    3) MqttEnergySnapshot (nur wenn kein Live-Mapping vorliegt).

    `mqtt_energie` steuert den dritten Aufruf: im Standalone-Betrieb ersetzt
    MQTT-Energie die Leistungs-Zuordnung als Vorbedingung von `aggregate_day`.
    """
    db = MagicMock()
    call_count = {"n": 0}
    lts_reads = {"n": 0}

    async def _execute(stmt):
        result = MagicMock()
        call_count["n"] += 1
        scalars = MagicMock()
        scalars.all = MagicMock(
            return_value=invs_list if call_count["n"] == 1 else tz_list
        )
        result.scalars = MagicMock(return_value=scalars)
        result.scalar_one_or_none = MagicMock(
            return_value=1 if mqtt_energie else None
        )
        return result

    db.execute = _execute
    checker = DatenChecker(db)

    ha_svc = MagicMock()
    ha_svc.is_available = ha_available

    async def _ha_lts(_anlage, _invs, datum):
        lts_reads["n"] += 1
        return ha_func(datum)

    patches = [
        patch("backend.services.ha_statistics_service.get_ha_statistics_service",
              return_value=ha_svc),
        patch("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
              side_effect=_ha_lts),
    ]
    for p in patches:
        p.start()
    try:
        return await checker._check_leere_tage_trotz_zaehler(anlage), lts_reads["n"]
    finally:
        for p in patches:
            p.stop()


def _gestern() -> date:
    return date.today() - timedelta(days=1)


_VOLL = {"einspeisung": 20.0, "netzbezug": 2.0, "pv_7": 30.0}


def _volle_zeilen(ab_tag: int, bis_tag: int = 90) -> list:
    """Gefüllte Tageszeilen, damit nur die interessanten Tage Kandidaten sind."""
    return [
        _make_tz(date.today() - timedelta(days=i), dict(_VOLL))
        for i in range(ab_tag, bis_tag + 1)
    ]


async def test_basis_zaehler_leer_wird_gemeldet():
    """Einspeisung/Netzbezug stehen auf 0, HA hat Werte → Befund mit beiden Aktionen.

    Das ist pipp086s Fall (Forum #44): PV kommt durch, die zwei Basis-Zähler nicht.
    """
    tag = _gestern()
    tz_list = [
        _make_tz(tag, {"pv_7": 29.0, "einspeisung": 0.0, "netzbezug": 0.0}),
        *_volle_zeilen(2),
    ]
    ha_func = lambda d: {"einspeisung": 22.0, "netzbezug": 3.4, "pv_7": 29.0}
    result, reads = await _run_check(_make_anlage(), tz_list, [_make_inv()], ha_func)
    assert reads == 1, f"Nur der eine Verdachts-Tag darf HA kosten, waren {reads}"

    range_eintraege = [r for r in result if r.action_kind == "reaggregate_range"]
    assert len(range_eintraege) == 1, f"Erwartet 1 Bereichs-Eintrag, bekommen {result}"
    re_ = range_eintraege[0]
    assert re_.kategorie == _KAT
    assert re_.schwere == "warning"
    assert re_.action_params == {
        "anlage_id": 1, "von": tag.isoformat(), "bis": tag.isoformat(),
    }, f"params: {re_.action_params}"
    assert re_.action_label == "Zeitraum neu aggregieren"
    # Reichweite muss benannt sein: Tag/Stunden ja, Monatswerte nein.
    assert "NICHT die Monatswerte" in re_.details, re_.details
    assert "Statistik-Import" in re_.details, re_.details

    day_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert len(day_eintraege) == 1, f"Erwartet 1 Einzeltag, bekommen {len(day_eintraege)}"
    assert day_eintraege[0].action_params == {"anlage_id": 1, "datum": tag.isoformat()}
    # Die Meldung nennt, was HA hat — sonst ist der Knopf ein Blindflug.
    assert "22.0 kWh" in day_eintraege[0].meldung, day_eintraege[0].meldung


async def test_fehlende_tageszeile_wird_gemeldet():
    """Gar keine TagesZusammenfassung → Befund; dort zählt auch PV mit."""
    tag = _gestern()
    ha_func = lambda d: {"einspeisung": 20.0, "netzbezug": 2.0, "pv_7": 30.0}
    result, _ = await _run_check(_make_anlage(), _volle_zeilen(2), [_make_inv()], ha_func)

    range_eintraege = [r for r in result if r.action_kind == "reaggregate_range"]
    assert len(range_eintraege) == 1, f"Erwartet Befund, bekommen {result}"
    # PV taucht in der Aufzählung auf (Bezeichnung statt Roh-Key)
    assert "Dach Süd" in range_eintraege[0].details, range_eintraege[0].details
    day_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert len(day_eintraege) >= 1
    assert any(d.action_params["datum"] == tag.isoformat() for d in day_eintraege)


async def test_ha_liefert_nichts_kein_befund():
    """#311: fehlende LTS-Lesbarkeit ist „nicht gelesen", nie „= 0".

    Sonst böte der Check einen Knopf an, der korrekte Werte mit 0 überschreibt.
    """
    tz_list = [
        _make_tz(_gestern(), {"einspeisung": 0.0, "netzbezug": 0.0, "pv_7": 29.0}),
        *_volle_zeilen(2),
    ]
    ha_func = lambda d: {}
    result, _ = await _run_check(_make_anlage(), tz_list, [_make_inv()], ha_func)

    assert not any(r.action_kind for r in result), f"Kein Knopf erwartet: {result}"
    assert len(result) == 1 and result[0].schwere == "ok", result
    assert "nicht mehr füllen" in result[0].details, result[0].details


async def test_gefuellter_tag_ohne_lts_read():
    """Alles da → OK, und zwar OHNE eine einzige HA-Abfrage (DB-Vorfilter)."""
    tz_list = [
        _make_tz(date.today() - timedelta(days=i),
                 {"einspeisung": 20.0, "netzbezug": 2.0, "pv_7": 30.0})
        for i in range(1, 91)
    ]
    ha_func = lambda d: {"einspeisung": 20.0}
    result, reads = await _run_check(_make_anlage(), tz_list, [_make_inv()], ha_func)

    assert reads == 0, f"Gesunde Anlage darf HA nicht abfragen, waren {reads} Reads"
    assert len(result) == 1 and result[0].schwere == "ok", result


async def test_pv_null_auf_vorhandener_zeile_ist_drift_check_turf():
    """Kein zweiter Turm: PV 0 bei gefüllten Basis-Zählern gehört DATENQUELLE_DRIFT."""
    tz_list = [
        _make_tz(date.today() - timedelta(days=i),
                 {"einspeisung": 20.0, "netzbezug": 2.0, "pv_7": 0.0})
        for i in range(1, 91)
    ]
    ha_func = lambda d: {"einspeisung": 20.0, "netzbezug": 2.0, "pv_7": 30.0}
    result, reads = await _run_check(_make_anlage(), tz_list, [_make_inv()], ha_func)

    assert reads == 0, f"Kein LTS-Read nötig, waren {reads}"
    assert not any(r.action_kind for r in result), f"Kein Knopf erwartet: {result}"
    assert len(result) == 1 and result[0].schwere == "ok", result


async def test_standalone_leer():
    """Kein HA-LTS → keine Referenz → leer, kein Crash."""
    tz_list = [_make_tz(_gestern(), {"einspeisung": 0.0})]
    ha_func = lambda d: {"einspeisung": 22.0}
    result, _ = await _run_check(
        _make_anlage(), tz_list, [_make_inv()], ha_func, ha_available=False,
    )
    assert result == [], f"Erwartet leer im Standalone, bekommen {result}"


async def test_ohne_zaehler_leer():
    """Kein kWh-Zähler zugeordnet → die Kategorie verspricht nichts → leer."""
    ha_func = lambda d: {"einspeisung": 22.0}
    result, reads = await _run_check(_make_anlage_ohne_zaehler(), [], [], ha_func)
    assert result == [], f"Erwartet leer, bekommen {result}"
    assert reads == 0


async def test_span_groesser_31_fenster_begrenzt():
    """40 leere Tage → Bereichs-Knopf nur jüngstes 31-Tage-Fenster, Rest benannt."""
    today = date.today()
    tz_list = [
        _make_tz(today - timedelta(days=i), {"einspeisung": 0.0, "netzbezug": 0.0,
                                             "pv_7": 30.0})
        for i in range(1, 41)
    ] + _volle_zeilen(41)
    ha_func = lambda d: {"einspeisung": 22.0, "netzbezug": 3.0, "pv_7": 30.0}
    result, _ = await _run_check(_make_anlage(), tz_list, [_make_inv()], ha_func)

    range_eintraege = [r for r in result if r.action_kind == "reaggregate_range"]
    assert len(range_eintraege) == 1
    params = range_eintraege[0].action_params
    neuester = today - timedelta(days=1)
    assert params["bis"] == neuester.isoformat()
    assert params["von"] == (neuester - timedelta(days=30)).isoformat(), params["von"]
    assert "ältere" in range_eintraege[0].details

    day_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert len(day_eintraege) == 15, f"Erwartet 15 Einzeltage, bekommen {len(day_eintraege)}"
    rest_hinweise = [r for r in result if r.action_kind is None and "weitere" in r.meldung]
    assert len(rest_hinweise) == 1


async def test_ohne_leistungssensor_kein_knopf():
    """E2E-Befund 2026-07-30: `aggregate_day` steigt ohne Leistungs-Zuordnung
    sofort aus und der Bereichs-Lauf meldet `erfolgreich: 0` bei HTTP 200.

    Der Befund bleibt (die Werte fehlen ja), aber der Knopf muss weg — sonst
    läuft er durch, schreibt nichts, und der Anwender sucht den Fehler bei sich.
    """
    tag = _gestern()
    tz_list = [
        _make_tz(tag, {"pv_7": 29.0, "einspeisung": 0.0, "netzbezug": 0.0}),
        *_volle_zeilen(2),
    ]
    ha_func = lambda d: {"einspeisung": 22.0, "netzbezug": 3.4}
    result, _ = await _run_check(
        _make_anlage(mit_live=False), tz_list, [_make_inv()], ha_func,
    )

    assert result, "Der Befund selbst muss bleiben"
    assert not any(r.action_kind for r in result), \
        f"Kein Knopf erwartet, bekommen {[r.action_kind for r in result]}"
    assert len(result) == 1, f"Keine Einzeltag-Zeilen ohne Reparatur-Pfad: {result}"
    d = result[0].details
    assert "NICHT möglich" in d, d
    assert "Leistungs-Zuordnung" in d, d
    # Der Weg raus muss dabeistehen, nicht nur die Absage.
    assert "Datenquellen" in d, d
    assert result[0].link == "/einstellungen/datenquellen", result[0].link


async def test_standalone_mqtt_energie_erlaubt_die_reparatur():
    """Gegenprobe: im Standalone-Betrieb ersetzt MQTT-Energie die W-Zuordnung.

    Dieselbe Bedingung wie in `aggregate_day` — sonst sperrte der Guard eine
    Reparatur aus, die tatsächlich läuft.
    """
    tag = _gestern()
    tz_list = [
        _make_tz(tag, {"pv_7": 29.0, "einspeisung": 0.0, "netzbezug": 0.0}),
        *_volle_zeilen(2),
    ]
    ha_func = lambda d: {"einspeisung": 22.0, "netzbezug": 3.4}
    result, _ = await _run_check(
        _make_anlage(mit_live=False), tz_list, [_make_inv()], ha_func,
        mqtt_energie=True,
    )
    assert any(r.action_kind == "reaggregate_range" for r in result), \
        f"Mit MQTT-Energie muss der Knopf da sein: {result}"


async def test_lts_read_cap_wird_benannt():
    """Mehr Verdachts-Tage als Abfrage-Budget → gedeckelt, aber nicht still."""
    today = date.today()
    tz_list = [
        _make_tz(today - timedelta(days=i), {"einspeisung": 0.0, "netzbezug": 0.0})
        for i in range(1, 91)
    ]
    ha_func = lambda d: {"einspeisung": 22.0, "netzbezug": 3.0}
    result, reads = await _run_check(_make_anlage(), tz_list, [_make_inv()], ha_func)

    assert reads == 45, f"Erwartet 45 LTS-Reads (Cap), waren {reads}"
    summe = [r for r in result if r.action_kind == "reaggregate_range"][0]
    assert "noch nicht gegen HA geprüft" in summe.details, summe.details
    assert "45" in summe.details


async def test_vor_inbetriebnahme_nicht_gemeldet():
    """Basiszähler existieren in HA oft lange vor der Anlage — das ist kein Befund."""
    today = date.today()
    anlage = _make_anlage(installationsdatum=today - timedelta(days=2))
    ha_func = lambda d: {"einspeisung": 22.0, "netzbezug": 3.0, "pv_7": 30.0}
    result, reads = await _run_check(anlage, [], [_make_inv()], ha_func)

    # Nur gestern + vorgestern sind prüfbar, nicht 90 Tage.
    assert reads == 2, f"Erwartet 2 LTS-Reads ab Inbetriebnahme, waren {reads}"
    day_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert len(day_eintraege) == 2, f"Erwartet 2 Einzeltage, bekommen {len(day_eintraege)}"


# ── N-57: die erwartete Schlüsselmenge ist tagesabhängig ────────────────────
#
# `aggregate_day` lädt seine Investitionen per `aktiv_am_tag(datum)`. Wo der
# Check das nicht spiegelt, meldet er eine Lücke und bietet „Tag reparieren"
# an — der Lauf schreibt für die Komponente nichts, antwortet HTTP 200, die
# Meldung bleibt stehen. Ein `select`-Filter reicht dafür nicht: die Menge wird
# einmal fürs ganze Fenster gebaut, die Aktivität ist aber pro Tag verschieden.

_BASIS_VOLL = {"einspeisung": 20.0, "netzbezug": 2.0}


def _zeilen_mit_wp(wp_keys: dict, tage: int = 90) -> list:
    """90 Tageszeilen: Basis gefüllt, die WP-Keys auf 0 (= Verdachtsfall)."""
    return [
        _make_tz(date.today() - timedelta(days=i), {**_BASIS_VOLL, **wp_keys})
        for i in range(1, tage + 1)
    ]


async def test_inaktive_komponente_wird_nicht_gemeldet():
    """`aktiv=False` verspricht nichts — die aktive Nachbarin aber schon.

    Die zweite Hälfte ist die wichtigere: ein Fix, der einfach alles verstummen
    lässt, ist ein Blindmacher, kein Fix.
    """
    anlage = _make_anlage(mit_pv=False, wp_ids=(8, 9))
    invs = [
        _make_inv(8, typ="waermepumpe", bezeichnung="WP alt", aktiv=False),
        _make_inv(9, typ="waermepumpe", bezeichnung="WP neu"),
    ]
    tz_list = _zeilen_mit_wp({"waermepumpe_8": 0.0, "waermepumpe_9": 0.0})
    ha_func = lambda d: {"waermepumpe_8": 6.0, "waermepumpe_9": 4.0}
    result, reads = await _run_check(anlage, tz_list, invs, ha_func)

    summe = [r for r in result if r.action_kind == "reaggregate_range"]
    assert len(summe) == 1, f"Die aktive WP muss weiter gemeldet werden: {result}"
    assert "WP neu" in summe[0].details, summe[0].details
    assert "WP alt" not in summe[0].details, \
        f"Die inaktive WP darf nicht auftauchen: {summe[0].details}"
    day_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert all("WP alt" not in d.meldung for d in day_eintraege), \
        [d.meldung for d in day_eintraege]
    assert reads == 45, f"Verdachtstage bleiben (aktive WP), waren {reads}"


async def test_anschaffung_mitten_im_fenster():
    """Tage vor der Anschaffung sind still, Tage danach werden gemeldet.

    Genau der Test, den ein Filter am `select` NICHT bestehen würde: dort wäre
    die Komponente entweder für alle 90 Tage erwartet oder für keinen.
    """
    today = date.today()
    anschaffung = today - timedelta(days=5)
    anlage = _make_anlage(mit_pv=False, wp_ids=(8,))
    invs = [_make_inv(8, typ="waermepumpe", bezeichnung="WP",
                      anschaffungsdatum=anschaffung)]
    tz_list = _zeilen_mit_wp({"waermepumpe_8": 0.0})
    ha_func = lambda d: {"waermepumpe_8": 6.0}
    result, reads = await _run_check(anlage, tz_list, invs, ha_func)

    assert reads == 5, f"Nur die 5 Tage ab Anschaffung dürfen HA kosten, waren {reads}"
    tage = {r.action_params["datum"] for r in result
            if r.action_kind == "reaggregate_day"}
    erwartet = {(today - timedelta(days=i)).isoformat() for i in range(1, 6)}
    assert tage == erwartet, f"Gemeldete Tage: {sorted(tage)}"


async def test_stilllegung_mitten_im_fenster_inklusiv():
    """Spiegelbild — und der Stilllegungstag selbst zählt noch (ist_aktiv_an)."""
    today = date.today()
    anlage = _make_anlage(mit_pv=False, wp_ids=(8,))
    invs = [_make_inv(
        8, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=today - timedelta(days=8),
        stilllegungsdatum=today - timedelta(days=5),
    )]
    tz_list = _zeilen_mit_wp({"waermepumpe_8": 0.0})
    ha_func = lambda d: {"waermepumpe_8": 6.0}
    result, reads = await _run_check(anlage, tz_list, invs, ha_func)

    assert reads == 4, f"Erwartet 4 aktive Tage (8…5 zurück), waren {reads}"
    tage = {r.action_params["datum"] for r in result
            if r.action_kind == "reaggregate_day"}
    assert (today - timedelta(days=5)).isoformat() in tage, \
        f"Stilllegungstag ist inklusiv: {sorted(tage)}"
    assert (today - timedelta(days=4)).isoformat() not in tage, \
        f"Tag nach der Stilllegung darf nicht gemeldet werden: {sorted(tage)}"


async def test_dietmars_konstellation_kein_knopf():
    """Inaktiv UND Anschaffungsdatum in der Zukunft — zwei Gründe gleichzeitig.

    Gemeldet war 16.06.–30.07. für eine Klimaanlage, die eedc für diese Tage
    gar nicht rechnen darf. Erwartung: keine Meldung, kein Knopf — und trotzdem
    die ehrliche OK-Zeile, weil die Basiszähler ja Werte tragen.
    """
    today = date.today()
    anlage = _make_anlage(mit_pv=False, wp_ids=(8,))
    invs = [_make_inv(
        8, typ="waermepumpe", bezeichnung="Klimaanlage",
        aktiv=False, anschaffungsdatum=today + timedelta(days=1),
    )]
    tz_list = _zeilen_mit_wp({"waermepumpe_8": 0.0})
    ha_func = lambda d: {"waermepumpe_8": 6.0}
    result, reads = await _run_check(anlage, tz_list, invs, ha_func)

    assert reads == 0, f"Nichts versprochen → nichts abzufragen, waren {reads}"
    assert not any(r.action_kind for r in result), f"Kein Knopf erwartet: {result}"
    assert len(result) == 1 and result[0].schwere == "ok", result
