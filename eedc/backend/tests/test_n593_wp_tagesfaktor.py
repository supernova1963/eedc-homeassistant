"""N-593 — die Temperaturkorrektur der Verbrauchsprognose rechnet mit dem TAGESmittel.

**Der Defekt.** Bis 01.10.2026 bekam jede Stunde einen eigenen Faktor: die
Heizgradtage *ihrer* Temperatur gegen die Heizgradtage des Mittels *aller*
Stunden der Lernwoche. Bei einem Tagesgang 7–17 °C (Ø 12 °C) und **genau
demselben** Wetter am Prognosetag bekam die 7-°C-Stunde ×2,67 und die
17-°C-Stunde ×0,1 — die Korrektur schob den Wärmepumpen-Strom bei unverändertem
Wetter in die Nacht, also genau dorthin, wo #420 plant.

**Die Regel** (K-2, ``core/berechnungen/heizgradtage.py``; KONZEPT-WAERME-KLIMA
§5.6): Heizgradtage nur aus **Tages**mitteln. Referenz = Mittel der
Tages-Heizgradtage der Lernwoche, Prognose = Heizgradtage des Tagesmittels,
ein Faktor je Tag für alle Stunden.

**Was hier gewächtert wird** (Vorlage §3 C1):

* (a) **Invarianz** — Prognosetag mit genau den Stundentemperaturen der
  Lernwoche ⇒ Faktor 1,0, die WP-Reihe ist das gelernte Profil. An der Formel,
  an der Live-Kurve, an der Export-Reihe und über den Lernpfad (DB) hinweg.
* (b) **Konvexität** — eine Lernwoche mit Tagen beidseits der Heizgrenze hat als
  Referenz das Mittel der Tageswerte, nicht die Heizgradtage des Mittels.
* (c) **Kälter** — Referenz 10 Kd, Tag Ø 0 °C ⇒ ×1,5 für **jede** Stunde.

Dazu die Degradation aus Vorlage §4: eine Stunde ohne Temperatur bleibt
unkorrigiert, ein Tag ganz ohne Temperatur hat Faktor 1.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.api.routes.live_wetter import _berechne_verbrauchsprofil
from backend.core.berechnungen.heizgradtage import (
    heizgradtage_tag,
    referenz_heizgradtage,
    wp_tagesfaktor,
)
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.verbrauchsprognose_heute import verbrauchsprognose_heute
from backend.tests import factories

#: Ein Tagesgang 7–17 °C, Minimum um 4/5 Uhr, Maximum um 15/16 Uhr — Ø genau 12,0 °C.
TAGESGANG = [
    11.0, 10.0, 9.0, 9.0, 7.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0,
    14.0, 15.0, 16.0, 17.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0, 12.0, 11.0,
]
#: Das gelernte Wärmepumpen-Profil: nachts mehr als nachmittags, wie bei jeder
#: Heizung — genau die Form, die die alte Formel bei gleichem Wetter verbog.
WP_PROFIL = {h: (0.8 if h < 7 or h >= 20 else 0.3) for h in range(24)}
HAUS = 0.4

_MITTWOCH = datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))


def _stunden(temps: list) -> list[dict]:
    return [{"zeit": f"{h:02d}:00", "temperatur_c": t} for h, t in enumerate(temps)]


def _gesamtprofil() -> dict[int, float]:
    return {h: round(HAUS + WP_PROFIL[h], 3) for h in range(24)}


# ── Vorbedingung der Proben ─────────────────────────────────────────────────

def test_tagesgang_hat_genau_12_grad_mittel():
    assert sum(TAGESGANG) / len(TAGESGANG) == pytest.approx(12.0)
    assert min(TAGESGANG) < 12.0 < max(TAGESGANG), "ein Tagesgang, keine Konstante"


# ── (a) Invarianz ───────────────────────────────────────────────────────────

def test_a1_gleiches_wetter_ergibt_faktor_eins():
    ref = referenz_heizgradtage({f"t{i}": TAGESGANG for i in range(7)})
    assert ref == pytest.approx(3.0)
    assert wp_tagesfaktor(ref, TAGESGANG) == pytest.approx(1.0)


def test_a2_live_kurve_laesst_das_gelernte_profil_stehen():
    """Kachel und Live-Kurve: jede Stunde == gelerntes Profil (Haus + WP)."""
    ref = referenz_heizgradtage({f"t{i}": TAGESGANG for i in range(7)})
    profil, _, _, _ = _berechne_verbrauchsprofil(
        _stunden(TAGESGANG), kwp=10.0,
        individuelles_profil=_gesamtprofil(), wp_profil=WP_PROFIL,
        referenz_hdd_kd=ref,
    )
    ist = {int(p["zeit"][:2]): p["verbrauch_kw"] for p in profil}
    erwartet = {h: round(v, 2) for h, v in _gesamtprofil().items()}
    assert ist == erwartet, (
        "Bei genau dem Wetter der Lernwoche muss das Profil bleiben, wie es ist — "
        "eine Abweichung je Stunde ist der Stundenfaktor von vor N-593"
    )


async def test_a3_export_reihe_ist_das_gelernte_wp_profil(db):
    """Die WP-Reihe des HA-Exports (Leser: P7-Heizfenster) == gelerntes WP-Profil."""
    anlage = await factories.anlage(db, latitude=51.0, longitude=11.0)
    ref = referenz_heizgradtage({f"t{i}": TAGESGANG for i in range(7)})
    daten = {
        "werktag": _gesamtprofil(), "tage_werktag": 5, "slots_werktag": 24,
        "wp_werktag": WP_PROFIL, "referenz_hdd_kd": ref,
    }
    times = [f"2026-03-18T{h:02d}:00" for h in range(24)]
    forecast = ({"hourly": {"time": times, "temperature_2m": TAGESGANG}}, None, True)
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=forecast),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=daten)
        ergebnis = await verbrauchsprognose_heute(anlage, db, now=_MITTWOCH)

    assert ergebnis is not None
    assert ergebnis.wp_stunden_kwh == [round(WP_PROFIL[h], 2) for h in range(24)]
    assert ergebnis.summe_kwh == pytest.approx(round(sum(_gesamtprofil().values()), 1))


class _FesterTag(date):
    """``date.today()`` des Lernpfads, festgenagelt — keine echte Uhr (N-167)."""

    @classmethod
    def today(cls):  # noqa: D401
        return cls(2026, 3, 18)


async def test_a4_ueber_den_lernpfad_hinweg_invariant(db, monkeypatch):
    """Lernwoche aus der DB (7 Tage, Tagesgang 7–17 °C) ⇒ Referenz 3,0 Kd ⇒
    derselbe Tagesgang als Vorhersage lässt das gelernte Profil stehen."""
    from backend.services import live_verbrauchsprofil_service as lvps

    monkeypatch.setattr(lvps, "date", _FesterTag)
    anlage = Anlage(anlagenname="N-593", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    for i in range(1, 8):
        d = date(2026, 3, 18) - timedelta(days=i)
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=d, stunde=h, source_provenance={},
                verbrauch_kw=_gesamtprofil()[h], waermepumpe_kw=WP_PROFIL[h],
                temperatur_c=TAGESGANG[h],
            ))
    await db.commit()

    gelernt = await lvps._profil_from_db(anlage.id, db)
    assert gelernt is not None
    assert gelernt["referenz_hdd_kd"] == pytest.approx(3.0)
    assert "referenz_temp_c" not in gelernt, "der Nenner der Stundenformel ist weg"

    profil, _, _, _ = _berechne_verbrauchsprofil(
        _stunden(TAGESGANG), kwp=10.0,
        individuelles_profil=gelernt["werktag"], wp_profil=gelernt["wp_werktag"],
        referenz_hdd_kd=gelernt["referenz_hdd_kd"],
    )
    ist = {int(p["zeit"][:2]): p["verbrauch_kw"] for p in profil}
    assert ist == {h: round(v, 2) for h, v in gelernt["werktag"].items()}


# ── (b) Konvexität ──────────────────────────────────────────────────────────

def test_b1_referenz_ist_das_mittel_der_tageswerte():
    """3 Tage Ø 5 °C (10 Kd) und 4 Tage Ø 20 °C (0 Kd): Referenz 30/7 Kd —
    die Heizgradtage des Wochenmittels (13,57 °C ⇒ 1,43 Kd) wären ein Drittel davon."""
    woche = {i: [5.0] * 24 for i in range(3)} | {i: [20.0] * 24 for i in range(3, 7)}
    ref = referenz_heizgradtage(woche)
    assert ref == pytest.approx(30.0 / 7.0)
    wochenmittel = (3 * 5.0 + 4 * 20.0) / 7.0
    assert ref > heizgradtage_tag(wochenmittel) * 2.5


async def test_b2_lernpfad_mittelt_tageswerte(db, monkeypatch):
    """Dieselbe Woche über den DB-Lernpfad — der Ort, an dem der Defekt saß."""
    from backend.services import live_verbrauchsprofil_service as lvps

    monkeypatch.setattr(lvps, "date", _FesterTag)
    anlage = Anlage(anlagenname="N-593b", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    for i in range(1, 8):
        d = date(2026, 3, 18) - timedelta(days=i)
        t = 5.0 if i <= 3 else 20.0
        for h in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage.id, datum=d, stunde=h, source_provenance={},
                verbrauch_kw=1.0, waermepumpe_kw=0.5, temperatur_c=t,
            ))
    await db.commit()

    gelernt = await lvps._profil_from_db(anlage.id, db)
    assert gelernt["referenz_hdd_kd"] == pytest.approx(30.0 / 7.0)


def test_b3_tag_ohne_temperatur_zaehlt_nicht_mit():
    assert referenz_heizgradtage({"a": [5.0], "b": []}) == pytest.approx(10.0)
    assert referenz_heizgradtage({"a": [], "b": []}) is None


# ── (c) Kälter: ein Faktor für jede Stunde ──────────────────────────────────

def test_c_kaelter_ergibt_1_5_fuer_jede_stunde():
    """Referenz 10 Kd, Tag Ø 0 °C (Tagesgang −5…+5) ⇒ ×1,5 auf den WP-Anteil
    jeder Stunde — die kalte Nachtstunde bekommt nicht mehr als die milde."""
    tag = [-5.0 + 10.0 * h / 23.0 for h in range(24)]
    tag = [t - sum(tag) / 24.0 for t in tag]           # Ø exakt 0 °C
    assert wp_tagesfaktor(10.0, tag) == pytest.approx(1.5)

    profil, _, _, _ = _berechne_verbrauchsprofil(
        _stunden(tag), kwp=10.0,
        individuelles_profil=_gesamtprofil(), wp_profil=WP_PROFIL,
        referenz_hdd_kd=10.0,
    )
    for p in profil:
        h = int(p["zeit"][:2])
        assert p["verbrauch_kw"] == round(HAUS + WP_PROFIL[h] * 1.5, 2), p


# ── Degradation (Vorlage §4) ────────────────────────────────────────────────

def test_stunde_ohne_temperatur_bleibt_unkorrigiert():
    tag = [0.0] * 24
    tag[3] = None
    profil, _, _, _ = _berechne_verbrauchsprofil(
        _stunden(tag), kwp=10.0,
        individuelles_profil=_gesamtprofil(), wp_profil=WP_PROFIL,
        referenz_hdd_kd=10.0,
    )
    ist = {int(p["zeit"][:2]): p["verbrauch_kw"] for p in profil}
    assert ist[3] == round(HAUS + WP_PROFIL[3], 2)
    assert ist[4] == round(HAUS + WP_PROFIL[4] * 1.5, 2)


def test_ohne_referenz_oder_ohne_temperatur_faktor_eins():
    assert wp_tagesfaktor(None, TAGESGANG) == 1.0
    assert wp_tagesfaktor(3.0, [None] * 24) == 1.0
    assert wp_tagesfaktor(3.0, []) == 1.0
