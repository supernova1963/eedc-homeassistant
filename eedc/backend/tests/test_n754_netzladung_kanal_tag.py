"""N-754 (H-3, HA-Bauform S4-Nachlauf) — die Speicher-Netzladung eines Monats ohne Speicher-Zeile ist die Σ seiner Tage, auch an
Kanal-Tagen.

**Befund (HEAD 0a4e852e, gemessen 17.10.2026, Messskript ``plans/ha-bauform-werkzeug/fund-s4-nachlauf/h3_messung.py``):**
Cockpit → Tag nennt die Netzladung eines Kanal-Tags seit E-S4-1 im Kalendertag (``boundary_range.tagesfenster_fuer(…,
kanal_tag=True)``). Die Rechenstelle des Monats-Rückfalls (``monats_fakten/netzladung_tage.speicher_netzladung_aus_tagen``,
gelesen von Cockpit → Monat und den Monats-Fakten) nahm jeden Tag rückwärts ([Vortag 23:00, 23:00)). Über den Monat
teleskopiert das zu ``[Vormonatsletzter 23:00, Monatsletzter 23:00)`` — Monat und Σ der Tagesliste lagen um die Netzladung
der Stunde 23–24 Uhr an den Monatsrändern auseinander. Vor S4 (``1427eed4``) waren Tag und Monat beide rückwärts und gleich.

**Regel seit dem Bau:** rückwärts nur Bestandstage; ein Kanal-Tag (``bilanz_leser.kanal_tage``) im Kalendertag — dieselbe
Weiche wie Cockpit → Tag.

Form: Achsen-Matrix M04, abgewandelt — Akku A lädt NUR 23–24 Uhr aus dem Netz, 1,0 kWh je Nacht, am 30.06. 2,0 kWh. Uhr der
Matrix 04.07.2026 00:30 (Juni vorbei ohne Abschluss, Juli läuft mit drei Tagen).

Schwesterdateien: ``test_427_netzladung_laufender_monat.py`` (dieselbe Rechenstelle, Netzladung 2–4 Uhr),
``test_achsen_matrix.py`` (M04).
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from datetime import datetime

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import pv_achse_matrix as mx

TAGE = am.TAGE_JUNI + am.TAGE_JULI


def _netzladung(t: datetime) -> float:
    if t.hour != 23:
        return 0.0
    return 2.0 if (t.month, t.day) == (6, 30) else 1.0


def _form() -> am.Form:
    m04 = am.MATRIX_FORMEN["M04"]
    akku_a = am.Geraet("Akku A", "speicher", {
        "ladung_kwh": am.summe(am.stunden(0.5, 10, 16), _netzladung),
        "entladung_kwh": am.stunden(0.4, 18, 23),
        "ladung_netz_kwh": _netzladung}, parameter={"kapazitaet_kwh": 10.0})
    return dataclasses.replace(m04, fid="H3", geraete=(akku_a, m04.geraete[1]),
                               netz=am.summe(am.netz_basis, _netzladung))


async def _messe(weg: str) -> dict:
    """Je Tag Cockpit → Tag, je Monat Cockpit → Monat und Monats-Fakten (mit Tageswerten); ``kanal_tage`` gezählt."""
    import backend.api.routes.aktueller_monat as amr
    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.services.kanal.bilanz_leser import kanal_tage
    from backend.services.monats_fakten import lade_monats_fakten

    form = _form()
    verz = tempfile.mkdtemp(prefix="eedc-h3-")
    try:
        engine, db = await mx._neue_db(f"{verz}/{weg}.db")
        try:
            aid, ids = await am.seed_anlage(db, form)
            svc = am.seed_ha(form) if weg == "HA" else mx._ha_aus()
            if weg != "HA":
                await am.seed_snapshots(db, form, aid, ids)
            with am.umgebung(form, svc):
                if weg == "HA":
                    await mx.fuelle_spiegel(engine, aid, svc)
                elif weg == "SA_KANAL":
                    await mx.fuelle_eigene_summe(engine, aid)
                await mx.aggregiere_tage(db, form.pvform, aid, TAGE)
                out = {"kanal_tage": len(await kanal_tage(db, aid, TAGE[0], TAGE[-1]))}
                tage = {t: (await get_tag_detail(anlage_id=aid, datum=t, db=db)).speicher_ladung_netz_kwh for t in TAGE}
                fakten = {f.schluessel: f for f in await lade_monats_fakten(db, aid, inkl_nur_tageswerte=True)}
                for monat in (6, 7):
                    c = await amr.get_aktueller_monat(anlage_id=aid, jahr=2026, monat=monat, db=db)
                    out[monat] = {
                        "summe_tage": round(sum(v for t, v in tage.items() if t.month == monat and v is not None), 4),
                        "cockpit_monat": c.speicher_ladung_netz_kwh,
                        "fakten": fakten[(2026, monat)].speicher.netzladung_kwh,
                    }
            return out
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("weg", ["HA", "SA_KANAL"])
async def test_monat_ist_die_summe_der_kanal_tage(weg):
    """Kanal-Tage: der Monat ist die Σ der Kalendertage — Juni 29 × 1,0 + 2,0 = 31,0, Juli 3 × 1,0 = 3,0 (bis zum Bau 30,0
    und 4,0: die Nacht 29./30.06. zählte im Juni nur als 1,0 und der 30.06. 23–24 Uhr (2,0) im Juli)."""
    m = await _messe(weg)
    assert m["kanal_tage"] == len(TAGE)
    assert m[6]["summe_tage"] == pytest.approx(31.0) and m[7]["summe_tage"] == pytest.approx(3.0)
    for monat in (6, 7):
        assert m[monat]["fakten"] == pytest.approx(m[monat]["summe_tage"]), (monat, m[monat])
    assert m[7]["cockpit_monat"] == pytest.approx(m[7]["summe_tage"])
    # Seit N-758 (17.10.2026) auch ohne HA: der vergangene Juni ist ein voll gedeckter Kanal-Monat, Cockpit → Monat nimmt
    # die fünfte Quelle (Wahl der Monats-Fakten) — bis dahin None (N-472/N-677: keine Ladung/Entladung ohne HA).
    assert m[6]["cockpit_monat"] == pytest.approx(31.0)


async def test_bestandstage_bleiben_rueckwaerts():
    """Gegenprobe ohne Kanäle (Bestandstage): Tag und Monat rückwärts wie vor S4 — Juni 30,0, Juli 4,0, Σ Tage gleich."""
    m = await _messe("SA_BESTAND")
    assert m["kanal_tage"] == 0
    assert (m[6]["summe_tage"], m[6]["fakten"]) == (pytest.approx(30.0), pytest.approx(30.0))
    assert (m[7]["summe_tage"], m[7]["fakten"], m[7]["cockpit_monat"]) == (
        pytest.approx(4.0), pytest.approx(4.0), pytest.approx(4.0))
