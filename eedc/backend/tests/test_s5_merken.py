"""HA-Bauform S5, Etappe E-S5-1c — Merken der Kanal-Stundentage je Prozess (Bauplan S5 §10d **S5-R7a–f**, Entscheid H-1 → A).

``services/kanal/merken.py`` hält je abgeschlossenem Tag die Adapter-Zeilen (Speicher ``ADAPTER``, gerufen aus
``kanal_stunden.stunden_der_kanal_tage``) und die Tageswahl der Bilanz (Speicher ``TAGESWAHL``, gerufen aus
``bilanz_leser.kanal_tage``). Proben (Auftrag Punkt 4, R7e):

* **Treffer bitgleich zum Kaltlauf** — zwei Aufrufe, ``repr``-gleich; der zweite rechnet nur die nicht abgeschlossenen Tage.
* **Je Schreibstelle von ``kanal_statistik``** (R7c i, die fünf aus ``SCHREIBER_KANAL_STATISTIK``) — die Schreibstelle real
  gerufen ⇒ der nächste Aufruf liefert die neuen Mengen (= Kaltlauf), beide Speicher gemeinsam.
* **Investition/Zuordnung/Offset/Löschen** (R7c ii, ``after_flush``) ⇒ neue Mengen.
* **Laufender Tag und Vortag** innerhalb ``SCHREIBVERZUG_S`` nie gemerkt — Uhr der Lese-Schicht gestellt (kein freezegun);
  die Tagesgrenze in der Prozesszone (die Datei läuft in Berlin, UTC und Auckland).
* **MQTT-Schlüsselwechsel** (R7c iii) ⇒ Fehltreffer; **LRU** bei ``OBERGRENZE_TAGE``; **Verfall** 24 h.
* **Lade-Kontext und Merken doppeln nicht** — innerhalb einer Anfrage hält der Kontext, darunter der Speicher.

Datenstand: Achsen-Formen (``kanal_bilanz_gleichheit.datenstand``, HA, Kanal-Tage 01.06.–03.07.2026), Uhr der Matrix
(04.07.2026 00:30: der 03.07. liegt im Schreibverzug, nicht abgeschlossen). Schwesterdateien: test_s5_stunden_der_tage.py,
test_kanal_lesen_waechter.py (Wächter ``SCHREIBER_KANAL_STATISTIK``), test_e4f_lade_kontext.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.energie_profil import kanal_stunden as ks
from backend.services.kanal import bilanz_leser, merken
from backend.services.kanal import stunden_leser as sl
from backend.tests import kanal_bilanz_gleichheit as kg

VON, BIS = date(2026, 6, 1), date(2026, 7, 3)
TAG = date(2026, 6, 15)
#: Ein MQTT-Zähler, den die HA-Anlage der Form vorher nicht hatte (``snapshot/keys._MQTT_BASIS_KEYS``).
MQTT_SCHLUESSEL = "netzbezug_kwh"
FELDER = ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "waermepumpe_kw", "wallbox_kw",
          "ueberschuss_kw", "defizit_kw", "spannen", "raster")


@pytest.fixture
def uhr(monkeypatch):
    """Die Uhr der Lese-Schicht steht auf der Uhr der Matrix (04.07.2026 00:30)."""
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


def _ts(tag: date, stunde: int = 0, minute: int = 0, sekunde: int = 0) -> int:
    return int(datetime(tag.year, tag.month, tag.day, stunde, minute, sekunde).timestamp())


async def _lesen(ds) -> tuple[str, str]:
    """Beide gemerkten Wege: die Tageswahl (``kanal_tage``) und die Stundenzeilen über die Ladefunktion (Adapter-Zeilen)."""
    kt = await bilanz_leser.kanal_tage(ds.db, ds.aid, VON, BIS)
    zeilen = await ks.stunden_der_tage(ds.db, ds.aid, VON, BIS)
    return repr(kt), repr([(z.datum, z.stunde, *(getattr(z, f, None) for f in FELDER),
                            tuple(f for f in ("wallbox_kw", "waermepumpe_kw") if ks.aus_kanal_gruppe(z, f)))
                           for z in zeilen])


async def _kalt(ds) -> tuple[str, str]:
    merken.leeren()
    return await _lesen(ds)


def _tage_im(speicher: merken.Speicher) -> set[date]:
    return {k[2] for k in speicher._d}


async def _pv_kanal(ds) -> Kanal:
    """Der Zähler eines PV-Geräts (``inv:<id>:<feld>``, nicht der Anlagenzähler)."""
    keys = [k for k in await ks.kanaele_der_achse(ds.db, ds.aid, VON, BIS, "pv") if k.startswith("inv:")]
    return (await ds.db.execute(select(Kanal).where(Kanal.anlage_id == ds.aid, Kanal.key.in_(keys))
                                .order_by(Kanal.key))).scalars().first()


def _sitzungen(ds):
    macher = async_sessionmaker(ds.db.bind, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    return sitzungen


async def _vorher_nachher(ds, schreiben) -> tuple[tuple, tuple, tuple]:
    """Lesen (füllt beide Speicher) → ``schreiben()`` → lesen → kalt lesen."""
    vorher = await _lesen(ds)
    assert TAG in _tage_im(merken.TAGESWAHL)     # gemerkt (als Kanal-Tag oder als «kein Kanal-Tag»)
    await schreiben()
    nachher = await _lesen(ds)
    return vorher, nachher, await _kalt(ds)


# ── R7e: Treffer bitgleich, nur abgeschlossene Tage ─────────────────────────


async def test_treffer_bitgleich_zum_kaltlauf_und_nur_offene_tage_neu(uhr, monkeypatch):
    async with kg.datenstand("achsen", "M04", "HA") as ds:
        kalt = await _kalt(ds)
        bereiche: list[tuple[date, date]] = []
        echt = sl.kanal_stundentage

        async def spion(db, aid, von, bis, **kw):
            bereiche.append((von, bis))
            return await echt(db, aid, von, bis, **kw)

        monkeypatch.setattr(ks, "kanal_stundentage", spion)
        warm = await _lesen(ds)
        assert warm == kalt
        # der zweite Aufruf rechnet nur den 03.07. (Schreibverzug) — EIN Bereich der Fehltage
        assert bereiche == [(BIS, BIS)]
        assert BIS not in _tage_im(merken.ADAPTER) | _tage_im(merken.TAGESWAHL)
        assert _tage_im(merken.TAGESWAHL) == {VON + timedelta(days=i) for i in range((BIS - VON).days)}


@pytest.mark.parametrize("stunde, minute, sekunde, gemerkt", [(1, 9, 59, False), (1, 10, 0, True)])
async def test_tagesgrenze_schreibverzug_in_der_prozesszone(monkeypatch, stunde, minute, sekunde, gemerkt):
    """R7a: der Vortag ist ab ``00:00 + SCHREIBVERZUG_S`` (01:10 Ortszeit) abgeschlossen, vorher nie gemerkt; der laufende
    Tag nie. Die Uhr wird in der Prozesszone gestellt (Berlin, UTC, Auckland)."""
    jetzt = _ts(date(2026, 7, 4), stunde, minute, sekunde)
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: jetzt)
    assert merken.abgeschlossen(date(2026, 7, 3), jetzt) is gemerkt
    assert merken.abgeschlossen(date(2026, 7, 4), jetzt) is False
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _lesen(ds)
        assert (date(2026, 7, 3) in _tage_im(merken.TAGESWAHL)) is gemerkt
        assert date(2026, 7, 4) not in _tage_im(merken.TAGESWAHL) | _tage_im(merken.ADAPTER)
        assert date(2026, 7, 2) in _tage_im(merken.TAGESWAHL)


# ── R7c (i): die fünf Schreibstellen, real gerufen ──────────────────────────


async def test_schreibstelle_schreiber_zeilen_einfuegen(uhr):
    """``schreiber._zeilen_einfuegen``: die Spiegelzeilen ab TAG 12:00 kommen (um 5 kWh höher) nach — TAG hat eine neue
    Tagesmenge (Tageswahl) und neue Stunden (Adapter-Zeilen): ein Kanal-Schreiben erneuert beide Speicher."""
    from backend.services.kanal.schreiber import _zeilen_einfuegen

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)
        alt = (await ds.db.execute(select(KanalStatistik).where(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(TAG, 12)))).scalars().all()
        zeilen = [{"kanal_id": k.id, "start_ts": z.start_ts, "sum": z.sum + 5.0, "state": z.state, "mean": None,
                   "min": None, "max": None, "familie": z.familie} for z in alt]
        await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id == k.id,
                                                         KanalStatistik.start_ts >= _ts(TAG, 12)))
        await ds.db.commit()
        merken.leeren()     # an der Schreibschicht vorbei (Vorbereitung der Probe)

        async def schreiben():
            assert await _zeilen_einfuegen(ds.db, zeilen) == len(zeilen)
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt
        assert nachher[0] != vorher[0] and nachher[1] != vorher[1]     # Tageswahl UND Adapter-Zeilen neu


async def test_beide_speicher_gemeinsam_ab_dem_tag_des_vorstands(uhr):
    """Ein Kanal-Schreiben verwirft in BEIDEN Speichern genau die Tage ab dem Tag des vorigen Stands."""
    from backend.services.kanal.schreiber import _zeilen_einfuegen

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)
        await _lesen(ds)
        vor_a, vor_t = _tage_im(merken.ADAPTER), _tage_im(merken.TAGESWAHL)
        z = (await ds.db.execute(select(KanalStatistik).where(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts == _ts(TAG, 12)))).scalar_one()
        await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id == k.id,
                                                         KanalStatistik.start_ts == z.start_ts))
        await _zeilen_einfuegen(ds.db, [{"kanal_id": k.id, "start_ts": z.start_ts, "sum": z.sum, "state": z.state,
                                         "mean": None, "min": None, "max": None, "familie": z.familie}])
        assert _tage_im(merken.ADAPTER) == {d for d in vor_a if d < TAG}
        assert _tage_im(merken.TAGESWAHL) == {d for d in vor_t if d < TAG}
        await ds.db.commit()


async def test_schreibstelle_abgeleitet_verwerfe_ab(uhr):
    """``abgeleitet.verwerfe_ab``: die abgeleiteten Kanäle ab dem Tag neu aufbauen (Wallbox + E-Auto, M08)."""
    from backend.services.kanal.abgeleitet import verwerfe_ab

    async with kg.datenstand("achsen", "M08", "HA") as ds:
        async def schreiben():
            assert await verwerfe_ab(ds.db, ds.aid, _ts(TAG)) > 0
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


async def test_schreibstelle_nachfuellen_neu_spiegeln(uhr):
    """``nachfuellen.neu_spiegeln``: ein verfälschter Spiegel-Abschnitt wird aus HA neu geladen ⇒ die Mengen von HA."""
    from backend.services.kanal.nachfuellen import neu_spiegeln

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)
        await ds.db.execute(update(KanalStatistik).where(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(TAG, 12),
            KanalStatistik.familie == FAMILIE_SPIEGEL).values(sum=KanalStatistik.sum + 5.0))
        await ds.db.commit()
        merken.leeren()     # an der Schreibschicht vorbei (Vorbereitung)

        async def schreiben():
            assert await neu_spiegeln(_sitzungen(ds), k.id, _ts(TAG), ha_svc=ds.svc) > 0

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


async def test_schreibstelle_verwerfen_loesche_zeilen(uhr):
    """``verwerfen.loesche_zeilen`` + ``markiere_quellen``: die Zeilen eines Kanals vor ``t`` weg ⇒ die Tage davor neu."""
    from backend.services.kanal.verwerfen import loesche_zeilen, markiere_quellen

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)

        async def schreiben():
            assert await loesche_zeilen(ds.db, k.id, _ts(TAG)) > 0
            await markiere_quellen(ds.db, k.id, _ts(TAG), _ts(date(2026, 7, 4)))
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


async def test_schreibstelle_investition_loeschen_messreihen(uhr):
    """``investitionen/crud._entferne_messreihen``: die Kanäle einer PV-Investition weg ⇒ neue Mengen."""
    from backend.api.routes.investitionen.crud import _entferne_messreihen

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)
        inv_id = int(k.key.split(":")[1]) if k.key.startswith("inv:") else None
        assert inv_id is not None, k.key

        async def schreiben():
            assert (await _entferne_messreihen(ds.db, ds.aid, inv_id))[1] > 0
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


# ── R7c (ii): after_flush an Anlage / Investition / Kanal / KanalQuelle ──────


async def test_investition_stilllegen_neue_mengen(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)
        inv = (await ds.db.execute(select(Investition).where(Investition.id == int(k.key.split(":")[1])))).scalar_one()

        async def schreiben():
            inv.stilllegungsdatum = TAG
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


async def test_investition_loeschen_orm_neue_mengen(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)
        inv = (await ds.db.execute(select(Investition).where(Investition.id == int(k.key.split(":")[1])))).scalar_one()

        async def schreiben():
            await ds.db.delete(inv)
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


async def test_zuordnung_aendern_neue_mengen(uhr):
    """``Anlage.sensor_mapping``: die Zuordnung des PV-Zählers entfernt ⇒ der Zähler fällt aus den Eingängen."""
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)
        _, inv_id, feld = k.key.split(":", 2)
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()

        async def schreiben():
            mapping = dict(anlage.sensor_mapping or {})
            invs = dict(mapping.get("investitionen") or {})
            eintrag = dict(invs.get(inv_id) or {})
            felder = dict(eintrag.get("felder") or {})
            felder.pop(feld, None)
            invs[inv_id] = {**eintrag, "felder": felder}
            anlage.sensor_mapping = {**mapping, "investitionen": invs}
            flag_modified(anlage, "sensor_mapping")
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


async def test_offset_neue_quelle_neue_mengen(uhr):
    """Eine neue ``KanalQuelle`` mit Offset mitten im Bereich (Sensortausch) ⇒ der Zuwachs an der Grenze ändert sich."""
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        k = await _pv_kanal(ds)

        async def schreiben():
            ds.db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(TAG, 12), familie=FAMILIE_SPIEGEL,
                                  statistic_id="sensor.tausch", offset=3.0))
            await ds.db.commit()

        vorher, nachher, kalt = await _vorher_nachher(ds, schreiben)
        assert nachher == kalt and nachher != vorher


# ── R7c (iii), R7d ──────────────────────────────────────────────────────────


async def test_mqtt_schluesselwechsel_ist_fehltreffer(uhr):
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _lesen(ds)      # kalt: zählt die Fehltage eines Kaltlaufs
        vorher, vorher_a = merken.TAGESWAHL.fehltage, merken.ADAPTER.fehltage
        ds.db.add(MqttEnergySnapshot(anlage_id=ds.aid, energy_key=MQTT_SCHLUESSEL, value_kwh=1.0,
                                     timestamp=datetime(2026, 7, 3, 12)))
        await ds.db.commit()
        await _lesen(ds)
        # jeder Tag neu gerechnet — so viele Fehltage wie im Kaltlauf
        assert merken.TAGESWAHL.fehltage - vorher == vorher and merken.ADAPTER.fehltage - vorher_a == vorher_a


def test_lru_verdraengt_bei_obergrenze():
    s = merken.Speicher("probe")
    tage = [date(2020, 1, 1) + timedelta(days=i) for i in range(merken.OBERGRENZE_TAGE + 1)]
    for d in tage[:-1]:
        s.lege((1, 7, d, ()), d, frozenset())
    assert s.nimm((1, 7, tage[0], ()), frozenset())[0]     # zuletzt benutzt ⇒ bleibt
    s.lege((1, 7, tage[-1], ()), tage[-1], frozenset())
    assert len(s) == merken.OBERGRENZE_TAGE
    assert s.nimm((1, 7, tage[0], ()), frozenset())[0]
    assert not s.nimm((1, 7, tage[1], ()), frozenset())[0]     # der älteste unbenutzte ist verdrängt


def test_verfall_nach_24_stunden(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(merken, "uhr_s", lambda: t[0])
    s = merken.Speicher("probe")
    s.lege((1, 7, date(2026, 6, 1), ()), "x", frozenset())
    t[0] += merken.VERFALL_S - 1
    assert s.nimm((1, 7, date(2026, 6, 1), ()), frozenset()) == (True, "x")
    t[0] += 1
    assert s.nimm((1, 7, date(2026, 6, 1), ()), frozenset()) == (False, None)


def test_generation_und_bereich():
    s = merken.ADAPTER
    for d in (date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)):
        s.lege((1, 7, d, ()), d, frozenset())
        s.lege((1, 8, d, ()), d, frozenset())
    merken.invalidiere(7, von=date(2026, 6, 2), bis=date(2026, 6, 2))
    assert {(k[1], k[2]) for k in s._d} == {(7, date(2026, 6, 1)), (7, date(2026, 6, 3))} | {
        (8, d) for d in (date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3))}
    merken.invalidiere(7)
    assert not s.nimm((1, 7, date(2026, 6, 1), ()), frozenset())[0]
    assert s.nimm((1, 8, date(2026, 6, 1), ()), frozenset())[0]
    merken.invalidiere(None)
    assert not s.nimm((1, 8, date(2026, 6, 1), ()), frozenset())[0]


# ── Lade-Kontext und Merken doppeln nicht ───────────────────────────────────


async def test_lade_kontext_und_merken_doppeln_nicht(uhr, monkeypatch):
    """In einer Anfrage hält der Lade-Kontext ``stunden_der_tage`` (der zweite Aufruf fragt den Speicher nicht); in der
    nächsten Anfrage liefert der Speicher jeden abgeschlossenen Tag, der Bereichs-Leser rechnet nur den offenen."""
    from backend.services.kanal.lade_kontext import lese_anfrage

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        bereiche: list = []
        echt = sl.kanal_stundentage

        async def spion(db, aid, von, bis, **kw):
            bereiche.append((von, bis))
            return await echt(db, aid, von, bis, **kw)

        monkeypatch.setattr(ks, "kanal_stundentage", spion)
        with lese_anfrage():
            a = await ks.stunden_der_tage(ds.db, ds.aid, VON, BIS)
            n = merken.ADAPTER.treffer + merken.ADAPTER.fehltage
            b = await ks.stunden_der_tage(ds.db, ds.aid, VON, BIS)
            assert merken.ADAPTER.treffer + merken.ADAPTER.fehltage == n
        assert len(bereiche) == 1 and [id(x) for x in a] == [id(x) for x in b]
        with lese_anfrage():
            await ks.stunden_der_tage(ds.db, ds.aid, VON, BIS)
        assert bereiche[1:] == [(BIS, BIS)]
