"""N-639 — Daten-Checker „Zählerstände – Rückgang in Home Assistant" (Melder Frank85, PN 08.10.2026).

Seit E4a-2 liest eedc den Spiegel der HA-Statistik ohne Rücksprung-Verwurf, wie das HA-Energie-Dashboard: fällt HAs
``sum``, steht die Stunde negativ in Tag und Monat. Der Checker benennt das — über den GANZEN Spiegel (ein Rückgang
vor 16 Monaten trifft „Aus HA laden" genauso), je Sensor und Tag, mit Menge und dem Weg in HA. Abgrenzung: ein
Phantomsprung (``ha_sprung``, ``sum`` steigt) und ein täglich zurückgesetzter Helfer (``state`` fällt, ``sum`` nicht)
sind kein Rückgang. Keine Probe liest die Uhr: die Prüfung hat kein Zeitfenster."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.models.anlage import Anlage
from backend.models.kanal import (
    ART_SUM,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalQuelle,
    KanalStatistik,
)
from backend.services.daten_checker.datenquelle.ha_rueckgang import HaRueckgangChecks, gruppiere, tag_der_zeile
from backend.services.daten_checker.datenquelle.ha_sprung import HaZaehlersprungChecks
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity

#: Frank85: Netzbezug am 05.06.2025 rund −540 kWh — 16 Monate vor der Meldung (08.10.2026).
T0 = datetime(2025, 5, 20, 0)
RUECKGANG_STUNDE = datetime(2025, 6, 5, 14)
STUNDEN = 24 * 30


class _Pruefer(HaRueckgangChecks, HaZaehlersprungChecks):
    def __init__(self, db):
        self.db = db


def _ts(t: datetime) -> int:
    return int(t.timestamp())


def _reihe(*, rueckgaenge: dict | None = None, rate: float = 0.4, start: float = 1000.0, stunden: int = STUNDEN,
           t0: datetime = T0):
    """``(start_ts, state, sum)`` je Stunde wie HA für einen fortlaufenden Zähler. ``rueckgaenge``: ``{Stunde: kWh}``
    — HA bucht in dieser Stunde eine Abnahme (``sum`` und ``state`` fallen um die Menge, z. B. „Wert anpassen" mit
    falschem Vorzeichen)."""
    out, stand, summe = [], start, 0.0
    for h in range(stunden):
        t = t0 + timedelta(hours=h)
        menge = -(rueckgaenge or {}).get(t, 0.0) if (rueckgaenge or {}).get(t) else rate
        stand += menge
        summe += menge
        out.append((_ts(t), stand, summe))
    return out


async def _anlage(db, name="N-639"):
    a = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    return a


async def _kanal(db, a, key, sid, zeilen, *, familie=FAMILIE_SPIEGEL, gueltig_ab=None, offset=0.0, quellen=None):
    k = Kanal(anlage_id=a.id, key=key, einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    for q in quellen or [(gueltig_ab if gueltig_ab is not None else zeilen[0][0] - 3600, familie, sid, offset)]:
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=q[0], familie=q[1], statistic_id=q[2], offset=q[3]))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ts, state=st, sum=su, familie=familie)
                for ts, st, su in zeilen])
    await db.commit()
    return k


async def test_ein_rueckgang_vor_16_monaten_ist_genau_eine_meldung_mit_menge_und_datum(db):
    """Der Minimalfall nach Frank: ein Kanal, eine Stunde mit −540 kWh am 05.06.2025."""
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _reihe(rueckgaenge={RUECKGANG_STUNDE: 540.0}))

    (e,) = await _Pruefer(db)._check_ha_rueckgang(a)
    assert e.kategorie == CheckKategorie.HA_ZAEHLER_RUECKGANG.value
    assert e.schwere == CheckSeverity.WARNING
    assert e.meldung.startswith("1 Tag(e) mit Rückgang")
    assert "sensor.netzbezug am 05.06.2025: −540,0 kWh (Stunde ab 14:00)" in e.details
    assert "Wert anpassen" in e.details and "nächtlichen Abgleich" in e.details
    assert "Monatsabschluss neu" in e.details
    # Kein „Beheben"-Knopf: die Korrektur liegt in HA (wie N-586, Lab 4.1.3-rc1).
    assert e.link is None


async def test_ohne_rueckgang_keine_meldung(db):
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _reihe())
    assert await _Pruefer(db)._check_ha_rueckgang(a) == []


def _phantom():
    """Wie ``test_n586_checker_ha_zaehlersprung._reihe``: Sensor meldet drei Stunden 0, kehrt zurück, HA bucht die
    Rückkehr als Zuwachs (Reset = neuer Zyklus ab 0)."""
    out, stand, summe, zuvor = [], 5000.0, 0.0, 5000.0
    t0 = datetime(2026, 6, 10, 0)
    for h in range(48):
        stand += 1.0
        st = 0.0 if 20 <= h < 23 else stand
        summe += (st - zuvor) if st >= zuvor else st
        zuvor = st
        out.append((_ts(t0 + timedelta(hours=h)), st, summe))
    return out


async def test_ein_phantomsprung_ist_kein_rueckgang(db):
    """Abgrenzung zu ``ha_sprung``: dort fällt ``state``, ``sum`` springt nach OBEN — diese Prüfung schweigt, die
    Schwester meldet ihn (Gegenprobe: das Muster ist wirklich eines)."""
    a = await _anlage(db)
    z = _phantom()
    await _kanal(db, a, "basis:pv_gesamt", "sensor.pv_gesamt", z)
    assert await _Pruefer(db)._check_ha_rueckgang(a) == []
    (s,) = await _Pruefer(db)._check_ha_zaehlersprung(a, jetzt=datetime(2026, 6, 20))
    assert s.kategorie == CheckKategorie.HA_ZAEHLERSPRUNG.value


async def test_ein_taeglich_zurueckgesetzter_helfer_ist_kein_rueckgang(db):
    """utility_meter mit Tageszyklus: ``state`` fällt jede Nacht auf 0, HAs ``sum`` zählt weiter."""
    out, summe, zuvor = [], 0.0, 0.0
    for h in range(24 * 5):
        t = T0 + timedelta(hours=h)
        st = float(sum(1 for x in range(8, 18) if x <= t.hour)) if t.hour else 0.0
        summe += st - zuvor if st >= zuvor else st
        zuvor = st
        out.append((_ts(t), st, summe))
    assert any(b[1] < a[1] for a, b in zip(out, out[1:])), "die Gegenprobe braucht einen fallenden Stand"
    a = await _anlage(db)
    await _kanal(db, a, "inv:1:pv_erzeugung_kwh", "sensor.helfer_heute", out)
    assert await _Pruefer(db)._check_ha_rueckgang(a) == []


async def test_ein_sensortausch_mit_offset_ist_kein_rueckgang(db):
    """Die Kanal-Summe ist ``sum + offset`` der geltenden Quelle (``lesen.py``): der neue Sensor beginnt in HA bei
    ``sum`` 0, der ``offset`` hält den Kanal stetig. Wer die Quelle der Zeile nicht auflöst, meldete hier −39,6 kWh."""
    a = await _anlage(db)
    alt = _reihe(stunden=100)
    t_neu = T0 + timedelta(hours=100)
    neu = _reihe(stunden=100, t0=t_neu, start=0.0)   # neuer Zähler: state und sum ab 0
    letzter = alt[-1][2]
    await _kanal(db, a, "basis:netzbezug", "sensor.alt", alt + neu, quellen=[
        (alt[0][0] - 3600, FAMILIE_SPIEGEL, "sensor.alt", 0.0),
        (_ts(t_neu), FAMILIE_SPIEGEL, "sensor.neu", letzter),
    ])
    assert await _Pruefer(db)._check_ha_rueckgang(a) == []


async def test_nur_der_spiegel_zaehlt(db):
    """Eine Abnahme in einem Kanal, dessen Quelle die MQTT-Mitschrift ist, ist keine HA-Statistik."""
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "netzbezug", _reihe(rueckgaenge={RUECKGANG_STUNDE: 540.0}),
                 familie=FAMILIE_MITSCHRIFT)
    assert await _Pruefer(db)._check_ha_rueckgang(a) == []


async def test_je_sensor_und_tag_eine_zeile_groesste_zuerst(db):
    """Zwei Stunden am selben Tag ⇒ eine Zeile mit der Summe; ein zweiter Sensor am Vortag ⇒ eine zweite."""
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _reihe(rueckgaenge={
        RUECKGANG_STUNDE: 500.0, RUECKGANG_STUNDE + timedelta(hours=2): 40.0}))
    await _kanal(db, a, "basis:einspeisung", "sensor.einspeisung", _reihe(rueckgaenge={
        datetime(2025, 6, 4, 9): 39.9}, rate=0.1))

    (e,) = await _Pruefer(db)._check_ha_rueckgang(a)
    assert e.meldung.startswith("2 Tag(e)")
    assert ("sensor.netzbezug am 05.06.2025: −540,0 kWh (2 Stunden, die größte ab 14:00); "
            "sensor.einspeisung am 04.06.2025: −39,9 kWh (Stunde ab 09:00)") in e.details


async def test_die_stunde_ab_23_uhr_zaehlt_zum_folgetag(db):
    """Tagesfenster des Bestands ``[Vortag 23:00, 23:00)`` (``kanal/fenster.tagesfenster``): die Zeile 04.06. 23:00
    steht in Cockpit → Tag am 05.06. — dort nennt sie die Meldung, die Stunde für HA mit vollem Datum."""
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _reihe(rueckgaenge={datetime(2025, 6, 4, 23): 12.0}))
    (e,) = await _Pruefer(db)._check_ha_rueckgang(a)
    assert "sensor.netzbezug am 05.06.2025: −12,0 kWh (Stunde ab 04.06.2025 23:00)" in e.details


def test_gruppiere_und_tag_der_zeile_rein():
    ts = _ts(datetime(2025, 6, 5, 14))
    (r,) = gruppiere([("sensor.x", ts, -1.5), ("sensor.x", ts + 3600, -0.5)])
    assert (r.statistic_id, r.tag.isoformat(), r.menge_kwh, r.groesste_stunde) == ("sensor.x", "2025-06-05", 2.0, ts)
    assert tag_der_zeile(_ts(datetime(2025, 6, 4, 22))).isoformat() == "2025-06-04"
    assert tag_der_zeile(_ts(datetime(2025, 6, 4, 23))).isoformat() == "2025-06-05"


async def test_eine_kleine_abnahme_hat_drei_nachkommastellen(db):
    """Ein ``total``-Sensor mit Messrauschen (−0,004 kWh) — eedc rechnet ihn mit, also nennt der Checker ihn, und zwar
    nicht als „−0,0"."""
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _reihe(rueckgaenge={RUECKGANG_STUNDE: 0.004}))
    (e,) = await _Pruefer(db)._check_ha_rueckgang(a)
    assert "−0,004 kWh" in e.details


@pytest.mark.parametrize("menge", [1e-7, 5e-7])
async def test_rundungsrauschen_unter_der_toleranz_ist_keiner(db, menge):
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _reihe(rueckgaenge={RUECKGANG_STUNDE: menge}))
    assert await _Pruefer(db)._check_ha_rueckgang(a) == []


async def test_der_volle_checklauf_ruft_die_pruefung(db, monkeypatch):
    """Die Prüfung hängt im Lauf von ``DatenChecker.check_anlage`` — sonst sähe sie der Anwender nie (F-21)."""
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker.kategorien import CheckErgebnis

    a = await _anlage(db, "N-639 Lauf")
    await db.commit()
    marke = CheckErgebnis(kategorie=CheckKategorie.HA_ZAEHLER_RUECKGANG.value, schwere=CheckSeverity.WARNING,
                          meldung="Marke N-639")

    async def _attrappe(self, anlage):
        return [marke]

    monkeypatch.setattr(HaRueckgangChecks, "_check_ha_rueckgang", _attrappe)
    erg = await DatenChecker(db).check_anlage(a.id)
    assert any(e.meldung == "Marke N-639" for e in erg.ergebnisse)
