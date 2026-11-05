"""RF-75 … RF-76 (5.11.2026): benannte Proben für die Zweige der zwei HA-Export-Rechner, die weder die direkten Tests
noch die In-Process-GMs (`ha-export-anlage`, `ha-export-investition`) betreten — am HEAD vor dem Schnitt grün.

* **RF-75 `calculate_anlage_sensors`:** Frühausstieg ohne Monatsdaten (kein Tarif, keine Investitionen geladen), die
  SQL-Folge des Kopfs (Monatsdaten → Tarif → aktive Investitionen → alle Investitionen), der Bezugspreis-Fehler der
  S3b-Eingänge (Warnung, Export bleibt grün, Fenster-Kontext ohne Bezugspreise), die Prozessuhr ohne ``jetzt``.
* **RF-76 `_wp_steuerung_und_plan`:** P4 (Menge der letzten drei abgeschlossenen Monate ÷ Tage, 2-h-Fenster, Frist ≤ 24
  N-544, kein Sensor ohne Fenster), P7 (Beginn ``(h−1) % 24``, Heizzeit ab dem laufenden Slot, kein Sensor ohne
  Verteilung), P8 (Menge der letzten drei Monate, 2-h-Fenster, Frist = Spitzen-Slot, kein Sensor ohne Fenster, keine
  Menge ⇒ kein Fenster).

Uhr gestellt (N-167); Prognose/Preis gestellt an den Patch-Zielen von `test_s3_geraete_fenster.py`.
"""

import calendar
import dataclasses
import logging
from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy import event

from backend.tests.test_s3_geraete_fenster import (
    HEUTE,
    _anlage,
    _ctx,
    _geraet,
    _keys,
    _letzte_monate,
    _mapping_mit_kuehlzaehler,
    _preis,
    _prognose,
    _rechne,
    _sv,
)


def _sql_mitschnitt(db) -> list[str]:
    sql: list[str] = []

    def _mit(conn, cursor, statement, params, context, executemany):
        sql.append(" ".join(statement.split()))
    event.listen(db.bind.sync_engine, "before_cursor_execute", _mit)
    return sql


def _stelle_prognose_und_preis(monkeypatch):
    from backend.api.routes.ha_export import anlage_sensorwerte

    async def _p(db_, anlage_, *, skip_jitter=False):
        return _prognose()

    async def _q(db_, anlage_):
        return _preis()

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _p)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _q)


def _tabelle(stmt: str) -> str:
    return stmt.split(" FROM ", 1)[1].split()[0] if " FROM " in stmt else stmt.split()[0]


# ── RF-75 · calculate_anlage_sensors ────────────────────────────────────────

async def test_ohne_monatsdaten_kein_sensor_und_kein_weiteres_laden(db):
    """Frühausstieg: ohne eine Monatszeile ``[]`` — und weder Tarif noch Investitionen werden geladen."""
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.models import Anlage

    anlage = Anlage(anlagenname="ohne Monate", leistung_kwp=5.0, installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.commit()
    sql = _sql_mitschnitt(db)
    kontext: dict = {}

    werte = await calculate_anlage_sensors(db, anlage, skip_jitter=True, kontext_out=kontext,
                                           jetzt=datetime(2026, 9, 21, 10))

    assert werte == []
    assert [_tabelle(s) for s in sql] == ["monatsdaten"]
    assert kontext == {}, "der Frühausstieg füllt den Kontext nicht"


async def test_kopf_laedt_monatsdaten_tarif_investitionen_in_dieser_reihenfolge(db, monkeypatch):
    from backend.api.routes.ha_export import calculate_anlage_sensors

    _stelle_prognose_und_preis(monkeypatch)
    anlage = await _anlage(db)
    sql = _sql_mitschnitt(db)

    await calculate_anlage_sensors(db, anlage, skip_jitter=True, jetzt=datetime(2026, 9, 21, 10))

    assert [_tabelle(s) for s in sql[:4]] == ["monatsdaten", "strompreise", "investitionen", "investitionen"]
    assert "stilllegungsdatum" in sql[2].split(" WHERE ")[1] and "stilllegungsdatum" not in sql[3].split(" WHERE ")[1], (
        "erst die heute aktiven Investitionen, dann alle der Anlage (USt-Satz je Jahr)"
    )


async def test_ust_phase_bekommt_alle_investitionen_die_anderen_nur_die_aktiven(db, monkeypatch):
    """`investitionen_und_ust` bekommt auch die stillgelegte Komponente (USt-Satz je Jahr, G1) — alle übrigen Phasen
    nur die heute aktiven."""
    from backend.api.routes.ha_export import anlage_sensoren, calculate_anlage_sensors

    _stelle_prognose_und_preis(monkeypatch)
    anlage = await _anlage(db)
    aktiv = await _geraet(db, anlage, "waermepumpe", {}, {})
    alt = await _geraet(db, anlage, "speicher", {}, {})
    alt.stilllegungsdatum = date(2025, 1, 31)
    await db.commit()
    gesehen: dict = {}
    echt = anlage_sensoren.investitionen_und_ust

    def _spion(**k):
        gesehen["alle"] = sorted(i.id for i in k["alle_investitionen"])
        gesehen["aktiv"] = sorted(i.id for i in k["investitionen"])
        return echt(**k)
    monkeypatch.setattr(anlage_sensoren, "investitionen_und_ust", _spion)

    await calculate_anlage_sensors(db, anlage, skip_jitter=True, jetzt=datetime(2026, 9, 21, 10))

    assert gesehen == {"alle": sorted([aktiv.id, alt.id]), "aktiv": [aktiv.id]}


async def test_jede_phase_bekommt_den_gleichnamigen_wert_der_phase_davor(db, monkeypatch):
    """«Reihenfolge ist Vertrag»: jedes Schlüsselwort einer Vorlage-8b-Phase ist DASSELBE Objekt, das eine frühere Phase
    unter diesem Namen zurückgab (die jüngste) — kein Wert unter falschem Namen, keiner aus einer älteren Phase.

    Jede Gleitkomma-Rückgabe wird in ein eigenes Objekt (`_Eigen`, Unterklasse von float, gleicher Wert) gehüllt: zwei
    Namen mit zufällig demselben Wert (Eigenverbrauch mit/ohne Wandlungsverluste ohne Verluste) wären sonst dasselbe
    Objekt, und eine Verwechslung bliebe unsichtbar."""
    import inspect

    from backend.api.routes.ha_export import anlage_sensoren, calculate_anlage_sensors

    _stelle_prognose_und_preis(monkeypatch)
    anlage = await _anlage(db)
    await _geraet(db, anlage, "speicher", {"kapazitaet_kwh": 10.0},
                  {m: {"ladung_kwh": 100.0, "entladung_kwh": 90.0} for m in _letzte_monate(HEUTE, 3)})
    namen = ("monatsfakten_und_energie", "finanz_aggregat", "investitionen_und_ust", "historische_komponenten",
             "alternativkosten_und_co2", "ertrag_und_amortisation", "speicher_kpis", "sensorwerte_erstellen")
    protokoll: list = []

    class _Eigen(float):
        pass

    def _eigen(out):
        for k, v in list(out.items()):
            if type(v) is float:
                out[k] = _Eigen(v)
        return out

    def _huelle(name, echt):
        if inspect.iscoroutinefunction(echt):
            async def _a(**k):
                out = _eigen(await echt(**k))
                protokoll.append((name, k, out))
                return out
            return _a

        def _s(**k):
            out = _eigen(echt(**k))
            protokoll.append((name, k, out))
            return out
        return _s
    for n in namen:
        monkeypatch.setattr(anlage_sensoren, n, _huelle(n, getattr(anlage_sensoren, n)))

    await calculate_anlage_sensors(db, anlage, skip_jitter=True, jetzt=datetime(2026, 9, 21, 10))

    assert [n for n, _k, _o in protokoll] == list(namen)
    geprueft = 0
    for i, (name, kwargs, _out) in enumerate(protokoll):
        for k, v in kwargs.items():
            frueher = [o for _n, _k, o in protokoll[:i] if k in o]
            if frueher:
                assert v is frueher[-1][k], f"{name}({k}=…) ist nicht der Wert der Phase davor"
                geprueft += 1
    assert geprueft >= 60, geprueft


async def test_bezugspreis_fehler_laesst_den_export_gruen(db, monkeypatch, caplog):
    """S3b: scheitert `lade_bezugspreise`, warnt der Rechner und baut den Fenster-Kontext ohne Bezugspreise."""
    from backend.api.routes.ha_export import anlage_sensoren, calculate_anlage_sensors
    from backend.services import ha_export_bezugspreis

    _stelle_prognose_und_preis(monkeypatch)
    anlage = await _anlage(db)

    async def _kaputt(*a, **k):
        raise RuntimeError("Probe")
    monkeypatch.setattr(ha_export_bezugspreis, "lade_bezugspreise", _kaputt)
    gesehen: list = []
    echt = anlage_sensoren.baue_fenster_kontext

    def _spion(prognose, preis, bezugspreise, *, jetzt):
        gesehen.append(bezugspreise)
        return echt(prognose, preis, bezugspreise, jetzt=jetzt)
    monkeypatch.setattr(anlage_sensoren, "baue_fenster_kontext", _spion)
    kontext: dict = {}

    with caplog.at_level(logging.WARNING, logger=anlage_sensoren.logger.name):
        werte = await calculate_anlage_sensors(db, anlage, skip_jitter=True, kontext_out=kontext,
                                               jetzt=datetime(2026, 9, 21, 10))

    assert werte, "der Export bleibt grün"
    assert gesehen == [None]
    assert kontext["fenster"] is not None
    assert any(
        f"HA-Export Bezugspreise fehlgeschlagen (Anlage {anlage.id}): RuntimeError: Probe" in r.getMessage()
        for r in caplog.records
    )


async def test_ohne_jetzt_gilt_die_prozessuhr(db, monkeypatch):
    """``jetzt=None`` ⇒ ``datetime.now()`` des Moduls; Tag und Stunde gehen an die Steuerungs-Phase."""
    from backend.api.routes.ha_export import anlage_sensoren, calculate_anlage_sensors

    _stelle_prognose_und_preis(monkeypatch)
    anlage = await _anlage(db)

    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 21, 7, 30)
    monkeypatch.setattr(anlage_sensoren, "datetime", _Uhr)
    gesehen: list = []
    echt = anlage_sensoren.steuerungs_sensoren

    async def _spion(**k):
        gesehen.append((k["heute"], k["jetzt_stunde"]))
        return await echt(**k)
    monkeypatch.setattr(anlage_sensoren, "steuerungs_sensoren", _spion)

    await calculate_anlage_sensors(db, anlage, skip_jitter=True)

    assert gesehen == [(date(2026, 9, 21), 7)]


# ── RF-76 · _wp_steuerung_und_plan ──────────────────────────────────────────

def _fenster_spion(monkeypatch, ergebnis="echt"):
    from backend.services import ha_export_fenster

    aufrufe: list = []
    echt = ha_export_fenster.fenster_fuer_menge

    def _spion(ctx, menge, **k):
        aufrufe.append((menge, k))
        return echt(ctx, menge, **k) if ergebnis == "echt" else ergebnis
    monkeypatch.setattr(ha_export_fenster, "fenster_fuer_menge", _spion)
    return aufrufe


async def _wp_mit_warmwasser_drei_monate(db):
    """Warmwasser gemessen in vier Monaten — der älteste liegt außerhalb der letzten drei abgeschlossenen.

    Die Anlage geht mit zurück: die Sitzung hält ihre Objekte nur schwach — ohne Verweis lädt `investition.anlage`
    nach (ohne Greenlet ⇒ `MissingGreenlet`)."""
    anlage = await _anlage(db)
    monate = _letzte_monate(HEUTE, 4)
    zeilen = {m: {"stromverbrauch_kwh": 100.0, "strom_warmwasser_kwh": ww}
              for m, ww in zip(monate, (30.0, 45.0, 60.0, 900.0))}
    inv = await _geraet(db, anlage, "waermepumpe", {"getrennte_strommessung": True}, zeilen)
    tage = sum(calendar.monthrange(j, m)[1] for j, m in monate[:3])
    return anlage, inv, 135.0 / tage, tage


async def test_p4_menge_der_letzten_drei_monate_und_zwei_stunden(db, monkeypatch):
    _anl, inv, je_tag, tage = await _wp_mit_warmwasser_drei_monate(db)
    aufrufe = _fenster_spion(monkeypatch)

    werte = await _rechne(db, inv, _ctx(stunde=0))

    menge, k = aufrufe[0]
    assert menge == je_tag
    assert k["dauer_h"] == 2
    sv = _sv(werte, "wp_warmwasser_fenster_ab")
    assert sv.zusatz_attribute["herkunft"] == "gemessen"
    assert f"aus {tage} Tagen" in sv.berechnung


async def test_p4_frist_hoechstens_slot_24(db, monkeypatch):
    """N-544: die Frist des Warmwasser-Fensters ist ``min(24, ctx.frist_slot)`` — und 24 ohne Frist."""
    _anl, inv, _je_tag, _tage = await _wp_mit_warmwasser_drei_monate(db)
    aufrufe = _fenster_spion(monkeypatch)
    ctx = _ctx(stunde=0)

    for frist, erwartet in ((40, 24), (None, 24), (20, 20)):
        aufrufe.clear()
        await _rechne(db, inv, dataclasses.replace(ctx, frist_slot=frist))
        assert aufrufe[0][1]["frist_slot"] == erwartet, (frist, aufrufe[0][1])


async def test_p4_ohne_fenster_kein_sensor(db, monkeypatch):
    _anl, inv, _je_tag, _tage = await _wp_mit_warmwasser_drei_monate(db)
    aufrufe = _fenster_spion(monkeypatch, ergebnis=None)

    werte = await _rechne(db, inv, _ctx(stunde=0))

    assert aufrufe, "die Menge ist da — gefragt wird"
    assert "wp_warmwasser_fenster_ab" not in _keys(werte)


async def test_p7_beginn_ist_die_vorstunde_des_slots(db, monkeypatch):
    """N-544: Slot ``h`` beginnt ``(h−1):00`` — Slot 1 ⇒ 00:00, Slot 24 ⇒ 23:00; Heizzeit ab dem laufenden Slot."""
    from backend.api.routes.ha_export import investition_sensoren

    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})
    ctx = _ctx(stunde=6)
    erwartete_heizzeit = [i for i, v in enumerate(ctx.wp_stundenprofil_kwh) if v > 0 and i >= ctx.jetzt_slot]
    gefragt: list = []

    def _verteilung(kosten, reihe, stunden):
        gefragt.append(stunden)
        return SimpleNamespace(stunden=[1, 7, 24], ersparnis_cent=12.4)
    monkeypatch.setattr(investition_sensoren, "verteile_auf_guenstigste", _verteilung)

    werte = await _rechne(db, inv, ctx)

    assert gefragt == [erwartete_heizzeit]
    sv = _sv(werte, "wp_heizfenster_stunden")
    assert sv.value == 3
    assert sv.zusatz_attribute["guenstige_heizstunden"] == ["00:00", "06:00", "23:00"]
    assert sv.zusatz_attribute["ersparnis_cent_vs_profil"] == 12
    assert sv.zusatz_attribute["heizzeit_stunden"] == len(erwartete_heizzeit)


async def test_p7_ohne_verteilung_kein_sensor(db, monkeypatch):
    from backend.api.routes.ha_export import investition_sensoren

    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})
    for ergebnis in (None, SimpleNamespace(stunden=[], ersparnis_cent=0.0)):
        monkeypatch.setattr(investition_sensoren, "verteile_auf_guenstigste", lambda *a, _e=ergebnis: _e)
        werte = await _rechne(db, inv, _ctx(stunde=0))
        assert "wp_heizfenster_stunden" not in _keys(werte), ergebnis


async def _wp_mit_kuehlzaehler(db, mengen):
    """Kühl-Zähler zugeordnet; ``mengen`` = Kühlstrom je Monat, neueste zuerst."""
    anlage = await _anlage(db)
    monate = _letzte_monate(HEUTE, len(mengen))
    zeilen = {m: {"stromverbrauch_kwh": 200.0, "betriebsart_strom_kuehlen_kwh": k, "modus_abdeckung_h": 700.0}
              for m, k in zip(monate, mengen)}
    inv = await _geraet(db, anlage, "waermepumpe", {}, zeilen)
    anlage.sensor_mapping = _mapping_mit_kuehlzaehler(inv.id)
    await db.commit()
    await db.refresh(inv)
    return anlage, inv, monate


async def test_p8_menge_der_letzten_drei_monate_frist_spitze(db, monkeypatch):
    _anl, inv, monate = await _wp_mit_kuehlzaehler(db, (30.0, 45.0, 60.0, 900.0))
    aufrufe = _fenster_spion(monkeypatch)
    tage = sum(calendar.monthrange(j, m)[1] for j, m in monate[:3])

    werte = await _rechne(db, inv, _ctx(stunde=6))

    menge, k = aufrufe[-1]
    assert menge == 135.0 / tage
    assert k == {"dauer_h": 2, "frist_slot": 14}, "Frist = Spitzen-Slot (33 °C um 14:00)"
    assert _sv(werte, "wp_kuehlfenster_ab").zusatz_attribute["temperatur_max_um"] == "14:00"


async def test_p8_ohne_fenster_kein_sensor(db, monkeypatch):
    _anl, inv, _monate = await _wp_mit_kuehlzaehler(db, (60.0,))
    aufrufe = _fenster_spion(monkeypatch, ergebnis=None)

    werte = await _rechne(db, inv, _ctx(stunde=6))

    assert aufrufe
    assert "wp_kuehlfenster_ab" not in _keys(werte)


async def test_p8_ohne_menge_in_den_letzten_drei_monaten_kein_fenster(db, monkeypatch):
    """Zähler da, Kühlstrom nur im vierten Monat zurück ⇒ Menge 0 ⇒ kein Fenster, nicht einmal gefragt."""
    _anl, inv, _monate = await _wp_mit_kuehlzaehler(db, (0.0, 0.0, 0.0, 80.0))
    aufrufe = _fenster_spion(monkeypatch)

    werte = await _rechne(db, inv, _ctx(stunde=6))

    assert [m for m, k in aufrufe if k.get("frist_slot") == 14] == []
    assert "wp_kuehlfenster_ab" not in _keys(werte)


async def test_p8_spitze_in_der_laufenden_stunde_zaehlt_noch(db, monkeypatch):
    """N-544: ``spitze >= jetzt_slot`` — um 13:xx läuft Slot 14, die Spitze liegt in Slot 14: gefragt wird noch."""
    _anl, inv, _monate = await _wp_mit_kuehlzaehler(db, (60.0,))
    aufrufe = _fenster_spion(monkeypatch)

    await _rechne(db, inv, _ctx(stunde=13))

    assert [k["frist_slot"] for _m, k in aufrufe if k.get("dauer_h") == 2 and k.get("frist_slot") == 14] == [14]


async def test_p8_ohne_kuehlstrom_monate_wird_der_zaehler_nicht_befragt(db, monkeypatch):
    """Erstes Kriterium zuerst: ohne einen einzigen Kühlstrom-Monat fragt P8 `hat_kuehl_zaehler` gar nicht."""
    from backend.api.routes.ha_export import investition_sensoren

    anlage = await _anlage(db)
    inv = await _geraet(db, anlage, "waermepumpe", {}, {})
    anlage.sensor_mapping = _mapping_mit_kuehlzaehler(inv.id)
    await db.commit()
    await db.refresh(inv)
    gefragt: list = []

    def _spion(*a, **k):
        gefragt.append(a)
        return True
    monkeypatch.setattr(investition_sensoren, "hat_kuehl_zaehler", _spion)

    werte = await _rechne(db, inv, _ctx(stunde=6))

    assert gefragt == []
    assert "wp_kuehlfenster_ab" not in _keys(werte)


async def test_p4_ohne_preis_jetzt_fehlt_die_ersparnis_statt_none(db, monkeypatch):
    """Ein Attribut ohne Wert fällt weg (`None` wird nie geschrieben): ohne Vergleichspreis «jetzt» fehlt
    `ersparnis_cent_vs_jetzt`, die übrigen Attribute bleiben."""
    from backend.services import ha_export_fenster

    _anl, inv, _je_tag, _tage = await _wp_mit_warmwasser_drei_monate(db)
    echt = ha_export_fenster.fenster_fuer_menge

    def _ohne_delta(ctx, menge, **k):
        f = echt(ctx, menge, **k)
        return None if f is None else dataclasses.replace(f, delta_vs_jetzt=None)
    monkeypatch.setattr(ha_export_fenster, "fenster_fuer_menge", _ohne_delta)

    werte = await _rechne(db, inv, _ctx(stunde=0))

    za = _sv(werte, "wp_warmwasser_fenster_ab").zusatz_attribute
    assert "ersparnis_cent_vs_jetzt" not in za
    assert None not in za.values()
    assert {"menge_kwh", "herkunft", "kosten_cent", "preisquelle"} <= set(za)
