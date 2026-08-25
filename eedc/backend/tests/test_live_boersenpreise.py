"""Live-Börsenpreise heute + morgen (#335, Chart-Kern) — Endpunkt und geteilte Bewertung.

Der Preis-Chart auf *Cockpit → Live* und die HA-Preis-Sensoren müssen dieselbe
Antwort auf „ist diese Stunde günstig?" geben. Bis #335 gab es nur die
Sensor-Hälfte; der Chart hätte die Rang-/Schwellen-Logik im Frontend nachbauen
müssen, und genau daraus entsteht die Drift, die dieses Projekt an anderen
Kennzahlen mehrfach eingefangen hat. Beide ziehen deshalb aus
``services/preis_tag.py`` — die Probe unten hält das fest.

⚠ **Der Mock beantwortet das angefragte Datum** ([[feedback_fixture_fremde_api_braucht_quelle]],
Lehre aus F-4 und F-6): Ein festes dict würde die Frage „welchen Tag fragt eedc
eigentlich ab?" gar nicht stellen können — und genau diese Frage war der Fehler
F-6. Die **Antwortform** von ``fetch_marktpreise`` (``{stunde: ct/kWh}``, nur
Stunden mit Preis) ist am 2026-08-06 gegen die echte aWATTar-Schnittstelle
gemessen; die Wandlung EUR/MWh → ct/kWh prüft
``test_strompreis_markt_fenster.py`` an der echten Antwortform.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.api.routes.live_dashboard import (
    DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE, get_boersenpreise,
)
from backend.models import Anlage
from backend.services import preis_tag as pt
from backend.services import strompreis_markt_service as smp

BERLIN = ZoneInfo("Europe/Berlin")

# Zwei Tage mit deutlich verschiedenem Preisniveau — der billige Tag liegt
# **komplett** unter dem Ø des teuren. Ein gemeinsamer 48-Stunden-Ø würde am
# teuren Tag keine einzige und am billigen Tag jede Stunde als günstig
# ausweisen; je Tag gerechnet hat jeder Tag seine eigenen günstigen Stunden.
TEURER_TAG = date(2026, 8, 6)
BILLIGER_TAG = date(2026, 8, 7)


def _preise_teuer() -> dict[int, float]:
    # 20..43 ct; ohne die 3 Peaks Ø = 30,0 → Schwelle (10 %) = 27,0
    return {h: 20.0 + h for h in range(24)}


def _preise_billig() -> dict[int, float]:
    # 2,0..4,3 ct; ohne die 3 Peaks Ø = 3,0 → Schwelle = 2,7
    return {h: 2.0 + h / 10 for h in range(24)}


def _mock_fetch(verfuegbar: dict[date, dict[int, float]]):
    """Ersatz für ``fetch_marktpreise``, der **nach Datum** antwortet.

    Ein nicht enthaltener Tag antwortet mit ``None`` — so verhält sich die echte
    Schnittstelle vor der Day-Ahead-Veröffentlichung.
    """
    gefragt: list[date] = []

    async def _fetch(datum, markt="DE", timeout=15.0):
        gefragt.append(datum)
        return verfuegbar.get(datum)

    return _fetch, gefragt


def _stelle_uhr(monkeypatch, jetzt_berlin: datetime):
    """Setzt die Uhr der Preis-Schicht auf einen festen Zeitpunkt.

    Ohne das hinge die Probe an der Laufzeit des Testlaufs — „morgen fehlt noch"
    wäre nachmittags grün und vormittags rot.
    """
    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt_berlin.astimezone(tz) if tz else jetzt_berlin.replace(tzinfo=None)

    monkeypatch.setattr(pt, "datetime", _Uhr)


async def _anlage(db, **kwargs) -> Anlage:
    anlage = Anlage(
        anlagenname="Preis-Test",
        leistung_kwp=10.0,
        latitude=48.8,
        longitude=9.2,
        standort_land="DE",
        **kwargs,
    )
    db.add(anlage)
    await db.commit()
    await db.refresh(anlage)
    return anlage


# ── Zwei Tage auf einer Achse ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_beide_tage_werden_geliefert(db, monkeypatch):
    """Nachmittags liegen heute und morgen vor — beide kommen mit."""
    anlage = await _anlage(db)
    fetch, gefragt = _mock_fetch({TEURER_TAG: _preise_teuer(), BILLIGER_TAG: _preise_billig()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    assert [t["datum"] for t in antwort["tage"]] == ["2026-08-06", "2026-08-07"]
    assert gefragt == [TEURER_TAG, BILLIGER_TAG]
    assert antwort["hinweis"] is None
    assert antwort["heute"] == "2026-08-06"
    assert antwort["aktuelle_stunde"] == 16
    assert len(antwort["tage"][0]["stunden"]) == 24


@pytest.mark.asyncio
async def test_jeder_tag_traegt_seine_eigene_schwelle(db, monkeypatch):
    """Der billige Tag hat eigene günstige Stunden — nicht 'alle' oder 'keine'.

    Das ist die Probe gegen einen gemeinsamen 48-Stunden-Ø: Läge die Schwelle
    über beide Tage, wäre am teuren Tag keine Stunde günstig und am billigen
    jede — und die HA-Sensoren derselben Anlage sagten etwas anderes.
    """
    anlage = await _anlage(db)
    fetch, _ = _mock_fetch({TEURER_TAG: _preise_teuer(), BILLIGER_TAG: _preise_billig()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    tage = (await get_boersenpreise(anlage.id, db))["tage"]

    assert tage[0]["schwelle_cent"] == pytest.approx(27.0)
    assert tage[1]["schwelle_cent"] == pytest.approx(2.7)
    assert tage[0]["optimierter_durchschnitt_cent"] == pytest.approx(30.0)
    # rapahl-PN 2026-08-23: der schlichte Tages-Ø steht DANEBEN, nicht statt
    # dessen — und er ist eine andere Zahl. 20…43 ct ⇒ Ø = 31,5; ohne die drei
    # Peaks (41/42/43) ⇒ 30,0. Wären beide gleich, prüfte die Zeile nichts.
    assert tage[0]["tages_durchschnitt_cent"] == pytest.approx(31.5)
    assert tage[1]["tages_durchschnitt_cent"] == pytest.approx(3.15)
    assert (
        tage[0]["tages_durchschnitt_cent"] != tage[0]["optimierter_durchschnitt_cent"]
    ), "Tages-Ø und optimierter Ø müssen unterscheidbar bleiben"
    # ⚠ Die Schwelle hängt WEITERHIN am optimierten Ø, nicht am neuen Wert —
    # sonst hätte die neue Kachel Rainers eigene Günstig-Definition verschoben.
    assert tage[0]["schwelle_cent"] == pytest.approx(
        tage[0]["optimierter_durchschnitt_cent"] * 0.9
    )
    # N-173: der ct-Abstand jeder Stunde bezieht sich auf den Ø DIESES Tages —
    # sonst trüge der billige Tag die Abstände des teuren.
    for tag in tage:
        for s in tag["stunden"]:
            assert s["abstand_cent"] == pytest.approx(
                s["preis_cent"] - tag["optimierter_durchschnitt_cent"], abs=0.01
            )
    for tag in tage:
        guenstig = [s["stunde"] for s in tag["stunden"] if s["unter_schwelle"]]
        assert 0 < len(guenstig) < len(tag["stunden"]), (
            f"{tag['datum']}: weder alle noch keine Stunde günstig"
        )


@pytest.mark.asyncio
async def test_guenstig_ist_nicht_auf_fuenf_gedeckelt(db, monkeypatch):
    """`unter_schwelle` ist ungekappt, der Rang bleibt auf 1–5 begrenzt (N-103).

    Beide Größen stehen nebeneinander in derselben Stunde; wer sie verwechselt,
    zeichnet zu wenige Stunden grün. Der Deckel gilt **je Fenster** (Tag und
    Nacht werden getrennt gerankt) — die billigen Stunden liegen hier deshalb
    alle im Nachtfenster, sonst prüfte die Probe zwei Deckel als einen.
    """
    from backend.core.berechnungen.preis_rang import GUENSTIG_TOP_N
    from backend.services.solar_forecast_service import sonnenauf_unter_stunde

    anlage = await _anlage(db)
    # Fenstergrenzen aus derselben Quelle wie der Produktionscode, statt sie zu
    # raten — sie wandern saisonal, eine geratene Grenze macht die Probe brüchig.
    sa, su = sonnenauf_unter_stunde(TEURER_TAG.isoformat(), 48.8, 9.2)
    nacht = [h for h in range(24) if not (sa <= h < su)]
    assert len(nacht) > GUENSTIG_TOP_N, "sonst kann die Probe gar nichts zeigen"
    # Nacht billig (1 ct), Tag teuer (10 ct): ohne die 3 Peaks liegt der Ø weit
    # über 1 ct, alle Nachtstunden fallen also unter die Schwelle.
    preise = {h: (1.0 if h in nacht else 10.0) for h in range(24)}
    fetch, _ = _mock_fetch({TEURER_TAG: preise})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    stunden = (await get_boersenpreise(anlage.id, db))["tage"][0]["stunden"]

    guenstig = [s["stunde"] for s in stunden if s["unter_schwelle"]]
    mit_rang = [s["stunde"] for s in stunden if s["rang"] != 99]
    assert sorted(guenstig) == sorted(nacht), "jede Nachtstunde unter der Schwelle zählt"
    assert len(mit_rang) == GUENSTIG_TOP_N, "der Rang bleibt bei fünf je Fenster gedeckelt"
    assert len(guenstig) > len(mit_rang), (
        "genau der Unterschied, den N-103 beschreibt — der Chart darf nicht dem Rang folgen"
    )


# ── ADR-002/P4: eine fehlende Hälfte sagt, dass sie fehlt ───────────────────

@pytest.mark.asyncio
async def test_vormittags_fehlt_morgen_und_der_hinweis_sagt_warum(db, monkeypatch):
    """Vor der Auktion gibt es morgen nicht — das wird benannt, nicht verschwiegen."""
    anlage = await _anlage(db)
    fetch, gefragt = _mock_fetch({TEURER_TAG: _preise_teuer()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 9, 0, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    assert [t["datum"] for t in antwort["tage"]] == ["2026-08-06"]
    assert BILLIGER_TAG in gefragt, "morgen wird gefragt, nicht vorab weggelassen"
    assert antwort["hinweis"] is not None
    assert str(DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE) in antwort["hinweis"]
    assert "morgen" in antwort["hinweis"]


@pytest.mark.asyncio
async def test_nachmittags_ohne_morgen_nennt_keine_uhrzeit_mehr(db, monkeypatch):
    """Nach 13 Uhr ist 'kommt gegen 13 Uhr' falsch — der Hinweis wechselt.

    Sonst stünde nachmittags eine Zusage im Block, die der Tag nicht mehr
    einlösen kann.
    """
    anlage = await _anlage(db)
    fetch, _ = _mock_fetch({TEURER_TAG: _preise_teuer()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 18, 0, tzinfo=BERLIN))

    hinweis = (await get_boersenpreise(anlage.id, db))["hinweis"]

    assert hinweis is not None
    assert str(DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE) not in hinweis


@pytest.mark.asyncio
async def test_gar_keine_preise_liefert_leere_tage_mit_grund(db, monkeypatch):
    """Keine Kurve ⇒ keine erfundene Kurve, aber auch kein stummes Nichts."""
    anlage = await _anlage(db)
    fetch, _ = _mock_fetch({})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    assert antwort["tage"] == []
    assert antwort["hinweis"] is not None


@pytest.mark.asyncio
async def test_ohne_koordinaten_keine_bewertung(db, monkeypatch):
    """Ohne Standort gibt es kein Tag-/Nachtfenster — und keine halbe Antwort."""
    anlage = Anlage(anlagenname="Ohne Ort", leistung_kwp=10.0, standort_land="DE")
    db.add(anlage)
    await db.commit()
    await db.refresh(anlage)
    fetch, gefragt = _mock_fetch({TEURER_TAG: _preise_teuer()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    assert antwort["tage"] == []
    assert antwort["hinweis"] is not None
    assert gefragt == [], "ohne Koordinaten wird die Marktquelle gar nicht erst gefragt"


# ── Die eine Wahrheit: Chart und HA-Sensor markieren dieselben Stunden ──────

@pytest.mark.asyncio
async def test_chart_und_ha_sensor_markieren_dieselben_stunden(db, monkeypatch):
    """Der Grund, warum ``preis_tag.py`` existiert — als Test, nicht als Absicht.

    Beide Pfade werden mit derselben gestellten Uhr und derselben Preisquelle
    gefahren; jede Stunde muss in beiden dieselbe Günstig-Markierung und
    denselben Rang tragen.
    """
    from backend.services.ha_export_preis import berechne_preis_export

    anlage = await _anlage(db, guenstig_schwelle_prozent=15.0)
    fetch, _ = _mock_fetch({TEURER_TAG: _preise_teuer(), BILLIGER_TAG: _preise_billig()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    chart = (await get_boersenpreise(anlage.id, db))["tage"][0]
    sensor = await berechne_preis_export(db, anlage)

    assert sensor is not None
    assert chart["schwelle_cent"] == sensor["guenstig_schwelle_cent"]
    assert chart["optimierter_durchschnitt_cent"] == sensor["optimierter_durchschnitt_cent"]
    aus_chart = {(s["stunde"], s["rang"], s["unter_schwelle"]) for s in chart["stunden"]}
    aus_sensor = {(s["stunde"], s["rang"], s["unter_schwelle"]) for s in sensor["rang_profil"]}
    assert aus_chart == aus_sensor
    # N-173: auch der ct-Abstand ist in beiden Pfaden derselbe — sonst nennt die
    # Live-Kachel eine andere Zahl als der Sensor, auf den die Automation hört.
    assert (
        {(s["stunde"], s["abstand_cent"]) for s in chart["stunden"]}
        == {(s["stunde"], s["abstand_cent"]) for s in sensor["rang_profil"]}
    )
    # Und die anlagen-eigene Schwelle wirkt in beiden: 15 % statt der Default-10 %.
    assert chart["schwelle_cent"] == pytest.approx(30.0 * 0.85)


# ── Zeitumstellung: 23 Stunden sind ein richtiger Tag ───────────────────────

@pytest.mark.asyncio
async def test_kurzer_tag_wird_nicht_auf_24_aufgefuellt(db, monkeypatch):
    """Ende März hat der Tag 23 Stundenpreise — die Lücke bleibt eine Lücke.

    Eine Achse, die stur 24 Positionen zeichnet, erfindet an diesem Tag einen
    Preis für eine Stunde, die es nicht gab (F-6, Folgerung 2).
    """
    umstellung = date(2027, 3, 28)  # letzter Sonntag im März: 02:00 → 03:00
    anlage = await _anlage(db)
    kurz = {h: 20.0 + h for h in range(24) if h != 2}
    fetch, _ = _mock_fetch({umstellung: kurz})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2027, 3, 28, 16, 0, tzinfo=BERLIN))

    stunden = (await get_boersenpreise(anlage.id, db))["tage"][0]["stunden"]

    assert len(stunden) == 23
    assert 2 not in [s["stunde"] for s in stunden]


@pytest.mark.asyncio
async def test_negative_preise_bleiben_negativ(db, monkeypatch):
    """Day-Ahead wird regelmäßig negativ — am 06.08.2026 gemessen bis −0,14 ct.

    Der Endpunkt darf sie weder abschneiden noch auf 0 heben; die Stufenfärbung
    im Chart hängt daran.
    """
    anlage = await _anlage(db)
    preise = {h: (-0.14 if 12 <= h <= 15 else 10.0 + h) for h in range(24)}
    fetch, _ = _mock_fetch({TEURER_TAG: preise})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    stunden = (await get_boersenpreise(anlage.id, db))["tage"][0]["stunden"]

    negativ = [s for s in stunden if s["preis_cent"] < 0]
    assert len(negativ) == 4
    assert all(s["unter_schwelle"] for s in negativ)


# ── Der Tag der Marktzone, nicht der Prozesszone ────────────────────────────

@pytest.mark.asyncio
async def test_kurz_nach_mitternacht_ist_heute_der_tag_der_marktzone(db, monkeypatch):
    """00:30 Berlin: „heute" ist der Berliner Tag, nicht der UTC-Tag (F-6).

    Auf einem UTC-Container liegt ``date.today()`` dann noch einen Tag zurück —
    der Chart zeigte die Kurve von gestern und nannte sie heute.
    """
    anlage = await _anlage(db)
    fetch, gefragt = _mock_fetch({
        BILLIGER_TAG: _preise_billig(),
        BILLIGER_TAG + timedelta(days=1): _preise_teuer(),
    })
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 7, 0, 30, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    assert antwort["heute"] == "2026-08-07"
    assert gefragt == [BILLIGER_TAG, BILLIGER_TAG + timedelta(days=1)]


# ── Endpreis der laufenden Stunde (N-173/R2, Melder rapahl) ─────────────────
#
# Alle Kacheln dieses Blocks zeigen den BÖRSENpreis. Der ist die Steuergröße
# für „wann laden", aber nicht der Preis auf der Rechnung — dazwischen liegen
# Netzentgelte, Steuern und Abgaben. Sein Wunsch: den echten Endpreis daneben,
# Börsenpreis bleibt.
#
# Die Probe sitzt bewusst auf der ROUTE und nicht auf dem Helper allein: Was
# zählt, ist das Feld in der Antwort — ein Layer-Test hätte nicht gemerkt, wenn
# es dort nie ankommt.

async def _schreibe_stundenpreis(db, anlage_id: int, datum: date, stunde: int, cent: float):
    """Eine Stunde der eigenen Mitschrift mit Endpreis füllen."""
    from backend.models.tages_energie_profil import TagesEnergieProfil
    db.add(TagesEnergieProfil(
        anlage_id=anlage_id, datum=datum, stunde=stunde, strompreis_cent=cent,
    ))
    await db.commit()


@pytest.mark.asyncio
async def test_endpreis_fehlt_ohne_strompreis_sensor(db, monkeypatch):
    """Ohne zugeordneten Strompreis-Sensor bleibt das Feld leer.

    ⚠ Das ist die eigentliche Aussage der Änderung: KEIN Rückfall auf
    ``Strompreis.netzbezug_arbeitspreis_cent_kwh``. Das Tarif-Feld ist bei
    dynamischem Tarif ein Mittelwert — ihn als „Preis dieser Stunde"
    auszugeben wäre erfundene Genauigkeit (ADR-002/P4).
    """
    anlage = await _anlage(db)
    fetch, _ = _mock_fetch({TEURER_TAG: _preise_teuer()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    assert antwort["endpreis_jetzt_cent"] is None


@pytest.mark.asyncio
async def test_endpreis_kommt_aus_der_laufenden_stunde(db, monkeypatch):
    """Der Endpreis der Antwort ist der der LAUFENDEN Stunde, nicht der davor.

    ⚠ Die Stundenkonvention ist hier die Falle, und sie hat einen Melder schon
    einmal beschäftigt: ``strompreis_cent`` wird je Stunde als Mittel über
    ``[h:00, h+1:00)`` geschrieben — **forward**, wie der Börsenpreis. Das ist
    NICHT die Backward-Konvention der Energiewerte (#144, Slot N = ``[N-1, N)``).
    Beide stehen in derselben Tabelle. Deshalb bekommen hier zwei benachbarte
    Stunden verschiedene Preise: griffe der Code eine daneben, wäre es sichtbar.
    """
    anlage = await _anlage(db)
    await _schreibe_stundenpreis(db, anlage.id, TEURER_TAG, 15, 28.0)
    await _schreibe_stundenpreis(db, anlage.id, TEURER_TAG, 16, 34.7)
    await _schreibe_stundenpreis(db, anlage.id, TEURER_TAG, 17, 41.0)
    fetch, _ = _mock_fetch({TEURER_TAG: _preise_teuer()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 30, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    assert antwort["aktuelle_stunde"] == 16
    assert antwort["endpreis_jetzt_cent"] == 34.7


@pytest.mark.asyncio
async def test_endpreis_liegt_ueber_dem_boersenpreis_derselben_stunde(db, monkeypatch):
    """Beide Preise stehen nebeneinander — und meinen verschiedene Größen.

    Der Melder soll den Aufschlag ohne Rechnen ablesen können. Die Probe hält
    fest, dass die Antwort beide trägt und sie nicht verwechselt.
    """
    anlage = await _anlage(db)
    await _schreibe_stundenpreis(db, anlage.id, TEURER_TAG, 16, 34.7)
    fetch, _ = _mock_fetch({TEURER_TAG: _preise_teuer()})
    monkeypatch.setattr(smp, "fetch_marktpreise", fetch)
    _stelle_uhr(monkeypatch, datetime(2026, 8, 6, 16, 0, tzinfo=BERLIN))

    antwort = await get_boersenpreise(anlage.id, db)

    heute = next(t for t in antwort["tage"] if t["datum"] == "2026-08-06")
    boerse_16 = next(s["preis_cent"] for s in heute["stunden"] if s["stunde"] == 16)
    assert antwort["endpreis_jetzt_cent"] == 34.7
    assert antwort["endpreis_jetzt_cent"] != boerse_16
