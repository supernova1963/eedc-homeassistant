"""`GET /api/mqtt/abwahl` trägt einen Vertrag (Nachlese 4.0.50, A6).

**Eine Route ohne `response_model` hat keinen Vertrag.** `api/routes/ha_export/konfig.py:89`
gab bis zum 22.09.2026 ein handgebautes `dict` zurück — die einzige Antwortroute
des HA-Export-Pakets ohne Modell. Zwei Folgen, beide gemessen:

* **Das OpenAPI-Schema kannte die Antwort nicht.** `/api/docs` zeigte für diese
  Route einen leeren Rumpf; `neues_paket` (N-545, einen Tag alt) kam dort
  überhaupt nicht vor. Wer den Vertrag nachschlagen wollte, musste den
  Quelltext lesen.
* **Nichts hielt Feldfolge und Typen fest.** Ein vergessenes Feld oder ein
  `None` statt `""` wäre erst im Frontend aufgefallen — genau die Klasse, gegen
  die `SensorExportItem` in derselben Datei längst steht.

**Die Antwort selbst ändert sich nicht.** Das hält `test_das_modell_aendert_die_antwort_nicht`
fest: dieselben Schlüssel in derselben Reihenfolge, dieselben Werte. Gemessen
wurde es zusätzlich an einer **Kopie** der Demo-Datenbank (`devbox-r28-demo.db`,
85 Sensordefinitionen) — vorher/nachher bitgleich, MD5 `e98d9729…`.

Schwesterdateien: `test_400_mqtt_sensor_abwahl.py` (die Abwahl-Mechanik selbst — welche
Schlüssel die Settings tragen und was der Publisher daraus macht),
`test_mqtt_export_toggle_b7_5b.py` (die Nachbarroute `POST /mqtt/auto-publish` im selben
Modul) und `test_ha_export_sensor_klassen_vertrag.py` (der Vertrag der Definitionen, aus
denen diese Liste entsteht).
"""

from __future__ import annotations

import json

import pytest

from backend.api.routes.ha_export.konfig import get_sensor_abwahl
from backend.api.routes.ha_export.schemas import (
    SensorAbwahlItem,
    SensorAbwahlResponse,
    SensorPaketInfo,
)
from backend.main import app


def _route_schema() -> dict:
    """Das OpenAPI-Antwortschema der Route — aufgelöst, nicht als `$ref`."""
    spec = app.openapi()
    eintrag = None
    for pfad, methoden in spec["paths"].items():
        if pfad.endswith("/mqtt/abwahl") and "get" in methoden:
            eintrag = methoden["get"]
            break
    assert eintrag is not None, "Route /mqtt/abwahl (GET) nicht im OpenAPI-Dokument"
    ref = eintrag["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    return spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]


def test_das_openapi_schema_nennt_die_drei_felder():
    """Vorher stand hier ein leeres Objekt — `neues_paket` war nirgends dokumentiert."""
    schema = _route_schema()

    assert list(schema["properties"]) == ["abgewaehlt", "neues_paket", "sensoren"]
    assert set(schema["required"]) == {"abgewaehlt", "neues_paket", "sensoren"}


def test_das_schema_beschreibt_auch_die_zeilen_und_das_paket():
    """Ein Modell, das nur den äußeren Rumpf kennt, ist ein halber Vertrag."""
    spec = app.openapi()
    item = spec["components"]["schemas"]["SensorAbwahlItem"]
    paket = spec["components"]["schemas"]["SensorPaketInfo"]

    assert list(item["properties"]) == [
        "key", "name", "unit", "icon", "category", "formel", "exportiert", "neu",
    ]
    assert list(paket["properties"]) == ["paket", "label", "keys", "abgewaehlt"]


async def test_das_modell_aendert_die_antwort_nicht(db):
    """Roh gebautes Dict und serialisiertes Modell — Schlüsselfolge und Werte gleich.

    `json.dumps` **ohne** `sort_keys`: die Reihenfolge ist Teil dessen, was hier
    belegt werden soll. Ein Modell, das die Felder umsortiert, wäre eine
    Vertragsänderung und keine Vertragsbeschreibung.
    """
    roh = await get_sensor_abwahl(db=db)

    durchs_modell = SensorAbwahlResponse.model_validate(roh).model_dump(mode="json")

    assert json.dumps(roh, ensure_ascii=False) == json.dumps(durchs_modell, ensure_ascii=False)


async def test_die_antwort_traegt_ueberhaupt_sensoren(db):
    """Sonst wäre der Vergleich oben eine Aussage über zwei leere Listen."""
    roh = await get_sensor_abwahl(db=db)

    assert len(roh["sensoren"]) > 50
    assert roh["neues_paket"]["paket"] >= 1
    assert roh["neues_paket"]["keys"], "das aktuelle Paket hat Schlüssel"
    assert any(s["neu"] for s in roh["sensoren"])


def test_eine_leere_einheit_bleibt_ein_leerer_string():
    """`binary_sensor` und Textsensoren tragen `""` — nicht `None`.

    Das Frontend hängt die Einheit direkt an die Zahl; ein `None` stünde dort
    als „null". Deshalb ist `unit` im Modell `str` und nicht `Optional[str]`.
    """
    zeile = SensorAbwahlItem(
        key="k", name="n", unit="", icon="mdi:x", category="energie",
        formel="f", exportiert=True, neu=False,
    )

    assert zeile.unit == ""
    with pytest.raises(Exception):
        SensorAbwahlItem(
            key="k", name="n", unit=None, icon="mdi:x", category="energie",
            formel="f", exportiert=True, neu=False,
        )


def test_das_paket_verlangt_seine_vier_felder():
    with pytest.raises(Exception):
        SensorPaketInfo(paket=1, label="x", keys=[])
