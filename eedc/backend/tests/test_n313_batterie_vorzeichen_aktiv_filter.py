"""N-313: Der Batterie-Vorzeichen-Check zieht die Aktiv-Grenze **pro Tag**.

**Der Befund.** ``_check_batterie_vorzeichen_historie`` lud die Investitionen
einer Anlage ohne Aktiv-Filter und reichte sie an
``get_komponenten_tageskwh_lts`` weiter. Diese Liste entscheidet, welche
Sensoren HA-seitig überhaupt gelesen werden. Die Gegenseite — die gespeicherte
``TagesZusammenfassung`` — entsteht dagegen in
``energie_profil.aggregator.aggregate_day``, das seine Investitionen mit
``aktiv_am_tag(datum)`` lädt.

Ein Speicher, der an diesem Tag stillgelegt, noch nicht angeschafft oder auf
``aktiv=False`` gesetzt war, dessen HA-Sensor aber weiterläuft, stand damit
**nur auf der HA-Seite**. Kippt sein Beitrag das Netto-Vorzeichen, meldet eedc
einen „vertauschten" Tag samt Knopf „Tag reparieren" — und die Neu-Aggregation
kann ihn nicht auflösen: Sie schreibt für dieses Gerät nichts, der gespeicherte
Wert bleibt, die Meldung bleibt. Die P-6-Falle, wortgleich zu N-57/#368.

⚠ **Es braucht einen ZWEITEN, aktiven Speicher.** Bei nur einem Gerät liegt
``stored_netto`` unter der 1-kWh-Schwelle, und die Schleife bricht ab, bevor
überhaupt gelesen wird — deshalb ist der Fall hier mit zwei Speichern gebaut.

⛔ **Was hier NICHT geprüft wird:** die drei anderen Stellen in derselben Datei
mit wörtlich derselben Query-Zeile (``:346``, ``:548``, ``:1589``). Sie sind
gemessen und tragen den Befund nicht: ``:346`` filtert 30 Zeilen tiefer selbst
(N-64), ``:548`` filtert in ``erwartete_komponenten_keys``, und ``:1589`` ist
ausdrücklich und begründet ohne Filter (die Liste dient dort nur dem *Namen*
in der Meldung). *Eine gleich aussehende Zeile ist kein gleicher Befund.*
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from backend.models.investition import Investition
from backend.services.daten_checker import DatenChecker, CheckKategorie

_KAT = CheckKategorie.BATTERIE_VORZEICHEN_HISTORIE.value

#: Feste Daten statt Prozessuhr (N-167): Die Suite läuft in drei Zeitzonen,
#: und eine Probe, die `date.today()` liest, wettet auf die Stunde ihres Laufs.
#: Das Fenster der Prüfung (`bis = heute − 1`, 90 Tage zurück) steckt allein in
#: der DB-Abfrage, und die ist hier ein Double — welches Datum die gelieferten
#: Zeilen tragen, ist der Prüfung gleichgültig.
_TAG = date(2026, 6, 15)
#: Der stillgelegte Speicher ging am Vortag außer Betrieb.
_STILLGELEGT_AM = _TAG - timedelta(days=1)

# Schwesterdateien: test_batterie_vorzeichen_historie_check.py (dieselbe
# Prüfung, ohne den Aktiv-Filter), test_etappe_6_drift_check.py (N-64 — der
# wortgleiche Filter im Drift-Check) und
# test_daten_checker_leere_tage_trotz_zaehler.py (N-57, derselbe Filter dort).


def _anlage():
    return SimpleNamespace(id=1, sensor_mapping={
        "investitionen": {
            "5": {"felder": {
                "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.bat_a"},
            }},
            "6": {"felder": {
                "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.bat_b"},
            }},
        },
    })


def _inv(inv_id, stilllegungsdatum=None):
    return Investition(
        id=inv_id, anlage_id=1, typ="speicher", parameter={}, aktiv=True,
        anschaffungsdatum=None, stilllegungsdatum=stilllegungsdatum,
    )


def _tz(netto_aktiv: float):
    """Gespeicherte Zeile — sie kennt NUR den aktiven Speicher.

    Genau so schreibt `aggregate_day` sie: das stillgelegte Gerät ist am
    Stichtag nicht `aktiv_am_tag`, also steht sein Key nicht in der Zeile.
    """
    return SimpleNamespace(
        id=1, anlage_id=1, datum=_TAG,
        komponenten_kwh={"batterie_5": netto_aktiv, "netzbezug": 2.0},
    )


async def _run(tz_list, invs, ha_komp):
    db = MagicMock()
    ruf = {"n": 0}

    async def _execute(_stmt):
        ruf["n"] += 1
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=tz_list if ruf["n"] == 1 else invs)
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)
        return result

    db.execute = _execute
    checker = DatenChecker(db)

    ha_svc = MagicMock()
    ha_svc.is_available = True

    #: Was der LTS-Read zurückgibt, hängt an der durchgereichten Investitions-
    #: Liste — genau das ist der Hebel des Befunds. Das Double bildet das nach:
    #: Es liefert einen Key NUR, wenn das Gerät in der Liste steht.
    gesehen: dict[str, dict] = {}

    async def _lts(_anlage_, invs_by_id, datum):
        gesehen["invs"] = dict(invs_by_id)
        return {k: v for k, v in ha_komp.items()
                if not k.startswith("batterie_")
                or k.split("_")[1] in invs_by_id}

    with patch(
        "backend.services.ha_statistics_service.get_ha_statistics_service",
        return_value=ha_svc,
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        side_effect=_lts,
    ):
        ergebnisse = await checker._check_batterie_vorzeichen_historie(_anlage())
    return ergebnisse, gesehen


async def test_stillgelegter_speicher_kippt_das_vorzeichen_nicht():
    """Der Befund: ohne Tagesfilter meldet eedc einen Konflikt, den es nicht gibt.

    Gespeichert steht **+3,0** (nur der aktive Speicher, ENTLADUNG positiv).
    HA liefert für den aktiven ebenfalls +3,0 — und für den **stillgelegten**
    zusätzlich −9,0, weil dessen Sensor weiterläuft. Ohne Filter ist das
    HA-Netto −6,0: entgegengesetztes Vorzeichen, beidseitig über der Schwelle,
    also eine Warnung samt Reparatur-Knopf, der nichts ausrichten kann.

    Mit dem Tagesfilter steht das stillgelegte Gerät gar nicht erst in der
    Liste, die den LTS-Read steuert — HA-Netto +3,0, kein Konflikt.
    """
    ergebnisse, gesehen = await _run(
        [_tz(3.0)],
        [_inv(5), _inv(6, stilllegungsdatum=_STILLGELEGT_AM)],
        {"batterie_5": 3.0, "batterie_6": -9.0},
    )

    warnungen = [e for e in ergebnisse if e.schwere == "warning"]
    assert warnungen == [], (
        "Ein am Stichtag stillgelegter Speicher darf das Vorzeichen nicht "
        f"kippen — gemeldet wurde: {[w.meldung for w in warnungen]}"
    )
    assert not any(e.action_kind == "reaggregate_range" for e in ergebnisse)
    assert "6" not in gesehen["invs"], (
        "Der stillgelegte Speicher wurde an den LTS-Read durchgereicht — "
        "genau der Weg, über den er auf die HA-Seite gelangt."
    )
    assert "5" in gesehen["invs"], "Der aktive Speicher muss weiter gelesen werden."


async def test_echter_vorzeichen_konflikt_wird_weiter_gemeldet():
    """Die Gegenrichtung: der Filter darf den echten Fall nicht mit wegräumen.

    Beide Speicher sind aktiv, gespeichert steht **−4,0** (alte Konvention),
    frisch liefert HA **+4,0**. Das ist der Fall, für den die Prüfung gebaut
    wurde — er muss unverändert eine Warnung mit beiden Knöpfen ergeben.
    """
    ergebnisse, _ = await _run(
        [_tz(-4.0)],
        [_inv(5), _inv(6)],
        {"batterie_5": 4.0},
    )

    bereich = [e for e in ergebnisse if e.action_kind == "reaggregate_range"]
    einzel = [e for e in ergebnisse if e.action_kind == "reaggregate_day"]
    assert len(bereich) == 1, f"Erwartet 1 Bereichs-Eintrag, bekommen {ergebnisse}"
    assert len(einzel) == 1, f"Erwartet 1 Einzeltag-Eintrag, bekommen {einzel}"
    assert einzel[0].action_params == {"anlage_id": 1, "datum": _TAG.isoformat()}
