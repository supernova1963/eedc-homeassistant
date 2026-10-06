"""Proben Leser der E-Mob- und Sonstiges-Gruppe (HA-Bauform E4c, Auftrag Punkt 1, 2, 4; ``services/kanal/geraete_leser.py``).

* Die Wahl einer Gruppe als reine Funktion: jeder Kanal muss decken, in einer Ersatzgruppe genügt einer und der ERSTE
  deckende trägt (W2-R4); der abgeleitete Kanal gehört zur E-Mob-Gruppe; der Anteil ist ``Σ Δ abgeleitet / Σ Δ Ladung``.
* An Datenständen der Achsen-Matrix (HA-Langzeitstatistik im echten Recorder-Schema): Zeilen und Anteil je Monat;
  ein abgeleiteter Kanal, der erst mitten im Monat beginnt, deckt ihn nicht (der Monat bleibt beim Bestand).
* **Eine Aufteilung für alle Sichten** (F-16): die Quote, die die Monats-Fakten für einen gedeckten Monat nehmen, ist
  dieselbe, die ``emob_ladeanteil.lade_abgeleitete_ladeanteile`` den Sichten außerhalb der Fakten gibt — auch wenn
  die Tagesebene etwas anderes sagt.
* **Pool auf den Kanal-Zeilen** (eigene Form: Wallbox + Auto mit eigener Messung + Auto ohne): das gemessene Auto trägt
  seine Ladung, der Rest der Wallbox geht an das andere — über die eine Funktion, wie im abgeschlossenen Monat.

Schwesterdateien: test_kanal_abgeleitet.py, test_kanal_geraete_gleichheit.py, test_kanal_bilanz_leser_wahl.py.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.kanal import Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.kanal.abgeleitet import abgeleitet_key
from backend.services.kanal.geraete_leser import _Bedarf, geraete_monate, waehle_gruppe
from backend.services.kanal.lesen import Zeitraum
from backend.services.kanal.quellenwahl import QUELLE_BESTAND, QUELLE_KANAL
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

JUNI, JULI = (mx.JAHR, mx.JUNI), (mx.JAHR, mx.JULI)


def _z(key: str, delta, *, voll: bool = True) -> Zeitraum:
    return Zeitraum(key=key, art="sum", einheit="kWh", von=0, bis=1, delta=delta if voll else None,
                    teil_delta=None if voll else delta, gedeckt_von=0, gedeckt_bis=1, rand_spanne=3600, voll=voll,
                    grund=None if voll else "beginnt_nach_von", laufend=False)


# ── Wahl (rein) ─────────────────────────────────────────────────────────────


def test_wahl_jeder_kanal_muss_decken_und_die_ersatzgruppe_nimmt_den_ersten_deckenden():
    b = _Bedarf(direkt={1: ["ladung_kwh"]}, ersatz={2: [["verbrauch_sonstig_kwh", "verbrauch_kwh"]]})
    e = {"inv:1:ladung_kwh": _z("a", 90.0), "inv:2:verbrauch_sonstig_kwh": _z("b", 72.0),
         "inv:2:verbrauch_kwh": _z("c", 108.0)}
    g = waehle_gruppe(b, e)
    assert g.wahl.quelle == QUELLE_KANAL
    assert g.zeilen == {1: {"ladung_kwh": 90.0}, 2: {"verbrauch_sonstig_kwh": 72.0}}
    # Der erste deckt nicht ⇒ der zweite trägt (W2-R4).
    e["inv:2:verbrauch_sonstig_kwh"] = _z("b", 70.0, voll=False)
    assert waehle_gruppe(b, e).zeilen[2] == {"verbrauch_kwh": 108.0}
    # Keiner der Ersatzgruppe deckt ⇒ die GANZE Gruppe bleibt beim Bestand (kein Wert halb aus der einen Quelle).
    e["inv:2:verbrauch_kwh"] = _z("c", 100.0, voll=False)
    g = waehle_gruppe(b, e)
    assert g.wahl.quelle == QUELLE_BESTAND and not g.zeilen and "inv:2:verbrauch_sonstig_kwh" in g.wahl.gruende
    # Ein direktes Feld ohne Kanal ⇒ Bestand.
    assert waehle_gruppe(_Bedarf(direkt={1: ["ladung_kwh"]}), {}).wahl.gruende == {"inv:1:ladung_kwh": "kein_kanal"}
    # Ohne jeden Eingang ⇒ Bestand („keine Eingänge").
    assert waehle_gruppe(_Bedarf(), {}).wahl.gruende == {"": "keine_eingaenge"}


def test_wahl_der_abgeleitete_kanal_gehoert_zur_gruppe_und_ergibt_den_anteil():
    b = _Bedarf(direkt={1: ["ladung_kwh"]}, abgeleitet={1: ("inv:1:ladung_kwh",)})
    e = {"inv:1:ladung_kwh": _z("a", 90.0), abgeleitet_key(1): _z("d", 67.5)}
    g = waehle_gruppe(b, e)
    assert g.quote == pytest.approx(0.75)
    assert waehle_gruppe(b, {"inv:1:ladung_kwh": _z("a", 90.0)}).wahl.quelle == QUELLE_BESTAND
    assert waehle_gruppe(b, {**e, abgeleitet_key(1): _z("d", 67.5, voll=False)}).quote is None
    # Ohne Ladung ⇒ keine Aussage.
    assert waehle_gruppe(b, {"inv:1:ladung_kwh": _z("a", 0.0), abgeleitet_key(1): _z("d", 0.0)}).quote is None


# ── An Datenständen ─────────────────────────────────────────────────────────


async def test_m02_zeilen_und_anteil_je_monat():
    async with kg.datenstand("achsen", "M02", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M02"], ds.svc):
            g = await geraete_monate(ds.db, ds.aid, von=JUNI, bis=JULI)
    wb = ds.ids["Wallbox"]
    assert g[JUNI].emob.kanal and g[JULI].emob.kanal
    assert g[JUNI].emob.zeilen[wb]["ladung_kwh"] == pytest.approx(90.0)
    assert g[JULI].emob.zeilen[wb]["ladung_kwh"] == pytest.approx(9.0)
    assert g[JUNI].emob.quote == pytest.approx(1.0)         # die Ladestunden liegen in der Sonne ohne Netzbezug
    assert g[JUNI].sonstiges.wahl.gruende == {"": "keine_eingaenge"}


async def test_abgeleiteter_kanal_ab_monatsmitte_deckt_den_monat_nicht():
    """Beginnt der abgeleitete Kanal erst am 15.06. (Update mitten im Monat), bleibt die E-Mob-Gruppe des Juni beim
    Bestand — die Monats-Fakten ohne Abschluss nennen dort keine Lademenge (heute) —, der Juli kommt aus den Kanälen."""
    from backend.services.monats_fakten import lade_monats_fakten

    async with kg.datenstand("achsen", "M02", "HA") as ds:
        k = (await ds.db.execute(select(Kanal).where(Kanal.anlage_id == ds.aid,
                                                     Kanal.key == abgeleitet_key(ds.ids["Wallbox"])))).scalar_one()
        grenze = int(datetime(2026, 6, 15).timestamp())
        await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id == k.id,
                                                         KanalStatistik.start_ts < grenze))
        k.aufbaubar_ab = grenze
        await ds.db.commit()
        with am.umgebung(am.MATRIX_FORMEN["M02"], ds.svc):
            g = await geraete_monate(ds.db, ds.aid, von=JUNI, bis=JULI)
            fk = {f.schluessel: f for f in await lade_monats_fakten(ds.db, ds.aid, von=JUNI, bis=JULI,
                                                                     inkl_nur_tageswerte=True)}
    assert g[JUNI].emob.wahl.quelle == QUELLE_BESTAND
    assert g[JUNI].emob.wahl.gruende == {abgeleitet_key(ds.ids["Wallbox"]): "beginnt_nach_von"}
    assert g[JULI].emob.kanal
    assert fk[JUNI].emob.ladung_kwh == pytest.approx(0.0)
    assert fk[JULI].emob.ladung_kwh == pytest.approx(9.0)


async def test_eine_aufteilung_fuer_die_fakten_und_die_sichten_ausserhalb():
    """Abgeschlossener Juni (S1) mit einer Wallbox-Zeile ohne Aufteilung. Die Tagesebene sagt 0 % PV (Tageszeilen
    umgeschrieben), der abgeleitete Kanal 100 %: Fakten UND ``lade_abgeleitete_ladeanteile`` (Hub, Aussichten,
    HA-Export) nehmen den Kanal. Ohne den Leser nennen beide die Quote der Tagesebene — die Probe unterscheidet."""
    from unittest.mock import AsyncMock, patch

    from backend.services.emob_ladeanteil import lade_abgeleitete_ladeanteile
    from backend.services.monats_fakten import lade_monats_fakten

    async with kg.datenstand("achsen", "M02", "HA") as ds:
        form = am.MATRIX_FORMEN["M02"]
        with am.umgebung(form, ds.svc):
            await am.schreibe_s1_aus_ha_laden(ds.db, form, ds.aid)
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.emob_ladung_pv_abgeleitet_kwh.isnot(None),
        ).values(emob_ladung_netz_abgeleitet_kwh=TagesZusammenfassung.emob_ladung_netz_abgeleitet_kwh
                 + TagesZusammenfassung.emob_ladung_pv_abgeleitet_kwh, emob_ladung_pv_abgeleitet_kwh=0.0))
        await ds.db.commit()

        async def _beide():
            with am.umgebung(form, ds.svc):
                q = await lade_abgeleitete_ladeanteile(ds.db, ds.aid, von=JUNI, bis=JUNI)
                f = (await lade_monats_fakten(ds.db, ds.aid, von=JUNI, bis=JUNI))[0]
            return q.get(JUNI), f.emob.ladung_pv_kwh

        mit = await _beide()
        with patch("backend.services.kanal.geraete_leser.geraete_monate", new=AsyncMock(return_value={})):
            ohne = await _beide()
    assert mit == (pytest.approx(1.0), pytest.approx(90.0))
    assert ohne == (pytest.approx(0.0), pytest.approx(0.0))


# ── Pool auf den Kanal-Zeilen (eigene Form) ─────────────────────────────────

FORM_POOL = am.Form(
    "P-POOL", "Wallbox 3 kWh/h, Auto A mit eigener Messung 1 kWh/h, Auto B ohne Zähler", ("netz", "emob"), ("E2",),
    geraete=(
        am.Geraet("Wallbox", "wallbox", {"ladung_kwh": am.stunden(3.0, 11, 14)}),
        am.Geraet("Auto A", "e-auto", {"ladung_kwh": am.stunden(1.0, 11, 14)}),
        am.Geraet("Auto B", "e-auto", {}),
    ),
)


@asynccontextmanager
async def _datenstand_form(form):
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel

    verz = tempfile.mkdtemp(prefix="eedc-kanal-geraete-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def sitzungen():
            async with macher() as s:
                yield s
                await s.commit()

        try:
            svc = am.seed_ha(form)
            aid, ids = await am.seed_anlage(db, form)
            with am.umgebung(form, svc):
                await nachfuellen_spiegel(sitzungen, aid, jetzt=mx.JETZT, ha_svc=svc)
                await mx.baue_abgeleitete(sitzungen, aid)
                await mx.aggregiere_tage(db, form.pvform, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
                yield db, aid, ids, svc
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("mit_bloecken", [True, False], ids=["mit-ladebloecken", "ohne-ladebloecke"])
async def test_pool_auf_den_kanal_zeilen_das_gemessene_auto_traegt_seine_der_rest_geht_an_das_andere(mit_bloecken):
    """Mit Ladeblöcken (Tagesspur, N-555 Stufe 3, bleiben Bestand) sind SIE die Messung des Autos; ohne sie trägt die
    Kanal-Zeile „Heim: gesamt" (Herkunft ``kanal`` ≠ Altwert, Regel 8) — beide Fälle nennen dieselben Zahlen."""
    from contextlib import nullcontext
    from unittest.mock import AsyncMock, patch

    from backend.services.monats_fakten import lade_monats_fakten

    ohne = (nullcontext() if mit_bloecken else
            patch("backend.services.energie_profil.monats_aus_tagen.emob_je_auto_monate", new=AsyncMock(return_value={})))
    async with _datenstand_form(FORM_POOL) as (db, aid, ids, svc):
        with am.umgebung(FORM_POOL, svc), ohne:
            vor = (await lade_monats_fakten(db, aid, von=JUNI, bis=JUNI, inkl_nur_tageswerte=True))[0]
            await am.schreibe_s1_aus_ha_laden(db, FORM_POOL, aid)
            nach = (await lade_monats_fakten(db, aid, von=JUNI, bis=JUNI))[0]
    for f in (vor, nach):
        assert f.emob.ladung_kwh == pytest.approx(270.0)
        assert f.emob.je_auto[ids["Auto A"]].ladung_kwh == pytest.approx(90.0)
        assert f.emob.je_auto[ids["Auto B"]].ladung_kwh == pytest.approx(180.0)
        assert f.emob.ladung_pv_kwh == pytest.approx(270.0)
    assert "emob" in vor.meta.tageswert_gruppen and "emob" not in nach.meta.tageswert_gruppen
