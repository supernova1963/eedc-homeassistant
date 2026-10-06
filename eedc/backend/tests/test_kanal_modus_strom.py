"""Abgeleiteter Kanal „Strom je Betriebsart" der Wärmepumpe (HA-Bauform E4d, Bauplan §8a, Auftrag Punkt 1 und 5).

* **Die Regel der Stunde** (``modus_split.modus_strom_der_stunde``): Menge × Anteil je Betriebsart, Rest = was keinen
  Anteil einer erfassten Betriebsart trägt; Σ = Menge, nichts hochgerechnet.
* **Gleich der Bestands-Faltung auf denselben Stunden** (Auftrag Punkt 5): ``falte_modus_split_tag`` legt die Menge der
  Stunde auf ihren Gewinner. Mit Anteil 1,0 je Stunde (eine Betriebsart je Stunde) sind beide Wege dieselbe Zahl —
  Toleranz 1e-9 (reine Gleitkomma-Reihenfolge). In einer Wechselstunde teilt der Kanal nach Verweildauer, der Bestand
  gibt alles dem länger gelaufenen: Abweichung je Betriebsart höchstens die Menge der Wechselstunden.
* **Die Menge der Stunde** ist K3 (``wp_strom_aufteilung``) auf die Δ der Strom-Kanäle; eine Zählerlücke hat keine
  Betriebsart-Aussage (Rest), und ohne die Zeile eines Gesamtzählers trägt die Stunde nichts (seine nächste Zeile).
* **Der Schreiber** am Datenstand der Achsen-Matrix (M05: Gesamtstrom + Wärmezähler + Etikett; M06: Klima mit
  gemessenen Betriebsart-Zählern; HA-Langzeitstatistik im Recorder-Schema, Spiegel, Mitschrift aus ``aggregate_day``):
  Σ der Kanäle = Strom, die Ankerstunde, der Mitschrift-Verzug, K2 (gemessene Betriebsart ⇒ kein Kanal), die zwei
  Einstiege, Neuaufbau bitgleich, Beginn mit dem laufenden Monat.

Schwesterdateien: test_kanal_abgeleitet.py (Vorbild E4c), test_kanal_wp_leser.py, test_kanal_wp_gleichheit.py,
test_achsen_matrix.py (die Zellen als Richter).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import and_, delete, select, text

from backend.core.berechnungen.modus_split import (
    MODUS_STROM_ERFASST,
    ModusStunde,
    falte_modus_split_tag,
    modus_strom_der_stunde,
)
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

TOL = 1e-9


# ── Die Regel der Stunde (rein) ─────────────────────────────────────────────


def test_regel_der_stunde_anteil_menge_und_rest():
    je, rest = modus_strom_der_stunde(0.6, {"heizen": 0.5, "warmwasser": 0.25, "aus": 0.25})
    assert je["heizen"] == pytest.approx(0.3) and je["warmwasser"] == pytest.approx(0.15)
    assert rest == pytest.approx(0.15)                       # `aus` hat keine Menge — Rest
    assert sum(je.values()) + rest == pytest.approx(0.6)
    # keine Mitschrift ⇒ alles Rest; Zählerlücke ⇒ alles Rest; nichts wird hochgerechnet
    assert modus_strom_der_stunde(0.6, None) == ({m: 0.0 for m in MODUS_STROM_ERFASST}, 0.6)
    assert modus_strom_der_stunde(0.6, {"heizen": 1.0}, stunde_eindeutig=False)[1] == 0.6
    je, rest = modus_strom_der_stunde(0.6, {"heizen": 0.5})        # halbe Stunde gesehen
    assert je["heizen"] == pytest.approx(0.3) and rest == pytest.approx(0.3)
    # Lüften/Entfeuchten werden erfasst (Konzept §5.4)
    je, _ = modus_strom_der_stunde(1.0, {"lueften": 0.5, "entfeuchten": 0.5})
    assert (je["lueften"], je["entfeuchten"]) == (0.5, 0.5)


def _gleiche_stunden():
    """Ein Tag wie die Matrix-Form M05: 0,3 kWh je Stunde, 06:00–08:00 Warmwasser, sonst Heizen; 03:00 ohne Signal."""
    out = []
    for h in range(24):
        modus = None if h == 3 else ("warmwasser" if 6 <= h < 8 else "heizen")
        out.append((0.3 + 0.01 * h, modus))
    return out


def test_ableitung_je_stunde_gleich_der_bestands_faltung_auf_denselben_stunden():
    """Auftrag Punkt 5: dieselben Stunden (Menge, Modus) durch beide Wege — eine Betriebsart je Stunde ⇒ gleich."""
    stunden = _gleiche_stunden()
    bestand = falte_modus_split_tag([ModusStunde(kwh=k, modus=m) for k, m in stunden])
    kanal = {m: 0.0 for m in MODUS_STROM_ERFASST}
    rest = abdeckung = 0.0
    for k, m in stunden:
        je, r = modus_strom_der_stunde(k, {m: 1.0} if m else None)
        for mm, v in je.items():
            kanal[mm] += v
        rest += r
        abdeckung += 1.0 if m else 0.0
    for m in ("heizen", "warmwasser", "kuehlen"):
        assert abs(kanal[m] - bestand.teilmenge_kwh(m)) <= TOL, m
    assert abdeckung == bestand.abdeckung_h
    assert abs(sum(kanal.values()) + rest - bestand.bezug_kwh) <= TOL


def test_wechselstunde_weicht_hoechstens_um_die_menge_der_stunde_ab():
    """Eine Stunde mit 40 min Heizen und 20 min Warmwasser: der Bestand gibt dem Gewinner alles, der Kanal teilt."""
    bestand = falte_modus_split_tag([ModusStunde(kwh=0.9, modus="heizen")])
    je, _rest = modus_strom_der_stunde(0.9, {"heizen": 2 / 3, "warmwasser": 1 / 3})
    assert je["heizen"] == pytest.approx(0.6) and je["warmwasser"] == pytest.approx(0.3)
    for m in ("heizen", "warmwasser"):
        assert abs(je[m] - bestand.teilmenge_kwh(m)) <= 0.9


# ── Die Menge der Stunde (K3) ───────────────────────────────────────────────


def _w(change, spanne=3600):
    return SimpleNamespace(change=change, spanne=spanne)


def test_menge_der_stunde_ist_k3():
    from backend.services.kanal.modus_strom import menge_der_stunde

    # Gesamtzähler ist die Menge (K1), die Summanden daneben teilen nur
    z = {"inv:1:stromverbrauch_kwh": _w(1.0), "inv:1:strom_heizen_kwh": _w(0.7), "inv:1:strom_warmwasser_kwh": _w(0.2)}
    assert menge_der_stunde(z, {"getrennte_strommessung": True}) == (1.0, True)
    # ohne Gesamtzähler tragen die Summanden (K3 Regel 3)
    z = {"inv:1:strom_heizen_kwh": _w(0.7), "inv:1:strom_warmwasser_kwh": _w(0.2)}
    assert menge_der_stunde(z, {"getrennte_strommessung": True}) == (pytest.approx(0.9), True)
    # Lücke im Gesamtzähler: die Stunde trägt nichts (seine nächste Zeile trägt sie), keine Aussage
    z = {"inv:1:stromverbrauch_kwh": None, "inv:1:strom_heizen_kwh": _w(0.7)}
    assert menge_der_stunde(z, {"getrennte_strommessung": True}) == (0.0, False)
    # Zeile mit Spanne 2 h: Menge ja, Aussage nein
    assert menge_der_stunde({"inv:1:stromverbrauch_kwh": _w(0.6, 7200)}, {}) == (0.6, False)


def test_kanal_zeile_traegt_die_abgeleitete_heizwaerme_wie_der_abschluss():
    """Wie ``modus_split_schreiben._schreibe_abgeleitete_waerme``: Heizstrom × gepflegte Effizienz, Marke
    ``jaz_modus_split``, nur ohne gemessene Heizwärme und nie aus einem Default."""
    from backend.core.berechnungen.modus_split import heizwaerme_ist_abgeleitet
    from backend.services.monats_fakten import wp_kanal_zeile

    inv = SimpleNamespace(parameter={"effizienz_modus": "gesamt_jaz", "jaz": 3.5})
    daten, herkunft = wp_kanal_zeile(inv, {"stromverbrauch_kwh": 100.0, "modus_strom_heizen_kwh": 80.0,
                                           "modus_abdeckung_h": 720.0})
    assert daten["heizenergie_kwh"] == pytest.approx(280.0) and heizwaerme_ist_abgeleitet(herkunft)
    daten, herkunft = wp_kanal_zeile(inv, {"heizenergie_kwh": 250.0, "modus_strom_heizen_kwh": 80.0})
    assert daten["heizenergie_kwh"] == 250.0 and not heizwaerme_ist_abgeleitet(herkunft)
    daten, _ = wp_kanal_zeile(SimpleNamespace(parameter={}), {"modus_strom_heizen_kwh": 80.0})
    assert "heizenergie_kwh" not in daten


# ── Der Schreiber am Datenstand der Matrix ──────────────────────────────────


async def _reihe(db, key: str) -> list[tuple[int, float]]:
    return [(int(ts), float(s)) for ts, s in (await db.execute(text(
        "SELECT s.start_ts, s.sum FROM kanal_statistik s JOIN kanal k ON k.id = s.kanal_id "
        "WHERE k.key = :k ORDER BY s.start_ts"), {"k": key})).all()]


async def _kanal(db, key: str):
    from backend.models.kanal import Kanal

    return (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one_or_none()


async def test_m05_summe_der_kanaele_ist_der_strom_und_die_aufteilung_folgt_dem_etikett():
    from backend.services.kanal.modus_strom import abdeckung_key, modus_strom_key

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        keys = {m: modus_strom_key(wp, m) for m in (*MODUS_STROM_ERFASST, "rest")}
        reihen = {m: await _reihe(ds.db, k) for m, k in keys.items()}
        abd = await _reihe(ds.db, abdeckung_key(wp))
        n = len(abd)
        assert n > 24 * 30 and all(len(r) == n for r in reihen.values())
        # Σ aller Kanäle = Strom 0,3 kWh je Stunde
        gesamt = sum(r[-1][1] for r in reihen.values())
        assert gesamt == pytest.approx(0.3 * n)
        # die Ankerstunde (vor der ersten Mitschrift) ist Rest; danach je Tag 22 h Heizen, 2 h Warmwasser
        assert reihen["rest"][-1][1] == pytest.approx(0.3)
        assert reihen["heizen"][-1][1] == pytest.approx(0.3 * 22 * (n - 1) / 24)
        assert reihen["warmwasser"][-1][1] == pytest.approx(0.3 * 2 * (n - 1) / 24)
        assert reihen["kuehlen"][-1][1] == 0.0 and abd[-1][1] == n - 1
        k = await _kanal(ds.db, keys["heizen"])
        assert k.aufbaubar_ab == abd[0][0]
        # die erste Zeile ist die Stunde VOR der ersten Mitschrift (Stand vor dem ersten gedeckten Zeitraum)
        erste_mitschrift = (await ds.db.execute(text(
            "SELECT min(s.start_ts) FROM kanal_statistik s JOIN kanal k ON k.id = s.kanal_id "
            "WHERE k.key LIKE :k"), {"k": f"modus:inv:{wp}:%"})).scalar()
        assert abd[0][0] == erste_mitschrift - 3600


async def test_mitschrift_verzug_der_kanal_wartet_auf_die_mitschrift():
    """Die Strom-Kanäle reichen weiter als die Mitschrift: der abgeleitete Kanal endet an der letzten Mitschrift-Zeile
    (am Ende heißt eine fehlende Zeile „noch nicht geschrieben", nicht „nicht hingesehen")."""
    from backend.services.kanal.modus_strom import abdeckung_key

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        letzte_mitschrift = (await ds.db.execute(text(
            "SELECT max(s.start_ts) FROM kanal_statistik s JOIN kanal k ON k.id = s.kanal_id "
            "WHERE k.key LIKE :k"), {"k": f"modus:inv:{wp}:%"})).scalar()
        letzter_strom = (await _reihe(ds.db, f"inv:{wp}:stromverbrauch_kwh"))[-1][0]
        assert letzter_strom > letzte_mitschrift
        assert (await _reihe(ds.db, abdeckung_key(wp)))[-1][0] == letzte_mitschrift


async def test_gemessene_betriebsart_hat_vorrang_kein_abgeleiteter_kanal():
    """K2: das Klimagerät der Form M06 misst seine Betriebsart-Ströme — auch MIT Betriebsart-Mitschrift bekommt es
    keinen abgeleiteten Kanal; die WP mit getrennter Strommessung daneben (gleiche Mitschrift, keine Betriebsart-Zähler)
    bekommt ihn, mit der Menge der Summanden (K3)."""
    from backend.models import Anlage
    from backend.services.kanal.modus_strom import abdeckung_key, modus_strom_key, schreibe_modus_strom

    async with kg.datenstand("achsen", "M06", "HA") as ds:
        n = (await ds.db.execute(text("SELECT count(*) FROM kanal WHERE key LIKE :k"),
                                 {"k": "abgeleitet:inv:%:modus%"})).scalar()
        assert n == 0                                           # ohne Mitschrift ohnehin keiner
        # Mitschrift „heizen" für beide Geräte über die ganze Reihe nachstellen (Seed, wie E1 sie schriebe)
        t, zeilen = int(mx.REIHE_VON.timestamp()), []
        for name in ("WP HW", "Klima"):
            for modus in ("heizen", "kuehlen"):
                kid = (await ds.db.execute(text(
                    "INSERT INTO kanal (anlage_id, key, einheit, art) VALUES (:a, :k, 'Anteil', 'mean') RETURNING id"),
                    {"a": ds.aid, "k": f"modus:inv:{ds.ids[name]}:{modus}"})).scalar()
                ts = t
                while ts < int(mx.REIHE_BIS.timestamp()):
                    zeilen.append({"k": kid, "t": ts, "m": 1.0 if modus == "heizen" else 0.0})
                    ts += 3600
        await ds.db.execute(text("INSERT INTO kanal_statistik (kanal_id, start_ts, mean, familie) "
                                 "VALUES (:k, :t, :m, 'mitschrift')"), zeilen)
        await ds.db.commit()
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        await schreibe_modus_strom(ds.db, anlage, mx.JETZT, ab_ts=int(mx.REIHE_VON.timestamp()))
        await ds.db.commit()
        assert await _kanal(ds.db, abdeckung_key(ds.ids["Klima"])) is None
        # … und zwar wegen K2, nicht nur mangels Strom-Zähler: trüge das Klimagerät zusätzlich einen Gesamtzähler, bliebe
        # es ohne abgeleiteten Kanal (seine gemessenen Betriebsart-Ströme sind die Aufteilung).
        from backend.models.investition import Investition
        from backend.services.kanal.abgeleitet import verfuegbarkeit
        from backend.services.kanal.modus_strom import abzuleitende_geraete

        echt = await verfuegbarkeit(ds.db, anlage)
        invs = list((await ds.db.execute(select(Investition).where(Investition.anlage_id == ds.aid))).scalars())
        mit_gesamt = lambda inv, f: echt(inv, f) or (inv.id == ds.ids["Klima"] and f == "stromverbrauch_kwh")  # noqa: E731
        geraete = await abzuleitende_geraete(ds.db, anlage, invs, mit_gesamt)
        assert ds.ids["Klima"] not in geraete and ds.ids["WP HW"] in geraete
        hw = await _reihe(ds.db, modus_strom_key(ds.ids["WP HW"], "heizen"))
        # Σ Summanden 0,25 + 0,05 je Stunde, jede geschriebene Stunde mit Mitschrift „heizen" (keine Ankerstunde: die
        # Mitschrift beginnt mit der Reihe)
        assert hw and hw[-1][1] == pytest.approx(0.3 * len(hw))


async def test_neuaufbau_nach_verwerfen_ist_bitgleich_und_beide_einstiege_schreiben():
    from backend.models import Anlage
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.modus_strom import alle_keys, schreibe_modus_strom

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        vorher = {k: await _reihe(ds.db, k) for k in alle_keys(wp)}
        grenze = int(datetime(2026, 6, 20, 12).timestamp())
        n = await verwerfe_ab(ds.db, ds.aid, grenze)
        await ds.db.commit()
        assert n == 7 * sum(1 for ts, _ in vorher[alle_keys(wp)[0]] if ts >= grenze)
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        # Einstieg 1: der Stundenlauf (über den Schreiber des Laufs, wie `schreibe_kanaele_im_stundenlauf`)
        await schreibe_modus_strom(ds.db, anlage, mx.JETZT)
        await ds.db.commit()
        nachher = {k: await _reihe(ds.db, k) for k in alle_keys(wp)}
        assert nachher == vorher
        # Einstieg 2: die Mitschrift schreibt den Kanal fort (eigener SAVEPOINT) — nach einem zweiten Verwerfen holt der
        # Mitschrift-Lauf eines schon geschriebenen Tages (keine neue Mitschrift-Zeile) den Kanal bitgleich nach.
        from backend.services.energie_profil._helpers import ModusJeStunde
        from backend.services.kanal import schreiber

        await verwerfe_ab(ds.db, ds.aid, grenze)
        await ds.db.commit()
        assert len(await _reihe(ds.db, alle_keys(wp)[0])) < len(vorher[alle_keys(wp)[0]])
        n = await schreiber.schreibe_betriebsart_mitschrift_sicher(
            ds.db, anlage, datetime(2026, 7, 3).date(),
            ModusJeStunde({}, anteile={1: {wp: {"heizen": 1.0}}}, entitaeten={wp: "climate.wp"}),
        )
        await ds.db.commit()
        assert n > 0
        assert {k: await _reihe(ds.db, k) for k in alle_keys(wp)} == vorher


async def test_stundenlauf_einstieg_schreibt_den_kanal_fort():
    from backend.models import Anlage
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.services.kanal.modus_strom import abdeckung_key, alle_keys
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        vorher = await _reihe(ds.db, abdeckung_key(wp))
        letzte = vorher[-1][0]
        ids = [k.id for k in (await ds.db.execute(select(Kanal).where(Kanal.key.in_(alle_keys(wp))))).scalars()]
        await ds.db.execute(delete(KanalStatistik).where(and_(
            KanalStatistik.kanal_id.in_(ids), KanalStatistik.start_ts > letzte - 5 * 3600)))
        await ds.db.commit()
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        with am.umgebung(am.MATRIX_FORMEN["M05"], ds.svc):
            await schreibe_kanaele_im_stundenlauf(ds.db, anlage, mx.JETZT)
        await ds.db.commit()
        assert await _reihe(ds.db, abdeckung_key(wp)) == vorher


async def test_neuer_kanal_beginnt_mit_dem_laufenden_monat():
    """H-2 aus E4c für den WP-Kanal: ohne ``ab_ts`` beginnt ein neuer Kanal eine Stunde vor dem Monatsfenster des
    laufenden Monats — der Juni (abgeschlossen) wird nicht gedeckt, der Juli schon."""
    from backend.models import Anlage
    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.services.kanal.fenster import monatsfenster
    from backend.services.kanal.modus_strom import abdeckung_key, alle_keys, schreibe_modus_strom

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        ids = [k.id for k in (await ds.db.execute(select(Kanal).where(Kanal.key.in_(alle_keys(wp))))).scalars()]
        await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids)))
        await ds.db.execute(delete(KanalQuelle).where(KanalQuelle.kanal_id.in_(ids)))
        await ds.db.execute(delete(Kanal).where(Kanal.id.in_(ids)))
        await ds.db.commit()
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        await schreibe_modus_strom(ds.db, anlage, mx.JETZT)
        await ds.db.commit()
        k = await _kanal(ds.db, abdeckung_key(wp))
        assert k.aufbaubar_ab == monatsfenster(2026, 7)[0] - 3600
        reihe = await _reihe(ds.db, abdeckung_key(wp))
        assert reihe[0][0] == k.aufbaubar_ab and reihe[-1][0] > reihe[0][0] + 24 * 3600
        assert datetime.fromtimestamp(reihe[0][0]) == datetime(2026, 6, 30, 22) + timedelta(0)
