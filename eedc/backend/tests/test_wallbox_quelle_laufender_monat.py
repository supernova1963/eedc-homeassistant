"""Der laufende Monat wählt die Heimlade-Quelle wie jede andere Sicht — strukturell.

**Der Befund** (Forum T89667 #363, Johnny_1993, 22.09.2026; am Code gemessen 23.09.):
Der Live-Zweig von ``get_aktueller_monat`` (Werte aus HA-Statistik, MQTT, Connector)
bildete die E-Mobilitäts-Ladung als ``max(E-Auto, Wallbox)``. Das ist die
**Größen-Heuristik**, die ``get_emob_heimladung_canonical`` (KONZEPT-WALLBOX-EAUTO,
Entscheidung 1) ausdrücklich abgelöst hat: Existiert eine Wallbox mit Heimladung, ist
sie die Quelle. Alle anderen Sichten (Cockpit-Übersicht, Monats-Fakten und damit der
gespeicherte Zweig desselben Monats, Jahresbericht, Wallbox-Dashboard) lesen längst
den SoT — der Live-Zweig war die letzte Stelle mit der alten Regel.

**Die Folge:** Ein Fahrverbrauchs-Zähler am E-Auto (Feld „Verbrauch", laut eigener
Felddefinition der *reine Fahrverbrauch*) schlug eine kleinere, echte Wallbox-Ladung
— und die Zahl änderte sich, sobald der Monat abgeschlossen war, weil der gespeicherte
Zweig schon strukturell wählte.

Die Proben laufen über die echte Route mit gestellter Uhr und gestellten Sammlern —
genau der Zweig, den die Symmetrie-Probe (``test_emob_readsite_symmetrie.py``, nur
gespeicherte Monatsdaten) nicht erreicht.
"""

from __future__ import annotations

from datetime import date, datetime

from backend.models import Anlage, Investition, Strompreis

JETZT = datetime(2026, 8, 20, 12, 0)


class _FesteUhr(datetime):
    """``datetime`` mit stehengebliebener ``now()`` — die Route entscheidet daran,
    ob der Monat läuft; eine Probe mit echter Uhr wettete auf den Tag ihres Laufs."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return JETZT


async def _anlage(db, *, mit_wallbox: bool = True):
    anlage = Anlage(anlagenname="Wallbox-Quelle", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    auto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto",
                       anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=30000.0)
    db.add(auto)
    wallbox = None
    if mit_wallbox:
        wallbox = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Ladeziegel",
                              anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=500.0)
        db.add(wallbox)
    await db.commit()
    return anlage.id, auto.id, (wallbox.id if wallbox else None)


async def _laufender_monat(db, monkeypatch, anlage_id, werte: dict):
    import backend.api.routes.aktueller_monat as am

    info = am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92, abdeckung_von=None)

    async def _leer(*args, **kwargs):
        return {}

    async def _ha(anlage, jahr, monat):
        return {k: (v, info) for k, v in werte.items()}

    monkeypatch.setattr(am, "datetime", _FesteUhr)
    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha)
    return await am.get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=8, db=db)


async def test_eine_wallbox_mit_ladung_schlaegt_den_groesseren_fahrverbrauch(db, monkeypatch):
    """Johnnys Konstellation: Wallbox 20 kWh, E-Auto-Fahrverbrauch 100 kWh.

    Bis zum Fix gewann die größere Zahl — der Fahrverbrauch erschien als
    „Ladung gesamt". Nach der strukturellen Regel ist die Wallbox die Quelle.
    """
    anlage_id, auto_id, wb_id = await _anlage(db)

    res = await _laufender_monat(db, monkeypatch, anlage_id, {
        f"inv_{wb_id}_ladung_kwh": 20.0,
        f"inv_{auto_id}_verbrauch_kwh": 100.0,
        f"inv_{auto_id}_km_gefahren": 54.0,
    })

    assert res.emob_ladung_kwh == 20.0
    assert res.emob_km == 54.0


async def test_ohne_wallbox_bleibt_das_e_auto_die_quelle(db, monkeypatch):
    """Steckerlader/Schuko: keine Wallbox — das E-Auto trägt die Ladung (unverändert)."""
    anlage_id, auto_id, _ = await _anlage(db, mit_wallbox=False)

    res = await _laufender_monat(db, monkeypatch, anlage_id, {
        f"inv_{auto_id}_ladung_kwh": 30.0,
    })

    assert res.emob_ladung_kwh == 30.0


def test_externe_ladekosten_kommen_aus_der_teureren_quelle():
    """#260: das Paar (kWh, €) der externen Ladung bleibt orthogonal — die höheren Kosten.

    Direkt an der Funktion: der Wert steht in den aufgelösten Feldern, die Antwort
    führt ihn nicht als eigenes Feld.
    """
    from backend.api.routes.aktueller_monat.aggregation import emob_heimladung_pool

    wallbox = Investition(id=1, typ="wallbox", aktiv=True, anschaffungsdatum=date(2024, 1, 1), parameter={})
    auto = Investition(id=2, typ="e-auto", aktiv=True, anschaffungsdatum=date(2024, 1, 1), parameter={})
    info = object()
    resolved = {
        "inv_1_ladung_kwh": (20.0, info),
        "inv_1_ladung_extern_euro": (4.0, info),
        "inv_2_ladung_extern_euro": (11.0, info),
        "inv_2_verbrauch_kwh": (100.0, info),
    }

    emob_heimladung_pool(direct_fields={}, investitionen=[wallbox, auto], jahr=2026, monat=8,
                         resolved=resolved)

    assert resolved["emob_ladung_kwh"][0] == 20.0
    assert resolved["emob_ladung_extern_euro"][0] == 11.0


def _pool(investitionen, resolved):
    from backend.api.routes.aktueller_monat.aggregation import emob_heimladung_pool

    emob_heimladung_pool(direct_fields={}, investitionen=investitionen, jahr=2026, monat=8,
                         resolved=resolved)
    return resolved.get("emob_ladung_kwh", (None,))[0]


def test_ein_dienstwagen_zaehlt_nicht_zur_heimladung():
    """Dienstwagen zählen separat (`dienstlich_ladekosten`), nicht in der Hausbilanz.

    ⚠ Beim Umbau der Schleife ohne Probe gewesen — ein Sprengsatz (Filter
    entfernt) blieb in 315 Proben grün. Jetzt gedeckt.
    """
    dienst = Investition(id=3, typ="e-auto", aktiv=True, anschaffungsdatum=date(2024, 1, 1),
                         parameter={"ist_dienstlich": True})
    info = object()

    assert _pool([dienst], {"inv_3_ladung_kwh": (40.0, info)}) is None


def test_ein_geraet_vor_seiner_anschaffung_zaehlt_nicht():
    """#239: Werte aus Monaten vor der Anschaffung gehören nicht in den Pool."""
    spaeter = Investition(id=4, typ="wallbox", aktiv=True, anschaffungsdatum=date(2026, 10, 1),
                          parameter={})
    info = object()

    assert _pool([spaeter], {"inv_4_ladung_kwh": (25.0, info)}) is None
