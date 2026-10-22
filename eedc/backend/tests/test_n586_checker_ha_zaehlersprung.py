"""N-586 — Daten-Checker „Zählersprung in Home Assistant" (HA-Bauform E4a-2, Auftrag Punkt 5).

Seit E4a-2 trägt eedc einen Phantomsprung aus HAs Statistik wie das HA-Energie-Dashboard in Tag und Monat (kein
Deckel). Der Checker benennt ihn: Muster Reset, danach Rückkehr auf etwa den alten Stand; Stunde, Sensor, Menge; Rat:
in HA korrigieren. Keine Probe liest die Uhr (Naht ``jetzt``)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.models.anlage import Anlage
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.services.daten_checker.datenquelle.ha_sprung import HaZaehlersprungChecks, finde_spruenge
from backend.services.daten_checker.kategorien import CheckKategorie

T0 = datetime(2026, 6, 10, 0)
JETZT = datetime(2026, 6, 20, 0)


def _reihe(stunden: int, *, reset_bei=None, rueckkehr_bei=None, rate=1.0, start=5000.0):
    """``(start_ts, state, sum)`` je Stunde wie HA: ``state`` der Zähler, ``sum`` HAs Summe. Zwischen Reset und
    Rückkehr meldet der Zähler 0; HA beginnt beim Reset einen neuen Zyklus und bucht die Rückkehr als Zuwachs."""
    out, stand, summe, zuvor = [], start, 0.0, start
    for h in range(stunden):
        stand += rate
        st = 0.0 if (reset_bei is not None and reset_bei <= h < rueckkehr_bei) else stand
        if st >= zuvor:
            summe += st - zuvor
        else:
            summe += st          # HA: Rücksprung = neuer Zyklus ab 0
        zuvor = st
        out.append((int((T0 + timedelta(hours=h)).timestamp()), st, summe))
    return out


def test_reset_und_rueckkehr_ergeben_einen_sprung_in_hoehe_des_alten_stands():
    z = _reihe(48, reset_bei=20, rueckkehr_bei=23)
    (s,) = finde_spruenge("sensor.pv", z)
    assert s.rueckkehr_ts == z[23][0]
    # Phantommenge = Σ sum über die Strecke − was der Zähler selbst zeigt = der Stand vor dem Reset; die 4 kWh,
    # die der Zähler in den vier Stunden wirklich gezählt hat, sind keine Phantomenergie.
    assert s.menge_kwh == pytest.approx(z[19][1], abs=1e-6)
    assert s.stand_reset == 0.0 and s.stand_vorher == pytest.approx(z[19][1])


def test_ohne_reset_kein_sprung_und_ein_echter_neubeginn_ist_keiner():
    assert finde_spruenge("sensor.pv", _reihe(48)) == []
    # Zählertausch: der Stand fällt und bleibt unten — keine Rückkehr, kein Phantom.
    z = _reihe(48)
    tausch = [(ts, (st - 5000.0 if i >= 20 else st), su) for i, (ts, st, su) in enumerate(z)]
    assert finde_spruenge("sensor.pv", tausch) == []


def _tagesreset(tage: int):
    """Ein täglich zurückgesetzter Helfer (utility_meter): ``state`` um Mitternacht 0, dann 1 kWh je Stunde 08–17;
    HAs ``sum`` zählt korrekt weiter (Reset = neuer Zyklus)."""
    out, summe, zuvor = [], 0.0, 0.0
    for h in range(24 * tage):
        t = T0 + timedelta(hours=h)
        st = float(sum(1 for x in range(8, 18) if x <= t.hour)) if t.hour else 0.0
        summe += st - zuvor if st >= zuvor else st
        zuvor = st
        out.append((int(t.timestamp()), st, summe))
    return out


def test_ein_taeglich_zurueckgesetzter_zaehler_ist_kein_sprung():
    """Nachmessung E4a-2, Punkt 6: der Stand fällt jede Nacht auf 0 und zählt dann hoch — die Rückkehr auf den
    Vortagesstand geschieht über zehn Stunden, nicht in EINER; HAs `sum` trägt keinen Phantomsprung."""
    assert finde_spruenge("sensor.helfer_heute", _tagesreset(5)) == []


# ── N-764 (#436): Tageszähler mit starkem erstem Zuwachs ─────────────────────────────────────────────────────


def _tagesertrag(tageswerte: list[float], *, glitch_tag=None):
    """PV-Tagesertrag wie HA ihn führt: ``state`` 00:00–08:00 = 0, ab 09:00 der Tageswert (eine helle Stunde
    bringt ihn ganz); HAs ``sum`` zählt korrekt (Reset = neuer Zyklus, der Sprung 0 → Tageswert ist echte Energie).
    ``glitch_tag``: an diesem Tag meldet der Sensor um 14:00 kurz 0 und kehrt um 15:00 zurück (echtes Phantom)."""
    out, summe, zuvor = [], 0.0, 0.0
    for d, wert in enumerate(tageswerte):
        for h in range(24):
            t = T0 + timedelta(days=d, hours=h)
            st = wert if h >= 9 else 0.0
            if glitch_tag == d and h == 14:
                st = 0.0
            summe += st - zuvor if st >= zuvor else st
            zuvor = st
            out.append((int(t.timestamp()), st, summe))
    return out


def test_n764_tageszaehler_nach_schwachem_vortag_ist_kein_sprung():
    """(a) Vortag 1,5 kWh, Mitternacht 0, erste helle Stunde 2,0 kWh (≥ 90 % des Vortags) — an drei Mitternächten.
    Bis N-764: drei Phantomfunde, der erste mit der Menge des Vortags (1,5 kWh) und der Anweisung, HAs richtige
    Statistik zu ändern."""
    assert finde_spruenge("sensor.pv_tagesertrag", _tagesertrag([1.5, 2.0, 2.0, 2.0])) == []


def test_n764_ein_einzelner_tag_im_fenster_bleibt_ein_fund():
    """(b) Benannte Grenze: mit nur einer Mitternacht im Fenster ist der Tageszähler vom Glitch nicht zu trennen."""
    (s,) = finde_spruenge("sensor.pv_tagesertrag", _tagesertrag([1.5, 2.0]))
    assert s.menge_kwh == pytest.approx(1.5)


def test_n764_lebenszeit_zaehler_mit_naechtlichem_reset_bleibt_drei_funde():
    """(c) Das N-586-Muster: Wechselrichter nachts aus (22:00–06:00 meldet er 0), morgens zurück auf den alten
    Stand — drei Nächte, drei Phantome. Die Reset-Zeile liegt um 22:00, nicht um Mitternacht."""
    out, stand, summe, zuvor = [], 5000.0, 0.0, 5000.0
    for h in range(24 * 4):
        t = T0 + timedelta(hours=h)
        if 7 <= t.hour < 20:
            stand += 1.0
        aus = any(24 * d + 22 <= h < 24 * (d + 1) + 6 for d in range(3))
        st = 0.0 if aus else stand
        summe += st - zuvor if st >= zuvor else st
        zuvor = st
        out.append((int(t.timestamp()), st, summe))
    funde = finde_spruenge("sensor.wr_gesamt", out)
    assert len(funde) == 3
    assert all(datetime.fromtimestamp(f.rueckkehr_ts).hour == 6 for f in funde)


def test_n764_ein_echtes_phantom_am_tageszaehler_bleibt_ein_fund():
    """Gegenprobe: nur der Mitternachts-Reset gilt als Zyklus — ein Aussetzer am Nachmittag desselben
    Tageszählers (14:00 → 0, 15:00 zurück) bleibt ein Fund in Höhe des Tagesstands."""
    (s,) = finde_spruenge("sensor.pv_tagesertrag", _tagesertrag([1.5, 2.0, 2.0, 2.0], glitch_tag=2))
    assert datetime.fromtimestamp(s.rueckkehr_ts) == T0 + timedelta(days=2, hours=15)
    assert s.menge_kwh == pytest.approx(2.0)


async def test_checker_nennt_stunde_sensor_menge_und_den_weg_in_ha(db):
    a = Anlage(anlagenname="N-586", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key="basis:pv_gesamt", einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    z = _reihe(48, reset_bei=20, rueckkehr_bei=23)
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=z[0][0] - 3600, familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.pv_gesamt", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ts, state=st, sum=su, familie=FAMILIE_SPIEGEL)
                for ts, st, su in z])
    await db.commit()

    class _Pruefer(HaZaehlersprungChecks):
        def __init__(self, db):
            self.db = db

    (e,) = await _Pruefer(db)._check_ha_zaehlersprung(a, jetzt=JETZT)
    assert e.kategorie == CheckKategorie.HA_ZAEHLERSPRUNG.value
    assert "sensor.pv_gesamt" in e.details and "Stunde ab 23:00" in e.details
    assert "Wert anpassen" in e.details and "Monatsabschluss neu" in e.details
    # Der Knopf zeigt nicht auf eedcs Datenquellen (Lab 4.1.3-rc1: dort ist nichts falsch), sondern auf die
    # Energieprofil-Pflege mit „HA-Spiegel jetzt abgleichen" — dem Schritt nach der Korrektur in HA (#429).
    from backend.services.daten_checker.kategorien import LINK_DATENQUELLEN, LINK_ENERGIEPROFIL
    assert e.link == LINK_ENERGIEPROFIL
    assert e.link != LINK_DATENQUELLEN
    assert "HA-Spiegel jetzt abgleichen" in e.details
    # Außerhalb des Fensters (30 Tage) kein Befund.
    assert await _Pruefer(db)._check_ha_zaehlersprung(a, jetzt=JETZT + timedelta(days=60)) == []


async def test_der_volle_checklauf_ruft_die_pruefung(db, monkeypatch):
    """Die Prüfung hängt im Lauf von ``DatenChecker.check_anlage`` — sonst sähe sie der Anwender nie (F-21)."""
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker.kategorien import CheckErgebnis, CheckSeverity

    a = Anlage(anlagenname="N-586 Lauf", leistung_kwp=10.0)
    db.add(a)
    await db.commit()
    marke = CheckErgebnis(kategorie=CheckKategorie.HA_ZAEHLERSPRUNG.value, schwere=CheckSeverity.WARNING,
                          meldung="Marke")

    async def _attrappe(self, anlage, jetzt=None):
        return [marke]

    monkeypatch.setattr(HaZaehlersprungChecks, "_check_ha_zaehlersprung", _attrappe)
    erg = await DatenChecker(db).check_anlage(a.id)
    assert any(e.meldung == "Marke" for e in erg.ergebnisse)
