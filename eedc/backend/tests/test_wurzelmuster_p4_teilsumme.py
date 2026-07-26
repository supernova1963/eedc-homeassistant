"""P4-Ehrlichkeit: eine Antwort, die weniger enthält als sie soll, sagt es selbst.

Wurzelmuster **P4** (`docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md` §5): „ein
Wert-Pfad darf nie eine Null oder eine Teilsumme als gültiges Ergebnis
ausliefern, ohne dass die Antwort selbst es sagt — die Unvollständigkeit gehört
in die Response, nicht ins Log."

Zwei Fundstellen, dieselbe Form, verschiedene Kanäle:

* **N77** — `get_multi_string_prognose` markiert einen unvollständigen
  Fan-out seit #306 als `vollstaendig: False` und **loggt** es; die
  HTTP-Antwort von `/api/solar-prognose/{id}` setzte `hinweise=hinweise` und
  füllte `hinweise` nie. Bei 4 Teilanlagen und einem OpenMeteo-Aussetzer fehlte
  grob ein Viertel von `summe_kwh` und allen Tagesbalken — kommentarlos. Bei der
  lokalen Repro der Diagnose-Session lieferte eine 20,8-kWp-Anlage 3,0 kWp,
  weil drei von vier Calls in HTTP 429 liefen.
* **N78/N79** — `/energieprofil/{id}/tagesprognose` lieferte `[0.0] * 24` als
  gültiges PV-Stundenprofil, wenn jeder Prognose-Pfad ausfiel (also „0 kWh"
  statt „keine Prognose", und die Speicher-Simulation rechnete damit weiter);
  und bei Solcast das Stundenprofil von HEUTE als Näherung für morgen, ohne
  dass die Antwort es sagte.

**Kein Ersatz von Daten durch Schätzungen, keine Kappung.** Die Werte bleiben
exakt wie sie sind — sie werden nur beschriftet. Geprüft wird deshalb beides:
dass der Hinweis kommt UND dass der Wert unverändert bleibt.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.services import solar_forecast_service as sfs
from backend.services.solar_forecast_service import (
    PVStringConfig,
    SolarPrognoseResponse,
    SolarPrognoseTag,
)

HEUTE = date.today()
MORGEN = HEUTE + timedelta(days=1)


def _fake_response(kwp: float, tages_kwh: float, tage: int = 2) -> SolarPrognoseResponse:
    tageswerte = [
        SolarPrognoseTag(
            datum=(HEUTE + timedelta(days=i)).isoformat(),
            pv_ertrag_kwh=tages_kwh, gti_kwh_m2=5.0, ghi_kwh_m2=4.0,
            sonnenstunden=8.0, temperatur_max_c=20.0, temperatur_min_c=10.0,
            bewoelkung_prozent=20, niederschlag_mm=0.0, schnee_cm=0.0,
            stunden_kw=[0.0] * 10 + [tages_kwh / 4] * 4 + [0.0] * 10,
        )
        for i in range(tage)
    ]
    return SolarPrognoseResponse(
        anlage_id=None, kwp_gesamt=kwp, neigung=30, ausrichtung=0,
        system_losses_prozent=14.0, prognose_zeitraum={},
        summe_kwh=tages_kwh * tage, durchschnitt_kwh_tag=tages_kwh,
        tageswerte=tageswerte, string_prognosen=None,
        datenquelle="best_match", abgerufen_am="2026-07-26T00:00:00",
    )


async def _anlage_mit_zwei_ausrichtungen(db) -> int:
    """Anlage mit Süd- und Ostdach — erzwingt den Multi-String-Fan-out."""
    from backend.models import Anlage, Investition

    anlage = Anlage(
        anlagenname="P4-Teilsumme", leistung_kwp=20.8,
        latitude=48.0, longitude=11.0,
    )
    db.add(anlage)
    await db.flush()
    for name, kwp, azimut in (("Süddach", 16.0, 0), ("Ostdach", 4.8, -90)):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=name,
            anschaffungsdatum=date(2024, 1, 1), leistung_kwp=kwp,
            neigung_grad=30.0, parameter={"ausrichtung_grad": azimut},
        ))
    await db.commit()
    return anlage.id


# ============================================================================
# N77 — unvollständiger Multi-String-Fan-out
# ============================================================================


async def test_unvollstaendiger_fanout_steht_in_der_response(db, monkeypatch):
    """`vollstaendig=False` ⇒ nichtleeres `hinweise`. Das ist die Regel."""
    from backend.api.routes import solar_prognose as sp_route

    anlage_id = await _anlage_mit_zwei_ausrichtungen(db)

    async def fake_gsp(**kw):
        # Das kleine Ostdach fällt aus (transienter 429) — genau der #306-Fall.
        if kw["kwp"] < 10.0:
            return None
        return _fake_response(kw["kwp"], kw["kwp"] * 4.0)

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_gsp)
    resp = await sp_route.get_solar_prognose_endpoint(
        anlage_id=anlage_id, tage=2, pro_string=False, db=db,
    )

    assert resp.hinweise, (
        "Die Antwort liefert eine Teilsumme und schweigt darüber — genau der "
        "P4-Befund N77."
    )
    text = " ".join(resp.hinweise)
    assert "1 von 2" in text, f"Der Hinweis nennt den Umfang nicht: {resp.hinweise}"
    assert "Teilsumme" in text


async def test_der_wert_wird_nicht_ersetzt_nur_beschriftet(db, monkeypatch):
    """Kein Hochrechnen, kein Kappen: die Zahl bleibt die Teilsumme.

    Der Gegentest zur Kennzeichnung — P4 verlangt Ehrlichkeit, nicht Reparatur.
    Eine hochgerechnete Zahl wäre eine zweite falsche Aussage.
    """
    from backend.api.routes import solar_prognose as sp_route

    anlage_id = await _anlage_mit_zwei_ausrichtungen(db)

    async def fake_gsp(**kw):
        if kw["kwp"] < 10.0:
            return None
        return _fake_response(kw["kwp"], kw["kwp"] * 4.0)

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_gsp)
    resp = await sp_route.get_solar_prognose_endpoint(
        anlage_id=anlage_id, tage=2, pro_string=False, db=db,
    )

    # Nur das Süddach hat geliefert: 16 kWp × 4 kWh/kWp × 2 Tage = 128 kWh.
    assert resp.summe_kwh == pytest.approx(128.0, abs=0.5)


async def test_vollstaendiger_fanout_hat_keine_hinweise(db, monkeypatch):
    """Gegenprobe: der Normalfall bleibt still — sonst ist der Hinweis Rauschen."""
    from backend.api.routes import solar_prognose as sp_route

    anlage_id = await _anlage_mit_zwei_ausrichtungen(db)

    async def fake_gsp(**kw):
        return _fake_response(kw["kwp"], kw["kwp"] * 4.0)

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_gsp)
    resp = await sp_route.get_solar_prognose_endpoint(
        anlage_id=anlage_id, tage=2, pro_string=False, db=db,
    )

    assert resp.hinweise == []
    assert resp.summe_kwh == pytest.approx(20.8 * 4.0 * 2, abs=0.5)


# ============================================================================
# N78/N79 — Tagesprognose ohne Profil bzw. mit dem Profil von heute
# ============================================================================


async def _anlage_mit_verbrauchshistorie(db) -> int:
    """Anlage mit genug Stundenprofil-Historie für die Verbrauchsprognose."""
    from backend.models import Anlage, Investition
    from backend.models.tages_energie_profil import TagesEnergieProfil

    anlage = Anlage(
        anlagenname="P4-Tagesprognose", leistung_kwp=10.0,
        latitude=48.0, longitude=11.0,
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
        neigung_grad=30.0,
    ))
    for tag_offset in range(1, 15):
        tag = HEUTE - timedelta(days=tag_offset)
        for stunde in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=tag, stunde=stunde,
                verbrauch_kw=0.5, pv_kw=0.0,
            ))
    await db.commit()
    return anlage.id


async def test_ohne_pv_prognose_sagt_die_antwort_dass_die_nullen_keine_prognose_sind(
    db, monkeypatch,
):
    """N78: `[0.0] * 24` durfte nicht als „0 kWh PV" durchgehen."""
    from backend.api.routes.energie_profil import views

    anlage_id = await _anlage_mit_verbrauchshistorie(db)

    # Kanon UND Einzel-Abruf fallen aus — der Zustand, in dem die Vorbelegung
    # als Ergebnis herauskam.
    async def kein_kanon(*a, **kw):
        return None

    async def kein_abruf(**kw):
        return None

    monkeypatch.setattr(views, "_pv_stunden_aus_kanon", kein_kanon)
    monkeypatch.setattr(sfs, "get_solar_prognose", kein_abruf)

    resp = await views.get_tagesprognose(anlage_id=anlage_id, datum=MORGEN, db=db)

    assert resp.pv_summe_kwh == pytest.approx(0.0), (
        "Der Wert soll unverändert 0 bleiben — beschriftet, nicht geschätzt."
    )
    assert resp.hinweise, "24 Nullen ohne Kennzeichnung — genau der Befund N78."
    text = " ".join(resp.hinweise)
    assert "keine PV-Prognose" in text
    assert "Speicher" in text, (
        "Der Hinweis muss die Speicher-Vorschau mit einschließen — sie rechnet "
        "mit denselben Nullen weiter."
    )


async def test_mit_pv_prognose_bleibt_die_antwort_still(db, monkeypatch):
    """Gegenprobe: liegt ein Profil vor, gibt es keinen Hinweis."""
    from backend.api.routes.energie_profil import views

    anlage_id = await _anlage_mit_verbrauchshistorie(db)

    async def kanon_liefert(*a, **kw):
        return [0.0] * 8 + [1.5] * 8 + [0.0] * 8

    monkeypatch.setattr(views, "_pv_stunden_aus_kanon", kanon_liefert)

    resp = await views.get_tagesprognose(anlage_id=anlage_id, datum=MORGEN, db=db)

    assert resp.pv_summe_kwh == pytest.approx(12.0, abs=0.1)
    assert resp.hinweise == []


async def test_solcast_profil_von_heute_wird_als_naeherung_ausgewiesen(db, monkeypatch):
    """N79: „morgen" zeigte das Stundenprofil von HEUTE, ohne es zu sagen.

    Der Code-Kommentar dokumentierte es, die Antwort nicht — `pv_quelle` meldete
    `solcast` wie bei einem echten Morgen-Profil.
    """
    from types import SimpleNamespace

    from backend.api.routes.energie_profil import views
    from backend.services import solcast_service

    anlage_id = await _anlage_mit_verbrauchshistorie(db)

    # Anlage auf Solcast als Prognosequelle stellen.
    from sqlalchemy import select

    from backend.models import Anlage

    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )).scalar_one()
    anlage.prognose_quelle = "solcast"
    # Standalone (Testumgebung ohne HA) verlangt einen API-Token, sonst fällt
    # `resolve_prognose_quelle` still auf eedc zurück — dann prüfte der Test den
    # falschen Zweig.
    anlage.sensor_mapping = {"solcast_config": {"api_key": "test-token"}}
    await db.commit()

    async def fake_solcast(_anlage):
        return SimpleNamespace(hourly_kw=[0.0] * 8 + [2.0] * 8 + [0.0] * 8)

    monkeypatch.setattr(solcast_service, "get_solcast_forecast", fake_solcast)

    morgen = await views.get_tagesprognose(anlage_id=anlage_id, datum=MORGEN, db=db)
    assert morgen.pv_quelle == "solcast"
    assert morgen.pv_summe_kwh == pytest.approx(16.0, abs=0.1), (
        "Der Wert bleibt der von Solcast — nur die Beschriftung kommt hinzu."
    )
    assert morgen.hinweise, "Profil von heute als Näherung für morgen, ungekennzeichnet."
    assert "heute" in " ".join(morgen.hinweise).lower()

    # Für HEUTE ist dasselbe Profil das richtige — dort kein Hinweis.
    heute = await views.get_tagesprognose(anlage_id=anlage_id, datum=HEUTE, db=db)
    assert heute.pv_quelle == "solcast"
    assert heute.hinweise == []
