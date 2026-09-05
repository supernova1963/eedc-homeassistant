"""#407 (8ear) — der Tachostand als Handeingabe, die gefahrenen Kilometer als Rechnung.

*„Warum nicht einfach den aktuellen KM Stand und das Tool zieht einfach den km
Stand von vorher ab?"* — Das ist das Zählerstand-Modell aus #377, auf das Auto
übertragen: eedc führt den **Stand**, die einzige Rechnung darauf ist
**Ende − Anfang**, und die landet als Vorschlag auf „Gefahrene km".

**Was hier gewächtert wird:**

1. Das alte Feld bleibt unverändert die **Menge** (Entscheid Gernot, 05.09.):
   `km_gefahren` ist weiter Pflicht, `km_stand` ist optional und nur Hilfe.
2. Der Stand ist **nur Handeingabe** (`nur_manuell`): der Sensorweg landet
   längst auf `km_gefahren` (HA-Statistik, MQTT-Reihe #396) — ein zweiter
   Sensor-Slot für denselben Stand wäre Doppelerfassung.
3. Ein Stand hat **keine Schätzung aus der Historie** — der Vormonat ist sein
   Anfang, nicht sein Wert. Bis 05.09.2026 bekam auch der Sonstiges-Zählerstand
   den Vormonats-Stand als Vorschlag mit Konfidenz 80: im Formular vorbelegt,
   hätte ein Klick eine Differenz von 0 gespeichert.
4. **Rückwärts gibt es nichts** — keinen Vorschlag, dafür eine Warnung. Ein
   Zähler läuft nicht rückwärts; fällt er, ist die Reihe gebrochen (#377).
5. Der Monatsabschluss-Status liefert den **Anfang** mit (`stand_vormonat`),
   damit der Client die Differenz zeigt, während der Anwender tippt.

Schwesterdateien: test_377_zaehlerstaende.py (das Modell, das hier übertragen
wird), test_mqtt_zaehlerstand_ist_keine_monatsmenge.py (der Sensorweg für
denselben Stand).
"""

from __future__ import annotations

import pytest

from backend.core.field_definitions import (
    FELD_BEDARF,
    INVESTITION_FELDER,
    get_felder_fuer_investition,
    ist_stand_feld,
    ist_zaehler_differenz_feld,
)
from backend.services.vorschlag_service import VorschlagQuelle, VorschlagService
from backend.tests import factories


def _feld(typ: str, name: str) -> dict:
    return next(f for f in INVESTITION_FELDER[typ] if f["feld"] == name)


# ── 1 + 2: das Feld ──────────────────────────────────────────────────────────

def test_km_stand_ist_ein_stand_und_nur_handeingabe():
    f = _feld("e-auto", "km_stand")
    assert f["stand"] is True and ist_stand_feld("km_stand")
    assert f["nur_manuell"] is True
    assert f["einheit"] == "km"
    # Kein Zählerdifferenz-Feld: der Stand wird NICHT aus HA-LTS als MAX−MIN gelesen —
    # dafür ist `km_gefahren` da, und nur dort.
    assert not ist_zaehler_differenz_feld("km_stand")
    assert ist_zaehler_differenz_feld("km_gefahren")


def test_das_alte_feld_bleibt_die_pflicht_menge():
    assert FELD_BEDARF[("e-auto", "km_gefahren")] == ("pflicht", None)
    assert FELD_BEDARF[("e-auto", "km_stand")] == ("optional", None)
    felder = [f["feld"] for f in get_felder_fuer_investition("e-auto", {})]
    # Der Stand steht direkt hinter der Menge, die er füllt.
    assert felder.index("km_stand") == felder.index("km_gefahren") + 1


async def _auto_mit_staenden(db, juli, august):
    anlage = await factories.anlage(db)
    inv = await factories.investition(db, anlage.id, "e-auto")
    if juli is not None:
        await factories.imd(db, inv.id, 2026, 7, {"km_stand": juli})
    if august is not None:
        await factories.imd(db, inv.id, 2026, 8, {"km_stand": august})
    await db.commit()
    return anlage, inv


def _tacho(vorschlaege):
    return [v for v in vorschlaege if "Tachostand" in v.beschreibung]


# ── Die Rechnung ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gefahrene_km_aus_ende_minus_anfang(db):
    anlage, inv = await _auto_mit_staenden(db, juli=44_100, august=45_230)
    vs = await VorschlagService(db).get_vorschlaege(anlage.id, "km_gefahren", 2026, 8, inv.id)
    (v,) = _tacho(vs)
    assert v.wert == 1130
    assert v.quelle == VorschlagQuelle.BERECHNUNG
    assert v.konfidenz == 95
    assert v.details == {"km_stand": 45_230, "km_stand_vormonat": 44_100}
    # Er ist der beste Vorschlag — vor Jahresfahrleistung (30) und Vormonat (80).
    assert vs[0] is v


@pytest.mark.asyncio
async def test_ohne_anfang_kein_vorschlag(db):
    """Der erste Monat: Stand da, Vormonat nicht — nichts wird erfunden."""
    anlage, inv = await _auto_mit_staenden(db, juli=None, august=45_230)
    vs = await VorschlagService(db).get_vorschlaege(anlage.id, "km_gefahren", 2026, 8, inv.id)
    assert _tacho(vs) == []


@pytest.mark.asyncio
async def test_rueckwaerts_kein_vorschlag_aber_eine_warnung(db):
    anlage, inv = await _auto_mit_staenden(db, juli=45_230, august=44_100)
    svc = VorschlagService(db)
    assert _tacho(await svc.get_vorschlaege(anlage.id, "km_gefahren", 2026, 8, inv.id)) == []
    warnungen = await svc.pruefe_plausibilitaet(anlage.id, "km_stand", 44_100, 2026, 8, inv.id)
    assert [w.typ for w in warnungen] == ["zu_niedrig"]
    assert "rückwärts" in warnungen[0].meldung
    assert warnungen[0].details == {"vormonat_wert": 45_230}


@pytest.mark.asyncio
async def test_ein_steigender_stand_bekommt_keine_mengen_warnung(db):
    """Ein Tachostand liegt immer über dem Vorjahr — die „+100 %"-Warnung für
    Mengen wäre hier Dauerlärm."""
    anlage = await factories.anlage(db)
    inv = await factories.investition(db, anlage.id, "e-auto")
    await factories.imd(db, inv.id, 2025, 8, {"km_stand": 10_000})
    await factories.imd(db, inv.id, 2026, 7, {"km_stand": 44_100})
    await db.commit()
    warnungen = await VorschlagService(db).pruefe_plausibilitaet(
        anlage.id, "km_stand", 45_230, 2026, 8, inv.id
    )
    assert warnungen == []


# ── 3: kein Vormonat als Vorschlag für einen Stand ───────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("typ,feld,kategorie", [
    ("e-auto", "km_stand", None),
    ("sonstiges", "zaehlerstand", "zaehler"),
])
async def test_ein_stand_hat_keine_schaetzung_aus_der_historie(db, typ, feld, kategorie):
    anlage = await factories.anlage(db)
    params = {"sonstiges_kategorie": kategorie, "zaehler_einheit": "m³"} if kategorie else {}
    inv = await factories.investition(db, anlage.id, typ, parameter=params)
    await factories.imd(db, inv.id, 2025, 8, {feld: 100.0})
    await factories.imd(db, inv.id, 2026, 7, {feld: 500.0})
    await db.commit()
    vs = await VorschlagService(db).get_vorschlaege(anlage.id, feld, 2026, 8, inv.id)
    quellen = {v.quelle for v in vs}
    assert not quellen & {
        VorschlagQuelle.VORMONAT, VorschlagQuelle.VORJAHR, VorschlagQuelle.DURCHSCHNITT,
    }, quellen


@pytest.mark.asyncio
async def test_eine_menge_behaelt_ihre_historie(db):
    """Gegenprobe: für die Menge daneben gibt es den Vormonat weiterhin."""
    anlage = await factories.anlage(db)
    inv = await factories.investition(db, anlage.id, "e-auto")
    await factories.imd(db, inv.id, 2026, 7, {"km_gefahren": 1200})
    await db.commit()
    vs = await VorschlagService(db).get_vorschlaege(anlage.id, "km_gefahren", 2026, 8, inv.id)
    assert any(v.quelle == VorschlagQuelle.VORMONAT and v.wert == 1200 for v in vs)


# ── 5: der Anfang reist im Status mit ────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_liefert_den_anfang_nur_fuer_stand_felder(db):
    from backend.api.routes.monatsabschluss.views import get_monatsabschluss

    anlage, inv = await _auto_mit_staenden(db, juli=44_100, august=None)
    status = await get_monatsabschluss(anlage.id, 2026, 8, db)
    (auto,) = [i for i in status.investitionen if i.id == inv.id]
    je_feld = {f.feld: f for f in auto.felder}
    assert je_feld["km_stand"].stand_vormonat == 44_100
    assert je_feld["km_gefahren"].stand_vormonat is None
    # Und das Formular sieht den Stand ohne Vorbelegung: kein Vorschlag, kein
    # gespeicherter Wert — der Anwender liest ihn im Auto ab.
    assert je_feld["km_stand"].vorschlaege == []
    assert je_feld["km_stand"].aktueller_wert is None
