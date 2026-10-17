"""WP-Kanal-Tage aus gespeicherten Ständen (HA-Bauform S4, Etappe E-S4-3, Entscheide Master H-2a/H-2b).

Nachbau 2 macht Tage zu WP-Kanal-Tagen, an denen es keine Betriebsart-Mitschrift gibt und deren Stände nur um 23:00/00:00
liegen (mess3 Anlage 2). Zwei Leser-Regeln dafür:

* **H-2a — die Betriebsart ist eine Bahn der Stundenzeile:** hat der abgeleitete Kanal «Strom je Betriebsart» eines Geräts am
  Tag keine Zeile, nehmen die Modus-Stunden (``kanal_stunden.modus_stunden_mit_rueckfall``) und der Tages-Split
  (``_wp_aus_kanaelen``) die Modus-Spur der Stundenzeilen — Stunde ``h`` (Beginn) aus der Bestandszeile ``h+1`` (S4-R-3b);
  hat er Zeilen, gewinnt er (Gegenprobe).
* **H-2b — kein Leistungspfad in einer Kanal-Stunde ohne Zeile:** ``/stunden`` fällt für die WP-Spalte nur bei Wahl
  ``bestand`` auf ``komponenten`` zurück (#263); eine leere Stunde eines WP-Kanal-Tags bleibt leer, Σ der Spalte = Tag.
  Gegenprobe: ein Bestandstag behält den Rückfall.

Datei-DB (Fixture ``datei`` aus ``test_kanal_eigene_summe_nachfuellen.py``): reine MQTT-Anlage mit einer Wärmepumpe,
Paar-Reihe ``stromverbrauch_kwh`` aus ``ha_statistics``, Stundenzeilen mit Leistungspfad und Betriebsart. Keine Probe
liest die Uhr.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import insert, select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.kanal.nachfuellen import nachfuellen_eigene_summe
from backend.tests.test_kanal_eigene_summe_nachfuellen import _investition, _staende, _ts, datei  # noqa: F401

AB = datetime(2026, 6, 1, 0)
TAG = date(2026, 6, 5)
BESTANDSTAG = date(2026, 6, 20)             # nach der Reihe: keine Stände ⇒ WP-Gruppe Bestand
JETZT = _ts(datetime(2026, 6, 25, 0, 30))
TAGES_KWH = 6.0                            # WP-Strom je Tag (Paar-Reihe: 5,5 bis 23:00, 0,5 in der letzten Stunde)


def _modus(h: int) -> str:
    return "heizen" if h < 12 else "warmwasser"


async def _anlage(datei):
    sitzungen, aid = await datei()
    wp = await _investition(sitzungen, aid, "waermepumpe")
    folge = {}
    for i in range(10):
        folge[i * 24 + 23] = 100.0 + TAGES_KWH * (i + 1) - 0.5
        folge[(i + 1) * 24] = 100.0 + TAGES_KWH * (i + 1)
    await _staende(sitzungen, aid, f"inv:{wp}:stromverbrauch_kwh", folge, quelle="ha_statistics", ab=AB)
    async with sitzungen() as s:
        await s.execute(insert(MqttEnergySnapshot), [{"anlage_id": aid, "energy_key": f"inv/{wp}/stromverbrauch_kwh",
                                                      "timestamp": AB + timedelta(minutes=30), "value_kwh": 1.0}])
        for d in (TAG, TAG + timedelta(days=1), BESTANDSTAG, BESTANDSTAG + timedelta(days=1)):
            for h in range(24):            # Stundenzeile (Ende-Raster): Leistungspfad 0,25 kWh, Betriebsart der Stunde
                s.add(TagesEnergieProfil(anlage_id=aid, datum=d, stunde=h, waermepumpe_kw=None,
                                         komponenten={f"waermepumpe_{wp}": -0.25},
                                         betriebsmodus_je_wp={str(wp): _modus(h)}))
            s.add(TagesZusammenfassung(anlage_id=aid, datum=d, komponenten_kwh={f"waermepumpe_{wp}": TAGES_KWH}))
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=datetime.fromtimestamp(JETZT))
    assert erg.gefuellt == 1
    return sitzungen, aid, wp


async def _stunden(sitzungen, aid, datum):
    from backend.api.routes.energie_profil.serien import get_stundenwerte
    from backend.services.kanal import bilanz_leser

    orig = bilanz_leser.uhr
    bilanz_leser.uhr = lambda: JETZT
    try:
        async with sitzungen() as s:
            return (await get_stundenwerte(aid, datum, s)).stunden
    finally:
        bilanz_leser.uhr = orig


async def test_h2b_kanal_tag_wp_spalte_ohne_leistungspfad_bestandstag_mit(datei):
    sitzungen, aid, _wp = await _anlage(datei)
    st = await _stunden(sitzungen, aid, TAG)
    werte = {z.stunde: z.waermepumpe_kw for z in st}
    assert werte[22] == 5.5 and werte[23] == 0.5 and all(werte[h] is None for h in range(22)), werte
    assert sum(v for v in werte.values() if v is not None) == TAGES_KWH
    bestand = {z.stunde: z.waermepumpe_kw for z in await _stunden(sitzungen, aid, BESTANDSTAG)}
    assert set(bestand.values()) == {0.25}                       # Bestandstag: der Rückfall #263 bleibt


async def test_h2a_modus_aus_den_stundenzeilen_ohne_mitschrift(datei):
    from backend.services.energie_profil.kanal_stunden import modus_stunden_mit_rueckfall, tages_eingaenge
    from backend.services.kanal import bilanz_leser
    from backend.services.kanal.stunden_leser import GRUPPE_WP, kanal_stundentag

    sitzungen, aid, wp = await _anlage(datei)
    orig = bilanz_leser.uhr
    bilanz_leser.uhr = lambda: JETZT
    try:
        async with sitzungen() as s:
            tag = await kanal_stundentag(s, aid, TAG)
            assert tag.wahlen[GRUPPE_WP].quelle == "kanal"
            modus = await modus_stunden_mit_rueckfall(s, aid, TAG, tag.gruppen[GRUPPE_WP])
            invs = {str(i.id): i for i in (await s.execute(select(Investition))).scalars().all()}
            e = await tages_eingaenge(s, await s.get(Anlage, aid), invs, TAG)
    finally:
        bilanz_leser.uhr = orig
    # Stunde h (Beginn) trägt die Betriebsart der Bestandszeile h+1 (Stunde 23: Slot 0 des Folgetags).
    je_stunde = {m.stunde: m.modus for m in modus[str(wp)]}
    assert je_stunde == {h: _modus(h + 1) if h < 23 else _modus(0) for h in range(24)}
    split = e.splits[str(wp)]
    assert e.wp_aus_kanal and split.abdeckung_h == 24.0
    assert set(split.kwh_je_modus) == {"heizen", "warmwasser"}


async def test_h2a_gegenprobe_mitschrift_kanal_gewinnt(datei, monkeypatch):
    """Hat der abgeleitete Modus-Kanal Zeilen, gewinnt er — die Modus-Spur der Stundenzeilen bleibt draußen."""
    from backend.services.energie_profil import kanal_stunden as ks

    sitzungen, aid, wp = await _anlage(datei)

    async def kanal_zeilen(db, anlage_id, datum, inv_ids, **kw):
        return {wp: {"kuehlen": tuple([1.0] + [None] * 23)}}

    monkeypatch.setattr(ks, "modus_strom_stunden", kanal_zeilen)
    monkeypatch.setattr(ks, "_abgeleitete_geraete", lambda _wp: [wp])
    async with sitzungen() as s:
        modus = await ks.modus_stunden_mit_rueckfall(s, aid, TAG, None)
    assert [(m.stunde, m.modus, m.kwh) for m in modus[str(wp)]] == [(0, "kuehlen", 1.0)]

