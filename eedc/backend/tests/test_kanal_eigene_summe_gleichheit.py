"""Gleichheit der nachgefüllten Eigenen Summe (HA-Bauform S3, Etappe E-S3-4, Auftrag Punkt 5).

Auf dem Matrix-Datenstand ``MQTT`` (``kanal_bilanz_gleichheit.datenstand``: reine MQTT-Anlage, Rohstände in
``mqtt_energy_snapshots``, Stundenstände in ``sensor_snapshots`` wie ``snapshot_anlage`` sie schreibt) entsteht die
Eigene Summe hier NICHT aus dem Stundenlauf, sondern aus dem Nachfüllen über die Stundenstände
(``eigene_summe_aus="sensor_snapshots"``). Je Form beider Abnahme-Matrizen (``MATRIX_FORMEN``):

* **Stand für Stand gleich der Eigenen Summe aus den Rohständen** (derselbe Zeitraum, dieselbe Datei; Toleranz 1e-6
  wie ``kanal_bilanz_gleichheit.TOL``): dieselben Kanäle, je Zeile derselbe Stand und derselbe Zuwachs. Einzige
  Abweichung, benannt: das Nachfüllen hat je Kanal **eine Zeile mehr am Anfang** — der erste Stundenstand (31.05.
  18:00) ist der Stand am Ende der Stunde 17:00 und wird deren Nullpunkt; der Stundenlauf beginnt mit dem ersten
  Rohstand eine Stunde später.
* **Kanal ↔ Bestand je Tag mit denselben Klassen wie der Datenstand ``MQTT``:** die Gleichheitsprobe der Bilanz-Gruppe
  (E4a: Fassung (a) == Bestand ohne Ausnahme, Weg-2-Klassen ``W2_KLASSEN``, Quellenwahl) und die des Kanal-Stundentags
  (E-S3-1: Klassen ``KLASSEN``, ``unbenannt`` 0) treffen die eingefrorenen Zahlen des Datenstands ``MQTT``.

Keine Probe liest die Uhr. Schwesterdateien: test_kanal_eigene_summe_nachfuellen.py, test_kanal_bilanz_gleichheit.py,
test_kanal_stunden_gleichheit.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from backend.models.anlage import Anlage
from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalNachfuellung, KanalQuelle, KanalStatistik
from backend.services.kanal.quellenwahl import QUELLE_KANAL
from backend.services.snapshot.keys import _sensor_key_to_mqtt_key
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import kanal_stunden_gleichheit as ks
from backend.tests import pv_achse_matrix as mx
from backend.tests.test_kanal_bilanz_gleichheit import W2_KLASSEN, ZAEHLER_OHNE_NACHTZEILEN
from backend.tests.test_kanal_stunden_gleichheit import KLASSEN

_FORMEN = [("achsen", f) for f in am.MATRIX_FORMEN] + [("pv", f) for f in mx.MATRIX_FORMEN]
#: Die Formen, für die die Bilanz-Gleichheit (E4a) Klassen eingefroren hat (``test_kanal_bilanz_gleichheit._FORMEN``).
_BILANZ_FORMEN = {("achsen", f) for f in am.FORMEN} | {("pv", f) for f in mx.FORMEN}
_ERSTE_STUNDE = int(mx.REIHE_VON.timestamp()) - 3600


async def _eigene_summe(db, aid: int) -> dict[str, list[tuple[int, float, float]]]:
    """``{Kanal-Key: [(start_ts, Kanalwert, Stand)]}`` der Eigenen-Summe-Kanäle (Quelle Mitschrift mit MQTT-Kennung)."""
    out = {}
    for k in (await db.execute(select(Kanal).where(Kanal.anlage_id == aid))).scalars().all():
        quellen = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()
        if not quellen or any(q.familie != FAMILIE_MITSCHRIFT or q.statistic_id != _sensor_key_to_mqtt_key(k.key)
                              for q in quellen):
            continue
        assert len(quellen) == 1, (k.key, [(q.gueltig_ab, q.statistic_id) for q in quellen])
        zeilen = (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id)
                                   .order_by(KanalStatistik.start_ts))).scalars().all()
        assert zeilen[0].start_ts == quellen[0].gueltig_ab, k.key
        wert = (lambda z: z.state) if k.art == "stand" else (lambda z, o=quellen[0].offset: z.sum + o)
        out[k.key] = [(z.start_ts, wert(z), z.state) for z in zeilen]
    return out


async def _neu_aus_rohstaenden(ds) -> dict[str, list[tuple[int, float, float]]]:
    """Die Eigene-Summe-Kanäle verwerfen und den Stundenlauf über die Rohstände laufen lassen (dieselbe Datei)."""
    ids = list((await ds.db.execute(select(Kanal.id).where(
        Kanal.anlage_id == ds.aid, Kanal.key.in_(list(await _eigene_summe(ds.db, ds.aid)))))).scalars().all())
    for tabelle in (KanalStatistik, KanalQuelle, KanalNachfuellung):
        await ds.db.execute(delete(tabelle).where(tabelle.kanal_id.in_(ids)))
    await ds.db.execute(delete(Kanal).where(Kanal.id.in_(ids)))
    await ds.db.commit()
    anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
    await kg._eigene_summe_tageslauf(ds.db, anlage)
    return await _eigene_summe(ds.db, ds.aid)


def _vergleiche_stand_fuer_stand(snap: dict, roh: dict) -> list[tuple]:
    """Abweichungen ``(key, start_ts, was, nachgefuellt, roh)``; die benannte erste Zeile des Nachfüllens zählt nicht."""
    abw = []
    assert set(snap) == set(roh) and snap, (sorted(snap), sorted(roh))
    for key in sorted(roh):
        s = {ts: (w, st) for ts, w, st in snap[key]}
        r = {ts: (w, st) for ts, w, st in roh[key]}
        if set(s) - set(r) != {_ERSTE_STUNDE} or not set(r) <= set(s):
            abw.append((key, None, "stunden", sorted(set(s) ^ set(r))[:4], None))
            continue
        folge = [ts for ts, *_ in roh[key]]
        for ts in folge:
            if abs(s[ts][1] - r[ts][1]) > kg.TOL:
                abw.append((key, ts, "stand", s[ts][1], r[ts][1]))
        for vor, ts in zip(folge, folge[1:]):
            dz, dr = s[ts][0] - s[vor][0], r[ts][0] - r[vor][0]
            if abs(dz - dr) > kg.TOL:
                abw.append((key, ts, "zuwachs", dz, dr))
    return abw


@pytest.mark.parametrize("matrix,fid", _FORMEN, ids=[f"{m}-{f}" for m, f in _FORMEN])
async def test_nachgefuellte_eigene_summe_gleich_der_aus_den_rohstaenden(matrix, fid):
    async with kg.datenstand(matrix, fid, "MQTT", eigene_summe_aus="sensor_snapshots") as ds:
        snap = await _eigene_summe(ds.db, ds.aid)
        stunden = await ks.probe_tage(ds.db, ds.aid, kg.TAGE, jetzt=kg.JETZT_TS, art="MQTT")
        bilanz = (await kg.probe(ds), await kg.probe_w2(ds)) if (matrix, fid) in _BILANZ_FORMEN else None
        roh = await _neu_aus_rohstaenden(ds)
    # Stand für Stand gleich (bis auf die benannte erste Zeile).
    abw = _vergleiche_stand_fuer_stand(snap, roh)
    assert abw == [], abw[:5]
    # Kanal-Stundentag ↔ Bestand: dieselben Klassen wie der Datenstand MQTT, `unbenannt` 0.
    klassen = dict(stunden.klassen)
    assert klassen.pop("komponenten_leistungspfad", 0) == 24 * stunden.tage["bilanz:kanal"]
    assert stunden.tage["bilanz:kanal"] >= 32 and "unbenannt" not in klassen, stunden.beispiele.get("unbenannt")
    assert klassen == KLASSEN.get((matrix, fid, "MQTT"), {}), {k: stunden.beispiele.get(k) for k in klassen}
    if bilanz is None:
        return
    (ba, bb), (w2_abw, w2_klassen, w2_n) = bilanz
    # Bilanz-Gruppe ↔ Bestand: Fassung (a) ohne Abweichung, Weg-2-Klassen und Quellenwahl wie im Datenstand MQTT.
    assert ba.verglichen["tag"] > 0 and ba.abweichungen == [], ba.abweichungen[:5]
    assert w2_n["referenz"] > 0 and w2_abw == [], w2_abw[:5]
    assert dict(w2_klassen) == W2_KLASSEN.get((matrix, fid, "MQTT"), {}), dict(w2_klassen)
    assert {k for k, w in bb.wahl.items() if w != QUELLE_KANAL} == ZAEHLER_OHNE_NACHTZEILEN.get(fid, set()), bb.wahl
    assert bb.abweichungen == [], bb.abweichungen[:5]
