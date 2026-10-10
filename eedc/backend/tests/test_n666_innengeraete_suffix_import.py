"""N-666 — Innengeräte-Zähler mit Nummern-Suffix (``…_kwh-3``) kommen in allen HA-Monatswegen an.

**Der Defekt (gemessen 10.10.2026).** ``ist_zaehler_differenz_feld("betriebsart_strom_kuehlen_kwh-3")`` ist ``False``
— die Feld-Registry kennt nur den Basis-Key. Import-Vorschau, Sammelimport und Monatsabschluss-Vorschlag fragten am
rohen Key und ließen den Zähler eines Innengeräts still fallen; nur „Aus HA laden" löste seit N-622 über
``basis_feld_key`` auf (``test_n622_ha_monatswerte_pv_gesamtzaehler.py::test_monatswerte_liefert_nur_zaehlerfelder``).
Je Weg eine Probe: der Wert eines zugeordneten Innengeräte-Zählers erscheint (Vorschau), wird gespeichert
(Sammelimport) bzw. vorgeschlagen (Monatsabschluss).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.core.betriebsmodus import BETRIEBSART_STROM_FELD, KUEHLEN
from backend.core.field_definitions import feld_je_innengeraet
from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten

JAHR, MONAT = 2025, 9
FELD = feld_je_innengeraet(BETRIEBSART_STROM_FELD[KUEHLEN], 3)
WERT = 33.0


class _Wert:
    def __init__(self, sensor_id, differenz):
        self.sensor_id, self.differenz = sensor_id, differenz


class _Monat:
    def __init__(self, sensoren):
        self.jahr, self.monat, self.monat_name, self.sensoren = JAHR, MONAT, "September", sensoren


class _Stats:
    is_available = True

    def __init__(self, werte):
        self._werte = werte

    def get_monatswerte(self, sensor_ids, jahr, monat, deckel_je_sensor=None):
        return _Monat([_Wert(s, self._werte[s]) for s in sensor_ids if s in self._werte])

    def get_alle_monatswerte(self, sensor_ids, ab_datum=None, deckel_je_sensor=None):
        return [self.get_monatswerte(sensor_ids, JAHR, MONAT)]


def _sensor(entity):
    return {"strategie": "sensor", "sensor_id": entity}


async def _anlage(db, monkeypatch, *, mit_zeile: bool) -> tuple[Anlage, Investition]:
    a = Anlage(anlagenname="N-666", leistung_kwp=10.0, sensor_mapping={
        "basis": {"einspeisung": _sensor("sensor.einsp"), "netzbezug": _sensor("sensor.netz")},
        "investitionen": {},
    })
    db.add(a)
    await db.flush()
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="Klima", anschaffungsdatum=date(2024, 1, 1),
                     parameter={"wp_art": "luft_luft",
                                "innengeraete": [{"id": 1, "bezeichnung": "Büro"},
                                                 {"id": 3, "bezeichnung": "Wohnzimmer"}]})
    db.add(wp)
    await db.flush()
    a.sensor_mapping["investitionen"][str(wp.id)] = {"felder": {FELD: _sensor("sensor.innen3")}}
    flag_modified(a, "sensor_mapping")
    if mit_zeile:
        db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=MONAT, einspeisung_kwh=100.0, netzbezug_kwh=200.0))
    await db.commit()
    stats = _Stats({"sensor.einsp": 100.0, "sensor.netz": 200.0, "sensor.innen3": WERT})
    monkeypatch.setattr("backend.api.routes.ha_statistics.get_ha_statistics_service", lambda: stats)
    return a, wp


async def test_vorschau_zeigt_den_innengeraete_zaehler(db, monkeypatch):
    from backend.api.routes.ha_statistics import get_import_vorschau

    a, wp = await _anlage(db, monkeypatch, mit_zeile=False)
    m = (await get_import_vorschau(a.id, db)).monate[0]

    eintrag = next(i for i in (m.investitionen or []) if i.investition_id == wp.id)
    assert list(eintrag.ha_werte.values()) == [WERT]


async def test_sammelimport_speichert_den_innengeraete_zaehler(db, monkeypatch):
    from backend.api.routes.ha_statistics import ImportRequest, import_ha_statistics

    a, wp = await _anlage(db, monkeypatch, mit_zeile=True)
    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    imd = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == wp.id))).scalar_one()
    assert (imd.verbrauch_daten or {}).get(FELD) == WERT


async def test_monatsabschluss_schlaegt_den_innengeraete_zaehler_vor(db, monkeypatch):
    from backend.api.routes.monatsabschluss import views

    a, wp = await _anlage(db, monkeypatch, mit_zeile=True)

    async def _ha(*_a, **_k):
        return {"sensor.einsp": 100.0, "sensor.netz": 200.0, "sensor.innen3": WERT}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, JAHR, MONAT, db=db)

    inv = next(i for i in resp.investitionen if i.id == wp.id)
    feld = next(f for f in inv.felder if f.feld == FELD)
    ha = [v if isinstance(v, dict) else v.model_dump() for v in feld.vorschlaege]
    assert [v["wert"] for v in ha if v["quelle"] == "ha_statistics"] == [WERT]
