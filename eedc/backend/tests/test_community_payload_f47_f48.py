"""Der Gemeinschaftsdatensatz: kein halber Monat, und der Maßstab kommt mit.

Zwei Fehler aus dem #387-Paket (2026-08-19), beide an dieser einen Stelle:

**F-48 — der angebrochene Monat wanderte mit.** ``_monatswert`` schickte jeden
Monat mit Zählerzeile und PV > 0 raus, also auch einen halben. Wer den Abschluss
des laufenden Monats schon anlegt (das Formular lässt es zu) oder ihn
importiert, stellte ein Bruchstück neben lauter ganze Monate. **Live gemessen:**
``/api/statistics/monthly-averages`` wies für 08/2026 **46,3 kWh/kWp bei n = 5**
aus — fünf halbe Monate —, und der Client benutzt genau diese Reihe als
Monats-Vergleichswert. ⚠ „Zu Ende" heißt **Kalendermonat vorbei**, nicht
„Monatsabschluss erledigt": sonst hinge die Vergleichbarkeit an der
Pflegedisziplin des Einzelnen.

**F-47 — der Server rechnete zwei Größen selbst nach.** ``statistics.py`` bildete
CO₂ als ``Eigenverbrauch × 0,38`` (ohne Wärmepumpe und E-Mobilität, rund 22 % zu
wenig) und rekonstruierte den Eigenverbrauch aus ``Erzeugung − Einspeisung``.
Beides gehört in den Datensatz, nicht in eine zweite Rechenstelle — der Server
hat die Rohdaten nie gesehen.

⚠ **Die Uhr wird gestellt, nicht gelesen** (Fund N-167): ein Test, der
``date.today()`` selbst aufruft, ist am Monatsletzten um Mitternacht ein
Zufallsgenerator.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.services.community_service import prepare_community_data


class _FixesHeute(date):
    """``date`` mit gestelltem ``today()`` — alles andere unverändert."""

    @classmethod
    def today(cls):
        return date(2026, 8, 19)


async def _anlage_mit_juli_und_august(db) -> int:
    anlage = Anlage(anlagenname="Halber-August", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add_all([
        Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=7,
                    einspeisung_kwh=400.0, netzbezug_kwh=100.0),
        # Der laufende Monat, halb voll — genau der Fall des Melders.
        Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=8,
                    einspeisung_kwh=180.0, netzbezug_kwh=40.0),
    ])
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    db.add(pv)
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=7,
                               verbrauch_daten={"pv_erzeugung_kwh": 1100.0}),
        InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=8,
                               verbrauch_daten={"pv_erzeugung_kwh": 520.0}),
    ])
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_laufender_kalendermonat_wird_nicht_geteilt(db):
    """F-48: Der August fehlt, der Juli ist da — am 19.08. gemessen."""
    anlage_id = await _anlage_mit_juli_und_august(db)

    with patch("backend.services.community_service.date", _FixesHeute):
        data = await prepare_community_data(db, anlage_id)

    monate = [(m["jahr"], m["monat"]) for m in data["monatswerte"]]
    assert monate == [(2026, 7)], (
        "F-48: Der laufende Kalendermonat gehört nicht in den "
        f"Gemeinschaftsdatensatz — ein halber Monat stünde neben ganzen. War: {monate}"
    )


@pytest.mark.asyncio
async def test_abgeschlossener_monat_bleibt_drin(db):
    """Gegenprobe: einen Monat später ist der August ein ganzer Monat.

    Ohne sie prüfte der Test oben auch dann grün, wenn der Filter *alles*
    verwürfe.
    """
    anlage_id = await _anlage_mit_juli_und_august(db)

    class _September(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 3)

    with patch("backend.services.community_service.date", _September):
        data = await prepare_community_data(db, anlage_id)

    monate = [(m["jahr"], m["monat"]) for m in data["monatswerte"]]
    assert monate == [(2026, 7), (2026, 8)], (
        f"Ein abgeschlossener August muss geteilt werden. War: {monate}"
    )


@pytest.mark.asyncio
async def test_eigenverbrauch_kwh_faehrt_mit(db):
    """F-47: der gemessene Eigenverbrauch, statt ihn serverseitig zu erraten."""
    anlage_id = await _anlage_mit_juli_und_august(db)

    with patch("backend.services.community_service.date", _FixesHeute):
        data = await prepare_community_data(db, anlage_id)

    juli = data["monatswerte"][0]
    assert "eigenverbrauch_kwh" in juli, (
        "F-47: Ohne diese Zahl rekonstruiert der Server sie als "
        "`Erzeugung − Einspeisung` — falsch, sobald ein weiterer Erzeuger "
        "hinter demselben Zähler sitzt oder der Speicher mitspielt."
    )
    assert juli["eigenverbrauch_kwh"] == pytest.approx(700.0, abs=1.0), (
        f"1100 erzeugt − 400 eingespeist = 700 kWh. War: {juli['eigenverbrauch_kwh']}"
    )


@pytest.mark.asyncio
async def test_ohne_aktive_prognose_kein_soll(db):
    """Ohne PVGIS-Prognose trägt der Datensatz keinen Maßstab — und behauptet keinen.

    Der Server fällt dann auf seine eigene Kaskade zurück; ein erfundenes SOLL
    wäre die zweite Konstruktionsstelle, an der F-47 hing.
    """
    anlage_id = await _anlage_mit_juli_und_august(db)

    with patch("backend.services.community_service.date", _FixesHeute):
        data = await prepare_community_data(db, anlage_id)

    assert data["soll_jahr_kwh"] is None
    assert "soll_ertrag_kwh" not in data["monatswerte"][0]
