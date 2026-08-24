"""Die Tag→Monat-Rollup-Kette — 536 Zeilen bis E6 ohne jede Testberührung (M9).

Vier Module, gemessen am 2026-08-24 per AST (je 0 Importe im Testbaum):

* ``energie_profil/aggregations_quelle.py`` (83 Z.) — *kann der Tages-Lauf für
  diesen Tag überhaupt etwas holen?* Drei Aufrufer, darunter der Knopf, den der
  Daten-Checker dem Anwender anbietet (P-8/#368).
* ``energie_profil/monats_aus_tagen.py`` (221 Z.) — Monats-Summen aus der
  lokalen Tagesebene (N-121).
* ``energie_profil/rollup.py`` (111 Z.) — schreibt fünf Monatsdaten-Felder.
* ``energie_profil/scheduler_jobs.py`` (121 Z.) — steht in
  ``test_scheduler_job_registrierung.py`` (M11).
"""

from datetime import date, datetime, timedelta

import pytest

from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import (
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.energie_profil.aggregations_quelle import (
    AggregationsQuelle,
    ermittle_aggregations_quelle,
)
from backend.services.energie_profil.monats_aus_tagen import (
    _monatsgrenzen,
    lade_monats_summen_aus_tagen,
)
from backend.services.energie_profil.rollup import rollup_month
from backend.tests.factories import anlage, monatsdaten


async def stunde(db, anlage_id, tag: date, stunde_nr: int, **werte):
    row = TagesEnergieProfil(
        anlage_id=anlage_id, datum=tag, stunde=stunde_nr, **werte
    )
    db.add(row)
    await db.flush()
    return row


async def mqtt_snapshot(db, anlage_id, zeitpunkt: datetime):
    """Ein MQTT-Energie-Snapshot — `energy_key`/`value_kwh` sind Pflicht."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    db.add(
        MqttEnergySnapshot(
            anlage_id=anlage_id, timestamp=zeitpunkt,
            energy_key="pv_gesamt", value_kwh=1.0,
        )
    )
    await db.flush()


async def tageszeile(db, anlage_id, tag: date, **werte):
    row = TagesZusammenfassung(anlage_id=anlage_id, datum=tag, **werte)
    db.add(row)
    await db.flush()
    return row


# ─────────────────────────────────────────────────────────────────────────────
# aggregations_quelle — die Vorbedingung, die drei Stellen kennen müssen
# ─────────────────────────────────────────────────────────────────────────────

class TestAggregationsQuelle:

    def test_vorhanden_ist_das_oder_der_beiden_wege(self):
        assert AggregationsQuelle(live_sensoren=True, mqtt_energie=False).vorhanden
        assert AggregationsQuelle(live_sensoren=False, mqtt_energie=True).vorhanden
        assert not AggregationsQuelle(
            live_sensoren=False, mqtt_energie=False
        ).vorhanden

    @pytest.mark.asyncio
    async def test_basis_live_zuordnung_genuegt(self, db):
        a = await anlage(db, sensor_mapping={"basis": {"live": {"pv": "sensor.pv"}}})
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 1))
        assert quelle.live_sensoren is True
        assert quelle.vorhanden is True

    @pytest.mark.asyncio
    async def test_auch_eine_INVESTITIONS_zuordnung_genuegt(self, db):
        """Der Daten-Checker darf keinen Knopf verstecken, der etwas holen kann."""
        a = await anlage(
            db,
            sensor_mapping={"investitionen": {"3": {"live": {"leistung": "sensor.wr"}}}},
        )
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 1))
        assert quelle.live_sensoren is True

    @pytest.mark.asyncio
    async def test_ohne_mapping_und_ohne_mqtt_ist_nichts_da(self, db):
        a = await anlage(db, sensor_mapping={})
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 1))
        assert quelle == AggregationsQuelle(live_sensoren=False, mqtt_energie=False)
        assert quelle.vorhanden is False

    @pytest.mark.asyncio
    async def test_leeres_live_dict_zaehlt_nicht_als_zuordnung(self, db):
        a = await anlage(db, sensor_mapping={"basis": {"live": {}}})
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 1))
        assert quelle.live_sensoren is False

    @pytest.mark.asyncio
    async def test_mqtt_snapshots_tragen_ohne_mapping(self, db):
        a = await anlage(db, sensor_mapping={})
        await mqtt_snapshot(db, a.id, datetime(2026, 6, 1, 12, 0))
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 1))
        assert quelle == AggregationsQuelle(live_sensoren=False, mqtt_energie=True)

    @pytest.mark.asyncio
    async def test_das_fenster_beginnt_einen_tag_VOR_dem_stichtag(self, db):
        """Der Zaehlerpfad braucht den Anfangsstand des Vortags."""
        a = await anlage(db, sensor_mapping={})
        await mqtt_snapshot(db, a.id, datetime(2026, 6, 1) - timedelta(hours=6))
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 2))
        assert quelle.mqtt_energie is False       # zwei Tage vorher: zu alt
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 1))
        assert quelle.mqtt_energie is True        # Vortag: genau im Fenster

    @pytest.mark.asyncio
    async def test_fremde_anlage_zaehlt_nicht(self, db):
        a = await anlage(db, sensor_mapping={})
        fremd = await anlage(db, anlagenname="Fremd", sensor_mapping={})
        await mqtt_snapshot(db, fremd.id, datetime(2026, 6, 1, 12, 0))
        quelle = await ermittle_aggregations_quelle(db, a, date(2026, 6, 1))
        assert quelle.mqtt_energie is False


# ─────────────────────────────────────────────────────────────────────────────
# monats_aus_tagen — die lokale Tagesebene je Monat falten (N-121)
# ─────────────────────────────────────────────────────────────────────────────

class TestMonatsgrenzen:
    """Beide Grenzen inklusive — der `bis`-Monat gehört ganz dazu."""

    def test_offenes_fenster(self):
        assert _monatsgrenzen(None, None) == (None, None)

    def test_von_ist_der_erste_des_monats(self):
        ab, vor = _monatsgrenzen((2026, 3), None)
        assert ab == date(2026, 3, 1) and vor is None

    def test_bis_reicht_bis_zum_ersten_des_FOLGEmonats(self):
        _ab, vor = _monatsgrenzen(None, (2026, 3))
        assert vor == date(2026, 4, 1)

    def test_dezember_rollt_ins_folgejahr(self):
        _ab, vor = _monatsgrenzen(None, (2026, 12))
        assert vor == date(2027, 1, 1)


class TestMonatsSummenAusTagen:

    @pytest.mark.asyncio
    async def test_ohne_tagesspur_kommt_nichts(self, db):
        a = await anlage(db)
        assert await lade_monats_summen_aus_tagen(db, a.id) == {}

    @pytest.mark.asyncio
    async def test_stunden_werden_je_monat_gefaltet(self, db):
        a = await anlage(db)
        for tag, werte in (
            (date(2026, 6, 1), (3.0, 1.0)),
            (date(2026, 6, 2), (4.0, 2.0)),
            (date(2026, 7, 1), (5.0, 3.0)),
        ):
            await stunde(
                db, a.id, tag, 12,
                einspeisung_kw=werte[0], netzbezug_kw=werte[1],
            )
        summen = await lade_monats_summen_aus_tagen(db, a.id)
        assert set(summen) == {(2026, 6), (2026, 7)}
        assert summen[(2026, 6)].einspeisung_kwh == pytest.approx(7.0)
        assert summen[(2026, 6)].netzbezug_kwh == pytest.approx(3.0)
        assert summen[(2026, 6)].tage == 2
        assert summen[(2026, 6)].stunden == 2
        assert summen[(2026, 7)].einspeisung_kwh == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_pv_kwh_ist_module_PLUS_balkonkraftwerk(self, db):
        a = await anlage(db)
        await tageszeile(
            db, a.id, date(2026, 6, 1),
            komponenten_kwh={"pv_1": 20.0, "pv_2": 5.0, "bkw_9": 3.0},
        )
        (summe,) = (await lade_monats_summen_aus_tagen(db, a.id)).values()
        assert summe.pv_module_kwh == pytest.approx(25.0)
        assert summe.bkw_kwh == pytest.approx(3.0)
        assert summe.pv_kwh == pytest.approx(28.0)

    @pytest.mark.asyncio
    async def test_das_fenster_ist_auf_BEIDEN_seiten_inklusive(self, db):
        a = await anlage(db)
        for monat in (5, 6, 7):
            await stunde(db, a.id, date(2026, monat, 15), 10, einspeisung_kw=1.0)
        summen = await lade_monats_summen_aus_tagen(
            db, a.id, von=(2026, 6), bis=(2026, 7)
        )
        assert set(summen) == {(2026, 6), (2026, 7)}

    @pytest.mark.asyncio
    async def test_abgeleiteter_anteil_ist_ein_ANTEIL(self, db):
        a = await anlage(db)
        await tageszeile(
            db, a.id, date(2026, 6, 1),
            emob_ladung_pv_abgeleitet_kwh=30.0,
            emob_ladung_netz_abgeleitet_kwh=10.0,
        )
        (summe,) = (await lade_monats_summen_aus_tagen(db, a.id)).values()
        assert summe.abgeleiteter_pv_anteil == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_ohne_ladung_ist_der_anteil_KEINE_AUSSAGE(self, db):
        """`None`, nicht 0 — sonst wuerde eine Schaetzung 0 % behaupten."""
        a = await anlage(db)
        await tageszeile(db, a.id, date(2026, 6, 1), komponenten_kwh={"pv_1": 10.0})
        (summe,) = (await lade_monats_summen_aus_tagen(db, a.id)).values()
        assert summe.abgeleiteter_pv_anteil is None

    @pytest.mark.asyncio
    async def test_fremde_anlage_faellt_heraus(self, db):
        a = await anlage(db)
        fremd = await anlage(db, anlagenname="Fremd")
        await stunde(db, fremd.id, date(2026, 6, 1), 12, einspeisung_kw=99.0)
        assert await lade_monats_summen_aus_tagen(db, a.id) == {}


# ─────────────────────────────────────────────────────────────────────────────
# rollup — fünf Monatsdaten-Felder, geschrieben über den Provenance-Resolver
# ─────────────────────────────────────────────────────────────────────────────

class TestRollupMonth:

    @pytest.mark.asyncio
    async def test_ohne_tageszeilen_wird_nichts_geschrieben(self, db):
        a = await anlage(db)
        await monatsdaten(db, a.id, 2026, 6)
        assert await rollup_month(a.id, 2026, 6, db) is False

    @pytest.mark.asyncio
    async def test_ohne_monatszeile_wird_nichts_geschrieben(self, db):
        """Der Rollup legt keine Monatszeile an — er fuellt eine vorhandene."""
        a = await anlage(db)
        await tageszeile(db, a.id, date(2026, 6, 1), ueberschuss_kwh=5.0)
        assert await rollup_month(a.id, 2026, 6, db) is False

    @pytest.mark.asyncio
    async def test_summen_mittel_und_maximum(self, db):
        a = await anlage(db)
        md = await monatsdaten(db, a.id, 2026, 6)
        for tag, ueber, defizit, zyklen, pr, peak in (
            (1, 10.0, 2.0, 0.5, 0.80, 3.0),
            (2, 20.0, 3.0, 0.5, 0.90, 7.5),
            (3, 30.0, 4.0, 1.0, 0.70, 5.0),
        ):
            await tageszeile(
                db, a.id, date(2026, 6, tag),
                ueberschuss_kwh=ueber, defizit_kwh=defizit,
                batterie_vollzyklen=zyklen, performance_ratio=pr,
                peak_netzbezug_kw=peak,
            )
        assert await rollup_month(a.id, 2026, 6, db) is True
        await db.flush()
        assert md.ueberschuss_kwh == pytest.approx(60.0)     # Σ
        assert md.defizit_kwh == pytest.approx(9.0)          # Σ
        assert md.batterie_vollzyklen == pytest.approx(2.0)  # Σ
        assert md.performance_ratio == pytest.approx(0.8)    # Ø
        assert md.peak_netzbezug_kw == pytest.approx(7.5)    # max

    @pytest.mark.asyncio
    async def test_nur_tage_DIESES_monats_zaehlen(self, db):
        a = await anlage(db)
        md = await monatsdaten(db, a.id, 2026, 6)
        await tageszeile(db, a.id, date(2026, 5, 31), ueberschuss_kwh=100.0)
        await tageszeile(db, a.id, date(2026, 6, 15), ueberschuss_kwh=7.0)
        await tageszeile(db, a.id, date(2026, 7, 1), ueberschuss_kwh=100.0)
        await rollup_month(a.id, 2026, 6, db)
        await db.flush()
        assert md.ueberschuss_kwh == pytest.approx(7.0)

    @pytest.mark.asyncio
    async def test_dezember_laeuft_nicht_ins_folgejahr(self, db):
        a = await anlage(db)
        md = await monatsdaten(db, a.id, 2026, 12)
        await tageszeile(db, a.id, date(2026, 12, 31), ueberschuss_kwh=4.0)
        await tageszeile(db, a.id, date(2027, 1, 1), ueberschuss_kwh=100.0)
        await rollup_month(a.id, 2026, 12, db)
        await db.flush()
        assert md.ueberschuss_kwh == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_ein_feld_ohne_tageswerte_bleibt_unberuehrt(self, db):
        """`None` wird nicht geschrieben — ein gepflegter Wert bliebe stehen."""
        a = await anlage(db)
        md = await monatsdaten(db, a.id, 2026, 6, defizit_kwh=42.0)
        await tageszeile(db, a.id, date(2026, 6, 1), ueberschuss_kwh=5.0)
        await rollup_month(a.id, 2026, 6, db)
        await db.flush()
        assert md.ueberschuss_kwh == pytest.approx(5.0)
        assert md.defizit_kwh == pytest.approx(42.0)

    @pytest.mark.asyncio
    async def test_manuelle_eingabe_schlaegt_den_auto_rollup(self, db):
        """`auto:monatsabschluss` (Stufe 3) verliert gegen `manual:form` (1)."""
        from backend.services.provenance import write_with_provenance

        a = await anlage(db)
        md = await monatsdaten(db, a.id, 2026, 6)
        await write_with_provenance(
            db, md, "ueberschuss_kwh", 999.0,
            source="manual:form", writer="test",
        )
        await tageszeile(db, a.id, date(2026, 6, 1), ueberschuss_kwh=5.0)
        await rollup_month(a.id, 2026, 6, db)
        await db.flush()
        assert md.ueberschuss_kwh == pytest.approx(999.0)

    @pytest.mark.asyncio
    async def test_fremde_anlage_wird_nicht_mitgefaltet(self, db):
        a = await anlage(db)
        fremd = await anlage(db, anlagenname="Fremd")
        md = await monatsdaten(db, a.id, 2026, 6)
        await tageszeile(db, a.id, date(2026, 6, 1), ueberschuss_kwh=5.0)
        await tageszeile(db, fremd.id, date(2026, 6, 2), ueberschuss_kwh=100.0)
        await rollup_month(a.id, 2026, 6, db)
        await db.flush()
        assert md.ueberschuss_kwh == pytest.approx(5.0)
