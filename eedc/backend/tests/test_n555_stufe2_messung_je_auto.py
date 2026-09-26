"""N-555 Stufe 2 — Messung je Auto (Konzept Heimladung/Fahrverbrauch, Fassung 7.1, §4).

Gernots Modell vom 24.09.2026: *„Wallbox = Summe aller Ladungen; wer eine eigene Messung hat,
trägt sie; der Rest der Wallbox geht an die privaten Autos ohne eigene Messung; Gast und
Dienstwagen haben für den Haushalt keine Ersparnis gegenüber dem Verbrenner."*

Die Proben sind nach den Bau-Schnitten gegliedert (S2-1 … S2-8). Jede trägt einen Sprengsatz
im Baubericht (`~/.claude/plans/opus-berichte/N555-S2-BAU.md`).

Schwesterdateien: test_n555_fahrverbrauch_bleibt_fahrverbrauch.py (Stufe 1 — Regel 1, 2-Ü, 4,
5, 6, 10), test_emob_write_canonical_felder.py (Heim-Felder im Formular),
test_daten_checker_emob_pool_pflege.py (Regel 7).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.datenquellen import get_datenquellen_felder
from backend.models.anlage import Anlage
from backend.models.investition import Investition
# Import registriert das Modell in `Base.metadata` — der `/felder`-Handler fragt die
# Gateway-Zeilen ab, die Tabelle muss in der Test-DB existieren.
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401


# ═════════════════════════════════════════════════════════════════════════════
# S2-1 — Feld und Flächen (Regel 8, E5)
# ═════════════════════════════════════════════════════════════════════════════

async def _anlage(db, *geraete, sensor_mapping=None):
    """Anlage + Geräte ``(typ, bezeichnung, dienstlich)``; gibt ``(anlage, [inv…])``."""
    a = Anlage(anlagenname="S2", leistung_kwp=10.0, sensor_mapping=sensor_mapping or {})
    db.add(a)
    await db.flush()
    invs = []
    for typ, bez, dienstlich in geraete:
        inv = Investition(
            anlage_id=a.id, typ=typ, bezeichnung=bez, anschaffungsdatum=date(2024, 1, 1),
            parameter={"ist_dienstlich": True} if dienstlich else {},
        )
        db.add(inv)
        await db.flush()
        invs.append(inv)
    await db.commit()
    return a, invs


def _flach(resp) -> dict:
    return {f["id"]: f for g in resp["gruppen"] for f in g["felder"]}


@pytest.mark.asyncio
async def test_s2_1_alte_ladung_gesamt_zuordnung_erscheint_als_heim_gesamt(db):
    """Messung aus dem Auftrag: der alte Assistenten-Slot `felder.ladung_kwh` am E-Auto.

    Bis Stufe 2 stand `ladung_kwh` nicht in der E-Auto-Registry — eine alte Zuordnung dort
    war auf der Datenquellen-Fläche **unsichtbar und unlöschbar** (gemessen an HEAD
    `5f821b6b`: keine Zeile, `quellen` leer). Mit dem Registry-Eintrag erscheint sie als
    „Heim: gesamt", belegt (Regel 8: „Was ab dann wirkt, obwohl es bisher ohne Wirkung war").
    """
    a, (wb, ea) = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "Auto", False))
    a.sensor_mapping = {"investitionen": {str(ea.id): {"felder": {
        "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.alt_ladung_gesamt"}}}}}
    await db.commit()
    felder = _flach(await get_datenquellen_felder(a.id, db))
    f = felder[f"inv_energy_{ea.id}_ladung_kwh"]
    assert f["label"] == "Heim: gesamt"
    assert f["ha_entity"] == "sensor.alt_ladung_gesamt"
    assert f["bedarf"] == "optional"          # neben der privaten Wallbox NICHT verdrängt


@pytest.mark.asyncio
async def test_s2_1_heim_felder_neben_privater_wallbox_nicht_inaktiv(db):
    """Regel 8: jedem E-Auto angeboten — auf der Fläche nicht mehr „inaktiv (keine_wallbox)"."""
    a, (wb, ea) = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "Auto", False))
    felder = _flach(await get_datenquellen_felder(a.id, db))
    for feld in ("ladung_pv_kwh", "ladung_netz_kwh", "ladung_kwh"):
        assert felder[f"inv_energy_{ea.id}_{feld}"]["bedarf"] != "inaktiv", feld


@pytest.mark.asyncio
async def test_s2_1_dienstwagen_neben_dienstlicher_wallbox_inaktiv_mit_grund(db):
    """Regel 3 auf der Fläche: inaktiv mit Begründung — ein privates Auto daneben nicht."""
    a, (wb, dw, ea) = await _anlage(
        db, ("wallbox", "WB dienstlich", True), ("e-auto", "Dienstwagen", True),
        ("e-auto", "Privat", False),
    )
    felder = _flach(await get_datenquellen_felder(a.id, db))
    for feld in ("ladung_pv_kwh", "ladung_netz_kwh", "ladung_kwh"):
        f = felder[f"inv_energy_{dw.id}_{feld}"]
        assert f["bedarf"] == "inaktiv" and f["bedarf_grund"] == "keine_dienstliche_wallbox", feld
        assert felder[f"inv_energy_{ea.id}_{feld}"]["bedarf"] != "inaktiv", feld


@pytest.mark.asyncio
async def test_s2_1_csv_vorlage_traegt_heim_gesamt_neben_wallbox(db):
    """Regel 8: „Heim: gesamt" in der CSV-Vorlage — auch neben einer Wallbox."""
    from backend.api.routes.import_export.csv_operations import get_csv_template_info

    a, _ = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "Auto", False))
    info = await get_csv_template_info(a.id, db)
    spalten = info["spalten"] if isinstance(info, dict) else info.spalten
    assert "Auto_Ladung_Heim_kWh" in spalten
    assert "Auto_Ladung_PV_kWh" in spalten and "Auto_Ladung_Netz_kWh" in spalten


@pytest.mark.asyncio
async def test_s2_1_mqtt_topic_fuer_heim_gesamt(db):
    """Regel 8: „Heim: gesamt" hat sein MQTT-Topic (der Inbound kannte es schon)."""
    from backend.services.mqtt_topic_registry import build_expected_topics

    a, (wb, ea) = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "Auto", False))
    topics = await build_expected_topics(db, a, [wb, ea])
    eintraege = [t for t in topics if t.get("match_key") == ("inv_energy", str(ea.id), "ladung_kwh")]
    assert eintraege and eintraege[0]["topic"].endswith("/ladung_kwh")
    assert eintraege[0]["bedingung_anlage"] is None   # privates Auto: nichts verdrängt


# ═════════════════════════════════════════════════════════════════════════════
# S2-3 / S2-3b — Regel 0/2/3 in der EINEN Funktion (Konzept 7.2, G1, W-1)
# ═════════════════════════════════════════════════════════════════════════════
#
# Die Proben laufen unmittelbar gegen `entscheide_emob_heimladung` (die eine Stelle,
# Regel 6); die Schicht-Proben weiter unten zeigen, dass dieselben Zahlen über
# `lade_monats_fakten` (Herkunft, „in Betrieb", Anreicherung) ankommen.

from backend.services.eauto_wirtschaftlichkeit import (  # noqa: E402
    ART_GEMESSEN,
    ART_REST,
    ART_SCHAETZUNG,
    entscheide_emob_heimladung,
)

WB_400 = {"ladung_kwh": 400.0, "ladung_pv_kwh": 200.0}  # 200 PV / 200 Netz
A_GEMESSEN = {"km_gefahren": 1000.0, "ladung_pv_kwh": 70.0, "ladung_netz_kwh": 30.0}
DW_HEIM_GESAMT = {"km_gefahren": 1000.0, "ladung_kwh": 150.0}
B_OHNE = {"km_gefahren": 1000.0}
A, B, D, WB = 1, 2, 3, 9


def _e(eautos, wallboxen=(WB_400,), **kw):
    kw.setdefault("wallbox_ids", {WB})
    return entscheide_emob_heimladung(eauto_je_inv=eautos, wallbox_zeilen=list(wallboxen), **kw)


def _pn(a):
    return (pytest.approx(a.pv_kwh), pytest.approx(a.netz_kwh))


def test_s2_3_beispiel_regel_2_und_die_invariante_des_topfs():
    """Konzept Regel 2 (Beispiel) + Regel 3/G1: der Topf ist Σ der privaten Autos.

    Wallbox 400 (200/200), A gemessen 70/30, Dienstwagen „Heim: gesamt" 150 (mit dem
    Wallbox-Anteil 50 % ⇒ 75/75), B ohne Messung ⇒ Rest 150 = 55 PV / 95 Netz an B.
    """
    e = _e({A: A_GEMESSEN, B: B_OHNE}, dienstwagen_je_inv={D: DW_HEIM_GESAMT}, heim_gesamt={D})
    assert (e.pool.pv_kwh, e.pool.netz_kwh) == (pytest.approx(125.0), pytest.approx(125.0))
    assert e.je_auto[A].pv_kwh == pytest.approx(70.0) and e.je_auto[A].art == ART_GEMESSEN
    assert (e.je_auto[B].pv_kwh, e.je_auto[B].netz_kwh) == (pytest.approx(55.0), pytest.approx(95.0))
    assert e.je_auto[B].art == ART_REST
    assert (e.dienstlich_je_inv[D].pv_kwh, e.dienstlich_je_inv[D].netz_kwh) == (
        pytest.approx(75.0), pytest.approx(75.0))
    assert e.wallbox_summe.ladung_kwh == pytest.approx(400.0)
    assert e.rest_nicht_zugeordnet_kwh == pytest.approx(0.0)
    # A 100 + Dienstwagen 150 + B 150 = 400
    assert e.pool.ladung_kwh + 150.0 == pytest.approx(e.wallbox_summe.ladung_kwh)


def test_s2_3_ohne_b_ist_der_rest_nicht_zugeordnet_und_die_wallbox_geht_auf():
    """Wallbox = Topf + nicht zugeordnet + Dienstwagen gemessen (Regel 3, G1)."""
    e = _e({A: A_GEMESSEN}, dienstwagen_je_inv={D: DW_HEIM_GESAMT}, heim_gesamt={D})
    assert e.pool.ladung_kwh == pytest.approx(100.0)
    assert e.rest_nicht_zugeordnet_kwh == pytest.approx(150.0)
    assert (e.rest_pv_kwh, e.rest_netz_kwh) == (pytest.approx(55.0), pytest.approx(95.0))
    dienst = sum(d.pv_kwh + d.netz_kwh for d in e.dienstlich_je_inv.values())
    assert e.pool.ladung_kwh + e.rest_nicht_zugeordnet_kwh + dienst == pytest.approx(400.0)


def test_s2_3_nur_heim_pv_das_andere_zaehlt_als_0():
    e = _e({A: {"km_gefahren": 500.0, "ladung_pv_kwh": 40.0}, B: B_OHNE})
    assert _pn(e.je_auto[A]) == (40.0, 0.0)
    assert e.je_auto[B].ladung_kwh == pytest.approx(360.0)


def test_s2_3_nur_heim_gesamt_wird_mit_dem_wallbox_anteil_geteilt():
    """„Heim: gesamt" (Herkunft ≠ Altwert) neben der Wallbox: PV-Anteil der Wallbox (25 %)."""
    wb = {"ladung_kwh": 400.0, "ladung_pv_kwh": 100.0}
    e = _e({A: {"km_gefahren": 500.0, "ladung_kwh": 80.0}, B: B_OHNE}, wallboxen=(wb,),
           heim_gesamt={A})
    assert _pn(e.je_auto[A]) == (20.0, 60.0)


@pytest.mark.parametrize("wb_pv, a_pv, a_netz", [
    (200.0, 70.0, 30.0),    # Wallbox 50 %, Auto 70 %
    (40.0, 90.0, 10.0),     # Auto PV > Wallbox-PV ⇒ Rest-PV 0
    (390.0, 10.0, 90.0),    # Rest-PV würde Rest übersteigen ⇒ gekappt
])
def test_s2_3_rest_teilung_autos_plus_rest_gleich_wallbox(wb_pv, a_pv, a_netz):
    e = _e({A: {"ladung_pv_kwh": a_pv, "ladung_netz_kwh": a_netz}, B: B_OHNE},
           wallboxen=({"ladung_kwh": 400.0, "ladung_pv_kwh": wb_pv},))
    rest = e.je_auto[B]
    assert 0.0 <= rest.pv_kwh <= rest.ladung_kwh
    assert e.je_auto[A].ladung_kwh + rest.ladung_kwh == pytest.approx(400.0)
    assert rest.pv_kwh == pytest.approx(min(max(0.0, wb_pv - a_pv), 400.0 - a_pv - a_netz))


def test_s2_3_rest_nie_unter_0_wenn_die_autos_die_wallbox_uebersteigen():
    """E2: weiterrechnen, nicht kappen — die Autos behalten ihre Werte, Rest 0."""
    e = _e({A: {"ladung_pv_kwh": 300.0, "ladung_netz_kwh": 200.0}, B: B_OHNE})
    assert e.je_auto[A].ladung_kwh == pytest.approx(500.0)
    assert e.je_auto[B].ladung_kwh == pytest.approx(0.0)
    assert (e.rest_pv_kwh, e.rest_netz_kwh) == (0.0, 0.0)
    assert e.pool.ladung_kwh == pytest.approx(500.0)


def test_s2_3_kein_empfaenger_rest_nicht_zugeordnet():
    e = _e({A: A_GEMESSEN})
    assert e.rest_zugeordnet is False
    assert e.rest_nicht_zugeordnet_kwh == pytest.approx(300.0)
    assert e.pool.ladung_kwh == pytest.approx(100.0), "Gast/Verluste stehen nicht im Topf"


def test_s2_3_empfaenger_mit_0_km_gleich_verteilt():
    """E6: sind die km der Empfänger zusammen 0, wird der Rest gleichmäßig verteilt."""
    e = _e({A: A_GEMESSEN, B: {"km_gefahren": 0.0}, 4: {}})
    assert e.je_auto[B].ladung_kwh == pytest.approx(150.0)
    assert e.je_auto[4].ladung_kwh == pytest.approx(150.0)


def test_s2_3_rest_nach_km():
    e = _e({B: {"km_gefahren": 300.0}, 4: {"km_gefahren": 100.0}})
    assert e.je_auto[B].ladung_kwh == pytest.approx(300.0)
    assert e.je_auto[4].ladung_kwh == pytest.approx(100.0)


def test_s2_3_gemessenes_auto_ohne_km_traegt_seine_menge():
    e = _e({A: {"ladung_pv_kwh": 20.0, "ladung_netz_kwh": 30.0}, B: {"km_gefahren": 800.0}})
    assert _pn(e.je_auto[A]) == (20.0, 30.0)


def test_s2_3_wallbox_leer_schaetzung_fuer_autos_ohne_messung():
    """Regel 2 „Die Wallbox ist leer": Regel 1 — der Fahrverbrauch als Schätzung."""
    e = _e({A: A_GEMESSEN, B: {"km_gefahren": 500.0, "verbrauch_kwh": 90.0}},
           wallboxen=({},), wallbox_in_betrieb=True)
    assert e.wallbox_hat_wert is False
    assert e.je_auto[B].art == ART_SCHAETZUNG
    assert e.je_auto[B].ladung_kwh == pytest.approx(90.0)
    assert e.pool.ladung_kwh == pytest.approx(190.0)


def test_s2_3_wallbox_0_rest_0():
    e = _e({A: A_GEMESSEN, B: {"km_gefahren": 500.0, "verbrauch_kwh": 90.0}},
           wallboxen=({"ladung_kwh": 0.0},))
    assert e.wallbox_hat_wert is True
    assert e.je_auto[B].ladung_kwh == pytest.approx(0.0)
    assert e.pool.ladung_kwh == pytest.approx(100.0)


def test_s2_3_alter_gesamtwert_neben_wallbox_zaehlt_nicht_ohne_wallbox_schon():
    """Regel 2 Schritt 1 / Regel 8: `ladung_kwh` mit Altwert-Herkunft (nicht in `heim_gesamt`)."""
    neben = _e({A: {"km_gefahren": 500.0, "ladung_kwh": 150.0}})
    assert neben.je_auto[A].art == ART_REST, "keine eigene Messung — A bekommt den Rest"
    assert neben.je_auto[A].ladung_kwh == pytest.approx(400.0)
    ohne = entscheide_emob_heimladung(
        eauto_je_inv={A: {"km_gefahren": 500.0, "ladung_kwh": 150.0}}, wallbox_zeilen=[],
    )
    assert ohne.je_auto[A].art == ART_GEMESSEN
    assert ohne.je_auto[A].ladung_kwh == pytest.approx(150.0)


def test_s2_3_dienstwagen_gemessen_fehlt_im_rest():
    e = _e({B: B_OHNE}, dienstwagen_je_inv={D: {"ladung_pv_kwh": 50.0, "ladung_netz_kwh": 50.0}})
    assert e.je_auto[B].ladung_kwh == pytest.approx(300.0)
    assert e.dienstlich_je_inv[D].gemessen is True
    assert D in e.dienstwagen_gemessen


def test_s2_3_dienstwagen_ohne_messung_schaetzung_ohne_abzug():
    """Regel 3: die Schätzung (Fahrverbrauch, als Netz) wird nie vom Rest abgezogen."""
    e = _e({B: B_OHNE}, dienstwagen_je_inv={D: {"km_gefahren": 900.0, "verbrauch_kwh": 160.0}})
    assert e.je_auto[B].ladung_kwh == pytest.approx(400.0)
    assert (e.dienstlich_je_inv[D].netz_kwh, e.dienstlich_je_inv[D].gemessen) == (160.0, False)
    assert D in e.dienstwagen_ungemessen


def test_s2_3_dienstliche_wallbox_in_betrieb_felder_und_schaetzung_zaehlen_nicht():
    e = _e({B: B_OHNE},
           dienstwagen_je_inv={D: {"ladung_pv_kwh": 50.0, "ladung_netz_kwh": 50.0,
                                   "verbrauch_kwh": 160.0}},
           dienstliche_wallbox_je_inv={7: {"ladung_kwh": 120.0, "ladung_pv_kwh": 20.0}},
           dienstliche_wallbox_in_betrieb=True)
    assert set(e.dienstlich_je_inv) == {7}
    assert e.dienstlich_je_inv[7].netz_kwh == pytest.approx(100.0)
    assert e.je_auto[B].ladung_kwh == pytest.approx(400.0), "nichts vom Rest abgezogen"


def test_s2_3_zwei_private_wallboxen_addiert():
    e = _e({A: A_GEMESSEN, B: B_OHNE},
           wallboxen=({"ladung_kwh": 250.0, "ladung_pv_kwh": 100.0},
                      {"ladung_kwh": 150.0, "ladung_pv_kwh": 100.0}))
    assert e.wallbox_summe.ladung_kwh == pytest.approx(400.0)
    assert e.je_auto[B].ladung_kwh == pytest.approx(300.0)


def test_s2_3_w1_nur_eine_wallbox_ist_das_private_auto():
    """W-1 (Master 26.09., Konzept Regel 2 Schritt 3): weder privates Auto noch Dienstwagen."""
    e = _e({}, wallboxen=({"ladung_kwh": 200.0, "ladung_pv_kwh": 120.0},))
    assert (e.pool.ladung_kwh, e.pool.pv_kwh) == (pytest.approx(200.0), pytest.approx(120.0))
    assert e.rest_nicht_zugeordnet_kwh == pytest.approx(0.0)


def test_s2_3_w1_wallbox_mit_dienstwagen_ohne_privates_auto_bleibt_nicht_zugeordnet():
    e = _e({}, wallboxen=({"ladung_kwh": 200.0, "ladung_pv_kwh": 120.0},),
           dienstwagen_je_inv={D: {"km_gefahren": 500.0, "verbrauch_kwh": 90.0}})
    assert e.pool.ladung_kwh == pytest.approx(0.0)
    assert e.rest_nicht_zugeordnet_kwh == pytest.approx(200.0)
    assert (e.dienstlich_je_inv[D].netz_kwh, e.dienstlich_je_inv[D].gemessen) == (90.0, False)
    # auch ein Dienstwagen ohne Monatszeile ist ein bekannter Nutznießer
    ohne_zeile = _e({}, wallboxen=({"ladung_kwh": 200.0},), dienstwagen_in_betrieb=[D])
    assert ohne_zeile.pool.ladung_kwh == pytest.approx(0.0)


def test_s2_3_privates_auto_ohne_monatszeile_ist_empfaenger_des_rests():
    """`eauto_in_betrieb`: ein Auto in Betrieb ohne Zeile bekommt den Rest (0 km, E6)."""
    e = _e({}, eauto_in_betrieb=[B])
    assert e.je_auto[B].ladung_kwh == pytest.approx(400.0)
    assert e.pool.ladung_kwh == pytest.approx(400.0)


# ── Über die Schicht (Herkunft, „in Betrieb", CO₂) ───────────────────────────

from backend.models.investition import InvestitionMonatsdaten  # noqa: E402
from backend.services.monats_co2 import co2_bilanz_aus_fakt  # noqa: E402
from backend.core.calculations import co2_emob_ersparnis_kg  # noqa: E402
from backend.services.eauto_wirtschaftlichkeit import km_gewichtete_eauto_params  # noqa: E402
from backend.services.monats_fakten import lade_monats_fakten  # noqa: E402

PROV_FORM = {"verbrauch_daten.ladung_kwh": {"source": "manual:form"}}
PROV_ALT = {"verbrauch_daten.ladung_kwh": {"source": "legacy:unknown"}}


async def _r2_anlage(db, *, mit_b=True, prov_d=PROV_FORM):
    a, invs = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "A", False),
                            ("e-auto", "D", True), *([("e-auto", "B", False)] if mit_b else []))
    wb, a_, d = invs[:3]
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=6, verbrauch_daten=WB_400))
    db.add(InvestitionMonatsdaten(investition_id=a_.id, jahr=2026, monat=6, verbrauch_daten=A_GEMESSEN))
    db.add(InvestitionMonatsdaten(investition_id=d.id, jahr=2026, monat=6,
                                  verbrauch_daten=DW_HEIM_GESAMT, source_provenance=prov_d))
    if mit_b:
        db.add(InvestitionMonatsdaten(investition_id=invs[3].id, jahr=2026, monat=6,
                                      verbrauch_daten=B_OHNE))
    await db.commit()
    return a, invs


@pytest.mark.asyncio
async def test_s2_3_schicht_und_co2_rechnen_mit_der_privaten_heimladung(db):
    """G1-Probe des Auftrags: die CO₂-Bilanz sieht E-Mob-Netzladung 125, nicht 200."""
    a, invs = await _r2_anlage(db)
    (fakt,) = [f for f in await lade_monats_fakten(db, a.id) if f.schluessel == (2026, 6)]
    assert fakt.emob.ladung_netz_kwh == pytest.approx(125.0)
    assert fakt.emob.ladung_kwh == pytest.approx(250.0)
    assert fakt.emob.wallbox_summe.ladung_kwh == pytest.approx(400.0)
    params = {i.id: i.parameter for i in invs}
    bilanz = co2_bilanz_aus_fakt(fakt, params)
    vergleich, _ = km_gewichtete_eauto_params(eauto_params_und_km=[
        (params.get(i), km) for i, km in fakt.emob.km_je_fahrzeug.items()
    ])
    benzin = fakt.emob.km / 100 * vergleich
    assert bilanz.co2_emob_kg == pytest.approx(co2_emob_ersparnis_kg(benzin, 125.0, fakt.emob.km))
    assert bilanz.co2_emob_kg != pytest.approx(co2_emob_ersparnis_kg(benzin, 200.0, fakt.emob.km))


@pytest.mark.asyncio
async def test_s2_3_schicht_altwert_am_dienstwagen_ist_keine_messung(db):
    """Herkunft `legacy:unknown` ⇒ alter Gesamtwert: neben der Wallbox keine Messung (Regel 8)."""
    a, _ = await _r2_anlage(db, mit_b=False, prov_d=PROV_ALT)
    (fakt,) = [f for f in await lade_monats_fakten(db, a.id) if f.schluessel == (2026, 6)]
    # D trägt nur den alten Gesamtwert ⇒ keine eigene Messung ⇒ nichts vom Rest abgezogen:
    # Rest = 400 − A 100 = 300, ohne Empfänger (A ist gemessen) nicht zugeordnet. Mit
    # Herkunft `manual:form` wären es 150 (s. Beispiel oben).
    assert fakt.emob.dienstwagen_gemessen == frozenset()
    assert fakt.emob.rest_zugeordnet is False
    assert fakt.emob.rest_pv_kwh + fakt.emob.rest_netz_kwh == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_s2_3_schicht_auto_ohne_monatszeile_bekommt_den_rest(db):
    a, invs = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "A", False))
    db.add(InvestitionMonatsdaten(investition_id=invs[0].id, jahr=2026, monat=6, verbrauch_daten=WB_400))
    await db.commit()
    (fakt,) = [f for f in await lade_monats_fakten(db, a.id) if f.schluessel == (2026, 6)]
    assert fakt.emob.ladung_kwh == pytest.approx(400.0)
    assert fakt.emob.je_auto[invs[1].id].art == ART_REST


@pytest.mark.asyncio
async def test_s2_3_nf1_wallbox_hub_kwh_ist_die_wallbox_ersparnis_der_topf(db):
    """NF-1 (Master 26.09.): Kachel = Messung der Wallbox, Ersparnis/Amortisation = Topf."""
    from backend.api.routes.investitionen.dashboard_wallbox import get_wallbox_dashboard
    a, _ = await _r2_anlage(db)
    (karte,) = await get_wallbox_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung
    assert z["gesamt_heim_ladung_kwh"] == pytest.approx(400.0)
    assert z["heim_als_extern_kosten_euro"] == pytest.approx(250.0 * 0.50)


# ═════════════════════════════════════════════════════════════════════════════
# S2-4 — Phase 5 je Zeile (Konzept Regel 2 Schritt 2; Fable-Runde 5 #3)
# ═════════════════════════════════════════════════════════════════════════════

from backend.services.emob_ladeanteil import (  # noqa: E402
    braucht_tages_quote,
    reichere_ladezeilen_an,
)


def test_s2_4_auto_zeile_nur_mit_heim_netz_bleibt_unangetastet():
    """Ohne Wallbox: eine Zeile mit nur „Heim: Netz" bekommt keinen erfundenen PV-Anteil."""
    ea, _wb, abgeleitet = reichere_ladezeilen_an(
        eauto_daten=[{"ladung_kwh": 100.0, "ladung_netz_kwh": 100.0}, {"ladung_kwh": 50.0}],
        wallbox_daten=[], quote=0.6,
    )
    assert "ladung_pv_kwh" not in ea[0]
    assert ea[1]["ladung_pv_kwh"] == pytest.approx(30.0), "die Zeile ohne Aufteilung wird abgeleitet"
    assert abgeleitet is True


def test_s2_4_auto_neben_wallbox_wird_nicht_angereichert():
    """Neben einer Wallbox teilt die eine Funktion „Heim: gesamt" mit dem Wallbox-Anteil."""
    ea, wb, _ = reichere_ladezeilen_an(
        eauto_daten=[{"ladung_kwh": 50.0}], wallbox_daten=[{"ladung_kwh": 200.0}], quote=0.6,
    )
    assert "ladung_pv_kwh" not in ea[0]
    assert wb[0]["ladung_pv_kwh"] == pytest.approx(120.0)
    # „in Betrieb" ohne Zeile zählt ebenso
    ea2, _, _ = reichere_ladezeilen_an(
        eauto_daten=[{"ladung_kwh": 50.0}], wallbox_daten=[], quote=0.6, wallbox_in_betrieb=True,
    )
    assert "ladung_pv_kwh" not in ea2[0]


def test_s2_4_die_quote_wird_je_zeile_gebraucht():
    """Ein Auto mit „Heim: PV" daneben sperrt die Quote für das zweite nicht mehr."""
    assert braucht_tages_quote([{"ladung_pv_kwh": 20.0}, {"ladung_kwh": 50.0}]) is True
    assert braucht_tages_quote([{"ladung_pv_kwh": 20.0, "ladung_netz_kwh": 5.0}]) is False


# ═════════════════════════════════════════════════════════════════════════════
# S2-5 — die `km > 0`-Tore sind gefallen (Konzept Regel 2, E6)
# ═════════════════════════════════════════════════════════════════════════════
#
# Ein Auto mit eigener Messung, das im Zeitraum nicht gefahren ist (0 km), trägt seine
# Stromrechnung. Differenzprobe je Sicht: dieselbe Anlage einmal mit 100 kWh Netzladung
# am Auto (Wallbox 100, alles Netz), einmal mit 0 — die Ersparnis muss sich um die
# Stromkosten unterscheiden. Mit einem Tor wären beide gleich.

from backend.models.monatsdaten import Monatsdaten  # noqa: E402
from backend.models.strompreis import Strompreis  # noqa: E402


async def _anlage_ohne_km(db, netz_kwh: float):
    a, invs = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "Steher", False))
    wb, auto = invs
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=6,
                                  verbrauch_daten={"ladung_kwh": netz_kwh, "ladung_pv_kwh": 0.0}))
    db.add(InvestitionMonatsdaten(investition_id=auto.id, jahr=2026, monat=6,
                                  verbrauch_daten={"km_gefahren": 0.0, "ladung_pv_kwh": 0.0,
                                                   "ladung_netz_kwh": netz_kwh}))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=100.0,
                       netzbezug_kwh=300.0, pv_erzeugung_kwh=500.0))
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    await db.commit()
    return a, auto


@pytest.mark.asyncio
async def test_s2_5_uebersicht_gemessenes_auto_ohne_km_traegt_seine_stromrechnung(db):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    a100, _ = await _anlage_ohne_km(db, 100.0)
    a0, _ = await _anlage_ohne_km(db, 0.0)
    mit = await get_cockpit_uebersicht(anlage_id=a100.id, jahr=None, db=db)
    ohne = await get_cockpit_uebersicht(anlage_id=a0.id, jahr=None, db=db)
    assert mit.emob_ersparnis_euro < ohne.emob_ersparnis_euro - 1.0


@pytest.mark.asyncio
async def test_s2_5_t_konto_gemessenes_auto_ohne_km_traegt_seine_stromrechnung(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    a100, _ = await _anlage_ohne_km(db, 100.0)
    res = await get_aktueller_monat(anlage_id=a100.id, jahr=2026, monat=6, db=db)
    zeile = next(f for f in res.investitionen_financials if f.bezeichnung == "Steher")
    assert zeile.ersparnis_euro is not None and zeile.ersparnis_euro < 0


def test_s2_5_monatsanteil_gemessenes_auto_ohne_km():
    """Der Monatsanteil (`emob_heimladung_im_monat` → `je_auto`) kennt kein km-Tor."""
    from backend.services.eauto_wirtschaftlichkeit import build_emob_pool_ctx, emob_heimladung_im_monat
    daten = {(1, 2026, 6): {"km_gefahren": 0.0, "ladung_netz_kwh": 100.0},
             (9, 2026, 6): {"ladung_kwh": 100.0}}
    ctx = build_emob_pool_ctx(daten, {1}, {9})
    assert emob_heimladung_im_monat(ctx, 1, 0.0, 2026, 6, daten[(1, 2026, 6)]) == (0.0, 100.0)


@pytest.mark.asyncio
async def test_s2_5_ha_export_gemessenes_auto_ohne_km_traegt_seine_stromrechnung(db, monkeypatch):
    """HA-Export: `bisherige_eauto_ersparnis` (Phase `alternativkosten_und_co2`) — sie speist
    ROI und Amortisation. Mitgeschnitten an der Phasen-Grenze des Orchestrators."""
    from backend.api.routes.ha_export import anlage_sensoren, calculate_anlage_sensors
    echt = anlage_sensoren.alternativkosten_und_co2
    gesehen: list[float] = []

    def mitschnitt(**kw):
        out = echt(**kw)
        gesehen.append(out["bisherige_eauto_ersparnis"])
        return out

    monkeypatch.setattr(anlage_sensoren, "alternativkosten_und_co2", mitschnitt)
    for netz in (100.0, 0.0):
        a, _ = await _anlage_ohne_km(db, netz)
        await calculate_anlage_sensors(db, a)
    assert gesehen[0] == pytest.approx(-30.0), "100 kWh × 30 ct — die Stromrechnung bleibt"
    assert gesehen[1] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_s2_5_aussichten_gemessenes_auto_ohne_km_traegt_seine_stromrechnung(db):
    from backend.api.routes.aussichten import get_finanz_prognose
    werte = {}
    for netz in (100.0, 0.0):
        a, _ = await _anlage_ohne_km(db, netz)
        werte[netz] = (await get_finanz_prognose(anlage_id=a.id, monate=12, db=db)).bisherige_ertraege_euro
    assert werte[100.0] < werte[0.0] - 1.0


@pytest.mark.asyncio
async def test_s2_5_leser_nehmen_auch_monate_ohne_zeile_des_autos(db):
    """`monate_des_autos`: der E-Auto-Hub zeigt den Rest, den das Auto ohne eigene Zeile
    bekommt — sonst gingen Topf und Summe der Fahrzeuge auseinander."""
    from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
    a, invs = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "OhneZeile", False))
    db.add(InvestitionMonatsdaten(investition_id=invs[0].id, jahr=2026, monat=6,
                                  verbrauch_daten=WB_400))
    await db.commit()
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    assert karte.zusammenfassung["ladung_netz_kwh"] == pytest.approx(200.0)
    assert karte.zusammenfassung["ladung_pv_kwh"] == pytest.approx(200.0)


# ═════════════════════════════════════════════════════════════════════════════
# S2-6 — Daten-Checker Regel 7 (Toleranz max(10 kWh, 10 %), E7)
# ═════════════════════════════════════════════════════════════════════════════

#: Fester Stichtag der Checker-Proben — das Fenster ist die letzten 12 Monate davor
#: (keine Probe liest die echte Uhr, N-167).
CHECK_HEUTE = date(2026, 7, 15)


def _vormonat() -> tuple[int, int]:
    return (2026, 6)


async def _checker(db, anlage_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from backend.services.daten_checker import DatenChecker
    a = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )).scalar_one()
    return DatenChecker(db)._check_emob_pool_pflege(a, heute=CHECK_HEUTE)


async def _checker_anlage(db, wb_daten, autos, *, sensor_mapping=None, dienstliche_wallbox=None):
    """``autos`` = [(bez, dienstlich, verbrauch_daten, provenance)]."""
    j, m = _vormonat()
    geraete = [("wallbox", "WB", False)] + [("e-auto", b, d) for b, d, _, _ in autos]
    if dienstliche_wallbox is not None:
        geraete.append(("wallbox", "WB-Firma", True))
    a, invs = await _anlage(db, *geraete)
    if wb_daten is not None:
        db.add(InvestitionMonatsdaten(investition_id=invs[0].id, jahr=j, monat=m, verbrauch_daten=wb_daten))
    for inv, (_b, _d, daten, prov) in zip(invs[1:], autos):
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=j, monat=m,
                                      verbrauch_daten=daten, source_provenance=prov))
    if dienstliche_wallbox is not None:
        db.add(InvestitionMonatsdaten(investition_id=invs[-1].id, jahr=j, monat=m,
                                      verbrauch_daten=dienstliche_wallbox))
    if sensor_mapping is not None:
        a.sensor_mapping = sensor_mapping(invs)
    await db.commit()
    return await _checker(db, a.id)


@pytest.mark.asyncio
async def test_s2_6_autos_mehr_als_die_wallbox_warnt(db):
    erg = await _checker_anlage(db, {"ladung_kwh": 100.0}, [
        ("A", False, {"ladung_pv_kwh": 100.0, "ladung_netz_kwh": 200.0}, None)])
    assert [e.schwere for e in erg] == ["warning"]
    assert "300" in erg[0].details and "100" in erg[0].details
    assert "Steckdose" in erg[0].details and "unterwegs" in erg[0].details


@pytest.mark.asyncio
async def test_s2_6_gemessener_dienstwagen_zaehlt_in_den_ueberschuss(db):
    erg = await _checker_anlage(db, {"ladung_kwh": 100.0}, [
        ("A", False, {"ladung_netz_kwh": 80.0}, None),
        ("D", True, {"ladung_netz_kwh": 80.0, "km_gefahren": 500.0}, None)])
    assert [e.schwere for e in erg] == ["warning"]


@pytest.mark.parametrize("wallbox, autos", [(50.0, 59.0), (400.0, 430.0)])
@pytest.mark.asyncio
async def test_s2_6_ueberschuss_innerhalb_der_toleranz_still(db, wallbox, autos):
    """9 kWh bei 50 (< 10 kWh) und 30 kWh bei 400 (< 10 %) melden nichts."""
    erg = await _checker_anlage(db, {"ladung_kwh": wallbox}, [
        ("A", False, {"ladung_netz_kwh": autos}, None)])
    assert erg == []


@pytest.mark.asyncio
async def test_s2_6_wallbox_leer_still(db):
    erg = await _checker_anlage(db, None, [("A", False, {"ladung_netz_kwh": 300.0}, None)])
    assert erg == []


@pytest.mark.asyncio
async def test_s2_6_reiner_schaetzfall_still(db):
    erg = await _checker_anlage(db, {"ladung_kwh": 100.0}, [
        ("A", False, {"km_gefahren": 800.0, "verbrauch_kwh": 400.0}, None)])
    assert erg == []


@pytest.mark.asyncio
async def test_s2_6_altwert_neben_wallbox_still(db):
    """`ladung_kwh` mit Herkunft `legacy:unknown` ist keine Messung (Regel 8)."""
    erg = await _checker_anlage(db, {"ladung_kwh": 100.0}, [
        ("A", False, {"ladung_kwh": 500.0}, PROV_ALT)])
    assert erg == []
    # Gegenprobe: dieselbe Zahl als „Heim: gesamt" (Herkunft Formular) meldet
    erg2 = await _checker_anlage(db, {"ladung_kwh": 100.0}, [
        ("A", False, {"ladung_kwh": 500.0}, PROV_FORM)])
    assert [e.schwere for e in erg2] == ["warning"]


@pytest.mark.asyncio
async def test_s2_6_schon_gemeldete_doppel_entity_still(db):
    def mapping(invs):
        return {"investitionen": {
            str(invs[0].id): {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb"}}},
            str(invs[1].id): {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb"}}},
        }}
    erg = await _checker_anlage(db, {"ladung_kwh": 100.0}, [
        ("A", False, {"ladung_kwh": 300.0}, PROV_FORM)], sensor_mapping=mapping)
    assert erg == []


@pytest.mark.asyncio
async def test_s2_6_heimladung_am_dienstwagen_fehlt_hinweis(db):
    erg = await _checker_anlage(db, {"ladung_kwh": 300.0}, [
        ("A", False, {"km_gefahren": 800.0}, None),
        ("Firmenwagen", True, {"km_gefahren": 1200.0}, None)])
    assert [e.schwere for e in erg] == ["info"]
    assert "Firmenwagen" in erg[0].meldung
    assert "trägt 0 ein" in erg[0].details


@pytest.mark.asyncio
async def test_s2_6_dienstwagen_mit_0_oder_ohne_fahrt_oder_dienstlicher_wallbox_still(db):
    mit_null = await _checker_anlage(db, {"ladung_kwh": 300.0}, [
        ("Firmenwagen", True, {"km_gefahren": 1200.0, "ladung_netz_kwh": 0.0}, None)])
    assert mit_null == []
    ohne_fahrt = await _checker_anlage(db, {"ladung_kwh": 300.0}, [
        ("Firmenwagen", True, {"km_gefahren": 0.0}, None)])
    assert ohne_fahrt == []
    wallbox_0 = await _checker_anlage(db, {"ladung_kwh": 0.0}, [
        ("Firmenwagen", True, {"km_gefahren": 1200.0}, None)])
    assert wallbox_0 == []
    firma = await _checker_anlage(db, {"ladung_kwh": 300.0}, [
        ("Firmenwagen", True, {"km_gefahren": 1200.0}, None)],
        dienstliche_wallbox={"ladung_kwh": 200.0})
    assert firma == []


# ═════════════════════════════════════════════════════════════════════════════
# S2-7 — Community E3 (das Wallbox-Feld trägt nur die private Ladung)
# ═════════════════════════════════════════════════════════════════════════════

async def _community(db, wb_daten, autos, *, dienstliche_wallbox=None):
    """``autos`` = [(bez, dienstlich, verbrauch_daten, provenance)] — Monat 06/2026."""
    from backend.services.community_service import prepare_community_data
    geraete = [("pv-module", "Dach", False), ("wallbox", "WB", False)]
    geraete += [("e-auto", b, d) for b, d, _, _ in autos]
    if dienstliche_wallbox is not None:
        geraete.append(("wallbox", "WB-Firma", True))
    a, invs = await _anlage(db, *geraete)
    invs[0].leistung_kwp = 10.0
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=invs[0].id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=invs[1].id, jahr=2026, monat=6, verbrauch_daten=wb_daten))
    for inv, (_b, _d, daten, prov) in zip(invs[2:], autos):
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2026, monat=6,
                                      verbrauch_daten=daten, source_provenance=prov))
    if dienstliche_wallbox is not None:
        db.add(InvestitionMonatsdaten(investition_id=invs[-1].id, jahr=2026, monat=6,
                                      verbrauch_daten=dienstliche_wallbox))
    await db.commit()
    data = await prepare_community_data(db, a.id)
    return data["monatswerte"][0]


WB_E3 = {"ladung_kwh": 400.0, "ladung_pv_kwh": 200.0, "ladevorgaenge": 20}


@pytest.mark.asyncio
async def test_s2_7_dienstwagen_gemessen_kuerzt_beide_wallbox_felder(db):
    mw = await _community(db, WB_E3, [
        ("A", False, {"km_gefahren": 1000.0}, None),
        ("D", True, {"km_gefahren": 800.0, "ladung_kwh": 150.0}, PROV_FORM)])
    # Dienstwagen „Heim: gesamt" 150 mit dem Wallbox-Anteil 50 % ⇒ 75 PV / 75 Netz
    assert mw["wallbox_ladung_kwh"] == pytest.approx(250.0)
    assert mw["wallbox_ladung_pv_kwh"] == pytest.approx(125.0)
    assert mw["wallbox_ladung_pv_kwh"] <= mw["wallbox_ladung_kwh"], "PV-Anteil ≤ 100 %"
    assert "wallbox_ladevorgaenge" not in mw, "Dienstwagen kann an der Wallbox geladen haben"


@pytest.mark.asyncio
async def test_s2_7_dienstwagen_ohne_messung_wallbox_feld_weg(db):
    mw = await _community(db, WB_E3, [
        ("A", False, {"km_gefahren": 1000.0}, None),
        ("D", True, {"km_gefahren": 800.0, "verbrauch_kwh": 150.0}, None)])
    assert "wallbox_ladung_kwh" not in mw and "wallbox_ladung_pv_kwh" not in mw
    assert "wallbox_ladevorgaenge" not in mw


@pytest.mark.asyncio
async def test_s2_7_kein_dienstwagen_wallbox_ganz(db):
    mw = await _community(db, WB_E3, [("A", False, {"km_gefahren": 1000.0}, None)])
    assert mw["wallbox_ladung_kwh"] == pytest.approx(400.0)
    assert mw["wallbox_ladung_pv_kwh"] == pytest.approx(200.0)
    assert mw["wallbox_ladevorgaenge"] == 20


@pytest.mark.asyncio
async def test_s2_7_rest_kleiner_gleich_0_feld_weg_nie_negativ(db):
    """Schema `ge=0`: ein negativer Wert wiese den ganzen Submit ab."""
    mw = await _community(db, WB_E3, [
        ("D", True, {"km_gefahren": 800.0, "ladung_pv_kwh": 300.0, "ladung_netz_kwh": 200.0}, None)])
    assert "wallbox_ladung_kwh" not in mw and "wallbox_ladung_pv_kwh" not in mw
    assert all(v >= 0 for v in mw.values() if isinstance(v, (int, float)))


@pytest.mark.asyncio
async def test_s2_7_ladevorgaenge_bleiben_bei_dienstlicher_wallbox(db):
    mw = await _community(db, WB_E3, [
        ("A", False, {"km_gefahren": 1000.0}, None),
        ("D", True, {"km_gefahren": 800.0}, None)], dienstliche_wallbox={"ladung_kwh": 100.0})
    assert mw["wallbox_ladung_kwh"] == pytest.approx(400.0)
    assert mw["wallbox_ladevorgaenge"] == 20


@pytest.mark.asyncio
async def test_s2_7_e_auto_seite_nur_private_messwerte_keine_schaetzung(db):
    mw = await _community(db, WB_E3, [
        ("A", False, {"km_gefahren": 1000.0, "verbrauch_kwh": 180.0}, None),
        ("B", False, {"km_gefahren": 500.0, "ladung_pv_kwh": 30.0, "ladung_netz_kwh": 20.0}, None),
        ("D", True, {"km_gefahren": 800.0, "ladung_kwh": 150.0}, PROV_FORM)])
    assert mw["eauto_ladung_gesamt_kwh"] == pytest.approx(50.0), "nur B gemessen, kein Rest, kein Dienstwagen"
    assert mw["eauto_ladung_pv_kwh"] == pytest.approx(30.0)


# ═════════════════════════════════════════════════════════════════════════════
# S2-8 — Regel 8 „in Betrieb" an der letzten Stelle (`live_sensor_config`)
# ═════════════════════════════════════════════════════════════════════════════

def test_s2_8_wallbox_verdraengt_das_auto_nur_wenn_sie_am_tag_in_betrieb_ist():
    from backend.models.investition import Investition as Inv
    from backend.services.live_sensor_config import baue_investitions_serien
    wb = Inv(id=1, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2026, 7, 1), aktiv=True)
    ea = Inv(id=2, typ="e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    live = {"1": {"leistung_w": "sensor.wb_w"}, "2": {"leistung_w": "sensor.auto_w"}}
    invs = {"1": wb, "2": ea}
    vorher, _ = baue_investitions_serien(live, invs, tag=date(2026, 6, 15))
    danach, _ = baue_investitions_serien(live, invs, tag=date(2026, 7, 15))
    assert {s.kategorie for s in vorher} == {"wallbox", "eauto"}, "vor der Anschaffung zählt das Auto"
    assert {s.kategorie for s in danach} == {"wallbox"}
    # ohne Tag (Aufrufer hat schon gefiltert) wie bisher
    ohne, _ = baue_investitions_serien(live, invs)
    assert {s.kategorie for s in ohne} == {"wallbox"}


def test_s2_8_live_pfad_reicht_seinen_tag_durch():
    """Der Live-/Vortags-Pfad baut die Serien für EINEN Tag — er muss ihn übergeben
    (sonst lädt er „heute aktive" Investitionen und die Regel fragt wieder „vorhanden").
    Quelltext-Probe nach dem Muster von `test_serien_aufbau_symmetrie_m1.py`."""
    import inspect
    from backend.services import live_tagesverlauf_service as svc
    src = inspect.getsource(svc)
    assert "baue_investitions_serien(\n        inv_live_map, investitionen, tag=start.date()," in src


def test_s2_7_dienstwagen_in_betrieb_ohne_zeile_ist_ungemessen():
    """Master 26.09.: ein Dienstwagen in Betrieb ohne Monatszeile hat keine eigene Messung."""
    e = _e({A: A_GEMESSEN}, dienstwagen_in_betrieb=[D])
    assert D in e.dienstwagen_ungemessen
    assert D not in e.dienstlich_je_inv, "keine dienstliche Menge (Fahrverbrauch unbekannt)"
    assert e.rest_nicht_zugeordnet_kwh == pytest.approx(300.0), "kein Abzug vom Rest"
    # neben einer dienstlichen Wallbox in Betrieb nicht (dort ist sie die dienstliche Ladung)
    firma = _e({A: A_GEMESSEN}, dienstwagen_in_betrieb=[D],
               dienstliche_wallbox_je_inv={7: {"ladung_kwh": 50.0}}, dienstliche_wallbox_in_betrieb=True)
    assert D not in firma.dienstwagen_ungemessen


@pytest.mark.asyncio
async def test_s2_7_dienstwagen_ohne_zeile_wallbox_feld_weg(db):
    from backend.services.community_service import prepare_community_data
    a, invs = await _anlage(db, ("pv-module", "Dach", False), ("wallbox", "WB", False),
                            ("e-auto", "A", False), ("e-auto", "D", True))
    invs[0].leistung_kwp = 10.0
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=invs[0].id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=invs[1].id, jahr=2026, monat=6, verbrauch_daten=WB_E3))
    db.add(InvestitionMonatsdaten(investition_id=invs[2].id, jahr=2026, monat=6,
                                  verbrauch_daten={"km_gefahren": 1000.0}))
    await db.commit()  # der Dienstwagen D hat KEINE Monatszeile
    mw = (await prepare_community_data(db, a.id))["monatswerte"][0]
    assert "wallbox_ladung_kwh" not in mw and "wallbox_ladung_pv_kwh" not in mw
    assert "wallbox_ladevorgaenge" not in mw


@pytest.mark.asyncio
async def test_s2_6_dienstwagen_ohne_zeile_hinweis_schweigt(db):
    """E7 sieht denselben Fall: ohne Zeile hat der Dienstwagen 0 km ⇒ „gefahren" ist nicht
    erfüllt, der Hinweis schweigt (Konzept Regel 7: nur wenn der Dienstwagen gefahren ist)."""
    erg = await _checker_anlage(db, {"ladung_kwh": 300.0}, [("A", False, {"km_gefahren": 800.0}, None)])
    assert erg == []
    from sqlalchemy import select
    a_id = (await db.execute(select(Anlage.id).order_by(Anlage.id.desc()))).scalars().first()
    db.add(Investition(anlage_id=a_id, typ="e-auto", bezeichnung="D-ohne-Zeile",
                       anschaffungsdatum=date(2024, 1, 1), parameter={"ist_dienstlich": True}))
    await db.commit()
    assert await _checker(db, a_id) == []


# ═════════════════════════════════════════════════════════════════════════════
# Nachträge der Nachmessung (F1, F2, F4; Master 26.09.)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_f1_wallbox_ersparnis_hoechstens_aus_der_messung_der_wallbox(db):
    """E2-Fall: Autos (300) > Wallbox (100) ⇒ Basis der Wallbox-Ersparnis 100, nicht 300."""
    from backend.api.routes.investitionen.dashboard_wallbox import get_wallbox_dashboard
    a, invs = await _anlage(db, ("wallbox", "WB", False), ("e-auto", "A", False))
    db.add(InvestitionMonatsdaten(investition_id=invs[0].id, jahr=2026, monat=6,
                                  verbrauch_daten={"ladung_kwh": 100.0, "ladung_pv_kwh": 0.0}))
    db.add(InvestitionMonatsdaten(investition_id=invs[1].id, jahr=2026, monat=6,
                                  verbrauch_daten={"ladung_pv_kwh": 0.0, "ladung_netz_kwh": 300.0}))
    await db.commit()
    (karte,) = await get_wallbox_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung
    assert z["gesamt_heim_ladung_kwh"] == pytest.approx(100.0)
    assert z["heim_als_extern_kosten_euro"] == pytest.approx(100.0 * 0.50), "Basis 100, nicht 300"


@pytest.mark.asyncio
async def test_f2_community_e_auto_seite_ohne_altwert_neben_wallbox(db):
    alt = await _community(db, WB_E3, [("A", False, {"km_gefahren": 800.0, "ladung_kwh": 80.0}, PROV_ALT)])
    assert "eauto_ladung_gesamt_kwh" not in alt, "Altwert neben Wallbox ist kein Messwert"
    form = await _community(db, WB_E3, [("A", False, {"km_gefahren": 800.0, "ladung_kwh": 80.0}, PROV_FORM)])
    assert form["eauto_ladung_gesamt_kwh"] == pytest.approx(80.0), "„Heim: gesamt“ mit Herkunft zählt"


@pytest.mark.asyncio
async def test_f2_community_altwert_ohne_wallbox_zaehlt(db):
    """Steckerlader: ohne Wallbox zählt der alte Gesamtwert (Regel 2)."""
    from backend.services.community_service import prepare_community_data
    a, invs = await _anlage(db, ("pv-module", "Dach", False), ("e-auto", "A", False))
    invs[0].leistung_kwp = 10.0
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=6, einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=invs[0].id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=invs[1].id, jahr=2026, monat=6,
                                  verbrauch_daten={"km_gefahren": 800.0, "ladung_kwh": 80.0},
                                  source_provenance=PROV_ALT))
    await db.commit()
    mw = (await prepare_community_data(db, a.id))["monatswerte"][0]
    assert mw["eauto_ladung_gesamt_kwh"] == pytest.approx(80.0)


def test_f4_null_km_nennt_den_gepflegten_vergleichsverbrauch():
    from backend.services.eauto_wirtschaftlichkeit import berechne_eauto_ersparnis
    erg = berechne_eauto_ersparnis(
        km_gefahren=0.0, ladung_netz_kwh=10.0, ladung_extern_euro=0.0,
        wallbox_strompreis_cent=30.0, eauto_parameter={"vergleich_verbrauch_l_100km": 5.5},
    )
    assert erg.verwendeter_verbrauch_l_100km == pytest.approx(5.5)
    assert erg.ersparnis_euro == pytest.approx(-3.0)
