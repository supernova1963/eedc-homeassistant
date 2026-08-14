"""Das Balkonkraftwerk gehört in die PV-Achse — auch im laufenden Monat.

Gemeldet von **dietmar1968** (Forum T77723 #775, 13.08.2026) an seinem eigenen
Bild: *Cockpit → Monat*, August 2026 (laufend, Quelle HA-Statistik). Die Kennzahl
„PV-Erzeugung" und die Energie-Bilanz standen auf **679 kWh**, während der
Kategorien-Block darunter korrekt „PV-Module 679 · Balkonkraftwerk 45" auswies —
Σ 724. Die 45 kWh tauchten in keiner Bilanzgröße auf.

**Die Ursache war eine Asymmetrie zwischen den zwei Zweigen derselben Route:**

* **DB-Zweig** (abgeschlossener Monat, ``_collect_saved_data``): setzt
  ``pv_erzeugung_kwh = fakt.erzeugung.pv_kwh`` — und ``ErzeugungFakten.pv_kwh``
  ist laut Kanon ausdrücklich „Module **+ Balkonkraftwerk"``. Korrekt, und seit
  C1c durch ``test_c1c_aktueller_monat_monats_fakten.py`` gedeckt.
* **Sensor-Zweig** (laufender Monat, ``typ_aggregation``): mappte
  ``balkonkraftwerk`` **nur** auf ``bkw_erzeugung_kwh``. Dieser Schlüssel wurde
  ausschließlich in die Response gelegt und **nie** zur PV-Achse addiert.

⇒ Dieselbe Anlage bekam zwei verschiedene PV-Zahlen, je nachdem ob der Monat
lief oder abgeschlossen war. Ein Monat „reparierte sich" beim Abschluss selbst.

⚠ **Was hier ausdrücklich KEINE Doppelzählung ist.** Das BKW läuft bewusst in
**zwei** Größen: ``bkw_erzeugung_kwh`` ist seine **eigene Zeile** (ROI/Finanz —
dort hat es eine getrennte Position), ``pv_erzeugung_kwh`` ist die **PV-Achse der
Anlage**. Die Trennung, die bleiben muss, liegt eine Ebene tiefer und ist eine
andere: ``pv_je_modul`` (nur ``pv-module``) gegen
``BkwFakten.erzeugung_je_investition`` — *dort* würde ein BKW in beiden Töpfen die
ROI-Zeile doppelt zählen. Siehe ``project_bkw_erzeuger_abgrenzung``.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Investition, Monatsdaten, Strompreis


async def _seed_pv_und_bkw(db: AsyncSession, *, jahr: int, monat: int) -> tuple[int, int, int]:
    """Anlage mit PV-Modulen **und** einem Balkonkraftwerk (dietmars Aufbau)."""
    anlage = Anlage(anlagenname="BKW-Achse", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=jahr, monat=monat,
        netzbezug_kwh=4.0, einspeisung_kwh=320.0,
    ))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Strassenseite",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=800.0)
    db.add_all([pv, bkw])
    await db.commit()
    return anlage.id, pv.id, bkw.id


def _info(am, quelle: str, konfidenz: int):
    return am.DatenquelleInfo(quelle=quelle, konfidenz=konfidenz, abdeckung_von=None)


async def test_laufender_monat_bkw_zaehlt_in_die_pv_achse(db, monkeypatch):
    """dietmar1968s Fall: 679 (Module) + 45 (BKW) müssen 724 ergeben.

    ⛔ **Der Sprengsatz für diesen Test:** in ``typ_aggregation`` beim Schlüssel
    ``balkonkraftwerk`` das Ziel ``"pv_erzeugung_kwh"`` aus dem Tupel entfernen.
    Dann steht ``pv_erzeugung_kwh`` wieder auf 679 — dem gemeldeten Zustand.
    """
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id, pv_id, bkw_id = await _seed_pv_und_bkw(db, jahr=now.year, monat=now.month)

    async def _leer(*args, **kwargs):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        # Genau wie HA-Statistik es liefert: je Investition ein eigener Wert.
        return {
            f"inv_{pv_id}_pv_erzeugung_kwh": (679.0, _info(am, "ha_statistics", 92)),
            f"inv_{bkw_id}_pv_erzeugung_kwh": (45.0, _info(am, "ha_statistics", 92)),
        }

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(
        anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db
    )

    # Die PV-Achse trägt beide Erzeuger — das ist die gemeldete Zahl.
    assert res.pv_erzeugung_kwh == 724.0
    # Und die eigene Zeile des BKW bleibt unangetastet (ROI/Finanz brauchen sie).
    assert res.bkw_erzeugung_kwh == 45.0


async def test_laufender_monat_ohne_bkw_unveraendert(db, monkeypatch):
    """Gegenprobe: ohne Balkonkraftwerk bewegt der Bau nichts.

    Schützt davor, dass die Mehrfach-Ziel-Aggregation reine PV-Anlagen
    verändert — die überwiegende Mehrheit der Installationen.
    """
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id, pv_id, _bkw_id = await _seed_pv_und_bkw(db, jahr=now.year, monat=now.month)

    async def _leer(*args, **kwargs):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {f"inv_{pv_id}_pv_erzeugung_kwh": (679.0, _info(am, "ha_statistics", 92))}

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(
        anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db
    )
    assert res.pv_erzeugung_kwh == 679.0


async def test_anlagen_gesamtwert_sperrt_die_bkw_addition(db, monkeypatch):
    """Ein direkter Anlagen-Gesamtwert misst das BKW bereits mit — dann darf
    nicht zusätzlich aggregiert werden.

    Das ist die eigentliche Doppelzählungs-Gefahr dieses Baus: Wer einen
    Gesamt-Erzeugungssensor gemappt hat, bekommt ``pv_erzeugung_kwh`` direkt
    gesetzt; die ``direct_fields``-Sperre in ``_aggregate`` muss dann greifen.
    """
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id, pv_id, bkw_id = await _seed_pv_und_bkw(db, jahr=now.year, monat=now.month)

    async def _leer(*args, **kwargs):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {
            # Anlagen-Gesamtwert (misst beide Erzeuger) …
            "pv_erzeugung_kwh": (724.0, _info(am, "ha_statistics", 92)),
            # … und zusätzlich die Einzelwerte.
            f"inv_{pv_id}_pv_erzeugung_kwh": (679.0, _info(am, "ha_statistics", 92)),
            f"inv_{bkw_id}_pv_erzeugung_kwh": (45.0, _info(am, "ha_statistics", 92)),
        }

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(
        anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db
    )
    # 724, nicht 769 (= 724 + 45) und nicht 1448.
    assert res.pv_erzeugung_kwh == 724.0
