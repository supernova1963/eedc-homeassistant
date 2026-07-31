"""
Der BKW-Akku-Kanon an den drei Flächen, die ihn anbieten bzw. verweigern.

Ergänzt `test_bkw_speicher_datenpfad.py` (Rechen-/Zählerpfad) um die Stellen,
die ein Anwender tatsächlich sieht:

1. **Parent-Optionen** — der Endpoint muss das Balkonkraftwerk als möglichen
   Parent eines Speichers anbieten. Bis 2026-07-31 zählte er ausschließlich
   Wechselrichter auf und widersprach damit sowohl der Validierung als auch dem
   Formular. Er war zusätzlich ohne Aufrufer, also unbemerkt falsch (N-33).
2. **Datenquellen-Fläche** — die BKW-eigenen Akku-Felder sind `nur_manuell` und
   verschwinden als zuordenbare Quelle. AUSNAHME: wer sie schon zugeordnet hat,
   sieht sie weiter, sonst ließe sich die Zuordnung nicht mehr entfernen.
3. **Daten-Checker** — Weg-B-Altbestand bekommt einen Hinweis mit benannter
   Handlung statt eines stillen Umbaus seiner Daten
   ([[feedback_kein_grosser_heiler_knopf]]).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.investitionen.crud import get_parent_options
from backend.api.routes.datenquellen import ohne_nicht_zuordenbare
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.daten_checker.kategorien import CheckSeverity
from backend.services.daten_checker.stammdaten import StammdatenChecks
from backend.services.mqtt_topic_registry import build_expected_topics


BKW_FELD_LADUNG = "speicher_ladung_kwh"
BKW_FELD_ENTLADUNG = "speicher_entladung_kwh"


async def _anlage_mit_bkw(db, hat_speicher=True, sensor_mapping=None):
    anlage = Anlage(
        anlagenname="BKW-Kanon", leistung_kwp=0.8, standort_plz="80331",
        installationsdatum=date(2024, 1, 1),
        sensor_mapping=sensor_mapping,
    )
    db.add(anlage)
    await db.flush()
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon Süd",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"leistung_wp": 400, "anzahl": 2, "hat_speicher": hat_speicher,
                   "speicher_kapazitaet_wh": 1600},
    )
    db.add(bkw)
    await db.flush()
    return anlage, bkw


# ─── 1. Parent-Optionen ─────────────────────────────────────────────────────

async def test_parent_optionen_bieten_das_balkonkraftwerk_an(db):
    """N-33: der Endpoint kannte nur Wechselrichter."""
    anlage, bkw = await _anlage_mit_bkw(db)
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Hybrid-WR",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(wr)
    await db.flush()

    optionen = await get_parent_options(anlage.id, db)

    speicher_parents = {(o.typ, o.id) for o in optionen["speicher"]}
    assert ("balkonkraftwerk", bkw.id) in speicher_parents
    assert ("wechselrichter", wr.id) in speicher_parents
    # Optional — ein Hausspeicher darf ohne Parent bleiben.
    assert all(o.required is False for o in optionen["speicher"])

    # PV-Module dagegen: nur Wechselrichter, und Pflicht, weil es einen gibt.
    assert {o.typ for o in optionen["pv-module"]} == {"wechselrichter"}
    assert all(o.required is True for o in optionen["pv-module"])


async def test_parent_pflicht_nur_wenn_es_einen_parent_gibt(db):
    """Ohne Wechselrichter darf ein PV-Modul parentlos bleiben (Altbestand) —
    dieselbe Bedingung wie in `_validate_parent_child`."""
    anlage, _bkw = await _anlage_mit_bkw(db)
    optionen = await get_parent_options(anlage.id, db)
    assert optionen["pv-module"] == []
    # Das BKW selbst hat keine Parent-Optionen.
    assert optionen["balkonkraftwerk"] == []


# ─── 2. Datenquellen-Fläche ─────────────────────────────────────────────────

def _feld_ids(eintraege) -> set[str]:
    return {"_".join((mk[0], *mk[1:])) for mk in (e["match_key"] for e in eintraege)}


async def _flaeche(db, anlage, quellen: dict | None = None) -> set[str]:
    """Die Feld-IDs, die die Zuordnungs-Fläche anbietet.

    Registry + Sichtbarkeits-Regel — bewusst ohne den Endpoint: der zieht
    MQTT-Cache, HA-Transport und Gateway-Tabellen mit, die mit dieser Frage
    nichts zu tun haben.
    """
    eintraege = await build_expected_topics(db, anlage)
    return _feld_ids(ohne_nicht_zuordenbare(eintraege, quellen or {}))


async def test_registry_kennt_die_felder_und_markiert_sie(db):
    """Die Registry ist die SoT „welche Felder gibt es" und filtert NICHT —
    sonst wäre eine bestehende Zuordnung nicht mehr auffindbar."""
    anlage, bkw = await _anlage_mit_bkw(db)
    eintraege = await build_expected_topics(db, anlage)
    nach_id = {
        "_".join((e["match_key"][0], *e["match_key"][1:])): e for e in eintraege
    }
    for feld in (BKW_FELD_LADUNG, BKW_FELD_ENTLADUNG):
        assert nach_id[f"inv_energy_{bkw.id}_{feld}"]["nur_manuell"] is True
    assert nach_id[f"inv_energy_{bkw.id}_pv_erzeugung_kwh"]["nur_manuell"] is False


async def test_bkw_akku_felder_sind_nicht_mehr_zuordenbar(db):
    """Weg B verschwindet als Quelle — die Erzeugung bleibt selbstverständlich."""
    anlage, bkw = await _anlage_mit_bkw(db)
    ids = await _flaeche(db, anlage)

    assert f"inv_energy_{bkw.id}_{BKW_FELD_LADUNG}" not in ids
    assert f"inv_energy_{bkw.id}_{BKW_FELD_ENTLADUNG}" not in ids
    assert f"inv_energy_{bkw.id}_pv_erzeugung_kwh" in ids
    # `eigenverbrauch_kwh` bleibt zuordenbar (Entscheid aus Paket D).
    assert f"inv_energy_{bkw.id}_eigenverbrauch_kwh" in ids


async def test_bestehende_zuordnung_bleibt_sichtbar_und_entfernbar(db):
    """Die Falle, die `bedingung_anlage` schon einmal gestellt hat: ein Feld
    auszublenden, auf dem eine Zuordnung liegt, macht sie unentfernbar."""
    anlage, bkw = await _anlage_mit_bkw(db)
    feld_id = f"inv_energy_{bkw.id}_{BKW_FELD_LADUNG}"

    ids = await _flaeche(db, anlage, {feld_id: {"quelle": "mqtt_inbound_standard"}})
    assert feld_id in ids
    # Das zweite, NICHT zugeordnete Akku-Feld bleibt draußen.
    assert f"inv_energy_{bkw.id}_{BKW_FELD_ENTLADUNG}" not in ids
    # Und eine auf „keine" gesetzte Quelle hält es nicht am Leben.
    ids_keine = await _flaeche(db, anlage, {feld_id: {"quelle": "keine"}})
    assert feld_id not in ids_keine


# ─── 3. Daten-Checker: Migrationspfad statt stillem Umbau ───────────────────

async def _bkw_monate(db, bkw, monate, mit_akku=True):
    """Legt Monatswerte an und liefert das BKW MIT geladener `monatsdaten`-
    Beziehung zurück — genau wie der Checker sie bekommt (`selectinload` in
    `daten_checker/__init__.py`). Ohne das wäre der Zugriff ein Lazy-Load und
    im Async-Kontext ein MissingGreenlet-Fehler."""
    for jahr, monat in monate:
        daten = {"pv_erzeugung_kwh": 40.0}
        if mit_akku:
            daten |= {BKW_FELD_LADUNG: 12.0, BKW_FELD_ENTLADUNG: 10.5}
        db.add(InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=jahr, monat=monat,
            verbrauch_daten=daten, source_provenance={},
        ))
    await db.flush()
    return (await db.execute(
        select(Investition)
        .where(Investition.id == bkw.id)
        .options(selectinload(Investition.monatsdaten))
    )).scalar_one()


def _hinweise(ergebnisse):
    return [e for e in ergebnisse if "Akku-Werte nur als Monatswert" in e.meldung]


async def test_gepflegter_weg_b_bekommt_den_hinweis_mit_handlung(db):
    anlage, bkw = await _anlage_mit_bkw(db)
    bkw = await _bkw_monate(db, bkw, [(2025, 3), (2025, 4), (2025, 5)])

    treffer = _hinweise(
        StammdatenChecks()._check_bkw_akku_erfassungsweg(
            bkw, "Balkon Süd (balkonkraftwerk)", [bkw],
        )
    )
    assert len(treffer) == 1
    hinweis = treffer[0]
    # Kein Alarm — es ist nichts kaputt, es geht besser.
    assert hinweis.schwere == CheckSeverity.INFO
    # Der Hinweis nennt Umfang, Handlung und die Zusicherung.
    assert "3 Monate" in hinweis.details
    assert "03/2025 bis 05/2025" in hinweis.details
    assert "Speicher" in hinweis.details and "Gehört zu" in hinweis.details
    assert "bleiben erhalten" in hinweis.details
    assert hinweis.link


async def test_ohne_gepflegte_akku_werte_kein_hinweis(db):
    """Ein BKW mit Akku-Schalter, aber ohne gepflegte Mengen, wird in Ruhe
    gelassen — sonst nörgelt der Checker jeden BKW-Besitzer an."""
    anlage, bkw = await _anlage_mit_bkw(db)
    bkw = await _bkw_monate(db, bkw, [(2025, 3)], mit_akku=False)
    assert not _hinweise(
        StammdatenChecks()._check_bkw_akku_erfassungsweg(
            bkw, "Balkon Süd (balkonkraftwerk)", [bkw],
        )
    )


async def test_wer_schon_auf_weg_a_ist_bekommt_keinen_hinweis(db):
    """Hängt ein Speicher am BKW, ist der Anwender migriert — auch wenn die
    alten Monatswerte noch dastehen. Sie bleiben ja bewusst erhalten."""
    anlage, bkw = await _anlage_mit_bkw(db)
    bkw = await _bkw_monate(db, bkw, [(2025, 3), (2025, 4)])
    akku = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Anker SOLIX",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parent_investition_id=bkw.id,
    )
    db.add(akku)
    await db.flush()

    assert not _hinweise(
        StammdatenChecks()._check_bkw_akku_erfassungsweg(
            bkw, "Balkon Süd (balkonkraftwerk)", [bkw, akku],
        )
    )


async def test_ein_einzelner_monat_nennt_ihn_ohne_zeitraum(db):
    anlage, bkw = await _anlage_mit_bkw(db)
    bkw = await _bkw_monate(db, bkw, [(2025, 11)])
    hinweis = _hinweise(
        StammdatenChecks()._check_bkw_akku_erfassungsweg(
            bkw, "Balkon Süd (balkonkraftwerk)", [bkw],
        )
    )[0]
    assert "1 Monate (11/2025)" in hinweis.details
    assert "bis" not in hinweis.details.split("Empfohlen")[0]
