"""N-544 — eine Achse, backward, und jede Zeitangabe sagt, was sie meint.

**Was falsch war.** Die Slot-Achse des HA-Export-Fensterkontexts lag **forward**
(Slot 0 = heute 00–01 Uhr), weil ihr Hauptlieferant — die Börsenreihe
`rang_profil` — forward beschriftet ist. Alles andere auf derselben Achse ist
backward (#144): die PV-Stundenreihe des Kanons, das Verbrauchsprofil von
Modell A, die Temperaturreihe, das Tagesprofil in der Datenbank. Zwei Folgen:

* **Der Preis einer Stunde wurde gegen den Überschuss der Nachbarstunde
  verrechnet.** Ein Fenster „ab 13 Uhr" konnte auf dem Preis von 13–14 Uhr und
  dem Überschuss von 12–13 Uhr stehen.
* **Fünf Zeitangaben waren um eine Stunde verschoben** — vier zu spät (E2
  `seit`, E5 `stunde_max_mittel`, P2 `fenster[].ab/bis`, P7
  `guenstige_heizstunden`), eine voraus (E1 `stand`, die die noch leere Zeile
  der laufenden Stunde las).

**Die Regel, die daraus folgt, gilt der Kategorie *Zeitangabe eines Slots*, nicht
den einzelnen Attributen:** Beginn-Angaben sind `ab` · `seit` · `stunden` ·
`stunde_von`, End-Angaben sind `bis` · `*_um` · `frist` · `stand` ·
`stunde_bis`. Ein `stunde: "14:00"` ohne diese Unterscheidung ist nicht
entscheidbar und deshalb entfallen.

⛔ **Kein Netz, keine echte Uhr.** Jede Probe stellt `jetzt` als Parameter
(N-167) und baut ihre Reihen selbst.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.core.berechnungen.slot_konvention import forward_stunde_zu_backward_slot
from backend.services.ha_export_fenster import SLOTS_JE_TAG, baue_fenster_kontext

HEUTE = date(2026, 9, 22)


# ── Bausteine ───────────────────────────────────────────────────────────────

def _preis(stunden_preise: dict[int, float], *, morgen: bool = False,
           guenstig_ab: float = 15.0) -> dict:
    """Ein Preis-Dict mit **forward** beschrifteten Börsenstunden."""
    def _profil(werte):
        return [
            {"stunde": h, "preis_cent": werte.get(h, 30.0),
             "unter_schwelle": werte.get(h, 30.0) < guenstig_ab}
            for h in range(24)
        ]

    out = {"rang_profil": _profil(stunden_preise), "guenstig_schwelle_cent": guenstig_ab}
    if morgen:
        out["rang_profil_morgen"] = _profil({})
    return out


def _prognose(*, pv=None, verbrauch=None, labels=None, temperatur=None) -> dict:
    """Ein Prognose-Dict mit **backward** indizierten Tagesreihen (Modell A + Kanon)."""
    n = 24 if labels is None else len(labels)
    return {
        "stundenprofil_heute": pv if pv is not None else [0.0] * 24,
        "verbrauch_stundenprofil_kwh": verbrauch if verbrauch is not None else [0.0] * n,
        "verbrauch_stunden_label": labels if labels is not None else list(range(24)),
        "verbrauch_temperatur_c": temperatur,
    }


# ── 1 · Die Verschiebung selbst ─────────────────────────────────────────────

def test_forward_stunde_zu_backward_slot_ist_plus_eins():
    """Der benannte SoT — und er faltet Slot 24 **nicht** zurück."""
    assert forward_stunde_zu_backward_slot(0) == 1
    assert forward_stunde_zu_backward_slot(13) == 14
    # Die Stunde [23, 24) ist Slot 0 des FOLGETAGS; ob der Aufrufer sie als
    # Slot 24 einer mehrtägigen Achse führt, ist seine Entscheidung.
    assert forward_stunde_zu_backward_slot(23) == 24


def test_preis_und_pv_derselben_physischen_stunde_landen_im_selben_slot():
    """Die Kernaussage von N-544 — die Probe, die der Achsenfehler rot machen muss.

    **Aufbau:** genau **eine** billige Börsenstunde (forward 13 = 13–14 Uhr) und
    genau **ein** Überschuss-Slot der PV-Prognose (backward 14 = 13–14 Uhr).
    Das ist dieselbe physische Stunde. Landen beide im selben Slot, ist die
    Achse richtig; auf der alten forward-Achse lagen sie in Slot 13 und 14.
    """
    ctx = baue_fenster_kontext(
        _prognose(pv=[0.0] * 14 + [5.0] + [0.0] * 9),
        _preis({13: 5.0}),
        jetzt=datetime(2026, 9, 22, 1, 0),
    )
    billigster = min(
        (i for i, p in enumerate(ctx.preis_cent) if p is not None),
        key=lambda i: ctx.preis_cent[i],
    )
    pv_slot = max(range(len(ctx.preis_cent)), key=lambda i: ctx.ueberschuss_kwh[i])
    assert billigster == pv_slot == 14
    # …und dieser Slot heißt in Klartext 13:00–14:00.
    assert ctx.slot_iso(14)[11:16] == "13:00"
    assert ctx.slot_ende_iso(14)[11:16] == "14:00"


# ── 2 · `jetzt_slot` und die Beschriftung ───────────────────────────────────

@pytest.mark.parametrize("stunde,minute,erwarteter_slot,beginn", [
    (14, 30, 15, "13:00"),   # laufende Stunde 14–15 Uhr ⇒ Slot 15, Beginn 14:00 …
    (0, 20, 1, "23:00"),     # … Slot 1 beginnt um 00:00; der Slot DAVOR ist gestern 23 Uhr
    (23, 30, 24, "22:00"),   # die letzte Stunde des Tages ist Slot 24
])
def test_jetzt_slot_ist_die_laufende_stunde(stunde, minute, erwarteter_slot, beginn):
    """`jetzt_slot` ist der Slot, in dem die Uhr gerade steht — nicht der abgelaufene."""
    ctx = baue_fenster_kontext(
        _prognose(), _preis({3: 5.0}),
        jetzt=datetime(2026, 9, 22, stunde, minute),
    )
    assert ctx.jetzt_slot == erwarteter_slot
    # Der Beginn des VORHERIGEN Slots — die Probe prüft damit zugleich, dass
    # `slot_iso` den Tagesübergang trägt (Slot 0 = gestern 23:00).
    assert ctx.slot_iso(erwarteter_slot - 1)[11:16] == beginn


def test_um_1430_beginnt_die_laufende_stunde_um_1400():
    ctx = baue_fenster_kontext(
        _prognose(), _preis({3: 5.0}), jetzt=datetime(2026, 9, 22, 14, 30),
    )
    assert ctx.slot_iso(ctx.jetzt_slot)[11:16] == "14:00"
    assert ctx.slot_ende_iso(ctx.jetzt_slot)[11:16] == "15:00"


def test_slot_25_ist_morgen_null_uhr():
    """Die Achse trägt den Tagesübergang selbst — kein Aufrufer rechnet ihn nach."""
    ctx = baue_fenster_kontext(
        _prognose(), _preis({3: 5.0}, morgen=True), jetzt=datetime(2026, 9, 22, 14, 30),
    )
    assert ctx.slot_iso(25)[:10] == "2026-09-23"
    assert ctx.slot_iso(25)[11:16] == "00:00"
    # Slot 24 gehört noch zu heute.
    assert ctx.slot_iso(24)[:10] == "2026-09-22"


# ── 3 · Die Achsenlänge ─────────────────────────────────────────────────────

def test_ohne_morgen_satz_ist_die_achse_25_slots_lang():
    """⚠ Nicht 24 — die Stunde 23–24 Uhr von heute ist Slot 24 und liegt im Rahmen.

    Auf einer 24er-Achse fiele sie heraus, und ein Fenster, das um 22 Uhr
    beginnt, wäre nicht mehr findbar.
    """
    ctx = baue_fenster_kontext(
        _prognose(), _preis({23: 5.0}), jetzt=datetime(2026, 9, 22, 20, 0),
    )
    assert len(ctx.preis_cent) == SLOTS_JE_TAG + 1 == 25
    assert ctx.preis_cent[24] == 5.0, "die Börsenstunde 23 landet in Slot 24"
    assert ctx.frist_slot == 24


def test_mit_morgen_satz_sind_es_48():
    ctx = baue_fenster_kontext(
        _prognose(), _preis({3: 5.0}, morgen=True), jetzt=datetime(2026, 9, 22, 14, 0),
    )
    assert len(ctx.preis_cent) == 2 * SLOTS_JE_TAG == 48


def test_slot_0_ist_gestern_23_uhr_und_hat_keinen_boersenpreis():
    """Die heutige Börsenreihe beginnt bei Slot 1 — Slot 0 gehört dem Vortag.

    Er bleibt hier `None`; sein Preis kommt aus dem persistierten Tagesprofil
    des Vortags und wird erst von der Bezugspreis-Reihe (S3b/B2) nachgereicht.
    Für ein Fenster „ab jetzt" ist er ohnehin nie im Rahmen.
    """
    ctx = baue_fenster_kontext(
        _prognose(), _preis({0: 5.0}), jetzt=datetime(2026, 9, 22, 1, 0),
    )
    assert ctx.preis_cent[0] is None
    assert ctx.preis_cent[1] == 5.0
    assert ctx.slot_iso(0)[:10] == "2026-09-21"
    assert ctx.slot_iso(0)[11:16] == "23:00"


# ── 4 · Modell A per Label (F-6: 23- und 25-Stunden-Tage) ───────────────────

def test_modell_a_wird_nach_label_eingeordnet_nicht_nach_position():
    """Der Normaltag — Position und Label sind gleich, das Ergebnis auch."""
    verbrauch = [round(0.1 * h, 2) for h in range(24)]
    ctx = baue_fenster_kontext(
        _prognose(verbrauch=verbrauch, labels=list(range(24))),
        _preis({3: 5.0}), jetzt=datetime(2026, 9, 22, 1, 0),
    )
    assert ctx.verbrauch_kwh[:24] == verbrauch


def test_23_stunden_tag_laesst_die_fehlende_stunde_leer():
    """Frühjahrs-Umstellung: die Stunde 2 gibt es nicht, der Tag hat 23 Einträge.

    Nach **Position** eingeordnet rutschte ab Slot 2 die ganze Reihe eine
    Stunde nach vorn. Nach Label bleibt Slot 2 auf 0 und alles andere sitzt
    richtig.
    """
    labels = [h for h in range(24) if h != 2]
    verbrauch = [float(h) for h in labels]
    ctx = baue_fenster_kontext(
        _prognose(verbrauch=verbrauch, labels=labels),
        _preis({3: 5.0}), jetzt=datetime(2026, 3, 29, 1, 0),
    )
    assert ctx.verbrauch_kwh[2] == 0.0, "die Stunde, die es nicht gibt"
    assert ctx.verbrauch_kwh[3] == 3.0, "Slot 3 trägt seinen eigenen Wert, nicht den von 4"
    assert ctx.verbrauch_kwh[23] == 23.0


def test_25_stunden_tag_die_erste_zweite_uhr_gewinnt():
    """Herbst-Umstellung: 02:00 kommt zweimal — dieselbe Regel wie bei der Börse.

    `strompreis_markt_service` lässt für die Börse die **erste** 02:00 gewinnen
    („im Frühjahr fehlt die Stunde 2 entsprechend ganz"). Eine zweite Regel an
    dieser Stelle hieße: dieselbe Stunde trägt in Preis und Verbrauch
    verschiedene Werte.
    """
    labels = list(range(3)) + [2] + list(range(3, 24))
    verbrauch = [float(i) for i in range(len(labels))]
    ctx = baue_fenster_kontext(
        _prognose(verbrauch=verbrauch, labels=labels),
        _preis({3: 5.0}), jetzt=datetime(2026, 10, 25, 1, 0),
    )
    assert len(labels) == 25
    assert ctx.verbrauch_kwh[2] == 2.0, "die ERSTE 02:00 (Position 2), nicht die zweite (Position 3)"
    assert ctx.verbrauch_kwh[3] == 4.0, "Position 4 trägt Label 3"


def test_ohne_labels_bleibt_es_bei_der_position():
    """Rückfall für ältere Prognose-Dicts — am Normaltag identisch."""
    verbrauch = [float(h) for h in range(24)]
    ctx = baue_fenster_kontext(
        {"stundenprofil_heute": [0.0] * 24, "verbrauch_stundenprofil_kwh": verbrauch},
        _preis({3: 5.0}), jetzt=datetime(2026, 9, 22, 1, 0),
    )
    assert ctx.verbrauch_kwh[:24] == verbrauch


def test_temperatur_folgt_demselben_label():
    """Sonst sucht P8 die Hitzespitze eine Stunde neben der Verbrauchsspitze."""
    labels = [h for h in range(24) if h != 2]
    temperatur = [float(h) for h in labels]
    ctx = baue_fenster_kontext(
        _prognose(labels=labels, verbrauch=[0.0] * 23, temperatur=temperatur),
        _preis({3: 5.0}), jetzt=datetime(2026, 3, 29, 1, 0),
    )
    assert ctx.temperatur_c[2] is None, "keine erfundene Temperatur für die Stunde, die fehlt"
    assert ctx.temperatur_c[3] == 3.0


# ── 5 · Die Teilzeile der laufenden Stunde (W9) ─────────────────────────────

async def _anlage_mit_teilzeile(db, *, bis_slot: int, teilzeile_slot: int):
    """Ein Tagesprofil mit Werten bis `bis_slot` und einer LEEREN Zeile darüber.

    Genau die Lage, die `live_tagesverlauf_service` + `aggregator` herstellen:
    die Zeile der laufenden Stunde existiert (der Bucket wurde angelegt), trägt
    aber keine Zählerwerte, weil `verrechne_stunde` sie ohne `pv_kw`/
    `verbrauch_kw` leer lässt.
    """
    from backend.models import Anlage, Monatsdaten
    from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

    anlage = Anlage(anlagenname="N544-Probe", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1), latitude=48.1, longitude=11.5)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=200.0))
    for h in range(bis_slot + 1):
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=HEUTE, stunde=h,
            ueberschuss_kw=2.5 if h >= 10 else 0.0,
            defizit_kw=0.0 if h >= 10 else 1.2,
            netzbezug_kw=0.0 if h >= 10 else 1.2,
            pv_kw=1.0 if h >= 8 else 0.0,
        ))
    # Die Teilzeile: angelegt, aber ohne jeden Wert.
    db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=HEUTE, stunde=teilzeile_slot))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=HEUTE,
                                ueberschuss_kwh=7.5, defizit_kwh=12.0,
                                peak_netzbezug_kw=4.8))
    await db.commit()
    return anlage


async def test_stand_und_letzte_uebergehen_die_teilzeile(db, monkeypatch):
    """`stand` nahm `zeilen[-1]` — und das war die noch leere Zeile: eine Stunde voraus.

    Aufbau: Werte bis Slot 14 (= 13–14 Uhr), die Teilzeile ist Slot 15. Richtig
    ist `stand = 14:00` (Ende von Slot 14), nicht `15:00`.
    """
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.api.routes.ha_export import anlage_sensorwerte

    anlage = await _anlage_mit_teilzeile(db, bis_slot=14, teilzeile_slot=15)

    async def _p(db_, anlage_, *, skip_jitter=False):
        return None

    async def _q(db_, anlage_):
        return None

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _p)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _q)

    werte = await calculate_anlage_sensors(
        db, anlage, skip_jitter=True, jetzt=datetime(2026, 9, 22, 14, 30),
    )
    sv = {v.definition.key: v for v in werte}

    assert sv["eedc_ueberschuss_heute_kwh"].zusatz_attribute["stand"] == "14:00"
    jetzt_kw = sv["eedc_ueberschuss_jetzt_kw"]
    assert jetzt_kw.zusatz_attribute["stunde_von"] == "13:00"
    assert jetzt_kw.zusatz_attribute["stunde_bis"] == "14:00"
    assert "stunde" not in jetzt_kw.zusatz_attribute


async def test_p6_nimmt_die_grenze_des_ist_nicht_die_uhr(db, monkeypatch):
    """SOLL und IST enden an derselben Stunde — und die sagt der Kanon.

    `ist_bisher_bis_slot` ist der höchste Slot mit Messwert. **Gemessen, wann das
    von der Uhr abweicht:** Sobald HA die eben abgelaufene LTS-Stunde
    geschrieben hat (gegen Minute ~12), endet das IST bei Slot `jetzt.hour + 1`
    — die Uhr-Summe `stundenprofil[:jetzt.hour]` dagegen eine Stunde davor. Drei
    Viertel jeder Stunde stand damit eine gemessene Stunde mehr über einer
    prognostizierten Stunde weniger.

    **Die Probe stellt genau diesen Fall:** 15:20 Uhr, IST reicht bis Slot 15
    (= 14–15 Uhr) und beträgt 8,0 kWh. Richtig ist SOLL = Slots 0…15 = 8,0 kWh
    ⇒ 0 %. Mit der Uhr als Grenze wären es Slots 0…14 = 7,0 kWh ⇒ **+14,3 %**.
    """
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.api.routes.ha_export import anlage_sensorwerte
    from backend.tests.test_s2_entscheidungs_sensoren import _prognose as _volle_prognose

    anlage = await _anlage_mit_teilzeile(db, bis_slot=14, teilzeile_slot=15)

    # SOLL: 1 kWh je Slot ab 8 — bis Slot 14 inklusive sind das 7 Stunden.
    soll = [0.0] * 8 + [1.0] * 16
    prognose = _volle_prognose(
        stundenprofil_heute=soll, ist_bisher_kwh=8.0, ist_bisher_bis_slot=15,
    )

    async def _p(db_, anlage_, *, skip_jitter=False):
        return prognose

    async def _q(db_, anlage_):
        return None

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _p)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _q)

    werte = await calculate_anlage_sensors(
        db, anlage, skip_jitter=True, jetzt=datetime(2026, 9, 22, 15, 20),
    )
    sv = {v.definition.key: v for v in werte}
    ampel = sv["eedc_prognose_abweichung_heute_prozent"]

    # Slots 0…15 ⇒ 8 Sonnenstunden ⇒ SOLL 8,0 — genau das gemessene IST.
    assert ampel.zusatz_attribute["prognose_kwh"] == pytest.approx(8.0)
    assert ampel.value == pytest.approx(0.0), (
        "mit der Uhr als Grenze (Slots 0…14) stünden hier 7,0 kWh SOLL und +14,3 %"
    )
    # End-Angabe: die letzte einbezogene Stunde (Slot 15) endet um 15:00.
    assert ampel.zusatz_attribute["bis_stunde"] == "15:00"
