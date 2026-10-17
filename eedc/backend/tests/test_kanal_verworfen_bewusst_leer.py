"""Verworfen heißt bewusst leer (HA-Bauform S4, Etappe E-S4-3, S4-R-V4; V-H4-4 aus E-S3-6).

Die Regel (``bilanz_adapter.BewusstLeer``, eine Stelle) gilt am Bedarf jeder Gruppenwahl — Bilanz (``tage_bilanz``,
``_monate_bilanz``), Werkbank-Auskunft (``bilanz_quellenwahl._benoetigt``), Geräte (``geraete_leser._bedarf``) und WP
(``wp_leser._bedarf``): ein zugeordnetes Feld zählt in ``[von, bis)`` nicht als benötigt, wenn alle dort geltenden Quellen
seines Kanals ``verworfen_ts`` tragen und der Kanal vor ``bis`` keine Zeile hat. Folge: ein Tag, den nur die Kanäle tragen,
behält nach dem Verwerfen EINES Felds seine Gruppe; das Feld fehlt wie ein nie zugeordnetes. Der Tag mit ``t`` (Zeilen vor
seinem Ende) bleibt benötigt; vor dem ersten ``gueltig_ab`` greift die Regel nicht.

Datei-DB (Fixture ``datei`` aus ``test_kanal_eigene_summe_nachfuellen.py``), reine MQTT-Anlage; Kanäle aus dem Nachfüllen,
das Verwerfen über die Bausteine der Werkbank (``kanal/verwerfen.loesche_zeilen``/``markiere_quellen``) nach einem
künstlichen Sensortausch (zweite Quelle). Keine Probe liest die Uhr.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import and_, insert, select

from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalQuelle
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.kanal import geraete_leser, wp_leser
from backend.services.kanal.bilanz_adapter import BewusstLeer, bewusst_leer
from backend.services.kanal.bilanz_leser import monate_bilanz, tage_bilanz
from backend.services.kanal.bilanz_quellenwahl import bilanz_benoetigte_kanaele
from backend.services.kanal.fenster import monatsfenster, tagesfenster
from backend.services.kanal.nachfuellen import nachfuellen_eigene_summe
from backend.services.kanal.verwerfen import loesche_zeilen, markiere_quellen
from backend.tests.test_kanal_eigene_summe_nachfuellen import _investition, _staende, _ts, datei  # noqa: F401

AB = datetime(2026, 5, 25, 0)
TAGE = 12
T = datetime(2026, 6, 4, 0)                 # Sensortausch: neue Quelle ab hier, Verwerfen vor t
JETZT = datetime(2026, 6, 6, 0, 30)
EINSP, NETZ = "basis:einspeisung", "basis:netzbezug"


# ── die Regel, rein ─────────────────────────────────────────────────────────


def test_regel_rein():
    v, n = 1000, 2000
    leer = BewusstLeer({
        "a": (2000, ((500, 2000, True), (2000, None, False))),     # verworfen, erste Zeile am Ende des Zeitraums
        "b": (1500, ((500, 2000, True), (2000, None, False))),     # Zeile vor dem Ende ⇒ benötigt
        "c": (2000, ((1500, 2000, True), (2000, None, False))),    # Zeitraum teils vor der ersten Quelle: geltende verworfen
        "d": (2000, ((1200, None, True),)),
        "e": (2000, ((500, 1500, True), (1500, 2000, False), (2000, None, False))),   # eine geltende nicht verworfen
    })
    assert leer.leer("a", v, n) and leer.leer("c", v, n) and leer.leer("d", v, n)
    assert not leer.leer("b", v, n) and not leer.leer("e", v, n) and not leer.leer("x", v, n)
    assert not leer.leer("d", 100, 1000)          # vor dem ersten gueltig_ab gilt keine Quelle ⇒ die Regel greift nicht
    assert BewusstLeer().ohne(["e1"], v, n) == ["e1"]


# ── Bilanz-Gruppe und Werkbank-Auskunft ─────────────────────────────────────


async def _mqtt_zaehler(sitzungen, aid: int, *mqtt_keys: str) -> None:
    async with sitzungen() as s:
        await s.execute(insert(MqttEnergySnapshot), [{"anlage_id": aid, "energy_key": mk, "value_kwh": 1.0,
                                                      "timestamp": AB + timedelta(minutes=30)} for mk in mqtt_keys])


async def _tausch_und_verwerfen(sitzungen, aid: int, key: str) -> int:
    """Zweite Quelle ab ``T`` (anderer Sensor), dann die Bausteine der Werkbank: Zeilen vor ``T`` löschen, Marke setzen."""
    t = _ts(T)
    async with sitzungen() as s:
        k = (await s.execute(select(Kanal).where(and_(Kanal.anlage_id == aid, Kanal.key == key)))).scalar_one()
        s.add(KanalQuelle(kanal_id=k.id, gueltig_ab=t, familie=FAMILIE_MITSCHRIFT, statistic_id="neu", offset=0.0))
        await s.flush()
        assert await loesche_zeilen(s, k.id, t) > 0 and await markiere_quellen(s, k.id, t, 1_800_000_000) == 1
        return k.id


async def _anlage(datei):
    sitzungen, aid = await datei()
    for key in (EINSP, NETZ):
        await _staende(sitzungen, aid, key, {h: 100.0 + 0.5 * h for h in range(TAGE * 24)}, ab=AB)
    await _mqtt_zaehler(sitzungen, aid, "einspeisung_kwh", "netzbezug_kwh")
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    assert erg.gefuellt == 2
    return sitzungen, aid


async def test_tag_vor_t_behaelt_die_bilanz_feld_fehlt(datei):
    sitzungen, aid = await _anlage(datei)
    jetzt = _ts(JETZT)
    vor_t, tag_t = date(2026, 6, 1), T.date()
    async with sitzungen() as s:
        vorher = await tage_bilanz(s, aid, vor_t, vor_t, jetzt=jetzt)
    assert vorher[vor_t].wahl.quelle == "kanal" and vorher[vor_t].komposition.bilanz.einspeisung_kwh == 12.0
    await _tausch_und_verwerfen(sitzungen, aid, EINSP)
    async with sitzungen() as s:
        tb = await tage_bilanz(s, aid, vor_t, tag_t, jetzt=jetzt)
        mb = await monate_bilanz(s, aid, (2026, 5), (2026, 5), jetzt=jetzt)
        leer = await bewusst_leer(s, aid)
        benoetigt = {d: await bilanz_benoetigte_kanaele(s, aid, d) for d in (vor_t, tag_t)}
    # Ganz vor t: Gruppe aus den Kanälen, Einspeisung nicht erfasst (nicht 0), Netzbezug bleibt.
    k = tb[vor_t]
    assert k.wahl.quelle == "kanal" and EINSP not in k.wahl.ergebnisse
    assert k.komposition.bilanz.netzbezug_kwh == 12.0
    assert EINSP not in k.komposition.komponenten and k.komposition.bilanz.eigenverbrauch_kwh is None
    # Der Tag mit t: Zeilen vor seinem Ende ⇒ benötigt, der Anker ist verworfen ⇒ Bestand.
    assert tb[tag_t].wahl.quelle == "bestand" and EINSP in tb[tag_t].wahl.gruende
    # Der Mai (ganz vor t, die Reihe beginnt am 25.05. ⇒ Bestand): die Einspeisung ist kein Grund mehr, nur der Netzbezug;
    # die Werkbank-Auskunft fragt dieselbe Regel.
    assert mb[(2026, 5)].wahl.quelle == "bestand" and set(mb[(2026, 5)].wahl.gruende) == {NETZ}
    assert EINSP not in benoetigt[vor_t] and EINSP in benoetigt[tag_t] and NETZ in benoetigt[vor_t]
    assert leer.leer(EINSP, *tagesfenster(vor_t)) and not leer.leer(EINSP, *tagesfenster(tag_t))
    assert leer.leer(EINSP, *monatsfenster(2026, 5)) and not leer.leer(NETZ, *tagesfenster(vor_t))


# ── Geräte- und WP-Gruppe ───────────────────────────────────────────────────


async def test_geraete_und_wp_bedarf_ohne_das_verworfene_feld(datei):
    sitzungen, aid = await datei()
    wb = await _investition(sitzungen, aid, "wallbox")
    wp = await _investition(sitzungen, aid, "waermepumpe")
    for key in (f"inv:{wb}:ladung_kwh", f"inv:{wp}:stromverbrauch_kwh", f"inv:{wp}:waerme_kwh"):
        await _staende(sitzungen, aid, key, {h: 10.0 + h for h in range(TAGE * 24)}, ab=AB)
    await _mqtt_zaehler(sitzungen, aid, f"inv/{wb}/ladung_kwh", f"inv/{wp}/stromverbrauch_kwh", f"inv/{wp}/waerme_kwh")
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    await _tausch_und_verwerfen(sitzungen, aid, f"inv:{wb}:ladung_kwh")
    await _tausch_und_verwerfen(sitzungen, aid, f"inv:{wp}:stromverbrauch_kwh")
    vor_t, tag_t = date(2026, 6, 1), T.date()
    async with sitzungen() as s:
        gst = await geraete_leser._stamm(s, aid)
        wst = await wp_leser._stamm(s, aid)
        aktiv = (lambda i: True)
        emob_vor, _ = await geraete_leser._bedarf(s, gst, aktiv, vor_t, tagesfenster(vor_t))
        emob_t, _ = await geraete_leser._bedarf(s, gst, aktiv, tag_t, tagesfenster(tag_t))
        wp_vor = await wp_leser._bedarf(s, wst, aktiv, tagesfenster(vor_t))
        wp_t = await wp_leser._bedarf(s, wst, aktiv, tagesfenster(tag_t))
        wp_ohne = await wp_leser._bedarf(s, wst, aktiv)
    assert wb not in emob_vor.direkt and emob_t.direkt[wb] == ["ladung_kwh"]
    assert wp_vor.direkt[wp] == ["waerme_kwh"] and "stromverbrauch_kwh" in wp_t.direkt[wp]
    assert "stromverbrauch_kwh" in wp_ohne.direkt[wp]               # ohne Fenster keine Regel (Aufrufer ohne Zeitraum)
