"""N-388: der vorläufige Strahlungswert wird nachgezogen — und nichts dabei verkürzt.

**Der Defekt.** Die Wetterzeile der letzten fünf Tage kommt vom Forecast-Endpunkt
(das ERA5-Archiv hinkt 2–5 Tage nach) und wurde **nie** durch den endgültigen
Wert ersetzt: `wetter_backfill_service` ist strikt additiv und kennt
`globalstrahlung_wm2` gar nicht. An Gernots Anlage über 91 Tage gemessen —
Median-Faktor 1,00, aber ein Schwanz bis **8,70×**, und **jeder** Tag mit einer
Performance Ratio > 1 liegt darin. Die Anlage stand damit bei 6 von 31 Tagen =
19,35 % gegen die 20-%-Schwelle des Doppelerfassungs-Verdachts — einen bewölkten
Tag vor einer Falschmeldung.

**Was hier gewächtert wird — beide Hälften:**

1. Der **Grenztag** ist der eine Tag, der die Archiv-Grenze in dieser Nacht
   passiert hat, und er wird aus `ARCHIVE_LAG_TAGE` **abgeleitet**, nicht als
   Konstante geschrieben. Für ihn holt `_get_wetter_ist` das Archiv, für den Tag
   davor noch den Forecast. Die berichtigte Strahlung zieht die PR mit.
2. Der **Vorflug**. Dieser Job macht den Scheduler zum ersten Mal zum Schreiber
   historischer Tage — genau die Annahme, mit der `aggregator.py` begründet,
   warum der Scheduler-Pfad *nicht* gegen Komponenten-Verlust geschützt ist.
   Deckt die HA-Historie den Tag inzwischen nur noch teilweise ab
   (`purge_keep_days` ≈ 6), muss der Tag **übersprungen** werden, statt einen
   vollständigen Tag durch einen verkürzten zu ersetzen. Eine **leere** Kurve
   ist dabei kein Abbruchgrund — das ist der Normalfall reiner MQTT-Anlagen.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import (
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.energie_profil.archiv_nachzug import (
    archiv_grenztag,
    archiv_nachzug_all,
    kurven_stunden,
)
from backend.services.wetter_backfill_service import ARCHIVE_LAG_TAGE, archive_cutoff
from backend.tests import factories

@pytest.fixture
def job_session(monkeypatch, db):
    """Lenkt das `get_session` des Nachzug-Jobs auf die Test-DB um.

    Der Modul-lokale Name wird gepatcht, nicht `backend.core.database` — der
    Import ist dort bereits gebunden, ein Patch an der Quelle liefe ins Leere.
    """

    @asynccontextmanager
    async def _fake():
        yield db
        await db.commit()

    monkeypatch.setattr(
        "backend.services.energie_profil.archiv_nachzug.get_session", _fake
    )
    return db


KWP = 10.0
PV_STUNDE = 12
PV_KWH = 6.0
GTI_VORLAEUFIG = 229.0   # der reale Forecast-Wert vom 18.08. an Gernots Anlage
GTI_ARCHIV = 1992.0      # derselbe Tag aus ERA5 — Faktor 8,70


# ══════════════════════════════════════════════════════════════════════════
# 1 · Der Grenztag folgt der Cutoff-Formel
# ══════════════════════════════════════════════════════════════════════════

def test_grenztag_ist_der_tag_der_die_grenze_gerade_passiert_hat() -> None:
    """Nicht „heute − 6", sondern die Ableitung aus `ARCHIVE_LAG_TAGE`.

    Beidseitig geprüft: heute geht der Grenztag ins Archiv, gestern wurde
    er noch vom Forecast bedient. Änderte sich der Lag, müsste der Grenztag
    mitwandern — eine hart geschriebene 6 täte das nicht.
    """
    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)

    assert grenztag == heute - timedelta(days=ARCHIVE_LAG_TAGE + 1)
    assert grenztag < archive_cutoff(heute), (
        "Heute muss der Grenztag ins Archiv fallen — sonst zieht der Nachzug "
        "denselben vorläufigen Forecast-Wert erneut."
    )
    assert grenztag >= archive_cutoff(heute - timedelta(days=1)), (
        "Gestern war er noch VOR der Grenze. Liegt er auch gestern schon "
        "dahinter, ist der Job einen Tag zu spät und lässt einen Tag aus."
    )


def test_grenztag_haengt_nicht_an_einer_konstante() -> None:
    """Gegenprobe zur Ableitung: ein anderer Lag verschiebt den Grenztag mit."""
    heute = date(2026, 9, 4)
    with patch(
        "backend.services.energie_profil.archiv_nachzug.ARCHIVE_LAG_TAGE", 3
    ):
        assert archiv_grenztag(heute) == date(2026, 8, 31)


# ══════════════════════════════════════════════════════════════════════════
# 2 · Für den Grenztag wird das Archiv gefragt, für den Tag davor der Forecast
# ══════════════════════════════════════════════════════════════════════════

def _antwort(gti: float) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"hourly": {
        "time": [f"2026-08-18T{h:02d}:00" for h in range(24)],
        "temperature_2m": [15.0] * 24,
        "shortwave_radiation": [gti if h == PV_STUNDE else 0.0 for h in range(24)],
        "global_tilted_irradiance": [gti if h == PV_STUNDE else 0.0 for h in range(24)],
        "cloud_cover": [80.0] * 24,
        "precipitation": [0.0] * 24,
        "weather_code": [3] * 24,
    }})
    return resp


class _UrlSammler:
    """Fängt die von `_get_wetter_ist` gewählte URL ab."""

    def __init__(self, gti: float) -> None:
        self.urls: list[str] = []
        self._gti = gti

    def __call__(self, *_a, **_kw):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        async def _get(url, params=None):
            self.urls.append(url)
            return _antwort(self._gti)

        client.get = _get
        return client


@pytest.mark.asyncio
async def test_grenztag_fragt_das_archiv_der_tag_davor_den_forecast() -> None:
    """Das ist der Kern des Funds: die Grenze trennt zwei Endpunkte.

    Ohne diese Trennung gäbe es das Problem nicht — und ohne einen Nachzug
    über die Grenze hinweg bleibt der vorläufige Wert für immer stehen.
    """
    from backend.services.energie_profil._helpers import _get_wetter_ist

    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)
    anlage = factories.mach_anlage_mit_mapping("Grenztag")
    anlage.latitude, anlage.longitude = 49.7, 7.9

    sammler = _UrlSammler(GTI_ARCHIV)
    with patch("httpx.AsyncClient", new=sammler), patch(
        "backend.services.wetter_backfill_service.date"
    ) as d1:
        d1.today.return_value = heute
        await _get_wetter_ist(anlage, grenztag)
        await _get_wetter_ist(anlage, grenztag + timedelta(days=1))

    assert "archive-api.open-meteo.com" in sammler.urls[0], (
        f"Der Grenztag muss aus dem Archiv kommen, gefragt wurde {sammler.urls[0]}."
    )
    assert sammler.urls[1].endswith("/forecast"), (
        "Der Tag INNERHALB der Grenze bleibt beim Forecast — das Archiv hat ihn "
        f"noch nicht. Gefragt wurde {sammler.urls[1]}."
    )


# ══════════════════════════════════════════════════════════════════════════
# 3 · Die berichtigte Strahlung zieht die Performance Ratio mit
# ══════════════════════════════════════════════════════════════════════════

def _wetter(gti: float) -> dict:
    return {
        h: {
            "temperatur_c": 15.0,
            "globalstrahlung_wm2": gti if h == PV_STUNDE else 0.0,
            "gti_wm2": gti if h == PV_STUNDE else 0.0,
            "bewoelkung_prozent": 80.0,
            "niederschlag_mm": 0.0,
            "wetter_code": 3,
        }
        for h in range(24)
    }


def _lts_nur_in_slot(slot: int, kwh: float) -> dict:
    leer = {
        "pv": 0.0, "einspeisung": 0.0, "netzbezug": 0.0, "verbrauch": 0.0,
        "wp": None, "wallbox": None, "batterie_netto": 0.0,
        "verbrauch_sonstiges": None,
    }
    return {h: (dict(leer, pv=kwh) if h == slot else dict(leer)) for h in range(24)}


async def _anlage_mit_tag(
    db, name: str, tag: date, *, gti: float, stunden: int = 24,
) -> Anlage:
    """Legt eine Anlage an und aggregiert `tag` einmal mit `gti`."""
    anlage = factories.mach_anlage_mit_mapping(name)
    anlage.leistung_kwp = KWP
    anlage.latitude, anlage.longitude = 49.7, 7.9
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="pv",
        aktiv=True, anschaffungsdatum=date(2020, 1, 1), leistung_kwp=KWP,
    ))
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(tag, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.commit()

    await _aggregiere(db, anlage, tag, gti=gti)
    if stunden != 24:
        tz = await _tz(db, anlage.id, tag)
        tz.stunden_verfuegbar = stunden
        await db.commit()
    return anlage


async def _aggregiere(db, anlage: Anlage, tag: date, *, gti: float) -> None:
    from backend.services.energie_profil._helpers import StrompreisStunden
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source

    with _quellen_mocks(gti):
        await aggregate_day(anlage, tag, db, source=Source.SCHEDULER)
    await db.commit()


def _quellen_mocks(gti: float, punkte: list | None = None):
    from contextlib import ExitStack

    from backend.services.energie_profil._helpers import StrompreisStunden

    stack = ExitStack()
    for ziel, wert in (
        ("backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
         _lts_nur_in_slot(PV_STUNDE, PV_KWH)),
        ("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts", {}),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.energie_profil._helpers._get_strompreis_stunden",
         StrompreisStunden(sensor={}, boerse={})),
        ("backend.services.energie_profil._helpers._get_wetter_ist", _wetter(gti)),
        ("backend.services.live_power_service.LivePowerService.get_tagesverlauf",
         {"serien": [], "punkte": punkte or [], "vortagsrand": []}),
    ):
        stack.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    return stack


async def _tz(db, anlage_id: int, tag: date) -> TagesZusammenfassung:
    return (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id,
        TagesZusammenfassung.datum == tag,
    ))).scalars().one()


@pytest.mark.asyncio
async def test_nachzug_berichtigt_strahlung_und_pr(db, job_session) -> None:
    """Der ganze Zweck des Funds, an der Zahl gemessen, die ihn ausgelöst hat.

    Mit dem vorläufigen Wert ergibt sich eine PR weit über 1 — genau das, was
    der Daten-Checker als „PV-Doppelerfassung" meldet. Mit dem Archivwert
    fällt sie in den plausiblen Bereich.
    """
    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)
    anlage = await _anlage_mit_tag(db, "NachzugPR", grenztag, gti=GTI_VORLAEUFIG)

    vorher = await _tz(db, anlage.id, grenztag)
    pr_vorher = vorher.performance_ratio
    assert pr_vorher is not None and pr_vorher > 1.0, (
        "Aufbau-Kontrolle: mit dem vorläufigen Wert MUSS eine unplausible PR "
        f"entstehen, sonst prüft dieser Test nichts. Gefunden: {pr_vorher}."
    )

    with _quellen_mocks(GTI_ARCHIV):
        await archiv_nachzug_all(heute)

    nachher = await _tz(db, anlage.id, grenztag)
    assert nachher.gti_summe_wh_m2 == pytest.approx(GTI_ARCHIV), (
        "Die Einstrahlung des Grenztages muss nach dem Nachzug der Archivwert "
        f"sein, gefunden {nachher.gti_summe_wh_m2}."
    )
    assert nachher.performance_ratio is not None
    assert nachher.performance_ratio < 1.0, (
        "Mit dem Archivwert muss die PR in den plausiblen Bereich fallen — "
        "sonst bleibt die Doppelerfassungs-Falschmeldung stehen. "
        f"Gefunden: {nachher.performance_ratio}."
    )


@pytest.mark.asyncio
async def test_tag_innerhalb_der_grenze_wird_nicht_angefasst(db, job_session) -> None:
    """Der Nachzug greift NUR den Grenztag — alles Jüngere ist noch vorläufig."""
    heute = date(2026, 9, 4)
    drinnen = archiv_grenztag(heute) + timedelta(days=1)
    anlage = await _anlage_mit_tag(db, "Drinnen", drinnen, gti=GTI_VORLAEUFIG)

    vorher = await _tz(db, anlage.id, drinnen)
    gti_vorher, pr_vorher = vorher.gti_summe_wh_m2, vorher.performance_ratio

    with _quellen_mocks(GTI_ARCHIV):
        await archiv_nachzug_all(heute)

    nachher = await _tz(db, anlage.id, drinnen)
    assert (nachher.gti_summe_wh_m2, nachher.performance_ratio) == (
        gti_vorher, pr_vorher,
    ), (
        "Ein Tag innerhalb der Archiv-Grenze darf nicht angefasst werden — das "
        "Archiv hat ihn noch nicht, der Nachzug schriebe denselben vorläufigen "
        "Wert erneut und verbrauchte dafür einen Abruf je Anlage und Nacht."
    )


@pytest.mark.asyncio
async def test_nachzug_ist_idempotent(db, job_session) -> None:
    """Zweiter Lauf derselben Nacht ändert nichts (Neustart, doppelter Trigger)."""
    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)
    anlage = await _anlage_mit_tag(db, "Idempotent", grenztag, gti=GTI_VORLAEUFIG)

    with _quellen_mocks(GTI_ARCHIV):
        await archiv_nachzug_all(heute)
    erst = await _tz(db, anlage.id, grenztag)
    werte = (erst.gti_summe_wh_m2, erst.performance_ratio, erst.stunden_verfuegbar)

    with _quellen_mocks(GTI_ARCHIV):
        await archiv_nachzug_all(heute)
    zweit = await _tz(db, anlage.id, grenztag)

    assert (zweit.gti_summe_wh_m2, zweit.performance_ratio,
            zweit.stunden_verfuegbar) == werte


# ══════════════════════════════════════════════════════════════════════════
# 4 · Der Vorflug
# ══════════════════════════════════════════════════════════════════════════

def test_kurven_stunden_spiegelt_die_bucket_regel_des_aggregators() -> None:
    """Der Vorflug zählt vorher genau das, was der Aggregator nachher schreibt.

    Beide gehen über `slot_konvention.leistungspfad_slot`. Ein zweiter Nachbau
    dieser Regel wäre die Klasse, aus der N-382 entstanden ist — eine Zeile,
    zwei verschiedene Stunden.
    """
    voll = [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)]
    # 00..22 → Slots 1..23, Label 23 fällt in den Folgetag, Slot 0 kommt dazu.
    assert kurven_stunden(voll, [{"zeit": "23:00", "werte": {}}]) == 24
    assert kurven_stunden(voll, []) == 24, (
        "Slot 0 existiert auch ohne Vortagsrand — sonst verlöre die Zeile 0 "
        "ihre Zähler-, Wetter- und Preiswerte."
    )
    assert kurven_stunden([], []) == 0
    # Recorder-Grenze mitten am Tag: nur noch ab 12:00.
    teil = [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(12, 24)]
    assert kurven_stunden(teil, []) == 12  # Slots 13..23 plus Slot 0


@pytest.mark.asyncio
async def test_vorflug_ueberspringt_eine_geschrumpfte_kurve(db, job_session) -> None:
    """Der eigentliche Grund, warum dieser Job einen Vorflug hat.

    `aggregator.py` begründet den fehlenden Preserve-Schutz des Scheduler-Pfads
    damit, dass er historische Tage nie anfasst. Dieser Job tut es. Deckt die
    HA-Historie den Tag nur noch teilweise ab (`purge_keep_days` ≈ 6), würde
    eine Neuaggregation einen vollständigen Tag durch einen verkürzten
    ersetzen — die Zeile muss dann unangetastet bleiben.
    """
    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)
    anlage = await _anlage_mit_tag(db, "Vorflug", grenztag, gti=GTI_VORLAEUFIG)

    vorher = await _tz(db, anlage.id, grenztag)
    gti_vorher = vorher.gti_summe_wh_m2
    zeilen_vorher = len((await db.execute(select(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage.id,
        TagesEnergieProfil.datum == grenztag,
    ))).scalars().all())

    geschrumpft = [{"zeit": f"{h:02d}:00", "werte": {"pv_1": 1.0}} for h in range(12, 23)]
    with _quellen_mocks(GTI_ARCHIV, punkte=geschrumpft):
        ergebnis = await archiv_nachzug_all(heute)

    assert ergebnis[anlage.id]["status"] == "uebersprungen"
    assert ergebnis[anlage.id]["grund"] == "kurve_geschrumpft"

    nachher = await _tz(db, anlage.id, grenztag)
    zeilen_nachher = len((await db.execute(select(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage.id,
        TagesEnergieProfil.datum == grenztag,
    ))).scalars().all())
    assert nachher.gti_summe_wh_m2 == gti_vorher, (
        "Übersprungen heißt unangetastet — auch das Wetter bleibt stehen. "
        "Eine berichtigte Strahlung ist keinen verkürzten Tag wert."
    )
    assert zeilen_nachher == zeilen_vorher


@pytest.mark.asyncio
async def test_vorflug_laesst_eine_vollstaendige_kurve_durch(db, job_session) -> None:
    """Gegenprobe: derselbe Aufbau mit vollständiger Kurve läuft durch.

    Ohne sie wäre nicht gezeigt, dass der Vorflug diskriminiert — er könnte
    schlicht immer überspringen.
    """
    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)
    anlage = await _anlage_mit_tag(db, "VorflugVoll", grenztag, gti=GTI_VORLAEUFIG)

    voll = [{"zeit": f"{h:02d}:00", "werte": {"pv_1": 1.0}} for h in range(24)]
    with _quellen_mocks(GTI_ARCHIV, punkte=voll):
        ergebnis = await archiv_nachzug_all(heute)

    assert ergebnis[anlage.id]["status"] == "ok"
    nachher = await _tz(db, anlage.id, grenztag)
    assert nachher.gti_summe_wh_m2 == pytest.approx(GTI_ARCHIV)
    assert nachher.stunden_verfuegbar == kurven_stunden(voll, []), (
        "Hier schließt sich der Vorflug: was er VORHER zählt, muss der "
        "Aggregator NACHHER schreiben. Laufen die beiden auseinander, "
        "überspringt der Vorflug entweder zu viel oder er schützt nichts."
    )


@pytest.mark.asyncio
async def test_leere_kurve_ist_kein_abbruchgrund(db, job_session) -> None:
    """Reine MQTT-Anlagen haben IMMER eine leere Leistungskurve.

    Für sie ist das der Normalweg (synthetische Slots), nicht ein Verlust —
    ein Vorflug, der auf „0 < 24" abbräche, nähme genau ihnen die Berichtigung
    weg und täte es dauerhaft und still.
    """
    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)
    anlage = await _anlage_mit_tag(db, "NurMqtt", grenztag, gti=GTI_VORLAEUFIG)

    with _quellen_mocks(GTI_ARCHIV, punkte=[]):
        ergebnis = await archiv_nachzug_all(heute)

    assert ergebnis[anlage.id]["status"] == "ok", (
        f"Leere Kurve darf nicht überspringen — gefunden {ergebnis[anlage.id]}."
    )
    nachher = await _tz(db, anlage.id, grenztag)
    assert nachher.gti_summe_wh_m2 == pytest.approx(GTI_ARCHIV)


@pytest.mark.asyncio
async def test_tag_ohne_zusammenfassung_wird_nicht_neu_erfunden(db, job_session) -> None:
    """Ein Tag, den es nie gab, wird nicht sechs Tage später erstmals angelegt.

    Das wäre neues Verhalten und nicht Gegenstand dieses Funds — dafür gibt es
    den Vollbackfill und die Reparatur-Werkbank.
    """
    heute = date(2026, 9, 4)
    grenztag = archiv_grenztag(heute)
    anlage = factories.mach_anlage_mit_mapping("OhneTag")
    anlage.leistung_kwp = KWP
    anlage.latitude, anlage.longitude = 49.7, 7.9
    db.add(anlage)
    await db.commit()

    with _quellen_mocks(GTI_ARCHIV):
        ergebnis = await archiv_nachzug_all(heute)

    assert ergebnis[anlage.id]["status"] == "kein_tag"
    assert (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage.id,
    ))).scalars().first() is None
