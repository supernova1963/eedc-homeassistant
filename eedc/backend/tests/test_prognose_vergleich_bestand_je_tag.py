"""N-317 — der Prognosen-Vergleich rechnet jeden Tag mit dem Bestand DIESES Tages.

Bis dahin holte ``_lade_anlage_mit_pv`` **eine** kWp-Kopfzahl über
``aktiv_jetzt()`` und multiplizierte damit alle 14 Tage. Der Kanon rechnet seit
N31 tagesgenau (``prognose_kanon._tages_gewichte``) und überschreibt Tag 0–3 —
ab Tag 4 blieb die Kopfzahl stehen. **Eine Antwort, zwei Bestandsbasen.**

Dazu die schärfere Hälfte: ``aktiv_jetzt()`` prüft die Anschaffungs-Untergrenze
**gar nicht** (``utils/investition_filter.py`` — nur ``aktiv`` und
``stilllegungsdatum > heute``). Ein erst in einer Woche angeschafftes Modul
zählte damit ab heute mit, ein in drei Tagen stillgelegtes bis Tag 13 weiter.
Das Formular verspricht das Gegenteil: „Ab diesem Datum zählt die Komponente
nicht mehr für Live/**Prognose**".

Gemessen wird an der Fundstelle — der Tagesschleife des Endpunkts, nicht am
Helfer daneben: ``anlagen_kwp`` hat eigene Tests, und ein Prüfer, der nur ihn
befragt, bliebe grün, während die Schleife weiter eine Kopfzahl einsetzt.

Damit die Schleife überhaupt sichtbar wird, ist der **Kanon abgeschaltet**:
sonst überschriebe er Tag 0–3 mit seinem eigenen (bereits korrekten) Wert, und
der Vergleich „Tag 0 gegen Tag 10" liefe gegen zwei verschiedene Rechenwege.

Schwesterdateien: ``test_prognose_kanon.py`` (derselbe Kanon, Symmetrie über
alle Pfade), ``test_prognose_ertrag_tag.py`` (die Tagesformel selbst),
``test_wurzelmuster_p1_orientierung.py`` (die kWp-Ermittlung je Modul).

⚠ **Diese Datei liest die echte Uhr — genau EINMAL, in der Fixture ``heute``,
und sie steht deshalb mit der Zahl 1 in der Baseline von
``test_konformitaet_echte_uhr_in_tests.py``.** Der Grund ist der Prüfling: der
Endpunkt verankert seinen Horizont selbst an ``date.today()`` (``heute`` und
``horizont`` in ``get_prognosen_vergleich``), und ``pv_invs_im_horizont``
filtert die Obermenge gegen genau dieses Fenster. Ein festes Datum in der
Fixture würde die geladene Menge leeren, statt den Test unabhängig zu machen —
die Probe prüfte dann nichts mehr. Ein gestellter Kalender wäre der andere Weg;
``freezegun`` ist am 23.08.2026 ausdrücklich verworfen worden. Alle drei Proben
bekommen ihr ``heute`` deshalb aus der einen Fixture: **eine** Ablesung statt
vier, damit ein Mitternachtswechsel während des Laufs nicht zwei verschiedene
Tage in derselben Probe erzeugen kann.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.models import Anlage, Investition
from backend.services.prognose_service import berechne_pv_ertrag_tag
from backend.services.pv_orientation import resolve_system_losses


HORIZONT_TAGE = 14
GLOBALSTRAHLUNG = 4.0          # kWh/m², für jeden Tag gleich
TEMPERATUR = 20.0              # unter 25 °C ⇒ keine Temperaturkorrektur
KWP_BESTAND = 6.0
KWP_WECHSEL = 4.0              # das Modul, dessen Datum im Horizont liegt


def _wetter_tage(heute: date) -> dict:
    """14 identische Prognosetage — jeder Unterschied im Ergebnis kommt dann
    aus der kWp und aus nichts sonst."""
    return {
        "tage": [
            {
                "datum": (heute + timedelta(days=i)).isoformat(),
                "globalstrahlung_kwh_m2": GLOBALSTRAHLUNG,
                "sonnenstunden": 8.0,
                "temperatur_max_c": TEMPERATUR,
                "temperatur_min_c": 10.0,
                "niederschlag_mm": 0.0,
                "bewoelkung_prozent": 10,
                "wetter_code": 0,
            }
            for i in range(HORIZONT_TAGE)
        ]
    }


def _erwartet(kwp: float) -> float:
    """Der Tageswert, den der Endpunkt für diese kWp liefern MUSS.

    Direkt über dieselbe Formel statt über eine Verhältnis-Annahme: dass
    ``berechne_pv_ertrag_tag`` linear in kWp ist, ist wahr, aber es ist eine
    zweite Behauptung — hier wird sie nicht gebraucht.
    """
    return berechne_pv_ertrag_tag(
        globalstrahlung_kwh_m2=GLOBALSTRAHLUNG,
        anlagenleistung_kwp=kwp,
        temperatur_max_c=TEMPERATUR,
        system_losses=resolve_system_losses(None),
    )


@pytest.fixture
def heute() -> date:
    """Die einzige Uhr-Ablesung dieser Datei — siehe Modul-Docstring."""
    return date.today()


@pytest.fixture
def _ohne_kanon_und_netz(monkeypatch, heute):
    """Kanon aus, OpenMeteo fest, Solcast aus, kein Lernfaktor.

    Der Kanon MUSS hier aus: er überschreibt Tag 0–3 mit seinem eigenen Wert
    (dem bereits tagesgenauen), und genau diese Tage sind der Gegenanker.
    """
    import backend.api.routes.prognosen as pr

    async def _kein_kanon(*_a, **_kw):
        return None

    async def _kein_solcast(*_a, **_kw):
        return None

    async def _kein_lernfaktor(*_a, **_kw):
        from backend.api.routes.live_wetter import LernfaktorResult

        return LernfaktorResult(faktor=None)

    async def _wetter(**_kw):
        return _wetter_tage(heute)

    monkeypatch.setattr(pr, "kanon_tagesprognose", _kein_kanon)
    monkeypatch.setattr(pr, "get_solcast_forecast", _kein_solcast)
    monkeypatch.setattr(pr, "fetch_open_meteo_forecast", _wetter)
    monkeypatch.setattr(pr, "_get_lernfaktor_detail", _kein_lernfaktor)


async def _seed(db, *, wechsel: dict) -> Anlage:
    """Anlage mit zwei Modulen — eines fest, eines mit ``wechsel``-Daten.

    ``leistung_kwp`` bewusst auf 0: der gepflegte Referenzwert darf hier nicht
    einspringen, sonst misst der Test ihn statt der Investitions-Summe.
    """
    anlage = Anlage(
        anlagenname="N-317", leistung_kwp=0.0,
        latitude=48.8, longitude=9.2, standort_land="DE", prognose_quelle="eedc",
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Bestand",
        leistung_kwp=KWP_BESTAND, neigung_grad=35,
        anschaffungsdatum=date(2024, 1, 1), parameter={"ausrichtung_grad": 0},
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Wechsel",
        leistung_kwp=KWP_WECHSEL, neigung_grad=35,
        parameter={"ausrichtung_grad": 0}, **wechsel,
    ))
    await db.flush()
    return anlage


async def _tageswerte(db, anlage_id: int) -> list[float]:
    from backend.api.routes.prognosen import get_prognosen_vergleich

    antwort = await get_prognosen_vergleich(anlage_id, db=db)
    assert len(antwort.openmeteo_tage) == HORIZONT_TAGE
    return [t.pv_prognose_kwh for t in antwort.openmeteo_tage]


# ── Stilllegung im Horizont ─────────────────────────────────────────────────

async def test_stilllegung_im_horizont_wirkt_ab_ihrem_tag(db, heute, _ohne_kanon_und_netz):
    """Ein am Tag +3 stillgelegtes Modul zählt ab Tag +3 nicht mehr.

    Vor dem Fix trugen ALLE 14 Tage die volle kWp — ``aktiv_jetzt()`` fragt
    ``stilllegungsdatum > heute``, und das ist am Tag 13 immer noch dieselbe
    Antwort wie am Tag 0.
    """
    anlage = await _seed(db, wechsel={
        "anschaffungsdatum": date(2024, 1, 1),
        "stilllegungsdatum": heute + timedelta(days=3),
    })
    werte = await _tageswerte(db, anlage.id)

    # Gegenanker: der Tag VOR der Stilllegung ist unverändert. Ein Rückbau des
    # Fixes lässt diese Zusicherung grün und macht nur die darunter rot —
    # der Prüfer zeigt damit auf die Änderung und nicht auf die Datei.
    assert werte[0] == pytest.approx(_erwartet(KWP_BESTAND + KWP_WECHSEL))
    assert werte[2] == pytest.approx(_erwartet(KWP_BESTAND + KWP_WECHSEL))
    # Der Stilllegungstag selbst zählt noch mit (``ist_aktiv_an``: Grenze
    # inklusiv — dieselbe Kante wie ``aktiv_am_tag``).
    assert werte[3] == pytest.approx(_erwartet(KWP_BESTAND + KWP_WECHSEL))
    # Ab Tag +4 nur noch der Bestand. DAS ist der Fund.
    assert werte[4] == pytest.approx(_erwartet(KWP_BESTAND))
    assert werte[13] == pytest.approx(_erwartet(KWP_BESTAND))


# ── Anschaffung im Horizont ────────────────────────────────────────────────

async def test_anschaffung_im_horizont_zaehlt_erst_ab_ihrem_tag(db, heute, _ohne_kanon_und_netz):
    """Ein erst am Tag +7 angeschafftes Modul zählt vorher NICHT.

    Diese Hälfte hat ``aktiv_jetzt()`` gar nicht gekannt: der Filter prüft die
    Anschaffungs-Untergrenze nicht, das Modul lief also ab heute mit voller
    kWp in die Prognose — die Zahl stand zu hoch, nicht zu niedrig.
    """
    anlage = await _seed(db, wechsel={
        "anschaffungsdatum": heute + timedelta(days=7),
    })
    werte = await _tageswerte(db, anlage.id)

    assert werte[0] == pytest.approx(_erwartet(KWP_BESTAND))
    assert werte[6] == pytest.approx(_erwartet(KWP_BESTAND))
    assert werte[7] == pytest.approx(_erwartet(KWP_BESTAND + KWP_WECHSEL))
    assert werte[13] == pytest.approx(_erwartet(KWP_BESTAND + KWP_WECHSEL))


# ── Die Bestandssperre fragt den Horizont, nicht „heute" ────────────────────

async def test_sperre_haelt_den_horizont_offen(db, heute, _ohne_kanon_und_netz):
    """Eine Anlage, deren einziges Modul in drei Tagen anläuft, HAT eine Prognose.

    Der Wächter gegen die naheliegende Verkürzung: wer die Sperre auf
    ``_kwp_am_tag(heute)`` stellt, liefert dieser Anlage HTTP 400 („Keine
    PV-Leistung konfiguriert") — obwohl elf ihrer vierzehn Tage einen Ertrag
    haben. ``leistung_kwp=0`` schließt aus, dass der Referenzwert die Sperre
    heimlich offen hält.
    """
    anlage = Anlage(
        anlagenname="N-317 Start", leistung_kwp=0.0,
        latitude=48.8, longitude=9.2, standort_land="DE", prognose_quelle="eedc",
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Neu",
        leistung_kwp=KWP_BESTAND, neigung_grad=35,
        anschaffungsdatum=heute + timedelta(days=3),
        parameter={"ausrichtung_grad": 0},
    ))
    await db.flush()

    werte = await _tageswerte(db, anlage.id)
    assert werte[0] == 0.0
    assert werte[2] == 0.0
    assert werte[3] == pytest.approx(_erwartet(KWP_BESTAND))
