"""Proben „Bestand unberührt" (HA-Bauform E1): der neue Schreiber ändert keine Zeile des Bestands.

* **Bitgleich:** ``sensor_snapshots``, Stunden- und Tageszeilen nach einem Stundenlauf (und der
  Tagesaggregation darüber) sind bitgleich zu einem Lauf OHNE den neuen Teil — auf dem
  Matrix-Datenstand (``achsen_matrix``: HA-Statistik im echten Schema, Zustands-Verlauf), HA-Weg und
  MQTT-Weg. ``created_at``/``updated_at`` bleiben außen vor (sie tragen die Uhr des Laufs).
* **Isolation:** scheitert der neue Teil mitten im Schreiben, steht der Bestand trotzdem vollständig
  da, der neue Teil ist ganz zurückgerollt (SAVEPOINT) und der Fehler als Aktivität in DERSELBEN
  Sitzung vermerkt (N-532).
* **Löschen:** eine gelöschte Anlage räumt ihre Kanäle wie ihre Snapshots (``ON DELETE CASCADE``);
  eine gelöschte Investition ebenso (seit N-668, 10.10.2026 — bis dahin räumte sie keines von beiden, und die
  nächste Investition mit derselben ID erbte beide; Probe dazu: ``test_n668_investition_loeschen_messreihen.py``).
* **E2:** dasselbe Bitgleich mit Nachfüllen Spiegel und Konsistenzlauf (samt einer Korrektur in HA)
  zwischen Stundenlauf und Tagesaggregation — beide schreiben nur Kanal-Tabellen.
* **S3, E-S3-4:** dasselbe Bitgleich mit dem Nachfüllen der Eigenen Summe aus ``sensor_snapshots`` (MQTT-Weg: der
  Kanal-Schreiber beginnt erst in der Mitte, das Nachfüllen setzt die Stunden davor an) — es liest die Stundenstände
  und schreibt nur Kanal-Tabellen.
* **S5b (HA-Bauform E-S5-3, Bauplan §10h 7):** macht das Nachfüllen einen Tag zum **Kanal-Tag** (Bilanz-Gruppe mit Wahl
  ``kanal``), schreibt ``aggregate_day`` dort keine gefalteten Mengen mehr (S5-R2, ``mengen_weiche``) — das ist an
  Kanal-Tagen das eigene Soll: die Mengen-Spalten der Stundenzeilen und Überschuss/Defizit der Tageszeile sind leer, die
  Herkunft ist ``TZ_QUELLE_KANAL``. **Bitgleich bleiben** ``sensor_snapshots``, jeder Bestandstag und an Kanal-Tagen
  die Bahnen (SoC, Preise, Wetter, Leistungspfad, Zählwerke, Betriebsart) und die Kennzahlen, die nicht aus Mengen
  abgeleitet sind (Peaks, Vollzyklen, Wetter, Börse).

Schwesterdateien: test_kanal_spiegel.py, test_kanal_eigene_summe.py, test_kanal_mitschrift_betriebsart.py, test_kanal_feld_deckung.py; Datenstand: test_achsen_matrix.py.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.orm.attributes import flag_modified

from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
from backend.services.snapshot.writer import snapshot_anlage
from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

START = datetime(2026, 6, 10, 0)
STUNDEN = 30
TAGE = (START.date(), (START + timedelta(days=1)).date())
_OHNE_SPALTEN = {"created_at", "updated_at"}
_BESTAND = ("sensor_snapshots", "tages_energie_profil", "tages_zusammenfassung")


def _ohne_uhr(wert):
    """Provenance-JSON trägt je Feld ``"at"`` = Uhr des Laufs — der einzige erlaubte Unterschied."""
    if isinstance(wert, str) and wert.startswith("{") and '"at"' in wert:
        def _weg(x):
            if isinstance(x, dict):
                return {k: _weg(v) for k, v in x.items() if k != "at"}
            if isinstance(x, list):
                return [_weg(v) for v in x]
            return x
        return json.dumps(_weg(json.loads(wert)), sort_keys=True)
    return wert


async def _dump(db, tabelle: str) -> list[tuple]:
    spalten = [r[1] for r in (await db.execute(text(f"PRAGMA table_info({tabelle})"))).all()
               if r[1] not in _OHNE_SPALTEN]
    rows = (await db.execute(text(f"SELECT {', '.join(spalten)} FROM {tabelle} ORDER BY 1"))).all()
    return [tuple(_ohne_uhr(w) for w in r) for r in rows]


def _mqtt_zeilen(form, aid: int, ids: dict) -> list[dict]:
    """5-Minuten-Rohstände für Netz/Einspeisung und alle Gerätezähler der Form (Standalone)."""
    reihen = {"netzbezug_kwh": form.netz, "einspeisung_kwh": form.einsp}
    for g in form.geraete:
        for feld, fn in g.felder.items():
            reihen[f"inv/{ids[g.name]}/{feld}"] = fn
    zeilen = []
    for key, fn in reihen.items():
        stand, t = 1000.0, START - timedelta(hours=1)
        while t < START + timedelta(hours=STUNDEN + 1):
            zeilen.append({"anlage_id": aid, "energy_key": key, "timestamp": t, "value_kwh": round(stand, 4)})
            stand += fn(t) / 12.0
            t += timedelta(minutes=5)
    return zeilen


async def _lauf(form, *, ha: bool, mit_kanal: bool, mitschrift: bool = True, stoerung=None,
                nachfuellen: bool = False, ha_korrektur: bool = False, kanal_ab: int = 1,
                es_nachfuellen: bool = False) -> dict:
    verz = tempfile.mkdtemp(prefix="eedc-kanal-bestand-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            svc = am.seed_ha(form) if ha else mx._ha_aus()
            aid, ids = await am.seed_anlage(db, form)
            anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
            if not ha:
                anlage.sensor_mapping = {"basis": {}, "investitionen": {}}
                flag_modified(anlage, "sensor_mapping")
                await db.execute(insert(MqttEnergySnapshot), _mqtt_zeilen(form, aid, ids))
                await db.commit()
            ohne_mitschrift = patch(
                "backend.services.kanal.schreiber.schreibe_betriebsart_mitschrift_sicher",
                new=_kein_schreiben,
            )
            with am.umgebung(form, svc), (stoerung or _nichts)():
                if not mitschrift:
                    ohne_mitschrift.start()
                try:
                    for h in range(1, STUNDEN + 1):
                        zp = START + timedelta(hours=h)
                        await snapshot_anlage(db, anlage, zeitpunkt=zp)
                        if mit_kanal and h >= kanal_ab:
                            await schreibe_kanaele_im_stundenlauf(db, anlage, zp)
                        await db.commit()
                    if nachfuellen or ha_korrektur:
                        out_e2 = await _e2_laeufe(engine, svc, aid, kanal=nachfuellen)
                    if es_nachfuellen:
                        out_es = await _es_nachfuellen(engine, svc, aid)
                    await mx.aggregiere_tage(db, form.pvform, aid, TAGE)
                finally:
                    if not mitschrift:
                        ohne_mitschrift.stop()
            out = {t: await _dump(db, t) for t in _BESTAND}
            out["zeilen"] = {t: await _zeilen(db, t) for t in _BESTAND[1:]}
            out["tz_zeilen"] = out["zeilen"]["tages_zusammenfassung"]
            out["kanal"] = await _dump(db, "kanal")
            out["kanal_statistik"] = await _dump(db, "kanal_statistik")
            out["aktivitaet"] = [(a.aktion, a.erfolg, a.details) for a in
                                 (await db.execute(select(ActivityLog))).scalars().all()]
            if nachfuellen or ha_korrektur:
                out["e2"] = out_e2
            if es_nachfuellen:
                out["es"] = out_es
            return out
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def _kein_schreiben(*_a, **_k):
    return 0


async def _e2_laeufe(engine, svc, aid: int, *, kanal: bool) -> dict:
    """E2: Nachfüllen Spiegel, dann eine Korrektur in HA (``sum`` ab Stunde 20 um −480) und der
    Konsistenzlauf — über eigene Sitzungen auf derselben Datei, wie im Betrieb. Die Korrektur in HA kommt
    in BEIDEN Läufen (sonst läse der Tageslauf verschiedene HA-Daten); Nachfüllen und Konsistenzlauf nur
    mit ``kanal``."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from backend.services.kanal.konsistenz import konsistenz_anlage
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel

    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    nf = await nachfuellen_spiegel(sitzungen, aid, jetzt=START + timedelta(hours=STUNDEN), ha_svc=svc) if kanal else None
    ab = int((START + timedelta(hours=20)).timestamp())
    with svc._engine.begin() as conn:
        conn.execute(text("UPDATE statistics SET sum = sum - 480 WHERE metadata_id = 1 AND start_ts >= :t"), {"t": ab})
    if not kanal:
        return {}
    ko = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    return {"nachgefuellt": nf.zeilen, "fehler": nf.fehler + ko.fehler, "korrigiert": len(ko.korrigiert)}


async def _es_nachfuellen(engine, svc, aid: int) -> dict:
    """S3, E-S3-4: der Einstieg des Produkts (``nachfuellen_anlage``: Spiegel + Eigene Summe) über eigene Sitzungen."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from backend.services.kanal.nachfuellen import nachfuellen_anlage

    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=START + timedelta(hours=STUNDEN, minutes=5), ha_svc=svc)
    return {"zeilen": erg.eigene_summe.zeilen, "kanaele": erg.eigene_summe.gefuellt, "fehler": erg.eigene_summe.fehler}


class _nichts:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("fid,ha", [("M04", True), ("M05", True), ("M06", True), ("M02", False), ("M10", False)])
async def test_bestand_bitgleich_mit_und_ohne_kanal_schreiber(fid, ha):
    form = am.FORMEN[fid]
    mit = await _lauf(form, ha=ha, mit_kanal=True)
    ohne = await _lauf(form, ha=ha, mit_kanal=False, mitschrift=False)
    for t in _BESTAND:
        assert mit[t] == ohne[t], f"{fid}: {t} weicht ab"
        assert mit[t], f"{fid}: {t} ist leer — die Probe hätte nichts verglichen"
    assert mit["kanal_statistik"], f"{fid}: der neue Teil hat nichts geschrieben"
    assert not ohne["kanal_statistik"]
    assert not [a for a in mit["aktivitaet"] if a[0] == "Kanalstatistik nicht geschrieben"]


async def test_m05_betriebsart_landet_als_mitschrift_im_kanal():
    mit = await _lauf(am.FORMEN["M05"], ha=True, mit_kanal=True)
    keys = {r[2] for r in mit["kanal"]}
    assert any(k.startswith("modus:inv:") and k.endswith(":heizen") for k in keys), keys
    assert any(k.startswith("modus:inv:") and k.endswith(":warmwasser") for k in keys), keys


class _SpiegelDannFehler:
    """Der Spiegel schreibt seine Zeilen, dann scheitert die eigene Summe — mitten im neuen Teil."""

    def __enter__(self):
        async def _kaputt(*_a, **_k):
            raise RuntimeError("Sprengsatz im neuen Teil")
        self._p = patch("backend.services.kanal.schreiber.schreibe_eigene_summe", new=_kaputt)
        self._p.start()
        return self

    def __exit__(self, *a):
        self._p.stop()
        return False


async def test_fehler_im_neuen_teil_beruehrt_den_bestand_nicht():
    form = am.FORMEN["M04"]
    gestoert = await _lauf(form, ha=True, mit_kanal=True, stoerung=_SpiegelDannFehler)
    ohne = await _lauf(form, ha=True, mit_kanal=False, mitschrift=False)
    for t in _BESTAND:
        assert gestoert[t] == ohne[t], t
    assert gestoert["kanal_statistik"] == []          # Spiegel-Zeilen mit zurückgerollt
    fehler = [a for a in gestoert["aktivitaet"] if a[0] == "Kanalstatistik nicht geschrieben"]
    assert len(fehler) == STUNDEN and all(a[1] is False and "Sprengsatz" in a[2] for a in fehler)


async def test_fehler_in_der_mitschrift_beruehrt_die_tagesaggregation_nicht():
    form = am.FORMEN["M05"]

    class _MitschriftKaputt(_nichts):
        def __enter__(self):
            async def _kaputt(db, anlage, *_a, **_k):
                # erst schreiben, dann scheitern — sonst bewiese ein leerer Kanal nichts über den SAVEPOINT
                db.add(Kanal(anlage_id=anlage.id, key="modus:inv:0:heizen", art="mean", einheit="Anteil"))
                await db.flush()
                raise RuntimeError("Sprengsatz Mitschrift")
            self._p = patch("backend.services.kanal.schreiber.schreibe_betriebsart_mitschrift", new=_kaputt)
            self._p.start()
            return self

        def __exit__(self, *a):
            self._p.stop()
            return False

    gestoert = await _lauf(form, ha=True, mit_kanal=False, stoerung=_MitschriftKaputt)
    ohne = await _lauf(form, ha=True, mit_kanal=False, mitschrift=False)
    for t in _BESTAND:
        assert gestoert[t] == ohne[t], t
    assert gestoert["kanal"] == [] and gestoert["kanal_statistik"] == []
    assert [a[1] for a in gestoert["aktivitaet"] if a[0] == "Kanalstatistik nicht geschrieben"] == [False, False]


# ── Löschen ────────────────────────────────────────────────────────────────


async def _mit_kanal_und_snapshot(db):
    from backend.tests import factories

    await db.execute(text("PRAGMA foreign_keys=ON"))
    a = await factories.anlage(db)
    inv = await factories.investition(db, anlage_id=a.id, typ="speicher")
    k = Kanal(anlage_id=a.id, key=f"inv:{inv.id}:ladung_kwh", art="sum", einheit="kWh")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=0, familie="spiegel", statistic_id="sensor.x", offset=0.0))
    db.add(KanalStatistik(kanal_id=k.id, start_ts=0, sum=1.0, state=1.0, familie="spiegel"))
    db.add(SensorSnapshot(anlage_id=a.id, sensor_key=f"inv:{inv.id}:ladung_kwh", zeitpunkt=START,
                          wert_kwh=1.0, quelle="ha_statistics"))
    await db.commit()
    return a, inv


async def _anzahl(db) -> tuple[int, int, int, int]:
    return tuple([
        (await db.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar_one()
        for t in ("kanal", "kanal_quelle", "kanal_statistik", "sensor_snapshots")
    ])


async def test_anlage_loeschen_raeumt_kanaele_wie_snapshots(db):
    from backend.api.routes.anlagen import delete_anlage

    a, _ = await _mit_kanal_und_snapshot(db)
    assert await _anzahl(db) == (1, 1, 1, 1)
    await delete_anlage(a.id, db)
    await db.commit()
    assert await _anzahl(db) == (0, 0, 0, 0)


async def test_investition_loeschen_raeumt_kanal_wie_snapshot(db):
    """Der Kanal folgt dem Snapshot („gleiches Verhalten", Auftrag E1) — seit N-668 (10.10.2026) räumt
    ``delete_investition`` beide. Bis dahin stand hier ``(1, 1, 1, 1)``: die Probe hielt das damalige Verhalten fest,
    das der Fund als Defekt benennt (eine neue Investition mit derselben ID erbte Snapshots und Kanäle). Die Substanz —
    Kanal und Snapshot verhalten sich beim Löschen gleich — bleibt."""
    from backend.api.routes.investitionen.crud import delete_investition

    _, inv = await _mit_kanal_und_snapshot(db)
    await delete_investition(inv.id, db)
    await db.commit()
    assert await _anzahl(db) == (0, 0, 0, 0)


#: S5b: die Spalten, die an einem Kanal-Tag aus den Kanälen kommen bzw. aus ihnen gerechnet sind (Mengen, Mengen-
#: Ableitungen, Herkunft) — an Kanal-Tagen nicht Teil des Bitgleich; die Mengen-Spalten dort sind ``KANAL_LEER``.
_KANAL_SPALTEN = {
    "tages_energie_profil": {"pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "waermepumpe_kw",
                             "wallbox_kw", "ueberschuss_kw", "defizit_kw", "spannen", "source_provenance"},
    "tages_zusammenfassung": {"ueberschuss_kwh", "defizit_kwh", "komponenten_kwh", "verworfen", "nachtrag",
                              "performance_ratio", "einspeisung_neg_preis_kwh", "emob_ladung_pv_abgeleitet_kwh",
                              "emob_ladung_netz_abgeleitet_kwh", "emob_ladung_speicher_abgeleitet_kwh",
                              "source_provenance"},
}
#: S5b-Soll an einem Kanal-Tag (die Bilanz-Gruppe hat dort immer Wahl ``kanal``).
_KANAL_LEER = {
    "tages_energie_profil": ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "ueberschuss_kw",
                             "defizit_kw"),
    "tages_zusammenfassung": ("ueberschuss_kwh", "defizit_kwh"),
}


async def _zeilen(db, tabelle: str) -> list[dict]:
    spalten = [r[1] for r in (await db.execute(text(f"PRAGMA table_info({tabelle})"))).all()
               if r[1] not in _OHNE_SPALTEN]
    rows = (await db.execute(text(f"SELECT {', '.join(spalten)} FROM {tabelle} ORDER BY 1"))).all()
    return [{s: _ohne_uhr(w) for s, w in zip(spalten, r)} for r in rows]


@pytest.mark.parametrize("fid", ["M04", "M05", "M06"])
async def test_bestand_bitgleich_mit_nachfuellen_und_konsistenzlauf(fid):
    """E2 (Auftrag „Bestand bitgleich, um das Nachfüllen erweitert"): Nachfüllen aus HA und ein
    Konsistenzlauf mit Korrektur ändern keine Zeile des Bestands. S5b (E-S5-3): das Nachfüllen macht die Tage zu
    Kanal-Tagen — dort sind die Mengen leer (eigenes Soll), die Bahnen bitgleich (Modul-Docstring)."""
    from backend.services.snapshot.boundary_range import TZ_QUELLE_KANAL

    form = am.FORMEN[fid]
    mit = await _lauf(form, ha=True, mit_kanal=True, nachfuellen=True)
    ohne = await _lauf(form, ha=True, mit_kanal=False, mitschrift=False, ha_korrektur=True)
    assert mit["sensor_snapshots"] == ohne["sensor_snapshots"], f"{fid}: sensor_snapshots weicht ab"
    kanal_tage = {z["datum"] for z in mit["tz_zeilen"] if TZ_QUELLE_KANAL in (z["source_provenance"] or "")}
    assert kanal_tage, f"{fid}: kein Kanal-Tag — die S5b-Probe hätte nichts geprüft"
    for t in ("tages_energie_profil", "tages_zusammenfassung"):
        a, b = mit["zeilen"][t], ohne["zeilen"][t]
        assert len(a) == len(b) and a, f"{fid}: {t}"
        for za, zb in zip(a, b):
            if za["datum"] not in kanal_tage:
                assert za == zb, f"{fid}: {t} Bestandstag {za['datum']} weicht ab"
                continue
            weg = _KANAL_SPALTEN[t]
            assert {k: v for k, v in za.items() if k not in weg} == {k: v for k, v in zb.items() if k not in weg}, \
                f"{fid}: {t} Bahnen am Kanal-Tag {za['datum']} weichen ab"
            assert all(za[s] is None for s in _KANAL_LEER[t]), f"{fid}: {t} Kanal-Tag {za['datum']} trägt Mengen"
    assert mit["e2"]["nachgefuellt"] > 0 and mit["e2"]["korrigiert"] >= 1 and mit["e2"]["fehler"] == 0, mit["e2"]


@pytest.mark.parametrize("fid", ["M02", "M10"])
async def test_bestand_bitgleich_mit_nachfuellen_der_eigenen_summe(fid):
    """S3, E-S3-4 (Auftrag Punkt 7): das Nachfüllen der Eigenen Summe aus ``sensor_snapshots`` ändert keine Zeile des
    Bestands — ``sensor_snapshots`` (es liest sie nur), Stunden- und Tageszeilen. MQTT-Weg; der Kanal-Schreiber beginnt
    in Stunde 15, das Nachfüllen setzt die 14 Stunden davor an."""
    form = am.FORMEN[fid]
    mit = await _lauf(form, ha=False, mit_kanal=True, kanal_ab=15, es_nachfuellen=True)
    ohne = await _lauf(form, ha=False, mit_kanal=False, mitschrift=False)
    for t in _BESTAND:
        assert mit[t] == ohne[t], f"{fid}: {t} weicht ab"
        assert mit[t], f"{fid}: {t} ist leer — die Probe hätte nichts verglichen"
    assert mit["es"]["fehler"] == 0 and mit["es"]["kanaele"] > 0, mit["es"]
    assert mit["es"]["zeilen"] == 14 * mit["es"]["kanaele"], mit["es"]
