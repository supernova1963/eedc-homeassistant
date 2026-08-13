"""N-240 — der HA-Statistik-Import sagt, wenn nur Gerätewerte entstehen.

**Der Registereintrag kannte nur die Hälfte** (gemessen 13.08.2026 an echten
Objekten). Es gibt **zwei** Wege, und sie verhielten sich unterschiedlich:

* **Basis-Felder abgewählt** — keine ``Monatsdaten``-Zeile, Gerätewerte da.
  Der Monat verschwindet aus jeder Liste, die an der Zählerzeile hängt. Stumm.
* **Basis-Felder aktiv, aber kein Zähler-Sensor zugeordnet** — hier entstand
  eine Zeile mit **0/0**: eine Einspeisung und ein Netzbezug von exakt null,
  die niemand gemessen hat. Der Plausibilitäts-Check meldete sie prompt als
  „beide 0" — eine erfundene Messung, die eine zweite Falschmeldung auslöste.

Seit 13.08. verhalten sich beide gleich und ehrlich: **keine Zeile ohne
Zählerwert**, dafür eine Warnung mit dem Weg zum Nachtragen.
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.ha_statistics import ImportRequest, import_ha_statistics
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.import_hauszaehler import warnung_monate_ohne_zaehlerwerte


# ─── Reine Textfunktion ──────────────────────────────────────────────────

def test_ohne_befund_schweigt_der_import():
    """Ein Lauf ohne Befund sagt nichts — kein „0 Warnungen"-Rauschen."""
    assert warnung_monate_ohne_zaehlerwerte([]) is None


def test_ein_monat_steht_im_singular():
    text = warnung_monate_ohne_zaehlerwerte([(2026, 5)])
    assert "Für den Monat 05/2026" in text
    assert "Dieser Monat bleibt" in text and "erscheint nicht" in text
    # Der Weg nach vorn gehört in die Meldung, nicht nur der Befund.
    assert "Monatsabschluss" in text


def test_viele_monate_werden_gekuerzt_und_gezaehlt():
    monate = [(2025, m) for m in range(1, 9)]
    text = warnung_monate_ohne_zaehlerwerte(monate)
    assert "und 2 weitere" in text
    assert "Diese Monate bleiben" in text and "erscheinen nicht" in text


def test_monate_werden_sortiert_und_entdoppelt():
    text = warnung_monate_ohne_zaehlerwerte([(2026, 5), (2025, 12), (2026, 5)])
    assert text.index("12/2025") < text.index("05/2026")
    assert text.count("05/2026") == 1


# ─── Der Import-Pfad ─────────────────────────────────────────────────────

class _Wert:
    def __init__(self, sensor_id, differenz):
        self.sensor_id, self.differenz = sensor_id, differenz


class _FakeStats:
    """LTS-Dienst mit festen Monatswerten."""

    is_available = True

    def __init__(self, werte):
        self._werte = werte

    def get_monatswerte(self, sensor_ids, jahr, monat):
        class _A:
            pass
        a = _A()
        a.sensoren = [_Wert(s, self._werte[s]) for s in sensor_ids if s in self._werte]
        return a


def _sensor(entity):
    return {"strategie": "sensor", "sensor_id": entity}


async def _anlage(db, *, mit_zaehler_sensor: bool) -> Anlage:
    basis = {"einspeisung": _sensor("sensor.einsp")} if mit_zaehler_sensor else {}
    a = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping={
        "basis": basis,
        "investitionen": {"1": {"felder": {"pv_erzeugung_kwh": _sensor("sensor.pv")}}},
    })
    db.add(a)
    await db.flush()
    db.add(Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2020, 1, 1), leistung_kwp=10.0,
    ))
    await db.flush()
    return a


def _patch_stats(monkeypatch, werte):
    monkeypatch.setattr(
        "backend.api.routes.ha_statistics.get_ha_statistics_service",
        lambda: _FakeStats(werte),
    )


async def _zeilen(db, anlage_id):
    return (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )).scalars().all()


@pytest.mark.asyncio
async def test_ohne_zaehler_sensor_entsteht_keine_null_zeile(db, monkeypatch):
    """Die Kernkorrektur: keine erfundene Messung von 0 kWh.

    Bis 13.08. legte dieser Pfad `einspeisung_kwh=0, netzbezug_kwh=0` an, weil
    „alle Basis-Felder importieren" auch dann galt, wenn gar keiner zugeordnet
    war. Der Plausibilitäts-Check meldete das anschließend als Fehler.
    """
    a = await _anlage(db, mit_zaehler_sensor=False)
    _patch_stats(monkeypatch, {"sensor.pv": 480.0})

    res = await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": 2026, "monat": 5}]), db,
    )

    assert await _zeilen(db, a.id) == []
    assert res.erfolg is True          # kein Fehler — der Lauf hat getan, was er konnte
    assert len(res.warnungen) == 1
    assert "05/2026" in res.warnungen[0]


@pytest.mark.asyncio
async def test_geraetewerte_kommen_trotzdem_an(db, monkeypatch):
    """Die Warnung ersetzt keine Daten — was gemessen wurde, wird geschrieben."""
    a = await _anlage(db, mit_zaehler_sensor=False)
    _patch_stats(monkeypatch, {"sensor.pv": 480.0})

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": 2026, "monat": 5}]), db)

    imd = (await db.execute(select(InvestitionMonatsdaten))).scalars().all()
    assert [i.verbrauch_daten.get("pv_erzeugung_kwh") for i in imd] == [480.0]


@pytest.mark.asyncio
async def test_abgewaehlte_basis_felder_melden_dasselbe(db, monkeypatch):
    """Der zweite Weg — für den Anwender derselbe Sachverhalt, also derselbe Text."""
    a = await _anlage(db, mit_zaehler_sensor=True)
    _patch_stats(monkeypatch, {"sensor.einsp": 300.0, "sensor.pv": 480.0})

    res = await import_ha_statistics(
        a.id,
        ImportRequest(monate=[{"jahr": 2026, "monat": 5, "basis_felder": []}]),
        db,
    )

    assert await _zeilen(db, a.id) == []
    assert len(res.warnungen) == 1


@pytest.mark.asyncio
async def test_mit_zaehlerwert_keine_warnung(db, monkeypatch):
    a = await _anlage(db, mit_zaehler_sensor=True)
    _patch_stats(monkeypatch, {"sensor.einsp": 300.0, "sensor.pv": 480.0})

    res = await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": 2026, "monat": 5}]), db,
    )

    zeilen = await _zeilen(db, a.id)
    assert [(z.jahr, z.monat, z.einspeisung_kwh) for z in zeilen] == [(2026, 5, 300.0)]
    assert res.warnungen == []


@pytest.mark.asyncio
async def test_gemessene_null_ist_keine_abwesenheit(db, monkeypatch):
    """Ein Zähler, der ehrlich 0 meldet, schreibt weiterhin seine Zeile.

    `is not None` statt truthiness — die 0-Falle aus CLAUDE.md. Ohne diese
    Unterscheidung verlöre eine Anlage ohne Einspeisung im Dezember ihren Monat.
    """
    a = await _anlage(db, mit_zaehler_sensor=True)
    _patch_stats(monkeypatch, {"sensor.einsp": 0.0, "sensor.pv": 12.0})

    res = await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": 2026, "monat": 12}]), db,
    )

    assert len(await _zeilen(db, a.id)) == 1
    assert res.warnungen == []


@pytest.mark.asyncio
async def test_bestehende_monatszeile_loest_keine_warnung_aus(db, monkeypatch):
    """Geprüft wird die ZEILE, nicht die Zuordnung.

    Wer den Monat im Monatsabschluss erfasst und danach Gerätewerte nachlädt,
    hat kein Problem — und soll keine Warnung bekommen.
    """
    a = await _anlage(db, mit_zaehler_sensor=False)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=5,
                       einspeisung_kwh=310.0, netzbezug_kwh=95.0))
    await db.flush()
    _patch_stats(monkeypatch, {"sensor.pv": 480.0})

    res = await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": 2026, "monat": 5}]), db,
    )

    assert res.warnungen == []


@pytest.mark.asyncio
async def test_mehrere_monate_ergeben_eine_warnung(db, monkeypatch):
    """Gesammelt statt je Monat — sonst stünde derselbe Satz zwölfmal da."""
    a = await _anlage(db, mit_zaehler_sensor=False)
    _patch_stats(monkeypatch, {"sensor.pv": 480.0})

    res = await import_ha_statistics(
        a.id,
        ImportRequest(monate=[
            {"jahr": 2026, "monat": 5},
            {"jahr": 2026, "monat": 6},
            {"jahr": 2026, "monat": 7},
        ]),
        db,
    )

    assert len(res.warnungen) == 1
    assert "05/2026" in res.warnungen[0] and "07/2026" in res.warnungen[0]
