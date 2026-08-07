"""Die Solarprognose zieht nach, wenn sie nicht mehr zur Anlage passt (#363).

Der gemeldete Fall: für ein 2,4-kWp-Balkonkraftwerk stand ein Jahres-SOLL von
357 MWh, weil die gespeicherte Prognose zu einer weit größeren Anlage gehörte.
Eine Prognose wird beim Abruf eingefroren; ändert sich die Anlage danach,
rechnet jede SOLL/IST-Sicht gegen eine Anlage, die es nicht mehr gibt.

**Die schärfsten Proben hier sind die Abgrenzungen, nicht der Fix:**

* `test_alte_aber_passende_prognose_ist_kein_grund` hält fest, dass ALTER allein
  nichts auslöst. Am 2026-08-07 gegen die echte API gemessen: PVGIS rechnet auf
  einem abgeschlossenen Klimamittel (v5_2 → SARAH2 2005-2020, v5_3 → SARAH3
  2005-2023), ein zweiter Abruf mit gleichen Eingaben liefert dieselbe Zahl. Wer
  die abgelöste 7-Tage-Regel zurückholt, reißt genau diese Probe.
* `test_frische_prognose_meldet_keine_abweichung` fängt den Fehler, der die
  Automatik in eine Dauerschleife schickt: rechnet der Prüfer die gewichteten
  Winkel anders als der Speicherpfad, meldet eine gerade geschriebene Prognose
  sich selbst als abweichend — und der Job ruft jede Nacht neu ab.

Kein Netz: `pruefe_prognose` liest ausschließlich Stammdaten und die
gespeicherte Zeile. Das ist kein Zufall, sondern der Grund, warum die Prüfung
täglich für jede Anlage laufen kann, ohne einen einzigen Request zu erzeugen.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.models import Anlage, Investition
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.pvgis_aktualitaet import (
    DATENSATZ_JE_API_VERSION,
    api_version,
    erwarteter_datensatz,
    pruefe_prognose,
)

AKTUELLER_DATENSATZ = "PVGIS-SARAH3"


async def _anlage(db, *, lat=48.1, lon=11.6, horizont=None, kwp=9.8) -> Anlage:
    anlage = Anlage(
        anlagenname="Testanlage",
        leistung_kwp=kwp,  # NOT NULL — die Prüfung liest sie nicht, die Spalte
        latitude=lat,      # trägt die Anlagen-Nennleistung, nicht die Modulsumme
        longitude=lon,
        horizont_daten=horizont,
    )
    db.add(anlage)
    await db.flush()
    return anlage


async def _modul(db, anlage_id: int, *, kwp: float, neigung=35.0, ausrichtung="Süd") -> Investition:
    inv = Investition(
        anlage_id=anlage_id,
        bezeichnung=f"String {kwp} kWp",
        typ="pv-module",
        anschaffungskosten_gesamt=1000.0,
        anschaffungsdatum=date(2020, 1, 1),
        leistung_kwp=kwp,
        neigung_grad=neigung,
        ausrichtung=ausrichtung,
        aktiv=True,
    )
    db.add(inv)
    await db.flush()
    return inv


async def _prognose(
    db,
    anlage_id: int,
    *,
    kwp: float,
    neigung=35.0,
    azimut=0.0,
    lat=48.1,
    lon=11.6,
    losses=14.0,
    horizont_verwendet=False,
    raddatabase=AKTUELLER_DATENSATZ,
    abgerufen_am=None,
) -> PVGISPrognose:
    p = PVGISPrognose(
        anlage_id=anlage_id,
        abgerufen_am=abgerufen_am or datetime(2026, 8, 1, 12, 0),
        latitude=lat,
        longitude=lon,
        neigung_grad=neigung,
        ausrichtung_grad=azimut,
        system_losses=losses,
        jahresertrag_kwh=kwp * 1000,
        spezifischer_ertrag_kwh_kwp=1000.0,
        gesamt_leistung_kwp=kwp,
        horizont_verwendet=horizont_verwendet,
        raddatabase=raddatabase,
        ist_aktiv=True,
    )
    db.add(p)
    await db.flush()
    return p


# ── Der gemeldete Fall ────────────────────────────────────────────────────


async def test_geschrumpfte_anlage_meldet_die_nennleistung(db):
    """#363: die Prognose gehört zu einer Anlage, die es so nicht mehr gibt."""
    anlage = await _anlage(db)
    await _modul(db, anlage.id, kwp=2.4)
    await _prognose(db, anlage.id, kwp=9.8)

    abweichung = await pruefe_prognose(db, anlage.id)

    assert abweichung is not None
    assert "Nennleistung" in abweichung.text
    assert "9.80" in abweichung.text and "2.40" in abweichung.text


async def test_die_eingestellten_verluste_gehen_in_den_neuabruf(db):
    """„Eingestellte Verluste bleiben erhalten" — sonst fällt der Nutzer
    stillschweigend auf den Default 14 % zurück. Die Verluste sind nirgends
    sonst gespeichert (im Client ein UI-State), die alte Prognose ist die
    einzige Quelle."""
    anlage = await _anlage(db)
    await _modul(db, anlage.id, kwp=2.4)
    await _prognose(db, anlage.id, kwp=9.8, losses=8.5)

    abweichung = await pruefe_prognose(db, anlage.id)

    assert abweichung is not None
    assert abweichung.system_losses == 8.5


# ── Die Abgrenzungen ──────────────────────────────────────────────────────


async def test_alte_aber_passende_prognose_ist_kein_grund(db):
    """ALTER allein löst nichts aus — die abgelöste 7-Tage-Regel (#363).

    PVGIS rechnet auf einem festen Klimamittel; ein Neuabruf für dieselbe
    Anlage liefert dieselbe Zahl. Diese Probe fällt, sobald jemand das Alter
    wieder zum Auslöser macht.
    """
    anlage = await _anlage(db)
    await _modul(db, anlage.id, kwp=9.8)
    await _prognose(
        db, anlage.id, kwp=9.8,
        abgerufen_am=datetime(2026, 8, 1) - timedelta(days=900),
    )

    assert await pruefe_prognose(db, anlage.id) is None


async def test_frische_prognose_meldet_keine_abweichung(db):
    """Der Prüfer muss die gewichteten Winkel genauso rechnen wie der
    Speicherpfad. Tut er es nicht, meldet eine gerade geschriebene Prognose
    sich selbst als abweichend und der Job ruft jede Nacht neu ab.

    Bewusst mit UNGLEICHEN Modulen: bei zwei identischen Strings stimmt jede
    Gewichtung zufällig überein.
    """
    anlage = await _anlage(db)
    await _modul(db, anlage.id, kwp=7.0, neigung=30.0, ausrichtung="Süd")
    await _modul(db, anlage.id, kwp=3.0, neigung=45.0, ausrichtung="West")

    # Gewichtet: Neigung (7·30 + 3·45)/10 = 34,5 · Azimut (7·0 + 3·90)/10 = 27,0
    await _prognose(db, anlage.id, kwp=10.0, neigung=34.5, azimut=27.0)

    assert await pruefe_prognose(db, anlage.id) is None


async def test_ohne_prognose_wird_nichts_abgerufen(db):
    """Wer nie abgerufen hat, hat es vielleicht mit Absicht nicht getan."""
    anlage = await _anlage(db)
    await _modul(db, anlage.id, kwp=9.8)

    assert await pruefe_prognose(db, anlage.id) is None


# ── Die übrigen Auslöser ──────────────────────────────────────────────────


async def test_umgerichteter_string_wird_erkannt(db):
    """Die kWp bleiben gleich, der Ertrag ändert sich trotzdem."""
    anlage = await _anlage(db)
    await _modul(db, anlage.id, kwp=9.8, ausrichtung="Ost")
    await _prognose(db, anlage.id, kwp=9.8, azimut=0.0)  # Prognose war Süd

    abweichung = await pruefe_prognose(db, anlage.id)

    assert abweichung is not None
    assert "Ausrichtung" in abweichung.text


async def test_hochgeladenes_horizontprofil_wird_erkannt(db):
    anlage = await _anlage(db, horizont=[5.0] * 36)
    await _modul(db, anlage.id, kwp=9.8)
    await _prognose(db, anlage.id, kwp=9.8, horizont_verwendet=False)

    abweichung = await pruefe_prognose(db, anlage.id)

    assert abweichung is not None
    assert "Horizontprofil" in abweichung.text


async def test_bestandsprognose_ohne_datensatz_zieht_einmalig_nach(db):
    """`raddatabase` NULL = vor v4.0.11 geschrieben, also PVGIS-SARAH2.

    Der einzige Auslöser, der NICHT an den Stammdaten hängt — ohne ihn bliebe
    der Bestand dauerhaft auf dem alten Strahlungsdatensatz, während jede
    Neuinstallation auf dem neuen rechnet.
    """
    anlage = await _anlage(db)
    await _modul(db, anlage.id, kwp=9.8)
    await _prognose(db, anlage.id, kwp=9.8, raddatabase=None)

    abweichung = await pruefe_prognose(db, anlage.id)

    assert abweichung is not None
    assert "Strahlungsdatensatz" in abweichung.text
    assert "PVGIS-SARAH2" in abweichung.text


# ── Der Azimut aus dem Ausrichtungstext ───────────────────────────────────


@pytest.mark.parametrize(
    "text,azimut",
    [
        ("Süd", 0), ("S", 0), ("Sued", 0), ("south", 0),
        ("Südost", -45), ("SO", -45), ("Süd-Ost", -45), ("süd ost", -45),
        ("Ost", -90), ("O", -90), ("east", -90),
        ("Nordost", -135), ("NO", -135),
        ("Nord", 180), ("N", 180),
        ("Nordwest", 135), ("NW", 135),
        ("West", 90), ("W", 90), ("  West  ", 90),
        ("Südwest", 45), ("SW", 45), ("Suedwest", 45),
        ("Ost-West", 0), ("OW", 0),
    ],
)
def test_ausrichtungstext_wird_zum_richtigen_azimut(text, azimut):
    """Bis v4.0.11 kamen 11 von 16 Himmelsrichtungen falsch heraus (#363).

    Ursache war ein Substring-Match: „s" (Süd) traf in „ost" und „west", „o"
    (Ost) in „nord". Eine Ost-Anlage ohne gepflegten `ausrichtung_grad` bekam
    damit eine SÜD-Prognose — eine SOLL-Zahl, die deutlich zu hoch ist.

    Die Funktion hatte keinen einzigen Test (Negativbeweis über den ganzen
    `tests/`-Baum), deshalb fiel es niemandem auf. Genau diese Fälle sind die
    Probe: „Süd", „S", „O", „N" und „W" waren auch vorher richtig — wer nur die
    prüft, misst nichts.
    """
    from backend.api.routes.pvgis import ausrichtung_zu_azimut

    assert ausrichtung_zu_azimut(text) == azimut


def test_unbekannte_ausrichtung_faellt_auf_sued_zurueck():
    """Abgrenzung: der Fallback bleibt, er war nie das Problem."""
    from backend.api.routes.pvgis import ausrichtung_zu_azimut

    assert ausrichtung_zu_azimut("Dachgaube hinten") == 0
    assert ausrichtung_zu_azimut(None) == 0
    assert ausrichtung_zu_azimut("") == 0


# ── Der Job selbst ────────────────────────────────────────────────────────


async def test_job_ruft_nur_bei_abweichung_ab_und_erhaelt_die_verluste(db, monkeypatch):
    """Der Scheduler-Job ist dünn, aber zwei Dinge muss er richtig machen:
    ohne Abweichung **gar nicht** abrufen, und die Verluste der bestehenden
    Prognose durchreichen. Ohne diese Probe wäre allein der SoT gedeckt und der
    Aufruf daneben ungeprüft — genau die Stelle, an der ein Default zurückkommt.
    """
    from backend.services import scheduler as sched

    aufrufe: list[dict] = []

    async def _speichern_stub(*, anlage_id, system_losses, db):
        aufrufe.append({"anlage_id": anlage_id, "system_losses": system_losses})
        return None

    class _SessionCtx:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *_):
            return False

    monkeypatch.setattr(
        "backend.api.routes.pvgis.speichere_pvgis_prognose", _speichern_stub
    )
    monkeypatch.setattr("backend.core.database.get_session", lambda: _SessionCtx())

    # Anlage 1 passt, Anlage 2 ist geschrumpft.
    passend = await _anlage(db)
    await _modul(db, passend.id, kwp=9.8)
    await _prognose(db, passend.id, kwp=9.8, losses=11.0)

    abweichend = await _anlage(db)
    await _modul(db, abweichend.id, kwp=2.4)
    await _prognose(db, abweichend.id, kwp=9.8, losses=8.5)
    await db.flush()

    await sched.pvgis_aktualitaet_job()

    assert len(aufrufe) == 1, "die passende Anlage darf keinen Abruf auslösen"
    assert aufrufe[0]["anlage_id"] == abweichend.id
    assert aufrufe[0]["system_losses"] == 8.5


# ── Die Pflege-Falle ──────────────────────────────────────────────────────


def test_erwarteter_datensatz_passt_zur_api_version():
    """Version und Datensatz dürfen nicht auseinanderlaufen.

    Wer `core/config.py::pvgis_api_url` hebt, ohne
    `DATENSATZ_JE_API_VERSION` zu ergänzen, bekommt `erwarteter_datensatz() is
    None` — dann schweigt der Datensatz-Auslöser stillschweigend, und niemand
    zieht nach. Diese Probe macht den vergessenen Eintrag laut.
    """
    version = api_version()
    assert version in DATENSATZ_JE_API_VERSION, (
        f"PVGIS-API-Version {version!r} ist konfiguriert, aber der zugehörige "
        f"Strahlungsdatensatz fehlt in DATENSATZ_JE_API_VERSION."
    )
    assert erwarteter_datensatz() == AKTUELLER_DATENSATZ
