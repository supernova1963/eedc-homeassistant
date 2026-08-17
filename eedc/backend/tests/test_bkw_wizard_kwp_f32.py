"""F-32: die Prognose eines Balkonkraftwerks aus dem Einrichtungsassistenten.

**Der Fehler.** Die Nennleistung eines `balkonkraftwerk` steht je nach Herkunft
in der **Spalte** ``leistung_kwp`` oder im ``parameter``-JSON (Anzahl × Wp) —
deshalb existiert der Typ-Dispatcher ``get_erzeuger_kwp`` (ADR-002/P3-a). Drei
Stellen des Prognose-Pfads lasen ``get_pv_kwp``, und der kennt die BKW-Form
nicht:

* ``api/routes/solar_prognose.py`` — kWp 0 ⇒ der String fällt heraus ⇒
  ``strings == []`` ⇒ **HTTP 400**. *Cockpit → Live* (zwei Aufrufe) und
  *Cockpit → Aussicht* zeigen keine Prognose.
* ``services/prefetch_service.py`` — ``{"status": "keine_strings"}``, der
  Prefetch bricht ab, ``_speichere_prognose`` läuft nie. Genauigkeits-Tracking
  und Lernfaktor bekommen nur an Tagen einen Datenpunkt, an denen jemand
  *Cockpit → Live* öffnet.
* ``api/routes/pvgis.py`` — die gespeicherte Prognose weist die BKW-Zeile mit
  „0,0 kWp" aus.

**Wen es traf: genau den Erstnutzer mit Balkonkraftwerk.** Das
*Investitionsformular* berechnet die Spalte aus Anzahl × Wp und schreibt sie —
dort greift der Fehler nicht. Der *Einrichtungsassistent* schrieb ausschließlich
ins ``parameter``. Melder-Weg: Daniel, Forum T89667 #170 ff.

**Warum 3011 Bestandstests daran vorbeiliefen — und die Auflage dieser Datei.**
Jede vorhandene BKW-Fixture (und der Demo-Bestand) setzt ``leistung_kwp`` in der
**Spalte**; damit ist der Fehler nicht reproduzierbar. Die Seeds hier lassen die
Spalte deshalb bewusst **NULL** — ``_wizard_bkw`` ist die Fixture-Form „so, wie
der Assistent es anlegt". Wer sie mit einer gefüllten Spalte kopiert, hat den
Wächter entwertet, nicht erweitert.

⚠ **Nur die kWp war betroffen, und das ist gemessen:** ``get_pv_neigung`` und
``get_pv_azimut`` lesen das ``parameter``-JSON von sich aus (Priorität
Spalte/``ausrichtung_grad`` → ``parameter``), Ausrichtung und Neigung des
Wizard-BKW kommen also an. Der Test hält das als Zusicherung fest, damit die
Abgrenzung nicht als Behauptung stehenbleibt.

**Der Selektor gehört dazu (N-266).** ``solar_prognose.py`` bildet die
PV-Erzeuger-Menge über **zwei getrennte Queries** statt über ein Typ-Literal —
deshalb hat der P11-Wächter sie nicht gesehen, und ``erzeuger_traeger`` fehlte
dort. Ohne ihn brächte ein BKW mit Modul-Kindern eine dritte String-Zeile mit
seiner alten Einzel-Ausrichtung mit, und mit dem Dispatcher trüge diese Zeile
die **Summe der Kinder** — dieselbe kWp zweimal. Der Fix der einen Hälfte macht
die andere scharf; beide stehen hier unter Proben.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from backend.core.investition_kennwerte import get_erzeuger_kwp, get_pv_kwp
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services import solar_forecast_service as sfs
from backend.services.pv_orientation import get_pv_azimut, get_pv_neigung
from backend.services.solar_forecast_service import (
    SolarPrognoseResponse,
    SolarPrognoseTag,
)

HEUTE = date.today()


# ─── Fixture-Formen ──────────────────────────────────────────────────────────

def _wizard_bkw(anlage_id: int, **kw) -> Investition:
    """Ein BKW, **wie der Einrichtungsassistent es anlegt: Spalte NULL.**

    2 × 400 Wp = 0,8 kWp, ausschließlich im ``parameter``. Genau diese Form
    reproduziert F-32; eine Fixture mit gefüllter Spalte tut es nicht.
    """
    return Investition(
        anlage_id=anlage_id, typ="balkonkraftwerk",
        bezeichnung=kw.pop("bezeichnung", "Balkonkraftwerk"),
        anschaffungsdatum=date(2025, 3, 1),
        # leistung_kwp: BEWUSST nicht gesetzt (der Assistent setzt sie nicht).
        parameter={
            "leistung_wp": 400, "anzahl": 2,
            "ausrichtung": "Süd", "neigung_grad": 30,
        },
        **kw,
    )


def _formular_bkw(anlage_id: int) -> Investition:
    """Dasselbe Gerät, wie das Investitionsformular es anlegt: Spalte gefüllt."""
    return Investition(
        anlage_id=anlage_id, typ="balkonkraftwerk", bezeichnung="Balkonkraftwerk",
        anschaffungsdatum=date(2025, 3, 1),
        leistung_kwp=0.8, ausrichtung="Süd", neigung_grad=30,
        parameter={
            "leistung_wp": 400, "anzahl": 2,
            "ausrichtung": "Süd", "neigung_grad": 30,
        },
    )


async def _anlage(db, *, bkw_form=_wizard_bkw, module: tuple = ()) -> Anlage:
    """Reine BKW-Anlage (Daniels Fall), optional mit Modul-Kindern am BKW."""
    anlage = Anlage(
        anlagenname="Nur Balkonkraftwerk", leistung_kwp=0.8,
        latitude=48.8, longitude=9.2, standort_land="DE",
        installationsdatum=date(2025, 3, 1),
    )
    db.add(anlage)
    await db.flush()
    bkw = bkw_form(anlage.id)
    db.add(bkw)
    await db.flush()
    for kwp, ausrichtung in module:
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module",
            bezeichnung=f"Modul {ausrichtung}",
            leistung_kwp=kwp, ausrichtung=ausrichtung, neigung_grad=30,
            anschaffungsdatum=date(2025, 3, 1),
            parent_investition_id=bkw.id,
        ))
    await db.flush()
    return anlage


def _fake_response(kwp: float, tage: int = 2) -> SolarPrognoseResponse:
    tages_kwh = kwp * 4.0
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
        datenquelle="test", abgerufen_am=HEUTE.isoformat(),
    )


@pytest.fixture
def _abrufe(monkeypatch):
    """Patcht OpenMeteo; sammelt jeden Abruf als ``(kwp, ausrichtung)``.

    ⚠ **Gepatcht werden DREI Bindungen, und das ist gemessen.** `solar_prognose.py`
    und `prefetch_service.py` importieren `get_solar_prognose` **am Modulkopf**,
    haben also je eine eigene Referenz; der Service-Namensraum wird nur vom
    internen Fan-out (`get_multi_string_prognose`) benutzt. Ein Patch allein auf
    `sfs` traf deshalb genau die Pfade mit **mehreren** Orientierungsgruppen —
    die Einzel-Gruppen-Proben (reines BKW) liefen in einen echten Abruf und im
    Volllauf auf HTTP 503, während der Kinder-Test grün blieb. Das Fehlerbild
    („drei rot, einer grün") war der Hinweis auf die Bindung, nicht auf die Zeit.

    ⚠ **Der Korrekturprofil-Cache MUSS mit geräumt werden, und das ist gemessen.**
    Ohne `_cache.clear()` und ohne den neutralisierten Lernfaktor waren drei
    Proben dieser Datei isoliert grün und im **Volllauf** rot (3,0 statt 6,4 kWh
    bzw. HTTP 503): `services/korrekturprofil_lookup._cache` ist ein
    Modul-Singleton, den fremde Tests füllen, und der gelernte Faktor eines
    anderen Tests rechnete hier mit. Dieselbe Konstruktion wie der
    SWR-Modul-Cache aus N-270 — nur backend-seitig. Alle vier bestehenden
    Prognose-Fixtures tun beides; diese hatte es zunächst vergessen.

    ⚠ Gezählt wird die **Menge** der Paare, nicht ihre Anzahl: die Route ruft je
    Orientierungsgruppe zweimal ab (Fan-out ``get_multi_string_prognose`` und
    danach der Kanon-Pfad ``kanon_tagesprognose``). Das ist so gewollt; eine
    Zusicherung auf die Aufruf-Zahl würde einen zweiten Sachverhalt pinnen.
    """
    import backend.api.routes.live_wetter as lw
    import backend.api.routes.solar_prognose as sp_route
    import backend.services.prefetch_service as ps_mod
    from backend.services.korrekturprofil_lookup import _cache

    calls: list[tuple[float, int]] = []

    async def fake_gsp(*args, **kw):
        # Der Fan-out ruft mit Schlüsselwörtern, der Prefetch positional
        # (lat, lon, kwp, neigung, ausrichtung) — beide Formen zählen.
        kwp = kw["kwp"] if "kwp" in kw else args[2]
        ausrichtung = kw["ausrichtung"] if "ausrichtung" in kw else args[4]
        calls.append((kwp, ausrichtung))
        return _fake_response(kwp, kw.get("days") or 2)

    async def kein_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return None

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_gsp)
    monkeypatch.setattr(sp_route, "get_solar_prognose", fake_gsp)
    monkeypatch.setattr(ps_mod, "get_solar_prognose", fake_gsp)
    monkeypatch.setattr(lw, "_get_lernfaktor", kein_lernfaktor)
    _cache.clear()
    return calls


def _gruppen(abrufe) -> set:
    """Die abgerufenen ``(kWp, Azimut)``-Paare, auf 3 Stellen gerundet."""
    return {(round(kwp, 3), azimut) for kwp, azimut in abrufe}


# ─── Der Seed selbst ist eine Behauptung: erst sie belegen ───────────────────

def test_der_seed_traegt_die_spalte_wirklich_nicht():
    """Ankerprüfung — ohne sie beweist keine der Proben unten etwas.

    ``get_pv_kwp`` = 0,0 **und** ``get_erzeuger_kwp`` = 0,8: genau die Differenz
    aus der Messung zu F-32. Wird die Fixture je „reparabel" gemacht (Spalte
    gefüllt), fällt dieser Test — und nicht stillschweigend die ganze Datei
    grün durch.
    """
    bkw = _wizard_bkw(anlage_id=1)
    assert bkw.leistung_kwp is None, "Die Fixture muss die Spalte NULL lassen."
    assert get_pv_kwp(bkw) == 0.0, (
        "Ohne Spalte liefert der engere Helper 0 — das IST der Fehler, gegen "
        "den diese Datei geschrieben ist."
    )
    assert get_erzeuger_kwp(bkw) == pytest.approx(0.8), (
        "Der Typ-Dispatcher muss die BKW-Form (Anzahl × Wp) kennen."
    )


def test_nur_die_kwp_war_betroffen_ausrichtung_und_neigung_kommen_an():
    """Die Abgrenzung als Zusicherung, nicht als Behauptung im Fließtext."""
    bkw = _wizard_bkw(anlage_id=1)
    assert get_pv_azimut(bkw) == 0, "Süd aus dem `parameter` ergibt Azimut 0."
    assert get_pv_neigung(bkw) == 30, "Neigung steht im `parameter` und wird gelesen."


# ─── Pfad 1: /api/solar-prognose (Cockpit → Live · Cockpit → Aussicht) ───────

async def test_reine_bkw_anlage_bekommt_eine_prognose(db, _abrufe):
    """Der sichtbare Befund: vorher HTTP 400, jetzt eine Prognose."""
    from backend.api.routes import solar_prognose as sp_route

    anlage = await _anlage(db)
    resp = await sp_route.get_solar_prognose_endpoint(
        anlage_id=anlage.id, tage=2, pro_string=False, db=db,
    )

    assert resp.summe_kwh > 0, (
        "Eine reine BKW-Anlage aus dem Assistenten lieferte HTTP 400 "
        "(keine PV-Module mit gueltiger Leistung gefunden) — F-32."
    )
    assert _gruppen(_abrufe) == {(0.8, 0)}, (
        f"Erwartet wird die echte kWp des BKW, gemessen: {_abrufe}"
    )


async def test_bestandsschutz_gefuellte_spalte_rechnet_bitgleich(db, _abrufe):
    """Gegenprobe: die Formular-Form (und der Demo-Bestand) ändert sich nicht.

    ⚠ Verglichen werden die **beiden Formen gegeneinander**, nicht gegen eine
    ausgerechnete Zahl. Ein absoluter Erwartungswert war hier zuerst drin und
    ging im Nachbarschafts-Lauf rot: die Route legt den Kanon-Pfad über die
    Tageswerte, und dessen Eingang hängt an Zuständen, die andere Tests
    hinterlassen. „Rechnet bitgleich" ist ohnehin die Aussage, die der
    Bestandsschutz braucht — die absolute Zahl gehört den Kanon-Tests.
    """
    from backend.api.routes import solar_prognose as sp_route

    wizard = await _anlage(db)
    formular = await _anlage(db, bkw_form=_formular_bkw)

    resp_wizard = await sp_route.get_solar_prognose_endpoint(
        anlage_id=wizard.id, tage=2, pro_string=False, db=db,
    )
    resp_formular = await sp_route.get_solar_prognose_endpoint(
        anlage_id=formular.id, tage=2, pro_string=False, db=db,
    )

    assert _gruppen(_abrufe) == {(0.8, 0)}, (
        f"Beide Formen müssen 0,8 kWp abrufen, gemessen: {_abrufe}"
    )
    assert resp_formular.summe_kwh > 0
    assert resp_wizard.summe_kwh == pytest.approx(resp_formular.summe_kwh), (
        "Dasselbe Gerät, zwei Pflege-Wege — die Prognose muss identisch sein."
    )
    assert resp_wizard.kwp_gesamt == pytest.approx(resp_formular.kwp_gesamt)


# ─── Pfad 2: der Prefetch (Genauigkeits-Tracking + Lernfaktor) ───────────────

async def test_prefetch_laeuft_durch_statt_keine_strings(db, _abrufe, monkeypatch):
    """`keine_strings` hieß: der Prefetch speichert an diesem Tag nichts.

    Belegt wird nicht nur der Status, sondern die **Folge**: dass
    ``_speichere_prognose`` überhaupt einen Tageswert bekommt. Genau daran hing
    der Lernfaktor.
    """
    from backend.api.routes import live_wetter as lw
    from backend.services import prefetch_service as ps

    gespeichert: list = []

    async def fake_speichere(anlage_id, tag, om_kwh, **kw):
        gespeichert.append((anlage_id, tag, om_kwh))

    async def kein_wetterabruf(*args, **kw):
        return None

    monkeypatch.setattr(lw, "_speichere_prognose", fake_speichere)
    monkeypatch.setattr(ps, "fetch_open_meteo_forecast", kein_wetterabruf)
    monkeypatch.setattr(ps, "_prefetch_live_wetter", kein_wetterabruf)

    anlage = await _anlage(db)
    ergebnis = await ps._prefetch_for_anlage(anlage, db)

    assert ergebnis.get("status") == "ok", (
        "Der Prefetch brach bei einer reinen BKW-Anlage mit `keine_strings` ab "
        f"(F-32), gemessen: {ergebnis}"
    )
    assert _abrufe, "Ohne Abruf wäre nichts prognostiziert worden."
    assert gespeichert and gespeichert[0][2] and gespeichert[0][2] > 0, (
        "`_speichere_prognose` lief nie — damit bekamen Genauigkeits-Tracking "
        "und Lernfaktor nur an Tagen einen Datenpunkt, an denen jemand "
        "*Cockpit → Live* öffnete (F-32)."
    )


# ─── Pfad 3: die gespeicherte PVGIS-Prognose weist die kWp aus ──────────────

async def test_gespeicherte_prognose_weist_die_bkw_kwp_aus(db):
    """`module_info` zeigte „0,0 kWp" für das Wizard-BKW."""
    from backend.api.routes.pvgis import get_aktive_prognose
    from backend.models.pvgis_prognose import PVGISPrognose

    anlage = await _anlage(db)
    bkw = (await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            Investition.typ == "balkonkraftwerk",
        )
    )).scalar_one()

    prognose = PVGISPrognose(
        anlage_id=anlage.id, ist_aktiv=True,
        latitude=48.8, longitude=9.2, neigung_grad=30.0, ausrichtung_grad=0.0,
        jahresertrag_kwh=800.0, spezifischer_ertrag_kwh_kwp=1000.0,
        monatswerte=[{"monat": m, "e_m": 66.0} for m in range(1, 13)],
        module_monatswerte={str(bkw.id): [{"monat": m, "e_m": 66.0} for m in range(1, 13)]},
    )
    db.add(prognose)
    await db.flush()

    resp = await get_aktive_prognose(anlage_id=anlage.id, db=db)
    assert resp is not None
    zeile = next(m for m in resp["module"] if m["investition_id"] == bkw.id)
    assert zeile["leistung_kwp"] == pytest.approx(0.8), (
        "Die BKW-Zeile der gespeicherten Prognose stand auf 0,0 kWp, obwohl "
        "die Leistung gepflegt ist (F-32, Anzeige-Hälfte)."
    )


# ─── Der Selektor: der Dispatcher darf nicht doppelt zählen (N-266) ─────────

async def test_bkw_mit_modul_kindern_zaehlt_seine_kwp_einmal(db, _abrufe):
    """Zwei Module über Eck am BKW ⇒ zwei Abrufe, nicht drei.

    Ohne ``erzeuger_traeger`` in ``solar_prognose.py`` käme das BKW als dritter
    String mit seiner EINEN Ausrichtung dazu — und seit dem Dispatcher mit der
    **Summe der Kinder** als kWp. Also 0,8 kWp doppelt, plus die Ausrichtung,
    die der Melder gerade loswerden wollte.
    """
    from backend.api.routes import solar_prognose as sp_route

    anlage = await _anlage(db, module=((0.4, "Ost"), (0.4, "West")))
    await sp_route.get_solar_prognose_endpoint(
        anlage_id=anlage.id, tage=2, pro_string=False, db=db,
    )

    assert _gruppen(_abrufe) == {(0.4, -90), (0.4, 90)}, (
        f"Erwartet Ost und West, gemessen: {_abrufe} — eine dritte Gruppe "
        "(0,8 kWp / Süd) ist das abtretende Balkonkraftwerk."
    )
    assert sum(kwp for kwp, _ in _gruppen(_abrufe)) == pytest.approx(0.8), (
        "Die Anlagen-kWp muss 0,8 bleiben: die Module SIND das "
        "Balkonkraftwerk, sie kommen nicht dazu."
    )
