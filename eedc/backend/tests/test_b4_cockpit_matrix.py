"""B4 — Matrix-Durchgang Cockpit (Monat · Jahr · Tag), 05.09.2026 (SOLL Wärme/Klima §3.2a × §6).

Je Sprosse EIN Gerät (dieselben Fixtures wie B3, dazu ein Tarif). Drei Sichten:
Cockpit → Monat (`get_aktueller_monat`), Cockpit → Jahr-Backend
(`get_cockpit_uebersicht(jahr)`) und Cockpit → Tag (`get_tag_detail`, Snapshot-Pfad).

**Was die Messung gefunden hat (IST §12):**

* **C-1** Cockpit → Jahr baute seinen Wärme/Klima-Block im Client aus den
  Monatsantworten und verlor 16 von 33 WP-Feldern — JAZ „—" ohne Grund, je-Funktion-
  Zeilen ersatzlos weg (N-348-Klasse), Restmenge ohne Lüften/Entfeuchten. Die
  Jahresroute liefert jetzt den ganzen Kennzahl-Satz aus dem Layer; die Symmetrie
  **Monat ≡ Jahr** über alle Sprossen ist der Wächter dagegen.
* **C-2** Monat/Jahr trugen keine Herkunft für geschätzte Wärme und keinen Vorbehalt
  an der Ersparnis (SOLL §6 vom 05.09.) — beides jetzt aus dem Layer, wie im Hub (B3).

Kein Fund, gemessen: Tag-Kühlzahl (Entscheid N-348) · F4-Grund (Betriebsart Heizen
enthält Warmwasser) · Monats-Ersparnis braucht den Tarif (Daten-Checker deckt es) ·
beide Tages-Stromquellen sind Zählerpfad.

Schwesterdateien: test_b3_hub_matrix.py (Hub ≡ Monat, dieselben Sprossen),
test_soll_waerme_klima_simulation_anlagen.py (A6: der Tages-Snapshot-Aufbau).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_FREMDWAERME,
    GRUND_KUEHLZAHL_NUR_MONAT,
    HERKUNFT_GEMESSEN,
    VORBEHALT_ABGELEITET,
    VORBEHALT_FREMDWAERME,
)
from backend.models import Anlage, Investition  # noqa: F401
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.tests.factories import strompreis
from backend.tests.test_b3_hub_matrix import LL, LW, SPROSSEN, JAHR, MONAT

TAG = date(2025, 7, 15)


async def _anlage(db, name: str) -> Anlage:
    a = Anlage(anlagenname=name, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    await strompreis(db, a.id, date(2025, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                     einspeiseverguetung_cent_kwh=8.0)
    return a


async def _geraet(db, anlage, parameter, daten=None, provenance=None):
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wärmepumpe",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter=parameter)
    db.add(inv)
    await db.flush()
    if daten is not None:
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                      verbrauch_daten=daten, source_provenance=provenance or {}))
    return inv


#: Monats-Attribut → Jahres-Attribut. Dieselbe Größe, EIN Wert (S1); im Jahr heißt
#: die Kennzahl historisch `wp_cop`.
SYMMETRIE = {
    "wp_strom_kwh": "wp_strom_kwh", "wp_waerme_kwh": "wp_waerme_kwh",
    "wp_heizung_kwh": "wp_heizung_kwh", "wp_warmwasser_kwh": "wp_warmwasser_kwh",
    "wp_jaz": "wp_cop", "wp_jaz_grund": "wp_cop_grund", "wp_jaz_hinweis": "wp_cop_hinweis",
    "wp_jaz_zaehler_kwh": "wp_jaz_zaehler_kwh", "wp_jaz_nenner_kwh": "wp_jaz_nenner_kwh",
    "wp_waerme_abgeleitet": "wp_waerme_abgeleitet",
    "wp_waerme_herkunft": "wp_waerme_herkunft", "wp_ersparnis_vorbehalt": "wp_ersparnis_vorbehalt",
    "wp_strom_heizen_kwh": "wp_strom_heizen_kwh", "wp_strom_warmwasser_kwh": "wp_strom_warmwasser_kwh",
    "wp_jaz_heizen": "wp_jaz_heizen", "wp_jaz_heizen_grund": "wp_jaz_heizen_grund",
    "wp_jaz_warmwasser": "wp_jaz_warmwasser", "wp_jaz_warmwasser_grund": "wp_jaz_warmwasser_grund",
    "wp_jaz_kuehlen": "wp_jaz_kuehlen", "wp_jaz_kuehlen_grund": "wp_jaz_kuehlen_grund",
    "wp_modus_strom_heizen_kwh": "wp_modus_strom_heizen_kwh",
    "wp_modus_strom_kuehlen_kwh": "wp_modus_strom_kuehlen_kwh",
    "wp_modus_strom_warmwasser_kwh": "wp_modus_strom_warmwasser_kwh",
    "wp_modus_strom_lueften_kwh": "wp_modus_strom_lueften_kwh",
    "wp_modus_strom_entfeuchten_kwh": "wp_modus_strom_entfeuchten_kwh",
    "wp_modus_nicht_aufgeteilt_kwh": "wp_modus_nicht_aufgeteilt_kwh",
    "wp_modus_abdeckung_h": "wp_modus_abdeckung_h", "wp_modus_strom_bezug_kwh": "wp_modus_strom_bezug_kwh",
    "wp_modus_gemessen": "wp_modus_gemessen", "wp_ersparnis_euro": "wp_ersparnis_euro",
}


def _leer(x) -> bool:
    return x is None or x == 0 or x == 0.0 or x is False


def _wert(x):
    return round(x, 1) if isinstance(x, float) else x


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse", list(SPROSSEN))
async def test_monat_und_jahr_nennen_dieselbe_zahl_und_denselben_grund(db, sprosse):
    """C-1: die Jahresroute trägt jede Größe, die der Monat trägt — mit denselben Werten."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    parameter, daten, prov = SPROSSEN[sprosse]
    a = await _anlage(db, sprosse)
    await _geraet(db, a, parameter, daten, prov)
    await db.commit()
    m = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    j = await get_cockpit_uebersicht(a.id, jahr=JAHR, db=db)

    abweichungen = []
    for mk, jk in SYMMETRIE.items():
        mv, jv = getattr(m, mk), getattr(j, jk)
        # Das Jahr nennt Mengen als 0.0, der Monat als None — beides „nichts".
        if _leer(mv) and _leer(jv):
            continue
        if _wert(mv) != _wert(jv):
            abweichungen.append(f"{mk}: Monat {mv!r} ≠ Jahr {jv!r}")
    assert not abweichungen, (
        f"[{sprosse}] Dieselbe Anlage, zwei Aussagen (Monat gegen Jahr):\n  " + "\n  ".join(abweichungen)
    )


@pytest.mark.asyncio
async def test_c1_das_jahr_nennt_hinweis_je_funktion_und_kuehlen(db):
    """Vor B4 lieferte die Jahresroute nur `wp_cop` und `wp_cop_grund`."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    a = await _anlage(db, "C-1 F7")
    await _geraet(db, a, *SPROSSEN["F7_wmz_je_funktion"])
    await db.commit()
    j = await get_cockpit_uebersicht(a.id, jahr=JAHR, db=db)
    assert j.wp_jaz_heizen == pytest.approx(4.0) and j.wp_jaz_warmwasser == pytest.approx(2.4)
    assert j.wp_jaz_zaehler_kwh == pytest.approx(3600.0) and j.wp_jaz_nenner_kwh == pytest.approx(1000.0)

    b = await _anlage(db, "C-1 F10")
    await _geraet(db, b, *SPROSSEN["F10_heizstab_in_wp"])
    await db.commit()
    j10 = await get_cockpit_uebersicht(b.id, jahr=JAHR, db=db)
    assert j10.wp_cop == pytest.approx(1.8) and j10.wp_cop_hinweis, "Heizstab-Satz (W-6) fehlt im Jahr"

    c = await _anlage(db, "C-1 F8")
    await _geraet(db, c, *SPROSSEN["F8_kaeltemenge"])
    await db.commit()
    j8 = await get_cockpit_uebersicht(c.id, jahr=JAHR, db=db)
    assert j8.wp_jaz_kuehlen == pytest.approx(3.0)
    assert j8.wp_modus_strom_kuehlen_kwh == pytest.approx(300.0)
    assert j8.wp_modus_nicht_aufgeteilt_kwh == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_c1_die_restmenge_kommt_aus_dem_layer_mit_e4(db):
    """Die Client-Formel zog Lüften/Entfeuchten nie ab (50 statt 35) — das Jahr rechnet im Layer."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    a = await _anlage(db, "C-1 E4")
    await _geraet(db, a, LL, {"stromverbrauch_kwh": 1000.0, "betriebsart_strom_heizen_kwh": 700.0,
                              "betriebsart_strom_kuehlen_kwh": 250.0, "betriebsart_strom_lueften_kwh": 10.0,
                              "betriebsart_strom_entfeuchten_kwh": 5.0})
    await db.commit()
    j = await get_cockpit_uebersicht(a.id, jahr=JAHR, db=db)
    assert j.wp_modus_strom_lueften_kwh == pytest.approx(10.0)
    assert j.wp_modus_strom_entfeuchten_kwh == pytest.approx(5.0)
    assert j.wp_modus_nicht_aufgeteilt_kwh == pytest.approx(35.0), "1000 − 700 − 250 − 10 − 5"


@pytest.mark.asyncio
async def test_c2_monat_traegt_herkunft_und_vorbehalt(db):
    """SOLL §6 (05.09.): geschätzte Wärme erscheint als geschätzt — auch im Cockpit."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    a = await _anlage(db, "C-2 F2b")
    await _geraet(db, a, *SPROSSEN["F2b_gesamtstrom_plus_schaetzung"])
    await db.commit()
    m = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    assert m.wp_waerme_abgeleitet is True
    assert m.wp_waerme_herkunft == "geschätzt: Strom × JAZ 3,5"
    assert m.wp_ersparnis_vorbehalt == VORBEHALT_ABGELEITET

    b = await _anlage(db, "C-2 F12")
    await _geraet(db, b, *SPROSSEN["F12_bivalent"])
    await db.commit()
    m12 = await get_aktueller_monat(b.id, jahr=JAHR, monat=MONAT, db=db)
    assert m12.wp_jaz is None and m12.wp_jaz_grund == GRUND_FREMDWAERME
    assert m12.wp_ersparnis_vorbehalt == VORBEHALT_FREMDWAERME

    c = await _anlage(db, "C-2 F6")
    await _geraet(db, c, *SPROSSEN["F6_wmz_gesamt"])
    await db.commit()
    m6 = await get_aktueller_monat(c.id, jahr=JAHR, monat=MONAT, db=db)
    assert m6.wp_waerme_herkunft == HERKUNFT_GEMESSEN and m6.wp_ersparnis_vorbehalt is None


# ─── Tag: Snapshot-Pfad ───────────────────────────────────────────────────────

async def _tag_geraet(db, anlage, parameter, *, komponenten_kwh=30.0,
                      zaehler: dict[str, tuple[float, float]] | None = None,
                      modus_stunden: list[tuple[str | None, float]] | None = None):
    """`zaehler`: feld → (Startstand, Endstand) als Snapshot an den Tagesgrenzen."""
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wärmepumpe",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter=parameter)
    db.add(inv)
    await db.flush()
    felder = {}
    t0 = datetime.combine(TAG, datetime.min.time())
    for feld, (start, ende) in (zaehler or {}).items():
        felder[feld] = {"strategie": "sensor", "sensor_id": f"sensor.wp_{feld}"}
        key = f"inv:{inv.id}:{feld}"
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key, zeitpunkt=t0,
                              wert_kwh=start, quelle="ha_statistics"))
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=key,
                              zeitpunkt=t0 + timedelta(days=1), wert_kwh=ende, quelle="ha_statistics"))
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": felder}}}
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=TAG,
                                komponenten_kwh={f"waermepumpe_{inv.id}": komponenten_kwh}))
    if modus_stunden:
        for stunde, (modus, kwh) in enumerate(modus_stunden):
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=TAG, stunde=stunde,
                                      komponenten={f"waermepumpe_{inv.id}": -kwh},
                                      betriebsmodus_je_wp={str(inv.id): modus} if modus else None))
    return inv


TAG_SPROSSEN = {
    "T-F2_nur_strom": (dict(parameter=LW), {
        "wp_waerme_kwh": None, "wp_jaz": None, "wp_jaz_grund": "kein Wärmemengenzähler zugeordnet"}),
    "T-F3_modus_abgeleitet": (dict(parameter=LL, komponenten_kwh=24.0,
                                   modus_stunden=[("heizen", 1.0)] * 12 + [("kuehlen", 1.0)] * 6 + [(None, 1.0)] * 6), {
        "wp_modus_strom_heizen_kwh": 12.0, "wp_modus_strom_kuehlen_kwh": 6.0,
        "wp_modus_nicht_aufgeteilt_kwh": 6.0, "wp_modus_abdeckung_h": 18.0, "wp_modus_gemessen": False,
        "wp_jaz_kuehlen_grund": GRUND_KUEHLZAHL_NUR_MONAT}),
    "T-F4_betriebsart": (dict(parameter=LL, zaehler={"betriebsart_strom_heizen_kwh": (100.0, 120.0),
                                                     "betriebsart_strom_kuehlen_kwh": (50.0, 58.0)}), {
        "wp_modus_strom_heizen_kwh": 20.0, "wp_modus_strom_kuehlen_kwh": 8.0,
        "wp_modus_nicht_aufgeteilt_kwh": 2.0, "wp_modus_gemessen": True}),
    "T-F5_getrennte_stroeme": (dict(parameter={**LW, "getrennte_strommessung": True},
                                    zaehler={"strom_heizen_kwh": (100.0, 122.0), "strom_warmwasser_kwh": (50.0, 58.0)}), {
        "wp_strom_heizen_kwh": 22.0, "wp_strom_warmwasser_kwh": 8.0,
        "wp_jaz_heizen": None, "wp_jaz_heizen_grund": "kein Wärmemengenzähler zugeordnet"}),
    "T-F6_wmz_gesamt": (dict(parameter=LW, zaehler={"heizenergie_kwh": (1000.0, 1105.0)}), {
        "wp_waerme_kwh": 105.0, "wp_jaz": 3.5, "wp_jaz_nenner_kwh": 30.0}),
    "T-F7_wmz_je_funktion": (dict(parameter={**LW, "getrennte_strommessung": True},
                                  zaehler={"strom_heizen_kwh": (100.0, 122.0), "strom_warmwasser_kwh": (50.0, 58.0),
                                           "heizenergie_kwh": (1000.0, 1088.0), "warmwasser_kwh": (500.0, 519.0)}), {
        "wp_jaz_heizen": 4.0, "wp_jaz_warmwasser": 2.375, "wp_waerme_kwh": 107.0}),
    "T-F8_kaeltemenge": (dict(parameter=LW, zaehler={"betriebsart_strom_heizen_kwh": (100.0, 120.0),
                                                     "betriebsart_strom_kuehlen_kwh": (50.0, 60.0),
                                                     "betriebsart_nutzenergie_kuehlen_kwh": (200.0, 230.0),
                                                     "heizenergie_kwh": (1000.0, 1060.0)}), {
        # 60 kWh Wärme ÷ (30 − 10 Kühlstrom) — W-14; die Kühlzahl bleibt Monatssache (N-348).
        "wp_jaz": 3.0, "wp_jaz_nenner_kwh": 20.0, "wp_jaz_kuehlen": None,
        "wp_jaz_kuehlen_grund": GRUND_KUEHLZAHL_NUR_MONAT}),
    "T-F11_fremdstrom": (dict(parameter={**LW, "abgrenzung": "fremdstrom"}, zaehler={"heizenergie_kwh": (1000.0, 1105.0)}), {
        "wp_waerme_kwh": 105.0, "wp_jaz": None, "wp_jaz_grund": "Heizstab-Strom auf dem WP-Zähler"}),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse", list(TAG_SPROSSEN))
async def test_tag_liefert_jede_sprosse_mit_zahl_oder_grund(db, sprosse):
    from backend.api.routes.energie_profil.views import get_tag_detail

    aufbau, erwartet = TAG_SPROSSEN[sprosse]
    a = await _anlage(db, sprosse)
    await _tag_geraet(db, a, **aufbau)
    await db.commit()
    t = await get_tag_detail(a.id, datum=TAG, db=db)
    for k, v in erwartet.items():
        ist = getattr(t, k)
        if isinstance(v, float):
            assert ist == pytest.approx(v, rel=1e-3), f"[{sprosse}] {k}: {ist!r} ≠ {v!r}"
        else:
            assert ist == v, f"[{sprosse}] {k}: {ist!r} ≠ {v!r}"
