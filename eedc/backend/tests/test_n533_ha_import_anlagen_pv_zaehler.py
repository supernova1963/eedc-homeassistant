"""N-533 (Frank85, T89667 #349): der HA-Statistik-Import kennt den Anlagen-PV-Zähler.

Bis zum 19.09.2026 zeigte die Vorschau „PV Erzeugung Gesamt", entschied „übersprungen"
aber nur über Einspeisung und Netzbezug — und der Import schrieb den Zähler nirgendwohin.
Wer nur einen gemeinsamen PV-Zähler in HA hat (Kanon „Über den Anlagen-Zählerstand
abgedeckt"), bekam Monate ohne PV: der Daten-Checker meldete „PV-Erzeugung fehlt" und
riet zu genau diesem Import. Bei Frank85 waren es 40 von 40 Monaten.

Die Regel folgt der Leseseite (ADR-002/P7, `resolve_pv_je_modul`): Module mit eigenem
Messwert behalten ihn, der Rest des Zählers geht nach kWp auf die Quellen ohne Messwert.
Und in der Vorschau ist ein Feld mit HA-Wert ohne lokalen Wert ein Import — kein „stimmt
überein".

⚑ **Seit HA-Bauform E4b Teil A (06.10.2026) speichert der Import den Zähler als Anlagenwert**
(`Monatsdaten.pv_erzeugung_kwh`) — wie „Aus HA laden" seit N-622 — statt ihn selbst auf die
Module zu verteilen. Die Auflösung geschieht beim Lesen (Monats-Fakten): dieselben Zahlen je
Modul wie vorher, dazu bekommt jetzt auch ein Balkonkraftwerk ohne eigenen Wert seinen Anteil
(N-621; vorher 0 — Ursache SAMMELIMPORT der PV-Matrix). Die Proben messen deshalb die
aufgelöste Zahl (`_aufgeloest`), nicht mehr die geschriebenen Gerätezeilen.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.ha_statistics import (
    ImportRequest,
    get_import_vorschau,
    import_ha_statistics,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.provenance import ABGELEITET_KWP_ANTEIL

JAHR, MONAT = 2023, 5
PV_LABEL = "PV Erzeugung Gesamt"


class _Wert:
    def __init__(self, sensor_id, differenz):
        self.sensor_id, self.differenz = sensor_id, differenz


class _Monat:
    def __init__(self, sensoren):
        self.jahr, self.monat, self.monat_name, self.sensoren = JAHR, MONAT, "Mai", sensoren


class _FakeStats:
    """LTS-Dienst mit festen Monatswerten — für Vorschau und Import."""

    is_available = True

    def __init__(self, werte):
        self._werte = werte

    def _sensoren(self, sensor_ids):
        return [_Wert(s, self._werte[s]) for s in sensor_ids if s in self._werte]

    def get_monatswerte(self, sensor_ids, jahr, monat, deckel_je_sensor=None):
        return _Monat(self._sensoren(sensor_ids))

    def get_alle_monatswerte(self, sensor_ids, ab_datum=None, deckel_je_sensor=None):
        return [_Monat(self._sensoren(sensor_ids))]


def _sensor(entity):
    return {"strategie": "sensor", "sensor_id": entity}


async def _anlage(db, *, module: list[tuple[str, float, str | None]]) -> tuple[Anlage, list[Investition]]:
    """Anlage mit Zähler-Sensoren; `module` = [(Name, kWp, eigener Sensor oder None)]."""
    a = Anlage(anlagenname="Frank", leistung_kwp=10.0, sensor_mapping={
        "basis": {
            "einspeisung": _sensor("sensor.einsp"),
            "netzbezug": _sensor("sensor.netz"),
            "pv_gesamt": _sensor("sensor.pv_gesamt"),
        },
        "investitionen": {},
    })
    db.add(a)
    await db.flush()
    invs = []
    for name, kwp, eigener in module:
        inv = Investition(
            anlage_id=a.id, typ="pv-module", bezeichnung=name,
            anschaffungsdatum=date(2020, 1, 1), leistung_kwp=kwp,
        )
        db.add(inv)
        await db.flush()
        if eigener:
            a.sensor_mapping["investitionen"][str(inv.id)] = {"felder": {"pv_erzeugung_kwh": _sensor(eigener)}}
        invs.append(inv)
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(a, "sensor_mapping")
    await db.flush()
    return a, invs


def _patch_stats(monkeypatch, werte):
    monkeypatch.setattr(
        "backend.api.routes.ha_statistics.get_ha_statistics_service",
        lambda: _FakeStats(werte),
    )


async def _frank_monat(db, anlage_id):
    """Die Ausgangslage des Melders: Zählerzeile da und passend, PV nirgends."""
    db.add(Monatsdaten(anlage_id=anlage_id, jahr=JAHR, monat=MONAT, einspeisung_kwh=1.2, netzbezug_kwh=345.1))
    await db.flush()


async def _modulwerte(db, invs):
    out = {}
    for inv in invs:
        imd = (await db.execute(select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id,
            InvestitionMonatsdaten.jahr == JAHR, InvestitionMonatsdaten.monat == MONAT,
        ))).scalar_one_or_none()
        out[inv.bezeichnung] = (
            (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh") if imd else None,
            ((imd.source_provenance or {}).get("verbrauch_daten.pv_erzeugung_kwh") or {}).get("abgeleitet") if imd else None,
        )
    return out


async def _aufgeloest(db, anlage_id, invs) -> dict[str, tuple[float, str]]:
    """Die PV je Modul, wie die Monats-Fakten sie auflösen (P7) — `(kWh auf 0,01, Quelle)`."""
    from backend.services.monats_fakten import lade_monats_fakten
    fakt = (await lade_monats_fakten(db, anlage_id, von=(JAHR, MONAT), bis=(JAHR, MONAT)))[0]
    namen = {inv.id: inv.bezeichnung for inv in invs}
    return {namen[i]: (round(w.pv_erzeugung_kwh, 2), w.quelle)
            for i, w in fakt.erzeugung.pv_je_modul.items() if i in namen}


async def _anlagenwert(db, anlage_id):
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id))).scalar_one()
    await db.refresh(md)
    return md.pv_erzeugung_kwh


HA = {"sensor.einsp": 1.2, "sensor.netz": 345.1, "sensor.pv_gesamt": 100.0}


async def test_vorschau_ein_fehlender_pv_wert_ist_ein_import_kein_stimmt_ueberein(db, monkeypatch):
    a, _ = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)

    vorschau = await get_import_vorschau(a.id, db)

    m = vorschau.monate[0]
    assert m.aktion == "importieren", m.grund
    assert PV_LABEL in m.grund
    assert m.ha_werte[PV_LABEL] == 100.0
    assert m.vorhandene_werte[PV_LABEL] is None
    assert vorschau.anzahl_importieren == 1 and vorschau.anzahl_ueberspringen == 0


async def test_import_speichert_den_anlagenzaehler_und_die_leseseite_verteilt_nach_kwp(db, monkeypatch):
    """E4b Teil A: der Zähler steht als Anlagenwert in der Zählerzeile; die Module bekommen beim Lesen ihren
    kWp-Anteil (60/40, verteilt). Der Import schreibt keine Gerätezeile mehr — eine zweite Ablage desselben
    Zählers neben dem Anlagenwert gibt es damit nicht (vorher: Modulwerte, KEIN Anlagenwert)."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)

    res = await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    assert res.importiert == 1 and res.fehler == []
    assert await _anlagenwert(db, a.id) == 100.0
    assert await _modulwerte(db, invs) == {"Ost": (None, None), "West": (None, None)}
    assert await _aufgeloest(db, a.id, invs) == {"Ost": (60.0, "verteilt"), "West": (40.0, "verteilt")}


async def test_nach_dem_import_stimmt_die_vorschau_ueberein(db, monkeypatch):
    a, _ = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)
    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    vorschau = await get_import_vorschau(a.id, db)

    m = vorschau.monate[0]
    assert m.aktion == "ueberspringen", m.grund
    assert m.vorhandene_werte[PV_LABEL] == 100.0


async def test_ein_modul_mit_eigenem_sensor_behaelt_seinen_messwert(db, monkeypatch):
    """P7: der Zähler füllt nur die Lücke — der gemessene String bleibt, der andere bekommt den Rest."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, "sensor.pv_ost"), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, {**HA, "sensor.pv_ost": 70.0})

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    werte = await _modulwerte(db, invs)
    assert werte["Ost"] == (70.0, None)
    # E4b: West bekommt den Rest beim Lesen (vorher als Gerätezeile ohne Marke — eine „Messung", die keine war).
    assert werte["West"] == (None, None)
    assert await _aufgeloest(db, a.id, invs) == {"Ost": (70.0, "gemessen"), "West": (30.0, "verteilt")}


async def test_ein_einzelnes_modul_bekommt_den_zaehler_beim_lesen(db, monkeypatch):
    a, invs = await _anlage(db, module=[("Dach", 10.0, None)])
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    assert (await _modulwerte(db, invs))["Dach"] == (None, None)
    assert (await _aufgeloest(db, a.id, invs))["Dach"][0] == 100.0
    assert await _anlagenwert(db, a.id) == 100.0


async def test_die_feldauswahl_kann_den_anlagenzaehler_ausschliessen(db, monkeypatch):
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)

    await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT, "basis_felder": ["Einspeisung", "Netzbezug"]}]), db,
    )

    assert (await _modulwerte(db, invs)) == {"Ost": (None, None), "West": (None, None)}
    assert await _anlagenwert(db, a.id) is None


async def test_gegenprobe_ohne_zugeordneten_anlagenzaehler_bleibt_alles_wie_bisher(db, monkeypatch):
    """Ohne `basis.pv_gesamt` im Mapping entsteht kein Modulwert und die Vorschau sagt „stimmt überein"."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    del a.sensor_mapping["basis"]["pv_gesamt"]
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(a, "sensor_mapping")
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)

    vorschau = await get_import_vorschau(a.id, db)
    assert vorschau.monate[0].aktion == "ueberspringen"
    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)
    assert (await _modulwerte(db, invs)) == {"Ost": (None, None), "West": (None, None)}


# ── N-611: der Zähler misst ALLE PV-Quellen — der eigene BKW-Wert mindert seinen Rest ──────────────


async def _mit_bkw(db, a, *, sensor: str | None):
    """Ein Balkonkraftwerk (0,8 kWp) an der Anlage, optional mit eigenem Erzeugungs-Sensor."""
    bkw = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2020, 1, 1), leistung_kwp=0.8)
    db.add(bkw)
    await db.flush()
    if sensor:
        a.sensor_mapping["investitionen"][str(bkw.id)] = {"felder": {"pv_erzeugung_kwh": _sensor(sensor)}}
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(a, "sensor_mapping")
        await db.flush()
    return bkw


async def _monat_pv(db, anlage_id):
    from backend.services.monats_fakten import lade_monats_fakten
    fakt = (await lade_monats_fakten(db, anlage_id, von=(JAHR, MONAT), bis=(JAHR, MONAT)))[0]
    return round(fakt.erzeugung.pv_kwh, 6)


async def test_n611_ein_string_und_bkw_mit_sensor_der_zaehler_fuellt_nur_den_rest(db, monkeypatch):
    """F1: Ost misst 55, das BKW 4,5, der Zähler 100 ⇒ West bekommt 40,5 (vorher 45) und der Monat 100 (vorher 104,5)."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, "sensor.pv_ost"), ("West", 4.0, None)])
    await _mit_bkw(db, a, sensor="sensor.pv_balkon")
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, {**HA, "sensor.pv_ost": 55.0, "sensor.pv_balkon": 4.5})

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    assert await _modulwerte(db, invs) == {"Ost": (55.0, None), "West": (None, None)}
    assert await _aufgeloest(db, a.id, invs) == {"Ost": (55.0, "gemessen"), "West": (40.5, "verteilt")}
    assert await _monat_pv(db, a.id) == 100.0


async def test_n611_keine_strings_und_bkw_mit_sensor(db, monkeypatch):
    """F2: kein String misst, das BKW 4,5 ⇒ 95,5 nach kWp auf Ost/West (57,3 / 38,2), der Monat 100."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _mit_bkw(db, a, sensor="sensor.pv_balkon")
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, {**HA, "sensor.pv_balkon": 4.5})

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    assert await _aufgeloest(db, a.id, invs) == {"Ost": (57.3, "verteilt"), "West": (38.2, "verteilt")}
    assert await _monat_pv(db, a.id) == 100.0


async def test_n611_ein_bkw_ohne_wert_bekommt_seinen_anteil(db, monkeypatch):
    """F6a: das BKW hat keinen Sensor. Bis E4b trugen die Module den ganzen Zähler (60/40) und das BKW bekam 0 —
    der Import speicherte keinen Anlagenwert, und N-621 gibt den Anteil nur, wo einer gespeichert ist (die Lücke
    „HA-Bauform S1"). Jetzt: 100 nach kWp auf Ost 6 · West 4 · BKW 0,8 ⇒ 55,56 / 37,04 / 7,41; der Monat bleibt 100."""
    from backend.services.monats_fakten import lade_monats_fakten

    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _mit_bkw(db, a, sensor=None)
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    assert await _aufgeloest(db, a.id, invs) == {"Ost": (55.56, "verteilt"), "West": (37.04, "verteilt")}
    fakt = (await lade_monats_fakten(db, a.id, von=(JAHR, MONAT), bis=(JAHR, MONAT)))[0]
    assert fakt.erzeugung.bkw_aus_anlagenwert_kwh == pytest.approx(100.0 * 0.8 / 10.8)
    assert await _monat_pv(db, a.id) == 100.0


async def test_n611_nach_dem_import_stimmt_die_vorschau_mit_bkw_ueberein(db, monkeypatch):
    """Die Vorschau vergleicht den Zähler mit Module + BKW — dieselbe Zahl wie die Monats-Fakten.
    Nur Module verglichen, meldete sie nach jedem korrekten Import einen Konflikt von 4,5."""
    a, _ = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _mit_bkw(db, a, sensor="sensor.pv_balkon")
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, {**HA, "sensor.pv_balkon": 4.5})
    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)

    m = (await get_import_vorschau(a.id, db)).monate[0]

    assert m.aktion == "ueberspringen", m.grund
    assert m.vorhandene_werte[PV_LABEL] == pytest.approx(100.0)


async def test_n611_die_vorschau_zeigt_den_alten_doppelt_gezaehlten_bestand_als_konflikt(db, monkeypatch):
    """Bestand aus der Zeit vor N-611 (West trägt den BKW-Anteil mit: 45 statt 40,5) ⇒ lokal 104,5 gegen
    den Zähler 100 — die Vorschau zeigt es als Abweichung, statt „stimmt überein" zu melden."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, "sensor.pv_ost"), ("West", 4.0, None)])
    bkw = await _mit_bkw(db, a, sensor="sensor.pv_balkon")
    await _frank_monat(db, a.id)
    for inv_id, kwh in ((invs[0].id, 55.0), (invs[1].id, 45.0), (bkw.id, 4.5)):
        db.add(InvestitionMonatsdaten(investition_id=inv_id, jahr=JAHR, monat=MONAT,
                                      verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    await db.flush()
    _patch_stats(monkeypatch, {**HA, "sensor.pv_ost": 55.0, "sensor.pv_balkon": 4.5})

    m = (await get_import_vorschau(a.id, db)).monate[0]

    assert m.aktion == "konflikt", m.grund
    assert m.vorhandene_werte[PV_LABEL] == pytest.approx(104.5)


async def _bestand(db, invs, bkw, werte: dict[str, tuple[float, str | None]]):
    """Modulwerte wie sie der Import vor N-611 geschrieben hat (Writer `ha_statistics_import`)."""
    from backend.services.provenance import seed_provenance
    for inv in invs:
        kwh, marke = werte[inv.bezeichnung]
        imd = InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                     verbrauch_daten={"pv_erzeugung_kwh": kwh})
        db.add(imd)
        await db.flush()
        seed_provenance(imd, source="external:ha_statistics", writer="ha_statistics_import",
                        json_subkeys={"verbrauch_daten": ["pv_erzeugung_kwh"]},
                        abgeleitet_je_subkey={"pv_erzeugung_kwh": marke} if marke else None)
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": 4.5}))
    await db.flush()


async def test_n611_alter_bestand_auf_zwei_module_verteilt_heilt_beim_erneuten_import(db, monkeypatch):
    """Vor N-611 verteilt: Ost/West 60/40 (markiert) + BKW 4,5 ⇒ Monat 104,5. Der erneute Import aus der
    Oberfläche (sie schickt „überschreiben") speichert den Anlagenwert 100; die markierten Zeilen sind Lücken, die
    Leseseite füllt sie mit dem Rest 95,5 ⇒ 57,3 / 38,2, Monat 100 (E4b: die Zeilen selbst bleiben stehen)."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    bkw = await _mit_bkw(db, a, sensor="sensor.pv_balkon")
    await _frank_monat(db, a.id)
    await _bestand(db, invs, bkw, {"Ost": (60.0, ABGELEITET_KWP_ANTEIL), "West": (40.0, ABGELEITET_KWP_ANTEIL)})
    _patch_stats(monkeypatch, {**HA, "sensor.pv_balkon": 4.5})
    assert await _monat_pv(db, a.id) == 104.5

    await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}], ueberschreiben=True), db,
    )

    assert await _aufgeloest(db, a.id, invs) == {"Ost": (57.3, "verteilt"), "West": (38.2, "verteilt")}
    assert await _monat_pv(db, a.id) == 100.0


async def test_n611_alter_bestand_auf_ein_modul_bleibt_auch_nach_erneutem_import(db, monkeypatch):
    """Festgehalten, nicht gewollt (HA-Bauform S1): hatte nur EIN Modul keinen eigenen Sensor, schrieb der
    Import ihm den Rest ohne Marke — als Messung. Ein erneuter Import ersetzt sie nicht; der Monat bleibt 104,5."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, "sensor.pv_ost"), ("West", 4.0, None)])
    bkw = await _mit_bkw(db, a, sensor="sensor.pv_balkon")
    await _frank_monat(db, a.id)
    await _bestand(db, invs, bkw, {"Ost": (55.0, None), "West": (45.0, None)})
    _patch_stats(monkeypatch, {**HA, "sensor.pv_ost": 55.0, "sensor.pv_balkon": 4.5})

    await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}], ueberschreiben=True), db,
    )

    assert await _modulwerte(db, invs) == {"Ost": (55.0, None), "West": (45.0, None)}
    assert await _monat_pv(db, a.id) == 104.5


async def test_n611_ein_unvollstaendiger_monat_bleibt_in_der_vorschau_fehlt_lokal(db, monkeypatch):
    """Fall B: Ost misst, West hat keinen Wert, das BKW 4,5, lokal kein Anlagenwert ⇒ die Modul-Summe ist
    unvollständig. Der BKW-Wert macht den Monat nicht „voll" — die Vorschau bleibt bei „importieren / fehlt lokal"
    (statt eines Konflikts aus 4,5 gegen 100)."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, "sensor.pv_ost"), ("West", 4.0, None)])
    bkw = await _mit_bkw(db, a, sensor="sensor.pv_balkon")
    await _frank_monat(db, a.id)
    for inv_id, kwh in ((invs[0].id, 55.0), (bkw.id, 4.5)):
        db.add(InvestitionMonatsdaten(investition_id=inv_id, jahr=JAHR, monat=MONAT,
                                      verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    await db.flush()
    _patch_stats(monkeypatch, {**HA, "sensor.pv_ost": 55.0, "sensor.pv_balkon": 4.5})

    m = (await get_import_vorschau(a.id, db)).monate[0]

    assert m.aktion == "importieren", m.grund
    assert PV_LABEL in m.grund
    assert m.vorhandene_werte[PV_LABEL] is None


# ── HA-Bauform E4b Teil A: Entscheide H-A1 (kein Ort ohne Zählerzeile) und H-A2 (alte Zerlegung fällt weg) ─────


async def _zeile(db, inv, kwh, *, writer: str, marke: str | None):
    """Eine Modulzeile mit Herkunft — wie sie ein früherer Schreiber hinterlassen hat."""
    quelle = {"monatsdaten_form": "manual:form", "ha_statistics_import": "external:ha_statistics"}.get(writer, writer)
    eintrag = {"source": quelle, "writer": writer, "at": "2026-01-01T00:00:00Z", **({"abgeleitet": marke} if marke else {})}
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": kwh},
                                  source_provenance={"verbrauch_daten.pv_erzeugung_kwh": eintrag}))
    await db.flush()


async def test_e4b_ohne_zaehlerzeile_wird_der_gesamtzaehler_nicht_gespeichert_und_genannt(db, monkeypatch):
    """H-A1: nur „PV Erzeugung Gesamt" ausgewählt, der Monat hat keine Zählerzeile ⇒ keine Zeile (N-240: keine
    erfundene 0/0), keine Verteilung auf Module (bis E4b: `_verteile_anlagen_pv`), und die Warnung nennt den Monat."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    _patch_stats(monkeypatch, HA)

    res = await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT, "basis_felder": [PV_LABEL]}]), db,
    )

    assert (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalar_one_or_none() is None
    assert await _modulwerte(db, invs) == {"Ost": (None, None), "West": (None, None)}
    assert res.erfolg and res.importiert == 0 and res.uebersprungen == 1
    assert res.warnungen == [
        "Monat 2023-05: PV-Gesamtzähler nicht gespeichert — der Monat hat keine Zählerzeile (Einspeisung/Netzbezug); "
        "erst Einspeisung und Netzbezug importieren oder den Monat anlegen"
    ]


async def test_e4b_nur_der_gesamtzaehler_ausgewaehlt_geht_in_eine_vorhandene_zeile(db, monkeypatch):
    """Gegenstück zu H-A1: gibt es die Zeile schon, landet der Zähler dort, auch wenn nur er ausgewählt ist."""
    a, _ = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    _patch_stats(monkeypatch, HA)

    res = await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT, "basis_felder": [PV_LABEL]}]), db,
    )

    assert await _anlagenwert(db, a.id) == 100.0
    assert res.importiert == 1 and res.warnungen == []


async def test_e4b_ueberschreiben_entfernt_nur_die_eigene_zerlegung(db, monkeypatch):
    """H-A2: West trägt eine frühere Zerlegung DIESES Imports (Schreiber `ha_statistics_import` + `kwp_anteil`) — sie
    fällt mit „überschreiben" weg. Ost trägt eine Zerlegung eines ANDEREN Schreibers (Portal, ebenfalls `kwp_anteil`) —
    sie bleibt. Ohne „überschreiben" bleibt alles."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    await _zeile(db, invs[0], 60.0, writer="portal_apply:x", marke=ABGELEITET_KWP_ANTEIL)
    await _zeile(db, invs[1], 40.0, writer="ha_statistics_import", marke=ABGELEITET_KWP_ANTEIL)
    _patch_stats(monkeypatch, {**HA, "sensor.pv_gesamt": 90.0})

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}]), db)
    assert await _modulwerte(db, invs) == {"Ost": (60.0, ABGELEITET_KWP_ANTEIL), "West": (40.0, ABGELEITET_KWP_ANTEIL)}

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}], ueberschreiben=True), db)
    assert await _modulwerte(db, invs) == {"Ost": (60.0, ABGELEITET_KWP_ANTEIL), "West": (None, None)}
    assert await _anlagenwert(db, a.id) == 90.0
    # Ost behält seine 60 (als Zahl, #352), West bekommt den Rest 30.
    assert await _aufgeloest(db, a.id, invs) == {"Ost": (60.0, "verteilt"), "West": (30.0, "verteilt")}


async def test_e4b_ueberschreiben_laesst_eine_handeingabe_stehen(db, monkeypatch):
    """H-A2: eine Handeingabe (Formular, ohne Marke) ist eine Messung des Anwenders und bleibt — nur die eigene
    Zerlegung des Imports daneben fällt weg; die Leseseite gibt West den Rest 100 − 70."""
    a, invs = await _anlage(db, module=[("Ost", 6.0, None), ("West", 4.0, None)])
    await _frank_monat(db, a.id)
    await _zeile(db, invs[0], 70.0, writer="monatsdaten_form", marke=None)
    await _zeile(db, invs[1], 40.0, writer="ha_statistics_import", marke=ABGELEITET_KWP_ANTEIL)
    _patch_stats(monkeypatch, HA)

    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": JAHR, "monat": MONAT}], ueberschreiben=True), db)

    assert await _modulwerte(db, invs) == {"Ost": (70.0, None), "West": (None, None)}
    assert await _aufgeloest(db, a.id, invs) == {"Ost": (70.0, "gemessen"), "West": (30.0, "verteilt")}
    assert await _monat_pv(db, a.id) == 100.0
