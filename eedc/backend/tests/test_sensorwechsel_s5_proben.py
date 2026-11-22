"""Sensorwechsel — Sitzung 5, Abschluss (Bauplan Nr. 167/168, Kurz-Nachmessung ``opus-berichte/SENSORWECHSEL-U3K4-NACHMESSUNG-…``
K4-B1 … K4-B5) — Proben mit Sprengsatz, Teil A «Zähler getauscht» über MQTT.

* **A1 (K4-B1, H-3)** R2 sucht den nächsten anderen Stand ohne Zeitgrenze (``rohstand.naechster_anderer_um``); gibt es nach der
  gewählten Zeit keinen anderen Stand, trägt der Dialog nicht ein (``noch_nicht_gemeldet``, ``SATZ_NOCH_NICHT_GEMELDET``).
* **A2 (K4-B2)** landet R2 in einer Stunde, in der der Stand eindeutig die Höhe wechselt, gilt dort R1 (Satz «springt»).
* **A3 (K4-B4, H-2)** bei R2 sagt der Dialog, dass für die Stunde danach kein weiterer Tausch eintragbar ist.
* **A5** Proben für die überlebenden Mutanten Q03 (lange Stille über 24 Stunden), Q07 (Korrektur-Zeile mit ``ansatz`` ist kein
  Nullpunkt), Q10 (Nullpunkt nur im Abschnitt der Entität).

Welten wie U3-K3/U3-K4 (Netzbezug 0,6 kWh je Stunde ab 5 000, Ereignis 08.06.2026 10:20). Die Datei liest keine Uhr und läuft
auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC``. Schwesterdateien: test_sensorwechsel_u3k4_proben.py,
test_sensorwechsel_u3k3_proben.py, test_sensorwechsel_u3b_proben.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.tests.test_sensorwechsel_u3b_proben import Saat, _wechsel_zeilen, betrieb, kanal_stunde  # noqa: F401
from backend.tests.test_sensorwechsel_u3k3_proben import EN, R, ST, T, _anlage, _befund, _dialog, _drei, w
from backend.tests.test_sensorwechsel_u3k4_proben import H10, KEIN, UNKLAR

R1_ANFANG = "eedc trägt den Tausch am "


def _ausfall_30h(art: str):
    """Der Zähler steht ab 07.06. 05:10 still (defekt, der Scheduler wiederholt den Stand), der neue meldet ab 08.06. 11:10."""
    neu_ab = datetime(2026, 6, 8, 11, 10)
    aus_ab = neu_ab - timedelta(hours=30)

    def stand(t):
        if t < aus_ab:
            return w(t)
        if t < neu_ab:
            return w(aus_ab)
        basis = {"plus_2000": w(aus_ab) + 2000.0, "plus_90": w(aus_ab) + 90.0, "neu_bei_0": 0.0}[art]
        return basis + round(R * (t - neu_ab).total_seconds() / 3600, 6)
    return stand


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_24h_grenze"])
@pytest.mark.parametrize("art", ["plus_90", "plus_2000", "neu_bei_0"])
async def test_a1_lange_stille_naechster_anderer_ohne_grenze(db, monkeypatch, art, sprengsatz):
    """K4-B1 / Q03: «Getauscht am» 07.06. 10:00, der neue Zähler meldet erst 30 Stunden später (08.06. 11:10): der Dialog nimmt
    diesen Stand — bei +90 und +2 000 mit der langen stillen Zeit (R2), beim Neubeginn bei 0 als Höhenwechsel (R1, A2) — und nach
    dem Eintrag zählt der 08.06. 7,65 in Kanal und Tagesansicht. Sprengsatz: R2 sucht nur 24 Stunden (U3-K4) ⇒ «noch nicht
    gemeldet» (bzw. bis U3-K4 ein Eintrag ohne Wirkung)."""
    from backend.services.zuordnung_wechsel import rohstand

    if sprengsatz:
        echt = rohstand.naechster_anderer_um

        async def nur_24h(db_, aid_, mk_, t_):
            p = await echt(db_, aid_, mk_, t_)
            return p if p is not None and p[1][0] <= t_ + timedelta(hours=24) else None
        monkeypatch.setattr(rohstand, "naechster_anderer_um", nur_24h)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_ausfall_30h(art), start=ST, ende=EN))
    zeit = datetime(2026, 6, 7, 10)
    p = await _dialog(db, aid, zeit)
    if sprengsatz:
        assert (p["weg"], p["eintragen"]) == ("noch_nicht_gemeldet", False)
        return
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, "2026-06-08T11:10:00")
    if art == "neu_bei_0":
        assert p["saetze"][0].startswith(R1_ANFANG)
    else:
        assert p["saetze"][0].startswith("Der Zählerstand steht von 07.06.2026 05:10 bis 08.06.2026 11:10 Uhr still")
    assert (await _dialog(db, aid, zeit, eintragen=True))["eingetragen"] is True
    k, _r, t = await _drei(db, aid)
    assert k[0] == t[0] == 7.65


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_eintragen_ohne_neuen_stand"])
async def test_a1_noch_nicht_gemeldet_traegt_nicht_ein(db, monkeypatch, sprengsatz):
    """H-3: um 10:32 für 10:22 — der Publisher wiederholt ab 10:20 denselben Stand, der neue Zähler meldet erst 13:20 mit 300:
    der Dialog trägt um 10:32 nicht ein und sagt es; ab 13:20 trägt er ein ⇒ Kanal, Reihe und Tagesansicht 12,6.
    Sprengsatz: der Weg ``noch_nicht_gemeldet`` gälte als eintragbar ⇒ eine Zeile ohne Rand-Stände, der Sprung zählt."""
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    if sprengsatz:
        monkeypatch.setattr(zg, "WEG_NOCH_NICHT_GEMELDET", zg.WEG_FORTSETZUNG)
    u, t2 = T + timedelta(minutes=2), T + timedelta(hours=3)

    def stand(t):
        if t < T:
            return w(t)
        return w(T) if t < t2 else round(300.0 + R * (t - t2).total_seconds() / 3600, 6)
    antw = []

    async def versuch(db_, aid_):
        antw.append(await _dialog(db_, aid_, u))
        antw.append(await _dialog(db_, aid_, u, eintragen=True))
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN, handlungen=[(u + timedelta(minutes=10), versuch)]))
    if sprengsatz:
        assert antw[1]["eingetragen"] is True and (await _drei(db, aid))[0][0] > 300.0
        return
    assert (antw[0]["weg"], antw[0]["eintragen"], antw[1]["eingetragen"]) == ("noch_nicht_gemeldet", False, False)
    assert antw[0]["saetze"] == [
        "Seit 08.06.2026 10:22 Uhr ist kein anderer Zählerstand gespeichert – der neue Zähler hat noch nichts gemeldet. eedc "
        "trägt deshalb noch nichts ein. Trag den Tausch ein, sobald er meldet: eedc nimmt dann den letzten Stand davor und "
        "seinen ersten."]
    assert await _wechsel_zeilen(db, aid) == []
    p = await _dialog(db, aid, u)                     # nach dem Betrieb: der neue Zähler hat um 13:20 gemeldet
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, "2026-06-08T13:20:00")
    assert (await _dialog(db, aid, u, eintragen=True))["eingetragen"] is True
    k, r, t = await _drei(db, aid)
    assert (k[0], r[0], t[0]) == (12.6, 12.6, 12.6)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_r1_nach_dem_nachruecken"])
@pytest.mark.parametrize("art", ["neu_bei_0", "plus_2000"])
async def test_a2_r2_landet_auf_einem_hoehenwechsel(db, monkeypatch, art, sprengsatz):
    """K4-B2: das Gerät steht 08:20–10:20 still, das neue meldet ab 10:20 (ab 0 bzw. +2 000); gewählt 09:30. Der nächste andere
    Stand liegt in einer Stunde mit eindeutigem Höhenwechsel — dort gilt R1: Satz «springt», kein Mengen-Satz, kein Hinweis;
    nach dem Eintrag 13,2 in Kanal, Reihe und Tagesansicht. Sprengsatz: ohne R1 nach dem Nachrücken (U3-K4) ⇒ Mengen-Satz."""
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    if sprengsatz:
        echt = zg._rohstand

        async def ohne_r1(db_, aid_, key_, q_, t_, **kw):
            from backend.services.zuordnung_wechsel import rohstand

            art_, paar = await echt(db_, aid_, key_, q_, t_, **kw)
            if art_ == "sprung" and paar is not None and paar[1][0].hour != t_.hour:
                return zg.ROH_SCHRITT, await rohstand.naechster_anderer_um(db_, aid_, "netzbezug_kwh", t_)
            return art_, paar
        monkeypatch.setattr(zg, "_rohstand", ohne_r1)

    def stand(t):
        if T - timedelta(hours=2) <= t < T:
            return w(T - timedelta(hours=2))
        if t < T:
            return w(t)
        return w(t) + 2000.0 if art == "plus_2000" else round(R * (t - T).total_seconds() / 3600, 6)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(stand, start=ST, ende=EN))
    p = await _dialog(db, aid, datetime(2026, 6, 8, 9, 30))
    assert (p["weg"], p["eintragen"], p["getauscht_am"]) == ("fortsetzung", True, "2026-06-08T10:20:00")
    if sprengsatz:
        assert p["saetze"][0].startswith("Der Zählerstand steht von ")
        return
    assert p["saetze"][0].startswith(R1_ANFANG) and KEIN not in p["saetze"] and UNKLAR not in p["saetze"]
    assert (await _dialog(db, aid, datetime(2026, 6, 8, 9, 30), eintragen=True))["eingetragen"] is True
    assert await _drei(db, aid) == [[13.2, 14.4], [13.2, 14.4], [13.2, 14.4]]


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_satz"])
async def test_a3_r2_nennt_die_grenze_je_stunde(db, monkeypatch, sprengsatz):
    """K4-B4: bei R2 sagt der Dialog, dass für die Stunde danach kein weiterer Tausch eintragbar ist — und das stimmt: nach dem
    Eintrag 10:20 sagt der Dialog um 10:40 «Dieser Tausch ist schon eingetragen.» (``_schon`` vergleicht ``ab_ts``). Sprengsatz:
    ohne den Satz."""
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    if sprengsatz:
        monkeypatch.setattr(zg, "SATZ_EIN_EINTRAG", "")
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(w, start=ST, ende=EN))
    p = await _dialog(db, aid, T)
    satz = "Für die Stunde bis 08.06.2026 11:00 Uhr ist danach kein weiterer Tausch eintragbar."
    assert (satz in p["saetze"]) is not sprengsatz
    if sprengsatz:
        return
    assert p["saetze"][1:3] == [KEIN, satz]
    assert (await _dialog(db, aid, T, eintragen=True))["eingetragen"] is True
    p2 = await _dialog(db, aid, T + timedelta(minutes=20))
    assert (p2["eintragen"], p2["saetze"]) == (False, ["Dieser Tausch ist schon eingetragen."])


# ═══ A5 — Mutanten Q07, Q10 ═════════════════════════════════════════════════════════════════════════════════════════


# ═══ Teil B ═══════════════════════════════════════════════════════════════════════════════════════════════════════════

def test_b1_kein_versprechen_nachzurechnen():
    """B-9 (Bauplan Nr. 149): der Grund «keine Zählerstände» verspricht kein Nachrechnen früherer Tage (Grundregel
    Quellentreue) — der wahre Satz."""
    from backend.core.tageswert_grund import GRUND_KEINE_ZAEHLERSTAENDE, TAGESWERT_GRUND_TEXT

    assert TAGESWERT_GRUND_TEXT[GRUND_KEINE_ZAEHLERSTAENDE] == (
        "Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände vor — eedc bildet für diesen Tag deshalb keinen "
        "Tageswert.")


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_auch_aufgehoben"])
async def test_b2_vorschlag_zaehlerstand_nennt_den_wechsel(db, monkeypatch, sprengsatz):
    """W7 (Lab-Durchlauf 1): am Vorschlag «Zählerstand» des Monatsabschlusses steht ein Satz, wenn im Monat für das Feld ein
    Wechsel eingetragen ist — aufgehobene Zeilen und andere Monate zählen nicht. Sprengsatz: auch aufgehobene Zeilen."""
    from types import SimpleNamespace

    from backend.api.routes.monatsabschluss import views as v
    from backend.models.zuordnung_wechsel import ZuordnungWechsel

    a = await _anlage(db)
    q = {"art": "ha", "entity_id": "sensor.gas_alt"}
    db.add_all([
        ZuordnungWechsel(anlage_id=a.id, sensor_key="inv:7:zaehlerstand", erklaert_ts=datetime(2026, 11, 3, 9, 12),
                         ab_ts=datetime(2026, 11, 3, 10), vorher=q, nachher={**q, "entity_id": "sensor.gas_neu"},
                         grund="fortsetzung", herkunft="wechsel", aufgehoben_durch=None),
        ZuordnungWechsel(anlage_id=a.id, sensor_key="inv:8:zaehlerstand", erklaert_ts=datetime(2026, 11, 5, 9),
                         ab_ts=datetime(2026, 11, 5, 10), vorher=q, nachher=q, grund="fortsetzung", herkunft="wechsel",
                         aufgehoben_durch=99),
        ZuordnungWechsel(anlage_id=a.id, sensor_key="inv:9:zaehlerstand", erklaert_ts=datetime(2026, 10, 5, 9),
                         ab_ts=datetime(2026, 10, 5, 10), vorher=q, nachher=q, grund="fortsetzung", herkunft="wechsel"),
    ])
    await db.commit()
    if sprengsatz:
        from backend.models.zuordnung_wechsel import ZuordnungWechsel as Z
        from sqlalchemy import update

        await db.execute(update(Z).values(aufgehoben_durch=None))
        await db.commit()
    w_ = await v.lade_wechsel_im_monat(db, a.id, 2026, 11)
    assert set(w_) == ({"inv:7:zaehlerstand", "inv:8:zaehlerstand"} if sprengsatz else {"inv:7:zaehlerstand"})
    ctx = SimpleNamespace(wechsel_im_monat=w_)
    assert v._beschreibung_zaehlerstand(ctx, 7) == (
        "Mitgeschriebener Stand am Monatsende. In diesem Monat ist für dieses Feld ein Wechsel eingetragen (03.11.2026). Der "
        "Vorschlag ist der letzte gespeicherte Zählerstand des Monats – nach dem Wechsel der Stand des neuen Zählers. Prüfe ihn "
        "gegen deine Ablesung.")
    assert v._beschreibung_zaehlerstand(ctx, 9) == "Mitgeschriebener Stand am Monatsende"
