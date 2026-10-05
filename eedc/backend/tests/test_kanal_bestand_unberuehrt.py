"""Proben „Bestand unberührt" (HA-Bauform E1): der neue Schreiber ändert keine Zeile des Bestands.

* **Bitgleich:** ``sensor_snapshots``, Stunden- und Tageszeilen nach einem Stundenlauf (und der
  Tagesaggregation darüber) sind bitgleich zu einem Lauf OHNE den neuen Teil — auf dem
  Matrix-Datenstand (``achsen_matrix``: HA-Statistik im echten Schema, Zustands-Verlauf), HA-Weg und
  MQTT-Weg. ``created_at``/``updated_at`` bleiben außen vor (sie tragen die Uhr des Laufs).
* **Isolation:** scheitert der neue Teil mitten im Schreiben, steht der Bestand trotzdem vollständig
  da, der neue Teil ist ganz zurückgerollt (SAVEPOINT) und der Fehler als Aktivität in DERSELBEN
  Sitzung vermerkt (N-532).
* **Löschen:** eine gelöschte Anlage räumt ihre Kanäle wie ihre Snapshots (``ON DELETE CASCADE``);
  eine gelöschte Investition räumt weder das eine noch das andere (heutiges Verhalten, gemessen).
* **E2:** dasselbe Bitgleich mit Nachfüllen Spiegel und Konsistenzlauf (samt einer Korrektur in HA)
  zwischen Stundenlauf und Tagesaggregation — beide schreiben nur Kanal-Tabellen.

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
                nachfuellen: bool = False, ha_korrektur: bool = False) -> dict:
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
                        if mit_kanal:
                            await schreibe_kanaele_im_stundenlauf(db, anlage, zp)
                        await db.commit()
                    if nachfuellen or ha_korrektur:
                        out_e2 = await _e2_laeufe(engine, svc, aid, kanal=nachfuellen)
                    await mx.aggregiere_tage(db, form.pvform, aid, TAGE)
                finally:
                    if not mitschrift:
                        ohne_mitschrift.stop()
            out = {t: await _dump(db, t) for t in _BESTAND}
            out["kanal"] = await _dump(db, "kanal")
            out["kanal_statistik"] = await _dump(db, "kanal_statistik")
            out["aktivitaet"] = [(a.aktion, a.erfolg, a.details) for a in
                                 (await db.execute(select(ActivityLog))).scalars().all()]
            if nachfuellen or ha_korrektur:
                out["e2"] = out_e2
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


async def test_investition_loeschen_raeumt_weder_kanal_noch_snapshot(db):
    """Heutiges Verhalten (``delete_investition`` löscht keine ``sensor_snapshots``-Zeile) —
    der Kanal folgt ihm, wie der Auftrag es verlangt („gleiches Verhalten")."""
    from backend.api.routes.investitionen.crud import delete_investition

    _, inv = await _mit_kanal_und_snapshot(db)
    await delete_investition(inv.id, db)
    await db.commit()
    assert await _anzahl(db) == (1, 1, 1, 1)


@pytest.mark.parametrize("fid", ["M04", "M05", "M06"])
async def test_bestand_bitgleich_mit_nachfuellen_und_konsistenzlauf(fid):
    """E2 (Auftrag „Bestand bitgleich, um das Nachfüllen erweitert"): Nachfüllen aus HA und ein
    Konsistenzlauf mit Korrektur ändern keine Zeile des Bestands."""
    form = am.FORMEN[fid]
    mit = await _lauf(form, ha=True, mit_kanal=True, nachfuellen=True)
    ohne = await _lauf(form, ha=True, mit_kanal=False, mitschrift=False, ha_korrektur=True)
    for t in _BESTAND:
        assert mit[t] == ohne[t], f"{fid}: {t} weicht ab"
        assert mit[t], f"{fid}: {t} ist leer — die Probe hätte nichts verglichen"
    assert mit["e2"]["nachgefuellt"] > 0 and mit["e2"]["korrigiert"] >= 1 and mit["e2"]["fehler"] == 0, mit["e2"]
