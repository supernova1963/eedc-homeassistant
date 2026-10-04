"""N-629 — die Import-Vorschau einer Anlage nur mit Balkonkraftwerk kennt den lokalen Monatswert.

**Der Fund.** Der lokale PV-Gesamtwert der Vorschau entstand nur über die ``pv-module``
(``lade_pv_je_monat``); der eigene BKW-Wert wurde zu einem vorhandenen Eintrag addiert. Eine Anlage
ohne Modul hatte keinen Eintrag: ein abgeschlossener Monat stand als „Fehlt lokal: PV Erzeugung
Gesamt", Aktion „importieren", obwohl er 90 kWh führte (Abnahme-Matrix K4, Form F11).

**Die Regel** (Bauplan PV-Achse T7): Monate OHNE aktives ``pv-module`` — lokal = eigene BKW-Werte +
BKW-Anteile am Anlagenwert (``eigene_bkw_erzeugung_kwh``, ``bkw_ohne_eigenen_wert``). Monate MIT Modul
bleiben bei ``pv_summe_je_monat``: eine Modul-Lücke ohne Anlagenwert bleibt „fehlt lokal → importieren"
— der Import schließt sie; die Anzeige-Summe der Monats-Fakten (seit N-626 eine Teilsumme) wäre dort
ein falscher Konflikt.

Datenstand: Matrix-Bausteine (HA-Statistik + Tageszeilen, Juni über „Aus HA laden" bzw. Handeingabe
über ``create_monatsdaten``).
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from backend.tests import pv_achse_matrix as mx


async def _vorschau(fid: str, *, handeingabe=None) -> dict:
    form = mx.FORMEN[fid]
    verz = tempfile.mkdtemp(prefix="eedc-n629-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            svc = mx.seed_ha(form)
            with mx._umgebung(svc):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI)
                if handeingabe is None:
                    await mx.schreibe_s1_aus_ha_laden(db, aid)
                else:
                    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten
                    await create_monatsdaten(MonatsdatenCreate.model_validate(handeingabe(aid, ids)), None, db)
                    await db.commit()
                return await mx.miss_vorschau(db, aid)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def test_reine_bkw_anlage_abgeschlossener_monat_ist_lokal_vorhanden():
    v = await _vorschau("F11")
    assert v["pv"] == pytest.approx(90.0)
    assert v["ha_pv"] == pytest.approx(90.0)
    assert v["aktion"] != "importieren"


async def test_modul_luecke_ohne_anlagenwert_bleibt_fehlt_lokal():
    """F04-Zuordnung, Handeingabe nur Süd (360), West und BKW leer, kein Anlagenwert: die Vorschau
    rät weiter zum Import (der den Anlagenzähler mitbringt) — kein Konflikt mit der Teilsumme."""
    def eingabe(aid, ids):
        return {"anlage_id": aid, "jahr": mx.JAHR, "monat": mx.JUNI, "einspeisung_kwh": 180.0,
                "netzbezug_kwh": 216.0, "geprueft_gegen": {},
                "investitionen_daten": {str(ids["Süd"]): {"pv_erzeugung_kwh": 360.0}}}
    v = await _vorschau("F04", handeingabe=eingabe)
    assert v["pv"] is None
    assert v["aktion"] == "importieren"
