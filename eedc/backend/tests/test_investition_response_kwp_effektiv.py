"""`InvestitionResponse.leistung_kwp_effektiv` — der effektive Kennwert an der
API-Grenze (A26/N106, ADR-002/P3-a Grenze (c)).

Der Backend-Wächter aus A24-3 sagt über den **Client** nichts: `v4/komponenten-
Adapter.tsx` rechnete die kWp-Verteilung ein zweites Mal auf der ROHSPALTE aus
der Investitionen-API. Ein Modul, dessen Nennleistung nur im `parameter`-JSON
gepflegt ist (#229-Datenlage), bekam dort 0 — die übrigen zu viel.

Diese Tests pinnen die **drei** Zusicherungen des zusätzlichen Response-Feldes:

1. **Es heilt** — Spalte, `parameter["kwp"]`, `parameter["leistung_kwp"]` und die
   BKW-Formel `leistung_wp × anzahl` liefern denselben Weg wie die SoT-Helper.
2. **Es ersetzt nichts** — `leistung_kwp` bleibt in derselben Antwort unverändert
   die Rohspalte; ohne diese Trennung liest ein Formular den abgeleiteten Wert
   und das nächste Speichern schreibt ihn in die Spalte.
3. **Der Schreibpfad kennt es nicht** — POST/PUT nehmen das Feld nicht entgegen
   (es steht in `InvestitionResponse`, nicht in `InvestitionBase`).
"""

from __future__ import annotations

import pytest

from backend.api.routes.import_export.json_operations import InvestitionExport
from backend.api.routes.investitionen.crud import (
    InvestitionCreate,
    InvestitionResponse,
    InvestitionUpdate,
    create_investition,
    update_investition,
)
from backend.models import Anlage, Investition


def _response(**felder) -> InvestitionResponse:
    """Response-Schema aus einem ORM-Objekt — wie `response_model` es baut."""
    basis = dict(id=1, anlage_id=1, bezeichnung="Dach Süd", aktiv=True)
    return InvestitionResponse.model_validate(Investition(**{**basis, **felder}))


# ---------------------------------------------------------------------------
# 1. Es heilt — alle Quellen der #229-Klasse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "typ,spalte,parameter,erwartet",
    [
        # Spalte gepflegt — der Normalfall, unverändert.
        ("pv-module", 8.4, None, 8.4),
        # #229: kWp NUR im parameter-JSON, Legacy-Key `kwp`.
        ("pv-module", None, {"kwp": 8.4}, 8.4),
        # #229: kWp NUR im parameter-JSON, kanonischer Key.
        ("pv-module", None, {"leistung_kwp": 8.4}, 8.4),
        # Spalte schlägt das JSON (Spalte ist SoT).
        ("pv-module", 8.4, {"kwp": 99.0}, 8.4),
        # Balkonkraftwerk über die Wp-Formel: 400 Wp × 2 = 0,8 kWp.
        ("balkonkraftwerk", None, {"leistung_wp": 400, "anzahl": 2}, 0.8),
        # BKW ohne gepflegte `anzahl` ⇒ 1 (Lese-Default, NICHT die Formular-2).
        ("balkonkraftwerk", None, {"leistung_wp": 400}, 0.4),
    ],
)
def test_effektiv_findet_die_kwp_in_jeder_quelle(typ, spalte, parameter, erwartet):
    resp = _response(typ=typ, leistung_kwp=spalte, parameter=parameter)
    assert resp.leistung_kwp_effektiv == pytest.approx(erwartet)


def test_rohspalte_bleibt_in_derselben_antwort_die_rohspalte():
    """Die Trennlinie: Anzeige liest `_effektiv`, Formulare lesen `leistung_kwp`.

    Würde das Feld die Rohspalte überschreiben, läse das Investitions-Formular
    den abgeleiteten Wert — und das nächste Speichern schriebe ihn in die
    Spalte. Genau diese Falle hat beim JSON-Export zur Allowlist-Einstufung
    geführt (P3A_BASELINE_AUSNAHMEN, json_operations.py::inv).
    """
    resp = _response(typ="pv-module", leistung_kwp=None, parameter={"kwp": 8.4})

    assert resp.leistung_kwp is None       # Rohspalte: unangetastet
    assert resp.leistung_kwp_effektiv == 8.4


# ---------------------------------------------------------------------------
# 2. 0/None — „nicht gepflegt" bleibt „nicht gepflegt"
# ---------------------------------------------------------------------------

def test_ohne_jede_quelle_bleibt_none_statt_null_kwp():
    """`None` darf nicht zu `0.0` werden.

    Die SoT-Helper liefern `0.0`, wenn sie nichts finden. Eine Anzeige-Zeile
    „0,0 kWp" wäre eine erfundene Zahl, wo heute korrekt gar keine Zeile steht
    — derselbe Fehlertyp wie ein 35°-Neigungs-Default (ADR-002 §offen).
    """
    resp = _response(typ="pv-module", leistung_kwp=None, parameter={})

    assert resp.leistung_kwp_effektiv is None


def test_echte_null_in_der_spalte_bleibt_null():
    """Eine gepflegte 0 ist ein Wert, keine Lücke — sie wird nicht zu `None`."""
    resp = _response(typ="pv-module", leistung_kwp=0.0, parameter=None)

    assert resp.leistung_kwp_effektiv == 0.0


def test_spalte_null_faellt_auf_das_parameter_json_durch():
    """0-Semantik N-C: eine 0 in der Spalte ist „nicht gepflegt", kein Messwert.

    Dieselbe Entscheidung wie in `get_pv_kwp` (`if direct:`); hier gepinnt,
    damit die Response nicht still eine andere Zahl liefert als der Helper.
    """
    resp = _response(typ="pv-module", leistung_kwp=0.0, parameter={"kwp": 8.4})

    assert resp.leistung_kwp_effektiv == 8.4


# ---------------------------------------------------------------------------
# 3. Typabhängigkeit — das Mehrzweckfeld (N-G) wird nicht umgedeutet
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("typ", ["speicher", "wechselrichter", "e-auto", "waermepumpe"])
def test_nicht_erzeuger_bekommen_die_rohspalte_ohne_pv_semantik(typ):
    """Beim Speicher trägt dieselbe Spalte kWh, beim Wechselrichter kW (AC).

    Die SoT-Helper tragen PV-Semantik und sind laut eigenem Docstring nur für
    Erzeuger zuständig. Ein `parameter["kwp"]` an einem Speicher darf deshalb
    NICHT als dessen Nennleistung durchschlagen — sonst hieße eine kWh-Spalte
    plötzlich anders als die Zahl daneben.
    """
    resp = _response(typ=typ, leistung_kwp=10.0, parameter={"kwp": 99.0})

    assert resp.leistung_kwp_effektiv == 10.0


def test_nicht_erzeuger_ohne_spalte_bleibt_none():
    resp = _response(typ="speicher", leistung_kwp=None, parameter={"kwp": 99.0})

    assert resp.leistung_kwp_effektiv is None


# ---------------------------------------------------------------------------
# 4. Nur lesend — der Schreibpfad kennt das Feld nicht
# ---------------------------------------------------------------------------

def test_create_schema_kennt_das_feld_nicht():
    assert "leistung_kwp_effektiv" not in InvestitionCreate.model_fields


def test_update_schema_kennt_das_feld_nicht():
    assert "leistung_kwp_effektiv" not in InvestitionUpdate.model_fields


def test_export_schema_ist_eigenstaendig_und_spiegelt_die_rohspalte():
    """Der JSON-Export ist NICHT betroffen (A26-Prüfauftrag).

    `InvestitionExport` ist ein eigenes Schema und erbt nicht von
    `InvestitionResponse`. Wäre es geteilt, schriebe der Re-Import den
    abgeleiteten Wert in eine bis dahin leere Spalte — der Export VERÄNDERTE
    die Daten, statt sie zu spiegeln.
    """
    assert not issubclass(InvestitionExport, InvestitionResponse)
    assert "leistung_kwp_effektiv" not in InvestitionExport.model_fields
    assert "leistung_kwp" in InvestitionExport.model_fields


async def test_post_nimmt_das_feld_nicht_entgegen(db):
    """Ein mitgesendetes `leistung_kwp_effektiv` darf die Spalte nicht füllen."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    await db.commit()

    data = InvestitionCreate.model_validate({
        "anlage_id": anlage.id,
        "typ": "pv-module",
        "bezeichnung": "Dach Süd",
        "leistung_kwp_effektiv": 99.0,   # wird ignoriert
    })
    inv = await create_investition(data=data, db=db)

    assert inv.leistung_kwp is None
    assert not hasattr(data, "leistung_kwp_effektiv")


async def test_put_nimmt_das_feld_nicht_entgegen(db):
    """Rundlauf Anzeige → Formular → Speichern darf die Spalte nicht befüllen.

    Der reale Weg: das Formular liest die Antwort, der Nutzer speichert. Käme
    der abgeleitete Wert über den Schreibpfad zurück, wanderte er dauerhaft in
    die Spalte — genau die Falle, gegen die die Trennlinie gebaut ist.
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        parameter={"kwp": 8.4},
    )
    db.add(inv)
    await db.flush()
    inv_id = inv.id
    await db.commit()

    vorher = InvestitionResponse.model_validate(inv)
    assert vorher.leistung_kwp_effektiv == 8.4 and vorher.leistung_kwp is None

    daten = InvestitionUpdate.model_validate({
        "leistung_kwp_effektiv": vorher.leistung_kwp_effektiv,
        "bezeichnung": "Dach Süd (neu)",
    })
    nachher = await update_investition(investition_id=inv_id, data=daten, db=db)

    assert nachher.leistung_kwp is None       # Spalte weiterhin leer
    assert nachher.parameter == {"kwp": 8.4}  # Quelle unangetastet
