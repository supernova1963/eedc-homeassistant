"""Werkbank «Werte vor dem Sensorbeginn verwerfen» (HA-Bauform S3, E-S3-5; Bauplan §7, Entscheid S3-E2).

Proben am selbst gesäten Datenstand (In-Memory-DB, keine HA nötig): ein Feld mit Sensortausch (zwei ``kanal_quelle``),
Kanalzeilen über den Tausch, Stunden- und Tageszeilen davor und danach, ein Monat mit Abschluss.

* **Vorschau schreibt nichts** und nennt Quellen (``statistic_id``, ``gueltig_ab``), Kanalzeilen, Bestandstage, Monate mit
  Abschluss und die Tage, die danach keinen Wert mehr haben — Zahlen gegen den Seed nachgerechnet.
* **Ausführung feldgenau in beiden Schichten:** Kanalzeilen vor ``t`` weg, ab ``t`` unverändert; ``kanal_quelle`` bleibt,
  die ältere trägt ``verworfen_ts``; in Stunden-/Tageszeilen nur die Schlüssel dieses Feldes (alle übrigen Spalten
  bitgleich); Monate mit Abschluss unberührt; Provenance ``verworfen:werkbank``; Aktivität in derselben Sitzung.
* **Idempotent:** zweiter Lauf 0/0, Vorschau «Nichts zu verwerfen».
* **Gerätefeld:** nur der ``komponenten_kwh``-Eintrag des Geräts; der Leistungspfad ``komponenten`` bleibt (⛔ H-3, Option B
  im Bericht); ein zweites Feld desselben Eintrags wird genannt.
* **Eingaben** (Zeitpunkt, Quellenzahl, Art, Schlüssel) und die lesende Auswahl-Route; Migration ``verworfen_ts``.

Schwesterdateien: test_werkbank_verwerfen_kommt_nicht_zurueck.py (H-2: Startlauf, Stände-Nachfüllen, Konsistenzlauf,
Stundenlauf), test_repair_orchestrator.py, test_kanal_nachfuellen.py.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm.attributes import flag_modified

from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.data_provenance_log import DataProvenanceLog
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services import verwerfen_vor_quellbeginn as vq
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
    _reset_state_for_tests,
    execute,
    plan,
)

T0 = datetime(2026, 4, 1, 0)        # Beginn des alten Sensors
TW = datetime(2026, 4, 21, 0)       # Beginn des neuen Sensors (Sensortausch)
ENDE = datetime(2026, 4, 24, 0)
BESTAND_TAGE = (date(2026, 3, 30), date(2026, 3, 31), date(2026, 4, 5), date(2026, 4, 20), date(2026, 4, 21),
                date(2026, 4, 22))
GELEERT = (date(2026, 4, 5), date(2026, 4, 20))       # vor t, kein Abschluss
OP = RepairOperationType.VERWERFEN_VOR_QUELLBEGINN


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


@pytest.fixture(autouse=True)
def _leer():
    _reset_state_for_tests()


async def _kanal(db, aid, key, quellen, *, art="sum", zeilen=True) -> Kanal:
    k = Kanal(anlage_id=aid, key=key, art=art, einheit="kWh")
    db.add(k)
    await db.flush()
    for ab, sid in quellen:
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(ab), familie="spiegel", statistic_id=sid, offset=0.0))
    ts, i = _ts(T0) - 3600, 0
    while zeilen and ts < _ts(ENDE):
        db.add(KanalStatistik(kanal_id=k.id, start_ts=ts, sum=i * 0.5, state=i * 0.5, familie="spiegel"))
        ts, i = ts + 3600, i + 1
    return k


async def _saat(db) -> dict:
    a = Anlage(anlagenname="Tausch", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süddach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    sp = Investition(anlage_id=a.id, typ="speicher", bezeichnung="Akku", anschaffungsdatum=date(2024, 1, 1))
    db.add_all([pv, sp])
    await db.flush()
    a.sensor_mapping = {
        "basis": {"einspeisung": _s("sensor.einsp_neu"), "netzbezug": _s("sensor.netz")},
        "investitionen": {
            str(pv.id): {"felder": {"pv_erzeugung_kwh": _s("sensor.pv_neu")}},
            str(sp.id): {"felder": {"ladung_kwh": _s("sensor.lad_neu"), "entladung_kwh": _s("sensor.entl")}},
        },
    }
    flag_modified(a, "sensor_mapping")
    tausch = [(T0, "sensor.einsp_alt"), (TW, "sensor.einsp_neu")]
    await _kanal(db, a.id, "basis:einspeisung", tausch)
    await _kanal(db, a.id, "basis:netzbezug", [(T0, "sensor.netz")])
    await _kanal(db, a.id, f"inv:{pv.id}:pv_erzeugung_kwh", [(T0, "sensor.pv_alt"), (TW, "sensor.pv_neu")])
    await _kanal(db, a.id, f"inv:{sp.id}:ladung_kwh", [(T0, "sensor.lad_alt"), (TW, "sensor.lad_neu")])
    await _kanal(db, a.id, f"inv:{sp.id}:entladung_kwh", [(T0, "sensor.entl")])
    await _kanal(db, a.id, "basis:strompreis", [(T0, "sensor.p_alt"), (TW, "sensor.p_neu")], art="mean")
    for d in BESTAND_TAGE:
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=a.id, datum=d, stunde=h, pv_kw=2.0, einspeisung_kw=0.7, netzbezug_kw=0.3, verbrauch_kw=1.6,
                batterie_kw=-0.2, temperatur_c=11.0, soc_prozent=50.0, strompreis_cent=30.0,
                komponenten={f"pv_{pv.id}": 2.0, f"batterie_{sp.id}": -0.2, f"soc_{sp.id}": 50.0, "netz": -0.4},
                spannen={"einspeisung": 2, "pv": 2} if h == 5 else None,
                source_provenance={"einspeisung_kw": {"source": "external:ha_statistics:hourly"}},
            ))
        db.add(TagesZusammenfassung(
            anlage_id=a.id, datum=d, kraftstoffpreis_euro=1.7, pv_prognose_kwh=20.0, verworfen={},
            komponenten_kwh={"einspeisung": 5.0, f"pv_{pv.id}": 10.0, f"batterie_{sp.id}": -1.0},
            source_provenance={"komponenten_kwh.einspeisung": {"source": "external:ha_statistics:daily"}},
        ))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=3, einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    await db.commit()
    return {"aid": a.id, "pv": pv.id, "sp": sp.id}


async def _dump(db, tabelle: str) -> dict:
    spalten = [r[1] for r in (await db.execute(text(f"PRAGMA table_info({tabelle})"))).all()
               if r[1] not in ("created_at", "updated_at")]
    return {r[0]: dict(zip(spalten, r)) for r in (await db.execute(
        text(f"SELECT {', '.join(spalten)} FROM {tabelle} ORDER BY id"))).all()} if "id" in spalten else {
        tuple(r[:2]): dict(zip(spalten, r)) for r in (await db.execute(
            text(f"SELECT {', '.join(spalten)} FROM {tabelle} ORDER BY 1, 2"))).all()}


async def _alles(db) -> dict:
    return {t: await _dump(db, t) for t in ("tages_energie_profil", "tages_zusammenfassung", "kanal_statistik",
                                           "kanal_quelle", "activity_log", "data_provenance_log")}


def _md5_ohne(zeile: dict, ohne: set[str]) -> str:
    return hashlib.md5(json.dumps({k: v for k, v in zeile.items() if k not in ohne}, sort_keys=True,
                                  default=str).encode()).hexdigest()


def _req(aid: int, key: str = "basis:einspeisung", zeitpunkt: str = "2026-04-21T00:00") -> RepairOperationRequest:
    return RepairOperationRequest(anlage_id=aid, operation=OP, params={"kanal": key, "zeitpunkt": zeitpunkt})


async def test_vorschau_schreibt_nichts_und_nennt_quellen_tage_und_abschluss(db):
    ids = await _saat(db)
    vorher = await _alles(db)
    p = await plan(_req(ids["aid"]), db)
    assert await _alles(db) == vorher
    stunden = (_ts(TW) - (_ts(T0) - 3600)) // 3600              # 31.03. 23:00 … 20.04. 23:00
    assert p.estimated_changes == {
        "kanalzeilen": stunden, "bestand_tage": 2, "stundenzeilen": 48, "tageszeilen": 2,
        "abschluss_monate": 1, "tage_ohne_werte": 20,
    }
    vor = p.operation_preview
    assert [(q["statistic_id"], q["gueltig_ab"], q["zeilen"]) for q in vor["quellen"]] == [
        ("sensor.einsp_alt", "2026-04-01T00:00", stunden)]
    assert vor["letzter_ganzer_tag"] == "2026-04-20" and vor["abschluss_monate"] == ["2026-03"]
    assert vor["tage_ohne_werte"][0] == "2026-04-01" and vor["tage_ohne_werte"][-1] == "2026-04-20"
    assert vor["tage_mit_bestand"] == ["2026-04-21"]
    text_ = " ".join(p.warnings)
    for teil in ("sensor.einsp_alt", "sensor.einsp_neu", "21.04.2026 00:00", "01.04.2026 00:00", "03/2026",
                 "Kein Rückweg", "Wetter, Prognose, Preise"):
        assert teil in text_, teil


async def test_ausfuehrung_leert_feldgenau_beide_schichten(db):
    ids = await _saat(db)
    vorher = await _alles(db)
    p = await plan(_req(ids["aid"]), db)
    r = await execute(p.plan_id, db)
    nachher = await _alles(db)
    stunden = (_ts(TW) - (_ts(T0) - 3600)) // 3600
    assert r.actual_changes["kanalzeilen_geloescht"] == stunden
    assert (r.actual_changes["stundenzeilen_geleert"], r.actual_changes["tageszeilen_geleert"]) == (48, 2)

    k = (await db.execute(select(Kanal).where(Kanal.key == "basis:einspeisung"))).scalar_one()
    kz = {key: z for key, z in nachher["kanal_statistik"].items() if key[0] == k.id}
    assert kz and min(key[1] for key in kz) == _ts(TW)                                    # vor t: nichts
    assert all(z == vorher["kanal_statistik"][key] for key, z in nachher["kanal_statistik"].items())  # ab t: gleich
    assert len(vorher["kanal_statistik"]) - len(nachher["kanal_statistik"]) == stunden    # andere Kanäle: unberührt
    qs = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id)
                           .order_by(KanalQuelle.gueltig_ab))).scalars().all()
    assert [q.statistic_id for q in qs] == ["sensor.einsp_alt", "sensor.einsp_neu"]
    assert qs[0].verworfen_ts is not None and qs[1].verworfen_ts is None

    for pk, z in nachher["tages_energie_profil"].items():
        alt = vorher["tages_energie_profil"][pk]
        d = date.fromisoformat(z["datum"])
        if d in GELEERT:
            assert z["einspeisung_kw"] is None
            assert "einspeisung" not in json.loads(z["spannen"] or "{}")
            assert json.loads(z["source_provenance"])["einspeisung_kw"]["source"] == "verworfen:werkbank"
        else:
            assert z == alt
        assert _md5_ohne(z, {"einspeisung_kw", "spannen", "source_provenance"}) == \
            _md5_ohne(alt, {"einspeisung_kw", "spannen", "source_provenance"})
        if d in GELEERT and json.loads(alt["spannen"] or "null"):
            assert json.loads(z["spannen"]) == {"pv": 2}                                   # nur der Achs-Eintrag
    for pk, z in nachher["tages_zusammenfassung"].items():
        alt = vorher["tages_zusammenfassung"][pk]
        kk_alt, kk_neu = json.loads(alt["komponenten_kwh"]), json.loads(z["komponenten_kwh"])
        if date.fromisoformat(z["datum"]) in GELEERT:
            assert kk_neu == {k_: v for k_, v in kk_alt.items() if k_ != "einspeisung"}
            assert "komponenten_kwh.einspeisung" not in json.loads(z["source_provenance"])
        else:
            assert z == alt
        assert _md5_ohne(z, {"komponenten_kwh", "source_provenance"}) == \
            _md5_ohne(alt, {"komponenten_kwh", "source_provenance"})
    audit = (await db.execute(select(DataProvenanceLog).where(DataProvenanceLog.source == "verworfen:werkbank")
                              )).scalars().all()
    assert len(audit) == 48 + 2 + 2                     # 48 Stundenspalten, 2 Spannen-Einträge, 2 Tageswerte
    assert r.actual_changes["audit_log_count"] == len(audit)


async def test_monate_mit_abschluss_bleiben_unberuehrt(db):
    ids = await _saat(db)
    vorher = await _alles(db)
    await execute((await plan(_req(ids["aid"]), db)).plan_id, db)
    nachher = await _alles(db)
    for tabelle in ("tages_energie_profil", "tages_zusammenfassung"):
        maerz = [pk for pk, z in vorher[tabelle].items() if z["datum"].startswith("2026-03")]
        assert maerz and all(nachher[tabelle][pk] == vorher[tabelle][pk] for pk in maerz)


async def test_zweiter_lauf_aendert_nichts_und_sagt_es(db):
    ids = await _saat(db)
    await execute((await plan(_req(ids["aid"]), db)).plan_id, db)
    stand = await _alles(db)
    p2 = await plan(_req(ids["aid"]), db)
    assert p2.estimated_changes["kanalzeilen"] == 0 and p2.estimated_changes["bestand_tage"] == 0
    assert p2.warnings[0].startswith("Nichts zu verwerfen")
    r2 = await execute(p2.plan_id, db)
    assert (r2.actual_changes["kanalzeilen_geloescht"], r2.actual_changes["felder_geleert"],
            r2.actual_changes["quellen_markiert"]) == (0, 0, 0)
    assert await _alles(db) == stand                     # auch kein zweiter Aktivitätseintrag


async def test_aktivitaet_in_derselben_sitzung(db):
    ids = await _saat(db)
    await execute((await plan(_req(ids["aid"]), db)).plan_id, db)
    log = (await db.execute(select(ActivityLog))).scalars().all()
    assert len(log) == 1 and log[0].kategorie == "repair" and log[0].anlage_id == ids["aid"]
    assert "Einspeisung" in log[0].aktion and log[0].details_json["kanal"] == "basis:einspeisung"


async def test_geraetefeld_leert_nur_den_tageswert_der_leistungspfad_bleibt(db):
    ids = await _saat(db)
    vorher = await _alles(db)
    p = await plan(_req(ids["aid"], f"inv:{ids['pv']}:pv_erzeugung_kwh"), db)
    assert p.operation_preview["bestand_ziele"] == {"spalte": None, "spannen": None,
                                                    "komponenten_kwh": [f"pv_{ids['pv']}"], "pv_aggregat": False}
    assert any("Leistungssensor" in w and "96 Stundenzeilen" in w for w in p.warnings)   # 4 Tage × 24 Stunden
    await execute(p.plan_id, db)
    nachher = await _alles(db)
    assert nachher["tages_energie_profil"] == vorher["tages_energie_profil"]            # H-3 B: Stunde unberührt
    for pk, z in nachher["tages_zusammenfassung"].items():
        if date.fromisoformat(z["datum"]) in GELEERT:
            assert f"pv_{ids['pv']}" not in json.loads(z["komponenten_kwh"])
            assert f"batterie_{ids['sp']}" in json.loads(z["komponenten_kwh"])
        else:
            assert z == vorher["tages_zusammenfassung"][pk]


async def test_eintrag_mit_zweitem_feld_wird_genannt(db):
    ids = await _saat(db)
    p = await plan(_req(ids["aid"], f"inv:{ids['sp']}:ladung_kwh"), db)
    assert p.operation_preview["bestand_ziele"]["komponenten_kwh"] == [f"batterie_{ids['sp']}"]
    assert any(f"inv:{ids['sp']}:entladung_kwh" in w and "als Ganzes" in w for w in p.warnings)


@pytest.mark.parametrize("params, fehler", [
    ({"zeitpunkt": "2026-04-21T00:00"}, "params.kanal"),
    ({"kanal": "basis:einspeisung"}, "params.zeitpunkt"),
    ({"kanal": "basis:einspeisung", "zeitpunkt": "21.04.2026"}, "kein Datum"),
    ({"kanal": "basis:einspeisung", "zeitpunkt": "2026-04-21T00:30"}, "vollen Stunde"),
    ({"kanal": "basis:einspeisung", "zeitpunkt": "2026-04-21T01:00"}, "nach dem Beginn des jüngsten"),
    ({"kanal": "basis:einspeisung", "zeitpunkt": "2026-04-01T00:00"}, "nicht nach dem Beginn der ersten"),
    ({"kanal": "basis:netzbezug", "zeitpunkt": "2026-04-10T00:00"}, "nur eine Quelle"),
    ({"kanal": "basis:strompreis", "zeitpunkt": "2026-04-21T00:00"}, "kein Zähler"),
    ({"kanal": "modus:inv:1:heizen", "zeitpunkt": "2026-04-21T00:00"}, "kein zugeordnetes Feld"),
])
async def test_eingaben_werden_geprueft(db, params, fehler):
    from backend.api.routes.repair import create_plan

    ids = await _saat(db)
    with pytest.raises(HTTPException) as e:
        await create_plan(RepairOperationRequest(anlage_id=ids["aid"], operation=OP, params=params), db=db)
    assert e.value.status_code == 400 and fehler in e.value.detail


async def test_unbekannter_kanal_ist_404(db):
    from backend.api.routes.repair import create_plan

    ids = await _saat(db)
    with pytest.raises(HTTPException) as e:
        await create_plan(_req(ids["aid"], "basis:pv_gesamt"), db=db)
    assert e.value.status_code == 404


async def test_auswahl_nennt_nur_felder_mit_sensortausch_und_die_vorbelegung(db):
    from backend.api.routes.repair import kanal_auswahl

    ids = await _saat(db)
    antwort = await kanal_auswahl(anlage_id=ids["aid"], db=db)
    assert [(k["key"], k["vorbelegung"]) for k in antwort.kanaele] == [
        ("basis:einspeisung", "2026-04-21T00:00"),
        (f"inv:{ids['pv']}:pv_erzeugung_kwh", "2026-04-21T00:00"),
        (f"inv:{ids['sp']}:ladung_kwh", "2026-04-21T00:00"),
    ]
    einsp = antwort.kanaele[0]
    assert einsp["label"] == "Anlage · Einspeisung" and einsp["typ"] is None
    assert [q["statistic_id"] for q in einsp["quellen"]] == ["sensor.einsp_alt", "sensor.einsp_neu"]
    assert antwort.kanaele[1]["typ"] == "pv-module" and antwort.kanaele[1]["label"].startswith("Süddach · ")


def test_pv_gesamt_leert_die_aus_dem_anlagenwert_zerlegten_eintraege_nicht_die_geteilte_spalte():
    """``pv_kw`` trägt alle PV-Zähler der Stunde (#406 wählt je Tag) — bleibt; die zerlegten Tageswerte gehen (H-5)."""
    ziele = vq._basis_ziele("pv_gesamt")
    assert (ziele.spalte, ziele.spannen_achse, ziele.pv_aggregat) == (None, None, True)
    assert (vq._basis_ziele("einspeisung").spalte, vq._basis_ziele("einspeisung").spannen_achse) == (
        "einspeisung_kw", "einspeisung")
    assert vq._basis_ziele("netzbezug").spalte == "netzbezug_kw"
    tz = TagesZusammenfassung(komponenten_kwh={"pv_6": 3.0, "pv_7": 4.0, "bkw_9": 1.0},
                              source_provenance={"komponenten_kwh.pv_6": {"abgeleitet": "kwp_anteil"},
                                                 "komponenten_kwh.pv_7": {"source": "x"}})
    assert vq.tz_keys_der_zeile(tz, ziele) == ["pv_6"]


def test_migration_verworfen_ts_legt_die_spalte_einmal_an(tmp_path):
    from backend.core.database import _migrate_kanal_quelle_verworfen_ts

    engine = create_engine(f"sqlite:///{tmp_path}/m.db")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE kanal_quelle (kanal_id INTEGER, gueltig_ab INTEGER, familie VARCHAR(12), "
                          "statistic_id VARCHAR(255), offset FLOAT, PRIMARY KEY (kanal_id, gueltig_ab))"))
        conn.execute(text("INSERT INTO kanal_quelle VALUES (1, 100, 'spiegel', 'sensor.x', 0.0)"))
        _migrate_kanal_quelle_verworfen_ts(conn)
        _migrate_kanal_quelle_verworfen_ts(conn)                   # idempotent
        spalten = [r[1] for r in conn.execute(text("PRAGMA table_info(kanal_quelle)")).all()]
        zeile = conn.execute(text("SELECT verworfen_ts FROM kanal_quelle")).all()
    engine.dispose()
    assert spalten.count("verworfen_ts") == 1 and zeile == [(None,)]


def test_migration_ohne_tabelle_tut_nichts(tmp_path):
    from backend.core.database import _migrate_kanal_quelle_verworfen_ts

    engine = create_engine(f"sqlite:///{tmp_path}/leer.db")
    with engine.begin() as conn:
        _migrate_kanal_quelle_verworfen_ts(conn)
        assert conn.execute(text("SELECT name FROM sqlite_master WHERE name = 'kanal_quelle'")).all() == []
    engine.dispose()


def test_tagesgrenzen_aus_dem_zeitpunkt():
    """Der Tag, in dem t liegt, ist nicht ganz vor t; der Tag davor endet spätestens bei t (Tagesfenster 23:00)."""
    from backend.services.kanal.abgeleitet import tag_der_stunde
    from backend.services.kanal.fenster import tagesfenster

    for t in (TW, TW + timedelta(hours=14), TW - timedelta(hours=1)):
        tag_t = tag_der_stunde(_ts(t))
        assert tagesfenster(tag_t)[0] <= _ts(t) < tagesfenster(tag_t)[1]
        assert tagesfenster(tag_t - timedelta(days=1))[1] <= _ts(t)


@pytest.mark.parametrize("zeitpunkt", ["2026-04-21T00:00", "2026-04-20T23:00"])
async def test_tage_der_vorschau_sind_danach_bestandstage_der_lese_schicht(db, zeitpunkt):
    """Was die Vorschau «danach ohne Wert» bzw. «verliert die Kanalzeilen» nennt, ist danach für die Quellenwahl der
    Bilanz-Gruppe (``bilanz_quellenwahl_tag``, dieselbe Lese-Schicht wie die Sichten) ein Bestandstag; der Tag nach dem
    Tausch bleibt Kanal-Tag. Mit ``t`` = 23:00 hat der 21.04. keine eigene Zeile vor ``t`` — er verliert nur den Anker
    (die Zeile 22:00 des Vortags) und muss trotzdem in der Vorschau stehen."""
    from backend.services.kanal.bilanz_quellenwahl import bilanz_quellenwahl_tag

    ids = await _saat(db)
    jetzt = _ts(ENDE)

    async def wahl(tag: date) -> str:
        return (await bilanz_quellenwahl_tag(db, ids["aid"], tag, jetzt=jetzt)).quelle

    p = await plan(_req(ids["aid"], zeitpunkt=zeitpunkt), db)
    betroffen = [date.fromisoformat(d) for d in p.operation_preview["tage_ohne_werte"] +
                 p.operation_preview["tage_mit_bestand"]]
    assert date(2026, 4, 21) in betroffen and date(2026, 4, 22) not in betroffen
    vorher = {d: await wahl(d) for d in betroffen}
    # Vorher Kanal-Tage — bis auf den 01.04.: der Seed beginnt mit dessen erster Stunde, der Anker davor fehlt.
    assert vorher.pop(date(2026, 4, 1)) == "bestand" and set(vorher.values()) == {"kanal"}
    assert await wahl(date(2026, 4, 22)) == "kanal"
    await execute(p.plan_id, db)
    gruende = {d: await bilanz_quellenwahl_tag(db, ids["aid"], d, jetzt=jetzt) for d in betroffen}
    assert {g.quelle for g in gruende.values()} == {"bestand"}
    assert all("basis:einspeisung" in g.gruende for g in gruende.values())
    assert all(set(g.gruende) == {"basis:einspeisung"} for d, g in gruende.items() if d != date(2026, 4, 1))
    assert await wahl(date(2026, 4, 22)) == "kanal"
