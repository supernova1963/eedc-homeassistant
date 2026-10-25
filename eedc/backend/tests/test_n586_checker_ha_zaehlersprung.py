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


def test_n764_ein_einzelner_tag_im_fenster_ist_seit_n768_kein_fund():
    """(b) Bis N-768 benannte Grenze («mit nur einer Mitternacht im Fenster ist der Tageszähler vom Glitch nicht zu
    trennen», Fund 1,5 kWh). Merkmal (B) trennt ihn: Stand 1,5 ≤ 3 × größter Tageszuwachs 1,5 (Tag 0)."""
    assert finde_spruenge("sensor.pv_tagesertrag", _tagesertrag([1.5, 2.0])) == []


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


# ── N-765 (#436): Tageszähler ohne Nachtzeilen — der Reset steht in der ersten Morgenzeile ─────────────────────

T765 = datetime(2026, 10, 6, 0)


def _tagesertrag_ohne_nacht(tage: int, *, dunkel=(1,), nachtzeilen=False):
    """PV-Tagesertrag eines nachts abgeschalteten Wechselrichters: HA schreibt nur Zeilen 07–18 (ohne Zustand keine
    Statistik), der Reset auf den neuen Tag steht in der 07:00-Zeile. Normaltag: 0,1 kWh um 07:00, je Stunde +0,8.
    ``dunkel``: Tage, die bis 14:00 auf 0,1 stehen und um 15:00 1,3 kWh erreichen (≥ 90 % des Vortags 1,4 kWh).
    ``nachtzeilen``: dieselbe Reihe mit allen 24 Zeilen (Stand 00–06 = 0, 19–23 = Tagesendstand) — N-764-Form."""
    out, summe, zuvor = [], 0.0, 0.0
    for d in range(tage):
        for h in (range(24) if nachtzeilen else range(7, 19)):
            hh = min(h, 18)
            if h < 7:
                st = 0.0
            elif d in dunkel:
                st = 0.1 if hh < 15 else (1.3 if hh == 15 else 1.4)
            else:
                st = round(0.1 + (hh - 7) * 0.8, 2)
            if d == 0 and h >= 7:
                st = min(st, 1.4)                 # Vortag 1,4 kWh
            summe += st - zuvor if st >= zuvor else st
            zuvor = st
            out.append((int((T765 + timedelta(days=d, hours=h)).timestamp()), st, summe))
    return out


def test_n765_tageszaehler_ohne_nachtzeilen_ist_kein_sprung():
    """(a) Melder-Reihe: Zeilen nur 07–18 Uhr, Vortag 1,4 kWh, Folgetag bis 14:00 auf 0,1, um 15:00 1,3 kWh —
    vier Tage, drei Tagesbeginn-Resets in der 07:00-Zeile. Bis N-765: ``[('07.10 15:00', 1.4)]``."""
    assert finde_spruenge("sensor.pv_tagesertrag", _tagesertrag_ohne_nacht(4)) == []


def test_n765_dieselbe_reihe_mit_nachtzeilen_bleibt_ohne_fund():
    """(b) N-764 bleibt: mit 00:00-Zeilen ist die 00:00-Zeile der Tagesbeginn."""
    assert finde_spruenge("sensor.pv_tagesertrag", _tagesertrag_ohne_nacht(4, nachtzeilen=True)) == []


def test_n765_ein_einzelner_tagesbeginn_reset_im_fenster_ist_seit_n768_kein_fund():
    """(c) Bis N-768 benannte Grenze (nur Vortag und dunkler Tag im Fenster ⇒ Fund 1,4 kWh um 15:00). Merkmal (B):
    Stand 1,4 ≤ 3 × größter Tageszuwachs 1,3 (Tag 0, 07–18 Uhr)."""
    assert finde_spruenge("sensor.pv_tagesertrag", _tagesertrag_ohne_nacht(2)) == []


def _lebenszeit_ohne_nacht(naechte: int, *, glitch=None):
    """Lebenszeitzähler eines nachts abgeschalteten Wechselrichters, Zeilen nur 07–22: um 22:00 meldet er 0 (die
    letzte Zeile des Abends), morgens um 07:00 steht er in EINER Zeile wieder auf dem alten Stand.
    ``glitch``: statt der Nachtresets ein Aussetzer am Tag 1 — 13:00 auf 0, 14:00 zurück."""
    out, stand, summe, zuvor = [], 5000.0, 0.0, 5000.0
    for d in range(naechte + 1):
        for h in range(7, 23):
            if h < 20:
                stand += 1.0
            if glitch:
                st = 0.0 if (d == 1 and h == 13) else stand
            else:
                st = 0.0 if (h == 22 and d < naechte) else stand
            summe += st - zuvor if st >= zuvor else st
            zuvor = st
            out.append((int((T765 + timedelta(days=d, hours=h)).timestamp()), st, summe))
    return out


def test_n765_lebenszeit_zaehler_mit_abendreset_ohne_nachtzeilen_bleibt_drei_funde():
    """(d) N-586-Muster ohne Nachtzeilen: der 22:00-Reset ist nicht die erste Zeile seines Tages — drei Nächte,
    drei Funde, jeweils mit der Rückkehr in der 07:00-Zeile."""
    funde = finde_spruenge("sensor.wr_gesamt", _lebenszeit_ohne_nacht(3))
    assert len(funde) == 3
    assert all(datetime.fromtimestamp(f.rueckkehr_ts).hour == 7 for f in funde)


def test_n765_lebenszeit_zaehler_mit_mittagsaussetzer_bleibt_ein_fund():
    """(e) Reset in der 13:00-Zeile, Rückkehr 14:00 — ein Fund in Höhe des Stands davor."""
    z = _lebenszeit_ohne_nacht(2, glitch=True)
    (s,) = finde_spruenge("sensor.wr_gesamt", z)
    assert datetime.fromtimestamp(s.rueckkehr_ts) == T765 + timedelta(days=1, hours=14)
    assert s.menge_kwh == pytest.approx(s.stand_vorher)

# ── N-768 (#436): Tageszähler an der Größe erkennen — gleich wo die 0 in der Zeilenfolge steht ───────────────────

T768 = datetime(2026, 10, 5, 0)


def _ha_summe(zeilen_state: list[tuple[datetime, float]], start_summe: float = 0.0):
    """HAs ``sum`` nach HAs Regel aus ``state``: Zuwachs = neuer − alter Stand, nach einem Rückgang = der neue Stand."""
    out, summe, zuvor = [], start_summe, None
    for t, st in zeilen_state:
        if zuvor is not None:
            summe += st - zuvor if st >= zuvor else st
        zuvor = st
        out.append((int(t.timestamp()), st, round(summe, 6)))
    return out


def _melder_436() -> list[tuple[int, float, float]]:
    """Die echten Stundenzeilen von jedema1805 (#436, 25.10.2026), ``sensor.wandpv_sud_yieldday``, Wh → kWh. Stunden, die
    der Melder nicht genannt hat, fehlen als Zeile (wie bei HA ohne Zustand). Tag 05.10. 06–11 Uhr und 07.10. aus seinen
    Kommentaren vom 24.10., 05.10. 15 Uhr bis 06.10. 07 Uhr aus der Tabelle vom 25.10. (dort mit HAs ``sum``: 339941 …
    340032 Wh). Lage: Nachtzeile 01:00 trägt noch den Vortagswert, Reset erst in der 06:00-Zeile — kein Tagesbeginn."""
    st = [(T768 + timedelta(hours=h), v) for h, v in
          [(6, 0.0), (7, 0.009), (8, 0.025), (9, 0.049), (10, 0.094), (11, 0.154),
           (15, 1.213), (16, 1.256), (17, 1.285), (18, 1.294), (19, 1.294), (22, 1.294), (23, 1.294)]]
    st += [(T768 + timedelta(days=1, hours=h), v) for h, v in
           [(1, 1.294), (6, 0.0), (7, 0.010), (8, 0.026), (9, 0.049), (14, 0.071), (15, 1.385)]]
    st += [(T768 + timedelta(days=2, hours=h), v) for h, v in
           [(6, 0.0), (7, 0.008), (8, 0.025), (9, 0.049), (14, 0.068), (15, 1.425)]]
    return _ha_summe(st, start_summe=339.941 - 1.213)


def test_n768_melder_zeilen_436_sind_kein_fund():
    """(a) Die Melder-Reihe am HEAD vor N-768: ``[('06.10 15:00', 1.294)]`` — die Warnzeile des Melders «am 06.10.2026,
    Stunde ab 15:00: +1,3 kWh (Stand 1,3 → 0,0 → zurück)». Jetzt: Stand 1,294 ≤ 3 × Tageszuwachs 1,294 ⇒ Tageszähler,
    keine 0 mit Rückkehr in der nächsten Zeile ⇒ kein Fund."""
    z = _melder_436()
    je_ts = {ts: su for ts, _st, su in z}
    # Unser HA-Modell trifft HAs echte Summen der Tabelle (Wh → kWh): 06.10. 01:00 / 06:00 / 07:00.
    assert je_ts[int((T768 + timedelta(days=1, hours=1)).timestamp())] == pytest.approx(340.022)
    assert je_ts[int((T768 + timedelta(days=1, hours=6)).timestamp())] == pytest.approx(340.022)
    assert je_ts[int((T768 + timedelta(days=1, hours=7)).timestamp())] == pytest.approx(340.032)
    assert finde_spruenge("sensor.wandpv_sud_yieldday", z) == []


def _tagesertrag_lage(tage: int, *, abend_null=(), weckwert=(), nachtzeile=()):
    """PV-Tagesertrag, Zeilen 07–18, Normaltag je Stunde +0,13 bis 1,3 kWh; Tag 3 dunkel (0,01 … 0,07) und um 15:00 1,385.
    ``abend_null``: Tage, deren 18:00-Zeile 0 trägt · ``weckwert``: Tage, deren 07:00-Zeile noch den Vortagsstand trägt ·
    ``nachtzeile``: Tage mit einer 01:00-Zeile, die den Vortagsstand trägt (Melder-Lage)."""
    st, zuvor = [], 0.0
    for d in range(tage):
        if d in nachtzeile and d > 0:
            st.append((T768 + timedelta(days=d, hours=1), zuvor))
        for h in range(7, 19):
            if d == 3:
                v = round(0.01 * (h - 6), 3) if h < 15 else (1.385 if h == 15 else 1.45)
            else:
                v = min(round((h - 7) * 0.13, 3), 1.3)
            if h == 7 and d in weckwert and d > 0:
                v = zuvor
            if h == 18 and d in abend_null:
                v = 0.0
            st.append((T768 + timedelta(days=d, hours=h), v))
            zuvor = v
    return _ha_summe(st)


@pytest.mark.parametrize("lage", [
    dict(abend_null=(2,)), dict(weckwert=(3,)), dict(nachtzeile=(3,)),
    dict(abend_null=(0, 1, 2, 3, 4)),           # jeden Abend 0: Merkmal (A) greift nie, (B) trägt allein
])
def test_n768_drei_zeilenlagen_der_null_am_tageszaehler_sind_kein_fund(lage):
    """(b) Bis N-768 je ``[('08.10 15:00', 1.3)]``: Abend-Null, Weckwert und Nachtzeile sind kein Tagesbeginn. Merkmal (B):
    Stand 1,3 ≤ 3 × Tageszuwachs 1,3."""
    assert finde_spruenge("sensor.pv_tag", _tagesertrag_lage(5, **lage)) == []


def test_n768_tageszaehler_ohne_lage_bleibt_ohne_fund():
    assert finde_spruenge("sensor.pv_tag", _tagesertrag_lage(5)) == []


def _gesamtzaehler_eingefroren(stand: float = 10714.0, null_zeilen: int = 1):
    """Die Lab-Form: Gesamtzähler ohne Zuwachs (PV-Prüfanlage, eingefroren), eine Stunde 0, dann der alte Stand —
    HA bucht beim Zurückkehren den ganzen Stand (Phantom = ``stand``)."""
    st = [(T768 + timedelta(hours=h), stand) for h in range(30)]
    st += [(T768 + timedelta(hours=30 + k), 0.0) for k in range(null_zeilen)]
    st += [(T768 + timedelta(hours=30 + null_zeilen + h), stand) for h in range(6)]
    return _ha_summe(st, start_summe=498.0)


def test_n768_gesamtzaehler_ohne_tageszuwachs_bleibt_ein_fund_in_hoehe_des_stands():
    """(c) Merkmal (B) am Gesamtzähler: größter Tageszuwachs 0 (ohne die Rückkehr-Zeile), Stand 10 714 ⇒ kein
    Tageszähler, Fund in Höhe des Stands — und zwar bei jeder Dauer der 0 (1 Zeile = Aussetzer, 3 Zeilen = Lücke)."""
    for null_zeilen in (1, 3):
        (s,) = finde_spruenge("sensor.eedc_lab_pv_gesamt", _gesamtzaehler_eingefroren(null_zeilen=null_zeilen))
        assert s.menge_kwh == pytest.approx(10714.0)
        assert s.stand_vorher == 10714.0 and s.stand_reset == 0.0


def test_n768_aussetzer_am_tageszaehler_in_jeder_lage_bleibt_ein_fund():
    """(d) Gegenprobe: ein Tageszähler (Merkmal A und B erfüllt), der mittags eine Zeile 0 meldet und in der nächsten
    Zeile zurück ist — HA bucht den Tag doppelt, der Fund bleibt (Höhe = Tagesstand bis dahin)."""
    z = _tagesertrag_lage(5)
    # Tag 1, 17:00 → 0 (Stand davor 1,17 ≥ MIN_STAND_KWH), 18:00 zurück auf 1,3
    idx = {ts: k for k, (ts, _s, _u) in enumerate(z)}
    k = idx[int((T768 + timedelta(days=1, hours=17)).timestamp())]
    st = [(datetime.fromtimestamp(ts), s) for ts, s, _u in z]
    st[k] = (st[k][0], 0.0)
    (s,) = finde_spruenge("sensor.pv_tag", _ha_summe(st))
    assert datetime.fromtimestamp(s.rueckkehr_ts) == T768 + timedelta(days=1, hours=18)
    assert s.stand_vorher == pytest.approx(1.17) and s.menge_kwh == pytest.approx(1.17)


def test_n768_benannte_grenze_aussetzer_ueber_zwei_zeilen_am_tageszaehler():
    """(e) Benannte Grenze (Handbuch §4.8b): bleibt ein Tageszähler ZWEI Zeilen auf 0 und kehrt dann zurück, ist das
    von einem Tagesbeginn nach einer Lücke nicht zu trennen — kein Fund, obwohl HA den Tag doppelt bucht (Phantom
    ≤ ein Tagesstand)."""
    z = _tagesertrag_lage(5)
    st = [(datetime.fromtimestamp(ts), s) for ts, s, _u in z]
    idx = {t: k for k, (t, _s) in enumerate(st)}
    for h in (16, 17):
        k = idx[T768 + timedelta(days=1, hours=h)]
        st[k] = (st[k][0], 0.0)
    assert finde_spruenge("sensor.pv_tag", _ha_summe(st)) == []


def test_n768_benannte_grenze_junger_gesamtzaehler_mit_nachtnullen():
    """(f) Benannte Grenze: ein Gesamtzähler mit zwei Tagen Historie (Stand 26 ≤ 3 × Tageszuwachs 13), dessen
    Nachtzeilen 22–05 Uhr 0 tragen — die Rückkehr um 06:00 folgt nicht unmittelbar auf den Reset ⇒ kein Fund
    (Phantom ≤ drei Tage). Derselbe Zähler mit 5 000 kWh Stand: Fund (N-764-Probe c)."""
    st, stand = [], 0.0
    for h in range(24 * 3):
        t = T768 + timedelta(hours=h)
        if 7 <= t.hour < 20:
            stand += 1.0
        aus = 22 <= t.hour or t.hour < 6
        st.append((t, 0.0 if aus and h > 20 else stand))
    assert finde_spruenge("sensor.wr_jung", _ha_summe(st)) == []



#: Echte HA-Stundenzeilen aus dem HAOS-Lab (25.10.2026, `sensor.eedc_lab_pv_gesamt`, Gesamtzähler eingefroren bei 10 714 kWh):
#: 13:04 per MQTT auf 0 gesetzt, 14:05 zurück (`lab-werkzeug/ha-sprung/sprung_lab.py`). HA bucht beim Zurückkehren den
#: ganzen Stand: ``sum`` 498 → 11 212. Epoch-Sekunden, damit die Probe in jeder Prozesszeitzone dieselben Zeilen liest.
LAB_DOPPELBUCHUNG = [
    (1792908000, 10714.0, 498.0), (1792911600, 10714.0, 498.0), (1792915200, 10714.0, 498.0),
    (1792918800, 10714.0, 498.0), (1792922400, 10714.0, 498.0), (1792926000, 10714.0, 498.0),
    (1792929600, 0.0, 498.0), (1792933200, 10714.0, 11212.0),
]


def test_n768_echte_ha_doppelbuchung_aus_dem_lab_bleibt_ein_fund():
    """(g) Die Gegenseite mit echten HA-Zeilen: HAs ``sum`` springt in der Rückkehr-Zeile um den ganzen Stand (10 714 kWh,
    nicht nachgestellt, sondern vom Recorder des Lab-HA geschrieben). Größter Tageszuwachs 0 ⇒ Gesamtzähler ⇒ Fund in
    Höhe des Stands, Rückkehr-Zeile = die 14:00-Zeile."""
    (s,) = finde_spruenge("sensor.eedc_lab_pv_gesamt", LAB_DOPPELBUCHUNG)
    assert s.rueckkehr_ts == 1792933200
    assert s.menge_kwh == pytest.approx(10714.0)
    assert s.stand_vorher == 10714.0 and s.stand_reset == 0.0
    # Unser HA-Modell (``_ha_summe``) liefert für dieselben Stände dieselbe Summe wie der echte Recorder.
    modell = _ha_summe([(datetime.fromtimestamp(ts), st) for ts, st, _su in LAB_DOPPELBUCHUNG], start_summe=498.0)
    assert [su for _ts, _st, su in modell] == [su for _ts, _st, su in LAB_DOPPELBUCHUNG]


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
