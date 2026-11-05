"""RF-81 … RF-82 — benannte Proben für die Phasen von `import_json` und `get_datenquellen_felder`.

Komplexitäts-Refactoring (Session P3-G1, Bauform RF-1): beide Routen werden in Phasen geschnitten, ihr Verhalten bleibt
bitgleich. Die Golden Master `skript-golden-master-json-import.py` / `-datenquellen-felder.py` (In-Process, drei DB-Kopien +
Fixture-Anlagen) halten die Antworten, Tabellen und SQL-Folgen fest; diese Proben benennen die Regeln, an denen die Phasen
hängen, damit ein Bruch mit Namen rot wird und nicht nur als Byte-Abweichung:

* Import: Versionen 1.0/1.1 warnen, 0.9 lehnt ab ohne zu schreiben; Pflichtfelder; Überschreiben ersetzt den Bestand,
  sonst Namens-Suffix; ID-Map + Remap #353; «neueste aktive PVGIS-Prognose gewinnt» (`max(abgerufen_am)`, A17);
  Fehler ⇒ Rollback + Protokoll in derselben Sitzung (N-532); Hierarchie + Provenance der Gerätezeilen.
* Felder: Preis-Slot nur bei dynamischem Tarif; B8-2 schreibt positive Evidenz mit EINEM Commit fest und deaktiviert das
  parallele Gateway (§2h); Bauschnitt 7; Bedarf je Gerät (N-456); Verfügbarkeit der Quell-Achsen; 404.
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select

from backend.api.routes import datenquellen as dq
from backend.api.routes.import_export.json_operations import import_json
from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.strompreis import Strompreis
from backend.tests import factories


# ═══ RF-81 — JSON-Import ═════════════════════════════════════════════════════════════════════════════════════════

async def _importiere(db, daten, ueberschreiben=False, roh: bytes | None = None):
    inhalt = roh if roh is not None else json.dumps(daten).encode("utf-8")
    return await import_json(file=UploadFile(filename="export.json", file=io.BytesIO(inhalt)),
                             ueberschreiben=ueberschreiben, db=db)


async def _anzahl(db, modell) -> int:
    return (await db.execute(select(func.count()).select_from(modell))).scalar_one()


@pytest.mark.parametrize("version, warnung", [
    ("1.0", "Import von Export-Version 1.0 - sensor_mapping nicht enthalten."),
    ("1.1", "Import von Export-Version 1.1 - horizont_daten und PVGIS-Details ggf. unvollständig."),
    ("1.2", None),
    ("1.3", None),
])
async def test_import_versionen_werden_angenommen_und_benannt(db, version, warnung):
    erg = await _importiere(db, {"export_version": version, "anlage": {"anlagenname": f"V{version}"}})
    assert erg.erfolg is True
    assert erg.warnungen == ([warnung] if warnung else [])


@pytest.mark.parametrize("daten, fehler", [
    ({"export_version": "0.9", "anlage": {"anlagenname": "A"}},
     "Nicht unterstützte Export-Version: 0.9. Unterstützt: 1.0, 1.1, 1.2, 1.3"),
    ({"export_version": "1.3"}, "Fehlende Anlage-Daten im Export"),
    ({"export_version": "1.3", "anlage": {"leistung_kwp": 3}}, "Fehlender Anlagenname im Export"),
])
async def test_import_lehnt_ab_ohne_zu_schreiben(db, daten, fehler):
    erg = await _importiere(db, daten)
    assert erg.erfolg is False and erg.fehler == [fehler]
    assert await _anzahl(db, Anlage) == 0
    assert await _anzahl(db, ActivityLog) == 0


async def test_import_kaputtes_json_und_falsche_kodierung(db):
    erg = await _importiere(db, None, roh=b"{kaputt")
    assert erg.erfolg is False and erg.fehler[0].startswith("Ungültiges JSON-Format: ")
    erg = await _importiere(db, None, roh=b"\xff\xfe{")
    assert erg.erfolg is False and erg.fehler[0].startswith("Fehler beim Lesen der Datei: ")


async def test_import_ueberschreiben_ersetzt_den_bestand_sonst_suffix(db):
    a = await factories.anlage(db, anlagenname="Haus")
    await factories.investition(db, a.id, "speicher", bezeichnung="Alt-Akku")
    await db.commit()
    datei = {"export_version": "1.3", "anlage": {"anlagenname": "Haus"},
             "investitionen": [{"typ": "pv-module", "bezeichnung": "Neu-Dach"}]}

    neben = await _importiere(db, datei)
    assert neben.anlage_name == "Haus (Import 1)"
    assert neben.warnungen[0] == "Anlage wurde als 'Haus (Import 1)' importiert (Original: 'Haus')"

    ueber = await _importiere(db, datei, ueberschreiben=True)
    assert ueber.erfolg is True and ueber.anlage_name == "Haus"
    assert ueber.warnungen[0] == "Existierende Anlage 'Haus' wurde überschrieben"
    namen = sorted((await db.execute(select(Anlage.anlagenname))).scalars().all())
    assert namen == ["Haus", "Haus (Import 1)"]
    bez = sorted((await db.execute(select(Investition.bezeichnung))).scalars().all())
    assert bez == ["Neu-Dach", "Neu-Dach"], "der Alt-Akku muss mit der überschriebenen Anlage verschwinden"


async def test_import_hierarchie_id_map_und_remap_353(db):
    datei = {
        "export_version": "1.3",
        "anlage": {"anlagenname": "Remap", "sensor_mapping": {
            "investitionen": {"7": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.akku"}}},
                              "99": {"felder": {"x": {"strategie": "sensor", "sensor_id": "sensor.weg"}}}},
            "quellen": {"inv_energy_7_ladung_kwh": {"quelle": "ha_app", "entity_id": "sensor.akku"}},
        }},
        "investitionen": [
            {"id": 5, "typ": "wechselrichter", "bezeichnung": "WR", "children": [
                {"id": 7, "typ": "speicher", "bezeichnung": "Akku",
                 "monatsdaten": [{"jahr": 2024, "monat": 1, "verbrauch_daten": {"ladung_kwh": 10}}]}]},
        ],
    }
    erg = await _importiere(db, datei)
    assert erg.erfolg is True
    assert erg.importiert["investitionen"] == 2 and erg.importiert["investition_monatsdaten"] == 1
    wr, akku = (await db.execute(select(Investition).order_by(Investition.id))).scalars().all()
    assert akku.parent_investition_id == wr.id
    mapping = (await db.get(Anlage, erg.anlage_id)).sensor_mapping
    assert set(mapping["investitionen"]) == {str(akku.id)}
    assert f"inv_energy_{akku.id}_ladung_kwh" in mapping["quellen"]
    assert "Sensor-Zuordnung für 1 Komponente(n) übernommen (Basis-Zähler und Komponenten-Felder bleiben erhalten)." \
        in erg.warnungen
    verworfen = [w for w in erg.warnungen if w.startswith("WICHTIG")]
    assert len(verworfen) == 1 and "99" in verworfen[0] and "vor 1.3" not in verworfen[0]
    imd = (await db.execute(select(InvestitionMonatsdaten))).scalar_one()
    assert imd.verbrauch_daten == {"ladung_kwh": 10}
    assert imd.source_provenance, "Gerätezeile ohne Initial-Provenance (manual:json_backup)"


async def test_import_altdatei_ohne_ids_verwirft_und_sagt_vor_13(db):
    datei = {"export_version": "1.2", "anlage": {"anlagenname": "Alt", "sensor_mapping": {
        "investitionen": {"7": {"felder": {"a": {"strategie": "sensor", "sensor_id": "sensor.a"}}}}}},
        "investitionen": [{"typ": "speicher", "bezeichnung": "Akku"}]}
    erg = await _importiere(db, datei)
    verworfen = [w for w in erg.warnungen if w.startswith("WICHTIG")]
    assert len(verworfen) == 1 and "vor 1.3" in verworfen[0]


@pytest.mark.parametrize("prognosen, aktiv_jahresertrag, warnung", [
    # zwei aktive: die zuletzt abgerufene gewinnt (max(abgerufen_am)), Warnung nennt die Zahl
    ([{"jahresertrag_kwh": 1, "ist_aktiv": True, "abgerufen_am": "2025-01-01T00:00:00"},
      {"jahresertrag_kwh": 2, "ist_aktiv": True, "abgerufen_am": "2024-01-01T00:00:00"},
      {"jahresertrag_kwh": 3, "ist_aktiv": False, "abgerufen_am": "2026-01-01T00:00:00"}], 1, "2 als aktiv markierte"),
    # eine aktive: sie bleibt es, auch wenn eine inaktive neuer ist
    ([{"jahresertrag_kwh": 1, "ist_aktiv": False, "abgerufen_am": "2026-01-01T00:00:00"},
      {"jahresertrag_kwh": 2, "ist_aktiv": True, "abgerufen_am": "2020-01-01T00:00:00"}], 2, None),
    # keine markiert (Feld fehlt ⇒ False): die zuletzt abgerufene wird aktiviert
    ([{"jahresertrag_kwh": 1, "abgerufen_am": "2024-01-01T00:00:00"},
      {"jahresertrag_kwh": 2, "abgerufen_am": "2026-01-01T00:00:00"}], 2, "ohne Aktiv-Kennzeichnung"),
])
async def test_import_neueste_aktive_prognose_gewinnt(db, prognosen, aktiv_jahresertrag, warnung):
    erg = await _importiere(db, {"export_version": "1.3", "anlage": {"anlagenname": "P"}, "pvgis_prognosen": prognosen})
    alle = (await db.execute(select(PVGISPrognose).order_by(PVGISPrognose.id))).scalars().all()
    assert [p.jahresertrag_kwh for p in alle if p.ist_aktiv] == [aktiv_jahresertrag]
    assert [p.abgerufen_am for p in alle] == [datetime.fromisoformat(p["abgerufen_am"]) for p in prognosen]
    pv_warnungen = [w for w in erg.warnungen if "PVGIS" in w]
    assert (len(pv_warnungen) == 1 and warnung in pv_warnungen[0]) if warnung else pv_warnungen == []


async def test_import_monatsdaten_ohne_jahr_oder_monat_uebersprungen(db):
    erg = await _importiere(db, {"export_version": "1.3", "anlage": {"anlagenname": "M"}, "monatsdaten": [
        {"jahr": 2024, "monat": 1, "einspeisung_kwh": 0, "datenquelle": None},
        {"monat": 2}, {"jahr": 2024}]})
    assert erg.importiert["monatsdaten"] == 1
    assert erg.warnungen.count("Monatsdaten ohne Jahr/Monat übersprungen") == 2


async def test_import_fehler_rollt_zurueck_und_protokolliert_in_der_sitzung(db):
    erg = await _importiere(db, {"export_version": "1.0", "anlage": {"anlagenname": "Kaputt"}, "strompreise": [1]})
    assert erg.erfolg is False
    assert erg.fehler == ["Import-Fehler: 'int' object has no attribute 'get'"]
    assert erg.warnungen == ["Import von Export-Version 1.0 - sensor_mapping nicht enthalten."]
    await db.commit()
    assert await _anzahl(db, Anlage) == 0
    assert await _anzahl(db, Strompreis) == 0
    log = (await db.execute(select(ActivityLog))).scalar_one()
    assert (log.kategorie, log.aktion, log.erfolg) == ("backup_import", "Import fehlgeschlagen", False)


async def test_import_erfolg_protokolliert(db):
    erg = await _importiere(db, {"export_version": "1.3", "anlage": {"anlagenname": "Ok"},
                                 "monatsdaten": [{"jahr": 2024, "monat": 1}]})
    await db.commit()
    log = (await db.execute(select(ActivityLog))).scalar_one()
    assert (log.aktion, log.details, log.anlage_id) == ("Anlage 'Ok' importiert", "1 Monate, 0 Investitionen", erg.anlage_id)


# ═══ RF-82 — Datenquellen-Felder ═════════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def ohne_aussen(monkeypatch):
    """Keine HA, kein Inbound, MQTT-Import aus — der Test stellt um, was er braucht."""
    import backend.services.mqtt_inbound_service as mis
    zustand = {"transport": (None, None, None), "detail": {}, "mqtt": False}

    async def _resolve(_db):
        return zustand["transport"]

    async def _detail(_db, ids):
        return {e: d for e, d in zustand["detail"].items() if e in ids}

    async def _mqtt(_db):
        return zustand["mqtt"]
    monkeypatch.setattr(dq, "_resolve_ha", _resolve)
    monkeypatch.setattr(dq, "_ha_states_detail", _detail)
    monkeypatch.setattr(dq, "_mqtt_import_aktiviert", _mqtt)
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    return zustand


def _felder(resp) -> dict:
    return {f["id"]: f for g in resp["gruppen"] for f in g["felder"]}


async def test_felder_404(db, ohne_aussen):
    with pytest.raises(HTTPException) as exc:
        await dq.get_datenquellen_felder(4711, db)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("vertragsart, sichtbar", [("dynamisch", True), ("fix", False)])
async def test_felder_preis_slot_nur_bei_dynamischem_tarif(db, ohne_aussen, vertragsart, sichtbar):
    a = await factories.anlage(db)
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30, einspeiseverguetung_cent_kwh=8,
                      gueltig_ab=date(2020, 1, 1), vertragsart=vertragsart, verwendung="allgemein"))
    await db.commit()
    felder = _felder(await dq.get_datenquellen_felder(a.id, db))
    assert ("basis_preis_strompreis" in felder) is sichtbar
    if sichtbar:
        slot = felder["basis_preis_strompreis"]
        assert slot["nur_ha"] is True and slot["standard_topic"] == ""
        assert list(felder)[-1] == "basis_preis_strompreis" or all(
            not k.startswith("basis_") for k in list(felder)[list(felder).index("basis_preis_strompreis") + 1:]
        ), "der Preis-Slot steht am Ende des Basis-Abschnitts"


async def test_felder_b82_schreibt_mit_einem_commit_fest_und_deaktiviert_gateway(db, ohne_aussen, monkeypatch):
    from backend.services.datenquellen_resolver import topic_suffix
    a = await factories.anlage(db, sensor_mapping={
        "basis": {"einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp_kwh"}}})
    topics = {e["match_key"][1]: e["topic"] for e in await dq.build_expected_topics(db, a, investitionen=[])
              if e["match_key"][0] == "basis_energy"}
    parallel = MqttGatewayMapping(anlage_id=a.id, quell_topic="x/einsp", ziel_key=topic_suffix(topics["einspeisung_kwh"]))
    allein = MqttGatewayMapping(anlage_id=a.id, quell_topic="x/netz", ziel_key=topic_suffix(topics["netzbezug_kwh"]))
    db.add_all([parallel, allein])
    await db.commit()
    ohne_aussen["transport"] = ("http://ha", "tok", "ha_connector")
    commits = []
    original = db.commit

    async def _zaehle():
        commits.append(1)
        await original()
    monkeypatch.setattr(db, "commit", _zaehle)

    felder = _felder(await dq.get_datenquellen_felder(a.id, db))

    assert len(commits) == 1, "positive Evidenz wird mit genau einem Commit der Route festgeschrieben"
    quellen = a.sensor_mapping["quellen"]
    assert quellen["basis_energy_einspeisung_kwh"] == {"quelle": "ha_connector", "entity_id": "sensor.einsp_kwh"}
    assert quellen["basis_energy_netzbezug_kwh"] == {"quelle": "mqtt_gateway", "mapping_id": allein.id}
    assert felder["basis_energy_netzbezug_kwh"]["gateway_topic"] == "x/netz"
    assert parallel.aktiv is False and allein.aktiv is True, "§2h: nur das parallele Gateway wird deaktiviert"

    commits.clear()
    await dq.get_datenquellen_felder(a.id, db)
    assert commits == [], "zweiter Aufruf: nichts Neues, kein Commit (guarded)"


async def test_felder_bauschnitt7_gesamtleistung_verdraengt_aufteilung(db, ohne_aussen):
    a = await factories.anlage(db)
    wp = await factories.investition(db, a.id, "waermepumpe")
    # Maßgeblich ist die HA-`live`-Map: der Inbound-Stempel am Warmwasser-Feld verdrängt nichts und wird nichts gemeldet.
    a.sensor_mapping = {"investitionen": {str(wp.id): {"live": {"leistung_w": "sensor.wp_w", "leistung_heizen_w": "sensor.h_w"}}},
                        "quellen": {f"inv_live_{wp.id}_leistung_warmwasser_w": {"quelle": "mqtt_inbound_standard"}}}
    await db.commit()
    felder = _felder(await dq.get_datenquellen_felder(a.id, db))
    arten = {fid: [p["art"] for p in f["probleme"]] for fid, f in felder.items() if f["probleme"]}
    assert arten == {f"inv_live_{wp.id}_leistung_heizen_w": ["gesamtleistung_verdraengt"]}


async def test_felder_bedarf_je_geraet_n456(db, ohne_aussen):
    a = await factories.anlage(db)
    wp_a = await factories.investition(db, a.id, "waermepumpe", bezeichnung="A")
    wp_b = await factories.investition(db, a.id, "waermepumpe", bezeichnung="B")
    a.sensor_mapping = {"quellen": {
        f"inv_energy_{wp_a.id}_heizenergie_kwh": {"quelle": "ha_app", "entity_id": "sensor.a_heiz"},
        f"inv_energy_{wp_a.id}_strom_heizen_kwh": {"quelle": "ha_app", "entity_id": "sensor.a_strom_heizen"}}}
    await db.commit()
    felder = _felder(await dq.get_datenquellen_felder(a.id, db))
    # Alternativ-Gruppe wp_waerme: das Geschwister an DEMSELBEN Gerät wird verdrängt, das am anderen nicht.
    assert felder[f"inv_energy_{wp_a.id}_waerme_kwh"]["bedarf"] == "inaktiv"
    assert felder[f"inv_energy_{wp_b.id}_heizenergie_kwh"]["bedarf"] == "pflicht"
    # Summanden-Gruppe wp_strom: `stromverbrauch_kwh` ist an A Pflicht und bleibt es, ohne Summanden-Zusatztext.
    sv = felder[f"inv_energy_{wp_a.id}_stromverbrauch_kwh"]
    assert (sv["bedarf"], sv["bedarf_grund"], sv["bedarf_text"]) == ("pflicht", None, None)


@pytest.mark.parametrize("transport, mqtt, erwartet", [
    ((None, None, None), False, {"ha": False, "ha_quelle": None, "mqtt": False}),
    (("http://ha", "tok", "ha_app"), True, {"ha": True, "ha_quelle": "ha_app", "mqtt": True}),
    (("http://ha", None, "ha_connector"), False, {"ha": True, "ha_quelle": "ha_connector", "mqtt": False}),
])
async def test_felder_verfuegbarkeit_der_quell_achsen(db, ohne_aussen, transport, mqtt, erwartet):
    a = await factories.anlage(db)
    await db.commit()
    ohne_aussen.update(transport=transport, mqtt=mqtt)
    resp = await dq.get_datenquellen_felder(a.id, db)
    assert list(resp) == ["anlage_id", "gruppen", "verfuegbarkeit", "historie_hinweis"]
    assert resp["verfuegbarkeit"] == erwartet
