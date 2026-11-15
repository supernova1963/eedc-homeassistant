"""Diagnose-Paket v4 (Konzept/Bauplan «Diagnose-Paket v4» 14.11.2026; vorher E1 v3) — Lage, Routen, Ablage, W-7 (c).

Was hier gehalten wird:
* Kopf (Standalone, Add-on, Zeitzone mit Quelle, Startzeit — Testpunkt 3), ``ha_info`` gibt URL und Token nie heraus;
* **W-7 (c)** — keine Geheimnisse: gesät in jede ``raus``-Spalte (aus dem Register iteriert), ``solcast_config.api_key``,
  ``connector_config.{password, host, username, seriennummer, cloud_import[].credentials}``, alle 8 ``settings``-Schlüssel,
  ``parameter.{oberflaeche_url, stamm_seriennummer, ansprechpartner_email}``, ``activity_log`` (Ü3-Formen), Log-Puffer,
  **SQL-Echo** (K4), ``writer`` mit E-Mail, die ``NIE``-Tabellen ⇒ in keinem Mitglied ``SPRENGSATZ``; ein JSON-Schlüssel auf
  einem Schlüsselwort steht nur als ``source_hash``/``input_hash``, als Name einer Einstellung der Allowlist oder mit dem Wert
  ``<geschwärzt>`` (Ergänzung zum Bauplan, s. ``_schluessel_im_paket``);
* **S5** — zweimal bereitstellen ⇒ Datenbank unverändert (Dump vor/nach), ``sensor_mapping`` bitgleich; Gegenprobe ``/felder``;
* Akte-Probe (Fall ottokar) auf JSON; Testpunkte 1–4; N-797; Einstellungen-Allowlist; Log ohne ``sqlalchemy.*``;
* Zeitgrenze des Checkers als Teilfehler (K9), eigene Sitzung je Lage-Teil;
* Routen (Variante A): bereitstellen, herunterladen, ``&pruefen=1`` 204/404, Bau wirft ⇒ 500 ohne Datei, Tabelle wirft ⇒
  Paket kommt; Ablage je Anlage, Ablauf nach 15 Minuten, je Datenbank (K7); Marke gilt mehrfach, Abbruch lässt die Datei stehen;
* K1: der Auszug öffnet jede Pfadform der Einstellung; der Standardweg ohne ``db_pfad``;
* Scheduler ``last_run``; ``code`` + ``werte`` an den Melder-Erzeugern (AST).

Fixtures ``voll_datei_db`` (``test_diagnose_paket_auszug.py``) und ``datei_anlage`` (hier: Datei-Datenbank mit einer echten
Anlage über die Factories). Keine Probe liest die Uhr.
"""
from __future__ import annotations

import ast
import asyncio
import io
import json
import logging
import re
import sqlite3
import zipfile
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.config import APP_VERSION
from backend.models.activity_log import ActivityLog
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401 — Tabelle im Schema der Datei
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.daten_checker import CheckErgebnis, DatenChecker, DatenCheckResult
from backend.services.daten_checker.kategorien import Aktion
from backend.services.diagnose_paket import ablage, lage, paket
from backend.services.diagnose_paket import register as reg
from backend.services.diagnose_paket.bereinigung import bereinige_log
from backend.tests import factories
from backend.tests import pv_achse_matrix as mx
from backend.tests.test_diagnose_paket_auszug import SPRENG, voll_datei_db  # noqa: F401 — Fixture

JETZT = datetime(2026, 11, 10, 12, 0)
SCHLUESSELWOERTER = r"token|passw|secret|authorization|api_key|apikey|kundennummer|hash"


class _KeinHa:
    is_available = False


@pytest.fixture(autouse=True)
def _ablage_im_tmp(tmp_path, monkeypatch):
    """Jede Probe mit eigener Ablage; kein HA-Statistik-Dienst der Box."""
    from backend.services import ha_statistics_service

    monkeypatch.setattr(ablage, "VERZEICHNIS", tmp_path / "ablage")
    monkeypatch.setattr(ablage, "_EINTRAEGE", {})
    monkeypatch.setattr(ha_statistics_service, "get_ha_statistics_service", lambda: _KeinHa())


async def _anlage(db, **felder):
    a = await factories.anlage(db, anlagenname="Haus Süd", standort_plz="12345", standort_ort="Musterstadt", **felder)
    await factories.investition(db, a.id, "pv-module", bezeichnung="Süddach", anschaffungsdatum=date(2020, 1, 1),
                                leistung_kwp=8.0, ausrichtung="Süd", neigung_grad=30.0,
                                parameter={"anzahl_module": 20, "modul_leistung_wp": 400, "ausrichtung_grad": 15,
                                           "neigung": 32})
    await factories.investition(db, a.id, "speicher", bezeichnung="Akku", anschaffungsdatum=date(2021, 1, 1),
                                parameter={"kapazitaet_kwh": 10.0, "arbitrage_faehig": True})
    await factories.strompreis(db, a.id, date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=32.5,
                               einspeiseverguetung_cent_kwh=8.2, verwendung="allgemein", vertragsart="fix")
    await factories.monatsdaten(db, a.id, 2026, 10, einspeisung_kwh=120.0, netzbezug_kwh=80.0)
    await db.commit()
    return a


class DateiAnlage:
    def __init__(self, pfad: Path, engine, aid: int):
        self.pfad, self.engine, self.aid = pfad, engine, aid
        macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        self.macher = macher

        @asynccontextmanager
        async def sitzungen():
            async with macher() as s:
                yield s
                await s.commit()

        self.sitzungen = sitzungen


@pytest.fixture
async def datei_anlage(tmp_path):
    pfad = tmp_path / "anlage.db"
    engine, db = await mx._neue_db(str(pfad))
    try:
        await db.execute(text(reg.MIGRATIONS_DDL))
        a = await _anlage(db)
        await db.close()
        yield DateiAnlage(pfad, engine, a.id)
    finally:
        await engine.dispose()


async def _bereit(d, **kw) -> dict:
    kw.setdefault("jetzt", JETZT)
    kw.setdefault("ha_svc", _KeinHa())
    return await paket.bereitstellen(getattr(d, "aid", 1), db_pfad=str(d.pfad), sitzungen=d.sitzungen, **kw)


def _zip(anlage_id: int) -> dict[str, bytes]:
    with zipfile.ZipFile(ablage._EINTRAEGE[anlage_id].pfad) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _lage(anlage_id: int) -> dict:
    return json.loads(_zip(anlage_id)["lage.json"])


def _inhalt(anlage_id: int) -> dict:
    return json.loads(_zip(anlage_id)["inhalt.json"])


def _tabelle(anlage_id: int, t: str) -> list[dict]:
    m = json.loads(_zip(anlage_id)[f"tabellen/{t}.json"])
    return [dict(zip(m["spalten"], z)) for z in m["zeilen"]]


def _dump(pfad: Path) -> list[str]:
    con = sqlite3.connect(pfad)
    try:
        return list(con.iterdump())
    finally:
        con.close()


# ─── Kopf ─────────────────────────────────────────────────────────────────────────────────────────────────────

async def test_kopf_standalone(datei_anlage):
    await _bereit(datei_anlage)
    k = _lage(datei_anlage.aid)["kopf"]
    assert (k["eedc_version"], k["profil"], k["anlage_id"], k["betriebsart"]) == (APP_VERSION, "diagnose",
                                                                                  datei_anlage.aid, "standalone")
    assert k["ha"] == {"verbunden": False, "erreichbar": False, "version": None, "zeitzone": None}
    assert k["erzeugt_am"].startswith("2026-11-10T12:00:00") and set(k["zeitzone"]) == {"iana", "quelle", "kuerzel",
                                                                                           "utc_offset"}


async def test_kopf_addon(datei_anlage, monkeypatch):
    async def _info(_db):
        return {"addon": True, "kind": "ha_app", "erreichbar": True, "version": "2026.11.1", "zeitzone": "Europe/Berlin"}

    monkeypatch.setattr(paket, "ha_info", _info)
    await _bereit(datei_anlage)
    k = _lage(datei_anlage.aid)["kopf"]
    assert k["betriebsart"] == "addon"
    assert k["ha"] == {"verbunden": True, "erreichbar": True, "version": "2026.11.1", "zeitzone": "Europe/Berlin"}


def test_kopf_zeitzone_quellen(tmp_path):
    from backend.core import laufzeit

    jetzt = datetime(2026, 7, 1, 12, 0)
    assert laufzeit.zeitzone(jetzt, tz="Europe/Berlin")["quelle"] == "TZ"
    assert laufzeit.zeitzone(jetzt, tz=":Europe/Vienna")["iana"] == "Europe/Vienna"
    ziel = tmp_path / "usr" / "share" / "zoneinfo" / "Europe" / "Vienna"
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(b"TZif")
    lt = tmp_path / "localtime"
    lt.symlink_to(ziel)
    z = laufzeit.zeitzone(jetzt, tz="", localtime=lt)
    assert (z["iana"], z["quelle"]) == ("Europe/Vienna", "/etc/localtime")
    z = laufzeit.zeitzone(jetzt, tz="Nirgendwo/Stadt", localtime=tmp_path / "fehlt")
    assert (z["iana"], z["quelle"]) == (None, None)
    assert z["kuerzel"] and re.fullmatch(r"[+-]\d\d:\d\d", z["utc_offset"])


async def test_testpunkt3_startzeit_im_kopf(datei_anlage, monkeypatch):
    from backend.core import laufzeit

    monkeypatch.setattr(laufzeit, "_START", None)
    await _bereit(datei_anlage)
    assert _lage(datei_anlage.aid)["kopf"]["gestartet_am"] is None
    laufzeit.merke_start(datetime(2026, 11, 10, 8, 55))
    await _bereit(datei_anlage)
    assert _lage(datei_anlage.aid)["kopf"]["gestartet_am"].startswith("2026-11-10T08:55:00")


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
    monkeypatch.setattr(paket.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(config, "HA_INTEGRATION_AVAILABLE", True)
    info = await paket.ha_info(db)
    assert gerufen == ["http://127.0.0.1:9/SPRENGSATZ/api/config"]
    assert info == {"addon": True, "kind": "ha_app", "erreichbar": True, "version": "2026.11.1",
                    "zeitzone": "Europe/Berlin"}
    assert "SPRENGSATZ" not in repr(info)


# ─── W-7 (c): keine Geheimnisse ──────────────────────────────────────────────────────────────────────────────

def _schluessel_treffer(t: str) -> list[str]:
    """Schlüsselwörter in Schlüssel-Stellung: JSON-Schlüssel, «- schlüssel: …», «schlüssel=…»."""
    treffer = re.findall(rf'"[^"\n]*(?:{SCHLUESSELWOERTER})[^"\n]*"\s*:', t, re.I)
    treffer += re.findall(rf"^\s*- ([\w ./-]{{0,40}}(?:{SCHLUESSELWOERTER})[\w ./-]{{0,40}}):", t, re.I | re.M)
    treffer += re.findall(rf"\b\w*(?:{SCHLUESSELWOERTER})\w*=", t, re.I)
    return treffer


def _eingebettet(wert, out: list) -> None:
    """Alle Strukturen eines Mitglieds, JSON-Zellen (gespeicherter Text) geparst — die «eingebettete Text-Form»."""
    if isinstance(wert, str):
        try:
            innen = json.loads(wert)
        except ValueError:
            return
        if isinstance(innen, (dict, list)):
            out.append(innen)
            _eingebettet(innen, out)
    elif isinstance(wert, dict):
        for v in wert.values():
            _eingebettet(v, out)
    elif isinstance(wert, list):
        for v in wert:
            _eingebettet(v, out)


def _schluessel_im_paket(mitglieder: dict[str, bytes]) -> list[str]:
    """Jeder JSON-Schlüssel auf einem Schlüsselwort (Mitglieder und eingebettete Text-Form). Erlaubt: ``source_hash``,
    ``input_hash`` (Bauplan K6), die Namen der Einstellungs-Allowlist in ``lage.einstellungen`` (Werte dort sind
    Wahrheitswerte/Zähler, §3.3) und ein Schlüssel mit dem Wert ``<geschwärzt>`` (§3.5 Nr 3). Alles andere wird gemeldet."""
    out = []
    rx = re.compile(SCHLUESSELWOERTER, re.I)

    def _lauf(x, pfad):
        if isinstance(x, dict):
            for k, v in x.items():
                erlaubt = (k in reg.ERLAUBTE_SCHLUESSELWORT_NAMEN or v == "<geschwärzt>"
                           or (pfad == "lage.json/einstellungen" and k in reg.EINSTELLUNGEN))
                if rx.search(str(k)) and not erlaubt:
                    out.append(f"{pfad}:{k}")
                _lauf(v, f"{pfad}/{k}" if pfad.count("/") < 1 else pfad)
        elif isinstance(x, list):
            for v in x:
                _lauf(v, pfad)

    for name, roh in mitglieder.items():
        obj = json.loads(roh)
        alle: list = [obj]
        _eingebettet(obj, alle)
        for o in alle:
            _lauf(o, name)
        rest = [t for t in _schluessel_treffer(roh.decode("utf-8")) if not t.startswith('"')]
        out += [f"{name}:{t}" for t in rest]
    return out


def _w7_saat(voll) -> None:
    con = voll.roh()
    for t, tab in reg.REGISTER.items():
        for s, sp in tab.spalten.items():
            if sp.klasse == "raus":
                wert = json.dumps({"x": f"{SPRENG}-{s}"}) if sp.json else f"{SPRENG}-{s}"
                con.execute(f'UPDATE "{t}" SET "{s}" = ?', (wert,))
    werte = {
        "mqtt_inbound": {"enabled": False, "host": f"{SPRENG}-host", "port": 1, "username": f"{SPRENG}-u",
                         "password": f"{SPRENG}-mqtt"},
        "mqtt_export": {"enabled": True, "sensor_paket_stand": 3, "abgewaehlte_sensoren": ["a"], "password": f"{SPRENG}-e"},
        "ha_remote": {"enabled": True, "base_url": f"http://127.0.0.1:9/{SPRENG}", "token": f"{SPRENG}-token"},
        "einstellungen_pin": {"salt": f"{SPRENG}-salt", "hash": f"{SPRENG}-hash", "gesetzt_am": "2026-01-01"},
        "sperre_secret": {"wert": f"{SPRENG}-secret"},
        "custom_import_templates": {f"{SPRENG}-vorlage": {"x": f"{SPRENG}-inhalt"}},
        "community_nachsende_lauf": {"stand": 2, "anlagen": [1], "lauf_erledigt": True},
        "wetter_altbestand_nachzug": {"1": {"bis": "2026-01-01"}, "2": {"x": f"{SPRENG}-andere"}},
    }
    con.executemany("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, '2026-11-01 10:00:00')",
                    [(k, json.dumps(v)) for k, v in werte.items()])
    ue3 = ['{"password": "SPRENGSATZ"}', "{'token': 'SPRENGSATZ'}",
           """[parameters: ('{"enabled": true, "password": "SPRENGSATZ"}', 1)]""", "pw=SPRENGSATZ",
           "Bearer SPRENGSATZ", "https://u:SPRENGSATZ@h/", "kontakt SPRENGSATZ@example.org"]
    con.executemany("INSERT INTO activity_log (timestamp, kategorie, aktion, erfolg, details, anlage_id) "
                    "VALUES ('2026-10-03 10:00:00', 'x', ?, 1, ?, 1)", [(f"Fehler {u}", u) for u in ue3])
    con.commit()
    con.close()


def _w7_log(echo: bool = True) -> None:
    """Log-Puffer mit URL/Token und — bei Log-Stufe debug — dem SQL-Echo (K4)."""
    from backend.core.log_buffer import get_log_buffer

    puffer = get_log_buffer()
    lg = logging.getLogger("backend.test_diagnose_paket")
    lg.addHandler(puffer)
    lg.warning(f"Remote-HA nicht erreichbar: http://127.0.0.1:9/{SPRENG} token={SPRENG}-log Bearer {SPRENG}-b")
    lg.removeHandler(puffer)
    echo_lg = logging.getLogger("sqlalchemy.engine.Engine")
    stufe = echo_lg.level
    echo_lg.setLevel(logging.INFO)
    echo_lg.addHandler(puffer)
    try:
        if echo:
            echo_lg.info(f"[generated in 0.1s] ('{SPRENG}-Strasse 5', 1)")
            echo_lg.info(f"""[generated in 0.1s] ('sperre_secret', '{{"wert": "{SPRENG}-s"}}')""")
    finally:
        echo_lg.removeHandler(puffer)
        echo_lg.setLevel(stufe)


async def test_w7_kein_geheimnis_im_paket(voll_datei_db):
    _w7_saat(voll_datei_db)
    _w7_log()
    felder = await _bereit(voll_datei_db)
    mitglieder = _zip(1)
    funde = [n for n, roh in mitglieder.items() if SPRENG.encode() in roh]
    assert funde == []
    assert SPRENG not in json.dumps(felder, ensure_ascii=False)
    assert _schluessel_im_paket(mitglieder) == []
    lg = json.loads(mitglieder["lage.json"])
    assert lg["einstellungen"].get("sperre_secret") == {"vorhanden": True}, lg["einstellungen"]
    assert lg["einstellungen"]["ha_remote"] == {"eingerichtet": True, "enabled": True}
    assert lg["einstellungen"]["wetter_altbestand_nachzug"] == {"1": {"bis": "2026-01-01"}}
    assert json.loads(mitglieder["inhalt.json"])["log_ausgelassen"] >= 2
    assert any("<url>" in z["message"] for z in lg["log"])
    # Die Sentinel-Spalten stehen gar nicht im Paket.
    an = json.loads(mitglieder["tabellen/anlagen.json"])["spalten"]
    assert not {"standort_strasse", "mastr_id", "community_hash", "versorger_daten"} & set(an)


def test_w7_schluessel_pruefung_hat_zaehne():
    assert _schluessel_treffer('{"api_key":"x"}') and _schluessel_treffer("- token: x")
    assert _schluessel_treffer("Parameter community_hash=1") and _schluessel_treffer("- Kundennummer: 4711")
    assert not _schluessel_treffer("- [info] sensor_mapping_lts — Token fehlt: nichts")


def test_w7c_scan_findet_gesaetes():
    mitglieder = {"tabellen/x.json": json.dumps({"spalten": ["a", "b"], "zeilen": [
        ["{\"api_key\": \"x\"}", "SPRENGSATZ"]]}).encode()}
    assert _schluessel_im_paket(mitglieder) == ["tabellen/x.json:api_key"]
    assert [n for n, roh in mitglieder.items() if SPRENG.encode() in roh] == ["tabellen/x.json"]
    erlaubt = {"tabellen/y.json": json.dumps({"spalten": ["s"], "zeilen": [[json.dumps(
        {"f": {"input_hash": "1", "password": "<geschwärzt>"}})]]}).encode()}
    assert _schluessel_im_paket(erlaubt) == []


async def test_w7c_sprengsatz_echo_filter_aus(voll_datei_db, monkeypatch):
    monkeypatch.setattr(lage, "LOG_AUSGESCHLOSSEN", "kein_logger_heisst_so")
    _w7_log()
    await _bereit(voll_datei_db)
    assert SPRENG.encode() in _zip(1)["lage.json"]


def test_log_bereinigung():
    z = bereinige_log("Fehler bei https://user:pw@ha.local:8123/api token=abc Authorization: Bearer xyz")
    assert "pw@" not in z and "abc" not in z and "xyz" not in z and "<url>" in z


@pytest.mark.parametrize("probe", [
    '{"password": "SPRENGSATZ"}', "{'token': 'SPRENGSATZ'}",
    """[parameters: ('{"enabled": true, "password": "SPRENGSATZ"}', 1)]""", "pw=SPRENGSATZ", "pw: SPRENGSATZ",
    "Bearer SPRENGSATZ", "https://u:SPRENGSATZ@h/", "kontakt SPRENGSATZ@example.org", "credential=SPRENGSATZ"])
def test_log_bereinigung_ue3_formen(probe):
    assert SPRENG not in bereinige_log(probe)


def test_log_bereinigung_laesst_entity_und_modus_stehen():
    for t in ("sensor.pv_leistung", "select.wp_betriebsmodus", "Heizen", "inv:14:stromverbrauch_kwh"):
        assert bereinige_log(t) == t


# ─── S5: bereitstellen schreibt nichts ───────────────────────────────────────────────────────────────────────

async def _roh_mapping(pfad: Path, aid: int):
    con = sqlite3.connect(pfad)
    try:
        return con.execute("SELECT sensor_mapping FROM anlagen WHERE id = ?", (aid,)).fetchone()[0]
    finally:
        con.close()


async def test_s5_zweimal_abrufen_schreibt_nichts(tmp_path):
    from backend.api.routes.datenquellen import get_datenquellen_felder

    pfad = tmp_path / "s5.db"
    engine, db = await mx._neue_db(str(pfad))
    try:
        await db.execute(text(reg.MIGRATIONS_DDL))
        mapping = {"investitionen": {"1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}},
                                           "live": {"leistung_w": "sensor.pv_w"}}}}
        a = await factories.anlage_mit_pv(db, mapping)
        await db.commit()
        await db.close()
        d = DateiAnlage(pfad, engine, a.id)
        vorher, mapping_vorher = _dump(pfad), await _roh_mapping(pfad, a.id)
        for _ in range(2):
            await _bereit(d)
            assert _dump(pfad) == vorher
        z = _lage(a.id)["zuordnungen"]
        assert "inv_energy_1_pv_erzeugung_kwh" in z["neu_aufgeloest"]
        # Gegenprobe: die Route /felder schreibt dieselbe Auflösung fest — ohne den Schnitt hätte das Paket es auch getan.
        async with d.macher() as s:
            await get_datenquellen_felder(a.id, s)
            await s.commit()
        assert await _roh_mapping(pfad, a.id) != mapping_vorher
    finally:
        await engine.dispose()


# ─── Akte-Probe (Fall ottokar), Testpunkte ───────────────────────────────────────────────────────────────────

async def test_akte_probe_sechs_fragen(datei_anlage, monkeypatch):
    aid = datei_anlage.aid
    async with datei_anlage.sitzungen() as db:
        from backend.models.anlage import Anlage

        a = await db.get(Anlage, aid)
        a.sensor_mapping = {"quellen": {"basis_energy_pv_gesamt_kwh": {"quelle": "ha_connector",
                                                                       "entity_id": "sensor.pv_gesamt"}}}
        k = Kanal(anlage_id=aid, key="basis:pv_gesamt", einheit="kWh", art=ART_SUM)
        db.add(k)
        await db.flush()
        ab = int(datetime(2026, 11, 1).timestamp())
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=ab, familie=FAMILIE_SPIEGEL, statistic_id="sensor.pv_gesamt",
                           offset=0.0))
        db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ab + 3600 * i, sum=float(i), state=float(i),
                                   familie=FAMILIE_SPIEGEL) for i in range(48)])
        for tag in (1, 2, 3):
            db.add(TagesZusammenfassung(anlage_id=aid, datum=date(2026, 11, tag), datenquelle="ha_statistics",
                                        stunden_verfuegbar=24, komponenten_kwh={"pv_1": 10.0 + tag}))
        db.add_all([
            ActivityLog(kategorie="scheduler", erfolg=True, anlage_id=aid, timestamp=datetime(2026, 11, 10, 2, 45),
                        aktion="Kanalstatistik: Konsistenzlauf — alle Abschnitte stimmen mit HA überein",
                        details="1 Abschnitte in 1 Kanälen geprüft · gleich 1 · korrigiert 0 · gekürzt 0 · Fehler 0"),
            ActivityLog(kategorie="repair", aktion="Reparatur: Tag neu aggregieren — 2026-11-02", erfolg=True,
                        details="Änderungen: tage 1", anlage_id=aid, timestamp=datetime(2026, 11, 8, 20, 0)),
            ActivityLog(kategorie="scheduler", aktion="Wetter: fremde Zeile", erfolg=True, anlage_id=aid),
        ])
    drift = CheckErgebnis(
        kategorie="datenquelle_drift", schwere="info",
        meldung="2026-11-02: PV 123.909,6 → HA 13,7 kWh (Δ −123.895,9 kWh, −100,0 %)",
        details="Tag mit Abweichung", action=Aktion("spiegel_abgleich_tag", {"datum": "2026-11-02"}),
        code="drift_tag", werte={"datum": "2026-11-02", "achse": "pv", "eedc": 123909.6, "ha": 13.7, "delta": -123895.9,
                                 "prozent": -99.99},
    )

    async def _check(self, _aid):
        return DatenCheckResult(anlage_id=_aid, anlage_name="Haus Süd", ergebnisse=[drift],
                                zusammenfassung={"error": 0, "warning": 0, "info": 1, "ok": 0})

    monkeypatch.setattr(DatenChecker, "check_anlage", _check)
    await _bereit(datei_anlage)
    lg = _lage(aid)
    # (1) Version und Betriebsart
    assert lg["kopf"]["eedc_version"] == APP_VERSION and lg["kopf"]["betriebsart"] == "standalone"
    # (2) welche Drift-Zeile, mit beiden Werten und den Details (Testpunkt 1)
    b = lg["daten_checker"]["ergebnisse"][0]
    assert (b["code"], b["werte"]["eedc"], b["werte"]["ha"], b["details"]) == ("drift_tag", 123909.6, 13.7,
                                                                               "Tag mit Abweichung")
    # (3), (4) Nachtlauf und Klick — und jetzt auch die übrigen Zeilen der Anlage (Q5)
    akt = {z["aktion"] for z in _tabelle(aid, "activity_log")}
    assert {"Kanalstatistik: Konsistenzlauf — alle Abschnitte stimmen mit HA überein",
            "Reparatur: Tag neu aggregieren — 2026-11-02", "Wetter: fremde Zeile"} <= akt
    # (5) Spiegel ganz, Tage, Quellen
    assert len(_tabelle(aid, "kanal_statistik")) == 48
    assert [q["statistic_id"] for q in _tabelle(aid, "kanal_quelle")] == ["sensor.pv_gesamt"]
    assert sorted(t["datum"] for t in _tabelle(aid, "tages_zusammenfassung")) == ["2026-11-01", "2026-11-02",
                                                                                  "2026-11-03"]
    # (6) Monate und Entity je Feld
    assert [(m["jahr"], m["monat"]) for m in _tabelle(aid, "monatsdaten")] == [(2026, 10)]
    felder = [f for g in lg["zuordnungen"]["gruppen"] for f in g["felder"]]
    assert any(f.get("ha_entity") == "sensor.pv_gesamt" for f in felder)


async def test_testpunkt1_checker_wie_route(datei_anlage):
    from backend.api.routes.daten_checker import daten_check

    await _bereit(datei_anlage)
    async with datei_anlage.macher() as s:
        route = (await daten_check(datei_anlage.aid, db=s)).model_dump(mode="json")
    assert _lage(datei_anlage.aid)["daten_checker"] == route


async def test_testpunkt2_alle_monate_und_tage(datei_anlage):
    aid = datei_anlage.aid
    async with datei_anlage.sitzungen() as db:
        for j in (2024, 2025):
            for m in range(1, 13):
                await factories.monatsdaten(db, aid, j, m, einspeisung_kwh=float(m))
        db.add_all([TagesZusammenfassung(anlage_id=aid, datum=date(2025, 1, 1) + (date(2025, 1, 2) - date(2025, 1, 1)) * i,
                                         datenquelle="ha_statistics") for i in range(400)])
    felder = await _bereit(datei_anlage)
    assert len(_tabelle(aid, "monatsdaten")) == 25 and felder["inhalt"]["tageswerte"] == 400
    assert felder["inhalt"]["monatswerte"] == 25


async def test_testpunkt4_source_provenance(datei_anlage):
    aid = datei_anlage.aid
    prov = {"einspeisung_kwh": {"source": "auto:monatsabschluss", "writer": "monatsabschluss_wizard",
                                "at": "2026-11-01T10:00:00", "input_hash": "abc", "abgeleitet": "aus Tagen"}}
    con = sqlite3.connect(datei_anlage.pfad)
    con.execute("UPDATE monatsdaten SET source_provenance = ?, datenquelle = NULL WHERE anlage_id = ?",
                (json.dumps(prov), aid))
    con.commit()
    con.close()
    await _bereit(datei_anlage)
    md = _tabelle(aid, "monatsdaten")[0]
    assert md["datenquelle"] is None and json.loads(md["source_provenance"]) == prov


async def test_n797_ausrichtung_neigung_im_paket(datei_anlage):
    await _bereit(datei_anlage)
    pv = next(i for i in _tabelle(datei_anlage.aid, "investitionen") if i["typ"] == "pv-module")
    assert (pv["ausrichtung"], pv["neigung_grad"]) == ("Süd", 30.0)
    p = json.loads(pv["parameter"])
    assert (p["ausrichtung_grad"], p["neigung"]) == (15, 32)


async def test_einstellungen_allowlist(datei_anlage):
    con = sqlite3.connect(datei_anlage.pfad)
    werte = {"mqtt_inbound": {"enabled": True, "host": "h", "password": "p"},
             "mqtt_export": {"enabled": False, "sensor_paket_stand": 4, "abgewaehlte_sensoren": ["s"], "x": 1},
             "ha_remote": {"enabled": False, "base_url": "", "token": "t"}, "einstellungen_pin": {"salt": "s"},
             "sperre_secret": {"wert": "w"}, "custom_import_templates": {"a": {}, "b": {}},
             "community_nachsende_lauf": {"stand": 1, "anlagen": [1], "lauf_erledigt": False},
             "wetter_altbestand_nachzug": {str(datei_anlage.aid): "fertig", "99": "x"}, "neuer_schluessel": {"y": 1}}
    con.executemany("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, '2026-11-01 10:00:00')",
                    [(k, json.dumps(v)) for k, v in werte.items()])
    con.commit()
    con.close()
    await _bereit(datei_anlage)
    lg = _lage(datei_anlage.aid)
    assert lg["einstellungen"] == {
        "community_nachsende_lauf": {"stand": 1, "anlagen": [1], "lauf_erledigt": False},
        "custom_import_templates": {"anzahl": 2}, "einstellungen_pin": {"gesetzt": False},
        "ha_remote": {"eingerichtet": False, "enabled": False}, "mqtt_export": {"enabled": False, "sensor_paket_stand": 4,
                                                                                "abgewaehlte_sensoren": ["s"]},
        "mqtt_inbound": {"enabled": True}, "sperre_secret": {"vorhanden": True},
        "wetter_altbestand_nachzug": {str(datei_anlage.aid): "fertig"}}
    assert lg["schema"]["einstellungen_unbekannt"] == ["neuer_schluessel"]


async def test_log_ohne_sqlalchemy_zeilen(datei_anlage):
    from backend.core.log_buffer import get_log_buffer

    puffer = get_log_buffer()
    for name in ("sqlalchemy", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
        lg = logging.getLogger(name)
        lg.addHandler(puffer)
        lg.warning("echo-zeile %s", name)
        lg.removeHandler(puffer)
    await _bereit(datei_anlage)
    lg = _lage(datei_anlage.aid)["log"]
    assert not any(z["logger_name"] == "sqlalchemy" or z["logger_name"].startswith("sqlalchemy.") for z in lg)
    assert _inhalt(datei_anlage.aid)["log_ausgelassen"] >= 3


# ─── Zeitgrenze, Sitzungen ───────────────────────────────────────────────────────────────────────────────────

async def test_checker_zeitgrenze_teilfehler_rest_ok(datei_anlage, monkeypatch):
    async def _haengt(self, _aid):
        await asyncio.sleep(5)

    monkeypatch.setattr(DatenChecker, "check_anlage", _haengt)
    monkeypatch.setattr(lage, "CHECKER_ZEITGRENZE_S", 0.2)
    felder = await _bereit(datei_anlage)
    lg, inhalt = _lage(datei_anlage.aid), _inhalt(datei_anlage.aid)
    assert lg["daten_checker"] == {"fehler": "zeitgrenze"}
    assert inhalt["lage"]["daten_checker"] == "zeitgrenze"
    assert {t: s for t, s in inhalt["lage"].items() if s != "ok"} == {"daten_checker": "zeitgrenze"}
    assert all(s["status"] == "ok" for s in inhalt["tabellen"].values())
    assert inhalt["vollstaendig"] is True and felder["teilfehler"] == ["lage.daten_checker"]
    assert lg["zuordnungen"]["gruppen"] is not None and lg["kopf"]["anlage_id"] == datei_anlage.aid


async def test_lage_teile_eigene_sitzung(datei_anlage):
    gesehen: list = []
    echt = datei_anlage.sitzungen

    @asynccontextmanager
    async def _zaehlend():
        async with echt() as s:
            gesehen.append(s)          # das Objekt festhalten — sonst könnte `id()` einer freigegebenen Sitzung wiederkehren
            yield s

    datei_anlage.sitzungen = _zaehlend
    await _bereit(datei_anlage)
    # Anlagenname, Kopf, Checker, Zuordnungen, Einstellungen, HA-Abgleich (Abschnitte lesen) — je eine eigene Sitzung.
    assert len(gesehen) >= 6 and len({id(x) for x in gesehen}) == len(gesehen)


# ─── Routen (Variante A), Ablage ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def standard_auf(monkeypatch):
    def _setze(d):
        monkeypatch.setattr(paket, "_db_pfad_standard", lambda: str(d.pfad))
        monkeypatch.setattr(paket, "_sitzungen_standard", lambda: d.sitzungen)
    return _setze


async def test_route_bereitstellen_und_herunterladen(datei_anlage, standard_auf):
    from fastapi.responses import FileResponse

    from backend.api.routes.daten_checker import diagnose_paket, diagnose_paket_bereitstellen

    standard_auf(datei_anlage)
    felder = await diagnose_paket_bereitstellen(datei_anlage.aid)
    assert set(felder) == {"marke", "dateiname", "bytes", "megabyte", "gueltig_s", "versandweg", "inhalt", "teilfehler"}
    assert felder["gueltig_s"] == 900 and felder["versandweg"] == "email" and felder["megabyte"] == felder["bytes"] / 1e6
    assert re.fullmatch(r"eedc_diagnose_Haus-S-d_\d{4}-\d{2}-\d{2}\.zip", felder["dateiname"])
    assert felder["inhalt"]["geraete"] == 2 and felder["inhalt"]["tarife"] == 1
    r = await diagnose_paket(datei_anlage.aid, marke=felder["marke"], pruefen=False)
    assert isinstance(r, FileResponse) and r.media_type == "application/zip"
    assert f'filename="{felder["dateiname"]}"' in r.headers["content-disposition"]
    assert Path(r.path).stat().st_size == felder["bytes"]
    with pytest.raises(HTTPException) as e:
        await diagnose_paket_bereitstellen(999999)
    assert e.value.status_code == 404


async def test_pruefen_204_404(datei_anlage, standard_auf):
    from backend.api.routes.daten_checker import diagnose_paket, diagnose_paket_bereitstellen

    standard_auf(datei_anlage)
    marke = (await diagnose_paket_bereitstellen(datei_anlage.aid))["marke"]
    assert (await diagnose_paket(datei_anlage.aid, marke=marke, pruefen=True)).status_code == 204
    for aid, m in ((datei_anlage.aid, "falsch"), (datei_anlage.aid, ""), (999999, marke)):
        with pytest.raises(HTTPException) as e:
            await diagnose_paket(aid, marke=m, pruefen=True)
        assert e.value.status_code == 404


async def test_g5_bau_wirft_500_keine_datei(datei_anlage, standard_auf, monkeypatch, tmp_path):
    from backend.api.routes.daten_checker import diagnose_paket_bereitstellen

    def _wirft(*a, **k):
        raise RuntimeError("Probe token=SPRENGSATZ")

    standard_auf(datei_anlage)
    monkeypatch.setattr(paket, "auszug", _wirft)
    with pytest.raises(HTTPException) as e:
        await diagnose_paket_bereitstellen(datei_anlage.aid)
    assert e.value.status_code == 500 and e.value.detail.startswith("RuntimeError: Probe") and SPRENG not in e.value.detail
    assert list((tmp_path / "ablage").glob("*")) == [] and datei_anlage.aid not in ablage._EINTRAEGE


async def test_g5_tabelle_wirft_paket_kommt(datei_anlage, monkeypatch):
    from backend.services.diagnose_paket import auszug as az

    echt = az._zellen_wandler

    def _wandler(t, *a, **k):
        if t == "strompreise":
            raise ValueError("Probe")
        return echt(t, *a, **k)

    monkeypatch.setattr(az, "_zellen_wandler", _wandler)
    felder = await _bereit(datei_anlage)
    inhalt = _inhalt(datei_anlage.aid)
    assert inhalt["tabellen"]["strompreise"] == {"zeilen": 0, "status": "fehler", "grund": "ValueError: Probe"}
    assert inhalt["vollstaendig"] is True and felder["teilfehler"] == ["strompreise"]
    assert inhalt["tabellen"]["investitionen"]["status"] == "ok"


async def test_ablage_eine_je_anlage(datei_anlage, tmp_path):
    erst = await _bereit(datei_anlage)
    pfad1 = ablage._EINTRAEGE[datei_anlage.aid].pfad
    zweit = await _bereit(datei_anlage)
    assert not pfad1.exists() and ablage._EINTRAEGE[datei_anlage.aid].pfad.exists()
    assert ablage.gueltig(datei_anlage.aid, erst["marke"]) is None
    assert ablage.gueltig(datei_anlage.aid, zweit["marke"]) is not None
    assert len([p for p in (tmp_path / "ablage").iterdir()]) == 1
    modus = (tmp_path / "ablage").stat().st_mode & 0o777, ablage._EINTRAEGE[datei_anlage.aid].pfad.stat().st_mode & 0o777
    assert modus == (0o700, 0o600)


async def test_ablage_ablauf_15_minuten(datei_anlage, monkeypatch):
    uhr = [1000.0]
    monkeypatch.setattr(ablage, "UHR", lambda: uhr[0])
    marke = (await _bereit(datei_anlage))["marke"]
    pfad = ablage._EINTRAEGE[datei_anlage.aid].pfad
    uhr[0] += 899
    assert ablage.gueltig(datei_anlage.aid, marke) is not None
    uhr[0] += 2
    assert ablage.gueltig(datei_anlage.aid, marke) is None and not pfad.exists()


def _zwei_ablagen(tmp_path, monkeypatch) -> bool:
    """Datei der Datenbank B überlebt das Aufräumen beim Start von A?"""
    pfad_b = ablage.bereit("/daten/b.db") / "b.zip"
    pfad_b.write_bytes(b"x")
    a = ablage.bereit("/daten/a.db") / "a.zip"
    a.write_bytes(b"x")
    ablage.raeume_beim_start("/daten/a.db")
    return pfad_b.exists() and not a.exists()


def test_ablage_start_raeumt_nur_eigene(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(ablage, "VERZEICHNIS", None)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert ablage.verzeichnis("/daten/a.db") != ablage.verzeichnis("/daten/b.db")
    assert ablage.verzeichnis("/daten/a.db").name.startswith("eedc-diagnose-")
    assert _zwei_ablagen(tmp_path, monkeypatch) is True
    # Sprengsatz: ein gemeinsames Verzeichnis für alle Datenbanken ⇒ der Start der einen löscht die Datei der anderen.
    monkeypatch.setattr(ablage, "VERZEICHNIS", tmp_path / "gemeinsam")
    assert _zwei_ablagen(tmp_path, monkeypatch) is False


async def test_versandweg_grenze(datei_anlage, monkeypatch):
    groesse = (await _bereit(datei_anlage))["bytes"]
    for grenze, weg in ((groesse + 100, "email"), (100, "freigabe_link")):
        monkeypatch.setattr(paket, "MAIL_GRENZE_BYTES", grenze)
        assert (await _bereit(datei_anlage))["versandweg"] == weg


def test_mail_grenze_ist_zehn_megabyte():
    assert paket.MAIL_GRENZE_BYTES == 10_000_000


async def _abrufen(r) -> tuple[int, bytes]:
    """Die Antwort wirklich ausliefern (ASGI, samt Hintergrund-Aufgaben) — Status und Körper."""
    teile: list = []
    status: list = []

    async def _empfang():
        await asyncio.sleep(10)
        return {"type": "http.disconnect"}

    async def _senden(nachricht):
        if nachricht["type"] == "http.response.start":
            status.append(nachricht["status"])
        elif nachricht["type"] == "http.response.body":
            teile.append(nachricht.get("body", b""))

    await r({"type": "http", "method": "GET", "headers": [], "http_version": "1.1"}, _empfang, _senden)
    return status[0], b"".join(teile)


async def test_marke_gilt_mehrfach_bis_ablauf(datei_anlage, standard_auf):
    """Maßgabe Master aus S0: die Android-App ruft die Adresse zweimal — die Marke gilt mehrfach, die Datei bleibt stehen."""
    from backend.api.routes.daten_checker import diagnose_paket, diagnose_paket_bereitstellen

    standard_auf(datei_anlage)
    marke = (await diagnose_paket_bereitstellen(datei_anlage.aid))["marke"]
    inhalte = []
    for _ in range(2):
        status, koerper = await _abrufen(await diagnose_paket(datei_anlage.aid, marke=marke, pruefen=False))
        assert status == 200
        inhalte.append(koerper)
    assert inhalte[0] == inhalte[1] and zipfile.is_zipfile(io.BytesIO(inhalte[0]))
    assert ablage._EINTRAEGE[datei_anlage.aid].pfad.is_file()


async def test_abgebrochener_abruf_laesst_datei_stehen(datei_anlage, standard_auf):
    from backend.api.routes.daten_checker import diagnose_paket, diagnose_paket_bereitstellen

    standard_auf(datei_anlage)
    marke = (await diagnose_paket_bereitstellen(datei_anlage.aid))["marke"]
    voll = Path(ablage._EINTRAEGE[datei_anlage.aid].pfad).read_bytes()
    r = await diagnose_paket(datei_anlage.aid, marke=marke, pruefen=False)
    r.chunk_size = 64
    gesendet = []

    async def _empfang():
        await asyncio.sleep(10)
        return {"type": "http.disconnect"}

    async def _senden(nachricht):
        if nachricht["type"] == "http.response.body":
            gesendet.append(nachricht["body"])
            if len(gesendet) == 2:
                raise OSError("Client hat die Verbindung geschlossen")

    scope = {"type": "http", "method": "GET", "headers": [], "http_version": "1.1"}
    with pytest.raises(OSError):
        await r(scope, _empfang, _senden)
    assert b"".join(gesendet) != voll                          # abgebrochen, nicht vollständig
    status, koerper = await _abrufen(await diagnose_paket(datei_anlage.aid, marke=marke, pruefen=False))
    assert (status, koerper) == (200, voll)


# ─── K1: Pfadformen, Standardweg ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["eedc.db", "mit leer # ? % zeichen.db"])
async def test_auszug_oeffnet_den_pfad_der_einstellung(tmp_path, name):
    from backend.services.diagnose_paket import auszug as az

    verz = tmp_path / "unter ordner"
    verz.mkdir()
    pfad = verz / name
    con = sqlite3.connect(pfad)
    con.execute("CREATE TABLE anlagen (id INTEGER PRIMARY KEY, anlagenname TEXT)")
    con.execute("INSERT INTO anlagen VALUES (1, 'x')")
    con.commit()
    con.close()
    for form in (str(pfad), "/" + str(pfad)):        # «//tmp/…» ist die Form aus settings.database_path
        c = az.verbinde(form)
        assert c.execute("SELECT anlagenname FROM anlagen").fetchone() == ("x",)
        c.close()
    # Sprengsatz: den Pfad in die URI kleben ⇒ «invalid uri authority» (bzw. falsche Datei bei Sonderzeichen).
    with pytest.raises(sqlite3.OperationalError):
        sqlite3.connect(f"file:{'/' + str(pfad)}?mode=ro", uri=True).execute("SELECT 1 FROM anlagen")


async def test_bereitstellen_ohne_db_pfad_standardweg():
    """Der Standardweg der Route: ``settings.database_path`` (Form ``//tmp/…``) und ``get_session`` — die Test-Datenbank
    dieses Workers (conftest). Ohne ``db_pfad`` muss der Auszug genau diese Datei lesen."""
    from sqlalchemy import delete

    from backend.core.config import settings
    from backend.core.database import get_session
    from backend.models.anlage import Anlage

    assert str(settings.database_path).startswith("//")
    async with get_session() as db:
        a = Anlage(anlagenname="Standardweg K1", leistung_kwp=1.0)
        db.add(a)
        await db.flush()
        aid = a.id
    try:
        await paket.bereitstellen(aid, jetzt=JETZT, ha_svc=_KeinHa())
        # Die Worker-Datenbank trägt nicht jede Tabelle (conftest) — geprüft wird, dass genau diese Datei gelesen wurde.
        assert _inhalt(aid)["tabellen"]["anlagen"] == {"zeilen": 1, "status": "ok", "grund": None}
        assert [z["anlagenname"] for z in _tabelle(aid, "anlagen")] == ["Standardweg K1"]
    finally:
        async with get_session() as db:
            await db.execute(delete(Anlage).where(Anlage.id == aid))


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


# ─── code + werte an den Melder-Erzeugern (Erhebung Teil B) ───────────────────────────────────────────────────

_ERZEUGER = {
    "datenquelle/ha_rueckgang.py": ["ha_zaehler_rueckgang"],
    "datenquelle/ha_sprung.py": ["ha_zaehlersprung"],
    # E5: die Drift-Zeilen stehen in `drift_zeilen.py`, die Restzeile `drift_weitere_tage` ist entfallen (V2).
    "datenquelle/drift_zeilen.py": ["drift_tag", "drift_komponente"],
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
