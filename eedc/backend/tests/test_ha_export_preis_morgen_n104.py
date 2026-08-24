"""N-104: der Preis-Export liefert auch den Folgetag — sobald es ihn gibt.

**Was vorher fehlte.** `berechne_preis_export` rief `bewerte_preistag` mit
`now.date()` und damit nur für heute, während dieselbe Funktion jedes Datum
annimmt und der Preis-Chart auf *Cockpit → Live* längst beide Tage zeigt. Wer in
HA die Nachtladung für morgen planen wollte, hatte die Kurve nicht — Melder ist
**rapahl**, der sich dafür einen eigenen Template-Sensor gebaut hat
(`ladepreis akku morgen`).

**Warum hier keine Uhr gestellt wird.** Die Proben patchen die **Naht**
(`preis_tag.jetzt_im_markt`) statt die Prozessuhr — `freezegun` ist am 23.08.
ausgeschlossen worden, und eine Probe, die `datetime.now()` liest, wettet auf die
Stunde ihres Laufs (N-167). Die Marktdaten kommen ebenfalls aus einem Stub, damit
die echte Bewertungslogik läuft und nicht mitgestubbt wird.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.services import preis_tag as pt
from backend.services import solar_forecast_service as sfs
from backend.services import strompreis_markt_service as sms
from backend.services.ha_export_preis import berechne_preis_export
from backend.tests import factories

# Ein fester Tag, keine Prozessuhr. Der 15. liegt weit von jeder Monats- oder
# Jahresgrenze — der Folgetag ist damit immer derselbe Monat.
HEUTE = date(2026, 3, 15)
MORGEN = HEUTE + timedelta(days=1)
_TZ = ZoneInfo("Europe/Berlin")

# Heute teuer am Abend, morgen nachts billig — zwei verschieden geformte Tage,
# damit sich die Tages-Schwellen messbar unterscheiden MÜSSEN. Ein Profil, das
# für beide Tage denselben Ø benutzt, fällt genau daran auf.
PREISE_HEUTE = {h: 20.0 + h for h in range(24)}
PREISE_MORGEN = {h: 5.0 + h * 0.5 for h in range(24)}


@pytest.fixture
def markt_stub(monkeypatch):
    """Marktpreise aus dem Stub, mit Aufrufzähler je Datum."""
    abrufe: list[date] = []

    async def _fetch(datum, markt="DE", timeout=15.0):
        abrufe.append(datum)
        if datum == HEUTE:
            return dict(PREISE_HEUTE)
        if datum == MORGEN:
            return dict(PREISE_MORGEN)
        return None

    monkeypatch.setattr(sms, "fetch_marktpreise", _fetch)
    monkeypatch.setattr(sfs, "sonnenauf_unter_stunde", lambda *a, **k: (7, 19))
    return abrufe


def _uhr(monkeypatch, stunde: int) -> None:
    """Setzt die Marktzeit — die Naht, nicht die Prozessuhr."""
    monkeypatch.setattr(
        pt, "jetzt_im_markt",
        lambda markt: datetime(HEUTE.year, HEUTE.month, HEUTE.day, stunde, tzinfo=_TZ),
    )


async def _anlage(db):
    return await factories.anlage(
        db, latitude=52.52, longitude=13.40, standort_land="DE",
        guenstig_schwelle_prozent=10.0,
    )


@pytest.mark.asyncio
async def test_heute_traegt_seinen_kalendertag(db, monkeypatch, markt_stub):
    """Ein Rang-Profil ohne Datum ist nach Mitternacht nicht datierbar."""
    _uhr(monkeypatch, 10)
    werte = await berechne_preis_export(db, await _anlage(db))
    assert werte is not None
    assert werte["datum"] == HEUTE.isoformat()
    assert len(werte["rang_profil"]) == 24


@pytest.mark.asyncio
async def test_vor_der_auktion_wird_morgen_NICHT_abgefragt(db, monkeypatch, markt_stub):
    """Der 13-Uhr-Riegel — und er ist am Aufrufzähler belegt, nicht am Ergebnis.

    `fetch_marktpreise` cacht ein **leeres** Ergebnis nicht. Ohne den Riegel
    ginge jeder Publish-Takt vor der Veröffentlichung erneut an die Markt-API
    (Takt-Default 60 min, konfigurierbar bis 5).
    """
    _uhr(monkeypatch, pt.DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE - 1)
    werte = await berechne_preis_export(db, await _anlage(db))
    assert werte is not None
    assert werte["morgen_verfuegbar"] is False
    assert "rang_profil_morgen" not in werte
    assert MORGEN not in markt_stub, (
        f"Morgen wurde vor {pt.DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE} Uhr abgefragt: "
        f"{markt_stub}"
    )


@pytest.mark.asyncio
async def test_ab_der_auktion_reist_morgen_vollstaendig_mit(db, monkeypatch, markt_stub):
    """Profil, Schwelle, Bezugsgröße und Datum — sonst ist nichts rechenbar."""
    _uhr(monkeypatch, pt.DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE)
    werte = await berechne_preis_export(db, await _anlage(db))
    assert werte is not None
    assert werte["morgen_verfuegbar"] is True
    assert werte["datum_morgen"] == MORGEN.isoformat()
    assert len(werte["rang_profil_morgen"]) == 24
    assert werte["guenstig_schwelle_cent_morgen"] is not None
    assert werte["optimierter_durchschnitt_cent_morgen"] is not None
    # Gleiche Gestalt wie heute — eine Automation liest beide mit demselben Code.
    assert set(werte["rang_profil_morgen"][0]) == set(werte["rang_profil"][0])


@pytest.mark.asyncio
async def test_jeder_tag_hat_seine_eigene_schwelle(db, monkeypatch, markt_stub):
    """Day-Ahead ist ein Tagesprodukt (Klassen-Docstring `PreisTag`).

    Ein gemeinsamer Ø über 48 Stunden würde am teuren Tag keine einzige günstige
    Stunde ausweisen und am billigen fast alle. Die beiden Stub-Tage sind deshalb
    verschieden geformt — hier wird gemessen, dass das ankommt.
    """
    _uhr(monkeypatch, pt.DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE)
    werte = await berechne_preis_export(db, await _anlage(db))
    assert werte["guenstig_schwelle_cent"] > werte["guenstig_schwelle_cent_morgen"], (
        "Heute ist im Stub deutlich teurer als morgen — die Schwellen müssen sich "
        f"unterscheiden: {werte['guenstig_schwelle_cent']} / "
        f"{werte['guenstig_schwelle_cent_morgen']}"
    )
    assert (
        werte["optimierter_durchschnitt_cent"]
        > werte["optimierter_durchschnitt_cent_morgen"]
    )


@pytest.mark.asyncio
async def test_ohne_veroeffentlichte_preise_sagt_er_es(db, monkeypatch):
    """Nach 13 Uhr, aber die Auktion liefert (noch) nichts: kein Halbsatz.

    `morgen_verfuegbar` ist **immer** gesetzt — eine Automation soll „noch nicht
    da" nicht daran erkennen müssen, dass ein Attribut fehlt.
    """
    async def _nur_heute(datum, markt="DE", timeout=15.0):
        return dict(PREISE_HEUTE) if datum == HEUTE else None

    monkeypatch.setattr(sms, "fetch_marktpreise", _nur_heute)
    monkeypatch.setattr(sfs, "sonnenauf_unter_stunde", lambda *a, **k: (7, 19))
    _uhr(monkeypatch, 18)
    werte = await berechne_preis_export(db, await _anlage(db))
    assert werte is not None
    assert werte["morgen_verfuegbar"] is False
    for schluessel in (
        "datum_morgen", "rang_profil_morgen",
        "guenstig_schwelle_cent_morgen", "optimierter_durchschnitt_cent_morgen",
    ):
        assert schluessel not in werte, schluessel


@pytest.mark.asyncio
async def test_heutige_werte_sind_unveraendert(db, monkeypatch, markt_stub):
    """Der Morgen-Satz kommt HINZU — kein bestehender Wert verschiebt sich.

    Der Sensor ist ausgeliefert und läuft in fremde Automationen; deshalb steht
    hier namentlich, was unverändert bleibt.
    """
    _uhr(monkeypatch, pt.DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE)
    werte = await berechne_preis_export(db, await _anlage(db))
    for schluessel in (
        "preis_rang", "guenstige_stunden_anzahl", "guenstige_stunden_tag",
        "guenstige_stunden_nacht", "guenstig_schwelle_cent", "preis_aktuell_cent",
        "tages_durchschnitt_cent", "optimierter_durchschnitt_cent",
        "abstand_prozent", "abstand_cent", "rang_profil",
    ):
        assert schluessel in werte, schluessel
    # Die laufende Stunde ist die von HEUTE, nicht die von morgen.
    assert werte["preis_aktuell_cent"] == PREISE_HEUTE[
        pt.DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE
    ]


@pytest.mark.asyncio
async def test_die_attribute_erreichen_den_sensor(db, monkeypatch, markt_stub):
    """Bis in die Attribut-Form — REST und MQTT teilen diesen Produzenten."""
    from backend.api.routes import ha_export as he

    # Der Prognose-Block derselben Funktion läuft sonst in die Netzsperre und
    # wartet auf DNS-Timeouts — 26 s für eine Probe, die den Preis-Sensor prüft.
    # Er ist hier nicht der Gegenstand; `test_ha_export_prognose_150.py` deckt ihn.
    # ⚠ Gepatcht wird `ha_export.berechne_prognose_export`, NICHT das
    # Herkunftsmodul: `ha_export.py:94` bindet den Namen beim Import, ein Patch
    # an `services/ha_export_prognose` erreicht die Aufrufstelle nicht (erst
    # gemessen, dann korrigiert — 26 s blieben 26 s).
    async def _keine_prognose(*a, **k):
        return None

    monkeypatch.setattr(he, "berechne_prognose_export", _keine_prognose)
    calculate_anlage_sensors = he.calculate_anlage_sensors

    _uhr(monkeypatch, pt.DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE)
    a = await _anlage(db)
    # `calculate_anlage_sensors` liefert ohne eine einzige Monatszeile GAR nichts
    # (`ha_export.py:322`) — auch keine Preis-Sensoren, obwohl Börsenpreise mit
    # Monatsdaten nichts zu tun haben. Hier nur Voraussetzung, kein Gegenstand.
    await factories.monatsdaten(db, a.id, 2026, 2, netzbezug_kwh=100.0)
    await db.commit()
    werte = await calculate_anlage_sensors(db, a)
    rang = [w for w in werte if w.definition.key == "eedc_preis_rang"]
    assert len(rang) == 1, [w.definition.key for w in werte]
    attribute = rang[0].zusatz_attribute or {}
    assert attribute.get("morgen_verfuegbar") is True
    assert attribute.get("datum") == HEUTE.isoformat()
    assert attribute.get("datum_morgen") == MORGEN.isoformat()
    assert len(attribute.get("rang_profil_morgen") or []) == 24
    assert attribute.get("guenstig_schwelle_cent_morgen") is not None
