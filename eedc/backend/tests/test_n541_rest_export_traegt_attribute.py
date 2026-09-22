"""N-541 — der REST-Export trägt die Zusatz-Attribute, die MQTT längst publiziert.

**Was fehlte.** `SensorExportItem` kannte elf Felder, und `zusatz_attribute` war
keines davon. Aus dem ganzen Attribut-Block kam genau **ein** Wert durch — der
Satz unter `hinweis` (`vorbehalt`/`grund`). Die Stundenreihen, die Fenster, die
Quellenangaben (`preisquelle`, `profil_typ`, `je_speicher`, `schwelle_cent` …)
endeten an der REST-Grenze.

**Zwei Folgen, beide real:**

* Ein HA-Anwender, der eedc per **REST** einbindet (`rest:`-Plattform, das
  Snippet aus `/api/ha/export/yaml/{id}`), sah Attribute nicht, die die
  Sensor-Referenz beschreibt. Nur der MQTT-Weg trug sie.
* Der **Golden Master** sah sie nicht. Er vergleicht die REST-Sichten; ein
  Umbau, der nur Attribute ändert, lief durch ein grünes Gate. Genau das steht
  mit S3b/B0 an (die ganze Zeitachse der Slot-Beschriftungen wird umgestellt) —
  deshalb kommt dieser Schritt **davor**.

**Die Probe prüft beide Richtungen:** ein Sensor mit Attributen trägt sie, ein
Sensor ohne trägt ein leeres Dict (nicht `None` — ein fehlendes Feld und ein
leeres Feld sind in HA zweierlei), und `hinweis` bleibt daneben unverändert.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Monatsdaten


async def _anlage(db) -> Anlage:
    anlage = Anlage(
        anlagenname="N541-Probe", leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=5,
        einspeisung_kwh=600.0, netzbezug_kwh=100.0,
    ))
    await db.commit()
    return anlage


def _item(key: str, *, attribute: dict | None = None, hinweis_text: str | None = None):
    """Ein `SensorExportItem` aus einem gestellten `SensorValue` — der Weg, den die drei Routen gehen."""
    from backend.api.routes.ha_export.schemas import SensorExportItem
    from backend.services.ha_sensors_export import SensorValue, get_all_sensor_definitions

    definition = next(d for d in get_all_sensor_definitions() if d.key == key)
    zusatz = dict(attribute or {})
    if hinweis_text is not None:
        zusatz["vorbehalt"] = hinweis_text
    return SensorExportItem.von_sensorwert(
        SensorValue(definition=definition, value=42.0, berechnung="x", zusatz_attribute=zusatz)
    )


def test_attribute_kommen_durch():
    """Ein Attribut-Block überlebt die REST-Serialisierungsgrenze vollständig."""
    attribute = {
        "stundenprofil_kwh": [0.0, 1.5, 2.0],
        "preisquelle": "boersenpreis",
        "je_speicher": {"7": 91.0},
        "frist": None,
    }
    item = _item("eedc_ueberschuss_heute_kwh", attribute=attribute)

    assert item.attribute == attribute
    # …und zwar als KOPIE: wer das Item ändert, ändert nicht den Produzenten.
    item.attribute["preisquelle"] = "vertrag"
    assert attribute["preisquelle"] == "boersenpreis"


def test_ohne_attribute_leeres_dict_statt_none():
    """Kein Attribut heißt `{}` — ein fehlendes und ein leeres Feld sind in HA zweierlei."""
    item = _item("eedc_ueberschuss_heute_kwh")
    assert item.attribute == {}
    assert item.attribute is not None


def test_hinweis_bleibt_daneben_stehen():
    """`hinweis` ist die herausgehobene Kurzform, nicht dasselbe wie das Roh-Attribut.

    Beide müssen nebeneinander ankommen — sonst müsste eine Oberfläche, die
    heute `hinweis` liest, morgen im Attribut-Block suchen.
    """
    item = _item("eedc_ueberschuss_heute_kwh", hinweis_text="Wärme geschätzt")
    assert item.hinweis == "Wärme geschätzt"
    assert item.attribute.get("vorbehalt") == "Wärme geschätzt"


def test_schema_kennt_das_feld():
    """Das Antwortmodell selbst trägt `attribute` — sonst fiele es aus dem OpenAPI-Vertrag."""
    from backend.api.routes.ha_export.schemas import SensorExportItem

    assert "attribute" in SensorExportItem.model_fields


#: Ein Stundenprofil, das sich von jedem Nachbarwert unterscheidet — so ist im
#: Ergebnis erkennbar, ob wirklich DIESE Reihe durchgereicht wurde.
PROFIL = [round(0.5 * h, 2) for h in range(24)]


def _stelle_prognose(monkeypatch):
    """Prognose- und Preis-Beschaffung stellen — kein Netz, keine Uhr (N-167-Muster).

    ⚠ Ohne das trägt **kein einziger** Anlagen-Sensor Attribute: alle zwölf
    attributtragenden hängen an Prognose oder Preis (gemessen 22.09.2026 an der
    r28-Kopie). Eine Probe ohne gestellte Quelle wäre grün und blind.
    """
    from backend.api.routes.ha_export import anlage_sensorwerte

    # Das vollstaendige Prognose-Dict kommt aus der Schwesterprobe — ein
    # zweites, handgepflegtes Exemplar waere die Drift-Klasse: `berechne_prognose_export`
    # liefert rund dreissig Pflichtschluessel, und wer hier einen vergisst,
    # misst einen KeyError statt eines Attributs.
    from backend.tests.test_s2_entscheidungs_sensoren import _prognose

    async def _p(db, anlage, *, skip_jitter=False):
        return _prognose(stundenprofil_heute=PROFIL, heute_kwh=sum(PROFIL))

    async def _q(db, anlage):
        return None

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _p)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _q)


@pytest.mark.parametrize("route", ["sensors_alle", "sensors_eine"])
async def test_rest_routen_liefern_attribute(db, monkeypatch, route):
    """Beide Lese-Routen tragen den Block — nicht nur eine von ihnen.

    Gegen die Drift-Klasse, wegen der die drei Bau-Stellen jetzt **einen**
    Konstruktor teilen: `hinweis` wurde 2026-09-05 an drei Stellen nachgetragen,
    ein vierter Aufrufer hätte ihn vergessen.
    """
    from backend.api.routes.ha_export.sensoren import get_all_sensors, get_anlage_sensors

    anlage = await _anlage(db)
    _stelle_prognose(monkeypatch)

    if route == "sensors_alle":
        res = await get_all_sensors(db=db)
        sensoren = [s for a in res.anlagen for s in a.sensors]
    else:
        res = await get_anlage_sensors(anlage.id, db=db)
        sensoren = res.sensors

    assert sensoren, "Vorbedingung: die Route liefert überhaupt Sensoren"
    # Jeder Sensor trägt das Feld (leer ist erlaubt, fehlend nicht).
    assert all(isinstance(s.attribute, dict) for s in sensoren)

    prognose = next((s for s in sensoren if s.key == "eedc_prognose_heute_kwh"), None)
    assert prognose is not None, "Vorbedingung: der Prognose-Sensor entsteht"
    assert prognose.attribute.get("stundenprofil_kwh") == PROFIL, (
        "die Stundenreihe kommt über REST nicht an — genau der Block, den N-541 öffnet"
    )
