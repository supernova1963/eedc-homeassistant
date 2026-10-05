"""Proben Betriebsart-Mitschrift (HA-Bauform E1, Auftrag Punkt 4 „Mitschrift").

Quelle ist der Zustands-Verlauf, den die Tagesaggregation ohnehin liest
(``energie_profil/_helpers._get_betriebsmodus_history``). Die Mitschrift legt je Wärmepumpe und
abgeschlossener Stunde „Anteil der Stunde je Betriebsart" ab — in jedem Kanon-Modus eine Zeile.

**Die Klasse N-595/N-596:** eine geschriebene Mitschrift-Stunde bleibt bei erneutem Lauf mit
anderer Quelle und bei fehlender Quelle unverändert — keine Zeile wird überschrieben oder geleert.

Die Uhr steht fest (``jetzt=`` / ``ZustandsVerlauf``) — keine Probe liest die echte Uhr.

Schwesterdateien: test_kanal_spiegel.py, test_kanal_eigene_summe.py, test_kanal_bestand_unberuehrt.py, test_kanal_feld_deckung.py; Quelle der Betriebsart: test_263_k2_betriebsmodus_lesen_mitschreiben.py.
"""

from __future__ import annotations

import time as _zeit
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.core.betriebsmodus import BETRIEBSMODUS_KANON
from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalQuelle, KanalStatistik
from backend.services.energie_profil import _helpers
from backend.services.kanal.schreiber import EINHEIT_ANTEIL, schreibe_betriebsart_mitschrift
from backend.tests import factories, ha_lts_helfer

TAG = date(2026, 6, 10)
T0 = datetime(2026, 6, 10, 0)


def _ts(dt: datetime) -> int:
    return int(_zeit.mktime(dt.timetuple()))


async def _anlage(db):
    a = await factories.anlage(db, sensor_mapping={"basis": {}, "investitionen": {}})
    wp = await factories.investition(db, typ="waermepumpe", anlage_id=a.id)
    a.sensor_mapping = {"basis": {}, "investitionen": {str(wp.id): {"live": {"betriebsmodus": "climate.wp"}}}}
    await db.commit()
    return a, wp


async def _verlauf(db, a, zustaende):
    with patch("backend.services.ha_state_service.get_ha_state_service",
               lambda: ha_lts_helfer.ZustandsVerlauf({"climate.wp": zustaende})):
        return await _helpers._get_betriebsmodus_history(a, a.sensor_mapping, TAG, db)


async def _zeilen(db, a, wp_id) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for modus in BETRIEBSMODUS_KANON:
        k = (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id,
                                                  Kanal.key == f"modus:inv:{wp_id}:{modus}"))).scalar_one_or_none()
        if k is None:
            continue
        rows = (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all()
        out[modus] = {r.start_ts: r.mean for r in rows}
    return out


#: Heizen bis 05:15, dann Kühlen, ab 05:45 Aus — Vortag 22:00 schon Heizen (Fortschreibung).
VERLAUF = [
    (datetime(2026, 6, 9, 22), "heat"),
    (T0 + timedelta(hours=5, minutes=15), "cool"),
    (T0 + timedelta(hours=5, minutes=45), "off"),
]


async def test_anteile_kommen_aus_derselben_schleife_wie_der_gewinner(db):
    a, wp = await _anlage(db)
    m = await _verlauf(db, a, VERLAUF)
    # Slot 6 = [05:00, 06:00): 15 min Heizen, 30 min Kühlen, 15 min Aus ⇒ Gewinner Kühlen
    assert m[6] == {wp.id: "kuehlen"}
    assert m.anteile[6][wp.id] == pytest.approx({"heizen": 0.25, "kuehlen": 0.5, "aus": 0.25})
    assert m.anteile[3][wp.id] == {"heizen": 1.0}
    assert m.entitaeten == {wp.id: "climate.wp"}
    assert dict(m) == {h: {wp.id: v[wp.id]} for h, v in m.items()}    # wertgleich ein dict


async def test_mitschrift_je_modus_und_nur_abgeschlossene_stunden(db):
    a, wp = await _anlage(db)
    m = await _verlauf(db, a, VERLAUF)
    jetzt = T0 + timedelta(hours=6, minutes=10)     # Slots 0…6 abgeschlossen (Slot 6 endet 06:00)
    n = await schreibe_betriebsart_mitschrift(db, a, TAG, m, jetzt=jetzt)
    await db.commit()
    z = await _zeilen(db, a, wp.id)
    assert set(z) == set(BETRIEBSMODUS_KANON)
    slot6 = _ts(T0 + timedelta(hours=5))
    assert {mo: z[mo][slot6] for mo in z} == pytest.approx(
        {mo: {"heizen": 0.25, "kuehlen": 0.5, "aus": 0.25}.get(mo, 0.0) for mo in BETRIEBSMODUS_KANON})
    for werte in z.values():
        assert max(werte) == slot6                                    # Slot 7 (läuft noch) fehlt
        assert min(werte) == _ts(T0 - timedelta(hours=1))            # Slot 0 = Vortag 23:00
    assert n == 7 * len(BETRIEBSMODUS_KANON)
    k = (await db.execute(select(Kanal).where(Kanal.key == f"modus:inv:{wp.id}:heizen"))).scalar_one()
    assert (k.art, k.einheit) == ("mean", EINHEIT_ANTEIL)
    q = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()
    assert [(x.familie, x.statistic_id) for x in q] == [(FAMILIE_MITSCHRIFT, "climate.wp")]


async def test_geschriebene_stunde_bleibt_bei_neuer_und_bei_fehlender_quelle(db):
    """N-595/N-596: Der Verlauf ändert sich (oder fehlt, weil HA ihn gelöscht hat) — die schon
    geschriebenen Stunden stehen danach bitgleich da; nur neue Stunden kommen dazu."""
    a, wp = await _anlage(db)
    await schreibe_betriebsart_mitschrift(db, a, TAG, await _verlauf(db, a, VERLAUF),
                                          jetzt=T0 + timedelta(hours=6, minutes=10))
    await db.commit()
    vorher = await _zeilen(db, a, wp.id)

    anders = [(datetime(2026, 6, 9, 22), "cool")]                      # ganz anderer Verlauf
    n = await schreibe_betriebsart_mitschrift(db, a, TAG, await _verlauf(db, a, anders),
                                              jetzt=T0 + timedelta(hours=8, minutes=10))
    await db.commit()
    nachher = await _zeilen(db, a, wp.id)
    for mo in vorher:
        assert {ts: nachher[mo][ts] for ts in vorher[mo]} == vorher[mo]
    assert n == 2 * len(BETRIEBSMODUS_KANON)                            # nur Slots 7 und 8 neu

    leer = await _verlauf(db, a, [])                                    # Quelle verfallen
    assert await schreibe_betriebsart_mitschrift(db, a, TAG, leer, jetzt=T0 + timedelta(days=2)) == 0
    await db.commit()
    assert await _zeilen(db, a, wp.id) == nachher


async def test_ohne_anteile_schreibt_die_mitschrift_nichts(db):
    """Eine ersetzte Quelle (Proben liefern ein einfaches dict) trägt keine Anteile."""
    a, wp = await _anlage(db)
    assert await schreibe_betriebsart_mitschrift(db, a, TAG, {6: {wp.id: "heizen"}}, jetzt=T0 + timedelta(days=1)) == 0
    assert (await db.execute(select(Kanal))).first() is None


# ── Umstellungstage: die EINE Umrechnung Slot → start_ts (HA-Bauform E2, B2) ──────────────────────

_UMSTELLUNG = (date(2026, 3, 29), date(2026, 10, 25), date(2026, 4, 5), date(2026, 9, 27))


@pytest.mark.parametrize("tag", _UMSTELLUNG, ids=str)
async def test_umstellungstag_jede_reale_stunde_genau_eine_zeile(db, tag):
    """Je Slot ein unterscheidbarer Anteil; geschrieben über den Einstieg der Tagesaggregation.

    In JEDER Zone (die Datei läuft in Berlin, UTC und Auckland): jede Zeile steht auf
    ``slot_start_ts(tag, h)`` — Herbst: die spätere 02:00, Frühjahr: der Slot ohne reale Stunde hat keine
    Zeile —, kein Zeitstempel doppelt, kein Slot mit realer Stunde fehlt, kein Fehlervermerk. In Berlin am
    29.03. warf die alte Umrechnung (fold=0: Slot 2 und 3 auf 1774742400) und die ganze Mitschrift des
    Tages rollte zurück.
    """
    from backend.core.berechnungen.slot_konvention import lts_boundary_index, slot_start_ts
    from backend.models.activity_log import ActivityLog
    from backend.services.energie_profil._helpers import ModusJeStunde
    from backend.services.kanal.schreiber import schreibe_betriebsart_mitschrift_sicher

    a, wp = await _anlage(db)
    m = ModusJeStunde({h: {wp.id: "heizen"} for h in range(24)},
                      anteile={h: {wp.id: {"heizen": h / 100, "aus": 1 - h / 100}} for h in range(24)},
                      entitaeten={wp.id: "climate.wp"})
    jetzt = datetime.combine(tag + timedelta(days=1), datetime.min.time()) + timedelta(hours=12)
    with patch("backend.services.kanal.schreiber.datetime") as dt:
        dt.now.return_value = jetzt
        dt.combine, dt.min = datetime.combine, datetime.min
        n = await schreibe_betriebsart_mitschrift_sicher(db, a, tag, m)
    await db.commit()
    soll = {slot_start_ts(tag, h): h / 100 for h in range(24) if slot_start_ts(tag, h) is not None}
    z = await _zeilen(db, a, wp.id)
    assert z["heizen"] == soll
    assert n == len(soll) * len(BETRIEBSMODUS_KANON)
    assert all(lts_boundary_index(datetime.fromtimestamp(ts), tag) == round(w * 100) for ts, w in z["heizen"].items())
    assert not (await db.execute(select(ActivityLog))).scalars().all()
