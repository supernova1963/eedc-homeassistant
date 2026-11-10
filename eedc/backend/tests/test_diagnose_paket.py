"""Diagnose-Paket (Etappe E1, Konzept Daten-Checker §8; Bauplan §4 W-7, W-9; Gegenprüfung S4, S5, N17, Ü2).

Was hier gehalten wird:
* die 13 Abschnitte in der Reihenfolge von Konzept §8.2 und die Kopfmarke;
* Standalone (``HA: nicht verbunden``, keine HA-Version) und Add-on (Betriebsart, HA-Version) im Kopf;
* **W-7 / S4** — keine Geheimnisse: ``SPRENGSATZ`` in Token, Passwort, Remote-URL, ``connector_config``,
  ``solcast_config.api_key``, ``versorger_daten.kundennummer``, ``community_hash`` (und in einer Log-Zeile) ⇒ 0 Treffer, und
  die Schlüsselwörter ``token|passw|secret|authorization|api_key|apikey|kundennummer|hash`` stehen nie als Schlüssel;
* **S5** — zweimal abrufen ⇒ ``anlagen.sensor_mapping`` bitgleich (kein ``_festschreiben``); die Route ``/felder`` schreibt
  an derselben Anlage (Gegenprobe: der Test hat Zähne);
* **W-9** — Kopieren-Fassung ≤ ``GRENZE_KOPIE_BYTES``, die Kürzung steht im Kopf, die Datei bleibt ungekürzt;
* **Akte-Probe** (Fall ottokar): die sechs Fragen sind aus dem Paket beantwortbar;
* Scheduler: ``last_run``/``last_ok`` nach einem Job-Lauf;
* die Route: Markdown, Anhang-Name, 404, 422;
* ``code`` + ``werte`` an den elf Melder-Erzeugern (AST).
"""
from __future__ import annotations

import ast
import asyncio
import logging
import re
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.core.config import APP_VERSION
from backend.models.activity_log import ActivityLog
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401 — Tabelle für die Zuordnungen
from backend.models.settings import Settings
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services import diagnose_paket as dp
from backend.services.daten_checker import CheckErgebnis, DatenCheckResult, DatenChecker
from backend.services.daten_checker.kategorien import Aktion
from backend.tests import factories

JETZT = datetime(2026, 11, 10, 12, 0)
ABSCHNITTE = ["Kopf", "Anlage", "Komponenten", "Zuordnungen", "Strompreise", "Daten-Checker", "HA-Spiegel",
              "Nachtlauf und Reparaturen", "Kanal-Tage", "Monate", "Tagesreihen", "Zeitpläne", "Log (WARNING und höher)"]
SCHLUESSELWOERTER = r"token|passw|secret|authorization|api_key|apikey|kundennummer|hash"


async def _anlage(db, **felder):
    a = await factories.anlage(db, anlagenname="Haus Süd", standort_plz="12345", standort_ort="Musterstadt", **felder)
    await factories.investition(db, a.id, "pv-module", bezeichnung="Süddach", anschaffungsdatum=date(2020, 1, 1),
                                leistung_kwp=8.0, parameter={"anzahl_module": 20, "modul_leistung_wp": 400})
    await factories.investition(db, a.id, "speicher", bezeichnung="Akku", anschaffungsdatum=date(2021, 1, 1),
                                parameter={"kapazitaet_kwh": 10.0, "arbitrage_faehig": True})
    await factories.strompreis(db, a.id, date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=32.5,
                               einspeiseverguetung_cent_kwh=8.2, verwendung="allgemein", vertragsart="fix")
    await factories.monatsdaten(db, a.id, 2026, 10, einspeisung_kwh=120.0, netzbezug_kwh=80.0)
    await db.commit()
    return a


def _ueberschriften(t: str) -> list[str]:
    return re.findall(r"^## \d+\. (.+)$", t, re.M)


# ─── Abschnitte, Kopf ─────────────────────────────────────────────────────────────────────────────────────────

async def test_dreizehn_abschnitte_in_reihenfolge_und_kopfmarke(db):
    a = await _anlage(db)
    p = await dp.baue_paket(db, a.id, jetzt=JETZT)
    assert p.text.startswith(dp.KOPFMARKE + "\n")
    assert _ueberschriften(p.text) == ABSCHNITTE
    assert [int(n) for n in re.findall(r"^## (\d+)\.", p.text, re.M)] == list(range(1, 14))
    assert sorted(p.bytes_je_abschnitt) == list(range(1, 14))
    assert p.dateiname == "eedc_diagnose_Haus-S-d_2026-11-10.md"
    assert "- leistung_kwp: 10.0" in p.text and "- standort_ort: Musterstadt" in p.text
    assert "Batteriespeicher «Akku»" in p.text and "arbitrage_faehig=True" in p.text and "10.0 kWh" in p.text
    assert "PV-Modulfeld «Süddach»" in p.text and "8.0 kWp" in p.text
    assert "Arbeitspreis 32.5 ct/kWh" in p.text and "Einspeisung 8.2 ct/kWh" in p.text


async def test_kopf_standalone(db):
    a = await _anlage(db)
    t = (await dp.baue_paket(db, a.id, jetzt=JETZT)).text
    assert f"- eedc-Version: {APP_VERSION}" in t
    assert "- Betriebsart: Standalone\n" in t
    assert "- HA: nicht verbunden" in t
    assert "HA-Version" not in t
    assert "- tageswerte_fehlen: braucht Home Assistant (nicht verbunden)" in t


async def test_kopf_addon(db, monkeypatch):
    a = await _anlage(db)

    async def _info(_db):
        return {"addon": True, "kind": "ha_app", "erreichbar": True, "version": "2026.11.1", "zeitzone": "Europe/Berlin"}

    monkeypatch.setattr(dp, "ha_info", _info)
    t = (await dp.baue_paket(db, a.id, jetzt=JETZT)).text
    assert "- Betriebsart: Add-on (Home Assistant)" in t
    assert "- HA: erreichbar ja · HA-Version 2026.11.1" in t
    assert "HA: Europe/Berlin" in t
    assert "braucht Home Assistant" not in t


async def test_ha_info_liest_config_ohne_url_und_token_herauszugeben(db, monkeypatch):
    from backend.core import config
    from backend.services import ha_connection

    async def _resolve(_db):
        return ("http://127.0.0.1:9/SPRENGSATZ/api", "SPRENGSATZ", "ha_app")

    gerufen = []

    class _Antwort:
        status_code = 200

        @staticmethod
        def json():
            return {"version": "2026.11.1", "time_zone": "Europe/Berlin"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers):
            gerufen.append(url)
            return _Antwort()

    monkeypatch.setattr(ha_connection, "resolve_ha_connection", _resolve)
    monkeypatch.setattr(dp.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(config, "HA_INTEGRATION_AVAILABLE", True)
    info = await dp.ha_info(db)
    assert gerufen == ["http://127.0.0.1:9/SPRENGSATZ/api/config"]
    assert info == {"addon": True, "kind": "ha_app", "erreichbar": True, "version": "2026.11.1",
                    "zeitzone": "Europe/Berlin"}
    assert "SPRENGSATZ" not in repr(info)


# ─── W-7 / S4: keine Geheimnisse ──────────────────────────────────────────────────────────────────────────────

def _schluessel_treffer(t: str) -> list[str]:
    """Schlüsselwörter in Schlüssel-Stellung: JSON-Schlüssel, «- schlüssel: …», «schlüssel=…»."""
    treffer = re.findall(rf'"[^"\n]*(?:{SCHLUESSELWOERTER})[^"\n]*"\s*:', t, re.I)
    treffer += re.findall(rf"^\s*- ([\w ./-]{{0,40}}(?:{SCHLUESSELWOERTER})[\w ./-]{{0,40}}):", t, re.I | re.M)
    treffer += re.findall(rf"\b\w*(?:{SCHLUESSELWOERTER})\w*=", t, re.I)
    return treffer


async def test_w7_kein_geheimnis_im_paket(db, monkeypatch):
    a = await _anlage(
        db,
        connector_config={"connector_id": "fronius", "password": "SPRENGSATZ-pw", "host": "SPRENGSATZ-host"},
        sensor_mapping={"solcast_config": {"api_key": "SPRENGSATZ-key", "resource_id": "SPRENGSATZ-res"}},
        versorger_daten={"kundennummer": "SPRENGSATZ-kd", "portal_url": "https://SPRENGSATZ.example"},
        community_hash="SPRENGSATZ-hash",
    )
    db.add_all([
        Settings(key="ha_remote", value={"enabled": True, "base_url": "http://127.0.0.1:9/SPRENGSATZ",
                                         "token": "SPRENGSATZ-token"}),
        Settings(key="mqtt_inbound", value={"enabled": False, "host": "127.0.0.1", "port": 1, "username": "u",
                                            "password": "SPRENGSATZ-mqtt"}),
        Settings(key="mqtt_export", value={"enabled": False, "password": "SPRENGSATZ-export"}),
    ])
    await db.commit()
    # Eine Log-Zeile mit URL und Token, wie ein Verbindungsfehler sie schreiben könnte.
    puffer = dp_log_puffer()
    lg = logging.getLogger("backend.test_diagnose_paket")
    lg.addHandler(puffer)
    try:
        lg.warning("Remote-HA nicht erreichbar: http://127.0.0.1:9/SPRENGSATZ token=SPRENGSATZ-log Bearer SPRENGSATZ-b")
    finally:
        lg.removeHandler(puffer)
    for fassung in ("datei", "kopie"):
        t = (await dp.baue_paket(db, a.id, fassung=fassung, jetzt=JETZT)).text
        assert "SPRENGSATZ" not in t, fassung
        assert _schluessel_treffer(t) == [], fassung
        assert "Geräte-Connector: fronius" in t
    assert "Betriebsart: Standalone mit Home Assistant (Remote)" in t
    assert "<url>" in (await dp.baue_paket(db, a.id, jetzt=JETZT)).text


def dp_log_puffer():
    from backend.core.log_buffer import get_log_buffer

    return get_log_buffer()


def test_w7_schluessel_pruefung_hat_zaehne():
    assert _schluessel_treffer('{"api_key":"x"}') and _schluessel_treffer("- token: x")
    assert _schluessel_treffer("Parameter community_hash=1") and _schluessel_treffer("- Kundennummer: 4711")
    assert not _schluessel_treffer("- [info] sensor_mapping_lts — Token fehlt: nichts")


def test_log_bereinigung():
    z = dp.bereinige_log("Fehler bei https://user:pw@ha.local:8123/api token=abc Authorization: Bearer xyz")
    assert "pw@" not in z and "abc" not in z and "xyz" not in z and "<url>" in z


# ─── S5: zweimal abrufen ⇒ sensor_mapping bitgleich ───────────────────────────────────────────────────────────

async def _roh_mapping(db, aid):
    return (await db.execute(text("SELECT sensor_mapping FROM anlagen WHERE id = :i"), {"i": aid})).scalar_one()


async def test_s5_zweimal_abrufen_schreibt_nichts(db):
    from backend.api.routes.datenquellen import get_datenquellen_felder

    mapping = {"investitionen": {"1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}},
                                       "live": {"leistung_w": "sensor.pv_w"}}}}
    a = await factories.anlage_mit_pv(db, mapping)
    await db.commit()
    vorher = await _roh_mapping(db, a.id)
    for _ in range(2):
        p = await dp.baue_paket(db, a.id, jetzt=JETZT)
        await db.commit()   # wie get_db am Ende der Route
        assert await _roh_mapping(db, a.id) == vorher
    # Das Paket zeigt die aufgelöste, noch nicht gespeicherte Quelle als solche.
    assert "inv_energy_1_pv_erzeugung_kwh" in p.text and "→ sensor.pv (aufgelöst, nicht gespeichert)" in p.text
    # Gegenprobe: die Route /felder schreibt dieselbe Auflösung fest — ohne den Schnitt hätte das Paket es auch getan.
    await get_datenquellen_felder(a.id, db)
    await db.commit()
    assert await _roh_mapping(db, a.id) != vorher


# ─── W-9: Größe und Kürzung ───────────────────────────────────────────────────────────────────────────────────

def _teile_gross() -> dp._Teile:
    t = dp._Teile(kopf=["- eedc-Version: x"], anlage=["- a"], komponenten=["- k"], zuordnungen=["- z"] * 50,
                  strompreise=["- s"])
    t.checker_kopf = ["- Zusammenfassung"]
    t.checker = [("- [ok] x — " + "o" * 300, True) for _ in range(30)] + [("- [warning] y", False)]
    t.spiegel = [("- basis:pv (kWh, sum)", ["  - Abschnitt " + "s" * 200] * 10)]
    t.tagesreihen = [("2026-10", ["- " + "t" * 200] * 31), ("2026-09", ["- " + "t" * 200] * 31)]
    t.log = ["- " + "l" * 290] * 30
    return t


def test_w9_kuerzungsfolge_bis_zur_grenze():
    t = _teile_gross()
    datei, _, k_datei = dp.setze_zusammen(t, "T", "datei")
    kopie, groessen, k_kopie = dp.setze_zusammen(t, "T", "kopie")
    assert len(datei.encode()) > dp.GRENZE_KOPIE_BYTES and k_datei == []
    assert len(kopie.encode()) <= dp.GRENZE_KOPIE_BYTES
    folge = ["Log weggelassen", "Tagesreihen nur 1 Monat", "Spiegel-Abschnitte weggelassen", "Checker-OK-Zeilen weggelassen"]
    assert len(k_kopie) >= 2 and k_kopie == folge[:len(k_kopie)]
    assert f"- Kürzungen: {', '.join(k_kopie)}" in kopie
    assert "#### 2026-10" in kopie and "#### 2026-09" not in kopie
    assert sorted(groessen) == list(range(1, 14))


def test_w9_harter_schnitt_als_letzte_stufe():
    t = _teile_gross()
    t.zuordnungen = ["- " + "z" * 500] * 60
    kopie, _, k = dp.setze_zusammen(t, "T", "kopie")
    assert len(kopie.encode()) <= dp.GRENZE_KOPIE_BYTES
    assert k[-1] == f"am Ende abgeschnitten bei {dp.GRENZE_KOPIE_BYTES} Bytes" and kopie.endswith("… (abgeschnitten)\n")


async def test_w9_kopie_der_fixture_unter_der_grenze_mit_kopfzeile(db):
    a = await _anlage(db)
    for fassung in ("datei", "kopie"):
        p = await dp.baue_paket(db, a.id, fassung=fassung, jetzt=JETZT)
        assert len(p.text.encode()) <= dp.GRENZE_KOPIE_BYTES
        assert "- Kürzungen: keine" in p.text


# ─── Akte-Probe (Fall ottokar): die sechs Fragen ──────────────────────────────────────────────────────────────

async def test_akte_probe_sechs_fragen(db, monkeypatch):
    a = await _anlage(db, sensor_mapping={"quellen": {"basis_energy_pv_gesamt_kwh": {
        "quelle": "ha_connector", "entity_id": "sensor.pv_gesamt"}}})
    k = Kanal(anlage_id=a.id, key="basis:pv_gesamt", einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    ab = int(datetime(2026, 11, 1).timestamp())
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=ab, familie=FAMILIE_SPIEGEL, statistic_id="sensor.pv_gesamt", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ab + 3600 * i, sum=float(i), state=float(i), familie=FAMILIE_SPIEGEL)
                for i in range(48)])
    for tag in (1, 2, 3):
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 11, tag), datenquelle="ha_statistics",
                                    stunden_verfuegbar=24, komponenten_kwh={"pv_1": 10.0 + tag}))
    db.add_all([
        ActivityLog(kategorie="scheduler", aktion="Kanalstatistik: Konsistenzlauf — alle Abschnitte stimmen mit HA überein",
                    erfolg=True, details="1 Abschnitte in 1 Kanälen geprüft · gleich 1 · korrigiert 0 · gekürzt 0 · Fehler 0",
                    anlage_id=a.id, timestamp=datetime(2026, 11, 10, 2, 45)),
        ActivityLog(kategorie="repair", aktion="Reparatur: Tag neu aggregieren — 2026-11-02", erfolg=True,
                    details="Änderungen: tage 1", anlage_id=a.id, timestamp=datetime(2026, 11, 8, 20, 0)),
        ActivityLog(kategorie="scheduler", aktion="Wetter: fremde Zeile", erfolg=True, anlage_id=a.id),
    ])
    await db.commit()
    drift = CheckErgebnis(
        kategorie="datenquelle_drift", schwere="info",
        meldung="2026-11-02: PV 123.909,6 → HA 13,7 kWh (Δ −123.895,9 kWh, −100,0 %)",
        altlink="/einstellungen/daten?block=energieprofil&karte=werkbank",
        action=Aktion("spiegel_abgleich_tag", {"anlage_id": a.id, "datum": "2026-11-02"}, "Aus Home Assistant neu übernehmen"),
        code="drift_tag", werte={"datum": "2026-11-02", "achse": "pv", "eedc": 123909.6, "ha": 13.7, "delta": -123895.9,
                                 "prozent": -99.99},
    )

    async def _check(self, aid):
        return DatenCheckResult(anlage_id=aid, anlage_name="Haus Süd", ergebnisse=[drift],
                                zusammenfassung={"error": 0, "warning": 0, "info": 1, "ok": 0})

    async def _kanal(_db, _aid, von, bis):
        return {d for d in (date(2026, 11, 2),) if von <= d <= bis}

    monkeypatch.setattr(DatenChecker, "check_anlage", _check)
    monkeypatch.setattr(dp, "_kanal_tage", _kanal)
    t = (await dp.baue_paket(db, a.id, fassung="kopie", jetzt=JETZT)).text
    # (1) Version und Betriebsart
    assert f"- eedc-Version: {APP_VERSION}" in t and "- Betriebsart: Standalone" in t
    # (2) welche Drift-Zeile, mit beiden Werten
    drift_zeile = next(z for z in t.splitlines() if "code drift_tag" in z)
    assert '"eedc":123909.6' in drift_zeile and '"ha":13.7' in drift_zeile and "Aktion spiegel_abgleich_tag" in drift_zeile
    # (3) lief der Nachtlauf, mit welchem Ergebnis
    assert "2026-11-10 02:45 · scheduler · ok · Kanalstatistik: Konsistenzlauf — alle Abschnitte stimmen" in t
    assert "Wetter: fremde Zeile" not in t
    # (4) was wurde geklickt
    assert "2026-11-08 20:00 · repair · ok · Reparatur: Tag neu aggregieren — 2026-11-02" in t
    # (5) Kanal- oder Bestandstag, Spiegel-Abschnitte
    assert "- 2026-11-02 · Kanal · ha_statistics" in t and "- 2026-11-01 · Bestand · ha_statistics" in t
    assert "- Kanal-Tage (aus dem HA-Spiegel): 2026-11-02" in t
    assert "- basis:pv_gesamt (kWh, sum): 48 Stunden, 2026-11-01 00:00 … 2026-11-02 23:00" in t
    assert "  - Abschnitt spiegel sensor.pv_gesamt gültig ab 2026-11-01 00:00" in t
    assert "- Tagesreihen: 2026-11 (aus den Befunden)" in t and "#### 2026-11" in t
    # (6) welche Monate und Feldmaske, welche Entity je Feld
    assert re.search(r"- Feldmaske M1: [^\n]*einspeisung_kwh", t) and "- 2026-10 · Quelle" in t
    assert "- basis_energy_pv_gesamt_kwh «" in t and "ha_connector → sensor.pv_gesamt" in t


async def test_monate_aus_befunden_und_angefragt(db):
    e = [CheckErgebnis(kategorie="x", schwere="warning", meldung="m", werte={"von": "2026-08-30", "bis": "2026-09-02"}),
         CheckErgebnis(kategorie="x", schwere="ok", meldung="m", werte={"datum": "2026-10-01"}),
         CheckErgebnis(kategorie="x", schwere="info", meldung="m", action=Aktion("x", {"datum": "2026-07-04"}, "x"))]
    assert dp.monate_aus_befunden(e) == [(2026, 9), (2026, 8), (2026, 7)]
    a = await _anlage(db)
    t = (await dp.baue_paket(db, a.id, monate=[(2026, 1), (2026, 10), (2026, 9)], jetzt=JETZT)).text
    assert "- Tagesreihen: 2026-10, 2026-09 (angefragt)" in t


# ─── Scheduler last_run ───────────────────────────────────────────────────────────────────────────────────────

async def test_scheduler_merkt_letzten_lauf():
    from backend.services.scheduler import EEDCScheduler

    s = EEDCScheduler()
    assert s.start()
    try:
        s._scheduler.remove_all_jobs()   # nur die Probe-Jobs, keine echten (vor dem ersten Takt der Schleife)

        async def _gut():
            return None

        async def _schlecht():
            raise RuntimeError("Probe")

        # Ohne Trigger läuft ein Job einmal sofort (APScheduler) — keine Prozessuhr in der Probe (N-167-Wächter).
        s._scheduler.add_job(_gut, id="probe_gut", name="Probe gut")
        s._scheduler.add_job(_schlecht, id="probe_schlecht", name="Probe schlecht")
        assert {j["id"]: j["last_run"] for j in s.get_status()["jobs"]} == {"probe_gut": None, "probe_schlecht": None}
        for _ in range(50):
            await asyncio.sleep(0.05)
            if len(s._letzte_laeufe) == 2:
                break
        assert s._letzte_laeufe["probe_gut"][1] is True
        assert s._letzte_laeufe["probe_schlecht"][1] is False
    finally:
        s.stop()


async def test_scheduler_status_traegt_last_run():
    from backend.services.scheduler import EEDCScheduler

    class _Job:
        id, name, next_run_time = "j", "Job", None

    class _Sched:
        @staticmethod
        def get_jobs():
            return [_Job()]

    s = EEDCScheduler()
    s._scheduler, s._running = _Sched(), True
    s._letzte_laeufe["j"] = (datetime(2026, 11, 10, 2, 45, 3), False)
    assert s.get_status()["jobs"] == [{"id": "j", "name": "Job", "next_run": None, "last_run": "2026-11-10T02:45:03",
                                       "last_ok": False}]


# ─── Route ────────────────────────────────────────────────────────────────────────────────────────────────────

async def test_route_markdown_anhang_404_422(db):
    from fastapi import HTTPException

    from backend.api.routes.daten_checker import diagnose_paket

    a = await _anlage(db)
    r = await diagnose_paket(a.id, fassung="kopie", monate="2026-10", db=db)
    assert r.media_type == "text/markdown; charset=utf-8"
    assert re.fullmatch(r'attachment; filename="eedc_diagnose_Haus-S-d_\d{4}-\d{2}-\d{2}\.md"',
                        r.headers["content-disposition"])
    assert r.body.decode().startswith(dp.KOPFMARKE)
    assert "2026-10 (angefragt)" in r.body.decode()
    with pytest.raises(HTTPException) as e:
        await diagnose_paket(999999, fassung="datei", monate=None, db=db)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        await diagnose_paket(a.id, fassung="datei", monate="2026-13", db=db)
    assert e.value.status_code == 422


# ─── code + werte an den Melder-Erzeugern (Erhebung Teil B) ───────────────────────────────────────────────────

_ERZEUGER = {
    "datenquelle/ha_rueckgang.py": ["ha_zaehler_rueckgang"],
    "datenquelle/ha_sprung.py": ["ha_zaehlersprung"],
    "datenquelle/quellen.py": ["drift_weitere_tage", "drift_tag", "drift_komponente"],
    "datenquelle/speicher.py": ["batterie_vorzeichen_tage", "batterie_vorzeichen_tag"],
    "datenquelle/tage.py": ["tageswerte_fehlen_tage", "tageswerte_fehlen_tag"],
    "energieprofil.py": ["nachtrag_nach_eingefrorenem_zaehler", "counter_spike_tag"],
}


@pytest.mark.parametrize("datei", sorted(_ERZEUGER))
def test_melder_erzeuger_tragen_code_und_werte(datei):
    pfad = Path(__file__).resolve().parents[1] / "services" / "daten_checker" / datei
    gefunden = []
    for n in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "CheckErgebnis":
            kw = {k.arg: k.value for k in n.keywords}
            # Seit E2 trägt jeder Erzeuger `code=` (W-1); `werte` tragen die Melder-Erzeuger dieser Liste.
            if isinstance(kw.get("code"), ast.Constant) and kw["code"].value in _ERZEUGER[datei]:
                assert "werte" in kw, (datei, kw["code"].value)
                gefunden.append(kw["code"].value)
    assert gefunden == _ERZEUGER[datei]
