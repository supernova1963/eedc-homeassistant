"""N-726 — Cockpit → Monat: ein Netz-Zähler, der nur einen Teil der Tagesspur trägt, wird als Teilwert gekennzeichnet.

**Der Fund.** Ist der Netzbezug-Sensor zugeordnet, HA hat für ihn im laufenden Monat aber keine Zeilen (umbenannte oder
gelöschte Entity), fällt Cockpit → Monat auf die Tagesebene zurück (`aktueller_monat/__init__.py::
_collect_tagesebene_data`). Dort genügt für «erfasst» schon EINE Stunde mit Wert (N-585); die Abdeckung, die die
Provenanz-Zeile nennt, gilt der ganzen Spur, nicht dem Feld. Gemessen am HEAD `7fb9b026` (Form F06 der PV-Matrix,
HA-Weg, Netz-Sensor ohne Juli-Zeilen, `JETZT` = 04.07. 00:30):

* Juli: **Netzbezug 0,4 kWh, Autarkie 99,1 %**, Quelle `tagesebene`, `hinweise []`;
* mit den Juli-Zeilen (Gegenprobe): Netzbezug 21,6, Autarkie 67,6 %.

Soll (Entscheid: kennzeichnen wie N-678, nicht unterdrücken): die Zahl bleibt, die Antwort sagt in `hinweise`, dass
der Netzbezug nur einen Teil der Tage misst (P4: «die Unvollständigkeit gehört in die Response»).

Schwesterdateien: test_wurzelmuster_p4_teilsumme.py (P4-Form), test_n472_laufender_monat_quellen.py (Tagesebene als
fünfte Quelle).
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime

import pytest

from backend.tests import pv_achse_matrix as mx

JULI_START = datetime(mx.JAHR, mx.JULI, 1)


async def _juli(*, netz_ohne_juli: bool, standalone: bool = False) -> dict:
    import backend.api.routes.aktueller_monat as am

    form = mx.FORMEN["F06"]
    abw = {"sensor.netz": (None, lambda t: t >= JULI_START)} if netz_ohne_juli else None
    verz = tempfile.mkdtemp(prefix="eedc-n726-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            if standalone:
                await mx.seed_snapshots(db, form, aid, ids)
                svc = mx._ha_aus()
            else:
                svc = mx.seed_ha(form, abweichung=abw)
            with mx._umgebung(svc):
                if not standalone:
                    await mx.fuelle_spiegel(engine, aid, svc)
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
                r = await am.get_aktueller_monat(anlage_id=aid, jahr=mx.JAHR, monat=mx.JULI, db=db)
            fq = (r.feld_quellen or {}).get("netzbezug_kwh")
            quelle = fq.get("quelle") if isinstance(fq, dict) else getattr(fq, "quelle", None)
            return {"netz": mx._r(r.netzbezug_kwh), "autarkie": mx._r(r.autarkie_prozent),
                    "quelle": quelle, "hinweise": list(r.hinweise or [])}
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.asyncio
async def test_netz_teilwert_wird_gekennzeichnet():
    m = await _juli(netz_ohne_juli=True)
    assert m["quelle"] == "tagesebene", m
    netz_hinweise = [h for h in m["hinweise"] if "Netzbezug" in h]
    assert netz_hinweise, m
    assert "am 01.07." in netz_hinweise[0] and "vom 01.07. bis 03.07." in netz_hinweise[0], netz_hinweise
    assert (m["netz"], m["autarkie"]) == (0.4, 99.1), "beschriften, nicht unterdrücken"


@pytest.mark.asyncio
async def test_voller_netz_zaehler_bleibt_ohne_hinweis():
    """Gegenprobe: mit den Juli-Zeilen misst der Zähler den Monat bis jetzt — kein Hinweis, Zahl unverändert."""
    m = await _juli(netz_ohne_juli=False)
    assert not [h for h in m["hinweise"] if "Netzbezug" in h], m


@pytest.mark.asyncio
async def test_tagesebene_mit_vollem_netz_zaehler_bleibt_ohne_hinweis():
    """Gegenprobe Standalone (ohne HA): die Tagesebene gewinnt, der Netz-Zähler trägt alle Tage — kein Hinweis."""
    m = await _juli(netz_ohne_juli=False, standalone=True)
    assert m["quelle"] == "tagesebene", m
    assert not [h for h in m["hinweise"] if "Netzbezug" in h or "Einspeisung" in h], m
