"""N-626 — fehlt einem String der Monatswert (und es gibt keinen Anlagenwert), zeigt der Monat die übrigen.

**Der Fund.** ``monats_fakten/bau.py``: ``pv_kwh = (pv_modul_summe or 0.0) + …`` — ``pv_modul_summe`` war
``None``, sobald einem Modul der Wert fehlte, und mit ihm fielen ALLE Modulwerte aus der Summe: Süd 360
gemessen, West ohne, Balkonkraftwerk 90 ⇒ der abgeschlossene Juni nannte 90 statt 450, Eigenverbrauch 0
(Abnahme-Matrix K2, Form F07).

**Der Entscheid (Gernot 04.10.2026, Lesart A):** „Ein möglicher Modul-Ausfall kann ja auch korrekt sein. Ich
habe an sich immer darauf bestanden, dass der Daten-Checker darauf hinweisen muss. Das reicht imo zur
Lösung." Die Anzeige-Summe nimmt die vorhandenen Modulwerte (``pv_monatswerte.pv_teilsumme_je_monat``), das
Flag ``pv_vollstaendig`` bleibt ``False``, die Prüf-Leser bleiben bei „nur vollständig" — und der Daten-Checker
nennt den Monat. Diese Datei hält beides fest: die Zahl und den Hinweis.

Datenstand: Matrix-Bausteine (HA-Statistik + Tageszeilen, Juni über „Aus HA laden"; F16 = F07 ohne BKW).
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from backend.tests import pv_achse_matrix as mx


async def _abgeschlossen(fid: str) -> dict:
    from backend.services.daten_checker import DatenChecker

    form = mx.FORMEN[fid]
    verz = tempfile.mkdtemp(prefix="eedc-n626-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            svc = mx.seed_ha(form)
            with mx._umgebung(svc):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
                await mx.schreibe_s1_aus_ha_laden(db, aid)
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
                    "tabelle": await mx.miss_aggregiert(db, aid, mx.JUNI, voll=False),
                    "checker_map": await mx.miss_checker(db, aid),
                    "befunde": [f"{e.meldung} {e.details or ''}"
                                for e in (await DatenChecker(db).check_anlage(aid)).ergebnisse],
                }
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("fid,summe,module", [("F07", 450.0, 360.0), ("F16", 360.0, 360.0)])
async def test_monat_zeigt_die_vorhandenen_werte(fid, summe, module):
    m = await _abgeschlossen(fid)
    assert m["fakten"]["pv"] == pytest.approx(summe)
    assert m["fakten"]["pv_module"] == pytest.approx(module)
    assert m["fakten"]["vollstaendig"] is False
    assert m["monat"]["pv"] == pytest.approx(summe)
    assert m["monat"]["ev"] == pytest.approx(summe - mx.soll_einspeisung(mx.FORMEN[fid], 30))
    assert m["tabelle"]["pv"] == pytest.approx(summe)
    assert m["tabelle"]["pv_module"] == pytest.approx(module)


@pytest.mark.parametrize("fid", ["F07", "F16"])
async def test_cockpit_monat_und_jahr_sagen_teilsumme(fid):
    """Wo der Anwender es sieht: der Hinweis aus `pv_unvollstaendig_hinweis` in Cockpit → Monat und
    → Jahr (die Monatstabelle trägt nur das Flag, der Client liest es nicht)."""
    m = await _abgeschlossen(fid)
    for liste in (m["hinweis_monat"], m["hinweis_jahr"]):
        treffer = [h for h in liste if "Teilsumme" in h]
        assert treffer and "06/2026" in treffer[0], liste


@pytest.mark.parametrize("fid", ["F07", "F16"])
async def test_daten_checker_nennt_den_monat_und_prueft_nicht_gegen_die_teilsumme(fid):
    m = await _abgeschlossen(fid)
    treffer = [b for b in m["befunde"] if "PV-Erzeugung unvollständig" in b]
    assert treffer, m["befunde"]
    assert "06/2026" in treffer[0]
    assert "kein Gesamtwert" in treffer[0]
    # Die PV-Map der Prüfungen führt nur vollständige Monate (Prüf-Leser bleibt bei „nur vollständig").
    assert m["checker_map"]["pv"] is None
