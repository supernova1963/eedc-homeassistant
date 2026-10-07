"""HA-Bauform E4f (Auftrag Punkt 2, E4c H-5): die Kalendermonats-Schreibwege nehmen für E-Mob und Sonstiges die Kanäle.

„Aus HA laden", alle Monatswerte, Import-Vorschau, Sammelimport und Monatsabschluss-Vorschlag gehen über EINE Stelle
(``bilanz_leser.monatswerte_mit_kanaelen``). Seit E4f ersetzt sie neben den Bilanz-Sensoren auch die E-Mob- und die
Sonstiges-Sensoren durch das Kanal-Δ des Kalendermonats — je Gruppe mit DERSELBEN Quellenwahl wie Cockpit → Monat (E4c,
``geraete_leser.geraete_kalendermonate``): die E-Mob-Gruppe deckt nur samt dem abgeleiteten PV-Anteil der Geräte, die
ihn brauchen; die Sonstiges-Gruppe je Ersatzgruppe mit dem ersten deckenden Feld (W2-R4).

**Wie die Probe Kanal und HA-Leser unterscheidet:** an den Datenständen der Achsen-Matrix (HA-Langzeitstatistik im
echten Recorder-Schema, Spiegel und abgeleiteter Kanal wie im Produkt) sind beide gleich. Die Probe verschiebt deshalb
den Kanal ab dem 15.06. 12:00 um +5 kWh (eine Korrektur in HA, die der Spiegel trägt — Konsistenzlauf); der HA-Leser der
Probe kennt sie nicht. Gedeckt ⇒ alle fünf Wege nennen HA + 5; ungedeckt ⇒ den HA-Leser.

Schwesterdateien: test_kanal_bilanz_gleichheit.py (dieselben Wege für die Bilanz-Gruppe), test_kanal_geraete_leser.py
(die Wahl der Gruppen), test_e4f_lade_kontext.py, test_e4f_nachlauf_nur_fehlende_tage.py.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select, text

from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg

_VERSATZ_AB = int(datetime(2026, 6, 15, 12).timestamp())
_VERSATZ = 5.0

#: (Form, Gerät, Feld) — Wallbox ohne gemessene Aufteilung (abgeleiteter Anteil), E-Auto mit gemessener PV-/Netz-Ladung,
#: Sonstiges-Verbraucher mit Ersatzgruppe (Alt- und Neuname, das erste Feld trägt), Sonstiges-Verbraucher allein.
FAELLE = [
    ("M02", "Wallbox", "ladung_kwh"),
    ("M09", "Privat", "ladung_pv_kwh"),
    ("M07", "Pool", "verbrauch_sonstig_kwh"),
    ("M10", "Sauna", "verbrauch_sonstig_kwh"),
]


async def _sensor(ds, geraet: str, feld: str) -> str:
    anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
    cfg = anlage.sensor_mapping["investitionen"][str(ds.ids[geraet])]["felder"][feld]
    assert cfg["strategie"] == "sensor"
    return cfg["sensor_id"]


async def _verschiebe(ds, key: str, ab: int = _VERSATZ_AB, um: float = _VERSATZ) -> None:
    n = (await ds.db.execute(text(
        "UPDATE kanal_statistik SET sum = sum + :um, state = state + :um WHERE start_ts >= :ab AND kanal_id = "
        "(SELECT id FROM kanal WHERE anlage_id = :a AND key = :k)"), {"um": um, "ab": ab, "a": ds.aid, "k": key})).rowcount
    assert n > 0, key
    await ds.db.commit()


async def _ohne_anfang(ds, key: str) -> None:
    """Der Kanal beginnt erst nach dem 01.06. — er deckt den Juni nicht (Regel (a) der Lese-Schicht)."""
    n = (await ds.db.execute(text(
        "DELETE FROM kanal_statistik WHERE start_ts < :t AND kanal_id = (SELECT id FROM kanal WHERE anlage_id = :a AND "
        "key = :k)"), {"t": int(datetime(2026, 6, 2).timestamp()), "a": ds.aid, "k": key})).rowcount
    assert n > 0, key
    await ds.db.commit()


async def _fuenf_wege(ds, inv_id: int, feld: str, sid: str) -> dict[str, float]:
    """Juni über die fünf Kalendermonats-Wege; der Sammelimport schreibt in die Kopie (letzter Schritt)."""
    from backend.api.routes.ha_statistics import (
        FELD_LABELS, ImportRequest, MonatFeldAuswahl, get_alle_monatswerte, get_import_vorschau, get_monatswerte,
        import_ha_statistics,
    )
    from backend.api.routes.monatsabschluss.views import lade_ha_statistik_werte
    from backend.services.monatswert_deckel import deckel_je_sensor

    def _inv(antwort) -> float:
        return next(f.differenz for i in antwort.investitionen if i.investition_id == inv_id for f in i.felder
                    if f.feld == feld)

    out: dict[str, float] = {}
    out["aus_ha_laden"] = _inv(await get_monatswerte(ds.aid, 2026, 6, ds.db))
    out["alle_monatswerte"] = _inv(next(r for r in await get_alle_monatswerte(ds.aid, None, None, ds.db)
                                        if (r.jahr, r.monat) == (2026, 6)))
    vorschau = next(m for m in (await get_import_vorschau(ds.aid, ds.db)).monate if (m.jahr, m.monat) == (2026, 6))
    out["vorschau"] = next(i.ha_werte[FELD_LABELS.get(feld, feld)] for i in vorschau.investitionen or [] if i.investition_id == inv_id)
    anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
    invs = (await ds.db.execute(select(Investition).where(Investition.anlage_id == ds.aid))).scalars().all()
    vorschlag = await lade_ha_statistik_werte(
        anlage.sensor_mapping["basis"], anlage.sensor_mapping["investitionen"], 2026, 6,
        deckel_je_sensor=deckel_je_sensor(anlage, invs), db=ds.db, anlage_id=ds.aid)
    out["monatsabschluss_vorschlag"] = vorschlag[sid]
    await import_ha_statistics(ds.aid, ImportRequest(monate=[MonatFeldAuswahl(jahr=2026, monat=6)],
                                                      ueberschreiben=True), ds.db)
    await ds.db.commit()
    imd = (await ds.db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == inv_id, InvestitionMonatsdaten.jahr == 2026,
        InvestitionMonatsdaten.monat == 6))).scalar_one()
    await ds.db.refresh(imd)
    out["sammelimport"] = float(imd.verbrauch_daten[feld])
    return out


@pytest.mark.parametrize("fid, geraet, feld", FAELLE)
async def test_gedeckter_kalendermonat_nimmt_in_allen_fuenf_wegen_das_kanal_delta(fid, geraet, feld):
    async with kg.datenstand("achsen", fid, "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN[fid], ds.svc):
            sid = await _sensor(ds, geraet, feld)
            ha = ds.svc.get_monatswerte([sid], 2026, 6).sensoren[0].differenz
            await _verschiebe(ds, f"inv:{ds.ids[geraet]}:{feld}")
            wege = await _fuenf_wege(ds, ds.ids[geraet], feld, sid)
    assert ha > 0
    assert wege == {k: pytest.approx(ha + _VERSATZ) for k in wege}, (ha, wege)


@pytest.mark.parametrize("fid, geraet, feld", FAELLE)
async def test_ungedeckter_kalendermonat_bleibt_in_allen_fuenf_wegen_beim_ha_leser(fid, geraet, feld):
    """Der Kanal des Feldes beginnt erst am 02.06. ⇒ die Gruppe deckt den Juni nicht ⇒ der HA-Leser, für das ganze
    Gerät und die ganze Gruppe (eine Wahl)."""
    async with kg.datenstand("achsen", fid, "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN[fid], ds.svc):
            sid = await _sensor(ds, geraet, feld)
            ha = ds.svc.get_monatswerte([sid], 2026, 6).sensoren[0].differenz
            key = f"inv:{ds.ids[geraet]}:{feld}"
            await _verschiebe(ds, key)
            await _ohne_anfang(ds, key)
            wege = await _fuenf_wege(ds, ds.ids[geraet], feld, sid)
    assert wege == {k: pytest.approx(ha) for k in wege}, (ha, wege)


async def test_emob_gruppe_deckt_nur_samt_dem_abgeleiteten_anteil():
    """M02: die Wallbox misst keine Aufteilung — der abgeleitete PV-Anteil gehört zur Gruppe (E4c). Deckt er den Juni
    nicht, bleibt die Lademenge beim HA-Leser, obwohl ihr eigener Kanal deckt."""
    async with kg.datenstand("achsen", "M02", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M02"], ds.svc):
            inv_id = ds.ids["Wallbox"]
            sid = await _sensor(ds, "Wallbox", "ladung_kwh")
            ha = ds.svc.get_monatswerte([sid], 2026, 6).sensoren[0].differenz
            await _verschiebe(ds, f"inv:{inv_id}:ladung_kwh")
            await _ohne_anfang(ds, f"abgeleitet:inv:{inv_id}:ladung_pv_kwh")
            wege = await _fuenf_wege(ds, inv_id, "ladung_kwh", sid)
    assert wege == {k: pytest.approx(ha) for k in wege}, (ha, wege)


async def test_sammelimport_ersetzt_einen_vorbestand_der_gruppe_nur_mit_dem_flag():
    """Wie die Bilanz-Gruppe (E4a-2, Nachmessung Punkt 4): der Sammelimport tauscht nur seine Wertquelle; ein
    gespeicherter Gerätewert bleibt ohne ``ueberschreiben`` stehen und wird nur mit dem Flag ersetzt — durch das
    Kanal-Δ."""
    from backend.api.routes.ha_statistics import ImportRequest, MonatFeldAuswahl, import_ha_statistics

    async with kg.datenstand("achsen", "M02", "HA") as ds:
        inv_id = ds.ids["Wallbox"]
        with am.umgebung(am.MATRIX_FORMEN["M02"], ds.svc):
            sid = await _sensor(ds, "Wallbox", "ladung_kwh")
            ha = ds.svc.get_monatswerte([sid], 2026, 6).sensoren[0].differenz
            await _verschiebe(ds, f"inv:{inv_id}:ladung_kwh")
            ds.db.add(InvestitionMonatsdaten(investition_id=inv_id, jahr=2026, monat=6,
                                             verbrauch_daten={"ladung_kwh": 999.0}))
            await ds.db.commit()
            werte = []
            for flag in (False, True):
                await import_ha_statistics(ds.aid, ImportRequest(
                    monate=[MonatFeldAuswahl(jahr=2026, monat=6)], ueberschreiben=flag), ds.db)
                await ds.db.commit()
                imd = (await ds.db.execute(select(InvestitionMonatsdaten).where(
                    InvestitionMonatsdaten.investition_id == inv_id, InvestitionMonatsdaten.jahr == 2026,
                    InvestitionMonatsdaten.monat == 6))).scalar_one()
                await ds.db.refresh(imd)
                werte.append(float(imd.verbrauch_daten["ladung_kwh"]))
    assert werte[0] == 999.0
    assert werte[1] == pytest.approx(ha + _VERSATZ)
