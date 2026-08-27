"""#395 (OB73-gif) — zwei Werte, die eedc kennt, verlassen eedc: VM/NM und Grundlast.

Punkt 3 und Punkt 5 seiner Wunschliste. Beide sind **Export**-Arbeiten, keine
Rechenarbeit — die Zahlen existierten längst und wurden nur nicht ausgeliefert.

⛔ **Beide tragen einen Fund, und beide Funde sind Namens-/Wortlaut-Fehler, keine
Rechenfehler:**

* **N-331** — die öffentliche Zusage in #395 nannte einen festen 13-Uhr-Schnitt
  und behauptete, das sei „die Aufteilung, die auf deinem Bildschirm steht".
  eedc schneidet an **allen** drei rechnenden Stellen am **Solar Noon**. Der
  Sensor folgt der Anzeige, nicht der Zusage — sonst stünden wieder zwei Zahlen
  für dieselbe Größe nebeneinander.
* **N-332** — „Grundlast" bezeichnete zwei verschiedene Zahlen: die aus dem
  Verbrauchs-**Profil** (ohne Historie ein BDEW-H0-Modellwert) und die
  **gemessene** aus den Nachtstunden. Der Sensor nimmt die gemessene.

`test_keine_stelle_schneidet_an_13_uhr` ist der **Wächter** dieser Runde: er
fängt auch eine Stelle, die es heute noch nicht gibt.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.services.ha_export_prognose import _solar_noon_text
from backend.services.solar_forecast_service import _solar_noon_hour

_BACKEND = Path(__file__).resolve().parents[1]


# ── N-331: der Schnitt ───────────────────────────────────────────────────────

def test_solar_noon_attribut_stammt_aus_derselben_quelle_wie_der_schnitt():
    """Die mitgelieferte Grenze MUSS die sein, an der wirklich getrennt wurde.

    ⭐ **Das ist der eigentliche Zweck des Attributs.** Der Einwand aus der
    Zusage — eine bewegliche Grenze lässt eine Automation an zwei Tagen
    verschieden entscheiden — ist berechtigt; beantwortet ist er nur, wenn die
    Automation die Grenze **lesen** kann. Eine zweite Berechnung dafür wäre die
    nächste zweite Wahrheit.
    """
    for tag in (date(2026, 1, 15), date(2026, 6, 21), date(2026, 10, 30)):
        stunde = _solar_noon_hour(tag.isoformat(), 11.5)
        h = int(stunde)
        assert _solar_noon_text(tag, 11.5) == f"{h:02d}:{int((stunde - h) * 60):02d}"


def test_ohne_laengengrad_keine_grenze():
    """Ohne Standort gibt es keinen Solar Noon — und dann auch keine erfundene
    Uhrzeit im Attribut."""
    assert _solar_noon_text(date(2026, 6, 21), None) is None


def test_solar_noon_liegt_im_sommer_nach_13_uhr():
    """Die Zahl hinter dem Fund: in MESZ liegt die Tagesmitte **nach** 13 Uhr.

    Ein fester 13-Uhr-Schnitt hätte im Sommer rund eine halbe Ertragsstunde
    anders zugeordnet als die Anzeige daneben — deshalb ist die Abweichung
    zwischen Zusage und Code kein Formalismus.
    """
    assert _solar_noon_hour("2026-06-21", 11.5) > 13.0
    # Im Winter (MEZ) umgekehrt — der feste Schnitt ist auch dort nicht richtig,
    # nur in die andere Richtung.
    assert _solar_noon_hour("2026-01-15", 11.5) < 13.0


def test_keine_stelle_schneidet_an_13_uhr():
    """**Wächter** (N-331): Vormittag/Nachmittag entsteht nirgends an einer
    festen Uhrzeit.

    Der Fund war ein Kommentar, der eine Schwelle nannte, die woanders berechnet
    wird. Ein Wächter auf den Wortlaut wäre wertlos — dieser prüft die
    **Rechnung**: jede Funktion, die eine Tageshälfte bildet, muss Solar Noon
    verwenden.
    """
    treffer = []
    for pfad in _BACKEND.rglob("*.py"):
        if "/tests/" in str(pfad):
            continue
        text = pfad.read_text(encoding="utf-8")
        for name in ("vormittag", "morgens_kwh", "vm_kwh", "tageshaelfte"):
            if name not in text:
                continue
            # Die Rechenstellen erkennt man am Namen der Grenze; fehlt sie
            # ganz, während eine 13 als Stundenschwelle auftaucht, ist das der
            # Fund.
            if re.search(r"(stunde|hour|h)\s*[<>=]=?\s*13\b", text):
                treffer.append(str(pfad.relative_to(_BACKEND)))
            break
    assert not treffer, (
        "Diese Dateien bilden eine Tageshälfte an einer festen 13-Uhr-Grenze — "
        f"eedc schneidet am Solar Noon (N-331): {sorted(set(treffer))}"
    )


def test_die_vier_haelften_sensoren_sind_definiert():
    """Vier statt zwei — die Abendentscheidung betrifft **morgen**.

    OB73-gifs Fall ist „warte ich auf den Nachmittags-Peak oder lade ich früher
    voll?". Abends ist „heute Nachmittag" dafür zu spät.
    """
    from backend.services.ha_sensors_export import PROGNOSE_SENSOREN

    keys = {s.key for s in PROGNOSE_SENSOREN}
    for tag in ("heute", "morgen"):
        for haelfte in ("vormittag", "nachmittag"):
            assert f"eedc_prognose_{tag}_{haelfte}_kwh" in keys


# ── N-332: die Grundlast ─────────────────────────────────────────────────────

#: Ein **festes** Datum statt der Prozessuhr — der Prüfling nimmt `heute` als
#: Parameter (dasselbe Muster wie `core/hub_leer_grund.py`). Eine Probe, die
#: `date.today()` liest, wettet auf die Stunde ihres Laufs (N-167).
_STICHTAG = date(2026, 6, 17)


async def _anlage(db):
    from backend.models import Anlage

    a = Anlage(anlagenname="395", leistung_kwp=10.0,
               installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    await db.commit()
    return a


async def _nachtstunden(db, anlage_id, werte: list[float]):
    """Gemessene Nachtstunden über den echten Weg: `TagesEnergieProfil`.

    ⚠ Bewusst **nicht** `berechne_grundlast` direkt gefüttert — dann prüfte die
    Probe die Formel (die eigene Tests hat) statt die Frage, ob der Sensor die
    **richtige Quelle** liest. Genau das ist der Fund.
    """
    from backend.models.tages_energie_profil import TagesEnergieProfil

    for i, kw in enumerate(werte):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id,
            datum=_STICHTAG.replace(day=1) + timedelta(days=i // 5),
            stunde=i % 5,
            verbrauch_kw=kw,
        ))
    await db.commit()


async def test_grundlast_nur_mit_gemessenen_nachtstunden(db):
    """Ohne Messung **kein** Wert — und mit Messung der Median, nicht das Mittel."""
    from backend.api.routes.ha_export import grundlast_sensorwert

    anlage = await _anlage(db)
    wert, weg = await grundlast_sensorwert(db, anlage.id, _STICHTAG)
    assert wert is None and weg is None, (
        "ohne Messung darf kein Sensor entstehen — sonst wäre der Modellwert "
        "aus dem Standardprofil als Messung unterwegs"
    )

    await _nachtstunden(db, anlage.id, [0.30, 0.34, 0.32, 0.40, 0.28])
    wert, weg = await grundlast_sensorwert(db, anlage.id, _STICHTAG)
    assert wert == pytest.approx(0.32), "Median, nicht Mittelwert (Ø wäre 0,328)"
    assert "gemessene" in weg


async def test_grundlast_ignoriert_einen_anderen_monat(db):
    """Der Sensor beschreibt den **laufenden** Monat.

    Ohne diese Probe wäre „liest die richtige Quelle" belegt, „liest den
    richtigen Zeitraum" aber nicht — und der Monatsfilter sitzt in der Query,
    nicht in der Formel.
    """
    from backend.api.routes.ha_export import grundlast_sensorwert

    anlage = await _anlage(db)
    await _nachtstunden(db, anlage.id, [0.30, 0.34, 0.32])
    wert, _ = await grundlast_sensorwert(db, anlage.id, date(2026, 7, 17))
    assert wert is None


def test_grundlast_sensor_traegt_seine_herkunft_im_namen():
    """Die Formel-Zeile ist das, was der Anwender in HA liest.

    Sie muss sagen, dass es die **gemessene** Größe ist — sonst wiederholt sich
    der Fund eine Ebene weiter: zwei Zahlen unter einem Namen, diesmal zwischen
    Sensor und Live-Anzeige.
    """
    from backend.services.ha_sensors_export import ANLAGE_SENSOREN

    sensor = next(s for s in ANLAGE_SENSOREN if s.key == "eedc_grundlast_kw")
    assert "GEMESSEN" in sensor.formel.upper()
    assert sensor.unit == "kW" and sensor.device_class == "power"


def test_live_anzeige_nennt_die_prognose_beim_namen():
    """Die andere Hälfte von N-332 — im Client.

    Die Live-Zahl bleibt (sie ist die richtige Antwort für ihre Frage), aber sie
    heißt nicht mehr wie die gemessene.
    """
    quelle = (
        _BACKEND.parent / "frontend/src/components/live/WetterWidget.tsx"
    ).read_text(encoding="utf-8")
    assert "Grundlast (Prognose)" in quelle
    assert "Grundlast {fmtZahl" not in quelle, "der alte, mehrdeutige Name ist zurück"
