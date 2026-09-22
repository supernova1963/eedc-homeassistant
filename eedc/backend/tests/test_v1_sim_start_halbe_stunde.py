"""V1 — die Speicher-Simulation des HA-Exports startet in der halb abgelaufenen Stunde.

**Der Befund (gemessen 22.09.2026).** `ha_export_prognose` startete die
Simulation bei `now.hour` und rechnete diesen Slot **ganz**. Der Startwert ist
aber `TagesEnergieProfil.soc_prozent` — ein **Stundenmittel**, also der
Ladestand etwa zur **Mitte** des zugehörigen Intervalls. Nach der
HA-Verdichtung (~:12) ist das derselbe Slot: seine erste Hälfte wurde ein
zweites Mal gerechnet. Hinkt HA nach, fehlte stattdessen eine halbe bis
mehrere ganze Stunden. Der Fehler pendelt um ±½ h und trifft
`eedc_speicher_voll_um` (seit v4.0.27 ausgeliefert), `eedc_speicher_voll_um_ts`,
`eedc_speicher_leer_um_ts` und `eedc_speicher_reicht_bis_mitternacht`.

**Zwei Umrechnungen stecken darin, und beide waren geraten:**

1. **Konvention.** `soc_prozent` liegt **forward** (N-387,
   `core/berechnungen/slot_konvention.py`): Zeile `stunde = s` trägt das Mittel
   über `[s:00, s+1:00)`. Die Simulation rechnet **backward** (Slot `h` =
   `[h-1, h)`) — dasselbe Wanduhr-Intervall heißt dort `s + 1`.
2. **Anteil.** Vom Start-Slot steht nur noch die **halbe** Stunde aus.

⚠ **Keine echte Uhr** (N-167): feste Daten, gestellte `datetime`/`date` im
Prüfling — wie die Nachbarproben in `test_ha_export_prognose_150.py`.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Optional

import pytest

from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil

#: Derselbe feste Mittwoch wie in den Nachbarproben.
_HEUTE = date(2026, 6, 17)


# ══════════════════════════════════════════════════════════════════════════
# (a) Layer — was `start_anteil` genau tut, und dass 1.0 nichts ändert
# ══════════════════════════════════════════════════════════════════════════

def _referenz_head(
    pv_stunden: list[float],
    verbrauch_stunden: list[float],
    speicher_kap: float,
    start_soc: float,
    start_stunde: int,
    wirkungsgrad_prozent: float,
) -> tuple[Optional[str], Optional[str], float, dict]:
    """Wortgleiche Kopie der Schleife aus HEAD `786483a4` — vor `start_anteil`.

    Dieselbe Bauform wie `_inline_referenz` in
    `test_speicher_simulation_bilanz.py`: Der Beweis, dass der Default nichts
    ändert, darf nicht aus derselben Funktion kommen, die er prüft.
    """
    from backend.core.berechnungen.speicher_simulation import (
        SOC_LEER_AB_STUNDE, SOC_LEER_PROZENT, SOC_VOLL_PROZENT,
    )

    soc = max(0.0, min(100.0, start_soc))
    eta = max(0.01, min(1.0, wirkungsgrad_prozent / 100.0))
    voll: Optional[str] = None
    leer: Optional[str] = None
    soc_pro_stunde: dict[int, float] = {}
    hat_speicher = speicher_kap > 0

    for h in range(max(0, start_stunde), 24):
        pv = (pv_stunden[h] if h < len(pv_stunden) else 0.0) or 0.0
        vb = (verbrauch_stunden[h] if h < len(verbrauch_stunden) else 0.0) or 0.0
        netto = pv - vb
        if hat_speicher:
            if netto > 0:
                lade_kapazitaet = (100.0 - soc) / 100.0 * speicher_kap / eta
                ladung = min(netto, lade_kapazitaet)
                soc += (ladung * eta / speicher_kap) * 100.0
                soc = min(soc, 100.0)
            else:
                entlade_kapazitaet = soc / 100.0 * speicher_kap
                entladung = min(abs(netto), entlade_kapazitaet)
                soc -= (entladung / speicher_kap) * 100.0
                soc = max(soc, 0.0)
            soc_pro_stunde[h] = round(soc, 1)
            if soc >= SOC_VOLL_PROZENT and voll is None:
                voll = f"{h:02d}:00"
            if soc <= SOC_LEER_PROZENT and leer is None and h >= SOC_LEER_AB_STUNDE:
                leer = f"{h:02d}:00"
    return voll, leer, round(soc, 1), soc_pro_stunde


_PV_TAG = [0.0] * 8 + [0.4, 1.2, 2.1, 2.8, 3.2, 3.0, 2.4, 1.6, 0.9, 0.3] + [0.0] * 6
_VB_TAG = [0.3] * 7 + [0.9, 0.6, 0.5, 0.5, 0.7, 1.1, 0.6, 0.5, 0.5, 0.8, 1.4, 1.2] + [0.6] * 5


def test_default_1_0_ist_bitgleich_zu_head():
    """Der Planungs-Tab, die Bestandsproben und der Golden Master dürfen nichts merken."""
    for start in (0, 7, 14, 23):
        for soc0 in (0.0, 12.5, 50.0, 97.0):
            for eta in (100.0, 85.0):
                neu = simuliere_speicher_tag(
                    _PV_TAG, _VB_TAG, speicher_kap_kwh=9.6,
                    start_soc_prozent=soc0, start_stunde=start,
                    wirkungsgrad_prozent=eta,
                )
                alt = _referenz_head(
                    _PV_TAG, _VB_TAG, 9.6, soc0, start, eta,
                )
                assert (
                    neu.speicher_voll_um, neu.speicher_leer_um,
                    neu.end_soc_prozent, neu.soc_pro_stunde,
                ) == alt, (
                    f"Default-Drift bei start={start}, soc={soc0}, eta={eta} — "
                    "`start_anteil=1.0` muss die Fassung von HEAD sein."
                )


def test_halber_anteil_halbiert_genau_den_start_slot():
    """0.5 halbiert den Nettofluss des Start-Slots — und nur seinen."""
    kap = 10.0
    ganz = simuliere_speicher_tag(
        _PV_TAG, _VB_TAG, speicher_kap_kwh=kap,
        start_soc_prozent=50.0, start_stunde=11, start_anteil=1.0,
    )
    halb = simuliere_speicher_tag(
        _PV_TAG, _VB_TAG, speicher_kap_kwh=kap,
        start_soc_prozent=50.0, start_stunde=11, start_anteil=0.5,
    )

    b_ganz, b_halb = ganz.stunden_bilanz, halb.stunden_bilanz
    assert [z.stunde for z in b_ganz] == [z.stunde for z in b_halb]

    # Start-Slot: PV, Verbrauch und damit das Netto exakt halbiert.
    assert b_halb[0].pv_kwh == pytest.approx(b_ganz[0].pv_kwh / 2)
    assert b_halb[0].verbrauch_kwh == pytest.approx(b_ganz[0].verbrauch_kwh / 2)
    assert b_halb[0].netto_kwh == pytest.approx(b_ganz[0].netto_kwh / 2)

    # Jeder weitere Slot geht unverändert ganz ein — nur der SoC-Pegel, auf dem
    # er aufsetzt, ist ein anderer.
    for zg, zh in zip(b_ganz[1:], b_halb[1:]):
        assert (zh.pv_kwh, zh.verbrauch_kwh, zh.netto_kwh) == (
            zg.pv_kwh, zg.verbrauch_kwh, zg.netto_kwh
        ), f"Slot {zh.stunde} wurde mitgewichtet — nur der Start-Slot darf das."


def test_handrechnung_die_verschiebung_ist_eine_halbe_stunde():
    """Die Verschiebung von „voll um" ist genau eine halbe Stunde — nachgerechnet.

    10 kWh nutzbar, η = 100 %, Start 50 % (= 5,0 kWh), PV 1 kW ab Slot 10,
    kein Verbrauch. Bis zur Voll-Schwelle (98 % = 9,8 kWh) fehlen **4,8 kWh**.

    * **Ganzer Start-Slot:** Slot 10 deckt `[09:00, 10:00)`, die Ladung läuft ab
      09:00 → 4,8 kWh sind um **13:48** beisammen. Der Sensor nennt das Ende des
      Slots, in dem die Schwelle fällt: Slot 14 = `[13:00, 14:00)` → **„14:00"**.
    * **Halber Start-Slot:** die Ladung beginnt erst um 09:30 → 4,8 kWh um
      **14:18**, Slot 15 = `[14:00, 15:00)` → **„15:00"**.

    Differenz der echten Zeitpunkte: **exakt 30 Minuten**. Dass das Etikett
    dabei um einen ganzen Slot springt, ist die Stundenraster-Auflösung des
    Textformats „HH:MM" — der Vertrag (CHANGELOG/Sensor-Referenz) nennt genau
    diese bis zu halbe Stunde.
    """
    pv = [0.0] * 10 + [1.0] * 14
    ganz = simuliere_speicher_tag(
        pv, [0.0] * 24, speicher_kap_kwh=10.0,
        start_soc_prozent=50.0, start_stunde=10, start_anteil=1.0,
    )
    halb = simuliere_speicher_tag(
        pv, [0.0] * 24, speicher_kap_kwh=10.0,
        start_soc_prozent=50.0, start_stunde=10, start_anteil=0.5,
    )
    assert ganz.speicher_voll_um == "14:00"
    assert halb.speicher_voll_um == "15:00"
    # Die Handrechnung an den Pegeln: nach Slot 13 fehlen ganz 1,0 kWh (90 %),
    # halb 1,5 kWh (85 %) — der halbe Slot ist die einzige Differenz.
    assert ganz.soc_pro_stunde[13] == pytest.approx(90.0)
    assert halb.soc_pro_stunde[13] == pytest.approx(85.0)


def test_anteil_0_5_bei_leerem_start_slot_aendert_nichts():
    """Ein Start-Slot ohne Netto ist halb wie ganz — die Gegenrichtung."""
    pv = [0.0] * 24
    pv[15] = 4.0
    ganz = simuliere_speicher_tag(pv, [0.0] * 24, speicher_kap_kwh=10.0,
                                  start_soc_prozent=40.0, start_stunde=10)
    halb = simuliere_speicher_tag(pv, [0.0] * 24, speicher_kap_kwh=10.0,
                                  start_soc_prozent=40.0, start_stunde=10,
                                  start_anteil=0.5)
    assert ganz.soc_pro_stunde == halb.soc_pro_stunde


# ══════════════════════════════════════════════════════════════════════════
# Service — welcher Slot, welcher Anteil
# ══════════════════════════════════════════════════════════════════════════

def test_sim_start_rechnet_forward_zeile_auf_backward_slot():
    """`_sim_start` ist die Umrechnungs-Tabelle — alle Fälle an einem Ort."""
    from backend.services.ha_export_prognose import _sim_start

    gestern = _HEUTE - timedelta(days=1)
    # Heute, HA hat bis Stunde 9 verdichtet → `[09:00,10:00)` = Slot 10, halb.
    assert _sim_start(_HEUTE, 9, _HEUTE) == (10, 0.5)
    assert _sim_start(_HEUTE, 0, _HEUTE) == (1, 0.5)
    # Heute Stunde 23 → der Tag ist durch, es gibt nichts mehr zu simulieren.
    assert _sim_start(_HEUTE, 23, _HEUTE) == (None, 1.0)
    # Gestern 23 Uhr IST der Backward-Slot 0 von heute — kein Altbestand.
    assert _sim_start(gestern, 23, _HEUTE) == (0, 0.5)
    # Jede frühere Stunde von gestern: heute liegt noch gar kein SoC vor.
    assert _sim_start(gestern, 17, _HEUTE) == (0, 1.0)
    # Keine Zeile gefunden.
    assert _sim_start(None, None, _HEUTE) == (None, 1.0)


def _fake_solar_prognose(tageswerte):
    tage = [
        SimpleNamespace(
            datum=(_HEUTE + timedelta(days=i)).isoformat(),
            pv_ertrag_kwh=val,
            stunden_kw=[val / 10 if 8 <= h < 18 else 0.0 for h in range(24)],
        )
        for i, val in enumerate(tageswerte)
    ]
    return SimpleNamespace(tageswerte=tage)


@pytest.fixture
def _patch_prognose(monkeypatch):
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache

    async def fake_get_solar_prognose(**kwargs):
        return _fake_solar_prognose([20.0, 18.0, 15.0, 12.0])

    async def fake_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return 1.0

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_get_solar_prognose)
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)
    _cache.clear()


def _stelle_uhr(monkeypatch, stunde: int) -> None:
    """Datum UND Stunde im Prüfling stellen — keine echte Uhr (N-167).

    ⚠ **Zwei Module, nicht eins.** `ha_export_prognose` legt den Tag und die
    Stunde fest, aber die PV-Reihe kommt aus `prognose_kanon`, und der ordnet
    seine Tage gegen seine EIGENE Uhr ein (`:340`). Wird nur der eine gestellt,
    liefert der Kanon ein Profil für den echten Kalendertag, `tage[0]` passt
    nicht zum gesäten Fake — die Simulation bekommt 24 Nullen und wird nie
    voll. (Gemessen beim Bau dieser Probe.)
    """
    from datetime import date as real_date, datetime as real_datetime, time as dt_time
    import backend.services.ha_export_prognose as hep
    import backend.services.prognose_kanon as pk

    class _FixedDate(real_date):
        @classmethod
        def today(cls):
            return _HEUTE

    class _Fixed(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.combine(_HEUTE, dt_time(stunde, 0), tzinfo=tz)

    for modul in (hep, pk):
        monkeypatch.setattr(modul, "date", _FixedDate)
        monkeypatch.setattr(modul, "datetime", _Fixed)


async def _seed(db, *, soc_zeilen: list[tuple[date, int, float]]) -> Anlage:
    anlage = Anlage(
        anlagenname="V1", leistung_kwp=10.0, latitude=48.8, longitude=9.2,
        standort_land="DE", prognose_quelle="eedc",
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1)))
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"kapazitaet_kwh": 10.0, "wirkungsgrad_prozent": 100},
    ))
    for tag, stunde, soc in soc_zeilen:
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=tag, stunde=stunde, soc_prozent=soc,
        ))
    await db.flush()
    return anlage


async def _export(db, anlage):
    from backend.services.ha_export_prognose import berechne_prognose_export
    return await berechne_prognose_export(db, anlage, skip_jitter=True)


async def test_b_start_slot_ist_zeilenstunde_plus_eins_und_halb(db, _patch_prognose, monkeypatch):
    """(b) Gesäter SoC in Stunde 9, Uhr 10:00 ⇒ Start-Slot 10, Anteil 0,5."""
    _stelle_uhr(monkeypatch, 10)
    anlage = await _seed(db, soc_zeilen=[(_HEUTE, h, 40.0 + h) for h in range(10)])

    p = await _export(db, anlage)

    assert p["speicher_soc_prozent"] == pytest.approx(49.0), "letzte Zeile ist Stunde 9"
    assert p["speicher_sim_start_stunde"] == 10
    assert p["speicher_sim_annahme"] == {"sim_start_stunde": 10, "sim_start_anteil": 0.5}
    assert min(p["speicher_soc_pro_stunde"]) == 10


async def test_c_ha_hinkt_nach_start_bleibt_bei_der_gemessenen_stunde(
    db, _patch_prognose, monkeypatch
):
    """(c) Letzte Zeile 7 Uhr, Uhr steht auf 10:00 ⇒ Start-Slot 8, keine Lücke.

    HEAD hätte bei Slot 10 begonnen und die Stunden 8 und 9 übersprungen —
    zwei Stunden PV, die in der Rechnung fehlen, obwohl der Startwert sie
    noch gar nicht enthält.
    """
    _stelle_uhr(monkeypatch, 10)
    anlage = await _seed(db, soc_zeilen=[(_HEUTE, h, 30.0) for h in range(8)])

    p = await _export(db, anlage)

    assert p["speicher_sim_start_stunde"] == 8
    assert p["speicher_sim_annahme"]["sim_start_anteil"] == 0.5
    slots = sorted(p["speicher_soc_pro_stunde"])
    assert slots == list(range(8, 24)), "die Lücke bis jetzt wird mit ganzen Slots gefüllt"


async def test_d_soc_nur_von_gestern(db, _patch_prognose, monkeypatch):
    """(d) Kein SoC von heute — gemessen und festgehalten.

    ⚠ **Das ist eine Verhaltensänderung gegenüber HEAD `786483a4`**, und sie
    fällt aus derselben Regel wie alles andere: der Start-Slot folgt der
    gelesenen Zeile, nicht der Uhr.

    * **`stunde = 23` von gestern** ist der **Normalfall kurz nach Mitternacht**
      und gar nicht veraltet: `[gestern 23:00, 00:00)` **ist** der Backward-Slot
      0 von heute ⇒ Slot 0, Anteil 0,5.
    * **jede frühere Stunde** heißt „heute liegt noch gar kein SoC vor" ⇒ der
      ganze Tag ab Slot 0, Anteil 1,0.

    HEAD startete in beiden Fällen bei `now.hour` (hier: 10) und ließ den
    Vormittag samt seiner PV aus der Rechnung fallen.
    """
    gestern = _HEUTE - timedelta(days=1)

    _stelle_uhr(monkeypatch, 10)
    a1 = await _seed(db, soc_zeilen=[(gestern, 23, 55.0)])
    p1 = await _export(db, a1)
    assert p1["speicher_sim_annahme"] == {"sim_start_stunde": 0, "sim_start_anteil": 0.5}

    _stelle_uhr(monkeypatch, 10)
    a2 = await _seed(db, soc_zeilen=[(gestern, 17, 55.0)])
    p2 = await _export(db, a2)
    assert p2["speicher_sim_annahme"] == {"sim_start_stunde": 0, "sim_start_anteil": 1.0}
    assert min(p2["speicher_soc_pro_stunde"]) == 0


async def test_e_voll_um_verschiebt_sich_hoechstens_einen_slot(
    db, _patch_prognose, monkeypatch
):
    """(e) Wirkungsbeleg auf den ECHTEN Eingängen des Dienstes.

    Der Prüfling gibt die Argumente heraus, mit denen er die Simulation ruft;
    damit wird derselbe Lauf noch einmal mit `start_anteil=1.0` gefahren (das
    Verhalten von HEAD auf demselben Start-Slot). Verglichen wird das, was der
    Anwender sieht: `eedc_speicher_voll_um`.
    """
    import backend.core.berechnungen.speicher_simulation as layer

    gesehen: dict = {}
    echt = layer.simuliere_speicher_tag

    def _merken(**kwargs):
        gesehen.update(kwargs)
        return echt(**kwargs)

    # Der Dienst importiert die Funktion erst im Rumpf — gepatcht wird deshalb
    # das QUELL-Modul, nicht der Aufrufer.
    monkeypatch.setattr(layer, "simuliere_speicher_tag", _merken)
    _stelle_uhr(monkeypatch, 10)
    anlage = await _seed(db, soc_zeilen=[(_HEUTE, h, 55.0) for h in range(10)])

    p = await _export(db, anlage)

    assert gesehen["start_stunde"] == 10 and gesehen["start_anteil"] == 0.5
    wie_head = echt(**{**gesehen, "start_anteil": 1.0})

    assert p["speicher_voll_um"] is not None and wie_head.speicher_voll_um is not None, (
        "Die Probe braucht einen Tag, an dem der Speicher in BEIDEN Rechnungen "
        "voll wird — sonst vergleicht sie None mit None."
    )
    neu_slot = int(p["speicher_voll_um"].split(":")[0])
    alt_slot = int(wie_head.speicher_voll_um.split(":")[0])
    assert 0 <= neu_slot - alt_slot <= 1, (
        f"„voll um“ springt von {wie_head.speicher_voll_um} auf "
        f"{p['speicher_voll_um']} — die halbe Startstunde darf hoechstens "
        "einen Slot kosten, nie mehr und nie frueher."
    )

    # Und der Grund dafuer steht im Start-Slot selbst: genau der halbe Zuwachs.
    zuwachs_ganz = wie_head.soc_pro_stunde[10] - gesehen["start_soc_prozent"]
    zuwachs_halb = p["speicher_soc_pro_stunde"][10] - gesehen["start_soc_prozent"]
    assert zuwachs_ganz > 0, "ohne Zuwachs im Start-Slot misst die Probe nichts"
    assert zuwachs_halb == pytest.approx(zuwachs_ganz / 2, abs=0.06), (
        "Der Start-Slot muss genau halb eingehen (Rundung auf 0,1 % im Ergebnis)."
    )


@pytest.fixture
def _fake_markt(monkeypatch):
    """Börsenpreise ohne Netz — wie die S3b-Schwesterproben.

    Der Sensorlauf holt Day-Ahead-Preise; ohne diesen Fake lebte die Probe
    von der Socket-Sperre in `conftest.py` (Nachmessung 22.09.2026) — sie war
    grün, weil ein Netzfehler still geschluckt wurde, nicht weil sie den Fall
    beherrschte.
    """
    async def _fake(datum, markt="DE", timeout=15.0):
        return {h: 8.0 for h in range(24)}

    monkeypatch.setattr("backend.services.strompreis_markt_service.fetch_marktpreise", _fake)


async def _sensoren(db, anlage) -> dict:
    from backend.api.routes.ha_export import calculate_anlage_sensors

    return {sv.definition.key: sv for sv in await calculate_anlage_sensors(db, anlage)}


def _pruefe_annahme(by_key: dict, keys: set[str]) -> None:
    fehlend = keys - set(by_key)
    assert not fehlend, f"Sim-Sensoren fehlen: {sorted(fehlend)}"
    for key in sorted(keys):
        z = by_key[key].zusatz_attribute or {}
        assert z.get("sim_start_stunde") == 10, f"{key} nennt seinen Start-Slot nicht"
        assert z.get("sim_start_anteil") == 0.5, f"{key} nennt seinen Start-Anteil nicht"


async def _seed_verbrauchshistorie(db, anlage, kw: float) -> None:
    """Drei gleiche Wochentage in den letzten acht Wochen — die Kaskadenstufe
    `gleicher_wochentag` braucht `MIN_TAGE_GLEICHER_WT = 3` vollständige Tage."""
    for wochen in (1, 2, 3):
        tag = _HEUTE - timedelta(weeks=wochen)
        for stunde in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=stunde, verbrauch_kw=kw,
            ))
    await db.flush()


async def test_attribut_am_sensor_ladender_tag(db, _patch_prognose, _fake_markt, monkeypatch):
    """Die Start-Annahme steht am Sensor, nicht nur im Dienst-Dict (Teil 1 von 2).

    S3b-Regel „jeder Sensor nennt sein Modell": bis 22.09.2026 nannten die vier
    Sim-Sensoren nur ihr **Verbrauchs**-Modell. Die Start-Annahme entscheidet
    aber über bis zu eine halbe Stunde — eine Automation, die auf „HH:MM"
    schaltet, soll sie lesen können statt sie zu raten.

    Dieser Tag lädt: `voll um`, sein Zeitstempel und `reicht bis Mitternacht`.
    """
    _stelle_uhr(monkeypatch, 10)
    anlage = await _seed(db, soc_zeilen=[(_HEUTE, h, 55.0) for h in range(10)])

    _pruefe_annahme(await _sensoren(db, anlage), {
        "eedc_speicher_voll_um",
        "eedc_speicher_voll_um_ts",
        "eedc_speicher_reicht_bis_mitternacht",
    })


async def test_attribut_am_sensor_entladender_tag(db, _patch_prognose, _fake_markt, monkeypatch):
    """Teil 2 von 2 — der vierte Sim-Sensor.

    `eedc_speicher_leer_um_ts` entsteht nur, wo die Simulation einen **Übergang**
    in den Leerstand sieht; dafür braucht es mehr Verbrauch als PV. Ohne diesen
    zweiten Tag bliebe genau der Sensor ungeprüft, dessen Uhrzeit sich mit V1
    verschiebt.
    """
    _stelle_uhr(monkeypatch, 10)
    anlage = await _seed(db, soc_zeilen=[(_HEUTE, h, 55.0) for h in range(10)])
    await _seed_verbrauchshistorie(db, anlage, kw=3.0)

    by_key = await _sensoren(db, anlage)
    assert "eedc_speicher_voll_um" not in by_key, "dieser Tag darf NICHT voll werden"
    _pruefe_annahme(by_key, {
        "eedc_speicher_leer_um_ts",
        "eedc_speicher_reicht_bis_mitternacht",
    })
