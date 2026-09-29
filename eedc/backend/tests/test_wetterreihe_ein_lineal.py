"""B1/B3 — die Monats-Wetterreihe steht auf EINEM Lineal, und sie sagt auf welchem.

**Der Befund, gemessen am 29.09.2026** (Paket „Die Wetterreihe geradeziehen",
#395 Punkt 1). Es gab zwei Schreibwege mit zwei Anbietern:

* ``api/routes/wetter.py`` (der Knopf im Monatsformular) rief
  ``get_wetterdaten_multi`` mit der an der Anlage **gewählten** Quelle —
  für DE also Bright Sky (DWD);
* ``import_export/csv_operations.py`` rief ``get_wetterdaten`` — eine zweite
  Kaskade **ohne Bright-Sky-Zweig**, also immer Open-Meteo.

Die beiden messen Sonnenstunden nicht gleich. An derselben Anlage, demselben
Monat, über die Vergleichsroute erhoben:

===========  ==========  ================  =============
Monat        Open-Meteo  Bright Sky (DWD)  Faktor Sonne
===========  ==========  ================  =============
2025-06      380 h       231,8 h           1,64
2025-07      341 h       172,3 h           1,98
2026-07      415 h       233,3 h           1,78
===========  ==========  ================  =============

Die Globalstrahlung liegt 12–16 % auseinander, die Sonnenstunden **64–98 %**.
Eine Reihe aus beiden Quellen beantwortet die Frage, für die sie da ist, falsch:
an einer echten Anlage wurde aus −1 % (auf einem Lineal nachgerechnet) ein
−37 %.

**Zwei Klauseln, zwei Mechanismen.**

1. *Der Import folgt der Anlagen-Wahl* — er ruft dieselbe Auflösung wie das
   Formular (``services/wetter/monatswerte.py``).
2. *Jeder Wert nennt seinen Anbieter* — geschrieben wird das Label des
   **tatsächlich liefernden**, nicht des gewünschten. ``auto`` ist über die
   Zeit nicht stabil (Land, Koordinaten-Box, ``brightsky_enabled``), und ein
   Monat, für den Bright Sky nichts hat, kommt über die Kette von Open-Meteo.
   Ohne die echte Quelle kann niemand sehen, dass eine Reihe gemischt ist.

Schwesterdateien: ``test_wetter_provider_land_386.py`` (welcher Anbieter
überhaupt gefragt werden darf) · ``test_wetter_monatstemperatur_n426.py``
(woher die Ø-Temperatur kommt) · ``test_pvgis_tmy_monatswerte.py`` (die
Rückfallebene darunter).
"""

from __future__ import annotations

import csv
from io import StringIO

import pytest
from sqlalchemy import select

from backend.api.routes.import_export.csv_operations import import_csv
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten

#: Ein vergangener Monat — nur für ihn läuft die Anbieter-Schleife überhaupt.
JAHR, MONAT = 2025, 7

#: Bewusst weit auseinander und je Anbieter eindeutig: eine Probe, in der beide
#: dasselbe lieferten, könnte den Unterschied nicht sehen.
BS_GHI, BS_SONNE, BS_TEMP = 170.9, 233.3, 18.7
OM_GHI, OM_SONNE, OM_TEMP = 198.5, 415.0, 19.6


def _antwort(ghi: float, sonne: float, temp: float) -> dict:
    return {
        "globalstrahlung_kwh_m2": ghi,
        "sonnenstunden": sonne,
        "durchschnitts_temperatur_c": temp,
        "tage_mit_daten": 31,
        "tage_gesamt": 31,
    }


@pytest.fixture
def beide_anbieter(monkeypatch):
    """Bright Sky und Open-Meteo antworten — mit unterscheidbaren Zahlen."""

    async def bs(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return _antwort(BS_GHI, BS_SONNE, BS_TEMP)

    async def om(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return _antwort(OM_GHI, OM_SONNE, OM_TEMP)

    monkeypatch.setattr("backend.services.brightsky_service.fetch_brightsky_month", bs)
    monkeypatch.setattr(
        "backend.services.wetter.orchestrator.fetch_open_meteo_archive", om
    )


async def _anlage(db, *, provider: str | None, land: str = "DE") -> Anlage:
    """Eine DE-Anlage mit Koordinaten INNERHALB der Bright-Sky-Reichweite."""
    a = Anlage(
        anlagenname=f"Lineal-{provider}",
        leistung_kwp=10.0,
        latitude=50.896149,
        longitude=7.533871,
        standort_land=land,
        wetter_provider=provider,
    )
    db.add(a)
    await db.flush()
    await db.commit()
    return a


class _FakeUpload:
    """Minimales ``UploadFile``-Double — der Import nutzt nur ``await .read()``."""

    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    async def read(self) -> bytes:
        return self._data


def _csv_ohne_wetter() -> str:
    out = StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh"])
    w.writerow([JAHR, MONAT, "500", "200"])
    return out.getvalue()


async def _importiere(db, anlage_id: int) -> Monatsdaten:
    ergebnis = await import_csv(
        anlage_id=anlage_id,
        file=_FakeUpload(_csv_ohne_wetter()),
        ueberschreiben=True,
        auto_wetter=True,
        db=db,
    )
    assert ergebnis.erfolg, ergebnis.fehler
    md = (
        await db.execute(
            select(Monatsdaten).where(
                Monatsdaten.anlage_id == anlage_id,
                Monatsdaten.jahr == JAHR,
                Monatsdaten.monat == MONAT,
            )
        )
    ).scalar_one()
    return md


# ══════════════════════════════════════════════════════════════════════════
# Klausel 1 · Der Import folgt der Anlagen-Wahl
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_import_folgt_der_anlagen_wahl(db, beide_anbieter):
    """``auto`` + Deutschland heißt Bright Sky — im Import wie im Formular.

    Das ist der Kern des Funds: derselbe Anwender, dieselbe Anlage, zwei Wege
    in dieselbe Spalte — und bis hierher zwei Anbieter.
    """
    a = await _anlage(db, provider="auto")

    md = await _importiere(db, a.id)

    assert md.sonnenstunden == pytest.approx(BS_SONNE), (
        f"Der Import schrieb {md.sonnenstunden} h. Bright Sky liefert "
        f"{BS_SONNE} h, Open-Meteo {OM_SONNE} h — der Faktor zwischen beiden "
        "ist genau der Defekt."
    )
    assert md.globalstrahlung_kwh_m2 == pytest.approx(BS_GHI)


@pytest.mark.asyncio
async def test_die_wahl_steuert_wirklich(db, beide_anbieter):
    """Gegenrichtung: wer Open-Meteo wählt, bekommt Open-Meteo.

    Ohne diese Klausel wäre die erste nur die Bestätigung einer Konstante —
    „DE bekommt immer Bright Sky" wäre genauso grün, und die Wahl wäre wieder
    ein Feld, das nichts tut (#386).
    """
    a = await _anlage(db, provider="open-meteo")

    md = await _importiere(db, a.id)

    assert md.sonnenstunden == pytest.approx(OM_SONNE)
    assert md.globalstrahlung_kwh_m2 == pytest.approx(OM_GHI)


@pytest.mark.asyncio
async def test_ohne_gepflegte_wahl_gilt_auto(db, beide_anbieter):
    """Eine Altanlage ohne gespeicherte Wahl verliert ihre Quelle nicht."""
    a = await _anlage(db, provider=None)

    md = await _importiere(db, a.id)

    assert md.sonnenstunden == pytest.approx(BS_SONNE)


@pytest.mark.asyncio
async def test_der_import_laesst_gepflegte_werte_stehen(db, beide_anbieter):
    """Nur eine LÜCKE wird gefüllt — eine Spalte in der Datei gewinnt.

    Dieselbe Regel wie beim Wetter-Knopf seit N-426: ein Wert, den jemand
    mitgebracht hat, wird nicht von einem Abruf ersetzt.
    """
    a = await _anlage(db, provider="auto")
    out = StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh",
                "Globalstrahlung_kWh_m2", "Sonnenstunden"])
    w.writerow([JAHR, MONAT, "500", "200", "123,4", "99,0"])

    ergebnis = await import_csv(
        anlage_id=a.id, file=_FakeUpload(out.getvalue()),
        ueberschreiben=True, auto_wetter=True, db=db,
    )
    assert ergebnis.erfolg, ergebnis.fehler

    md = (
        await db.execute(
            select(Monatsdaten).where(Monatsdaten.anlage_id == a.id)
        )
    ).scalar_one()
    assert md.globalstrahlung_kwh_m2 == pytest.approx(123.4)
    assert md.sonnenstunden == pytest.approx(99.0)


# ══════════════════════════════════════════════════════════════════════════
# Klausel 2 · Das Provenance-Label nennt den LIEFERNDEN Anbieter
# ══════════════════════════════════════════════════════════════════════════


def test_beide_anbieter_haben_ein_label():
    """Ohne Eintrag in ``SOURCE_LABELS`` wirft ``write_with_provenance``."""
    from backend.core.source_priority import SOURCE_LABELS, SourcePriority
    from backend.services.wetter.monatswerte import PROVENANCE_LABEL

    for datenquelle, label in PROVENANCE_LABEL.items():
        assert label in SOURCE_LABELS, (
            f"{datenquelle!r} → {label!r} fehlt in SOURCE_LABELS — "
            "provenance.py wirft dort ausdrücklich KeyError statt still zu raten."
        )
        assert SOURCE_LABELS[label] is SourcePriority.EXTERNAL_AUTHORITATIVE


@pytest.mark.asyncio
async def test_provenance_nennt_den_liefernden_anbieter(db, beide_anbieter):
    """Gewünscht ``auto``, geliefert Bright Sky ⇒ Label ``external:brightsky``.

    ``auto`` selbst ist **kein** Label: es ist eine Regel, kein Anbieter, und
    sie kann morgen anders entscheiden als heute.
    """
    from backend.services.wetter.monatswerte import (
        loese_monats_wetter,
        provenance_label,
    )

    a = await _anlage(db, provider="auto")
    data = await loese_monats_wetter(db, a, JAHR, MONAT)

    assert data["datenquelle"] == "brightsky"
    assert provenance_label(data["datenquelle"]) == "external:brightsky"


@pytest.mark.asyncio
async def test_faellt_bright_sky_aus_nennt_das_label_open_meteo(db, monkeypatch):
    """Die Kette liefert, das Label folgt ihr — nicht dem Wunsch.

    Genau der Fall aus #386: Bright Sky hat für den Ort keinen einzigen
    Strahlungstag, Open-Meteo springt ein. Stünde jetzt ``external:brightsky``
    in der Provenance, wäre die Reihe gemischt und die Herkunft trotzdem
    einheitlich — also unauffindbar.
    """
    from backend.services.wetter.monatswerte import (
        loese_monats_wetter,
        provenance_label,
    )

    async def bs_ohne_strahlung(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return {
            "globalstrahlung_kwh_m2": 0.0, "sonnenstunden": 0.0,
            "tage_mit_daten": 0, "tage_gesamt": 31,
        }

    async def om(latitude, longitude, jahr, monat, **kw):  # noqa: ARG001
        return _antwort(OM_GHI, OM_SONNE, OM_TEMP)

    monkeypatch.setattr(
        "backend.services.brightsky_service.fetch_brightsky_month", bs_ohne_strahlung
    )
    monkeypatch.setattr(
        "backend.services.wetter.orchestrator.fetch_open_meteo_archive", om
    )

    a = await _anlage(db, provider="auto")
    data = await loese_monats_wetter(db, a, JAHR, MONAT)

    assert data["datenquelle"] == "open-meteo"
    assert provenance_label(data["datenquelle"]) == "external:openmeteo"


def test_ein_langjaehriges_mittel_bekommt_kein_label():
    """PVGIS-TMY und die statischen Defaults dürfen nichts festschreiben.

    Ein Mittel über viele Jahre ist keine Messung *dieses* Monats. Ein Label
    dafür hieße: ein automatischer Pfad dürfte es eintragen — und ein schwaches
    Jahr verschwände hinter seinem eigenen Durchschnitt.
    """
    from backend.services.wetter.monatswerte import (
        ist_messende_quelle,
        provenance_label,
    )

    for quelle in ("pvgis-tmy", "defaults", None, ""):
        assert provenance_label(quelle) is None, quelle
        assert ist_messende_quelle(quelle) is False, quelle
    assert ist_messende_quelle("brightsky") is True
    assert ist_messende_quelle("open-meteo") is True
