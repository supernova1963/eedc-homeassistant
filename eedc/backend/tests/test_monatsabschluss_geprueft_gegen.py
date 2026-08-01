"""Regression PN 90128: „gespeicherten behalten" überlebt das Speichern.

Der Monatsabschluss meldet „weicht ab", wenn ein gemessener Vorschlag vom
gespeicherten Wert abweicht. Entscheidet der Nutzer sich bewusst für den
gespeicherten Wert, war diese Entscheidung bis v4.0.5 reiner Client-State —
nach dem Speichern meldete sich dasselbe Feld wieder (Auftrag 3, Befund b).

Gespeichert wird deshalb nicht „bestätigt: ja", sondern die **Situation**:
gegen welchen Sensorwert bestätigt wurde und welcher Wert behalten wurde.
Dieser Test deckt den Schreib-/Lese-Weg beider Ebenen ab (Anlage-Feld und
Investitionsfeld) und dass die Rücknahme über ein leeres Objekt funktioniert.

Dass die Bestätigung bei geändertem Sensorwert **nicht** mehr gilt, entscheidet
der Client (`lib/erfassungZustand.ts::bestaetigungGilt`) — dort auch getestet.
Hier geht es um die Persistenz: was gespeichert wird, muss unverändert
zurückkommen.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from backend.api.routes.monatsdaten import (
    MonatsdatenCreate,
    MonatsdatenUpdate,
    create_monatsdaten,
    update_monatsdaten,
)
from backend.api.routes.monatsabschluss.views import get_monatsabschluss
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
)


async def _anlage_mit_pv(db) -> tuple[Anlage, Investition]:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süddach",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=5.0, parameter={},
    )
    db.add(pv)
    await db.flush()
    return anlage, pv


async def test_geprueft_gegen_ueberlebt_create_und_update(db):
    """Anlage-Feld: beim Anlegen gesetzt, beim Aktualisieren geändert, dann
    zurückgenommen — jedes Mal steht in der DB genau das Gesendete."""
    anlage, _ = await _anlage_mit_pv(db)

    md = await create_monatsdaten(
        MonatsdatenCreate(
            anlage_id=anlage.id, jahr=2025, monat=11,
            einspeisung_kwh=173.16, netzbezug_kwh=454.74,
            geprueft_gegen={"netzbezug_kwh": {"sensor": 453.7, "wert": 454.74}},
        ),
        db=db,
    )
    assert md.geprueft_gegen == {"netzbezug_kwh": {"sensor": 453.7, "wert": 454.74}}

    # Zweites Feld kommt dazu (die Form schickt immer die volle Menge).
    md = await update_monatsdaten(
        md.id,
        MonatsdatenUpdate(geprueft_gegen={
            "netzbezug_kwh": {"sensor": 453.7, "wert": 454.74},
            "einspeisung_kwh": {"sensor": 170.0, "wert": 173.16},
        }),
        db=db,
    )
    assert set(md.geprueft_gegen) == {"netzbezug_kwh", "einspeisung_kwh"}

    # Leeres Objekt = alle Bestätigungen zurückgenommen.
    md = await update_monatsdaten(md.id, MonatsdatenUpdate(geprueft_gegen={}), db=db)
    assert md.geprueft_gegen == {}

    # Feld gar nicht gesendet ⇒ Bestand bleibt unangetastet.
    md = await update_monatsdaten(
        md.id, MonatsdatenUpdate(geprueft_gegen={"netzbezug_kwh": {"sensor": 1.0, "wert": 2.0}}), db=db,
    )
    md = await update_monatsdaten(md.id, MonatsdatenUpdate(netzbezug_kwh=455.0), db=db)
    assert md.geprueft_gegen == {"netzbezug_kwh": {"sensor": 1.0, "wert": 2.0}}


async def test_geprueft_gegen_investition_landet_nicht_in_verbrauch_daten(db):
    """Investitionsfeld: die Bestätigung geht in die eigene Spalte — im
    `verbrauch_daten`-JSON hat sie nichts zu suchen, dort lesen Aggregatoren,
    CSV-Export und MQTT mit."""
    anlage, pv = await _anlage_mit_pv(db)

    md = await create_monatsdaten(
        MonatsdatenCreate(
            anlage_id=anlage.id, jahr=2025, monat=11,
            einspeisung_kwh=100.0, netzbezug_kwh=200.0,
            investitionen_daten={
                str(pv.id): {
                    "pv_erzeugung_kwh": 379.0,
                    "geprueft_gegen": {"pv_erzeugung_kwh": {"sensor": 376.0, "wert": 379.0}},
                },
            },
        ),
        db=db,
    )
    await db.flush()

    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == pv.id)
    )).scalar_one()
    assert imd.verbrauch_daten == {"pv_erzeugung_kwh": 379.0}
    assert imd.geprueft_gegen == {"pv_erzeugung_kwh": {"sensor": 376.0, "wert": 379.0}}

    # Update über denselben Weg: Messwert bleibt, Bestätigung wird zurückgenommen.
    await update_monatsdaten(
        md.id,
        MonatsdatenUpdate(investitionen_daten={
            str(pv.id): {"pv_erzeugung_kwh": 379.0, "geprueft_gegen": {}},
        }),
        db=db,
    )
    await db.refresh(imd)
    assert imd.verbrauch_daten == {"pv_erzeugung_kwh": 379.0}
    assert imd.geprueft_gegen == {}


async def test_monatsabschluss_liefert_geprueft_gegen_je_feld(db):
    """Der Status-Endpoint reicht die Bestätigung an genau dem Feld heraus, zu
    dem sie gehört — Basis wie Investition."""
    anlage, pv = await _anlage_mit_pv(db)

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=11,
        einspeisung_kwh=173.16, netzbezug_kwh=454.74,
        geprueft_gegen={"netzbezug_kwh": {"sensor": 453.7, "wert": 454.74}},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=11,
        verbrauch_daten={"pv_erzeugung_kwh": 379.0},
        geprueft_gegen={"pv_erzeugung_kwh": {"sensor": 376.0, "wert": 379.0}},
    ))
    await db.flush()

    res = await get_monatsabschluss(anlage.id, 2025, 11, db=db)

    basis = {f.feld: f for f in res.basis_felder}
    assert basis["netzbezug_kwh"].geprueft_gegen == {"sensor": 453.7, "wert": 454.74}
    assert basis["einspeisung_kwh"].geprueft_gegen is None

    inv_felder = {f.feld: f for inv in res.investitionen for f in inv.felder}
    assert inv_felder["pv_erzeugung_kwh"].geprueft_gegen == {"sensor": 376.0, "wert": 379.0}
