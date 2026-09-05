"""N-393 — ein gespeicherter Wert in einem Feld, das das Gerät nicht führt, hat einen Handgriff.

**Der Fall (dietmar1968, T89667 #295/#300):** 889 kWh „Warmwasser" an einer
Split-Klimaanlage — eedcs eigener COP-Vorschlag (254 kWh × JAZ 3,5), im
Monatsabschluss vorbelegt und gespeichert. N-304 hat das Feld an der Klimaanlage
aus dem Monatsabschluss genommen, N-379 den Lesepfad geschlossen und eine INFO
gebaut, die sagte: *„bleibt stehen, bis du ihn selbst umträgst."* **Den Weg gab
es nicht:** `getFelderFuerInvestition` filtert ohne Rücksicht auf gespeicherte
Werte, und `write_json_subkey_with_provenance` merged je Sub-Key — ein erneuter
Abschluss lässt den Altwert stehen.

**Die Klasse ist größer als die Klimaanlage.** Jedes Feld mit harter `bedingung`
wird unerreichbar, sobald der Schalter am Gerät zurückgestellt ist: Netzladung
ohne `laedt_aus_netz`, V2H ohne `v2h_faehig`, BKW-Speicher ohne `hat_speicher`,
getrennte Ströme nach Abschalten der getrennten Messung. Der Checker fragt
deshalb die Registry (`groesse_gibt_es_am_geraet`), nicht die Bauart — R1.

**Warum kein wieder eingeblendetes Formularfeld** (Gernots Einwand, 05.09.):
Es stellte die zweite Wahrheit her, die N-304 beseitigt hat, der Vorschlagsdienst
böte daneben wieder „254 × 3,5" an — und der Zustand hat schon einen Melder.
Der Handgriff gehört an die Meldung: Bauform #349 (`geraetewerte_loeschen`).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.data_provenance_log import DataProvenanceLog
from backend.services.daten_checker import DatenChecker


async def _anlage_mit(db, *, typ: str, parameter: dict, monate: dict[int, dict]):
    anlage = Anlage(anlagenname="N-393", leistung_kwp=10.0,
                    installationsdatum=date(2026, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung="Gerät",
        anschaffungsdatum=date(2026, 1, 1), anschaffungskosten_gesamt=1000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    for monat, daten in monate.items():
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2026, monat=monat, verbrauch_daten=dict(daten),
            source_provenance={
                f"verbrauch_daten.{k}": {"source": "manual:form", "writer": "test",
                                         "written_at": "2026-07-01T00:00:00"}
                for k in daten
            },
        ))
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=monat,
                           einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    await db.commit()
    geladen = (await db.execute(
        select(Investition).options(selectinload(Investition.monatsdaten))
        .where(Investition.id == inv.id)
    )).scalar_one()
    return anlage, geladen


def _befunde(db, inv):
    return DatenChecker(db)._check_werte_in_nicht_gefuehrten_feldern(
        inv, inv.bezeichnung, inv.parameter or {}
    )


# ── Der Checker ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_klimaanlage_warmwasser_bekommt_eine_meldung_mit_handgriff(db):
    """dietmars Fall: EINE INFO, Aktion `feldwert_entfernen`, der Monat steht drin."""
    _, klima = await _anlage_mit(
        db, typ="waermepumpe", parameter={"wp_art": "luft_luft"},
        monate={6: {"stromverbrauch_kwh": 254.0, "warmwasser_kwh": 889.0}},
    )
    befunde = _befunde(db, klima)
    assert len(befunde) == 1
    e = befunde[0]
    assert "Warmwasserkreis" in e.meldung
    assert e.action_kind == "feldwert_entfernen"
    assert e.action_label == "Wert entfernen"
    assert e.action_params == {
        "investition_id": klima.id, "feld": "warmwasser_kwh",
        "label": "Warmwasser-Wärme", "monate": ["06/2026"],
    }
    assert "„Wert entfernen“" in e.details, "der genannte Weg ist der Knopf, kein Umtragen"
    assert "umträgst" not in e.details, "der alte Weg ins Leere darf nicht mehr genannt werden"
    assert e.investition_id == klima.id


@pytest.mark.asyncio
async def test_mehrere_monate_ergeben_eine_meldung_und_alle_monate_in_der_aktion(db):
    """Nicht je Monat eine Meldung (N-379-Entscheid) — die Aktion nimmt alle mit."""
    _, klima = await _anlage_mit(
        db, typ="waermepumpe", parameter={"wp_art": "luft_luft"},
        monate={5: {"warmwasser_kwh": 10.0}, 6: {"warmwasser_kwh": 889.0},
                7: {"stromverbrauch_kwh": 100.0}},
    )
    befunde = _befunde(db, klima)
    assert len(befunde) == 1
    assert befunde[0].action_params["monate"] == ["05/2026", "06/2026"]
    assert "2 Monat(en)" in befunde[0].meldung


@pytest.mark.asyncio
async def test_luft_wasser_wp_mit_warmwasser_bleibt_still(db):
    """Gegenprobe Bauart: das Gerät führt das Feld — kein Befund."""
    _, wp = await _anlage_mit(
        db, typ="waermepumpe", parameter={"wp_art": "luft_wasser"},
        monate={6: {"stromverbrauch_kwh": 254.0, "warmwasser_kwh": 142.0}},
    )
    assert _befunde(db, wp) == []


@pytest.mark.asyncio
async def test_die_klasse_reicht_ueber_die_klimaanlage_hinaus_speicher_netzladung(db):
    """Ein Speicher OHNE `laedt_aus_netz`, aber mit gespeicherter Netzladung."""
    _, sp = await _anlage_mit(
        db, typ="speicher", parameter={"laedt_aus_netz": False},
        monate={3: {"ladung_kwh": 300.0, "ladung_netz_kwh": 40.0}},
    )
    befunde = _befunde(db, sp)
    assert len(befunde) == 1
    e = befunde[0]
    assert e.action_kind == "feldwert_entfernen"
    assert e.action_params["feld"] == "ladung_netz_kwh"
    assert "führt das Feld nicht mehr" in e.meldung
    assert "Warmwasserkreis" not in e.meldung, "der Klima-Text gehört nur zur Klimaanlage"
    assert "zurück" in e.details, "der Ausweg „Einstellung zurückstellen“ muss genannt sein"


@pytest.mark.asyncio
async def test_speicher_mit_netzladung_erlaubt_bleibt_still(db):
    """Gegenprobe Schalter: `laedt_aus_netz` an ⇒ das Feld wird geführt."""
    _, sp = await _anlage_mit(
        db, typ="speicher", parameter={"laedt_aus_netz": True},
        monate={3: {"ladung_kwh": 300.0, "ladung_netz_kwh": 40.0}},
    )
    assert _befunde(db, sp) == []


@pytest.mark.asyncio
async def test_eine_null_loest_nichts_aus(db):
    """Eine 0 ist keine Aussage und rechnet nirgends mit — kein Lärm."""
    _, klima = await _anlage_mit(
        db, typ="waermepumpe", parameter={"wp_art": "luft_luft"},
        monate={6: {"stromverbrauch_kwh": 254.0, "warmwasser_kwh": 0}},
    )
    assert _befunde(db, klima) == []


@pytest.mark.asyncio
async def test_ein_erweitertes_feld_gilt_als_gefuehrt(db):
    """Weiche Bedingung (R1, `weich`): Heizwärme an einer Brauchwasser-WP ist
    untypisch, nicht unmöglich — wer sie gepflegt hat, meint es so. Kein Befund."""
    _, bw = await _anlage_mit(
        db, typ="waermepumpe", parameter={"wp_art": "brauchwasser"},
        monate={1: {"stromverbrauch_kwh": 80.0, "heizenergie_kwh": 120.0}},
    )
    assert _befunde(db, bw) == []


@pytest.mark.asyncio
async def test_der_gesamtlauf_des_checkers_traegt_die_meldung(db):
    """Nicht nur die Methode — der Aufruf aus `stammdaten.py` erreicht jeden Typ."""
    anlage, _ = await _anlage_mit(
        db, typ="speicher", parameter={"laedt_aus_netz": False},
        monate={3: {"ladung_kwh": 300.0, "ladung_netz_kwh": 40.0}},
    )
    result = await DatenChecker(db).check_anlage(anlage.id)
    treffer = [e for e in result.ergebnisse if e.action_kind == "feldwert_entfernen"]
    assert len(treffer) == 1
    assert treffer[0].action_params["feld"] == "ladung_netz_kwh"


# ── Der Endpunkt ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_endpunkt_entfernt_genau_den_wert_und_schreibt_einen_audit_eintrag(db):
    from backend.api.routes.monatsdaten import delete_feldwert_nicht_gefuehrt

    _, klima = await _anlage_mit(
        db, typ="waermepumpe", parameter={"wp_art": "luft_luft"},
        monate={5: {"warmwasser_kwh": 10.0}, 6: {"stromverbrauch_kwh": 254.0, "warmwasser_kwh": 889.0}},
    )
    antwort = await delete_feldwert_nicht_gefuehrt(klima.id, "warmwasser_kwh", db=db)
    assert antwort["entfernt"] == 2
    assert [(m["jahr"], m["monat"], m["wert"]) for m in antwort["monate"]] == [
        (2026, 5, 10.0), (2026, 6, 889.0),
    ]

    zeilen = (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == klima.id)
        .order_by(InvestitionMonatsdaten.monat)
    )).scalars().all()
    assert (zeilen[0].verbrauch_daten or {}) == {}
    assert zeilen[1].verbrauch_daten == {"stromverbrauch_kwh": 254.0}, "der Strom bleibt"
    assert "verbrauch_daten.warmwasser_kwh" not in (zeilen[1].source_provenance or {})
    assert "verbrauch_daten.stromverbrauch_kwh" in (zeilen[1].source_provenance or {})

    logs = (await db.execute(
        select(DataProvenanceLog).where(
            DataProvenanceLog.field_name == "verbrauch_daten.warmwasser_kwh"
        )
    )).scalars().all()
    assert len(logs) == 2
    assert {log.old_value for log in logs} == {"10.0", "889.0"}
    assert all(log.new_value is None and log.decision == "applied" for log in logs)
    assert all("N-393" in log.decision_reason for log in logs)

    # Danach ist der Checker still.
    geladen = (await db.execute(
        select(Investition).options(selectinload(Investition.monatsdaten))
        .where(Investition.id == klima.id)
    )).scalar_one()
    assert _befunde(db, geladen) == []


@pytest.mark.asyncio
async def test_endpunkt_weist_ein_gefuehrtes_feld_ab(db):
    """Bewusst eng (#349-Muster): ein erreichbares Feld wird im Formular geleert."""
    from backend.api.routes.monatsdaten import delete_feldwert_nicht_gefuehrt

    _, wp = await _anlage_mit(
        db, typ="waermepumpe", parameter={"wp_art": "luft_wasser"},
        monate={6: {"warmwasser_kwh": 142.0}},
    )
    with pytest.raises(HTTPException) as exc:
        await delete_feldwert_nicht_gefuehrt(wp.id, "warmwasser_kwh", db=db)
    assert exc.value.status_code == 409
    zeile = (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == wp.id)
    )).scalar_one()
    assert zeile.verbrauch_daten == {"warmwasser_kwh": 142.0}, "nichts angefasst"


@pytest.mark.asyncio
async def test_endpunkt_unbekannte_investition_404(db):
    from backend.api.routes.monatsdaten import delete_feldwert_nicht_gefuehrt

    with pytest.raises(HTTPException) as exc:
        await delete_feldwert_nicht_gefuehrt(99999, "warmwasser_kwh", db=db)
    assert exc.value.status_code == 404
