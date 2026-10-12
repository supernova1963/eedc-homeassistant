"""N-725 — der Tageswert-Rückfall der PV erbt die Vollständigkeit der Module (P4), statt sie als vollständig zu setzen.

**Der Fund.** `services/monats_fakten/bau.py`: fehlt einem Modul der Monatswert und gibt es keinen Anlagenwert
(`pv_modul_summe is None`), füllt die Tagesebene die PV-Summe — und setzte dabei `pv_vollstaendig = True`. Die Tagesebene
lädt jeder Standard-Aufrufer, sobald eine Wallbox-Monatszeile ohne PV-Anteil im Fenster liegt (Ableitung des
PV-Anteils, `laden.py`, N-141 Weg c). Form F16 (Süd mit Zähler, West ohne, kein Gesamtzähler), Juni abgeschlossen über
«Aus HA laden», dazu eine Wallbox mit Juni-Zeile `ladung_kwh` ohne `ladung_pv_kwh`. Gemessen am HEAD `7fb9b026`:

* Monats-Fakten `pv_vollstaendig` **True**, PV 360 (= die Teilsumme Süd);
* der Hinweis «PV-Erzeugung ist eine Teilsumme (06/2026)» **fehlt** in Cockpit → Monat und Cockpit → Jahr;
* die PV-Map des Daten-Checkers prüft gegen **360** statt gegen `None`.

Ohne die Wallbox-Zeile (Gegenprobe, `test_n626_teilsumme_und_checker.py`) ist alles richtig. Soll: die Zahl bleibt
(360 ist auf beiden Wegen dieselbe), das Kennzeichen folgt der Vollständigkeit der Module wie im Zweig ohne
Tagesebene: fehlt einem aktiven Modul der Wert, ist auch der Tageswert eine Teilsumme.

Schwesterdateien: test_n626_teilsumme_und_checker.py (derselbe Monat ohne Wallbox), test_wurzelmuster_p4_teilsumme.py.
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from backend.tests import factories
from backend.tests import pv_achse_matrix as mx


async def _abgeschlossen_mit_wallbox(fid: str, *, mit_wallbox: bool = True) -> dict:
    from backend.services.daten_checker import DatenChecker

    form = mx.FORMEN[fid]
    verz = tempfile.mkdtemp(prefix="eedc-n725-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            svc = mx.seed_ha(form)
            with mx._umgebung(svc):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
                await mx.schreibe_s1_aus_ha_laden(db, aid)
                if mit_wallbox:
                    wb = await factories.investition(db, aid, "wallbox", bezeichnung="Wallbox")
                    await factories.imd(db, wb.id, mx.JAHR, mx.JUNI, {"ladung_kwh": 120.0})
                    await db.commit()
                import backend.api.routes.aktueller_monat as am
                from backend.services.jahres_aggregat import baue_jahr

                monat_roh = await am.get_aktueller_monat(anlage_id=aid, jahr=mx.JAHR, monat=mx.JUNI, db=db)
                jahr_roh = await baue_jahr(db, aid, mx.JAHR, heute=mx.JETZT.date())
                kopf = jahr_roh["kopf"] if isinstance(jahr_roh["kopf"], dict) else jahr_roh["kopf"].model_dump()
                return {
                    "hinweis_monat": list(monat_roh.hinweise or []),
                    "hinweis_jahr": list(kopf.get("hinweise") or []),
                    "fakten": await mx.miss_fakten(db, aid, ids, mx.JUNI),
                    "monat": await mx.miss_cockpit_monat(db, aid, mx.JUNI),
                    "checker_map": await mx.miss_checker(db, aid),
                    "befunde": [f"{e.meldung} {e.details or ''}"
                                for e in (await DatenChecker(db).check_anlage(aid)).ergebnisse],
                }
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.asyncio
async def test_rueckfall_auf_tageswerte_bleibt_teilsumme():
    m = await _abgeschlossen_mit_wallbox("F16")
    assert m["fakten"]["pv"] == pytest.approx(360.0), "die Zahl bleibt"
    assert m["monat"]["pv"] == pytest.approx(360.0)
    assert m["fakten"]["vollstaendig"] is False


@pytest.mark.asyncio
async def test_cockpit_monat_und_jahr_sagen_teilsumme_auch_mit_wallbox_zeile():
    m = await _abgeschlossen_mit_wallbox("F16")
    for liste in (m["hinweis_monat"], m["hinweis_jahr"]):
        treffer = [h for h in liste if "Teilsumme" in h]
        assert treffer and "06/2026" in treffer[0], liste


@pytest.mark.asyncio
async def test_daten_checker_prueft_nicht_gegen_die_teilsumme_auch_mit_wallbox_zeile():
    m = await _abgeschlossen_mit_wallbox("F16")
    assert m["checker_map"]["pv"] is None
    treffer = [b for b in m["befunde"] if "PV-Erzeugung unvollständig" in b]
    assert treffer and "06/2026" in treffer[0], m["befunde"]


@pytest.mark.asyncio
async def test_vollstaendige_module_bleiben_vollstaendig_mit_wallbox_zeile():
    """Gegenprobe: F14 (Gesamtzähler + Süd gemessen, West ohne) — der Anlagenwert füllt die Lücke, kein Hinweis."""
    m = await _abgeschlossen_mit_wallbox("F14")
    assert m["fakten"]["vollstaendig"] is True
    assert not [h for h in m["hinweis_monat"] if "Teilsumme" in h]
