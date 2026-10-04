"""N-622 — „Aus HA laden" bringt den PV-Gesamtzähler unter dem Namen, den das Formular liest.

**Der Defekt (gemessen 04.10.2026).** ``MAPPING_KEY_TO_DB_FELD`` (``ha_statistics.py``) kannte den
Basis-Schlüssel ``pv_gesamt`` seit v2.5.3 nicht; ``map_sensor_values_to_fields`` reicht unbekannte
Schlüssel unverändert durch, die Route ``/monatswerte`` lieferte also ``feld: "pv_gesamt"``. Das
Formular sucht die Spalte ``pv_erzeugung_kwh`` (``MonatsdatenForm.tsx``) und blieb leer — N-534 hatte
die Vorbelegung gebaut, ihre zwei Vitest-Proben fütterten aber einen Feldnamen, den das Backend nie
sendet. Nach dem Speichern fehlte der Anlagenwert: alle Strings gemessen + BKW ohne Zähler 930 statt
1000, ein String ohne Sensor KEINE PV in Übersicht und Tabelle, Strings ohne Sensor + BKW 45 nur 45.

**Was diese Datei festhält.**

* Die Antwort der Route ``/monatswerte`` (und der zweiten Leserin ``/alle-monatswerte``) trägt den
  Anlagenzähler als ``pv_erzeugung_kwh``; ein Feld ``pv_gesamt`` gibt es nicht mehr.
* **Vertrag mit dem Client:** die Antwort für Form 1 ist bitgleich die Fixture
  ``frontend/src/test/ha-monatswerte-n622.fixture.json``, mit der die Vitest-Proben das Formular
  füttern (``test/monatsdaten-ha-vorbelegung-n534.test.tsx``, ``lib/haVergleich.test.ts``). Ändert
  sich die Antwort, wird diese Probe rot — neu schreiben mit ``N622_FIXTURE_SCHREIBEN=1``, dann die
  Vitest-Proben fahren.
* Ende zu Ende über die Einstiege: Route → Speichern wie das Formular (``create_monatsdaten`` mit dem
  vorbelegten Wert) → Cockpit → Monat, Cockpit → Übersicht, Monatstabelle: 1000 / 1000 / 1000 / 975, und
  Cockpit → Monat nennt vor und nach dem Abschluss dieselbe Zahl.
* Eine leere Zeile speichert nichts, und ein Bearbeiten ohne den Wert lässt einen gespeicherten
  Anlagenwert stehen (``exclude_unset`` der Schreibroute) — die Zusage des Hinweistexts im Formular.

Der Formularschritt selbst (die Zeile ist sichtbar, gesendet wird nur, was darin steht) ist Sache der
Vitest-Probe; hier wird er mit dem Wert nachgestellt, den das Formular aus ``basis`` übernimmt.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.models import Anlage, Investition, Monatsdaten, Strompreis

J, M = 2025, 5
FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "test" / "ha-monatswerte-n622.fixture.json"


class _SensorWert:
    def __init__(self, sensor_id: str, differenz: float):
        self.sensor_id, self.differenz = sensor_id, differenz
        self.start_wert, self.end_wert, self.einheit = 0.0, differenz, "kWh"


class _Antwort:
    def __init__(self, sensoren, jahr=J, monat=M):
        self.sensoren, self.jahr, self.monat, self.monat_name = sensoren, jahr, monat, "Mai"


class _HaStatistik:
    """Die HA-Langzeitstatistik, nachgestellt für alle Leser: Route, Monatsabschluss, Cockpit → Monat."""

    is_available = True

    def __init__(self, werte: dict[str, float]):
        self.werte = werte

    def get_monatswerte(self, sensor_ids, jahr, monat, deckel_je_sensor=None):
        return _Antwort([_SensorWert(s, self.werte[s]) for s in sensor_ids if s in self.werte], jahr, monat)

    def get_alle_monatswerte(self, sensor_ids, ab_datum=None, deckel_je_sensor=None):
        return [self.get_monatswerte(sensor_ids, J, M)]


FORMEN = {
    "alle-strings-gemessen+bkw-ohne-zaehler": (dict(sued=550.0, west=380.0, bkw=None), 1000.0),
    "ein-string-ohne-sensor": (dict(sued=550.0, west=None, bkw=None), 1000.0),
    "strings-ohne-sensor+bkw-45": (dict(sued=None, west=None, bkw=45.0), 1000.0),
    "alle-quellen-gemessen": (dict(sued=550.0, west=380.0, bkw=45.0), 975.0),
}


async def _seed(db, monkeypatch, *, sued, west, bkw) -> int:
    anlage = Anlage(anlagenname="N-622", leistung_kwp=10.8)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    s = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0,
                    anschaffungsdatum=date(2024, 1, 1))
    w = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="West", leistung_kwp=4.0,
                    anschaffungsdatum=date(2024, 1, 1))
    b = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                    anschaffungsdatum=date(2024, 1, 1))
    db.add_all([s, w, b])
    await db.flush()
    werte = {"sensor.einspeisung": 400.0, "sensor.netzbezug": 200.0, "sensor.pv_gesamt": 1000.0}
    inv_map = {}
    for inv, wert, sid in ((s, sued, "sensor.pv_sued"), (w, west, "sensor.pv_west"), (b, bkw, "sensor.balkon")):
        if wert is not None:
            werte[sid] = wert
            inv_map[str(inv.id)] = {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": sid}}}
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einspeisung"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netzbezug"},
            "pv_gesamt": {"strategie": "sensor", "sensor_id": "sensor.pv_gesamt"},
        },
        "investitionen": inv_map,
    }
    flag_modified(anlage, "sensor_mapping")
    await db.commit()
    stats = _HaStatistik(werte)
    monkeypatch.setattr("backend.api.routes.ha_statistics.get_ha_statistics_service", lambda: stats)
    monkeypatch.setattr("backend.services.ha_statistics_service.get_ha_statistics_service", lambda: stats)
    return anlage.id


async def _aus_ha_laden(db, anlage_id):
    from backend.api.routes.ha_statistics import get_monatswerte
    return await get_monatswerte(anlage_id, J, M, db)


async def test_monatswerte_liefert_den_anlagenzaehler_als_pv_erzeugung_kwh(db, monkeypatch):
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    antwort = await _aus_ha_laden(db, aid)
    felder = {b.feld: (b.feld_label, b.differenz) for b in antwort.basis}
    assert felder == {
        "einspeisung_kwh": ("Einspeisung", 400.0),
        "netzbezug_kwh": ("Netzbezug", 200.0),
        "pv_erzeugung_kwh": ("PV Erzeugung Gesamt", 1000.0),
    }


async def test_alle_monatswerte_liest_dieselbe_tabelle(db, monkeypatch):
    """Die zweite Leserin von ``MAPPING_KEY_TO_DB_FELD`` (Client-Funktion ohne Aufrufer, Route erreichbar)."""
    from backend.api.routes.ha_statistics import get_alle_monatswerte
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    antworten = await get_alle_monatswerte(aid, ab_jahr=None, ab_monat=None, db=db)
    assert [sorted(b.feld for b in a.basis) for a in antworten] == [
        ["einspeisung_kwh", "netzbezug_kwh", "pv_erzeugung_kwh"],
    ]


async def test_antwort_ist_die_fixture_der_vitest_proben(db, monkeypatch):
    """Der Vertrag mit dem Client: genau diese Form füttern die Formular- und Dialog-Proben."""
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    antwort = (await _aus_ha_laden(db, aid)).model_dump(mode="json")
    if os.environ.get("N622_FIXTURE_SCHREIBEN") == "1":
        FIXTURE.write_text(json.dumps(antwort, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gespeichert = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert antwort == gespeichert, (
        "Die Antwort von /ha-statistics/monatswerte weicht von der Fixture der Vitest-Proben ab — "
        "mit N622_FIXTURE_SCHREIBEN=1 neu schreiben und `npm run test` fahren."
    )


@pytest.mark.parametrize("form", list(FORMEN))
async def test_aus_ha_laden_speichern_abgeschlossener_monat(db, monkeypatch, form):
    """Route → Speichern wie das Formular → Cockpit → Monat / Übersicht / Tabelle; vor = nach dem Abschluss."""
    import backend.api.routes.aktueller_monat as am
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten, list_monatsdaten_aggregiert

    quellen, erwartet = FORMEN[form]
    aid = await _seed(db, monkeypatch, **quellen)
    antwort = await _aus_ha_laden(db, aid)
    basis = {b.feld: b.differenz for b in antwort.basis}

    vorher = await am.get_aktueller_monat(anlage_id=aid, jahr=J, monat=M, db=db)

    # Das Formular übernimmt `basis["pv_erzeugung_kwh"]` in die sichtbare Zeile und sendet sie.
    await create_monatsdaten(MonatsdatenCreate(
        anlage_id=aid, jahr=J, monat=M,
        einspeisung_kwh=basis["einspeisung_kwh"], netzbezug_kwh=basis["netzbezug_kwh"],
        pv_erzeugung_kwh=basis["pv_erzeugung_kwh"],
        investitionen_daten={str(i.investition_id): {f.feld: f.differenz for f in i.felder}
                             for i in antwort.investitionen},
    ), None, db)
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == aid))).scalar_one()
    assert md.pv_erzeugung_kwh == 1000.0

    nachher = await am.get_aktueller_monat(anlage_id=aid, jahr=J, monat=M, db=db)
    uebersicht = await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)
    tabelle = await list_monatsdaten_aggregiert(anlage_id=aid, jahr=J, db=db)

    assert nachher.pv_erzeugung_kwh == erwartet
    assert uebersicht.pv_erzeugung_kwh == erwartet
    assert [(z.jahr, z.monat, z.pv_erzeugung_kwh) for z in tabelle] == [(J, M, erwartet)]
    assert vorher.pv_erzeugung_kwh == nachher.pv_erzeugung_kwh
    assert vorher.eigenverbrauch_kwh == nachher.eigenverbrauch_kwh


async def test_leere_zeile_speichert_keinen_anlagenwert(db, monkeypatch):
    """Lässt der Anwender die Zeile leer, sendet das Formular nichts — dann gibt es keinen Anlagenwert."""
    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    antwort = await _aus_ha_laden(db, aid)
    basis = {b.feld: b.differenz for b in antwort.basis}
    # Wie das Formular: Gerätewerte gehen mit, die geleerte Zeile nicht. ADR-002/P7 — der Anlagenwert
    # wird nicht aus der Modul-Summe gefüllt.
    await create_monatsdaten(MonatsdatenCreate(
        anlage_id=aid, jahr=J, monat=M, einspeisung_kwh=basis["einspeisung_kwh"],
        netzbezug_kwh=basis["netzbezug_kwh"],
        investitionen_daten={str(i.investition_id): {f.feld: f.differenz for f in i.felder}
                             for i in antwort.investitionen},
    ), None, db)
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == aid))).scalar_one()
    assert md.pv_erzeugung_kwh is None


async def test_bearbeiten_ohne_den_wert_laesst_den_gespeicherten_stehen(db, monkeypatch):
    """Die Zusage im Hinweistext („bleibt bei leerem Feld stehen"): ein PUT ohne `pv_erzeugung_kwh`
    ändert den gespeicherten Anlagenwert nicht (``exclude_unset``)."""
    from backend.api.routes.monatsdaten import MonatsdatenUpdate, update_monatsdaten
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    md = Monatsdaten(anlage_id=aid, jahr=J, monat=M, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                     pv_erzeugung_kwh=990.0)
    db.add(md)
    await db.commit()
    await update_monatsdaten(md.id, MonatsdatenUpdate(einspeisung_kwh=400.0, netzbezug_kwh=200.0), None, db)
    await db.refresh(md)
    assert md.pv_erzeugung_kwh == 990.0


async def test_bestehender_monat_bekommt_den_zaehler_ueber_aus_ha_laden(db, monkeypatch):
    """Ein vor N-622 abgeschlossener Monat (ohne Anlagenwert, 930) — „Aus HA laden" → Vergleich → „HA-Werte
    übernehmen" öffnet ihn zum Bearbeiten mit der Zeile; Speichern (``PUT``) trägt den Zähler nach ⇒ 1000."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import (
        MonatsdatenCreate, MonatsdatenUpdate, create_monatsdaten, update_monatsdaten,
    )
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    antwort = await _aus_ha_laden(db, aid)
    basis = {b.feld: b.differenz for b in antwort.basis}
    geraete = {str(i.investition_id): {f.feld: f.differenz for f in i.felder} for i in antwort.investitionen}
    await create_monatsdaten(MonatsdatenCreate(
        anlage_id=aid, jahr=J, monat=M, einspeisung_kwh=400.0, netzbezug_kwh=200.0, investitionen_daten=geraete,
    ), None, db)
    assert (await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)).pv_erzeugung_kwh == 930.0
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == aid))).scalar_one()
    await update_monatsdaten(md.id, MonatsdatenUpdate(
        einspeisung_kwh=basis["einspeisung_kwh"], netzbezug_kwh=basis["netzbezug_kwh"],
        pv_erzeugung_kwh=basis["pv_erzeugung_kwh"], investitionen_daten=geraete,
    ), None, db)
    assert (await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)).pv_erzeugung_kwh == 1000.0


# ── N-622 Nacharbeit ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quelle", [None, "manual:form", "external:portal_import"],
                         ids=["ohne-provenance", "von-hand", "portal-import"])
async def test_put_mit_null_entfernt_den_gespeicherten_anlagenwert(db, monkeypatch, quelle):
    """Die geleerte Formularzeile sendet ``pv_erzeugung_kwh: null`` — die Schreibroute löscht den Wert
    (``exclude_unset`` behält ausdrücklich gesetzte Schlüssel, ``manual:form`` schlägt auch einen Import).
    Folge über den Einstieg: der Monat fällt auf die Summe der Strings zurück (1000 → 930)."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import MonatsdatenCreate, MonatsdatenUpdate, create_monatsdaten, update_monatsdaten
    from backend.services.provenance import write_with_provenance
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    antwort = await _aus_ha_laden(db, aid)
    geraete = {str(i.investition_id): {f.feld: f.differenz for f in i.felder} for i in antwort.investitionen}
    await create_monatsdaten(MonatsdatenCreate(
        anlage_id=aid, jahr=J, monat=M, einspeisung_kwh=400.0, netzbezug_kwh=200.0, investitionen_daten=geraete,
    ), None, db)
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == aid))).scalar_one()
    if quelle is None:
        md.pv_erzeugung_kwh = 1000.0
    else:
        await write_with_provenance(db, md, "pv_erzeugung_kwh", 1000.0, source=quelle, writer="probe")
    await db.commit()
    assert (await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)).pv_erzeugung_kwh == 1000.0

    # So kommt der Körper aus dem Client: JSON mit ausdrücklichem null.
    body = MonatsdatenUpdate.model_validate_json(json.dumps(
        {"einspeisung_kwh": 400.0, "netzbezug_kwh": 200.0, "pv_erzeugung_kwh": None}))
    await update_monatsdaten(md.id, body, None, db)
    await db.refresh(md)
    assert md.pv_erzeugung_kwh is None
    assert (await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)).pv_erzeugung_kwh == 930.0


async def test_monatswerte_liefert_nur_zaehlerfelder(db, monkeypatch):
    """Härtung: ``/monatswerte`` filtert wie Monatsabschluss-Vorschlag, Import-Vorschau und Sammelimport mit
    ``ist_zaehler_differenz_feld`` — ein Preis-Sensor (Basis ``strompreis``, Gerätefeld
    ``speicher_ladepreis_cent``) liefert keine Monatsspanne ins Formular. Innengeräte-Keys mit Suffix bleiben."""
    aid = await _seed(db, monkeypatch, sued=550.0, west=380.0, bkw=None)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    sp = Investition(anlage_id=aid, typ="speicher", bezeichnung="Akku", anschaffungsdatum=date(2024, 1, 1))
    db.add(sp)
    await db.flush()
    mapping = dict(anlage.sensor_mapping)
    mapping["basis"] = {**mapping["basis"], "strompreis": {"strategie": "sensor", "sensor_id": "sensor.preis"}}
    mapping["investitionen"] = {**mapping["investitionen"], str(sp.id): {"felder": {
        "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.akku_ladung"},
        "speicher_ladepreis_cent": {"strategie": "sensor", "sensor_id": "sensor.akku_preis"},
        "betriebsart_strom_kuehlen_kwh-3": {"strategie": "sensor", "sensor_id": "sensor.innen3"},
    }}}
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    await db.commit()
    from backend.api.routes import ha_statistics as route
    stats = route.get_ha_statistics_service()
    stats.werte.update({"sensor.preis": 18.5, "sensor.akku_ladung": 120.0, "sensor.akku_preis": 21.0,
                        "sensor.innen3": 33.0})
    antwort = await _aus_ha_laden(db, aid)
    assert [b.feld for b in antwort.basis] == ["einspeisung_kwh", "netzbezug_kwh", "pv_erzeugung_kwh"]
    akku = next(i for i in antwort.investitionen if i.investition_id == sp.id)
    assert {f.feld: f.differenz for f in akku.felder} == {"ladung_kwh": 120.0, "betriebsart_strom_kuehlen_kwh-3": 33.0}
